"""Create mdvn-landmark-v1 hashes for an independently licensed audio catalog item.

Usage: python scripts_fingerprint_catalog.py /path/to/licensed-track.mp3
Output JSON can be used to populate music_catalog.fingerprint_hashes.
Do not fingerprint Spotify streams or audio unless your license permits it.
"""
import json, sys
from app.services.landmark_fingerprint import generate_landmark_fingerprint
if len(sys.argv) != 2:
    raise SystemExit("Usage: python scripts_fingerprint_catalog.py <licensed-audio-file>")
result=generate_landmark_fingerprint(sys.argv[1])
print(json.dumps(result,ensure_ascii=False))
