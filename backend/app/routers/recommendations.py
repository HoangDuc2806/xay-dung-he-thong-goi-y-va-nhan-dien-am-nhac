"""Personalized discovery using an independently curated music catalog."""
from typing import Literal
import asyncio
import logging
import sqlite3
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.auth import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.core.supabase import SupabaseRestClient, get_user_supabase
from app.services.recommendation import artist_key, artist_names, track_key, track_artist_keys, rank_recommendations, similar_tracks, catalog_coverage, has_interests
from app.services.collaborative import load_model, rank_collaborative
from app.services.listenbrainz_profile import recent_profile
from app.services import discovery_cache, musicbrainz_metadata
from app.services.release_metadata import verified_releases

router=APIRouter(prefix="/api/recommendations",tags=["Recommendations"])
logger = logging.getLogger(__name__)

class Preferences(BaseModel):
    model_config=ConfigDict(extra="forbid")
    genres:list[str]=Field(default_factory=list,max_length=15)
    moods:list[str]=Field(default_factory=list,max_length=12)
    languages:list[str]=Field(default_factory=list,max_length=8)
    artists:list[str]=Field(default_factory=list,max_length=12)
    blocked_artists:list[str]=Field(default_factory=list,max_length=12)
    discovery_level:int=Field(50,ge=0,le=100)
    @field_validator("genres","moods","languages","artists","blocked_artists")
    @classmethod
    def clean(cls,items:list[str])->list[str]:
        return list(dict.fromkeys(x.strip().casefold() for x in items if x.strip() and len(x)<=80))

class FeedbackInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    track_id: UUID
    action: Literal["like","dislike","save","skip"]


class MetadataSearch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)
    artist: str = Field(min_length=1, max_length=80)

CATALOG_FIELDS="id,title,artist,album,release_year,genres,moods,tags,language,spotify_search_query,artwork_url,source,source_url,source_license"
PREFERENCE_FIELDS="user_id,genres,moods,languages,artists,blocked_artists,discovery_level"

def public_preferences(row:dict)->dict:
    # Database ownership belongs to the auth context, never to the editable form.
    values={name:row[name] for name in Preferences.model_fields if name in row}
    return Preferences.model_validate(values).model_dump()

async def current_preferences(db:SupabaseRestClient,uid:str)->dict:
    rows=await db.select("user_music_preferences",select=PREFERENCE_FIELDS,
                         filters={"user_id":f"eq.{uid}"},limit=1)
    return public_preferences(rows[0]) if rows else Preferences().model_dump()

async def active_catalog(db:SupabaseRestClient)->list[dict]:
    entries=[]
    # PostgREST caps a page at 1000. Fetch deterministic pages, bounded at 5000.
    for offset in range(0,5000,1000):
        page=await db.select("music_catalog",select=CATALOG_FIELDS,
                             filters={"is_active":"eq.true"},order="id.asc",limit=1000,offset=offset)
        entries.extend(page)
        if len(page)<1000:break
    return entries


async def read_local_profile(settings: Settings, uid: str, required_track_id: str | None = None):
    if settings.discovery_cache_path is None:
        return [], []
    try:
        return await asyncio.to_thread(discovery_cache.local_profile, settings.discovery_cache_path, uid, required_track_id)
    except (sqlite3.Error, OSError):
        logger.warning("Discovery metadata cache is temporarily unavailable")
        return [], []


async def lookup_metadata(settings: Settings, artist: str, title: str | None = None):
    path = settings.discovery_cache_path
    if path is None:
        return musicbrainz_metadata.LookupResult("unavailable", [])
    key = f"artist:{artist_key(artist)}" if title is None else f"recording:{artist_key(artist)}:{artist_key(title)}"
    try:
        hit = await asyncio.to_thread(discovery_cache.cached_lookup, path, key)
        result = hit
        if result is None:
            result = await (musicbrainz_metadata.lookup_artist(artist) if title is None else musicbrainz_metadata.lookup_title(title, artist))
        if result.status != "ambiguous" and (backup := verified_releases(artist, title)):
            supplemented, _ = discovery_cache.merge_catalog(result.items, backup)
            result = musicbrainz_metadata.LookupResult("found", supplemented)
        if result == hit:
            return result
        await asyncio.to_thread(discovery_cache.remember_lookup, path, key, result)
        return result
    except (sqlite3.Error, OSError):
        logger.warning("Could not store discovered metadata")
        return musicbrainz_metadata.LookupResult("unavailable", [])


def merge_feedback(saved, local, aliases):
    actions = {aliases.get(str(row["track_id"]), str(row["track_id"])): row["action"] for row in local}
    actions.update((str(row["track_id"]), row["action"]) for row in saved)
    return [{"track_id": key, "action": action} for key, action in actions.items()]

@router.get("/preferences",response_model=Preferences)
async def get_preferences(context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase)):
    return await current_preferences(db,str(context.user.id))

