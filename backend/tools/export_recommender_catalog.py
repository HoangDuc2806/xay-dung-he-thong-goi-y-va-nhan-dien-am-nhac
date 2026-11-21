"""Export learned song metadata for the existing admin catalog importer.

No audio, user IDs, interaction histories or Spotify metadata are exported.
"""
import argparse
import csv
import json
from pathlib import Path


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--model", type=Path, default=Path("artifacts/recommender.json"))
    cli.add_argument("--output", type=Path, default=Path("data/catalog_listenbrainz.csv"))
    args = cli.parse_args()
    model = json.loads(args.model.read_text(encoding="utf-8"))
    if model.get("version") != 1 or model.get("algorithm") != "item-knn-cosine":
        cli.error("Unsupported model")
    fields = ["id", "title", "artist", "album", "release_year", "genres", "moods", "tags", "language", "spotify_search_query", "artwork_url", "source", "source_url", "source_license"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for item in model["items"]:
            writer.writerow({**{field: item.get(field) for field in fields},
                             **{field: "|".join(item.get(field) or []) for field in ("genres", "moods", "tags")}})
    print(f"Exported {len(model['items'])} independent metadata rows to {args.output}")


if __name__ == "__main__":
    main()
