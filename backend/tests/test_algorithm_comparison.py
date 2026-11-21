"""Correctness/HTTP contracts; real dataset scores live in artifacts, not assertions."""
import io
import json
import wave
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.core.auth import get_auth_context
from app.core.config import Settings, get_settings
from app.main import create_app
from app.services.content_recommendation import fit_content
from app.services.collaborative import model_scores, rank_collaborative
from app.services.mfcc_dtw import mfcc_features, subsequence_dtw
from app.services.audio_decode import prepare_local_pcm, InvalidAudio, AudioDurationExceeded
from tools.evaluate_recognition import choose_threshold, summarize, write_wav
from tests.test_collaborative import tiny_model
from tests.test_recommendation_integration import FakeDb, make_app, example_catalog, T1, T2, T3, USER
from tests.test_landmark_fingerprint import melody


def test_content_model_uses_artist_album_and_tags_not_recording_identity():
    items=[{"id":"a","artist":"One","album":"Shared"},
           {"id":"b","artist":"One","album":"Shared"},
           {"id":"c","artist":"Other","album":"Shared"}]
    graph=fit_content(items)
    assert graph["a"][0][0]=="b"
    assert graph["c"]==[]
    assert all(key!="a" for key,_ in graph["a"])


def test_method_selection_changes_ranking_and_hybrid_is_normalized():
    model=tiny_model();model["content_neighbors"]={T1:[[T3,1.0]],T2:[],T3:[]}
    profile={T1:2}
    assert max(model_scores(model,profile,"item_knn"),key=model_scores(model,profile,"item_knn").get)==T2
    assert max(model_scores(model,profile,"content_based"),key=model_scores(model,profile,"content_based").get)==T3
    hybrid=model_scores(model,profile,"hybrid")
    assert hybrid[T2]==pytest.approx(.7) and hybrid[T3]==pytest.approx(.65)
    rows,mode,_=rank_collaborative(example_catalog(),{},[{"track_id":T1,"action":"like"}],model,method="content_based")
    assert mode=="content_based" and [row["id"] for row in rows]==[T3]
    with pytest.raises(ValueError):model_scores(model,profile,"made_up_ai")


def test_unrelated_content_is_not_replaced_with_popularity_after_a_positive_seed():
    model=tiny_model();model["content_neighbors"]={T1:[],T2:[],T3:[]}
    catalog=[{**row,"genres":[],"moods":[],"tags":[]} for row in example_catalog()]
    rows,mode,_=rank_collaborative(catalog,{},[{"track_id":T1,"action":"like"}],model,method="content_based")
    assert rows==[] and mode=="metadata"


def test_mfcc_dtw_finds_offset_excerpt_and_silence_has_no_features():
    reference=melody(42, duration=12)/32768
    query=reference[int(3.137*11025):int(3.137*11025)+5*11025]
    cost,end=subsequence_dtw(mfcc_features(query),mfcc_features(reference))
    other,_=subsequence_dtw(mfcc_features(query),mfcc_features(melody(5,duration=12)/32768))
    assert cost<other and 6000<end<10000
    assert mfcc_features(np.zeros(11025*5)).shape==(0,13)
    assert not np.isfinite(subsequence_dtw(np.empty((0,13)),np.empty((0,13)))[0])


def test_native_browser_pcm_path_resamples_and_bounds_duration(tmp_path):
    source,output=tmp_path/"browser.wav",tmp_path/"normalized.wav"
    with wave.open(str(source),"wb") as audio:
        audio.setnchannels(2);audio.setsampwidth(2);audio.setframerate(16000)
        audio.writeframes(np.zeros((16000*6,2),dtype="<i2").tobytes())
    assert prepare_local_pcm(source,output)==6
    with wave.open(str(output),"rb") as audio:
        assert audio.getframerate()==11025 and audio.getnchannels()==1 and audio.getnframes()==6*11025
    with pytest.raises(AudioDurationExceeded):prepare_local_pcm(source,output,max_duration=5)


def test_threshold_selection_and_metrics_count_false_accepts():
    calibration=[{"expected":"a","predicted":"a","score":.9},{"expected":None,"predicted":"a","score":.6}]
    threshold=choose_threshold(calibration)
    assert .6<threshold<=.9
    result=summarize([{"expected":"a","predicted":"a","elapsed_ms":10},
                      {"expected":None,"predicted":"a","elapsed_ms":20}])
    assert result["unknown_false_accept_rate"]==1 and result["precision"]==.5


def test_local_api_is_authenticated_and_never_calls_cloud_or_database(tmp_path,monkeypatch):
    from app.services import local_recognition
    from app.routers import identify
    references=[{"id":"open","title":"Open song","artist":"Composer","source_url":"https://example.com/song", "license":"CC BY 3.0"}]
    monkeypatch.setattr(local_recognition,"load_references",lambda path:references)
    matched_wav = []

    def match(wav, catalog, method):
        matched_wav.append((wav, method))
        return [{"id":"open","score":.99 if method == "mfcc_dtw" else .05}]

    monkeypatch.setattr(local_recognition,"candidates",match)
    async def forbidden(*args,**kwargs):raise AssertionError("External recognition must not be called")
    monkeypatch.setattr(identify,"recognize_audd",forbidden)
    report=tmp_path/"report.json";report.write_text(json.dumps({"results":{"landmark":{"threshold":.1},"mfcc_dtw":{"threshold":.9}}}))
    db=FakeDb();app=make_app(db)
    app.dependency_overrides[get_settings]=lambda:Settings(_env_file=None,recognition_local_evaluation=str(report))
    wav=tmp_path/"query.wav";write_wav(wav,np.zeros(6*11025))
    client=TestClient(app)
    response=client.post("/api/identify/local?method=mfcc_dtw",files={"file":("query.wav",wav.read_bytes(),"audio/wav")})
    assert response.status_code==200
    assert response.json()["results"][0]["recognition_method"]=="mfcc_dtw"
    comparison = client.post("/api/identify/local/compare", files={"file": ("query.wav", wav.read_bytes(), "audio/wav")})
    assert comparison.status_code == 200
    results = comparison.json()["results"]
    assert [(row["method"], row["track_id"]) for row in results] == [("landmark", None), ("mfcc_dtw", "open")]
    assert matched_wav[-2][0] == matched_wav[-1][0]
    assert all(row["elapsed_ms"] >= 0 for row in results)
    assert db.seen==[]
    assert client.get("/api/identify/local-catalog").json()["items"][0]["license"]=="CC BY 3.0"
    assert client.post("/api/identify/local?method=cloud",files={"file":("query.wav",wav.read_bytes(),"audio/wav")}).status_code==422
    app.dependency_overrides.pop(get_auth_context)
    assert client.post("/api/identify/local",files={"file":("query.wav",wav.read_bytes(),"audio/wav")}).status_code==401
    assert client.post("/api/identify/local/compare",files={"file":("query.wav",wav.read_bytes(),"audio/wav")}).status_code==401
