"""Integration tests for real FFmpeg decoding and independent landmark matching."""
import shutil
import subprocess
import wave
from pathlib import Path
import numpy as np
import pytest

from app.services.audio_decode import decode_audio, InvalidAudio
from app.services.landmark_fingerprint import fingerprint_wav, offset_vote_matches

def make_signal(path:Path, duration:float=9.0,rate:int=11025):
    t=np.arange(int(rate*duration))/rate
    # Multiple changing pitches and harmonics make a repeatable musical-like signal.
    freq=np.where(t<3,440,np.where(t<6,523.25,659.25))
    phase=2*np.pi*np.cumsum(freq)/rate
    envelope=0.5+0.5*np.sin(2*np.pi*2*t)
    signal=((np.sin(phase)+0.35*np.sin(phase*1.5))*0.4*envelope*32767).astype("<i2")
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(signal.tobytes())

@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="FFmpeg unavailable")
@pytest.mark.parametrize("extension,encoder",[
    ("wav","pcm_s16le"),("mp3","libmp3lame"),("webm","libopus"),("ogg","libvorbis"),
    ("flac","flac"),("m4a","aac"),("aiff","pcm_s16be"),
])
def test_decode_real_audio_formats(tmp_path,extension,encoder):
    source=tmp_path/"tone.wav"
    make_signal(source,5.5)
    uploaded=tmp_path/("input."+extension)
    result=subprocess.run(["ffmpeg","-v","error","-y","-i",str(source),"-c:a",encoder,str(uploaded)],
                          capture_output=True)
    if result.returncode:pytest.skip("Encoder unavailable: "+encoder)
    decoded=tmp_path/"normalized.wav"
    duration=decode_audio(uploaded,decoded,max_duration=20)
    assert 5 <= duration <= 6
    assert decoded.exists()

@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="FFmpeg unavailable")
def test_invalid_audio_is_rejected(tmp_path):
    path=tmp_path/"bad.webm";path.write_bytes(b"not a webm")
    with pytest.raises(InvalidAudio):
        decode_audio(path,tmp_path/"out.wav",max_duration=20)

def test_offset_alignment_picks_the_correct_track(tmp_path):
    source=tmp_path/"track.wav";make_signal(source,9)
    with wave.open(str(source),"rb") as wf:
        wav_bytes=wf.readframes(wf.getnframes())
        rate=wf.getframerate()
    query=tmp_path/"clip.wav"
    clip_bytes=wav_bytes[2*rate*2:7*rate*2]
    with wave.open(str(query),"wb") as wf:
        wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(rate);wf.writeframes(clip_bytes)
    full=fingerprint_wav(source)
    segment=fingerprint_wav(query)
    assert len(full)>20 and len(segment)>10
    result=offset_vote_matches(segment,{"same":full,"other":[("abcdef1234567890",0)]})
    assert result and result[0][0]=="same"
