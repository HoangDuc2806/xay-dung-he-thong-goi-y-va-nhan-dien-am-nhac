"""Fetch/cache independent MusicBrainz core metadata at <=1 request/second."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import httpx
from app.services.recommendation import artist_key

DEFAULT_ARTISTS=["B-Ray","HIEUTHUHAI","Rhymastic","JustaTee","Phương Ly","Chillies"]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artist",action="append",help="Repeat for multiple artist names; ambiguous identities are skipped")
    parser.add_argument("--refresh",action="store_true")
    args=parser.parse_args()
    folder=Path("data/musicbrainz");folder.mkdir(parents=True,exist_ok=True)
    cache={}
    for file in folder.glob("*.json"):
        data=json.loads(file.read_text(encoding="utf-8-sig"));cache[artist_key(data["artist"]["name"])]=data
    count=0
    with httpx.Client(timeout=25,headers={"User-Agent":"MusicDiscoveryVN/0.1 (academic metadata importer; https://github.com/HoangDuc2806)"}) as client:
        def request(entity,query):
            for attempt in range(3):
                time.sleep(1.2 if not attempt else 2**attempt)
                response=client.get(f"https://musicbrainz.org/ws/2/{entity}/",params={"query":query,"fmt":"json","limit":100})
                if response.status_code in (429,503) and attempt<2:continue
                response.raise_for_status()
                return json.loads(response.content)
        for name in args.artist or DEFAULT_ARTISTS:
            if not args.refresh and artist_key(name) in cache:
                print("Using verified cache:",name);count+=1;continue
            try:
                escaped=name.replace("\\","\\\\").replace('"','\\"')
                matches=[artist for artist in request("artist",f'artist:"{escaped}"')["artists"] if artist_key(artist["name"])==artist_key(name)]
                if len(matches)!=1:
                    print("Skipped ambiguous identity:",name);continue
                artist=matches[0];records=request("recording","arid:"+artist["id"])
                payload={"artist":artist,"recordings":records["recordings"],"recording_count":records["count"],"retrieved_at":datetime.now(timezone.utc).isoformat()}
                (folder/(artist["id"]+".json")).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
                print(f"Fetched {name}: {len(records['recordings'])} recordings");count+=1
            except (httpx.HTTPError,ValueError,KeyError):print("Source unavailable:",name)
    if not count:raise SystemExit("No source metadata available. Retry later; no catalog was changed.")


if __name__=="__main__":main()
