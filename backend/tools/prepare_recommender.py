"""Download/check an official dump, then train. Does not modify the database."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse
import httpx

DEFAULT_URL = "https://data.metabrainz.org/pub/musicbrainz/listenbrainz/incremental/listenbrainz-dump-2782-20261113-000002-incremental/listenbrainz-listens-dump-2782-20261113-000002-incremental.tar.zst"


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--url", default=DEFAULT_URL)
    cli.add_argument("--since", default="2026-10-13")
    cli.add_argument("--max-items", type=int, default=2000)
    cli.add_argument("--max-users", type=int, default=5000)
    args = cli.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != "https" or parsed.netloc != "data.metabrainz.org" or not parsed.path.startswith("/pub/musicbrainz/listenbrainz/") or not parsed.path.endswith(".tar.zst"):
        cli.error("Only official HTTPS ListenBrainz .tar.zst dumps are supported")
    folder = Path("data/raw")
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / Path(parsed.path).name
    with httpx.Client(timeout=120, follow_redirects=False, headers={"User-Agent": "MusicDiscoveryVN/0.1 (academic recommender)"}) as client:
        checksum = client.get(args.url + ".sha256")
        checksum.raise_for_status()
        expected = checksum.text.strip().split()[0].lower()
        if not re.fullmatch(r"[a-f0-9]{64}", expected):
            cli.error("Invalid official SHA256 checksum")
        if not destination.exists():
            temporary = destination.with_suffix(".partial")
            with client.stream("GET", args.url) as response:
                response.raise_for_status()
                size = int(response.headers.get("content-length", 0))
                if size > 600*1024*1024:
                    cli.error("Dump exceeds the 600 MiB download budget; choose a smaller incremental dump")
                total = 0
                with temporary.open("wb") as file:
                    for block in response.iter_bytes(1024*1024):
                        total += len(block)
                        if total > 600*1024*1024:
                            cli.error("Download exceeded 600 MiB")
                        file.write(block)
            temporary.replace(destination)
    with destination.open("rb") as file:
        actual = hashlib.file_digest(file, "sha256").hexdigest()
    if actual != expected:
        cli.error("Checksum mismatch. Remove the invalid local archive and download again.")
    print("Official SHA256 verified. Training and evaluating...")
    result = subprocess.run([sys.executable, "-m", "tools.train_recommender", str(destination),
                             "--source-url", args.url, "--since", args.since,
                             "--max-items", str(args.max_items), "--max-users", str(args.max_users)])
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
