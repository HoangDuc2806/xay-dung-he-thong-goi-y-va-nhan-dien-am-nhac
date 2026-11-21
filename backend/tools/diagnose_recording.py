"""Inspect a WAV recording; optionally make at most two real AudD requests."""
import argparse
import asyncio
import json
import math
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.config import Settings
from app.services.audd_recognition import recognize_audd


def dbfs(value):
    return round(20 * math.log10(max(float(value), 1e-9) / 32768), 1)


async def diagnose(path, check_audd=False):
    with wave.open(str(path), "rb") as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        if width != 2:
            raise ValueError("This diagnostic expects PCM 16-bit WAV.")
        data = wav.readframes(wav.getnframes())
    samples = np.frombuffer(data, dtype="<i2").reshape(-1, channels).astype(np.float64)
    mono = samples.mean(axis=1)
    seconds = len(mono) / rate
    windows = [mono[start:start + rate] for start in range(0, len(mono), rate)]
    rms = float(np.sqrt(np.mean(mono * mono))) if len(mono) else 0
    print(json.dumps({"duration_seconds": round(seconds, 3), "sample_rate": rate,
        "channels": channels, "pcm_bits": width * 8, "rms_dbfs": dbfs(rms),
        "peak_dbfs": dbfs(np.max(np.abs(samples)) if len(samples) else 0),
        "clipped_sample_percent": round(float(np.mean(np.abs(samples) >= 32760) * 100), 3),
        "seconds_rms_dbfs": [dbfs(np.sqrt(np.mean(window * window))) for window in windows]}, ensure_ascii=False))
    if not check_audd:
        return
    settings = Settings(_env_file=BACKEND / ".env.local")
    if not settings.audd_api_token.strip():
        print(json.dumps({"error": "AUDD_API_TOKEN is not configured"}))
        return
    starts = [0]
    if seconds > 13:
        starts.append(max(0, len(samples) - 12 * rate))
    # Stop after first match. No automatic retry or unbounded quota consumption.
    with tempfile.TemporaryDirectory(prefix="mdvn-diagnose-") as temporary:
        for start in starts:
            clip = Path(temporary) / "clip.wav"
            chunk = samples[start:start + 12 * rate].astype("<i2")
            with wave.open(str(clip), "wb") as output:
                output.setnchannels(channels); output.setsampwidth(2); output.setframerate(rate)
                output.writeframes(chunk.tobytes())
            try:
                result = await recognize_audd(clip, settings.audd_api_token)
                print(json.dumps({"offset_seconds": round(start / rate, 3),
                                  "provider": "audd", "results": result}, ensure_ascii=False))
                if result:
                    break
            except HTTPException as exc:
                print(json.dumps({"status": exc.status_code, "error": str(exc.detail)}, ensure_ascii=False))
                break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--check-audd", action="store_true", help="Send at most two real requests using backend token.")
    args = parser.parse_args()
    asyncio.run(diagnose(args.file, args.check_audd))


if __name__ == "__main__":
    main()
