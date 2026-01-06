# events.py

import asyncio
from typing import Any, List, DefaultDict
from collections import defaultdict

# topic -> list[asyncio.Queue]
_topics: DefaultDict[str, List[asyncio.Queue]] = defaultdict(list)
_lock = asyncio.Lock()

async def publish(topic: str, event: Any) -> None:
    """Publish to all subscribers of a topic."""
    async with _lock:
        queues = list(_topics.get(topic, []))
    for q in queues:
        try:
            q.put_nowait(event)
        except Exception:
            # best-effort; drop if a slow consumer
            pass

async def subscribe(topic: str) -> asyncio.Queue:
    """Subscribe to a topic; caller should read from the returned queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    async with _lock:
        _topics[topic].append(q)
    return q

async def unsubscribe(topic: str, q: asyncio.Queue) -> None:
    async with _lock:
        try:
            _topics[topic].remove(q)
        except ValueError:
            pass
