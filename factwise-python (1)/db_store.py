"""
Minimal file-based persistence layer.

The project statement asks for local file storage, with the internal
storage format left up to the developer, and the caller should never be
exposed to it. This module is the *only* place that touches disk; every
implementation module (user_impl / team_impl / project_board_impl) goes
through the small collection-style API below.

Design choices (see README for the full rationale):
  * A single JSON file per logical collection (users, teams, ...) is kept
    under the ``db`` directory. JSON keeps the files human-inspectable
    while debugging, and avoids pulling in a database engine for what is
    an assignment-scoped, single-process app.
  * Each collection is a dict keyed by id, so id-based lookups don't need
    a linear scan.
  * Writes are atomic (write to a temp file, then os.replace) and guarded
    by an in-process lock so concurrent Django requests (threaded dev
    server) don't corrupt a file mid-write.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")

_locks = {}
_locks_guard = threading.Lock()


def _lock_for(name: str) -> threading.Lock:
    with _locks_guard:
        if name not in _locks:
            _locks[name] = threading.Lock()
        return _locks[name]


def _path_for(name: str) -> str:
    os.makedirs(DB_DIR, exist_ok=True)
    return os.path.join(DB_DIR, f"{name}.json")


def new_id() -> str:
    """Return a compact, unique identifier for a new entity."""
    return uuid.uuid4().hex


def now_iso() -> str:
    """Return the current UTC time in ISO-8601, used for all timestamps."""
    return datetime.now(timezone.utc).isoformat()


class Collection:
    """
    A dict-of-records collection persisted as one JSON file.

    Every record is stored as {id: {...fields..., "id": id}}. Callers get
    back plain dicts (copies) so mutating the returned value never
    silently corrupts the in-memory/on-disk state.
    """

    def __init__(self, name: str):
        self.name = name
        self.lock = _lock_for(name)

    def _read_all_unlocked(self) -> dict:
        path = _path_for(self.name)
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)

    def _write_all_unlocked(self, data: dict) -> None:
        path = _path_for(self.name)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp_path, path)

    def all(self) -> dict:
        with self.lock:
            return dict(self._read_all_unlocked())

    def get(self, record_id: str):
        with self.lock:
            data = self._read_all_unlocked()
            record = data.get(record_id)
            return dict(record) if record is not None else None

    def insert(self, record: dict) -> dict:
        with self.lock:
            data = self._read_all_unlocked()
            data[record["id"]] = record
            self._write_all_unlocked(data)
            return dict(record)

    def update(self, record_id: str, record: dict) -> dict:
        with self.lock:
            data = self._read_all_unlocked()
            if record_id not in data:
                raise KeyError(record_id)
            data[record_id] = record
            self._write_all_unlocked(data)
            return dict(record)

    def find_one(self, predicate):
        with self.lock:
            data = self._read_all_unlocked()
            for record in data.values():
                if predicate(record):
                    return dict(record)
            return None

    def values(self):
        return list(self.all().values())
