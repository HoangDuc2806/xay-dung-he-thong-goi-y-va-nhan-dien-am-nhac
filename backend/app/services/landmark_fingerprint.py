"""Independent offset-aware spectral-landmark fingerprinting for licensed audio.

mdvn-landmark-v2 is *not* compatible with AcoustID or Spotify. Index only audio
whose owner has authorized fingerprinting. Scores must be calibrated on real clips.
"""
from __future__ import annotations
from collections import defaultdict
from functools import lru_cache
import hashlib
from pathlib import Path
import wave

import numpy as np

ALGORITHM = "mdvn-landmark-v2"
SAMPLE_RATE = 11025


@lru_cache(maxsize=65536)
def _pair_digest(anchor: int, target: int, delta: int) -> str:
    return hashlib.blake2s(f"{anchor}:{target}:{delta}".encode(), digest_size=8).hexdigest()


def sample_query_points(points: list[tuple[str, int]], limit: int = 400) -> list[tuple[str, int]]:
    """RPC counts distinct hashes, so repeated tones must not consume query slots."""
    if limit < 1:
        return []
    by_hash = {}
    for digest, offset in points:
        by_hash.setdefault(digest, (digest, offset))
    unique = sorted(by_hash.values(), key=lambda point: (point[1], point[0]))
    if len(unique) <= limit:
        return unique
    return [unique[int(i)] for i in np.linspace(0, len(unique) - 1, limit)]

def fingerprint_wav(path: Path, *, max_points: int = 11000, max_seconds: int = 120) -> list[tuple[str, int]]:
    if max_points < 1 or max_seconds <= 0:
        raise ValueError("Fingerprint limits must be positive.")
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != SAMPLE_RATE:
            raise ValueError("Fingerprint requires 16-bit mono PCM WAV at 11025 Hz; decode audio first.")
        sample_rate=wf.getframerate()
        samples=np.frombuffer(wf.readframes(min(wf.getnframes(), int(max_seconds * sample_rate))), dtype="<i2").astype(np.float32)
    window=2048
    hop=512
    if len(samples)<window: return []
    frames=np.lib.stride_tricks.sliding_window_view(samples,window)[::hop]
    # Bounded processing: spectrogram peaks for at most max_seconds.
    frames=frames[:int(sample_rate*max_seconds/hop)]
    lower=max(1,int(260*window/sample_rate))
    upper=min(window//2,int(3500*window/sample_rate))
    peaks_by_frame=[]
    # Batch STFT to bound FFT memory even when indexing a complete recording.
    for start in range(0, len(frames), 512):
        batch = frames[start:start + 512]
        spectrum = np.abs(np.fft.rfft(batch * np.hanning(window), axis=1))
        for frame, row in zip(batch, spectrum):
            # Avoid indexing digital silence and near-silent quantization noise.
            if np.sqrt(np.mean(frame * frame)) < 20:
                peaks_by_frame.append([])
                continue
            band=row[lower:upper]
            candidates=np.flatnonzero((band[1:-1]>band[:-2]) & (band[1:-1]>=band[2:]))+lower+1
            if not len(candidates):
                peaks_by_frame.append([])
                continue
            k=min(4,len(candidates))
            chosen=candidates[np.argpartition(row[candidates],-k)[-k:]]
            peaks_by_frame.append(sorted({int(freq//3) for freq in chosen}))
    result=[]
    # Pair anchor and target peaks, encode frequency bands + time distance.
    for frame_index in range(0,len(peaks_by_frame),2):
        anchors=peaks_by_frame[frame_index]
        offset = round(frame_index * hop * 1000 / sample_rate)
        for dt in (5,8,12,18,25,35):
            end=frame_index+dt
            if end>=len(peaks_by_frame):continue
            for a in anchors:
                for b in peaks_by_frame[end]:
                    result.append((_pair_digest(a, b, dt), offset))
    if len(result) > max_points:
        # Keep hashes sampled throughout the full segment instead of truncating
        # to the beginning; preserves matching late portions of the recording.
        step=max(1,(len(result)+max_points-1)//max_points)
        result=result[::step][:max_points]
    return result

class LandmarkIndex:
    """Index a reference collection once and reuse it across recorded queries."""

    def __init__(self, references):
        self.tracks = tuple(references)
        postings = defaultdict(list)
        for index, points in enumerate(references.values()):
            for digest, time_ms in points:
                postings[digest].append((index, time_ms))
        self.postings = dict(postings)

    def match(self, query, *, tolerance_ms=125):
        # Each digest contributes at most one vote per track/offset bucket.
        query_offsets = defaultdict(list)
        for digest, time_ms in query:
            query_offsets[digest].append(time_ms)
        votes = defaultdict(int)
        best = defaultdict(int)
        for digest, offsets in query_offsets.items():
            buckets = set()
            for track, reference_ms in self.postings.get(digest, ()):
                for query_ms in offsets:
                    delta = reference_ms - query_ms
                    shift = (2 * abs(delta) + tolerance_ms) // (2 * tolerance_ms)
                    buckets.add((track, shift if delta >= 0 else -shift))
            for bucket in buckets:
                votes[bucket] += 1
                track = bucket[0]
                if votes[bucket] > best[track]:
                    best[track] = votes[bucket]
        ranked = sorted(best, key=lambda track: (-best[track], track))
        return [(self.tracks[track], best[track], min(1.0, best[track] / max(10, len(query))))
                for track in ranked if best[track] >= 7]


def offset_vote_matches(query: list[tuple[str,int]], references: dict[str,list[tuple[str,int]]], *, tolerance_ms: int = 125) -> list[tuple[str,int,float]]:
    return LandmarkIndex(references).match(query, tolerance_ms=tolerance_ms) if query else []
