"""Audio recognition with FFmpeg normalization and licensed-catalog fingerprint fallback."""
from __future__ import annotations
import logging
import tempfile
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.core.supabase import SupabaseRestClient, get_user_supabase
from app.services.audio_decode import (
    SUPPORTED_SUFFIXES, NON_AUDIO_MIMES, AudioDecoderUnavailable, AudioDurationExceeded,
    InvalidAudio, decode_audio_async,
)
from app.services.landmark_fingerprint import fingerprint_wav
from app.services.music_recognition import (
    AcoustIDUnavailable, FingerprintTimeout, FingerprintToolMissing,
    InvalidAudioFile, generate_fingerprint, lookup_acoustid, parse_acoustid_matches,
)

router = APIRouter(prefix="/api/identify", tags=["Music Recognition"])
logger = logging.getLogger(__name__)

class RecognizedTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    artists: list[str] = Field(default_factory=list)
    album: str | None = None
    year: int | None = None
    score: float = Field(ge=0, le=1)
    acoustid_id: str | None = None
    musicbrainz_recording_id: str | None = None
    musicbrainz_url: str | None = None
    acoustid_url: str | None = None
    recognition_method: Literal["acoustid", "mdvn_landmark"] = "acoustid"

class MusicRecognitionResponse(BaseModel):
    status: Literal["matched","not_found"]
    message: str
    duration_seconds: int
    results: list[RecognizedTrack]

def _validate_upload(file: UploadFile) -> str:
    suffix=Path(file.filename or "").suffix.lower()
    content_type=(file.content_type or "").split(";",1)[0].lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=415,detail="Định dạng file chưa hỗ trợ. Chọn tệp âm thanh phổ biến (WebM/Opus, WAV, MP3, M4A, FLAC...).")
    if content_type and not (content_type.startswith("audio/") or content_type in NON_AUDIO_MIMES):
        raise HTTPException(status_code=415,detail="MIME type không phù hợp với tệp âm thanh.")
    return suffix

async def _save_history(db: SupabaseRestClient, user_id: str, response: MusicRecognitionResponse) -> None:
    try:
        await db.insert("recognition_history",{
            "user_id": user_id, "status":response.status,
            "duration_seconds":response.duration_seconds,
            "results": [x.model_dump() for x in response.results],
        },select="id")
    except HTTPException as exc:
        logger.warning("Recognition history not saved; check migration (status=%s)",exc.status_code)

