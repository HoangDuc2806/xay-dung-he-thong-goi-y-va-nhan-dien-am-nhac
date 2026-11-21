import asyncio
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.auth import AuthContext, AuthenticatedUser, get_auth_context
from app.core.config import Settings, get_settings
from app.routers.recommendations import Preferences
from app.services import discovery_cache, musicbrainz_metadata
from tests.test_recommendation_integration import FakeDb, make_app


ARTIST = "New Artist"
RECORDING = "88104428-426c-4c89-8a8e-ef78aaf17507"
OTHER = "3b1b0aaf-42f4-48e3-ad74-795541bcbd53"


def track(recording=RECORDING, title="Second Light"):
    return musicbrainz_metadata.normalize_recording({
        "id": recording, "title": title, "artist-credit": [{"artist": {"name": ARTIST}}],
        "releases": [{"title": "Same Album", "status": "Official"}],
    })


class CatalogDb(FakeDb):
    async def select(self, table, **kwargs):
        if table == "music_catalog" and "id" in kwargs.get("filters", {}):
            return []
        return await super().select(table, **kwargs)


def configure(app, tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, discovery_cache_path=tmp_path / "cache.sqlite")


def test_missing_artist_adds_recordings_and_keeps_feedback_private(tmp_path, monkeypatch):
    calls = []

    async def lookup(name):
        calls.append(name)
        return musicbrainz_metadata.LookupResult("found", [track(), track(OTHER, "Third Light")])

    monkeypatch.setattr(musicbrainz_metadata, "lookup_artist", lookup)
    db = CatalogDb()
    db.prefs = Preferences(artists=[ARTIST]).model_dump()
    app = make_app(db)
    configure(app, tmp_path)
    client = TestClient(app)
    first = client.get("/api/recommendations?expand_metadata=true")
    assert first.status_code == 200
    assert first.json()["missing_artists"] == []
    assert {row["id"] for row in first.json()["items"]} == {RECORDING, OTHER}
    assert first.json()["metadata_lookup"][0]["status"] == "found"
    feedback = client.post("/api/recommendations/feedback", json={"track_id": RECORDING, "action": "like"})
    assert feedback.status_code == 200
    assert [row["id"] for row in client.get("/api/recommendations?expand_metadata=true").json()["items"]] == [OTHER]
    assert calls == ["new artist"]
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=AuthenticatedUser(id=UUID("ee85404a-4936-4173-9b32-fc866d3b925d")), access_token="other-user")
    assert {row["id"] for row in client.get("/api/recommendations?expand_metadata=true").json()["items"]} == {RECORDING, OTHER}


def test_exact_title_can_be_found_when_artist_is_already_in_catalog(tmp_path, monkeypatch):
    async def lookup(title, artist):
        assert title == "Second Light" and artist == ARTIST
        return musicbrainz_metadata.LookupResult("found", [track()])

    monkeypatch.setattr(musicbrainz_metadata, "lookup_title", lookup)

    class ExistingArtistDb(CatalogDb):
        async def select(self, table, **kwargs):
            if table == "music_catalog" and "id" not in kwargs.get("filters", {}):
                return [track(OTHER, "Earlier Single")]
            return await super().select(table, **kwargs)

    app = make_app(ExistingArtistDb())
    configure(app, tmp_path)
    client = TestClient(app)
    response = client.post("/api/recommendations/metadata/search", json={"title": "Second Light", "artist": ARTIST})
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == RECORDING
    assert client.post("/api/recommendations/feedback", json={"track_id": RECORDING, "action": "skip"}).status_code == 200
    similar = client.get(f"/api/recommendations/similar/{RECORDING}?method=hybrid")
    assert similar.status_code == 200
    assert [row["id"] for row in similar.json()["items"]] == [OTHER]


def test_lookup_by_title_preserves_verified_artist_alias(tmp_path):
    path = tmp_path / "cache.sqlite"
    discovery_cache.remember_lookup(path, "artist:alias", musicbrainz_metadata.LookupResult(
        "found", [{**track(), "artist_alias_keys": ["alias"]}]))
    discovery_cache.remember_lookup(path, "recording:title", musicbrainz_metadata.LookupResult("found", [track()]))
    tracks, _ = discovery_cache.local_profile(path, "user")
    assert tracks[0]["artist_alias_keys"] == ["alias"]


