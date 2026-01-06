# app/agent_client.py
import json
import os
import websockets
import logging
from websockets.legacy.client import WebSocketClientProtocol
from .settings import DG_API_KEY, build_deepgram_settings
from .agent_functions import FUNCTION_DEFS

log = logging.getLogger("agent_client")

# Prefer header auth when available
async def connect_agent() -> WebSocketClientProtocol:
    url = os.getenv("DG_AGENT_URL", "wss://agent.deepgram.com/v1/agent/converse")
    headers = [("Authorization", f"Token {DG_API_KEY}")]
    try:
        ws = await websockets.connect(url, extra_headers=headers, max_size=2**24)
        log.info("✅ Connected to Deepgram Agent (auth header)")
        return ws
    except Exception as e:
        log.error(f"❌ Deepgram connection error: {e}")
        raise
    
async def send_agent_settings(ws: WebSocketClientProtocol):
    s = build_deepgram_settings()
    # inject tools under think.functions
    s["agent"]["think"]["functions"] = FUNCTION_DEFS
    await ws.send(json.dumps(s))
    log.info("➡️  Sent Agent Settings")
