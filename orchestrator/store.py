"""Locked, crash-resistant JSON state persistence using only the stdlib."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .errors import OrchestrationError

try:
    import fcntl
except ImportError as exc:  # pragma: no cover - project targets Unix CI today
    raise RuntimeError("orchestrator requires POSIX advisory file locks") from exc


class StateStore:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir.resolve()
        self.path = self.state_dir / "state.json"
        self.lock_path = self.state_dir / "state.lock"

    @contextmanager
    def _locked(self, exclusive: bool) -> Iterator[None]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> dict:
        with self._locked(False):
            return self._read_unlocked()

    def initialize(self, initial: dict) -> dict:
        with self._locked(True):
            if self.path.exists():
                raise OrchestrationError(f"state already exists: {self.path}")
            self._write_unlocked(initial)
            return initial

    def update(self, mutation: Callable[[dict], object]) -> tuple[dict, object]:
        with self._locked(True):
            state = self._read_unlocked()
            result = mutation(state)
            self._write_unlocked(state)
            return state, result

    def _read_unlocked(self) -> dict:
        if not self.path.exists():
            raise OrchestrationError(f"state is not initialized: {self.path}")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OrchestrationError(f"cannot read valid state: {exc}") from exc
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise OrchestrationError("unsupported or missing state schema_version")
        return value

    def _write_unlocked(self, state: dict) -> None:
        payload = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode()
        fd, tmp_name = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=self.state_dir)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp_name, self.path)
            directory_fd = os.open(self.state_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass

