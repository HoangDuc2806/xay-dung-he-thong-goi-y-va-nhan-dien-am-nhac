"""Bounded recent public listens; no token, full-history scraping or Spotify API."""
from collections import Counter
import time
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from app.services.collaborative import listen_metadata

_cache: dict[str, tuple[float, dict]] = {}


async def recent_profile(username: str) -> dict:
    now = time.monotonic()
    cached = _cache.get(username)
    if cached and cached[0] > now:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(f"https://api.listenbrainz.org/1/user/{quote(username, safe='')}/listens",
                                        params={"count": 200},
                                        headers={"User-Agent": "MusicDiscoveryVN/0.1 (academic recommender)", "Accept": "application/json"})
        if response.status_code == 404:
            raise HTTPException(404, "Không tìm thấy tên người dùng ListenBrainz này.")
        if response.status_code == 429:
            raise HTTPException(503, "ListenBrainz đang giới hạn lượt gọi. Hãy thử lại sau.")
        response.raise_for_status()
        listens = response.json()["payload"]["listens"]
        if not isinstance(listens, list):
            raise ValueError("Invalid listens")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Chưa đọc được lịch sử công khai từ ListenBrainz. Hãy thử lại sau.") from exc
    counts = Counter()
    accepted = 0
    for listen in listens[:200]:
        if isinstance(listen, dict) and (item := listen_metadata(listen)):
            counts[item["id"]] += 1
            accepted += 1
    result = {"counts": dict(counts), "recent_listens": len(listens[:200]), "accepted_listens": accepted}
    # Bounded cache; usernames/recordings are never added to the deployed model.
    if len(_cache) >= 256:
        _cache.pop(next(iter(_cache)))
    _cache[username] = (now + 180, result)
    return result