async def _fallback_match(wav:Path, db: SupabaseRestClient) -> list[RecognizedTrack]:
    import asyncio
    points=await asyncio.to_thread(fingerprint_wav,wav)
    if len(points)<10:return []
    # Limit input to avoid unbounded JSON or database work. Query starts from many positions.
    sampled=points[::max(1,len(points)//400)][:400]
    try:
        rows=await db.request("POST","rpc/match_audio_landmarks",json={
            "query_hashes":[x[0] for x in sampled],
            "query_offsets":[x[1] for x in sampled],
        })
    except HTTPException as exc:
        logger.warning("Fingerprint catalog unavailable (status=%s)",exc.status_code)
        return []
    matches=[]
    for item in (rows if isinstance(rows,list) else [])[:5]:
        votes=int(item.get("votes") or 0)
        if votes < 7:continue
        matches.append(RecognizedTrack(
            title=item["title"],artists=[item["artist"]], album=item.get("album"),
            year=item.get("release_year"), score=max(0.0,min(1.0,float(item.get("score") or 0))),
            recognition_method="mdvn_landmark",
        ))
    return matches

@router.get("/history")
async def identification_history(
    context:AuthContext=Depends(get_auth_context),db:SupabaseRestClient=Depends(get_user_supabase)
):
    return await db.select("recognition_history",select="id,status,duration_seconds,results,created_at",
                           filters={"user_id":f"eq.{context.user.id}"},
                           order="created_at.desc",limit=40)

@router.get("/{recognition_id}")
async def identification_detail(
    recognition_id:UUID,context:AuthContext=Depends(get_auth_context),
    db:SupabaseRestClient=Depends(get_user_supabase)
):
    rows=await db.select("recognition_history",select="id,status,duration_seconds,results,created_at",
                         filters={"user_id":f"eq.{context.user.id}","id":f"eq.{recognition_id}"},limit=1)
    if not rows: raise HTTPException(status_code=404,detail="Không tìm thấy lượt nhận diện.")
    return rows[0]

@router.post("",response_model=MusicRecognitionResponse)
async def identify_music(
    file:UploadFile=File(...),
    context:AuthContext=Depends(get_auth_context), settings:Settings=Depends(get_settings),
    db:SupabaseRestClient=Depends(get_user_supabase)
)->MusicRecognitionResponse:
    suffix=_validate_upload(file)
    max_bytes=max(1,settings.recognition_max_upload_bytes)
    with tempfile.TemporaryDirectory(prefix="music-recognition-") as temp:
        input_path=Path(temp)/f"input{suffix}"
        output_path=Path(temp)/"normalized.wav"
        try:
            with input_path.open("wb") as stream:
                written=0
                while True:
                    chunk=await file.read(min(1024*1024,max_bytes-written+1))
                    if not chunk:break
                    written+=len(chunk)
                    if written>max_bytes:
                        raise HTTPException(status_code=413,detail="Tệp âm thanh vượt giới hạn dung lượng.")
                    stream.write(chunk)
            if written==0:raise HTTPException(status_code=422,detail="Tệp âm thanh đang trống.")
        finally:
            await file.close()
        try:
            duration=await decode_audio_async(input_path,output_path,
                ffmpeg=settings.recognition_ffmpeg_path,
                ffprobe=settings.recognition_ffprobe_path,
                max_duration=settings.recognition_max_duration_seconds)
        except AudioDecoderUnavailable as exc:
            raise HTTPException(status_code=503,detail=str(exc)) from exc
        except AudioDurationExceeded as exc:
            raise HTTPException(status_code=413,detail=str(exc)) from exc
        except InvalidAudio as exc:
            raise HTTPException(status_code=422,detail=f"{exc} Hãy kiểm tra codec âm thanh; không cần tự đổi sang MP3.") from exc

        if duration<settings.recognition_min_duration_seconds:
            raise HTTPException(status_code=422,detail=f"Đoạn âm thanh quá ngắn, cần ít nhất {settings.recognition_min_duration_seconds} giây.")
        matches=[]
        primary_status="not_configured"
        if settings.acoustid_client_key.strip():
            try:
                _,fp=await generate_fingerprint(output_path,
                    fpcalc_path=settings.chromaprint_fpcalc_path,
                    fingerprint_length_seconds=max(10,settings.recognition_fingerprint_length_seconds))
                payload=await lookup_acoustid(settings.acoustid_client_key.strip(),fp,duration)
                matches=[RecognizedTrack.model_validate(item) for item in parse_acoustid_matches(payload)]
                primary_status="ok"
            except (AcoustIDUnavailable,FingerprintToolMissing,FingerprintTimeout,InvalidAudioFile):
                primary_status="unavailable"
        if not matches:
            matches=await _fallback_match(output_path,db)
        response=MusicRecognitionResponse(
            status="matched" if matches else "not_found",
            message=("Nhận diện từ AcoustID/MusicBrainz." if matches and matches[0].recognition_method=="acoustid"
                     else "Tìm thấy bài hát trong kho fingerprint độc lập." if matches
                     else "Không tìm thấy kết quả phù hợp trong AcoustID hoặc kho fingerprint độc lập. Hãy thử đoạn rõ hơn hoặc bổ sung catalog."),
            duration_seconds=duration,results=matches,
        )
        await _save_history(db,str(context.user.id),response)
        return response
