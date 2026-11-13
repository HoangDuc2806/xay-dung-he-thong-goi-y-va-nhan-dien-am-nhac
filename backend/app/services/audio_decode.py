"""Safely decode uploaded audio using FFprobe/FFmpeg before fingerprinting.

Do not trust file extension or MIME alone. Input media is never retained.
"""
from __future__ import annotations
import asyncio
import json
import subprocess
from pathlib import Path

SUPPORTED_SUFFIXES = {
    ".mp3", ".wav", ".wave", ".flac", ".ogg", ".oga", ".opus", ".webm",
    ".m4a", ".m4b", ".mp4", ".aac", ".wma", ".aif", ".aiff", ".caf",
    ".mka", ".3gp", ".amr",
}
NON_AUDIO_MIMES = {
    "application/octet-stream", "video/webm", "video/mp4",
    "video/x-matroska", "application/ogg",
}

class AudioDecoderUnavailable(Exception):
    pass

class InvalidAudio(Exception):
    pass

class AudioDurationExceeded(Exception):
    pass

def decode_audio(
    source: Path, destination: Path, *, ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe", max_duration: int = 1800,
) -> int:
    """Return decoded duration; output is bounded PCM mono WAV at 11025 Hz."""
    try:
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
             "-show_entries", "format=duration:stream=codec_type", "-of", "json",
             str(source)],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise AudioDecoderUnavailable("FFprobe chưa được cài hoặc không khả dụng.") from exc
    except subprocess.TimeoutExpired as exc:
        raise InvalidAudio("Đọc thông tin file âm thanh quá lâu.") from exc
    try:
        data = json.loads(probe.stdout)
    except (ValueError, TypeError) as exc:
        raise InvalidAudio("Không đọc được cấu trúc file âm thanh.") from exc
    if probe.returncode != 0 or not any(
        stream.get("codec_type") == "audio" for stream in data.get("streams", [])
    ):
        raise InvalidAudio("File không chứa luồng âm thanh hợp lệ hoặc codec chưa được hỗ trợ.")
    duration_value = data.get("format", {}).get("duration")
    try:
        duration = float(duration_value)
        if duration > max_duration:
            raise AudioDurationExceeded("File âm thanh vượt giới hạn thời lượng.")
    except (TypeError, ValueError):
        pass  # Some WebM streams report no duration; decoded output determines length.
    try:
        decode = subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-y",
             "-protocol_whitelist", "file,pipe",
             "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1",
             "-ar", "11025", "-c:a", "pcm_s16le", "-t",
             str(max_duration + 1), str(destination)],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise AudioDecoderUnavailable("FFmpeg chưa được cài hoặc không khả dụng.") from exc
    except subprocess.TimeoutExpired as exc:
        raise InvalidAudio("Giải mã file âm thanh quá lâu.") from exc
    if decode.returncode != 0 or not destination.is_file():
        raise InvalidAudio("Không thể giải mã codec âm thanh này bằng FFmpeg.")
    import wave
    try:
        with wave.open(str(destination), "rb") as wav:
            result = wav.getnframes() / wav.getframerate()
    except (wave.Error, EOFError) as exc:
        raise InvalidAudio("Không đọc được âm thanh PCM sau chuyển đổi.") from exc
    if result <= 0:
        raise InvalidAudio("File không chứa mẫu âm thanh hợp lệ.")
    if result > max_duration:
        raise AudioDurationExceeded("File âm thanh vượt giới hạn thời lượng.")
    return int(round(result))

async def decode_audio_async(*args, **kwargs) -> int:
    return await asyncio.to_thread(decode_audio, *args, **kwargs)
