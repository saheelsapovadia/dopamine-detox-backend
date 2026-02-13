"""
Audio Session Store
===================

In-memory store for audio buffers accumulated during WebSocket
streaming sessions.  Keyed by ``sessionId`` so the save endpoint
can look up recorded audio after the stream ends.

NOT persistent — sessions are lost on restart.  A TTL-based cleanup
task evicts stale sessions to prevent unbounded memory growth.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Sessions older than this are eligible for eviction.
SESSION_TTL_SECONDS = 60 * 30  # 30 minutes

# How often the cleanup loop runs.
_CLEANUP_INTERVAL_SECONDS = 60 * 5  # 5 minutes


@dataclass
class AudioSession:
    """Holds accumulated audio chunks for a single streaming session."""

    session_id: str
    chunks: list[bytes] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)

    def append(self, chunk: bytes) -> None:
        self.chunks.append(chunk)
        self.last_activity = time.monotonic()

    def get_audio(self) -> bytes:
        """Return all accumulated audio as a single bytes object."""
        return b"".join(self.chunks)

    @property
    def total_bytes(self) -> int:
        return sum(len(c) for c in self.chunks)


# ---------------------------------------------------------------------------
# Module-level store
# ---------------------------------------------------------------------------

_sessions: dict[str, AudioSession] = {}
_cleanup_task: Optional[asyncio.Task] = None


def create_session(session_id: str) -> AudioSession:
    """Create (or reset) a session with the given *session_id*."""
    session = AudioSession(session_id=session_id)
    _sessions[session_id] = session
    logger.debug("Audio session created: %s", session_id)
    return session


def get_session(session_id: str) -> Optional[AudioSession]:
    """Return the session for *session_id*, or ``None``."""
    return _sessions.get(session_id)


def remove_session(session_id: str) -> Optional[AudioSession]:
    """Remove and return the session, or ``None`` if it doesn't exist."""
    session = _sessions.pop(session_id, None)
    if session:
        logger.debug(
            "Audio session removed: %s (%d bytes)",
            session_id,
            session.total_bytes,
        )
    return session


# ---------------------------------------------------------------------------
# Background cleanup
# ---------------------------------------------------------------------------

async def _cleanup_loop() -> None:
    """Periodically evict stale sessions."""
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
        now = time.monotonic()
        stale = [
            sid
            for sid, s in _sessions.items()
            if (now - s.last_activity) > SESSION_TTL_SECONDS
        ]
        for sid in stale:
            removed = _sessions.pop(sid, None)
            if removed:
                logger.info(
                    "Evicted stale audio session %s (%d bytes)",
                    sid,
                    removed.total_bytes,
                )


def start_cleanup_task() -> None:
    """Start the background cleanup task (safe to call multiple times)."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())


def stop_cleanup_task() -> None:
    """Cancel the background cleanup task."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
