"""Recommendation over licensed, independently curated metadata and explicit choices.

Do not ingest Spotify history, Spotify audio features, popularity, or Spotify
user profiles. Spotify remains a separate playback/search integration.
"""
from __future__ import annotations
from collections import Counter
import unicodedata
import re
from functools import lru_cache


@lru_cache(maxsize=8192)
def artist_key(value:str)->str:
    """Match punctuation/spacing/diacritics, without fuzzy substring guesses."""
    value=unicodedata.normalize("NFKD",str(value).casefold().replace("đ","d"))
    return "".join(character for character in value if character.isalnum() and not unicodedata.combining(character))


@lru_cache(maxsize=8192)
def artist_names(value: str) -> tuple[str, ...]:
    parts = re.split(r"\s+(?:&|feat\.?|ft\.?|featuring|x|×)\s+|,\s+|;\s*", value, flags=re.IGNORECASE)
    return tuple(name.strip() for name in parts if name.strip())


@lru_cache(maxsize=8192)
def artist_keys(value:str)->frozenset[str]:
    """Keep the full band name and explicit collaboration participants, never substrings."""
    return frozenset(key for name in (str(value), *artist_names(str(value))) if (key:=artist_key(name)))


def track_key(row:dict)->tuple[str,str]:
    return (" ".join(unicodedata.normalize("NFKC",str(row.get("title") or "")).casefold().split()),artist_key(row.get("artist") or ""))


def track_artist_keys(row: dict) -> frozenset[str]:
    return artist_keys(row.get("artist") or "") | frozenset(row.get("artist_alias_keys") or ())


def has_interests(preferences:dict,feedback:list[dict]|None=None)->bool:
    return any(preferences.get(field) for field in ("genres","moods","languages","artists")) or any(
        row.get("action") in ("like","save") for row in feedback or [])


def catalog_coverage(catalog:list[dict],preferences:dict)->dict:
    available=list(dict.fromkeys(str(row.get("artist") or "").strip() for row in catalog if row.get("artist")))
    keys = {key for row in catalog for key in track_artist_keys(row)}
    return {"catalog_size":len(catalog),"available_artists":available[:30],
            "available_genres":sorted({str(value) for row in catalog for value in row.get("genres") or []}),
            "available_moods":sorted({str(value) for row in catalog for value in row.get("moods") or []}),
            "available_languages":sorted({str(row["language"]) for row in catalog if row.get("language")}),
            "missing_artists":[name for name in preferences.get("artists") or [] if artist_key(name) not in keys]}

def tokens(row: dict) -> set[str]:
    return {str(x).strip().casefold() for x in
            (row.get("genres") or [])+(row.get("moods") or [])+(row.get("tags") or [])
            if str(x).strip()}


def eligible_catalog(catalog:list[dict], preferences:dict, feedback:list[dict]|None=None)->list[dict]:
    feedback=feedback or []
    hidden={str(row["track_id"]) for row in feedback if row.get("action") in ("dislike","skip")}
    hidden_songs={track_key(row) for row in catalog if str(row["id"]) in hidden}
    positive={str(row["track_id"]) for row in feedback if row.get("action") in ("like","save")}
    blocked={artist_key(value) for value in preferences.get("blocked_artists") or []}
    anchors={artist_key(value) for value in preferences.get("artists") or []}
    selected_languages = {value.casefold() for value in preferences.get("languages") or []}
    tag_filters = {field: {value.casefold() for value in preferences[field]}
                   for field in ("genres", "moods") if preferences.get(field)}
    for row in catalog:
        if str(row["id"]) in positive:anchors.update(track_artist_keys(row))
    result=[]
    for row in catalog:
        names=track_artist_keys(row)
        if str(row["id"]) in hidden or track_key(row) in hidden_songs or names & blocked:continue
        anchor=bool(names & anchors)
        language=str(row.get("language") or "other").casefold()
        if selected_languages and language not in selected_languages and not (anchor and language in ("other","und","")):continue
        allowed=True
        for field, selected in tag_filters.items():
            actual={str(value).casefold() for value in row.get(field) or []}
            # Unknown metadata is not a conflicting label. A strong artist
            # anchor may still make this relevant, without inventing mood/genre.
            if selected and not selected & actual and not (anchor and not actual):allowed=False;break
        if allowed:result.append(row)
    return result

