"""Index one licensed audio recording for the independent landmark matcher.

Requires an administrator DB connection and affirmative rights confirmation.
Usage:
  DATABASE_URL=... python backend/tools/index_licensed_audio.py --track-id UUID --file licensed.wav --i-have-rights
No Spotify audio may be downloaded, captured, copied, or indexed via this tool.
"""
from __future__ import annotations
import argparse
import os
import sys
import tempfile
from pathlib import Path
import psycopg

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.audio_decode import decode_audio
from app.services.landmark_fingerprint import ALGORITHM, fingerprint_wav

def main()->int:
    cli=argparse.ArgumentParser()
    cli.add_argument("--track-id",required=True)
    cli.add_argument("--file",required=True,type=Path)
    cli.add_argument("--i-have-rights",action="store_true")
    options=cli.parse_args()
    if not options.i_have_rights:cli.error("Audio fingerprinting requires permission from the rights holder.")
    if not options.file.is_file():cli.error("Audio file is missing.")
    db_url=os.getenv("DATABASE_URL")
    if not db_url:cli.error("Provide DATABASE_URL only in administrator environment.")
    with tempfile.TemporaryDirectory(prefix="mdvn-index-") as t:
        wav=Path(t)/"audio.wav"
        duration=decode_audio(options.file,wav,max_duration=1800)
        points=fingerprint_wav(wav,max_points=100000,max_seconds=300)
    if len(points)<20:cli.error("Insufficient unique musical fingerprint points.")
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute("select 1 from public.music_catalog where id=%s", (options.track_id,))
        if not cur.fetchone():cli.error("Track does not exist in music_catalog.")
        cur.execute("delete from public.music_fingerprint_points where track_id=%s and algorithm=%s",(options.track_id,ALGORITHM))
        cur.executemany(
            "insert into public.music_fingerprint_points(track_id,hash,offset_ms,algorithm) values(%s,%s,%s,%s) on conflict do nothing",
            [(options.track_id,h,offset,ALGORITHM) for h,offset in points],
        )
    print(f"Indexed {len(points)} fingerprint points from first {min(duration,300)}s of authorized audio.")
    return 0

if __name__=="__main__":raise SystemExit(main())
