# app/http_routes.py
import os
import json as _json
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, JSONResponse, HTMLResponse, StreamingResponse

from .orders_store import (
    list_recent_orders,
    list_in_progress_orders,
    get_order_phone,
    set_order_status,
    add_order,
    get_order,  # full order lookup
)
from .events import subscribe, unsubscribe, publish
from .send_sms import send_ready_sms

# Optional call log appends (if file/module exists)
try:
    from .call_logger import LOGS_DIR  # type: ignore
except Exception:
    LOGS_DIR = None  # safe fallback

http_router = APIRouter()

# -------------------- Helpers --------------------

def _host_and_scheme() -> tuple[str, str]:
    host = os.getenv("VOICE_HOST", "localhost:8000")
    # Allow explicit override by WS_SCHEME (wss / ws)
    ws_scheme = os.getenv("WS_SCHEME")
    if ws_scheme:
        scheme = ws_scheme.strip().lower()
    else:
        scheme = "wss" if not host.startswith("localhost") else "ws"
    return host, scheme

def _autorefresh_meta(refresh_seconds: Optional[int]) -> str:
    if not refresh_seconds or refresh_seconds <= 0:
        return ""
    return f'<meta http-equiv="refresh" content="{int(refresh_seconds)}" />'

# -------------------- Landing page --------------------

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>🧋 Servizio - Voice Ordering System</title>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
           min-height:100vh; display:grid; place-items:center;
           background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .card { background: rgba(255,255,255,0.95); border-radius: 20px; padding: 32px; max-width: 900px; width: 94%;
            box-shadow: 0 18px 60px rgba(0,0,0,0.25); }
    h1 { margin: 0 0 8px; color:#2d3748; }
    p  { margin: 0 0 20px; color:#4a5568; }
    .grid { display:grid; gap:14px; grid-template-columns: repeat(auto-fit,minmax(240px,1fr)); margin-top: 12px; }
    .tile { padding:18px; border: 2px solid #e2e8f0; background:#fff; border-radius: 12px; text-decoration:none; display:block; }
    .tile:hover { border-color:#667eea; box-shadow: 0 4px 14px rgba(102,126,234,0.2); transform: translateY(-1px); }
    .t1 { font-weight:700; color:#2d3748; margin:0 0 6px; }
    .t2 { color:#718096; margin:0 0 10px; }
    code { background:#f7fafc; padding: 4px 6px; border-radius:6px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🧋 Servizio</h1>
    <p>Voice Ordering System</p>
    <div class="grid">
      <a class="tile" href="/orders">
        <div class="t1">📺 Orders TV</div>
        <div class="t2">Big-screen display (auto-updates)</div>
        <code>/orders</code>
      </a>
      <a class="tile" href="/barista">
        <div class="t1">👨‍🍳 Barista Console</div>
        <div class="t2">Mark orders ready (sends SMS)</div>
        <code>/barista</code>
      </a>
      <a class="tile" href="/orders.json">
        <div class="t1">📋 Orders JSON</div>
        <div class="t2">Recent orders feed</div>
        <code>/orders.json</code>
      </a>
      <div class="tile">
        <div class="t1">☎️ Twilio Voice Webhook</div>
        <div class="t2">TwiML endpoint (Twilio calls this)</div>
        <code>/voice</code>
      </div>
    </div>
  </div>
</body>
</html>
"""

@http_router.get("/")
def index():
    return HTMLResponse(INDEX_HTML)

# -------------------- Twilio Voice Webhook (TwiML) --------------------

@http_router.post("/voice")
async def voice_twiml(request: Request):
    host, scheme = _host_and_scheme()

    # (Optional) small debug log for your POST body
    try:
        form = await request.form()
        body = "&".join([f"{k}={v}" for k, v in form.items()])
        log_http = os.getenv("LOG_HTTP", "1") not in ("0", "false", "no")
        if log_http:
            print(f"INFO [http] HTTP POST /voice body={body}")
    except Exception:
        form = {}

    call_sid = form.get("CallSid", "unknown")
    from_num = form.get("From", "")
    to_num   = form.get("To", "")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Connecting you to the Deepgram Boba Rista.</Say>
  <Connect>
    <Stream url="{scheme}://{host}/twilio">
      <Parameter name="call_sid" value="{call_sid}"/>
      <Parameter name="from" value="{from_num}"/>
      <Parameter name="to" value="{to_num}"/>
    </Stream>
  </Connect>
</Response>"""

    # Some HTTP servers fuss when streaming a long-lived response; return plain XML immediately
    return Response(content=twiml, media_type="text/xml")

# -------------------- JSON APIs --------------------

@http_router.get("/orders.json")
def orders_json(limit: int = 50):
    return JSONResponse(list_recent_orders(limit=limit))

@http_router.get("/orders/in_progress.json")
def orders_in_progress_json(limit: int = 100):
    return JSONResponse(list_in_progress_orders(limit=limit))

# Full order (flavor/toppings/etc.)
@http_router.get("/api/orders/{order_no}")
def api_get_order(order_no: str):
    o = get_order(order_no)
    if not o:
        raise HTTPException(404, "Order not found")
    return o

@http_router.get("/api/orders/phone/{order_no}")
def api_get_phone(order_no: str):
    phone = get_order_phone(order_no)
    return {"order_number": order_no, "phone": phone}

@http_router.post("/api/orders/{order_no}/done")
async def api_mark_done(order_no: str):
    ok = set_order_status(order_no, "ready")
    if not ok:
        raise HTTPException(404, "Order not found")

    await publish("orders", {"type": "order_status_changed", "order_number": order_no, "status": "ready"})

    phone = get_order_phone(order_no)
    if phone:
        try:
            send_ready_sms(order_no, phone)
            # Append to call log if available
            if LOGS_DIR:
                try:
                    sanitized = phone.replace("+", "").replace("-", "").replace(" ", "")
                    # find latest matching file
                    matches = list(LOGS_DIR.glob(f"{sanitized}_*.log"))
                    if matches:
                        latest = max(matches, key=lambda p: p.stat().st_mtime)
                        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        with open(latest, "a", encoding="utf-8") as f:
                            f.write(f"\n{'='*80}\n")
                            f.write(f"[{ts}] [ORDER_COMPLETED_BY_BARISTA]\n")
                            f.write(f"Order Number: {order_no}\n")
                            f.write(f"Status: ready for pickup\n")
                            f.write(f"[{ts}] [READY_SMS_SENT]\n")
                            f.write(f"Notification sent to: {phone}\n")
                            f.write(f"{'='*80}\n\n")
                        print(f"📝 Logged order completion to: {latest.name}")
                except Exception as e:
                    print(f"⚠️ Could not append to call log: {e}")
        except Exception as e:
            print(f"❌ SMS send failed for {order_no}: {e}")

    return {"ok": True}

# --- DEV seed (optional) ---
@http_router.post("/api/seed")
async def api_seed(n: int = Query(2, ge=1, le=10)):
    created = []
    # Create simple fake orders without touching agent/session/business_logic
    for i in range(n):
        order = {
            "order_number": f"T{datetime.utcnow().strftime('%H%M%S')}{i}",
            "phone": "+16146205644",
            "items": [
                {"flavor": "taro milk tea", "toppings": ["boba"], "sweetness": "50%", "ice": "regular ice", "addons": ["matcha stencil on top"]}
            ],
            "total": 0.0,
            "status": "received",
            "created_at": int(datetime.utcnow().timestamp()),
        }
        add_order(order)
        await publish("orders", {"type": "order_created", "order_number": order["order_number"], "status": "received"})
        created.append(order["order_number"])
    return {"ok": True, "orders": created}

# -------------------- Server-Sent Events (orders bus) --------------------

@http_router.get("/orders/events")
async def orders_events():
    q = await subscribe("orders")

    async def event_gen():
        try:
            while True:
                try:
                    # Wait up to 25s for a real event
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {_json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat keeps proxies/browsers from dropping idle SSE
                    yield 'data: {"type":"ping"}\n\n'
        except asyncio.CancelledError:
            pass
        finally:
            await unsubscribe("orders", q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")

# -------------------- UI Pages (Orders TV + Barista) --------------------

def _orders_tv_html(refresh: int) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Boba Orders - Now Preparing</title>
  {_autorefresh_meta(refresh)}
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; background: #111; color:#fff; }}
    header {{ padding: 16px 24px; background: #222; border-bottom: 1px solid #333; display:flex; align-items:center; gap:10px; }}
    h1 {{ margin: 0; font-size: 22px; }}
    .muted {{ color:#aaa; font-size:12px; margin-left:auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; padding: 24px; }}
    .card {{ background: #1b1b1b; border: 1px solid #333; border-radius: 16px; padding: 24px; text-align: center; box-shadow: 0 1px 8px rgba(0,0,0,0.25); }}
    .ord {{ font-size: 64px; letter-spacing: 2px; font-weight: 900; }}
  </style>
</head>
<body>
  <header>
    <h1>🧋 Now Preparing</h1>
    <div class="muted">Auto refresh: {refresh or 15}s • Live via SSE</div>
  </header>
  <main>
    <div id="grid" class="grid"></div>
  </main>
  <script>
    const grid = document.getElementById('grid');

    function render(list){{
      grid.innerHTML = '';
      if(!list || list.length === 0){{
        const div = document.createElement('div');
        div.style.gridColumn = '1 / -1';
        div.style.color = '#aaa';
        div.style.padding = '80px 16px';
        div.style.textAlign = 'center';
        div.textContent = ' ';
        grid.appendChild(div);
        return;
      }}
      for(const o of list){{
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = '<div class="ord">' + (o.order_number || '----') + '</div>' +
                         '<div style="margin-top:6px;color:#aaa;">' + (o.status || '') + '</div>';
        grid.appendChild(card);
      }}
    }}

    async function load() {{
      const res = await fetch('/orders/in_progress.json', {{ cache: 'no-store' }});
      render(await res.json());
    }}

    function startSSE() {{
      const es = new EventSource('/orders/events');
      es.onopen = () => {{
        // Pull latest state immediately on (re)connect
        load();
      }};
      es.onmessage = (ev) => {{
        try {{
          const msg = JSON.parse(ev.data);
          if (msg.type === 'order_created' ||
              msg.type === 'order_status_changed' ||
              msg.type === 'CallEnded') {{
            load();
          }}
          // ignore 'ping'
        }} catch(e) {{}}
      }};
      es.onerror = () => {{
        // Browser will auto-reconnect; do a one-off reload for safety
        load();
      }};
    }}

    load(); startSSE();
    const REFRESH = {refresh or 15};
    if (REFRESH > 0) setInterval(load, REFRESH * 1000);
  </script>
</body>
</html>"""

def _barista_html(refresh: int) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Barista Console</title>
  {_autorefresh_meta(refresh)}
  <style>
    :root{{ color-scheme: light dark; }}
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin:24px; }}
    h1 {{ margin: 0 0 8px; }}
    .muted {{ color:#777; font-size: 12px; margin: 0 0 14px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: 10px; text-align: left; vertical-align: top; }}
    tr:hover {{ background: rgba(0,0,0,0.04); }}
    button {{ padding: 6px 12px; border-radius: 8px; border: 1px solid #999; cursor: pointer; }}
    .detail-item {{ margin: 0 0 6px; line-height: 1.25; }}
    .nowrap {{ white-space: nowrap; }}
  </style>
</head>
<body>
  <h1>🧋 Barista Console</h1>
  <p class="muted">Mark orders as done to text the customer that it's ready for pickup. Auto refresh: {refresh or 15}s • Live via SSE</p>

  <table id="tbl">
    <thead>
      <tr>
        <th class="nowrap">Order #</th>
        <th>Phone</th>
        <th>Details</th>
        <th>Status</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <script>
    const tbody = document.querySelector('#tbl tbody');

    function fmtDetails(order) {{
      if (!order || !Array.isArray(order.items) || order.items.length === 0) return '—';
      return order.items.map((it) => {{
        const flavor = it.flavor || 'unknown';
               const toppings = (it.toppings && it.toppings.length) ? it.toppings.join(', ') : 'no toppings';
        const sweet = it.sweetness || '50%';
        const ice = it.ice || 'regular ice';
        return `<div class="detail-item"><strong>${{flavor}}</strong><br/><small>${{toppings}} • ${{sweet}}, ${{ice}}</small></div>`;
      }}).join('');
    }}

    async function load() {{
      const res = await fetch('/orders/in_progress.json', {{ cache: 'no-store' }});
      const list = await res.json();
      tbody.innerHTML = '';
      for (const o of list) {{
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="nowrap"><strong>${{o.order_number}}</strong></td>
          <td data-phone>—</td>
          <td data-details style="color:#777;">Loading…</td>
          <td>${{o.status || ''}}</td>
          <td><button data-done="${{o.order_number}}">Done</button></td>
        `;
        tbody.appendChild(tr);

        // Fill phone
        fetch('/api/orders/phone/' + o.order_number, {{ cache: 'no-store' }})
          .then(r => r.json())
          .then(d => {{ tr.querySelector('[data-phone]').textContent = d.phone || '—'; }})
          .catch(() => {{ tr.querySelector('[data-phone]').textContent = '—'; }});

        // Fill details
        fetch('/api/orders/' + o.order_number, {{ cache: 'no-store' }})
          .then(r => r.ok ? r.json() : null)
          .then(order => {{
            tr.querySelector('[data-details]').innerHTML = order ? fmtDetails(order) : '—';
          }})
          .catch(() => {{ tr.querySelector('[data-details]').textContent = '—'; }});
      }}
    }}

    tbody.addEventListener('click', async (e) => {{
      const btn = e.target.closest('button[data-done]');
      if (!btn) return;
      const order = btn.getAttribute('data-done');
      btn.disabled = true; btn.textContent = 'Sending...';
      try {{
        const res = await fetch('/api/orders/' + order + '/done', {{ method: 'POST' }});
        if (!res.ok) throw new Error('Failed');
        btn.textContent = 'Sent ✅';
        setTimeout(load, 600);
      }} catch (e) {{
        btn.textContent = 'Error';
      }}
    }});

    function startSSE() {{
      const es = new EventSource('/orders/events');
      es.onopen = () => {{
        // Pull latest state immediately on (re)connect
        load();
      }};
      es.onmessage = (ev) => {{
        try {{
          const msg = JSON.parse(ev.data);
          if (msg.type === 'order_created' ||
              msg.type === 'order_status_changed' ||
              msg.type === 'CallEnded') {{
            load();
          }}
          // ignore 'ping'
        }} catch(e) {{}}
      }};
      es.onerror = () => {{
        // Browser auto-reconnects; do a one-off reload for safety
        load();
      }};
    }}

    load(); startSSE();
    const REFRESH = {refresh or 15};
    if (REFRESH > 0) setInterval(load, REFRESH * 1000);
  </script>
</body>
</html>"""

@http_router.get("/orders")
def orders_tv(refresh: Optional[int] = Query(default=15, ge=0, le=120)):
    # Default to 15s meta+JS refresh; SSE instantly pushes on events (incl. CallEnded)
    return HTMLResponse(_orders_tv_html(refresh or 15))

@http_router.get("/barista")
def barista(refresh: Optional[int] = Query(default=15, ge=0, le=120)):
    # Default to 15s meta+JS refresh; SSE instantly pushes on events (incl. CallEnded)
    return HTMLResponse(_barista_html(refresh or 15))