def _preferences_score(row:dict, preferences:dict) -> tuple[float,list[str]]:
    genre={str(x).strip().casefold() for x in preferences.get("genres") or []}
    mood={str(x).strip().casefold() for x in preferences.get("moods") or []}
    langs={str(x).strip().casefold() for x in preferences.get("languages") or []}
    artists={artist_key(x) for x in preferences.get("artists") or []}
    g=genre & {str(x).strip().casefold() for x in row.get("genres") or []}
    m=mood & {str(x).strip().casefold() for x in row.get("moods") or []}
    l=str(row.get("language") or "").casefold() in langs
    a=bool(track_artist_keys(row) & artists)
    parts=[(0.42,len(g)/len(genre) if genre else 0), (0.32,len(m)/len(mood) if mood else 0),
           (0.10,1.0 if l else 0.0), (0.16,1.0 if a else 0.0)]
    # Report a normalized score on the configured dimensions.
    active_weights=[0.42 if genre else 0,0.32 if mood else 0,0.10 if langs else 0,0.16 if artists else 0]
    denom=sum(active_weights)
    score=sum(w*value for w,value in parts)/denom if denom else 0
    reasons=[*(f"Thể loại {x}" for x in sorted(g)),*(f"Tâm trạng {x}" for x in sorted(m))]
    if l:reasons.append("Ngôn ngữ phù hợp")
    if a:reasons.append("Nghệ sĩ yêu thích")
    return score,reasons

def rank_recommendations(catalog:list[dict], preferences:dict, feedback:list[dict]|None=None,limit:int=24,*,diversify:bool=True)->list[dict]:
    feedback=feedback or []
    if limit <= 0:return []
    personalized=has_interests(preferences,feedback)
    likes={str(x["track_id"]) for x in feedback if x.get("action") in ("like","save")}
    liked_tags=Counter()
    for item in catalog:
        if str(item.get("id")) in likes:liked_tags.update(tokens(item))
    diversity=max(0,min(100,int(preferences.get("discovery_level",50))))
    per_artist=1 if diversity>=75 else 2 if diversity>=35 else 3
    actions={str(x["track_id"]):x.get("action") for x in feedback}
    candidates=[]
    for item in eligible_catalog(catalog,preferences,feedback):
        score,reasons=_preferences_score(item,preferences)
        positive=0
        ts=tokens(item)
        if liked_tags:
            positive=sum(liked_tags[t] for t in ts)/max(1,sum(liked_tags.values()))
        combined=(0.80*score+0.20*positive) if liked_tags else score
        # A larger catalog or diversity slider cannot turn an unrelated track
        # into a personalized match. Preserve an honest no-match state instead.
        if personalized and combined<=0:continue
        row=dict(item)
        row["feedback_action"]=actions.get(str(item.get("id")))
        candidates.append((combined, row, reasons or (["Tương đồng với bài bạn thích"] if positive else ["Khám phá catalog độc lập"])))
    candidates.sort(key=lambda v:(v[0],v[1].get("title","")),reverse=True)
    # Diversify artists so one artist does not saturate the first screen.
    ranked=[]
    used=set()
    artist_count=Counter()
    for score,row,reasons in candidates:
        identity=track_key(row)
        if identity in used:continue
        name=artist_key(row.get("artist") or "")
        if diversify and artist_count[name]>=per_artist:continue
        artist_count[name]+=1
        used.add(identity)
        row["score"]=round(max(0,min(1,score)),4)
        row["reasons"]=reasons
        ranked.append(row)
        if len(ranked)>=limit:break
    return ranked

def similar_tracks(seed:dict,catalog:list[dict],limit:int=12)->list[dict]:
    seed_tags=tokens(seed)
    scored=[]
    for item in catalog:
        if str(item.get("id"))==str(seed.get("id")):continue
        other=tokens(item)
        similarity=len(seed_tags & other)/max(1,len(seed_tags | other))
        if similarity>0:
            row=dict(item);row["score"]=round(similarity,4)
            row["reasons"]=["Tương đồng thể loại / tâm trạng / tag"]
            scored.append(row)
    return sorted(scored,key=lambda x:x["score"],reverse=True)[:limit]
