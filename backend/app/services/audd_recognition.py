"""Server-side AudD adapter for recognizing ambient microphone recordings.

The provider performs recognition against its own catalog. Never describe these
results as matches produced by the project's local landmark algorithm.
"""
from pathlib import Path
import re

import httpx
from fastapi import HTTPException

AUDD_URL = "https://api.audd.io/"


async def recognize_audd(wav: Path, token: str) -> list[dict]:
    if not token.strip():
        raise HTTPException(status_code=503, detail="Chưa cấu hình AUDD_API_TOKEN trong backend/.env.local. Lấy token từ dashboard.audd.io và khởi động lại backend.")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with wav.open("rb") as audio:
                response = await client.post(AUDD_URL,
                    data={"api_token": token.strip(), "return": "spotify", "market": "VN"},
                    files={"file": ("recording.wav", audio, "audio/wav")})
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise HTTPException(status_code=503, detail="Không kết nối được dịch vụ AudD. Kiểm tra Internet và thử lại.") from exc
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="AudD giới hạn yêu cầu. Đợi một lát và kiểm tra hạn mức tài khoản.")
    if not response.is_success:
        raise HTTPException(status_code=503, detail="AudD chưa xử lý được yêu cầu. Kiểm tra token, hạn mức và trạng thái dịch vụ.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="AudD trả dữ liệu không hợp lệ.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="AudD trả dữ liệu không hợp lệ.")
    if payload.get("status") != "success":
        error = payload.get("error")
        code = str(error.get("error_code")) if isinstance(error, dict) else ""
        # Do not reflect provider error text: it may contain credentials or URLs.
        if code in ("900", "901"):
            raise HTTPException(status_code=503, detail="Token AudD không hợp lệ hoặc tài khoản hết hạn mức. Kiểm tra dashboard.audd.io.")
        if code in ("300", "400", "500", "700"):
            raise HTTPException(status_code=422, detail="AudD không phân tích được đoạn âm thanh. Hãy ghi đoạn nhạc rõ khoảng 10–15 giây và thử lại.")
        raise HTTPException(status_code=503, detail="AudD báo lỗi xử lý. Kiểm tra tài khoản dịch vụ và thử lại.")
    result = payload.get("result")
    if result is None or result == []:
        return []
    if not isinstance(result, dict) or not isinstance(result.get("title"), str) or not result["title"].strip():
        raise HTTPException(status_code=502, detail="AudD không trả thông tin bài hát hợp lệ.")
    spotify = result.get("spotify")
    spotify = spotify if isinstance(spotify, dict) else {}
    external_urls = spotify.get("external_urls")
    spotify_url = external_urls.get("spotify") if isinstance(external_urls, dict) else None
    if not isinstance(spotify_url, str) or not re.fullmatch(r"https://open\.spotify\.com/track/[A-Za-z0-9]+", spotify_url):
        spotify_url = None
    date = result.get("release_date")
    year = re.match(r"^(\d{4})", date) if isinstance(date, str) else None
    artist = result.get("artist")
    return [{"title": result["title"].strip(),
             "artists": [artist.strip()] if isinstance(artist, str) and artist.strip() else [],
             "album": result.get("album") if isinstance(result.get("album"), str) else None,
             "year": int(year.group(1)) if year else None,
             "score": None, "spotify_url": spotify_url, "recognition_method": "audd"}]
