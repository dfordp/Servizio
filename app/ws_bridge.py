# app/ws_bridge.py
import os
import json
import base64
import logging
import asyncio
import contextlib
import time
import inspect
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .session import sessions
from .events import publish
from .audio import (
    ulaw8k_to_lin16_48k,
    lin16_24k_to_ulaw8k,
    chunk_bytes,
    TWILIO_FRAME_BYTES,
)
from .agent_client import connect_agent, send_agent_settings
from .agent_functions import FUNCTION_MAP
from .orders_store import add_order
from .send_sms import send_received_sms
from . import business_logic as bl

log = logging.getLogger("ws_bridge")
router = APIRouter()

# ========== ENV / TOGGLES ==========
DG_AUDIO_BRIDGE = os.getenv("DG_AUDIO_BRIDGE", "true").lower() not in ("0", "false", "no")
LOG_AGENT_EVENTS = os.getenv("LOG_AGENT_EVENTS", "1").lower() not in ("0", "false", "no")
LOG_AGENT_AUDIO  = os.getenv("LOG_AGENT_AUDIO",  "0").lower() not in ("0", "false", "no")
LOG_TOOL_MAXLEN  = int(os.getenv("LOG_TOOL_MAXLEN", "800").split()[0])

CLOSE_ON_PHRASE   = os.getenv("CLOSE_ON_PHRASE", "1").lower() not in ("0", "false", "no")
CLOSING_PHRASE_ENV = os.getenv("CLOSING_PHRASE", "Goodbye!").strip()
HANGUP_DELAY_MS = int(os.getenv("HANGUP_DELAY_MS", "2000").split()[0])

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")

# ========== PHRASE NORMALIZATION ==========
def _norm_text(s: str) -> str:
    if not s:
        return ""
    rep = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "\u00A0": " "}
    for a, b in rep.items():
        s = s.replace(a, b)
    return " ".join(s.lower().strip().split())

EXACT_CLOSE_NORM = _norm_text(CLOSING_PHRASE_ENV)

# ========== DG message keys/types ==========
DG_KEY_TYPE                 = "type"
DG_TYPE_WELCOME             = "Welcome"
DG_TYPE_SETTINGS_APPLIED    = "SettingsApplied"
DG_TYPE_ERROR               = "Error"
DG_TYPE_CONV_TEXT           = "ConversationText"
DG_TYPE_HISTORY             = "History"
DG_TYPE_FUNCTION_CALL_REQ   = "FunctionCallRequest"
DG_TYPE_FUNCTION_CALL_RESP  = "FunctionCallResponse"
DG_TYPE_AGENT_AUDIO_DONE    = "AgentAudioDone"
DG_TYPE_USER_STARTED        = "UserStartedSpeaking"

# ========== Twilio helpers ==========
def _twilio_media_payload(ulaw8k_bytes: bytes, stream_sid: str) -> str:
    return json.dumps({
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": base64.b64encode(ulaw8k_bytes).decode("ascii")}
    })

_twilio_client = None
def _get_twilio_client():
    global _twilio_client
    if _twilio_client is None and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        from twilio.rest import Client
        _twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _twilio_client

async def _hangup_call(call_sid: str):
    try:
        client = _get_twilio_client()
        if not client:
            log.warning(f"[{call_sid}] Twilio client not configured; cannot hang up.")
            return
        client.calls(call_sid).update(status="completed")
        log.info(f"[{call_sid}] ☎️  Hangup requested (status=completed).")
    except Exception as e:
        log.warning(f"[{call_sid}] hangup failed: {e}")

# Debounce: avoid duplicate finalize/hangup
_HUNG_UP: set[str] = set()
_HANGUP_INFLIGHT: set[str] = set()

# ========== Tool execution ==========
async def execute_agent_function(tool_name: str, args: dict, *, call_sid: str):
    fn = FUNCTION_MAP.get(tool_name)
    if not fn:
        return {"ok": False, "error": f"Unknown tool: {tool_name}"}

    if isinstance(args, str):
        try:
            args = json.loads(args) if args else {}
        except Exception:
            args = {}
    args = dict(args or {})
    args.setdefault("call_sid", call_sid)

    try:
        sig = inspect.signature(fn)
        accepted = {k: v for k, v in args.items() if k in sig.parameters}
    except Exception:
        accepted = args

    async def _run():
        if inspect.iscoroutinefunction(fn):
            return await fn(**accepted)
        return fn(**accepted)  # type: ignore

    try:
        return await asyncio.wait_for(_run(), timeout=8.0)
    except asyncio.TimeoutError:
        log.exception(f"[{call_sid}] tool {tool_name} timed out")
        return {"ok": False, "error": "tool_timeout"}
    except Exception as e:
        log.exception(f"[{call_sid}] tool {tool_name} failed: {e}")
        return {"ok": False, "error": str(e)}

