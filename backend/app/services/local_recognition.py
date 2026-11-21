"""Two local, reproducible recognition algorithms over an attributed small catalog."""
from functools import lru_cache
import json
from pathlib import Path
import numpy as np
from app.services.landmark_fingerprint import fingerprint_wav, LandmarkIndex, sample_query_points
from app.services.mfcc_dtw import mfcc_features, read_pcm, subsequence_dtw


class ReferenceCatalog(list):
    def __init__(self, tracks, landmark_query_points=400):
        self.landmark_index = LandmarkIndex({row["id"]: row["landmarks"] for row in tracks})
        super().__init__({key: value for key, value in row.items() if key != "landmarks"} for row in tracks)
        self.landmark_query_points = landmark_query_points


@lru_cache(maxsize=2)
def _load(path, modified):
    with np.load(path, allow_pickle=False) as data:
        metadata = json.loads(str(data["metadata"]))
        if metadata.get("version") != 1:
            raise ValueError("Unsupported reference bundle")
        tracks = metadata["tracks"]
        for index, track in enumerate(tracks):
            track["mfcc"] = data[f"mfcc_{index}"]
            track["landmarks"] = list(zip(data[f"hashes_{index}"].tolist(), data[f"offsets_{index}"].tolist()))
    query_points = metadata.get("landmark_query_points", 400)
    if type(query_points) is not int or not 100 <= query_points <= 1600:
        raise ValueError("Invalid landmark query limit")
    return ReferenceCatalog(tracks, query_points)


def load_references(path):
    file = Path(path)
    return _load(str(file.resolve()), file.stat().st_mtime_ns)


def candidates(wav, references, method):
    if method == "landmark":
        catalog = references if isinstance(references, ReferenceCatalog) else ReferenceCatalog(references)
        query = sample_query_points(fingerprint_wav(wav), limit=catalog.landmark_query_points)
        votes = catalog.landmark_index.match(query)
        return [{"id": key, "score": score if count >= 12 else 0.0, "votes": count} for key,count,score in votes]
    if method != "mfcc_dtw":
        raise ValueError("Unsupported local matcher")
    features = mfcc_features(read_pcm(wav, max_seconds=15))
    if not len(features):
        return []
    result = []
    for track in references:
        cost, end_ms = subsequence_dtw(features, track["mfcc"])
        if np.isfinite(cost):
            result.append({"id": track["id"], "score": max(0.0, min(1.0, 1-cost)), "distance": cost, "end_ms": end_ms})
    return sorted(result, key=lambda value: (-value["score"], value["id"]))


def accepted_candidate(values, threshold):
    return values[0] if values and values[0]["score"] >= threshold else None
