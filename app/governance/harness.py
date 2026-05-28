from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import get_settings


class HarnessSupervisor:
    """File-backed supervisor state for long-running research tasks."""

    def __init__(self, state_root: str | None = None):
        settings = get_settings()
        root = state_root or getattr(settings, "harness_state_root", None) or "./data/harness"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.tasks_path = self.root / "harness-tasks.json"
        self.progress_path = self.root / "harness-progress.txt"
        self.active_marker = self.root / ".harness-active"
        if not self.tasks_path.exists():
            self.tasks_path.write_text(json.dumps({
                "version": 1,
                "created": datetime.utcnow().isoformat(),
                "tasks": [],
            }, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> dict[str, Any]:
        return json.loads(self.tasks_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        temp = self.tasks_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.tasks_path)

    def _append_progress(self, line: str) -> None:
        timestamp = datetime.utcnow().isoformat()
        with self.progress_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{timestamp}] {line}\n")

    def ensure_active(self) -> None:
        self.active_marker.touch(exist_ok=True)

    def clear_active_if_idle(self) -> None:
        data = self._load()
        if not any(task.get("runtime_status") in {"running", "awaiting_approval", "retryable_failed"} for task in data.get("tasks", [])):
            if self.active_marker.exists():
                self.active_marker.unlink()

    def upsert_task(
        self,
        *,
        session_id: str,
        public_status: str,
        runtime_status: str,
        budget: dict[str, Any],
        current_batch: list[str] | None = None,
        checkpoint_seq: int = 0,
        pending_approval_id: str | None = None,
        used_total_tokens: int = 0,
        used_cost_usd: float = 0.0,
        last_error: dict[str, Any] | None = None,
        worker_id: str = "worker-1",
        state_snapshot: dict[str, Any] | None = None,
    ) -> None:
        self.ensure_active()
        data = self._load()
        tasks = data.setdefault("tasks", [])
        task = next((item for item in tasks if item.get("id") == session_id), None)
        if task is None:
            task = {
                "id": session_id,
                "depends_on": [],
                "attempts": 0,
                "max_attempts": 3,
            }
            tasks.append(task)
        task["public_status"] = public_status
        task["runtime_status"] = runtime_status
        task["budget"] = budget
        task["checkpoint"] = {
            "checkpoint_seq": checkpoint_seq,
            "thread_id": session_id,
            "current_batch": current_batch or [],
            "pending_approval_id": pending_approval_id,
            "used_total_tokens": used_total_tokens,
            "used_cost_usd": used_cost_usd,
            "state_snapshot": state_snapshot,
        }
        task["last_error"] = last_error
        task["lease"] = {
            "claimed_by": worker_id,
            "lease_expires_at": (datetime.utcnow() + timedelta(minutes=10)).isoformat(),
        }
        data["last_session"] = datetime.utcnow().isoformat()
        self._save(data)
        self._append_progress(
            f"SESSION {session_id} runtime={runtime_status} public={public_status} batch={current_batch or []}"
        )

    def get_task(self, session_id: str) -> dict[str, Any] | None:
        data = self._load()
        return next((item for item in data.get("tasks", []) if item.get("id") == session_id), None)
