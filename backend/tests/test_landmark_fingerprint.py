"""Signal-level regression tests; no API key, database or licensed audio needed."""
import wave
import numpy as np
import pytest
from app.services.landmark_fingerprint import fingerprint_wav, offset_vote_matches, sample_query_points


def write_wav(path, samples, rate=11025):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(np.clip(samples, -32767, 32767).astype("<i2").tobytes())


def melody(seed, duration=22):
    rate = 11025
    rng = np.random.default_rng(seed)
    time = np.arange(rate * duration) / rate
    notes = rng.choice([277, 330, 392, 440, 523, 622, 740, 880], int(duration / 0.3) + 1)
    frequency = notes[np.minimum((time / 0.3).astype(int), len(notes) - 1)]
    phase = 2 * np.pi * np.cumsum(frequency) / rate
    return 11000 * (np.sin(phase) + 0.4 * np.sin(2 * phase) + 0.2 * np.sin(3 * phase))


@pytest.mark.parametrize("offset", [2.137, 8.319])
def test_recognizes_unaligned_excerpt_with_noise_and_lower_volume(tmp_path, offset):
    original = melody(42)
    reference = tmp_path / "reference.wav"
    other = tmp_path / "other.wav"
    clip = tmp_path / "clip.wav"
    write_wav(reference, original)
    write_wav(other, melody(87))
    begin = int(offset * 11025)
    excerpt = original[begin:begin + 8 * 11025] * 0.55
    excerpt += np.random.default_rng(8).normal(0, 250, len(excerpt))
    write_wav(clip, excerpt)
    points = sample_query_points(fingerprint_wav(clip))
    result = offset_vote_matches(points, {
        "correct": fingerprint_wav(reference, max_points=100000),
        "other": fingerprint_wav(other, max_points=100000),
    })
    assert result and result[0][0] == "correct"
    assert result[0][1] >= 12 and result[0][2] >= 0.05


def test_silence_has_no_fingerprint(tmp_path):
    path = tmp_path / "silence.wav"
    write_wav(path, np.zeros(11025 * 6))
    assert fingerprint_wav(path) == []


def test_duplicate_hashes_cannot_inflate_votes():
    repeated = [("1234567890abcdef", x * 125) for x in range(200)]
    assert offset_vote_matches(repeated, {"tone": repeated}) == []
    assert len(sample_query_points(repeated)) == 1


def test_unrelated_noise_is_not_accepted_as_a_known_song(tmp_path):
    reference = tmp_path / "song.wav"
    noise = tmp_path / "noise.wav"
    write_wav(reference, melody(42))
    write_wav(noise, np.random.default_rng(9).normal(0, 3000, 8 * 11025))
    query = sample_query_points(fingerprint_wav(noise))
    result = offset_vote_matches(query, {"song": fingerprint_wav(reference, max_points=100000)})
    assert not any(votes >= 12 and score >= 0.05 for _, votes, score in result)


def test_empty_and_nonmatching_queries():
    assert offset_vote_matches([], {"a": []}) == []
    assert offset_vote_matches([("abcdef1234567890", 0)], {"a": [("1234567890abcdef", 0)]}) == []


def test_query_sampling_is_bounded_and_spans_clip():
    points = [(f"{index:016x}", index * 10) for index in range(2000)]
    sampled = sample_query_points(points)
    assert len(sampled) == 400
    assert sampled[0] == points[0] and sampled[-1] == points[-1]


def test_fingerprint_requires_normalized_sample_rate(tmp_path):
    path = tmp_path / "wrong-rate.wav"
    write_wav(path, np.zeros(22050), rate=22050)
    with pytest.raises(ValueError, match="11025"):
        fingerprint_wav(path)