# ========== Finalize & notify ==========
async def _finalize_and_notify(call_sid: str):
    s = await sessions.get(call_sid)
    if not s or s.received_sms_sent or not s.order_number or not s.phone_confirmed or not s.phone:
        return

    fin = await bl.finalize_order(s.order_number, call_sid=call_sid)
    if not (isinstance(fin, dict) and fin.get("ok")):
        log.error(f"[{call_sid}] finalize failed: {fin}")
        return

    order = {
        "order_number": fin["order_number"],
        "phone": fin.get("phone") or s.phone,
        "items": fin.get("items") or [],
        "total": 0.0,
        "status": fin.get("status", "received"),
        "created_at": fin.get("created_at", int(time.time())),
    }

    add_order(order)
    await publish("orders", {"type": "order_created", "order_number": order["order_number"], "status": order["status"]})

    try:
        send_received_sms(order["order_number"], order["phone"])
        s.received_sms_sent = True
        log.info(f"[{call_sid}] ✅ SMS(sent) and order persisted ({order['order_number']})")
    except Exception as e:
        log.warning(f"[{call_sid}] SMS failed: {e}")

async def _finalize_and_hangup(call_sid: str):
    if call_sid in _HUNG_UP or call_sid in _HANGUP_INFLIGHT:
        return
    _HANGUP_INFLIGHT.add(call_sid)
    try:
        await _finalize_and_notify(call_sid)
        if HANGUP_DELAY_MS > 0:
            await asyncio.sleep(HANGUP_DELAY_MS / 1000.0)
        await _hangup_call(call_sid)
        _HUNG_UP.add(call_sid)
    finally:
        _HANGUP_INFLIGHT.discard(call_sid)