def test_unavailable_lookup_preserves_existing_suggestions_and_backs_off(tmp_path, monkeypatch):
    calls = []

    async def lookup(name):
        calls.append(name)
        return musicbrainz_metadata.LookupResult("unavailable", [])

    monkeypatch.setattr(musicbrainz_metadata, "lookup_artist", lookup)
    db = CatalogDb()
    db.prefs = Preferences(artists=[ARTIST], genres=["indie"]).model_dump()
    app = make_app(db)
    configure(app, tmp_path)
    client = TestClient(app)
    for _ in range(2):
        response = client.get("/api/recommendations?expand_metadata=true")
        assert response.status_code == 200
        assert response.json()["items"] and response.json()["metadata_lookup"][0]["status"] == "unavailable"
    assert calls == ["new artist"]


def test_liked_existing_recording_expands_credited_artists(tmp_path, monkeypatch):
    seed = {**track(), "artist": f"{ARTIST} & Coartist"}
    new_track = {**track(OTHER, "Uncatalogued Single"), "artist": "Coartist"}
    calls = []

    async def lookup(name):
        calls.append(name)
        return musicbrainz_metadata.LookupResult("found", [new_track] if name == "Coartist" else [seed])

    class SavedFeedbackDb(FakeDb):
        action = None

        async def select(self, table, **kwargs):
            if table == "music_catalog":
                return [seed]
            if table == "user_music_feedback" and self.action:
                return [self.action]
            return await super().select(table, **kwargs)

        async def insert(self, table, values, **kwargs):
            if table == "user_music_feedback":
                self.action = values
            return await super().insert(table, values, **kwargs)

    monkeypatch.setattr(musicbrainz_metadata, "lookup_artist", lookup)
    app = make_app(SavedFeedbackDb())
    configure(app, tmp_path)
    client = TestClient(app)
    url = f"/api/recommendations?expand_metadata=true&liked_track_id={RECORDING}"
    assert client.get(url).json()["new_candidates"] == 0
    assert calls == []
    assert client.post("/api/recommendations/feedback", json={"track_id": RECORDING, "action": "like"}).status_code == 200
    result = client.get(url).json()
    assert calls == [ARTIST, "Coartist"]
    assert result["new_candidates"] == result["new_in_top_10"] == 1
    assert [row["id"] for row in result["items"]] == [OTHER]
    assert client.get(url).json()["new_candidates"] == 0
    assert calls == [ARTIST, "Coartist"]


def test_browse_by_artist_id_preserves_recording_without_album(monkeypatch):
    artist_id = "fffe9266-7930-4267-a178-e0ed2a04a40a"

    async def request(client, entity, params, key, limit):
        if entity == "artist":
            return [{"id": artist_id, "name": "B-Wine"}]
        assert params == {"artist": artist_id, "inc": "artist-credits"}
        return [{"id": RECORDING, "title": "Verified recording",
                 "artist-credit": [{"artist": {"id": artist_id, "name": "B-Wine"}}]},
                {"id": OTHER, "title": "Different artist",
                 "artist-credit": [{"artist": {"id": OTHER, "name": "Other Artist"}}]}]

    monkeypatch.setattr(musicbrainz_metadata, "_request", request)
    result = asyncio.run(musicbrainz_metadata.lookup_artist("b-wine"))
    assert result.status == "found"
    assert [(item["id"], item["album"]) for item in result.items] == [(RECORDING, None)]


def test_verified_releases_rescue_artist_lookup_while_musicbrainz_is_busy(tmp_path, monkeypatch):
    async def unavailable(name):
        return musicbrainz_metadata.LookupResult("unavailable", [])

    monkeypatch.setattr(musicbrainz_metadata, "lookup_artist", unavailable)
    db = CatalogDb()
    db.prefs = Preferences(artists=["b-wine"]).model_dump()
    app = make_app(db)
    configure(app, tmp_path)
    client = TestClient(app)
    result = client.get("/api/recommendations?expand_metadata=true").json()
    assert result["new_candidates"] == 5
    assert result["missing_artists"] == []
    songs = client.post("/api/recommendations/metadata/search", json={"title": "DATLE", "artist": "B-Wine"}).json()["items"]
    assert songs[0]["title"] == "DATLE"
    feedback = client.post("/api/recommendations/feedback", json={"track_id": songs[0]["id"], "action": "like"})
    assert feedback.status_code == 200
