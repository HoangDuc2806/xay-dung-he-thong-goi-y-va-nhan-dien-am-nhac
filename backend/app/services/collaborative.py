"""Item-based collaborative filtering over independent ListenBrainz data.

The deployed JSON contains song metadata/neighbours, never listener identities.
No Spotify SDK events, listening_history, audio or user profiles enter this model.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import json
import logging
import math
from pathlib import Path
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from app.services.recommendation import artist_key, track_artist_keys, track_key, rank_recommendations, eligible_catalog
from app.services.content_recommendation import catalog_content_graph


def recording_key(title: str, artist: str) -> str:
    # Preserve accents and version words: a remix must not silently become the original.
    def clean(text):
        return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())
    return clean(artist) + "\n" + clean(title)


def recording_id(title: str, artist: str) -> str:
    return str(uuid5(NAMESPACE_URL, "listenbrainz:recording:" + recording_key(title, artist)))


def listen_metadata(listen: dict) -> dict | None:
    metadata = listen.get("track_metadata") or {}
    info = metadata.get("additional_info") or {}
    # Do not import identified Spotify submissions, service IDs, features or tags.
    if any("spotify" in str(field).casefold() for field in info) or any("spotify" in str(info.get(field, "")).casefold() for field in
           ("music_service", "music_service_name", "submission_client", "media_player", "origin_url")):
        return None
    title, artist = metadata.get("track_name"), metadata.get("artist_name")
    if not isinstance(title, str) or not isinstance(artist, str) or not title.strip() or not artist.strip():
        return None
    if len(title) > 400 or len(artist) > 400:
        return None
    return {"id": recording_id(title, artist), "title": title.strip(), "artist": artist.strip(),
            "album": str(metadata.get("release_name") or "")[:400] or None,
            "release_year": None, "genres": [], "moods": [], "tags": [], "language": "other",
            "artwork_url": None, "spotify_search_query": f"{title.strip()} {artist.strip()}",
            "source": "ListenBrainz public listens", "source_url": "https://listenbrainz.org/data/",
            "source_license": "CC0-1.0 (listen metadata; no audio)"}


@lru_cache(maxsize=2)
def _read_model(path: str, modified: int) -> dict | None:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if value.get("version") != 1 or value.get("algorithm") != "item-knn-cosine":
            raise ValueError("Unsupported recommender artifact")
        if not isinstance(value.get("neighbors"), dict) or not isinstance(value.get("items"), list):
            raise ValueError("Invalid recommender artifact")
        return value
    except (OSError, ValueError, TypeError):
        logging.getLogger(__name__).warning("Recommendation model unavailable or invalid: %s", path)
        return None


def load_model(path: str) -> dict | None:
    file = Path(path)
    try:
        return _read_model(str(file.resolve()), file.stat().st_mtime_ns)
    except OSError:
        return None


def profile_scores(model: dict, profile: dict[str, float]) -> dict[str, float]:
    scores = Counter()
    for seed, weight in profile.items():
        if weight <= 0 or not math.isfinite(weight):
            continue
        for target, similarity in model["neighbors"].get(seed, []):
            scores[target] += float(similarity) * weight
    return dict(scores)


def model_scores(model: dict, profile: dict[str, float], method="item_knn", *, candidates=None) -> dict[str, float]:
    def eligible(scores):
        if candidates is None:
            return scores
        return {key: score for key, score in scores.items() if key in candidates}

    if method == "item_knn":
        return eligible(profile_scores(model, profile))
    content = eligible(profile_scores({"neighbors": model.get("content_neighbors", {})}, profile))
    if method == "content_based":
        return content
    if method != "hybrid":
        raise ValueError("Unsupported recommendation method")
    collaborative = eligible(profile_scores(model, profile))
    def normalize(scores):
        maximum = max(scores.values(), default=0)
        return {key: value/maximum for key, value in scores.items()} if maximum > 0 else {}
    collaborative, content = normalize(collaborative), normalize(content)
    weight = model.get("hybrid_cf_weight", 0.7)
    return {key: weight * collaborative.get(key, 0) + (1 - weight) * content.get(key, 0)
            for key in collaborative.keys() | content.keys()}


def rank_collaborative(catalog: list[dict], preferences: dict, feedback: list[dict],
                       model: dict | None, limit=24, history: dict[str, float] | None = None, *, method="item_knn"):
    """Use learned co-listens when supported; retain explicit filters/exclusions."""
    if not model:
        return rank_recommendations(catalog, preferences, feedback, limit), "metadata", 0
    by_id = {str(item["id"]): item for item in catalog}
    # Collaborative counts cannot be invented for newly imported recordings.
    # Their independent metadata can still support content/cold-start ranking.
    if method in ("content_based","hybrid") and any(key not in model.get("content_neighbors",{}) for key in by_id):
        model={**model,"content_neighbors":catalog_content_graph(catalog)}
    known = set(model["neighbors"]) | (set(model.get("content_neighbors",{})) if method!="item_knn" else set())
    if not known.intersection(by_id):
        return rank_recommendations(catalog, preferences, feedback, limit), "metadata", 0
    profile = {key: min(5.0, math.log1p(count)) for key, count in (history or {}).items()
               if key in known and count > 0}
    heard=set(profile)
    for row in feedback:
        key = str(row["track_id"])
        if row.get("action") in ("like", "save") and key in known:
            profile[key] = profile.get(key, 0) + 2.0
            heard.add(key)
        elif row.get("action") in ("dislike", "skip"):
            profile.pop(key, None)
    # An explicit artist choice is a cold-start seed, not an observed listen.
    artists = {artist_key(name) for name in preferences.get("artists", [])}
    hidden={str(row["track_id"]) for row in feedback if row.get("action") in ("dislike","skip")}
    blocked={artist_key(name) for name in preferences.get("blocked_artists",[])}
    profile={key:weight for key,weight in profile.items() if key not in hidden and not track_artist_keys(by_id.get(key,{})) & blocked}
    if artists:
        seed_count=Counter()
        for key,row in sorted(by_id.items(),key=lambda value:(-model.get("popularity",{}).get(value[0],0),value[0])):
            names = track_artist_keys(row)
            matched = names & artists
            if key in known and key not in hidden and not names & blocked and matched and min(seed_count[name] for name in matched)<3:
                profile[key]=profile.get(key,0)+0.5
                seed_count.update(matched)
    eligible = eligible_catalog(catalog, preferences, feedback)
    heard_tracks = {track_key(by_id[key]) for key in heard if key in by_id}
    candidate_ids = {str(row["id"]) for row in eligible if track_key(row) not in heard_tracks}
    scores = model_scores(model, profile, method, candidates=candidate_ids)
    mode = method if scores else "popularity"
    if method=="hybrid" and scores:
        has_cf=bool(candidate_ids.intersection(profile_scores(model,profile)))
        has_content=bool(candidate_ids.intersection(profile_scores({"neighbors":model.get("content_neighbors",{})},profile)))
        mode="hybrid" if has_cf and has_content else "item_knn" if has_cf else "content_based"
    # Artist preferences express interest, not proof that every song by that
    # artist has already been heard. Keep direct matches as valid candidates.
    direct = {}
    if artists:
        preferred = [row for row in eligible if track_artist_keys(row) & artists]
        # Include positive feedback tracks so metadata affinity still uses the
        # same profile when the liked track is from another artist.
        seed_ids = {str(row["track_id"]) for row in feedback if row.get("action") in ("like", "save")}
        preferred_ids = {str(row["id"]) for row in preferred}
        direct_ids = preferred_ids & candidate_ids
        pool = preferred + [by_id[key] for key in seed_ids - preferred_ids if key in by_id]
        direct = {str(row["id"]): row for row in rank_recommendations(pool, preferences, feedback, len(pool), diversify=False)
                  if str(row["id"]) in direct_ids}
    if direct:
        maximum=max(scores.values(),default=1) or 1
        scores={key:0.45*value/maximum for key,value in scores.items()}
        for key,row in direct.items():scores[key]=scores.get(key,0)+0.55*max(0.1,row["score"])
        if mode=="popularity":mode="metadata"
    if not scores:
        # Popularity is explicitly labelled, never presented as personalization.
        if profile or any(preferences.get(k) for k in ("artists", "genres", "moods", "languages")) or history:
            fallback = rank_recommendations(catalog, preferences, feedback, len(eligible))
            return [row for row in fallback if str(row["id"]) in candidate_ids][:limit], "metadata", len(profile)
        scores = {key:value for key,value in model.get("popularity", {}).items() if key in by_id}
        if not scores:
            return rank_recommendations(catalog,preferences,feedback,limit),"metadata",len(profile)
    maximum = max(scores.values(), default=1) or 1
    ranked = []
    used=heard_tracks.copy()
    counts = Counter()
    cap = 1 if preferences.get("discovery_level", 50) >= 75 else 2 if preferences.get("discovery_level", 50) >= 35 else 3
    actions = {str(row["track_id"]): row.get("action") for row in feedback}
    for item in sorted(eligible, key=lambda row: (-scores.get(str(row["id"]), 0), str(row["id"]))):
        key = str(item["id"])
        identity=track_key(item)
        if key in heard or identity in used or scores.get(key, 0) <= 0:
            continue
        artist = artist_key(item.get("artist", ""))
        favorite=bool(track_artist_keys(item) & artists)
        artist_cap=max(cap,3 if preferences.get("discovery_level",50)>=75 else min(8,max(4,limit//2))) if favorite else cap
        if counts[artist] >= artist_cap:
            continue
        counts[artist] += 1
        used.add(identity)
        ranked.append({**item, "score": round(scores[key] / maximum, 4),
                       "feedback_action": actions.get(key),
                       "reasons": ["Nghệ sĩ bạn yêu thích" if favorite else {"item_knn": "Người nghe có gu gần bạn cũng nghe bài này",
                                    "content_based": "Tương đồng metadata nghệ sĩ, album hoặc thể loại với bài bạn thích",
                                    "hybrid": "Kết hợp hành vi cùng nghe và độ tương đồng metadata",
                                    "metadata": "Phù hợp với sở thích đã lưu",
                                    "popularity": "Được nhiều người nghe trong mẫu ListenBrainz"}[mode]]})
        if len(ranked) >= limit:
            break
    return ranked, mode, len(profile)
