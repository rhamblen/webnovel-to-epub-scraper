"""In-memory build-progress registry.

Single-process, matching the current in-process build tasks (fire-and-forget asyncio).
The Novel page polls `/volumes/{id}/progress`; this holds the live state. Superseded when
the full persistent job queue lands (Phase 5).
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_state: dict[int, dict] = {}


def start(volume_id: int, total: int = 0, done: int = 0, message: str = "Starting…") -> None:
    with _lock:
        _state[volume_id] = {
            "active": True, "phase": "downloading",
            "done": done, "total": max(total, 0), "message": message,
        }


def update(volume_id: int, **fields) -> None:
    with _lock:
        st = _state.get(volume_id)
        if st is not None:
            st.update(fields)


def finish(volume_id: int, phase: str, message: str) -> None:
    with _lock:
        st = _state.get(volume_id, {})
        st.update({"active": False, "phase": phase, "message": message})
        _state[volume_id] = st


def get(volume_id: int) -> dict:
    with _lock:
        return dict(_state.get(volume_id, {}))
