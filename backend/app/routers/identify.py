"""Audio recognition with FFmpeg normalization and licensed-catalog fingerprint fallback."""
from __future__ import annotations
import logging
import tempfile
import shutil
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.core.supabase import SupabaseRestClient, get_user_supabase
from app.services.audio_decode import (
    SUPPORTED_SUFFIXES, NON_AUDIO_MIMES, AudioDecoderUnavailable, AudioDurationExceeded,
    InvalidAudio, decode_audio_async, prepare_cloud_wav, prepare_local_pcm,
)
from app.services.audd_recognition import recognize_audd
from app.services.landmark_fingerprint import ALGORITHM, fingerprint_wav, sample_query_points
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
    score: float | None = Field(default=None, ge=0, le=1)
    spotify_url: str | None = None
    acoustid_id: str | None = None
    musicbrainz_recording_id: str | None = None
    musicbrainz_url: str | None = None
    acoustid_url: str | None = None
    recognition_method: Literal["acoustid", "mdvn_landmark", "audd", "mfcc_dtw"] = "acoustid"

class MusicRecognitionResponse(BaseModel):
    status: Literal["matched","not_found"]
    message: str
    duration_seconds: int
    results: list[RecognizedTrack]
    warnings: list[str] = Field(default_factory=list)


LocalMethod = Literal["landmark", "mfcc_dtw"]


class LocalComparisonResult(BaseModel):
    method: LocalMethod
    track_id: str | None
    track: RecognizedTrack | None
    elapsed_ms: float


class LocalComparisonResponse(BaseModel):
    duration_seconds: float
    results: list[LocalComparisonResult]

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

async def _fallback_match(wav:Path, db: SupabaseRestClient, settings:Settings | None = None) -> list[RecognizedTrack]:
    import asyncio
    settings = settings or get_settings()
    points=await asyncio.to_thread(fingerprint_wav,wav)
    if len(points)<10:return []
    sampled=sample_query_points(points)
    try:
        rows=await db.request("POST","rpc/match_audio_landmarks",json={
            "query_hashes":[x[0] for x in sampled],
            "query_offsets":[x[1] for x in sampled],
        })
    except HTTPException as exc:
        logger.warning("Fingerprint catalog unavailable (status=%s)",exc.status_code)
        raise HTTPException(status_code=503, detail="Không truy vấn được kho fingerprint. Kiểm tra migration 20261113 và RPC match_audio_landmarks trong Supabase.") from exc
    matches=[]
    for item in (rows if isinstance(rows,list) else [])[:5]:
        votes=int(item.get("votes") or 0)
        if votes < settings.recognition_landmark_min_votes or float(item.get("score") or 0) < settings.recognition_landmark_min_score:continue
        matches.append(RecognizedTrack(
            title=item["title"],artists=[item["artist"]], album=item.get("album"),
            year=item.get("release_year"), score=max(0.0,min(1.0,float(item.get("score") or 0))),
            recognition_method="mdvn_landmark",
        ))
    return matches

@router.get("/status")
async def recognition_status(
    _context:AuthContext=Depends(get_auth_context), settings:Settings=Depends(get_settings),
    db:SupabaseRestClient=Depends(get_user_supabase),
):
    tools = {name: bool(shutil.which(path)) for name, path in {
        "ffmpeg": settings.recognition_ffmpeg_path,
        "ffprobe": settings.recognition_ffprobe_path,
        "fpcalc": settings.chromaprint_fpcalc_path,
    }.items()}
    catalog_available = False
    if settings.recognition_mode in ("hybrid", "landmark"):
        try:
            await db.request("POST", "rpc/match_audio_landmarks", json={"query_hashes": [], "query_offsets": []})
            catalog_available = True
        except HTTPException:
            pass
    return {"mode": settings.recognition_mode, "algorithm": ALGORITHM, "tools": tools,
            "local_comparison_ready": Path(settings.recognition_local_bundle).is_file() and Path(settings.recognition_local_evaluation).is_file(),
            "acoustid_configured": bool(settings.acoustid_client_key.strip()),
            "audd_configured": bool(settings.audd_api_token.strip()),
            "catalog_available": catalog_available,
            "message": "RPC khả dụng không có nghĩa đã có fingerprint. Cần lập chỉ mục audio tham chiếu trước khi nhận diện."}


