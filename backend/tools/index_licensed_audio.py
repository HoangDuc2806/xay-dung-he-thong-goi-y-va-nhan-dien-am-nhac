"""Index authorized reference audio for the project's landmark recognition algorithm."""
from __future__ import annotations
import argparse
import sys
import tempfile
from pathlib import Path
from uuid import UUID, uuid4
import psycopg

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))
from app.core.config import Settings
from app.services.audio_decode import decode_audio, AudioDecoderUnavailable, InvalidAudio, AudioDurationExceeded
from app.services.landmark_fingerprint import ALGORITHM, fingerprint_wav

def main()->int:
    cli=argparse.ArgumentParser()
    cli.add_argument("--track-id",type=UUID)
    cli.add_argument("--title")
    cli.add_argument("--artist")
    cli.add_argument("--source-url")
    cli.add_argument("--source-license")
    cli.add_argument("--file",required=True,type=Path)
    cli.add_argument("--i-have-rights",action="store_true")
    options=cli.parse_args()
    if not options.i_have_rights:cli.error("Audio fingerprinting requires permission from the rights holder.")
    if not options.file.is_file():cli.error("Audio file is missing.")
    if not options.track_id and not all(value and value.strip() for value in (
        options.title, options.artist, options.source_url, options.source_license,
    )):
        cli.error("Provide --track-id, or --title --artist --source-url --source-license.")
    if not options.track_id and not options.source_url.startswith("https://"):
        cli.error("--source-url must start with https://.")
    settings = Settings(_env_file=BACKEND / ".env.local")
    db_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    if not db_url:cli.error("Set DATABASE_URL in backend/.env.local or administrator environment.")
    try:
        with tempfile.TemporaryDirectory(prefix="mdvn-index-") as t:
            wav=Path(t)/"audio.wav"
            duration=decode_audio(options.file,wav,ffmpeg=settings.recognition_ffmpeg_path,
                                  ffprobe=settings.recognition_ffprobe_path,max_duration=1800)
            # Index the entire reference (up to 30 minutes), not just its intro.
            points=fingerprint_wav(wav,max_points=2_000_000,max_seconds=1800)
        if len({digest for digest, _ in points}) < settings.recognition_landmark_min_votes:
            cli.error("Insufficient distinct landmarks. Choose clear audio with changing musical content.")
        track_id = options.track_id or uuid4()
        with psycopg.connect(db_url,connect_timeout=10) as conn, conn.cursor() as cur:
            if options.track_id:
                cur.execute("select 1 from public.music_catalog where id=%s", (track_id,))
                if not cur.fetchone():cli.error("Track does not exist in music_catalog.")
            else:
                cur.execute("""insert into public.music_catalog
                    (id,title,artist,spotify_search_query,source,source_url,source_license)
                    values (%s,%s,%s,%s,%s,%s,%s)""",
                    (track_id,options.title.strip(),options.artist.strip(),
                     f"{options.title.strip()} {options.artist.strip()}","Authorized reference recording",
                     options.source_url,options.source_license))
            # Re-indexing is transactional: a failed insert rolls back deletion.
            cur.execute("delete from public.music_fingerprint_points where track_id=%s and algorithm=%s",(track_id,ALGORITHM))
            for start in range(0,len(points),5000):
                cur.executemany(
                    "insert into public.music_fingerprint_points(track_id,hash,offset_ms,algorithm) values(%s,%s,%s,%s) on conflict do nothing",
                    [(track_id,h,offset,ALGORITHM) for h,offset in points[start:start+5000]],
                )
        print(f"Indexed track {track_id}: {len(points)} points, {duration}s, {ALGORITHM}.")
        print("Open /identify and record a 10-15 second excerpt of this recording.")
        return 0
    except (AudioDecoderUnavailable,InvalidAudio,AudioDurationExceeded,ValueError) as exc:
        print(f"Audio indexing failed: {exc}",file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(f"Database indexing failed (SQLSTATE {exc.sqlstate or 'connection error'}). Check DATABASE_URL, migrations and administrator permissions.",file=sys.stderr)
        return 1

if __name__=="__main__":raise SystemExit(main())
