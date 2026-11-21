"""Evaluate landmark recognition locally before uploading references to Supabase."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.config import Settings
from app.services.audio_decode import decode_audio, AudioDecoderUnavailable, InvalidAudio, AudioDurationExceeded
from app.services.landmark_fingerprint import ALGORITHM, fingerprint_wav, offset_vote_matches, sample_query_points


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", type=Path, required=True, help="A recorded/cropped excerpt.")
    parser.add_argument("--reference", type=Path, action="append", required=True,
                        help="An authorized original recording; repeat to compare multiple songs.")
    args = parser.parse_args()
    if not all(path.is_file() for path in [args.query, *args.reference]):
        parser.error("One or more audio files do not exist.")
    settings = Settings(_env_file=BACKEND / ".env.local")
    try:
        with tempfile.TemporaryDirectory(prefix="mdvn-evaluate-") as temp:
            def extract(path, name, reference=False):
                wav = Path(temp) / name
                decode_audio(path, wav, ffmpeg=settings.recognition_ffmpeg_path,
                             ffprobe=settings.recognition_ffprobe_path)
                return fingerprint_wav(wav, max_points=2_000_000 if reference else 11000,
                                       max_seconds=1800 if reference else 120)
            query = sample_query_points(extract(args.query, "query.wav"))
            references = {str(path): extract(path, f"reference-{i}.wav", True)
                          for i, path in enumerate(dict.fromkeys(args.reference))}
        votes = offset_vote_matches(query, references)
        candidates = [{"reference": name, "votes": count, "score": score}
                      for name, count, score in votes
                      if count >= settings.recognition_landmark_min_votes
                      and score >= settings.recognition_landmark_min_score]
        print(json.dumps({"algorithm": ALGORITHM, "query_hashes": len(query),
                          "status": "matched" if candidates else "not_found",
                          "candidates": candidates}, ensure_ascii=False, indent=2))
        return 0
    except (AudioDecoderUnavailable, InvalidAudio, AudioDurationExceeded, ValueError) as exc:
        print(f"Audio evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
