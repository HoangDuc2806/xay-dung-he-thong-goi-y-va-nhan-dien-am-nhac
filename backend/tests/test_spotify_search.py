from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app


def make_app(settings: Settings | None = None):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings or Settings(
        spotify_client_id="test-client-id",
        spotify_client_secret="test-client-secret",
    )
    return app


def test_spotify_search_returns_catalog_tracks(monkeypatch):
    from app.routers import spotify

    async def fake_search(query, limit, market, settings, *, offset=0):
        assert query == "B-Ray"
        assert limit == 5
        assert market == "VN"
        assert settings.spotify_client_id == "test-client-id"
        return {"items":[{
            "id": "spotify-track-id",
            "name": "Song name",
            "artists": ["Artist name"],
            "album_name": "Album name",
            "album_image_url": "https://i.scdn.co/image/example",
            "release_date": "2024-01-01",
            "duration_ms": 190000,
            "spotify_url": "https://open.spotify.com/track/spotify-track-id",
            "uri": "spotify:track:spotify-track-id",
        }],"next_offset":5,"total":30}

    monkeypatch.setattr(spotify, "search_spotify_tracks", fake_search)
    response = TestClient(make_app()).get(
        "/api/spotify/search", params={"q": "B-Ray", "limit": 5, "market": "VN"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "spotify"
    assert body["items"][0]["id"] == "spotify-track-id"
    assert body["items"][0]["artists"] == ["Artist name"]


def test_spotify_search_rejects_blank_query():
    response = TestClient(make_app()).get("/api/spotify/search", params={"q": "   "})
    assert response.status_code == 422


def test_spotify_search_requires_credentials(monkeypatch):
    from app.routers import spotify

    async def should_not_search(query, limit, market, settings, *, offset=0):
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Backend chưa cấu hình Spotify.")

    monkeypatch.setattr(spotify, "search_spotify_tracks", should_not_search)
    settings = Settings(spotify_client_id="", spotify_client_secret="")
    response = TestClient(make_app(settings)).get("/api/spotify/search", params={"q": "B-Ray"})
    assert response.status_code == 503


def test_spotify_search_accepts_next_page_without_increasing_limit(monkeypatch):
    from app.routers import spotify
    async def page(query, limit, market, settings, *, offset=0):
        assert limit == 10 and offset == 30
        return {"items":[],"next_offset":None,"total":30}
    monkeypatch.setattr(spotify,"search_spotify_tracks",page)
    response=TestClient(make_app()).get("/api/spotify/search",params={"q":"nhac Viet","offset":30})
    assert response.status_code == 200
    assert response.json()["offset"] == 30
    assert response.json()["next_offset"] is None


def test_spotify_pagination_rejects_out_of_range_requests():
    client=TestClient(make_app())
    for params in ({"offset":-1},{"offset":1001},{"limit":11}):
        assert client.get("/api/spotify/search",params={"q":"pop",**params}).status_code == 422


def test_spotify_service_passes_offset_and_normalizes_pagination(monkeypatch):
    import asyncio
    import httpx
    from app.services import spotify_catalog
    original=httpx.AsyncClient
    def handler(request):
        if request.url.host == "accounts.spotify.com":
            return httpx.Response(200,json={"access_token":"test-token","expires_in":3600})
        assert request.url.params["offset"] == "20"
        assert request.url.params["limit"] == "10"
        return httpx.Response(200,json={"tracks":{"items":[{"id":"track-21","name":"Song","artists":[]}],
            "next":"https://api.spotify.com/v1/search?offset=30","total":60}})
    monkeypatch.setattr(spotify_catalog,"_TOKEN",None)
    monkeypatch.setattr(spotify_catalog.httpx,"AsyncClient",lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    settings=Settings(spotify_client_id="client",spotify_client_secret="secret")
    page=asyncio.run(spotify_catalog.search_spotify_tracks("pop",10,"VN",settings,offset=20))
    assert page["items"][0]["id"] == "track-21"
    assert page["next_offset"] == 30 and page["total"] == 60
