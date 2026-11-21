"""Build a source-verifiable catalog from cached MusicBrainz core JSON responses.

No audio, Spotify data, user tags, guessed mood or guessed language is imported.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from app.services.musicbrainz_metadata import EXCLUDED_RECORDINGS as EXCLUDED, normalize_recording


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,default=Path("data/musicbrainz"))
    parser.add_argument("--output",type=Path,default=Path("artifacts/catalog_enrichment.json"))
    parser.add_argument("--sql-output",type=Path,help="Optional idempotent metadata seed for Supabase SQL Editor")
    args=parser.parse_args()
    songs={};sources=[]
    for file in sorted(args.input.glob("*.json")):
        data=json.loads(file.read_text(encoding="utf-8-sig"))
        artist_id=data["artist"]["id"]
        for record in data["recordings"]:
            if row:=normalize_recording(record,artist_id):songs[row["id"]]=row
        sources.append({"artist":data["artist"]["name"],"artist_mbid":artist_id,
                        "retrieved_at":data.get("retrieved_at"),"cache_sha256":hashlib.sha256(file.read_bytes()).hexdigest()})
    if not songs:parser.error("No valid independently sourced recordings")
    payload={"version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"sources":sources,
             "license":"CC0-1.0 core metadata only","excluded":EXCLUDED,
             "items":sorted(songs.values(),key=lambda row:(row["artist"],row["title"]))}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    if args.sql_output:
        encoded=json.dumps(payload["items"],ensure_ascii=False).replace("'","''")
        sql="""-- MusicBrainz core metadata CC0-1.0; no audio or inferred mood/language.
-- Sources/provenance: backend/artifacts/catalog_enrichment.json
begin;
insert into public.music_catalog
(id,title,artist,album,release_year,genres,moods,tags,language,artwork_url,spotify_search_query,source,source_url,source_license)
select x.id,x.title,x.artist,x.album,x.release_year,x.genres,x.moods,x.tags,x.language,x.artwork_url,x.spotify_search_query,x.source,x.source_url,x.source_license
from jsonb_to_recordset('__PAYLOAD__'::jsonb) as x(id uuid,title text,artist text,album text,release_year integer,genres text[],moods text[],tags text[],language text,artwork_url text,spotify_search_query text,source text,source_url text,source_license text)
where not exists (select 1 from public.music_catalog c where lower(trim(c.title))=lower(trim(x.title)) and lower(trim(c.artist))=lower(trim(x.artist)) and c.id<>x.id)
on conflict(id) do update set title=excluded.title,artist=excluded.artist,album=excluded.album,spotify_search_query=excluded.spotify_search_query,source=excluded.source,source_url=excluded.source_url,source_license=excluded.source_license;
commit;
""".replace("__PAYLOAD__",encoded)
        args.sql_output.parent.mkdir(parents=True,exist_ok=True)
        args.sql_output.write_text(sql,encoding="utf-8")
    print(json.dumps({"recordings":len(songs),"artists":[source["artist"] for source in sources]},ensure_ascii=True))


if __name__=="__main__":main()
