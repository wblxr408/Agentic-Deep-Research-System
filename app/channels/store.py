"""Owner-scoped, bounded maintenance records with cross-process serialization."""
from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from app.core.atomic_io import atomic_write_json
from app.channels.models import ChannelError

_locks: dict[str, threading.RLock] = {}
_guard = threading.Lock()


class ChannelStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("CHANNELS_STATE_ROOT", "./data/channels"))

    def _path(self, owner: str) -> Path:
        return self.root / (str(uuid.UUID(owner)) + ".json")

    @contextmanager
    def _locked(self, owner):
        path = self._path(owner)
        path.parent.mkdir(parents=True, exist_ok=True)
        key = str(path.absolute())
        with _guard:
            lock = _locks.setdefault(key, threading.RLock())
        with lock, path.with_suffix(".lock").open("a+b") as handle:
            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield path
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def _read(self, path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or not isinstance(value.get("configs"), dict) or not isinstance(value.get("history"), list):
                raise ValueError
            return value
        except FileNotFoundError:
            return {"configs": {}, "history": []}
        except (OSError, ValueError):
            raise ChannelError("state_unavailable") from None

    def read(self, owner: str | None) -> dict:
        if owner is None:
            return {"configs": {}, "history": []}
        with self._locked(owner) as path:
            return self._read(path)

    def configure(self, owner: str, channel: str, config: dict):
        with self._locked(owner) as path:
            state = self._read(path)
            state["configs"][channel] = config
            atomic_write_json(path, state)

    def record(self, owner: str | None, attempts: list[dict], timestamp: str):
        if owner is None:
            return
        with self._locked(owner) as path:
            state = self._read(path)
            state["history"] = [*state["history"], *({**a, "timestamp": timestamp} for a in attempts)][-100:]
            atomic_write_json(path, state)
