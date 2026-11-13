"""Personalized discovery using an independently curated music catalog."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.auth import AuthContext, get_auth_context
from app.core.supabase import SupabaseRestClient, get_user_supabase
from app.services.recommendation import rank_recommendations, similar_tracks

router=APIRouter(prefix="/api/recommendations",tags=["Recommendations"])

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

CATALOG_FIELDS="id,title,artist,album,release_year,genres,moods,tags,language,spotify_search_query,artwork_url,source,source_url,source_license"
PREFERENCE_FIELDS="user_id,genres,moods,languages,artists,blocked_artists,discovery_level"

async def current_preferences(db:SupabaseRestClient,uid:str)->dict:
    rows=await db.select("user_music_preferences",select=PREFERENCE_FIELDS,
                         filters={"user_id":f"eq.{uid}"},limit=1)
    return rows[0] if rows else Preferences().model_dump()

@router.get("/preferences")
async def get_preferences(context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase)):
    return await current_preferences(db,str(context.user.id))

@router.put("/preferences")
async def save_preferences(preferences:Preferences,context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase)):
    content={"user_id":str(context.user.id),**preferences.model_dump()}
    rows=await db.insert("user_music_preferences",content,select=PREFERENCE_FIELDS,
                        prefer="resolution=merge-duplicates,return=representation",params={"on_conflict":"user_id"})
    if not rows:raise HTTPException(status_code=503,detail="Không thể lưu sở thích.")
    return rows[0]

@router.get("")
async def recommendations(limit:int=Query(24,ge=1,le=48),context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase)):
    uid=str(context.user.id)
    prefs=await current_preferences(db,uid)
    catalog=await db.select("music_catalog",select=CATALOG_FIELDS,
                            filters={"is_active":"eq.true"},order="created_at.desc",limit=1000)
    feedback=await db.select("user_music_feedback",select="track_id,action",
                             filters={"user_id":f"eq.{uid}"},limit=2000)
    return {"source":"independent_catalog","preferences":prefs,
            "items":rank_recommendations(catalog,prefs,feedback,limit),
            "message":"Dữ liệu catalog độc lập và sở thích tự khai báo; không sử dụng lịch sử nghe Spotify."}

@router.post("/feedback")
async def send_feedback(value:FeedbackInput,context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase)):
    rows=await db.select("music_catalog",select="id",filters={"id":f"eq.{value.track_id}","is_active":"eq.true"},limit=1)
    if not rows:raise HTTPException(status_code=404,detail="Bài hát không tồn tại trong catalog.")
    values={"user_id":str(context.user.id),"track_id":str(value.track_id),"action":value.action}
    response=await db.insert("user_music_feedback",values,select="track_id,action",
        prefer="resolution=merge-duplicates,return=representation",
        params={"on_conflict":"user_id,track_id"})
    if not response:raise HTTPException(status_code=503,detail="Không thể lưu phản hồi.")
    return response[0]

@router.get("/similar/{track_id}")
async def similar(track_id:UUID,limit:int=Query(12,ge=1,le=30),
                 _context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase)):
    entries=await db.select("music_catalog",select=CATALOG_FIELDS,
                            filters={"is_active":"eq.true"},limit=1000)
    seed=next((x for x in entries if str(x["id"])==str(track_id)),None)
    if not seed:raise HTTPException(status_code=404,detail="Bài hát không có trong catalog.")
    return {"source":"independent_catalog","items":similar_tracks(seed,entries,limit)}