@router.put("/preferences",response_model=Preferences)
async def save_preferences(preferences:Preferences,context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase)):
    content={"user_id":str(context.user.id),**preferences.model_dump()}
    rows=await db.insert("user_music_preferences",content,select=PREFERENCE_FIELDS,
                        prefer="resolution=merge-duplicates,return=representation",params={"on_conflict":"user_id"})
    if not rows:raise HTTPException(status_code=503,detail="Không thể lưu sở thích.")
    return public_preferences(rows[0])

@router.get("")
async def recommendations(limit:int=Query(24,ge=1,le=48),browse:bool=Query(False),
                          method:Literal["item_knn","content_based","hybrid"]=Query("hybrid"),
                          expand_metadata: bool = Query(False),
                          liked_track_id: UUID | None = Query(None),
                          listenbrainz_user:str|None=Query(None,min_length=1,max_length=64,pattern=r"^[^/\\?#\x00-\x1f]+$"),
                          context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase),
                          settings:Settings=Depends(get_settings)):
    uid=str(context.user.id)
    prefs, catalog, feedback, (cached_tracks, cached_feedback) = await asyncio.gather(
        current_preferences(db, uid),
        active_catalog(db),
        db.select("user_music_feedback", select="track_id,action", filters={"user_id": f"eq.{uid}"},
                  order="updated_at.desc,track_id.asc", limit=2000),
        read_local_profile(settings, uid),
    )
    merged, aliases = discovery_cache.merge_catalog(catalog, cached_tracks)
    metadata_lookup = []
    new_candidates = set()
    if expand_metadata and not browse:
        prior_keys = {track_key(row) for row in merged}
        blocked = {artist_key(name) for name in prefs["blocked_artists"]}
        missing = catalog_coverage(merged, prefs)["missing_artists"]
        seed_names = ()
        if liked_track_id is not None:
            liked_id = aliases.get(str(liked_track_id), str(liked_track_id))
            actions = merge_feedback(feedback, cached_feedback, aliases)
            if any(row["track_id"] == liked_id and row["action"] in ("like", "save") for row in actions):
                seed = next((row for row in merged if str(row["id"]) == liked_id), None)
                if seed and not blocked & track_artist_keys(seed):
                    seed_names = artist_names(seed.get("artist") or "")
        lookups = {}
        for name in (*seed_names, *missing):
            name_key = artist_key(name)
            if name_key and name_key not in blocked:
                lookups.setdefault(name_key, name)
        # Bound how long a fresh recommendation request waits on external data.
        for name in list(lookups.values())[:2]:
            result = await lookup_metadata(settings, name)
            metadata_lookup.append({"artist": name, "status": result.status, "count": len(result.items)})
            cached_tracks.extend(result.items)
        merged, aliases = discovery_cache.merge_catalog(catalog, cached_tracks)
        new_candidates = {track_key(row) for row in merged} - prior_keys
    catalog = merged
    feedback = merge_feedback(feedback, cached_feedback, aliases)
    ranking_prefs={**prefs,"genres":[],"moods":[],"languages":[],"artists":[]} if browse else prefs
    ranking_feedback=[row for row in feedback if row.get("action") in ("dislike","skip")] if browse else feedback
    model=load_model(settings.recommendation_model_path) if settings.recommendation_model_path else None
    profile=await recent_profile(listenbrainz_user.strip()) if listenbrainz_user and not browse else None
    if browse:
        items=rank_recommendations(catalog,ranking_prefs,ranking_feedback,limit,diversify=False)
        algorithm,matched_seeds="catalog",0
    else:
        items,algorithm,matched_seeds=await asyncio.to_thread(rank_collaborative,catalog,ranking_prefs,ranking_feedback,model,limit,
                                                       history=profile["counts"] if profile else None,method=method)
    if browse:
        actions={str(row["track_id"]):row.get("action") for row in feedback}
        for item in items:item["feedback_action"]=actions.get(str(item["id"]))
    status="empty_catalog" if not catalog else "no_matches" if not items else "personalized" if has_interests(prefs,feedback) else "discovery"
    if browse and items:status="discovery"
    if algorithm=="popularity" and items:status="discovery"
    if algorithm in ("item_knn","content_based","hybrid") and items:status="personalized"
    manifest=model.get("manifest",{}) if model else {}
    return {"source":"independent_catalog","preferences":prefs,
            "metadata_lookup": metadata_lookup,
            "new_candidates": len(new_candidates),
            "new_in_top_10": sum(track_key(row) in new_candidates for row in items[:10]),
            "items":items,"status":status,"view":"catalog" if browse else "personalized",**catalog_coverage(catalog,prefs),
            "model":{"loaded":bool(model),"algorithm":algorithm,"trained_users":manifest.get("users",0),
                     "requested_method":method,"available_methods":model.get("methods",["item_knn"]) if model else [],
                     "trained_items":manifest.get("items",0),"matched_seeds":matched_seeds,
                     "profile_source":"listenbrainz_recent" if profile else "app_feedback",
                     "recent_listens":profile["recent_listens"] if profile else 0,
                     "accepted_listens":profile["accepted_listens"] if profile else 0},
            "message":"Gợi ý từ dữ liệu ListenBrainz độc lập, phản hồi và sở thích của bạn; không phân tích lịch sử Spotify."}

