"""Public Spotify catalog search endpoint; no user-specific data is requested."""
from typing import Literal

from fastapi import APIRouter, Depends, Query, Header, HTTPException
import httpx
from app.core.auth import AuthContext, get_auth_context
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings, get_settings
from app.services.spotify_catalog import search_spotify_tracks

router = APIRouter(prefix="/api/spotify", tags=["Spotify"])


class SpotifyTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    artists: list[str]
    album_name: str | None = None
    album_image_url: str | None = None
    release_date: str | None = None
    duration_ms: int
    spotify_url: str
    uri: str


class SpotifySearchResponse(BaseModel):
    provider: Literal["spotify"] = "spotify"
    query: str
    market: str
    items: list[SpotifyTrack]
    limit: int
    offset: int
    next_offset: int | None = None
    total: int | None = None


@router.get("/search", response_model=SpotifySearchResponse, summary="Search Spotify tracks")
async def search_tracks(
    q: str = Query(min_length=1, max_length=200, description="Tên bài hát, nghệ sĩ hoặc album"),
    limit: int = Query(default=10, ge=1, le=10),
    market: str = Query(default="VN", min_length=2, max_length=2, pattern="^[A-Z]{2}$"),
    offset: int = Query(default=0, ge=0, le=1000),
    settings: Settings = Depends(get_settings),
) -> SpotifySearchResponse:
    query = q.strip()
    if not query:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Hãy nhập tên bài hát hoặc nghệ sĩ.")
    page = await search_spotify_tracks(query, limit, market, settings, offset=offset)
    return SpotifySearchResponse(query=query, market=market, limit=limit, offset=offset, **page)


@router.get("/now-playing")
async def spotify_now_playing(
    spotify_token: str = Header(alias="X-Spotify-Access-Token", min_length=8, max_length=4096),
    _context: AuthContext = Depends(get_auth_context),
):
    """Fetch currently playing metadata with user's own Spotify OAuth token.

    Never uses the app's client-credentials token; no audio is copied.
    """
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers={"Authorization": f"Bearer {spotify_token}"},
                params={"additional_types":"track"},
            )
    except (httpx.TimeoutException,httpx.RequestError) as exc:
        raise HTTPException(status_code=503,detail="Không kết nối được Spotify Now Playing.") from exc
    if response.status_code==204:
        return {"status":"not_playing","track":None}
    if response.status_code in (401,403):
        raise HTTPException(status_code=response.status_code,detail="Spotify chưa cấp quyền đọc bài đang phát. Hãy kết nối lại với user-read-currently-playing.")
    if response.status_code==429:
        raise HTTPException(status_code=429,detail="Spotify giới hạn số yêu cầu. Hãy thử lại sau.")
    if not response.is_success:
        raise HTTPException(status_code=502,detail="Spotify không trả được trạng thái phát nhạc.")
    try:
        payload=response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502,detail="Dữ liệu Spotify không hợp lệ.") from exc
    item=payload.get("item") if isinstance(payload,dict) else None
    if not item or item.get("type")!="track":
        return {"status":"not_playing","track":None}
    return {
        "status":"playing" if payload.get("is_playing") else "paused",
        "track":{
            "id":item.get("id"),"name":item.get("name"),
            "artists":[x.get("name","") for x in item.get("artists",[])],
            "album":(item.get("album") or {}).get("name"),
            "image_url":next((x.get("url") for x in (item.get("album") or {}).get("images",[]) if x.get("url")),None),
            "spotify_url":(item.get("external_urls") or {}).get("spotify"),
            "duration_ms":item.get("duration_ms"),
        },
    }
