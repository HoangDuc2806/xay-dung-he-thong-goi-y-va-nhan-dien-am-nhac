"""Small fixtures verify algorithm behaviour; real evaluation is a separate artifact."""
import json
from uuid import UUID
import httpx
import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings, get_settings
from app.services.collaborative import listen_metadata, load_model, rank_collaborative, recording_id
from app.services import listenbrainz_profile
from tools.train_recommender import fit, evaluate, temporal_split, listen_timestamp
from tests.test_recommendation_integration import FakeDb, make_app, T1, T2, T3, example_catalog


def tiny_model():
    return {"version": 1, "algorithm": "item-knn-cosine", "items": example_catalog(),
            "neighbors": {T1: [[T2, 0.8], [T3, 0.4]], T2: [[T1, 0.8]], T3: [[T1, 0.4]]},
            "popularity": {T1: 10, T2: 20, T3: 5}, "manifest": {"users": 3, "items": 3}}


def test_dump_and_api_timestamp_formats():
    assert listen_timestamp({"timestamp": 1794428183}) == 1794428183
    assert listen_timestamp({"listened_at": 1794428183}) == 1794428183


def test_learned_neighbors_exclude_seed_hidden_tracks_and_blocked_artists():
    model = tiny_model()
    result, mode, seeds = rank_collaborative(example_catalog(), {}, [{"track_id": T1, "action": "like"}], model)
    assert mode == "item_knn" and seeds == 1
    assert [row["id"] for row in result] == [T2, T3]
    result, _, _ = rank_collaborative(example_catalog(), {"blocked_artists": ["b"]},
                                     [{"track_id": T1, "action": "like"}, {"track_id": T3, "action": "skip"}], model)
    assert result == []


def test_trained_results_still_respect_language_and_mood():
    result, _, _ = rank_collaborative(example_catalog(), {"languages": ["vi"], "moods": ["chill"]},
                                     [{"track_id": T1, "action": "like"}], tiny_model())
    assert [row["id"] for row in result] == [T3]


def test_public_history_has_influence_without_explicit_likes():
    result, mode, _ = rank_collaborative(example_catalog(), {}, [], tiny_model(), history={T1: 8})
    assert mode == "item_knn" and result[0]["id"] == T2
    result, mode, _ = rank_collaborative(example_catalog(), {}, [], tiny_model())
    assert mode == "popularity" and result[0]["id"] == T2


def test_missing_or_incompatible_model_falls_back_honestly(tmp_path):
    assert load_model(str(tmp_path / "missing.json")) is None
    broken = tmp_path / "broken.json"
    broken.write_text('{"version":100}')
    assert load_model(str(broken)) is None
    result, mode, _ = rank_collaborative(example_catalog(), {"genres": ["indie"]}, [], None)
    assert mode == "metadata" and {row["id"] for row in result} == {T1, T3}


def test_song_identity_preserves_remix_and_discards_service_metadata():
    assert recording_id(" SONG ", "Artist") == recording_id("song", "artist")
    assert recording_id("Song Remix", "Artist") != recording_id("Song", "Artist")
    listen = {"track_metadata": {"track_name": "Song", "artist_name": "Artist", "additional_info": {"tags": ["not imported"]}}}
    row = listen_metadata(listen)
    assert UUID(row["id"]) and row["tags"] == []
    listen["track_metadata"]["additional_info"]["music_service"] = "spotify.com"
    assert listen_metadata(listen) is None
    listen["track_metadata"]["additional_info"] = {"spotify_id": "do-not-import"}
    assert listen_metadata(listen) is None


def test_fit_learns_multi_user_cosine_and_temporal_evaluation_has_no_future_edges():
    events = [("u1", "a", 1), ("u1", "b", 2), ("u2", "a", 3), ("u2", "b", 4), ("u3", "c", 5),
              ("u1", "c", 100), ("u2", "c", 101)]
    train, test, cutoff = temporal_split(events)
    assert max(row[2] for row in train) < cutoff <= min(row[2] for row in test)
    model = fit(train)
    assert model["neighbors"]["a"][0][0] == "b"
    assert all(key != "c" for key, _ in model["neighbors"]["a"])
    report = evaluate(model, train, test, k=2)
    assert report["test_users"] == 2
    assert 0 <= report["item_knn"]["recall@2"] <= 1


def test_api_serves_model_with_only_authenticated_users_own_feedback(tmp_path):
    model_file = tmp_path / "model.json"
    model_file.write_text(json.dumps(tiny_model()))
    class LikedDb(FakeDb):
        async def select(self, table, **kwargs):
            if table == "user_music_feedback":
                assert kwargs["filters"].get("user_id", "").startswith("eq.")
                return [{"track_id": T1, "action": "like"}]
            return await super().select(table, **kwargs)
    db = LikedDb()
    app = make_app(db)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, recommendation_model_path=str(model_file), discovery_cache_path=None)
    response = TestClient(app).get("/api/recommendations")
    assert response.status_code == 200
    assert response.json()["model"]["algorithm"] == "hybrid"
    assert response.json()["items"][0]["id"] == T2
    assert "listening_history" not in db.seen


def test_recent_profile_handles_unknown_user_and_does_not_follow_redirects(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, **kwargs):
            assert url.startswith("https://api.listenbrainz.org/1/user/")
            assert kwargs["params"] == {"count": 200}
            return httpx.Response(404, request=httpx.Request("GET", url))
    monkeypatch.setattr(listenbrainz_profile.httpx, "AsyncClient", Client)
    app = make_app(FakeDb())
    response = TestClient(app).get("/api/recommendations", params={"listenbrainz_user": "nonexistent-user-for-test"})
    assert response.status_code == 404
    assert TestClient(app).get("/api/recommendations", params={"listenbrainz_user": "../../localhost"}).status_code == 422
