"""Compare the local matchers on labeled WAVs recorded through a microphone."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from app.core.config import Settings
from app.services.audio_decode import prepare_local_pcm
from app.services.local_recognition import accepted_candidate, candidates, load_references
from tools.evaluate_recognition import summarize


METHODS = ("landmark", "mfcc_dtw")


def main():
    settings = Settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON with recordings [{file, expected, condition}]")
    parser.add_argument("--bundle", type=Path, default=Path(settings.recognition_local_bundle))
    parser.add_argument("--thresholds", type=Path, default=Path(settings.recognition_local_evaluation))
    parser.add_argument("--output", type=Path, default=Path("data/recognition/microphone-results.json"))
    args = parser.parse_args()
    references = load_references(args.bundle)
    ids = {row["id"] for row in references}
    labels = json.loads(args.manifest.read_text(encoding="utf-8-sig"))["recordings"]
    if not labels or not any(row["expected"] in ids for row in labels) or not any(row["expected"] is None for row in labels):
        parser.error("Include labeled recordings both inside and outside the reference catalog")
    thresholds = json.loads(args.thresholds.read_text(encoding="utf-8"))["results"]
    source = args.manifest.parent.resolve()
    rows = []
    with TemporaryDirectory(prefix="mdvn-microphone-") as folder:
        wav = Path(folder) / "normalized.wav"
        for label in labels:
            name, expected, condition = label["file"], label["expected"], label["condition"]
            path = (source / name).resolve()
            if not path.is_relative_to(source) or path.suffix.lower() != ".wav" or (expected is not None and expected not in ids):
                parser.error(f"Invalid WAV path or track ID for {name}")
            start = perf_counter()
            duration = prepare_local_pcm(path, wav)
            normalize_ms = (perf_counter() - start) * 1000
            if duration < 5:
                parser.error(f"Need at least five seconds in {name}")
            for method in METHODS:
                start = perf_counter()
                match = accepted_candidate(candidates(wav, references, method), thresholds[method]["threshold"])
                rows.append({"file": name, "condition": condition, "method": method, "expected": expected,
                             "predicted": match["id"] if match else None,
                             "elapsed_ms": round(normalize_ms + (perf_counter() - start) * 1000, 3)})
    report = {"dataset": "Labeled WAV input", "latency": "Local WAV normalization and matching; excludes network",
              "reference_tracks": len(references), "results": {}, "recordings": rows}
    for method in METHODS:
        group = [row for row in rows if row["method"] == method]
        results = summarize(group)
        results["conditions"] = {}
        for name in sorted({row["condition"] for row in group}):
            measured = summarize([row for row in group if row["condition"] == name])
            if not measured["known_queries"]:
                measured["known_recall"] = None
            if not measured["unknown_queries"]:
                measured["unknown_false_accept_rate"] = None
            results["conditions"][name] = measured
        report["results"][method] = results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["results"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
