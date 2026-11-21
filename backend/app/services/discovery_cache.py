"""Persistent public metadata and account-scoped feedback for discovered tracks."""

from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3
from time import time

from app.services.musicbrainz_metadata import LookupResult
from app.services.recommendation import track_key


_SCHEMA = """
CREATE TABLE IF NOT EXISTS discovered_tracks (
    id TEXT PRIMARY KEY, metadata TEXT NOT NULL, added_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS discovered_tracks_recent ON discovered_tracks(added_at DESC, id);
CREATE TABLE IF NOT EXISTS metadata_lookups (
    lookup_key TEXT PRIMARY KEY, status TEXT NOT NULL,
    items TEXT NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS discovered_feedback (
    user_id TEXT NOT NULL, track_id TEXT NOT NULL REFERENCES discovered_tracks(id),
    action TEXT NOT NULL CHECK(action IN ('like', 'save', 'dislike', 'skip')),
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, track_id)
);
CREATE INDEX IF NOT EXISTS discovered_feedback_track ON discovered_feedback(track_id);
"""


@contextmanager
def _connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=2)) as db, db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(_SCHEMA)
        yield db


def cached_lookup(path: Path, key: str) -> LookupResult | None:
    with _connect(path) as db:
        row = db.execute("SELECT status, items FROM metadata_lookups WHERE lookup_key = ? AND expires_at > ?",
                         (key, time())).fetchone()
    return LookupResult(row[0], json.loads(row[1])) if row else None


def remember_lookup(path: Path, key: str, result: LookupResult) -> None:
    now = time()
    lifetime = {"found": 7 * 86400, "not_found": 86400, "ambiguous": 86400, "unavailable": 60}
    with _connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        items = []
        for item in result.items:
            previous = db.execute("SELECT metadata FROM discovered_tracks WHERE id = ?", (item["id"],)).fetchone()
            if previous:
                item = _with_aliases(item, json.loads(previous[0]))
            items.append(item)
        db.executemany("INSERT INTO discovered_tracks VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET metadata = excluded.metadata, added_at = excluded.added_at",
                       [(item["id"], json.dumps(item, ensure_ascii=False), now) for item in items])
        db.execute("DELETE FROM metadata_lookups WHERE expires_at <= ?", (now,))
        db.execute("INSERT OR REPLACE INTO metadata_lookups VALUES (?, ?, ?, ?)",
                   (key, result.status, json.dumps(items, ensure_ascii=False), now + lifetime[result.status]))


def local_profile(path: Path, user_id: str, required_track_id: str | None = None) -> tuple[list[dict], list[dict]]:
    if not path.is_file():
        return [], []
    with _connect(path) as db:
        recent = db.execute("SELECT id, metadata FROM discovered_tracks ORDER BY added_at DESC, id LIMIT 600").fetchall()
        own = db.execute("""SELECT t.id, t.metadata, f.action FROM discovered_feedback AS f
                            JOIN discovered_tracks AS t ON t.id = f.track_id
                            WHERE f.user_id = ? ORDER BY f.updated_at DESC LIMIT 1000""", (user_id,)).fetchall()
        if required_track_id is not None:
            recent.extend(db.execute("SELECT id, metadata FROM discovered_tracks WHERE id = ?", (required_track_id,)).fetchall())
    tracks = {key: json.loads(metadata) for key, metadata in recent}
    tracks.update((key, json.loads(metadata)) for key, metadata, _ in own)
    return list(tracks.values()), [{"track_id": key, "action": action} for key, _, action in own]


def store_feedback(path: Path, user_id: str, track_id: str, action: str) -> bool:
    if not path.is_file():
        return False
    with _connect(path) as db:
        result = db.execute("""INSERT INTO discovered_feedback(user_id, track_id, action, updated_at)
                               SELECT ?, id, ?, ? FROM discovered_tracks WHERE id = ?
                               ON CONFLICT(user_id, track_id) DO UPDATE SET
                                   action = excluded.action, updated_at = excluded.updated_at""",
                            (user_id, action, time(), track_id))
        return result.rowcount == 1


def _with_aliases(entry: dict, other: dict) -> dict:
    names = sorted(set(entry.get("artist_alias_keys", [])) | set(other.get("artist_alias_keys", [])))
    return {**entry, "artist_alias_keys": names} if names else entry


def merge_catalog(primary: list[dict], extra: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Keep curated metadata/IDs when the same recording is already available."""
    by_id = {str(item["id"]): item for item in primary}
    by_recording = {track_key(item): str(item["id"]) for item in primary}
    aliases = {}
    for item in extra:
        key = str(item["id"])
        identity = track_key(item)
        if key not in by_id and identity in by_recording:
            aliases[key] = by_recording[identity]
        canonical = aliases.get(key, key)
        by_id[canonical] = _with_aliases(by_id.get(canonical, item), item)
        by_recording.setdefault(identity, canonical)
    return list(by_id.values()), aliases
