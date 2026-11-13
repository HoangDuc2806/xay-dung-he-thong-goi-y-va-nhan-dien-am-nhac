"""Recommendation over licensed, independently curated metadata and explicit choices.

Do not ingest Spotify history, Spotify audio features, popularity, or Spotify
user profiles. Spotify remains a separate playback/search integration.
"""
from __future__ import annotations
from collections import Counter
from typing import Any

def tokens(row: dict) -> set[str]:
    return {str(x).strip().casefold() for x in
            (row.get("genres") or [])+(row.get("moods") or [])+(row.get("tags") or [])
            if str(x).strip()}

def _preferences_score(row:dict, preferences:dict) -> tuple[float,list[str]]:
    genre=set(preferences.get("genres") or [])
    mood=set(preferences.get("moods") or [])
    langs=set(preferences.get("languages") or [])
    artists=set(x.casefold() for x in preferences.get("artists") or [])
    g=genre & set(row.get("genres") or [])
    m=mood & set(row.get("moods") or [])
    l=str(row.get("language") or "") in langs
    a=str(row.get("artist") or "").casefold() in artists
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

def rank_recommendations(catalog:list[dict], preferences:dict, feedback:list[dict]|None=None,limit:int=24)->list[dict]:
    feedback=feedback or []
    dislikes={str(x["track_id"]) for x in feedback if x.get("action") in ("dislike","skip")}
    likes={x["track_id"] for x in feedback if x.get("action") in ("like","save")}
    liked_tags=Counter()
    for item in catalog:
        if str(item.get("id")) in likes:liked_tags.update(tokens(item))
    blocked={x.casefold() for x in preferences.get("blocked_artists") or []}
    candidates=[]
    for item in catalog:
        if str(item.get("id")) in dislikes or str(item.get("artist","")).casefold() in blocked:continue
        score,reasons=_preferences_score(item,preferences)
        positive=0
        ts=tokens(item)
        if liked_tags:
            positive=sum(liked_tags[t] for t in ts)/max(1,sum(liked_tags.values()))
        combined=(0.80*score+0.20*positive) if liked_tags else score
        exploration=max(0,min(100,int(preferences.get("discovery_level",50))))/100
        if liked_tags and str(item.get("id")) not in likes:
            combined=min(1, combined+0.08*exploration)
        candidates.append((combined, dict(item), reasons or (["Phù hợp với lựa chọn trước đây"] if positive else ["Khám phá catalog độc lập"])))
    candidates.sort(key=lambda v:(v[0],v[1].get("title","")),reverse=True)
    # Diversify artists so one artist does not saturate the first screen.
    ranked=[]
    artist_count=Counter()
    for score,row,reasons in candidates:
        name=str(row.get("artist","")).casefold()
        if artist_count[name]>=3:continue
        artist_count[name]+=1
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
