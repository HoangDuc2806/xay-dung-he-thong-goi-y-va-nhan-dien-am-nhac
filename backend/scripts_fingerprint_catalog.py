"""Export v2 fingerprints as JSON. Use tools/index_licensed_audio.py for database indexing."""
import argparse
import json
import tempfile
from pathlib import Path
from app.core.config import Settings
from app.services.audio_decode import decode_audio
from app.services.landmark_fingerprint import ALGORITHM, fingerprint_wav


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    settings = Settings(_env_file=Path(__file__).parent / ".env.local")
    with tempfile.TemporaryDirectory(prefix="mdvn-export-") as temp:
        wav = Path(temp) / "audio.wav"
        duration = decode_audio(args.file, wav, ffmpeg=settings.recognition_ffmpeg_path,
                                ffprobe=settings.recognition_ffprobe_path)
        points = fingerprint_wav(wav, max_points=2_000_000, max_seconds=1800)
    print(json.dumps({"algorithm": ALGORITHM, "duration_seconds": duration,
                      "points": [{"hash": digest, "offset_ms": offset} for digest, offset in points]}))


if __name__ == "__main__":
    main()