# ========== Main Twilio endpoint ==========
@router.websocket("/twilio")
async def twilio_ws(ws: WebSocket):
    await ws.accept()
    call_sid: str = "unknown"
    stream_sid: Optional[str] = None

    agent = None
    agent_reader_task = None
    rx_state = None

    # meter
    ts_last = time.time()
    frames_last_sec = 0

    async def media_meter():
        nonlocal ts_last, frames_last_sec
        while True:
            await asyncio.sleep(1.0)
            now = time.time()
            if now - ts_last >= 1.0:
                log.info(f"[{call_sid}] Twilio media frames last 1s: {frames_last_sec}")
                ts_last = now
                frames_last_sec = 0

    meter_task = asyncio.create_task(media_meter())

    # --- inner agent reader (graceful cancel/close) ---
    async def _agent_reader():
        nonlocal stream_sid
        tx_state = None
        assistant_buf: list[str] = []

        # import here to avoid hard dep at module import time
        from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

        try:
            async for message in agent:
                # Binary audio from Agent (linear16@24k)
                if isinstance(message, (bytes, bytearray)):
                    if not DG_AUDIO_BRIDGE or not stream_sid:
                        continue
                    if LOG_AGENT_AUDIO:
                        log.info(f"[{call_sid}] (agent audio {len(message)} bytes)")
                    ulaw8k, tx_state = lin16_24k_to_ulaw8k(message, tx_state)
                    for chunk in chunk_bytes(ulaw8k, TWILIO_FRAME_BYTES):
                        if not chunk:
                            continue
                        try:
                            await ws.send_text(_twilio_media_payload(chunk, stream_sid))
                        except Exception:
                            return
                    continue

                # JSON events
                try:
                    evt = json.loads(message)
                except Exception:
                    continue

                etype = evt.get(DG_KEY_TYPE)

                if etype in (DG_TYPE_WELCOME, DG_TYPE_SETTINGS_APPLIED, DG_TYPE_ERROR, DG_TYPE_USER_STARTED):
                    if LOG_AGENT_EVENTS:
                        log.info(f"[{call_sid}] Agent: {json.dumps(evt)}")
                    continue

                if etype in (DG_TYPE_CONV_TEXT, DG_TYPE_HISTORY):
                    if LOG_AGENT_EVENTS:
                        log.info(f"[{call_sid}] Agent: {json.dumps(evt)}")
                    if (evt.get("role") or "").lower() == "assistant":
                        assistant_buf.append(evt.get("content") or "")
                    continue

                if etype == DG_TYPE_AGENT_AUDIO_DONE:
                    if LOG_AGENT_EVENTS:
                        log.info(f"[{call_sid}] Agent: {json.dumps(evt)}")
                    if CLOSE_ON_PHRASE and assistant_buf:
                        full_text_norm = _norm_text(" ".join(assistant_buf))
                        if EXACT_CLOSE_NORM in full_text_norm:
                            log.info(f"[{call_sid}] 🔔 Closing sentence found in full utterance. Finalizing + hangup…")
                            asyncio.create_task(_finalize_and_hangup(call_sid))
                    assistant_buf.clear()
                    continue

                if etype == DG_TYPE_FUNCTION_CALL_REQ:
                    for fc in evt.get("functions", []):
                        if fc.get("client_side") is False:
                            continue
                        fn_id   = fc.get("id")
                        fn_name = fc.get("name")
                        raw_args = fc.get("arguments") or "{}"
                        if LOG_AGENT_EVENTS:
                            a = raw_args if isinstance(raw_args, str) else json.dumps(raw_args)
                            log.info(f"[{call_sid}] 🔧 function.call {fn_name}({a[:LOG_TOOL_MAXLEN]})")

                        result = await execute_agent_function(fn_name, raw_args, call_sid=call_sid)
                        resp = {
                            "type": DG_TYPE_FUNCTION_CALL_RESP,
                            "id": fn_id,
                            "name": fn_name,
                            "content": json.dumps(result) if not isinstance(result, str) else result,
                        }
                        await agent.send(json.dumps(resp))
                        if LOG_AGENT_EVENTS:
                            log.info(f"[{call_sid}] 🔧 function.result {fn_name}: {resp['content'][:LOG_TOOL_MAXLEN]}")
                    continue

                if LOG_AGENT_EVENTS:
                    log.info(f"[{call_sid}] Agent: {json.dumps(evt)}")

        except asyncio.CancelledError:
            # Graceful: task was cancelled during shutdown/hangup
            log.debug(f"[{call_sid}] agent reader cancelled")
            return
        except (ConnectionClosedOK, ConnectionClosedError):
            # Agent ws closed first—normal during hangup
            log.debug(f"[{call_sid}] agent websocket closed")
            return

    try:
        while True:
            try:
                raw = await ws.receive_text()
                msg = json.loads(raw)
            except WebSocketDisconnect:
                raise
            except Exception:
                continue

            ev = msg.get("event")

            if ev == "start":
                stream_sid = msg["start"]["streamSid"]
                params = msg["start"].get("customParameters", {}) or {}
                call_sid = params.get("call_sid", "unknown")

                await sessions.set_stream_sid(call_sid, stream_sid)

                s = await sessions.get_or_create(call_sid)
                s.order = {}
                s.order_number = None
                s.pending_item = None
                s.phone = None
                s.phone_confirmed = False
                s.received_sms_sent = False
                s.dg_request_id = None
                _HUNG_UP.discard(call_sid)
                _HANGUP_INFLIGHT.discard(call_sid)

                try:
                    agent = await connect_agent()
                except Exception as e:
                    log.error(f"[{call_sid}] Failed to connect to Deepgram Agent: {e}")
                    await ws.send_text(json.dumps({"event": "error", "message": f"Agent connection failed: {e}"}))
                    raise
                try:
                    await send_agent_settings(agent)
                except Exception as e:
                    log.error(f"[{call_sid}] Failed to send agent settings: {e}")
                    raise
                agent_reader_task = asyncio.create_task(_agent_reader())

                log.info(f"[{call_sid}][{stream_sid}] Twilio start; Agent connected & configured")

            elif ev == "media":
                frames_last_sec += 1
                if not DG_AUDIO_BRIDGE or not agent:
                    continue
                try:
                    payload_b64 = msg["media"]["payload"]
                    ulaw8k = base64.b64decode(payload_b64)
                    lin48k, rx_state = ulaw8k_to_lin16_48k(ulaw8k, rx_state)
                except Exception:
                    continue
                try:
                    await agent.send(lin48k)
                except Exception:
                    break

            elif ev == "stop":
                log.info(f"[{call_sid}][{stream_sid}] Twilio stream stopped")
                await _finalize_and_hangup(call_sid)  # idempotent
                break

            else:
                pass

    except WebSocketDisconnect:
        log.info(f"[{call_sid}][{stream_sid}] websocket disconnect")
    except Exception as e:
        log.exception(f"[{call_sid}][{stream_sid}] error: {e}")
    finally:
        # stop meter cleanly
        meter_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await meter_task

        # close agent + background reader (graceful: suppress CancelledError)
        if agent_reader_task:
            agent_reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await agent_reader_task
        with contextlib.suppress(Exception):
            if agent:
                await agent.close()

        # session cleanup + event
        with contextlib.suppress(Exception):
            if call_sid and call_sid != "unknown":
                await publish("orders", {"type": "CallEnded", "call_sid": call_sid})
                await sessions.remove(call_sid)
        _HUNG_UP.discard(call_sid)
        _HANGUP_INFLIGHT.discard(call_sid)

# Back-compat shim
def register_ws_routes(app):
    app.include_router(router)
