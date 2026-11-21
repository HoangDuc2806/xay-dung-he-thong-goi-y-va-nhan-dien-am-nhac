"""Exercise actual landmark extraction through HTTP with an in-memory RPC substitute."""
from uuid import UUID
import shutil

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth import AuthContext, AuthenticatedUser, get_auth_context
from app.core.config import Settings, get_settings
from app.core.supabase import get_user_supabase
from app.main import create_app
from app.services.landmark_fingerprint import fingerprint_wav, offset_vote_matches
from tests.test_landmark_fingerprint import melody, write_wav


class LandmarkDB:
    def __init__(self, references=None, broken=False):
        self.references = references or {}
        self.broken = broken
        self.saved = []
        self.queries = []

    async def request(self, method, table, *, json):
        if self.broken:
            raise HTTPException(status_code=404)
        assert method == "POST" and table == "rpc/match_audio_landmarks"
        self.queries.append(json)
        query = list(zip(json["query_hashes"], json["query_offsets"]))
        return [{"title": title, "artist": "Reference artist", "votes": votes, "score": score}
                for title, votes, score in offset_vote_matches(query, self.references)]

    async def insert(self, table, values, **kwargs):
        self.saved.append((table, values))
        return [{"id": "saved"}]


def client_for(db, **options):
    app = create_app()
    settings = Settings(_env_file=None, recognition_mode="landmark", **options)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=AuthenticatedUser(id=UUID("c924b932-e8d5-4fb2-9f43-0ed81066cc29")), access_token="test")
    app.dependency_overrides[get_user_supabase] = lambda: db
    return TestClient(app)


def test_uploaded_excerpt_is_matched_by_own_algorithm_and_saved(tmp_path, monkeypatch):
    from app.routers import identify
    original = melody(42)
    reference = tmp_path / "reference.wav"
    query = tmp_path / "query.wav"
    write_wav(reference, original)
    write_wav(query, original[int(5.137 * 11025):int(13.137 * 11025)] * 0.6)
    db = LandmarkDB({"Known song": fingerprint_wav(reference, max_points=100000)})

    # Decode is tested separately against FFmpeg. Here the uploaded file is
    # already normalized WAV; all fingerprint extraction and voting are real.
    async def normalized_wav(source, destination, **kwargs):
        shutil.copyfile(source, destination)
        return 8

    async def no_external_call(*args, **kwargs):
        raise AssertionError("Landmark mode must not contact AcoustID")

    monkeypatch.setattr(identify, "decode_audio_async", normalized_wav)
    monkeypatch.setattr(identify, "lookup_acoustid", no_external_call)
    response = client_for(db).post("/api/identify", files={"file": ("clip.wav", query.read_bytes(), "audio/wav")})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "matched"
    assert result["results"][0]["title"] == "Known song"
    assert result["results"][0]["recognition_method"] == "mdvn_landmark"
    assert db.saved[0][1]["results"][0]["recognition_method"] == "mdvn_landmark"
    assert len(db.queries[0]["query_hashes"]) <= 400


def test_missing_rpc_is_an_actionable_error_not_not_found(tmp_path, monkeypatch):
    from app.routers import identify
    query = tmp_path / "query.wav"
    write_wav(query, melody(42, 8))

    async def normalized_wav(source, destination, **kwargs):
        shutil.copyfile(source, destination)
        return 8

    monkeypatch.setattr(identify, "decode_audio_async", normalized_wav)
    response = client_for(LandmarkDB(broken=True)).post(
        "/api/identify", files={"file": ("clip.wav", query.read_bytes(), "audio/wav")})
    assert response.status_code == 503
    assert "match_audio_landmarks" in response.text


def test_readiness_reports_missing_tools_and_rpc_without_exposing_credentials(monkeypatch):
    from app.routers import identify
    monkeypatch.setattr(identify.shutil, "which", lambda _: None)
    response = client_for(LandmarkDB(broken=True)).get("/api/identify/status")
    assert response.status_code == 200
    assert response.json()["catalog_available"] is False
    assert response.json()["tools"] == {"ffmpeg": False, "ffprobe": False, "fpcalc": False}
    assert "access_token" not in response.text


def test_readiness_requires_authentication():
    assert TestClient(create_app()).get("/api/identify/status").status_code == 401


def test_weak_match_is_not_accepted(tmp_path, monkeypatch):
    import asyncio
    from app.routers import identify

    class WeakDB:
        async def request(self, *args, **kwargs):
            return [{"title": "Weak", "artist": "Other", "votes": 8, "score": 0.02}]

    monkeypatch.setattr(identify, "fingerprint_wav", lambda _: [(f"{i:016x}", i * 10) for i in range(400)])
    assert asyncio.run(identify._fallback_match(tmp_path / "unused.wav", WeakDB(), Settings(_env_file=None))) == []
