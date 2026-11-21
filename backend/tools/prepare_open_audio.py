"""Prepare a small attributed CC-BY music benchmark from Wikimedia Commons.

Only download allowlisted files after checking their current audio license.
Raw audio and derived excerpts remain in ignored backend/data.
"""
import hashlib
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx
import numpy as np
import soundfile as sf

TITLES = ["Tranquility", "Ritual", "Broken Reality", "On the Passing of Time", "Parisian", "Thatched Villagers", "The Endless", "Radio Martini"]
ORIGINAL_SOURCES = [
    (f"File:Kevin MacLeod - {title}.ogg", title, "Kevin MacLeod", role)
    for title, role in zip(TITLES, ["reference"] * 6 + ["calibration_unknown", "test_unknown"])
]
ADDITIONAL_SOURCES = [
    ("File:The Entertainer by Kevin MacLeod.ogg", "The Entertainer", "Kevin MacLeod", "reference"),
    ("File:Josh Woodward - Swansong.ogg", "Swansong", "Josh Woodward", "reference"),
    ("File:Josh Woodward - 01 - California Lullabye.ogg", "California Lullabye", "Josh Woodward", "reference"),
    ("File:Wikipedia guitar solo.ogg", "Guitar Solo in F# Minor", "Leechfoot", "reference"),
    ("File:Maple Leaf Rag by Kevin MacLeod.ogg", "Maple Leaf Rag", "Kevin MacLeod", "test_unknown"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", action="store_true", help="Use the original eight recordings")
    parser.add_argument("--reference-seconds", type=int, choices=range(39, 121), metavar="39–120")
    args = parser.parse_args()
    sources = ORIGINAL_SOURCES if args.original else ORIGINAL_SOURCES + ADDITIONAL_SOURCES
    reference_seconds = args.reference_seconds or (60 if args.original else 120)
    folder = Path("data/recognition")
    folder.mkdir(parents=True, exist_ok=True)
    manifest = []
    with httpx.Client(timeout=60, headers={"User-Agent": "MusicDiscoveryVN/0.1 academic-audio-benchmark (https://github.com/HoangDuc2806)"}) as client:
        response = client.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata",
            "titles": "|".join(row[0] for row in sources)})
        response.raise_for_status()
        pages = {page["title"]: page for page in response.json()["query"]["pages"].values()}
        for index, (filename, title, artist, role) in enumerate(sources):
            page = pages[filename]
            info = page["imageinfo"][0]
            metadata = info["extmetadata"]
            license_name = metadata.get("LicenseShortName", {}).get("value", "")
            license_url = metadata.get("LicenseUrl", {}).get("value", "")
            allowed_licenses = {"CC BY 3.0", "CC BY 3.0 us", "CC BY 4.0", "CC0", "CC0 1.0"}
            if license_name not in allowed_licenses or urlparse(license_url).hostname != "creativecommons.org":
                raise ValueError("Unexpected license for " + title + ": " + license_name)
            if urlparse(info["url"]).hostname != "upload.wikimedia.org":
                raise ValueError("Unexpected audio download host")
            raw = folder / ("source-" + hashlib.sha256(info["url"].encode()).hexdigest()[:12] + ".ogg")
            if not raw.exists():
                with client.stream("GET", info["url"]) as download:
                    download.raise_for_status()
                    total = 0
                    with raw.with_suffix(".partial").open("wb") as file:
                        for block in download.iter_bytes(1024*1024):
                            total += len(block)
                            if total > 25*1024*1024:
                                raise ValueError("Audio exceeds 25 MiB limit")
                            file.write(block)
                raw.with_suffix(".partial").replace(raw)
            with sf.SoundFile(raw) as audio:
                samples = audio.read(min(audio.frames, audio.samplerate*(reference_seconds + 1)), dtype="float32", always_2d=True).mean(axis=1)
                source_rate = audio.samplerate
            # Anti-alias FIR before resampling to the algorithm's common sample rate.
            from app.services.mfcc_dtw import resample_audio
            samples = resample_audio(samples, source_rate, 11025)[:reference_seconds*11025]
            if len(samples) < 39*11025:
                raise ValueError("Audio too short for disjoint benchmark query windows")
            path = folder / f"track-{index}.wav"
            sf.write(path, samples, 11025, subtype="PCM_16")
            manifest.append({"id": f"open-{index}", "title": title, "artist": artist, "file": path.name,
                             "source_url": info["descriptionurl"], "download_url": info["url"],
                             "license": license_name, "license_url": license_url,
                             "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                             "role": role,
                             "duration_seconds": round(len(samples)/11025, 3),
                             "changes": f"Up to first {reference_seconds} seconds, mono, anti-aliased resampling to 11025 Hz, PCM16"})
            print(f"Prepared {title}: {license_name}")
    (folder/"manifest.json").write_text(json.dumps({"tracks": manifest}, indent=2, ensure_ascii=False), encoding="utf-8")
    credits = "# Audio credits\n\n" + "\n\n".join(f"{row['title']} — {row['artist']}. {row['license']} ({row['license_url']}). Source: {row['source_url']}. Changes: {row['changes']}." for row in manifest)
    (folder/"ATTRIBUTION.md").write_text(credits + "\n", encoding="utf-8")
    Path("artifacts").mkdir(parents=True,exist_ok=True)
    Path("artifacts/recognition_sources.json").write_text(json.dumps({"tracks": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
