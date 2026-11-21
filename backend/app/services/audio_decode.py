"""Safely decode uploaded audio using FFprobe/FFmpeg before fingerprinting.

Do not trust file extension or MIME alone. Input media is never retained.
"""
from __future__ import annotations
import asyncio
import json
import subprocess
import wave
from pathlib import Path
import numpy as np

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


def prepare_local_pcm(source: Path, destination: Path, max_duration=16):
    """Browser PCM16 WAV path for local research matchers; no external decoder."""
    from app.services.mfcc_dtw import resample_audio
    try:
        with wave.open(str(source), "rb") as audio:
            channels, rate = audio.getnchannels(), audio.getframerate()
            if audio.getsampwidth()!=2 or channels not in (1,2) or not 8000<=rate<=96000 or audio.getcomptype()!="NONE":
                raise InvalidAudio("Thử nghiệm nội bộ cần WAV PCM 16-bit mono/stereo.")
            duration=audio.getnframes()/rate
            if duration > max_duration:
                raise AudioDurationExceeded(f"Thử nghiệm nội bộ nhận đoạn tối đa {max_duration} giây.")
            frame_count=min(audio.getnframes(),15*rate)
            data=audio.readframes(frame_count)
            if len(data)!=frame_count*channels*2:
                raise InvalidAudio("File WAV bị cắt hỏng.")
        samples=np.frombuffer(data,dtype="<i2").astype(np.float32).reshape(-1,channels).mean(axis=1)/32768
        samples=resample_audio(samples,rate)
        with wave.open(str(destination),"wb") as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(11025)
            audio.writeframes(np.clip(samples*32768,-32768,32767).astype("<i2").tobytes())
        return min(duration,15)
    except (wave.Error,EOFError,OSError,ValueError) as exc:
        raise InvalidAudio("Cần bản ghi WAV PCM hợp lệ.") from exc


def prepare_cloud_wav(source: Path, destination: Path, *, max_duration: int = 1800, clip_seconds: int = 12) -> int:
    """Validate browser PCM WAV and extract a bounded clip without FFmpeg.

    This path is for the cloud recognizer; the local matcher still requires its
    normalized 11025-Hz input. Reject truncated/unsupported WAV before API calls.
    """
    try:
        with wave.open(str(source), "rb") as audio:
            rate = audio.getframerate()
            channels = audio.getnchannels()
            if audio.getcomptype() != "NONE" or audio.getsampwidth() != 2 or channels not in (1, 2) or not 8000 <= rate <= 96000:
                raise InvalidAudio("Cần file WAV PCM 16-bit, mono hoặc stereo.")
            duration = audio.getnframes() / rate
            if duration > max_duration:
                raise AudioDurationExceeded("File âm thanh vượt giới hạn thời lượng.")
            frame_count = audio.getnframes()
            frames = min(frame_count, clip_seconds * rate)
            # Scan a bounded prefix. A microphone often starts recording before
            # the music begins. Preserve stereo and the provider's clip length.
            scanned = min(frame_count, max(30, clip_seconds) * rate)
            data = audio.readframes(scanned)
            if not frames or len(data) != scanned * channels * 2:
                raise InvalidAudio("File WAV đang trống hoặc bị cắt hỏng.")
            samples = np.frombuffer(data, dtype="<i2").reshape(-1, channels)
            if np.all(np.ptp(samples.astype(np.int32), axis=0) < 4):
                raise InvalidAudio("Đoạn ghi âm gần như im lặng. Kiểm tra micro hoặc nguồn phát rồi ghi lại.")
            start = _active_clip_start(samples, rate, frames)
            data = data[start * channels * 2:(start + frames) * channels * 2]
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(channels)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(data)
        return int(round(frames / rate))
    except (wave.Error, EOFError, OSError) as exc:
        raise InvalidAudio("Không đọc được file WAV. Hãy ghi âm lại hoặc tải tệp âm thanh hợp lệ.") from exc


def _active_clip_start(samples, rate, frames):
    if len(samples) <= frames:
        return 0
    block = rate // 4
    whole = len(samples) // block
    blocks = samples[:whole * block].reshape(whole, block, samples.shape[1])
    # Variance ignores DC. Saturating the weights prevents a single loud
    # transient from outweighing a sustained audible passage.
    rms = np.sqrt(blocks.var(axis=1, dtype=np.float32).mean(axis=1))
    typical = float(np.percentile(rms, 75))
    activity = np.minimum(rms / max(8.0, typical * 0.18), 1.0)
    windows = np.convolve(activity, np.ones(frames // block), mode="valid")
    options = windows[:(len(samples) - frames) // block + 1]
    return int(np.argmax(options)) * block

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
