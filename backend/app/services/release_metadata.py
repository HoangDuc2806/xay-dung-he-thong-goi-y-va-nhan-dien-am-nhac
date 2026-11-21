"""Small verified fallback for releases missing from the public metadata lookup."""

from uuid import NAMESPACE_URL, uuid5

from app.services.recommendation import artist_key, artist_keys


# Titles, credits and release details were verified against the linked editions.
_VERIFIED_RELEASES = (
    ("DATLE", "B-Wine", "DATLE - Single", 2024, "https://music.apple.com/us/album/datle-single/1766483376"),
    ("TOURIST", "B-Wine & V#", "TOURIST - Single", 2021, "https://music.apple.com/us/album/tourist-single/1767354997"),
    ("Không Phải Rapper", "B-Wine & Anh Phan & Liu Quẽn", "Không Phải Rapper - Single", 2024,
     "https://music.apple.com/us/album/kh%C3%B4ng-ph%E1%BA%A3i-rapper-single/1762816140"),
    ("ĐỘC FREESTYLE", "B-Wine", "ĐỘC", 2026, "https://music.apple.com/us/album/%C4%91%E1%BB%99c/6766829113"),
    ("ĐỪNG PHIỀN", "B-Wine", "ĐỘC", 2026, "https://music.apple.com/us/album/%C4%91%E1%BB%99c/6766829113"),
)


def verified_releases(artist: str, title: str | None = None) -> list[dict]:
    wanted_artist = artist_key(artist)
    wanted_title = artist_key(title) if title is not None else None
    matches = []
    for name, credit, album, year, url in _VERIFIED_RELEASES:
        if wanted_artist not in artist_keys(credit) or (wanted_title is not None and wanted_title != artist_key(name)):
            continue
        identity = f"mdvn:verified-release:{artist_key(credit)}:{artist_key(name)}"
        matches.append({"id": str(uuid5(NAMESPACE_URL, identity)), "title": name, "artist": credit,
                        "album": album, "release_year": year, "genres": [], "moods": [], "tags": [],
                        "language": "other", "artwork_url": None, "spotify_search_query": f"{name} {credit}",
                        "source": "Bản phát hành chính thức · Apple Music", "source_url": url,
                        "source_license": "Release facts only"})
    return matches