@asynccontextmanager
async def local_test_audio(file: UploadFile, settings: Settings):
    if Path(file.filename or "").suffix.lower() not in (".wav",".wave"):
        await file.close()
        raise HTTPException(415,"Thử nghiệm hai thuật toán cần WAV PCM, tối đa 15 giây. Bản ghi micro trên web đã ở định dạng này.")
    with tempfile.TemporaryDirectory(prefix="mdvn-local-") as temp:
        source,normalized=Path(temp)/"upload.wav",Path(temp)/"normalized.wav"
        try:
            with source.open("wb") as output:
                total=0
                while chunk:=await file.read(1024*1024):
                    total+=len(chunk)
                    if total>min(settings.recognition_max_upload_bytes,8*1024*1024):
                        raise HTTPException(413,"Bản ghi nội bộ vượt giới hạn dung lượng.")
                    output.write(chunk)
        finally:
            await file.close()
        try:
            duration=await asyncio.to_thread(prepare_local_pcm,source,normalized)
        except AudioDurationExceeded as exc:raise HTTPException(413,str(exc)) from exc
        except InvalidAudio as exc:raise HTTPException(422,str(exc)) from exc
        if duration<5:raise HTTPException(422,"Cần ghi ít nhất 5 giây.")
        yield normalized, duration


def run_local_methods(wav: Path, settings: Settings, methods: tuple[LocalMethod, ...]):
    from app.services.local_recognition import load_references, candidates, accepted_candidate

    try:
        references = load_references(settings.recognition_local_bundle)
        evaluation = json.loads(Path(settings.recognition_local_evaluation).read_text(encoding="utf-8"))
        thresholds = {method: float(evaluation["results"][method]["threshold"]) for method in methods}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Bộ tham chiếu nội bộ chưa sẵn sàng. Chạy prepare_open_audio và evaluate_recognition.") from exc
    tracks = {row["id"]: row for row in references}
    results = []
    for method in methods:
        started = perf_counter()
        best = accepted_candidate(candidates(wav, references, method), thresholds[method])
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        track = None
        if best:
            row = tracks[best["id"]]
            track = RecognizedTrack(title=row["title"], artists=[row["artist"]], score=best["score"],
                                    recognition_method="mdvn_landmark" if method == "landmark" else "mfcc_dtw")
        results.append(LocalComparisonResult(method=method, track_id=best["id"] if best else None,
                                            track=track, elapsed_ms=elapsed_ms))
    return references, results


@router.post("/local", response_model=MusicRecognitionResponse)
async def identify_local(file:UploadFile=File(...),method:LocalMethod=Query("landmark"),
                         _context:AuthContext=Depends(get_auth_context),settings:Settings=Depends(get_settings)):
    """Independent small-catalog demo. Never calls AudD/Spotify or writes history."""
    async with local_test_audio(file, settings) as (normalized, duration):
        references, measured = await asyncio.to_thread(run_local_methods, normalized, settings, (method,))
    results = [row.track for row in measured if row.track is not None]
    indexed_seconds = max((float(row.get("duration_seconds") or 0) for row in references), default=0)
    return MusicRecognitionResponse(status="matched" if results else "not_found",results=results,
        duration_seconds=round(duration),message="Kết quả từ kho thử nghiệm nội bộ." if results else "Chưa khớp bài trong kho thử nghiệm nội bộ.",
        warnings=[f"Kho thử nghiệm gồm {len(references)} bản nhạc mở, tối đa {indexed_seconds:g} giây đầu mỗi bài. Điểm số thể hiện mức độ khớp."])


@router.post("/local/compare", response_model=LocalComparisonResponse)
async def compare_local(file: UploadFile = File(...), _context: AuthContext = Depends(get_auth_context),
                        settings: Settings = Depends(get_settings)):
    async with local_test_audio(file, settings) as (normalized, duration):
        _, results = await asyncio.to_thread(run_local_methods, normalized, settings, ("landmark", "mfcc_dtw"))
    return LocalComparisonResponse(duration_seconds=round(duration, 2), results=results)


