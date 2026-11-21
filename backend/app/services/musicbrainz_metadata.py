"""Bounded lookup of public MusicBrainz core recording metadata."""

import asyncio
from dataclasses import dataclass
from time import monotonic
from uuid import UUID

import httpx

from app.services.recommendation import artist_key, track_key


EXCLUDED_RECORDINGS = {"385bc9a5-3ab9-4cfc-b430-95a250808e27": "Artist identity conflict"}
_HEADERS = {"User-Agent": "MusicDiscoveryVN/0.1 (https://github.com/HoangDuc2806)"}
_lock = asyncio.Lock()
_next_request = 0.0


@dataclass(frozen=True)
class LookupResult:
    status: str
    items: list[dict]


def quoted(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


async def _request(client: httpx.AsyncClient, entity: str, params: dict, key: str, limit: int) -> list[dict]:
    global _next_request
    async with _lock:
        delay = _next_request - monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        _next_request = monotonic() + 1.1
        response = await client.get(f"https://musicbrainz.org/ws/2/{entity}/", params={
            **params, "fmt": "json", "limit": limit,
        })
        if response.status_code in (429, 503):
            _next_request = monotonic() + 30
        response.raise_for_status()
    rows = response.json()[key]
    if not isinstance(rows, list):
        raise ValueError("Invalid MusicBrainz response")
    return rows


def normalize_recording(record: dict, artist_id: str | None = None, *, allow_unlisted_release: bool = False) -> dict | None:
    try:
        key = str(UUID(record["id"]))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if key in EXCLUDED_RECORDINGS:
        return None
    artist_credits = record.get("artist-credit", [])
    if artist_id and not any(row.get("artist", {}).get("id") == artist_id for row in artist_credits):
        return None
    title = str(record.get("title") or "").strip()
    if not title or len(title) > 400 or title.casefold() in ("intro", "outro", "skit"):
        return None
    names = [row.get("artist", {}).get("name") or row.get("name") for row in artist_credits]
    artist = " & ".join(dict.fromkeys(name.strip() for name in names if isinstance(name, str) and name.strip()))
    if not artist or len(artist) > 400:
        return None
    releases = [row for row in record.get("releases", []) if row.get("status") in (None, "Official")]
    if not releases and (not allow_unlisted_release or record.get("releases")):
        return None
    release = releases[0] if releases else {}
    year = str(record.get("first-release-date") or release.get("date") or "")[:4]
    album = str(release.get("title") or "").strip()[:400] or None
    return {"id": key, "title": title, "artist": artist, "album": album,
            "release_year": int(year) if year.isdecimal() and year.isascii() and 1600 <= int(year) <= 2100 else None,
            "genres": [], "moods": [], "tags": [], "language": "other", "artwork_url": None,
            "spotify_search_query": f"{title} {artist}", "source": "MusicBrainz recording",
            "source_url": f"https://musicbrainz.org/recording/{key}",
            "source_license": "CC0-1.0 (core metadata; no audio)"}


def recordings(rows, artist_id=None, limit=12, *, allow_unlisted_release=False):
    found = {}
    for record in rows:
        if row := normalize_recording(record, artist_id, allow_unlisted_release=allow_unlisted_release):
            found.setdefault(track_key(row), row)
        if len(found) == limit:
            break
    return list(found.values())


async def lookup_artist(name: str) -> LookupResult:
    try:
        async with asyncio.timeout(5):
            async with httpx.AsyncClient(headers=_HEADERS, timeout=3.5) as client:
                artists = await _request(client, "artist", {"query": f"artist:{quoted(name)} OR alias:{quoted(name)}"}, "artists", 20)
                matches = {str(UUID(row["id"])) for row in artists
                           if artist_key(name) in {artist_key(row["name"]),
                                                  *(artist_key(alias["name"]) for alias in row.get("aliases", []))}}
                if len(matches) != 1:
                    return LookupResult("ambiguous" if matches else "not_found", [])
                artist_id = next(iter(matches))
                rows = await _request(client, "recording", {"artist": artist_id, "inc": "artist-credits"}, "recordings", 35)
                items = recordings(rows, artist_id, allow_unlisted_release=True)
                for item in items:
                    item["artist_alias_keys"] = [artist_key(name)]
                return LookupResult("found" if items else "not_found", items)
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
        return LookupResult("unavailable", [])


async def lookup_title(title: str, artist: str) -> LookupResult:
    try:
        async with asyncio.timeout(5):
            async with httpx.AsyncClient(headers=_HEADERS, timeout=3.5) as client:
                query = f"recording:{quoted(title)} AND artist:{quoted(artist)}"
                rows = await _request(client, "recording", {"query": query}, "recordings", 25)
                exact = [row for row in rows if artist_key(row.get("title", "")) == artist_key(title)
                         and any(artist_key(credit.get("artist", {}).get("name", "")) == artist_key(artist)
                                 or artist_key(credit.get("name", "")) == artist_key(artist)
                                 for credit in row.get("artist-credit", []))]
                items = recordings(exact)
                return LookupResult("found" if items else "not_found", items)
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
        return LookupResult("unavailable", [])
