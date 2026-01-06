# app/session.py
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class CallSession:
    """Holds *per-call* state so two calls never clobber each other."""
    call_sid: str
    stream_sid: Optional[str] = None

    # Per-call order/session fields
    order: Dict[str, Any] = field(default_factory=dict)         # free-form scratch (optional)
    order_number: Optional[str] = None                          # set after checkout (not finalized)
    pending_item: Optional[Dict[str, Any]] = None               # (not used in this build)

    phone: Optional[str] = None
    phone_confirmed: bool = False
    received_sms_sent: bool = False

    # Optional: Deepgram request id for debugging/trace
    dg_request_id: Optional[str] = None

class SessionStore:
    def __init__(self) -> None:
        self._by_call: Dict[str, CallSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, call_sid: str) -> CallSession:
        async with self._lock:
            s = self._by_call.get(call_sid)
            if not s:
                s = CallSession(call_sid=call_sid)
                self._by_call[call_sid] = s
            return s

    async def get(self, call_sid: str) -> Optional[CallSession]:
        async with self._lock:
            return self._by_call.get(call_sid)

    async def set_stream_sid(self, call_sid: str, stream_sid: str) -> None:
        async with self._lock:
            s = self._by_call.get(call_sid)
            if s:
                s.stream_sid = stream_sid

    async def reset_for_new_stream(self, call_sid: str) -> None:
        """Ensure the session exists and clear transient audio/stream-related fields if needed."""
        async with self._lock:
            s = self._by_call.get(call_sid)
            if not s:
                s = CallSession(call_sid=call_sid)
                self._by_call[call_sid] = s
            # keep persistent order/phone fields; nothing transient to clear here

    async def remove(self, call_sid: str) -> None:
        async with self._lock:
            self._by_call.pop(call_sid, None)

sessions = SessionStore()