@router.get("/local-catalog")
async def local_catalog(_context:AuthContext=Depends(get_auth_context),settings:Settings=Depends(get_settings)):
    from app.services.local_recognition import load_references
    try:
        references=await asyncio.to_thread(load_references,settings.recognition_local_bundle)
    except (OSError,ValueError,KeyError) as exc:
        raise HTTPException(503,"Kho thử nghiệm nội bộ chưa sẵn sàng.") from exc
    return {"items":[{key:row.get(key) for key in ("id","title","artist","source_url","license","license_url","duration_seconds")} for row in references]}

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
    if settings.recognition_mode == "audd" and not settings.audd_api_token.strip():
        raise HTTPException(status_code=503, detail="Chưa cấu hình AUDD_API_TOKEN trong backend/.env.local. Lấy token từ dashboard.audd.io và khởi động lại backend.")
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
            if settings.recognition_mode == "audd" and suffix in (".wav", ".wave"):
                duration=await asyncio.to_thread(prepare_cloud_wav,input_path,output_path,
                    max_duration=settings.recognition_max_duration_seconds)
            else:
                duration=await decode_audio_async(input_path,output_path,
                    ffmpeg=settings.recognition_ffmpeg_path,
                    ffprobe=settings.recognition_ffprobe_path,
                    max_duration=settings.recognition_max_duration_seconds)
                if settings.recognition_mode == "audd":
                    cloud_path = Path(temp)/"cloud-clip.wav"
                    duration=await asyncio.to_thread(prepare_cloud_wav,output_path,cloud_path,
                        max_duration=settings.recognition_max_duration_seconds)
                    output_path = cloud_path
        except AudioDecoderUnavailable as exc:
            raise HTTPException(status_code=503,detail=str(exc)) from exc
        except AudioDurationExceeded as exc:
            raise HTTPException(status_code=413,detail=str(exc)) from exc
        except InvalidAudio as exc:
            raise HTTPException(status_code=422,detail=f"{exc} Hãy kiểm tra codec âm thanh; không cần tự đổi sang MP3.") from exc

        if duration<settings.recognition_min_duration_seconds:
            raise HTTPException(status_code=422,detail=f"Đoạn âm thanh quá ngắn, cần ít nhất {settings.recognition_min_duration_seconds} giây.")
        if settings.recognition_mode == "audd":
            results = [RecognizedTrack.model_validate(row) for row in await recognize_audd(output_path,settings.audd_api_token)]
            response = MusicRecognitionResponse(status="matched" if results else "not_found",
                message="Nhận diện từ dịch vụ AudD." if results else "AudD chưa tìm thấy bài phù hợp. Hãy thu đoạn rõ có giọng hát hoặc giai điệu chính, đưa micro gần loa và thử lại.",
                duration_seconds=duration,results=results)
            await _save_history(db,str(context.user.id),response)
            return response
        matches=[]
        warnings=[]
        catalog_error = None
        # Run the project's own algorithm first. AcoustID is an optional extension.
        if settings.recognition_mode != "acoustid":
            try:
                matches=await _fallback_match(output_path,db,settings)
            except HTTPException as exc:
                if settings.recognition_mode == "landmark":
                    raise
                catalog_error = exc
                warnings.append(str(exc.detail))
        if settings.recognition_mode == "acoustid" and not settings.acoustid_client_key.strip():
            raise HTTPException(status_code=503, detail="Chế độ AcoustID chưa được cấu hình ACOUSTID_CLIENT_KEY.")
        if not matches and settings.recognition_mode != "landmark" and settings.acoustid_client_key.strip():
            try:
                _,fp=await generate_fingerprint(output_path,
                    fpcalc_path=settings.chromaprint_fpcalc_path,
                    fingerprint_length_seconds=max(10,settings.recognition_fingerprint_length_seconds))
                payload=await lookup_acoustid(settings.acoustid_client_key.strip(),fp,duration)
                matches=[RecognizedTrack.model_validate(item) for item in parse_acoustid_matches(payload)]
            except (AcoustIDUnavailable,FingerprintToolMissing,FingerprintTimeout,InvalidAudioFile):
                if settings.recognition_mode == "acoustid":
                    raise HTTPException(status_code=503, detail="AcoustID không khả dụng. Kiểm tra key, fpcalc và kết nối mạng.")
                warnings.append("AcoustID không khả dụng; kết quả chỉ dựa trên kho fingerprint nội bộ.")
        if not matches and catalog_error is not None:
            raise catalog_error
        response=MusicRecognitionResponse(
            status="matched" if matches else "not_found",
            message=("Nhận diện từ AcoustID/MusicBrainz." if matches and matches[0].recognition_method=="acoustid"
                     else "Tìm thấy bài hát trong kho fingerprint độc lập." if matches
                     else "Không tìm thấy bản ghi phù hợp. Hãy thử đoạn rõ 10–15 giây; thuật toán nội bộ chỉ nhận diện audio đã được lập chỉ mục, không phải mọi bài trên Spotify."),
            duration_seconds=duration,results=matches,warnings=warnings,
        )
        await _save_history(db,str(context.user.id),response)
        return response
