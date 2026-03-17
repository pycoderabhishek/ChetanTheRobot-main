import asyncio
from typing import Dict
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def add(self, device_id: str, websocket: WebSocket):
        async with self._lock:
            existing = self.active.get(device_id)
            self.active[device_id] = websocket
        if existing and existing is not websocket:
            try:
                await existing.close()
            except Exception:
                pass

    async def remove(self, device_id: str):
        async with self._lock:
            self.active.pop(device_id, None)

    async def disconnect(self, device_id: str):
        async with self._lock:
            ws = self.active.pop(device_id, None)
        if ws:
            try:
                await ws.close()
            except Exception:
                pass

    async def is_connected(self, device_id: str) -> bool:
        async with self._lock:
            return device_id in self.active

    async def send_to_device(self, device_id: str, message: dict) -> bool:
        async with self._lock:
            ws = self.active.get(device_id)

        if not ws:
            return False

        try:
            await ws.send_json(message)
            return True
        except Exception:
            await self.remove(device_id)
            return False
