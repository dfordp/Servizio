# order_ids.py
import asyncio
import time


class OrderIdGen:
    """Simple atomic order id generator safe across concurrent requests."""
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # seed to reduce chance of identical ids across restarts
        self._n = int(time.time() % 1000000)

    async def next(self) -> str:
        async with self._lock:
            self._n += 1
            return f"MZ{self._n:06d}"


order_ids = OrderIdGen()
