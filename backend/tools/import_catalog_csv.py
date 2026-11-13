"""Import independently sourced catalog metadata into Supabase PostgreSQL.

CSV: title,artist,album,release_year,genres,moods,tags,language,
     spotify_search_query,artwork_url,source,source_url,source_license
Tags/genres/moods are pipe-separated. Run with DATABASE_URL admin credentials,
never from the public frontend. No audio is downloaded or analyzed.
"""
import argparse,csv,os,re,uuid
from pathlib import Path
import psycopg

def nonempty(value,name):
    text=(value or "").strip()
    if not text:raise ValueError("Missing "+name)
    return text
def split(value):
    return [t.strip().casefold() for t in (value or "").split("|") if t.strip()][:40]
def normal(row):
    title=nonempty(row.get("title"),"title")
    artist=nonempty(row.get("artist"),"artist")
    source=nonempty(row.get("source"),"source")
    url=nonempty(row.get("source_url"),"source_url")
    if not re.match(r"^https://[A-Za-z0-9.-]+/",url):raise ValueError("source_url must be an HTTPS page")
    license_name=nonempty(row.get("source_license"),"source_license")
    track_id=uuid.uuid5(uuid.NAMESPACE_URL,url+"|"+title+"|"+artist)
    return (str(track_id),title,artist,row.get("album") or None,
            int(row["release_year"]) if row.get("release_year") else None,
            split(row.get("genres")),split(row.get("moods")),split(row.get("tags")),
            (row.get("language") or "other").strip().casefold(),
            (row.get("spotify_search_query") or f"{title} {artist}").strip(),
            row.get("artwork_url") or None,source,url,license_name)

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("catalog_csv",type=Path)
    cli.add_argument("--acknowledge-provenance",action="store_true")
    args=cli.parse_args()
    if not args.acknowledge_provenance:cli.error("You must verify and acknowledge metadata provenance and rights.")
    url=os.getenv("DATABASE_URL")
    if not url:cli.error("DATABASE_URL is required in the administrator environment.")
    with args.catalog_csv.open(encoding="utf-8-sig",newline="") as file:
        rows=list(csv.DictReader(file))
    records=[normal(x) for x in rows]
    with psycopg.connect(url) as db, db.cursor() as cur:
        cur.executemany("""
            insert into public.music_catalog
            (id,title,artist,album,release_year,genres,moods,tags,language,
             spotify_search_query,artwork_url,source,source_url,source_license)
            values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict(id) do update set
             title=excluded.title,artist=excluded.artist,album=excluded.album,
             genres=excluded.genres,moods=excluded.moods,tags=excluded.tags,
             language=excluded.language,spotify_search_query=excluded.spotify_search_query,
             source=excluded.source,source_url=excluded.source_url,
             source_license=excluded.source_license
        """,records)
    print(f"Imported {len(records)} source-verified metadata rows.")
if __name__=="__main__":main()
