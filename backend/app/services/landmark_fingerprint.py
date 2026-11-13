"""Independent offset-aware spectral-landmark fingerprinting for licensed audio.

mdvn-landmark-v2 is *not* compatible with AcoustID or Spotify. Index only audio
whose owner has authorized fingerprinting. Scores must be calibrated on real clips.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import wave

import numpy as np

ALGORITHM = "mdvn-landmark-v2"

def fingerprint_wav(path: Path, *, max_points: int = 11000, max_seconds: int = 120) -> list[tuple[str, int]]:
    import hashlib
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError("Fingerprint requires 16-bit mono PCM WAV.")
        sample_rate=wf.getframerate()
        samples=np.frombuffer(wf.readframes(wf.getnframes()), dtype="<i2").astype(np.float32)
    window=2048
    hop=512
    if len(samples)<window: return []
    frames=np.lib.stride_tricks.sliding_window_view(samples,window)[::hop]
    # Bounded processing: spectrogram peaks for at most max_seconds.
    frames=frames[:int(sample_rate*max_seconds/hop)]
    spectrum=np.abs(np.fft.rfft(frames*np.hanning(window),axis=1))
    lower=max(1,int(260*window/sample_rate))
    upper=min(window//2,int(3500*window/sample_rate))
    peaks_by_frame=[]
    for row in spectrum:
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
        for dt in (5,8,12,18,25,35):
            end=frame_index+dt
            if end>=len(peaks_by_frame):continue
            for a in anchors:
                for b in peaks_by_frame[end]:
                    raw=f"{a}:{b}:{dt}".encode()
                    digest=hashlib.blake2s(raw,digest_size=8).hexdigest()
                    result.append((digest,round(frame_index*hop*1000/sample_rate)))
    if len(result) > max_points:
        # Keep hashes sampled throughout the full segment instead of truncating
        # to the beginning; preserves matching late portions of the recording.
        step=max(1,(len(result)+max_points-1)//max_points)
        result=result[::step][:max_points]
    return result

def offset_vote_matches(query: list[tuple[str,int]], references: dict[str,list[tuple[str,int]]], *, tolerance_ms: int = 125) -> list[tuple[str,int,float]]:
    """Offset-aligned voting used by unit tests and small offline evaluation sets."""
    if not query:return []
    index=defaultdict(list)
    for track,points in references.items():
        for digest,time_ms in points:
            index[digest].append((track,time_ms))
    votes=Counter()
    for digest,qtime in query:
        for track,rtime in index.get(digest,[]):
            shift=round((rtime-qtime)/tolerance_ms)
            votes[(track,shift)]+=1
    out=[]
    for track in references:
        best=max((count for (key,_),count in votes.items() if key==track),default=0)
        if best>=6:out.append((track,best,min(1.0,best/max(1,len(query)))))
    return sorted(out,key=lambda v:v[1],reverse=True)
