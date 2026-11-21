"""Independent MFCC + subsequence DTW matcher; no pretrained/cloud model.

This is a small-catalog baseline, not an implementation of Shazam or AudD.
"""
from functools import lru_cache
from pathlib import Path
import wave
import numpy as np

SAMPLE_RATE = 11025
HOP = 512


def resample_audio(samples, source_rate, target_rate=SAMPLE_RATE):
    samples = np.asarray(samples, dtype=np.float32)
    if source_rate == target_rate:
        return samples
    if source_rate > target_rate:
        t = np.arange(-48, 49, dtype=np.float64)
        cutoff = 0.45 * target_rate/source_rate
        kernel = 2*cutoff*np.sinc(2*cutoff*t)*np.hanning(len(t))
        kernel /= kernel.sum()
        samples = np.convolve(samples, kernel, mode="same")
    count = int(len(samples)*target_rate/source_rate)
    return np.interp(np.arange(count)*source_rate/target_rate, np.arange(len(samples)), samples).astype(np.float32)


def read_pcm(path: Path, max_seconds=120):
    with wave.open(str(path), "rb") as audio:
        if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or audio.getframerate()!=SAMPLE_RATE:
            raise ValueError("Expected normalized 11025 Hz mono PCM16 WAV")
        return np.frombuffer(audio.readframes(min(audio.getnframes(), int(max_seconds*SAMPLE_RATE))), dtype="<i2").astype(np.float32)/32768


@lru_cache(maxsize=1)
def _filters():
    n_fft, bands = 1024, 40
    mel = lambda value: 2595*np.log10(1+value/700)
    hz = lambda value: 700*(10**(value/2595)-1)
    edges = hz(np.linspace(mel(80), mel(5000), bands+2))
    frequencies = np.fft.rfftfreq(n_fft, 1/SAMPLE_RATE)
    bank = np.zeros((bands, len(frequencies)))
    for band in range(bands):
        left, center, right = edges[band:band+3]
        bank[band] = np.maximum(0, np.minimum((frequencies-left)/(center-left), (right-frequencies)/(right-center)))
    # DCT-II cepstra C1..C13, excluding the gain-dominated C0 coefficient.
    dct = np.cos(np.pi/bands*(np.arange(bands)+0.5)[None,:]*np.arange(1,14)[:,None])*np.sqrt(2/bands)
    return bank.astype(np.float32), dct.astype(np.float32)


def mfcc_features(samples):
    samples = np.asarray(samples, dtype=np.float32)
    if len(samples) < 1024 or np.sqrt(np.mean(samples*samples)) < 1e-4:
        return np.zeros((0,13), dtype=np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(samples, 1024)[::HOP]
    spectrum = np.abs(np.fft.rfft(frames*np.hanning(1024), axis=1))**2
    bank, dct = _filters()
    cepstra = np.log(np.maximum(spectrum @ bank.T, 1e-9)) @ dct.T
    # Normalize each vector: gain changes affect C0, omitted above.
    cepstra /= np.maximum(np.linalg.norm(cepstra, axis=1, keepdims=True), 1e-9)
    return cepstra.astype(np.float32)


def subsequence_dtw(query, reference):
    """Average cosine cost; subsequence start is free, tempo steps are bounded.

Allowed (query, reference) steps: (1,1), (1,2), (2,1). Weight local
cost by query progress so paths of different lengths remain comparable.
"""
    if len(query)<3 or len(reference)<len(query)//2:
        return float("inf"), 0
    cost = np.maximum(0, 1-query@reference.T)
    previous2 = np.full(len(reference)+2, np.inf, dtype=np.float32)
    previous = np.zeros(len(reference)+2, dtype=np.float32)
    current = np.full_like(previous2, np.inf)
    alternate = np.empty_like(cost[0])
    for i, row in enumerate(cost):
        current[:2] = np.inf
        np.minimum(previous[1:-1], previous[:-2], out=current[2:])
        current[2:] += row
        if i >= 1:
            np.add(previous2[1:-1], cost[i-1], out=alternate)
            alternate += row
            np.minimum(current[2:], alternate, out=current[2:])
        previous2, previous, current = previous, current, previous2
    end = int(np.argmin(previous[2:]))
    return float(previous[end+2]/len(query)), round(end*HOP*1000/SAMPLE_RATE)