@router.post("/feedback")
async def send_feedback(value:FeedbackInput,context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase),
                        settings: Settings = Depends(get_settings)):
    rows=await db.select("music_catalog",select="id",filters={"id":f"eq.{value.track_id}","is_active":"eq.true"},limit=1)
    values={"user_id":str(context.user.id),"track_id":str(value.track_id),"action":value.action}
    if not rows:
        if settings.discovery_cache_path is None:
            raise HTTPException(status_code=404, detail="Bài hát không tồn tại trong catalog.")
        try:
            saved = await asyncio.to_thread(discovery_cache.store_feedback, settings.discovery_cache_path,
                                            values["user_id"], values["track_id"], value.action)
        except (sqlite3.Error, OSError) as exc:
            raise HTTPException(status_code=503, detail="Chưa lưu được phản hồi cho bài vừa tìm.") from exc
        if not saved:
            raise HTTPException(status_code=404, detail="Bài hát không tồn tại trong catalog.")
        return {"track_id": values["track_id"], "action": value.action}
    response=await db.insert("user_music_feedback",values,select="track_id,action",
        prefer="resolution=merge-duplicates,return=representation",
        params={"on_conflict":"user_id,track_id"})
    if not response:raise HTTPException(status_code=503,detail="Không thể lưu phản hồi.")
    return response[0]


@router.post("/metadata/search")
async def search_metadata(value: MetadataSearch, context: AuthContext = Depends(get_auth_context),
                          db: SupabaseRestClient = Depends(get_user_supabase), settings: Settings = Depends(get_settings)):
    title, artist = artist_key(value.title), artist_key(value.artist)
    if not title or not artist:
        raise HTTPException(status_code=422, detail="Nhập tên bài hát và nghệ sĩ để tra cứu.")
    uid = str(context.user.id)
    catalog, (cached, local) = await asyncio.gather(active_catalog(db), read_local_profile(settings, uid))
    entries, aliases = discovery_cache.merge_catalog(catalog, cached)
    def exact(rows):
        return [row for row in rows if artist_key(row["title"]) == title and artist in track_artist_keys(row)]
    matches = exact(entries)
    status = "found" if matches else "not_found"
    if not matches:
        result = await lookup_metadata(settings, value.artist, value.title)
        entries, aliases = discovery_cache.merge_catalog(catalog, cached + result.items)
        matches, status = exact(entries), result.status
    saved = await db.select("user_music_feedback", select="track_id,action", filters={"user_id": f"eq.{uid}"}, limit=2000)
    actions = {row["track_id"]: row["action"] for row in merge_feedback(saved, local, aliases)}
    return {"status": status, "items": [{**row, "score": 0, "reasons": [],
                                         "feedback_action": actions.get(str(row["id"]))} for row in matches[:12]]}

@router.get("/similar/{track_id}")
async def similar(track_id:UUID,limit:int=Query(12,ge=1,le=30),
                 method:Literal["item_knn","content_based","hybrid"]=Query("item_knn"),
                 _context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase),settings:Settings=Depends(get_settings)):
    uid = str(_context.user.id)
    catalog, (cached, local), prefs, feedback = await asyncio.gather(
        active_catalog(db), read_local_profile(settings, uid, str(track_id)), current_preferences(db, uid),
        db.select("user_music_feedback", select="track_id,action", filters={"user_id": f"eq.{uid}"}, limit=2000),
    )
    entries, aliases = discovery_cache.merge_catalog(catalog, cached)
    seed_id = aliases.get(str(track_id), str(track_id))
    seed=next((x for x in entries if str(x["id"])==seed_id),None)
    if not seed:raise HTTPException(status_code=404,detail="Bài hát không có trong catalog.")
    feedback = merge_feedback(feedback, local, aliases)
    model=load_model(settings.recommendation_model_path) if settings.recommendation_model_path else None
    if model:
        feedback=[row for row in feedback if row.get("action") in ("dislike","skip") and str(row["track_id"])!=seed_id]+[{"track_id":seed_id,"action":"like"}]
        items,algorithm,_=await asyncio.to_thread(rank_collaborative,entries,prefs,feedback,model,limit,method=method)
    else:
        allowed=rank_recommendations(entries,{**prefs,"artists":[]},[row for row in feedback if row.get("action") in ("dislike","skip")],len(entries),diversify=False)
        items,algorithm=similar_tracks(seed,allowed,limit),"metadata"
    return {"source":"independent_catalog","algorithm":algorithm,"items":items}
