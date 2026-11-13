"""Recommendation isolation, Spotify metadata and real WebM HTTP recognition tests."""
from uuid import UUID
import shutil, subprocess, wave
import numpy as np
import pytest
import httpx
from fastapi.testclient import TestClient

from app.core.auth import AuthContext,AuthenticatedUser,get_auth_context
from app.core.config import Settings,get_settings
from app.core.supabase import get_user_supabase
from app.main import create_app
from app.services.recommendation import rank_recommendations,similar_tracks

USER=UUID("c924b932-e8d5-4fb2-9f43-0ed81066cc29")
T1="22222222-2222-4222-8222-222222222222"
T2="33333333-3333-4333-8333-333333333333"
T3="44444444-4444-4444-8444-444444444444"

def example_catalog():
    return [
        {"id":T1,"title":"Indie Track","artist":"A","genres":["indie"],"moods":["chill"],"tags":["acoustic"],"language":"vi"},
        {"id":T2,"title":"Rock Track","artist":"B","genres":["rock"],"moods":["energetic"],"tags":["guitar"],"language":"en"},
        {"id":T3,"title":"Indie Track 2","artist":"C","genres":["indie"],"moods":["chill"],"tags":["acoustic"],"language":"vi"},
    ]

def test_preference_ranking_and_feedback_are_independent():
    catalog=example_catalog()
    preferences={"genres":["indie"],"moods":["chill"],"languages":["vi"]}
    result=rank_recommendations(catalog,preferences,[],10)
    assert result[0]["id"] in (T1,T3)
    assert result[0]["score"]==1.0
    assert all(x["id"]!=T1 for x in rank_recommendations(catalog,preferences,[{"track_id":T1,"action":"dislike"}],10))

def test_similar_tracks_use_curated_tags():
    result=similar_tracks(example_catalog()[0],example_catalog(),10)
    assert result[0]["id"]==T3

def test_empty_catalog_and_new_user():
    assert rank_recommendations([],{},[])==[]
    assert all(x["score"]==0 for x in rank_recommendations(example_catalog(),{},[]))

class FakeDb:
    def __init__(self):
        self.seen=[]
        self.prefs=None
    async def select(self,table,**kw):
        self.seen.append(table)
        if table=="music_catalog": return example_catalog()
        if table=="user_music_preferences": return [self.prefs] if self.prefs else []
        if table=="user_music_feedback": return []
        return []
    async def insert(self,table,values,**kw):
        self.seen.append(table)
        if table=="user_music_preferences":self.prefs=values
        return [values]
    async def request(self,*args,**kwargs): return []

def make_app(db):
    app=create_app()
    app.dependency_overrides[get_auth_context]=lambda:AuthContext(user=AuthenticatedUser(id=USER,email="user@example.com"),access_token="supabase-token")
    app.dependency_overrides[get_user_supabase]=lambda:db
    app.dependency_overrides[get_settings]=lambda:Settings(supabase_url="https://example.supabase.co",supabase_publishable_key="pk",acoustid_client_key="mock")
    return app

def test_recommendation_routes_never_query_spotify_listening_history():
    db=FakeDb();client=TestClient(make_app(db))
    got=client.get("/api/recommendations")
    assert got.status_code==200
    assert len(got.json()["items"])==3
    updated=client.put("/api/recommendations/preferences",json={"genres":["INDIE"],"moods":["chill"],"languages":["vi"],"artists":[],"blocked_artists":[]})
    assert updated.status_code==200
    refreshed=client.get("/api/recommendations").json()["items"]
    assert refreshed[0]["genres"]==["indie"]
    assert "listening_history" not in db.seen
    assert "spotify" not in db.seen
    assert client.get(f"/api/recommendations/similar/{T1}").status_code==200
    assert client.post("/api/recommendations/feedback",json={"track_id":T1,"action":"like"}).status_code==200

def test_now_playing_requires_auth():
    client=TestClient(create_app())
    assert client.get("/api/spotify/now-playing",headers={"X-Spotify-Access-Token":"a-long-spotify-token"}).status_code==401

def test_now_playing_mocked_success(monkeypatch):
    from app.routers import spotify
    class FakeClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return None
        async def get(self,url,headers,params):
            assert headers["Authorization"]=="Bearer personal-spotify-token"
            return httpx.Response(200,json={"is_playing":True,"item":{"type":"track","id":"testtrack","name":"Track","artists":[{"name":"Artist"}],"album":{"name":"Album","images":[]},"external_urls":{"spotify":"https://open.spotify.com/track/testtrack"},"duration_ms":123000}},request=httpx.Request("GET",url))
    monkeypatch.setattr(spotify.httpx,"AsyncClient",lambda **kwargs:FakeClient())
    response=TestClient(make_app(FakeDb())).get("/api/spotify/now-playing",headers={"X-Spotify-Access-Token":"personal-spotify-token"})
    assert response.status_code==200
    assert response.json()["status"]=="playing"

@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="FFmpeg unavailable")
def test_http_webm_opus_audio_recognition(tmp_path,monkeypatch):
    from app.routers import identify
    wav=tmp_path/"original.wav"
    rate=11025
    t=np.arange(rate*6)/rate
    audio=(np.sin(2*np.pi*440*t)*10000).astype("<i2")
    with wave.open(str(wav),"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(audio.tobytes())
    webm=tmp_path/"audio.webm"
    result=subprocess.run(["ffmpeg","-v","error","-y","-i",str(wav),"-c:a","libopus",str(webm)],capture_output=True)
    if result.returncode:pytest.skip("Opus encoder unavailable")
    async def fake_fp(*args,**kwargs):return 6,"fingerprint"
    async def fake_lookup(*args,**kwargs):
        return {"status":"ok","results":[{"score":0.93,"id":"acoustid","recordings":[{"title":"WebM Test","artists":[{"name":"Tester"}]}]}]}
    monkeypatch.setattr(identify,"generate_fingerprint",fake_fp)
    monkeypatch.setattr(identify,"lookup_acoustid",fake_lookup)
    response=TestClient(make_app(FakeDb())).post("/api/identify",files={"file":("ghi-am.webm",webm.read_bytes(),"audio/webm")})
    assert response.status_code==200,response.text
    assert response.json()["status"]=="matched"
    assert response.json()["results"][0]["title"]=="WebM Test"
