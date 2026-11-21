import asyncio
import wave
import numpy as np

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth import AuthContext, AuthenticatedUser, get_auth_context
from app.core.config import Settings, get_settings
from app.core.supabase import get_user_supabase
from app.main import create_app
from app.services import audd_recognition
from app.services.audio_decode import prepare_cloud_wav, InvalidAudio
from tests.test_landmark_fingerprint import melody, write_wav


def mock_provider(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(audd_recognition.httpx, "AsyncClient",
                        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


@pytest.fixture
def wav_file(tmp_path):
    path = tmp_path / "query.wav"
    write_wav(path, melody(42, 15))
    return path


def test_audd_sends_multipart_and_does_not_invent_a_confidence_score(wav_file, monkeypatch):
    def handle(request):
        assert str(request.url) == "https://api.audd.io/"
        assert "multipart/form-data" in request.headers["Content-Type"]
        assert b"private-test-token" in request.content
        assert b"RIFF" in request.content
        return httpx.Response(200, json={"status": "success", "result": {
            "title": "Test Song", "artist": "Singer", "album": "Album", "release_date": "2023-01-01",
            "spotify": {"external_urls": {"spotify": "https://open.spotify.com/track/abc123"}},
        }})
    mock_provider(monkeypatch, handle)
    result = asyncio.run(audd_recognition.recognize_audd(wav_file, "private-test-token"))
    assert result[0]["title"] == "Test Song"
    assert result[0]["year"] == 2023
    assert result[0]["score"] is None
    assert result[0]["recognition_method"] == "audd"


@pytest.mark.parametrize("result", [None, []])
def test_audd_no_match_is_not_a_service_error(wav_file, monkeypatch, result):
    mock_provider(monkeypatch, lambda _: httpx.Response(200, json={"status": "success", "result": result}))
    assert asyncio.run(audd_recognition.recognize_audd(wav_file, "test")) == []


@pytest.mark.parametrize("code, status", [(900, 503), (901, 503), (500, 422), (400, 422), (999, 503)])
def test_provider_errors_are_actionable_and_do_not_leak_credentials(wav_file, monkeypatch, code, status):
    mock_provider(monkeypatch, lambda _: httpx.Response(200, json={"status": "error", "error": {
        "error_code": code, "error_message": "secret-token-must-not-be-reflected"}}))
    with pytest.raises(HTTPException) as error:
        asyncio.run(audd_recognition.recognize_audd(wav_file, "test"))
    assert error.value.status_code == status
    assert "secret-token" not in error.value.detail


def test_provider_timeout_is_not_reported_as_no_match(wav_file, monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("secret-token", request=request)
    mock_provider(monkeypatch, timeout)
    with pytest.raises(HTTPException) as error:
        asyncio.run(audd_recognition.recognize_audd(wav_file, "test"))
    assert error.value.status_code == 503
    assert "secret-token" not in error.value.detail


def test_cloud_wav_is_clipped_to_twelve_seconds_without_ffmpeg(wav_file, tmp_path):
    output = tmp_path / "cloud.wav"
    assert prepare_cloud_wav(wav_file, output) == 12
    with wave.open(str(output), "rb") as wav:
        assert wav.getnframes() == wav.getframerate() * 12


def test_invalid_wav_rejected_before_contacting_provider(tmp_path):
    source = tmp_path / "bad.wav"
    source.write_bytes(b"not audio")
    with pytest.raises(InvalidAudio):
        prepare_cloud_wav(source, tmp_path / "output.wav")


def test_audd_clip_skips_leading_silence_without_sending_an_extra_request(tmp_path):
    source, output = tmp_path / "late-start.wav", tmp_path / "cloud.wav"
    rate = 11025
    original = melody(42, 12)
    write_wav(source, np.concatenate([np.zeros(3 * rate), original]))
    assert prepare_cloud_wav(source, output) == 12
    with wave.open(str(output), "rb") as wav:
        sent = np.frombuffer(wav.readframes(12 * rate), dtype="<i2")
    assert len(sent) == 12 * rate
    assert np.count_nonzero(sent[:rate // 2]) > rate // 4


def test_silent_recording_does_not_consume_audd_quota(tmp_path):
    source = tmp_path / "silent.wav"
    write_wav(source, np.zeros(6 * 11025))
    with pytest.raises(InvalidAudio, match="im lặng"):
        prepare_cloud_wav(source, tmp_path / "cloud.wav")


def app_for(db, token="test-token"):
    from uuid import UUID
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, recognition_mode="audd", audd_api_token=token)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=AuthenticatedUser(id=UUID("c924b932-e8d5-4fb2-9f43-0ed81066cc29")), access_token="test")
    app.dependency_overrides[get_user_supabase] = lambda: db
    return app


class HistoryDB:
    def __init__(self): self.saved = []
    async def insert(self, table, values, **kwargs):
        self.saved.append(values)
        return [{"id": "saved"}]
    async def request(self, *args, **kwargs):
        raise AssertionError("Cloud recognition must not require a local fingerprint catalog")


def test_http_wav_recognition_needs_neither_ffmpeg_nor_local_catalog(wav_file, monkeypatch):
    from app.routers import identify
    async def forbidden(*args, **kwargs):
        raise AssertionError("WAV cloud recognition must not invoke FFmpeg or local fingerprint matching")
    monkeypatch.setattr(identify, "decode_audio_async", forbidden)
    monkeypatch.setattr(identify, "_fallback_match", forbidden)
    mock_provider(monkeypatch, lambda _: httpx.Response(200, json={
        "status": "success", "result": {"title": "Recognized song", "artist": "Singer"}}))
    db = HistoryDB()
    response = TestClient(app_for(db)).post("/api/identify", files={"file": ("microphone.wav", wav_file.read_bytes(), "audio/wav")})
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["title"] == "Recognized song"
    assert response.json()["results"][0]["score"] is None
    assert response.json()["duration_seconds"] == 12
    assert db.saved[0]["results"][0]["recognition_method"] == "audd"


def test_missing_cloud_token_has_clear_error(wav_file):
    response = TestClient(app_for(HistoryDB(), token="")).post(
        "/api/identify", files={"file": ("microphone.wav", wav_file.read_bytes(), "audio/wav")})
    assert response.status_code == 503
    assert "AUDD_API_TOKEN" in response.text


def test_cloud_status_does_not_query_fingerprint_catalog():
    response = TestClient(app_for(HistoryDB())).get("/api/identify/status")
    assert response.status_code == 200
    assert response.json()["audd_configured"] is True
    assert "test-token" not in response.text
