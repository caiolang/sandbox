from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionState:
    verified_patient_id: str | None = None
    identity_fields: dict[str, str] = field(default_factory=dict)
    last_listed_appointment_ids: list[str] = field(default_factory=list)


_current_thread_id: ContextVar[str | None] = ContextVar("current_thread_id", default=None)
_sessions: dict[str, SessionState] = {}


@contextmanager
def bind_thread(thread_id: str):
    token = _current_thread_id.set(thread_id)
    try:
        yield
    finally:
        _current_thread_id.reset(token)


def get_current_thread_id() -> str | None:
    return _current_thread_id.get()


def get_session(thread_id: str) -> SessionState:
    if thread_id not in _sessions:
        _sessions[thread_id] = SessionState()
    return _sessions[thread_id]


def get_current_session() -> SessionState | None:
    thread_id = get_current_thread_id()
    if not thread_id:
        return None
    return get_session(thread_id)


def reset_all_sessions() -> None:
    _sessions.clear()


def export_session_state(thread_id: str) -> dict[str, Any]:
    session = get_session(thread_id)
    return {
        "verified_patient_id": session.verified_patient_id,
        "identity_fields": dict(session.identity_fields),
        "last_listed_appointment_ids": list(session.last_listed_appointment_ids),
    }
