import asyncio
from datetime import datetime, timedelta

from app.devices.registry import DeviceRegistry
from app.websocket.manager import ConnectionManager


class HeartbeatMonitor:
    def __init__(
        self,
        device_registry: DeviceRegistry,
        connection_manager: ConnectionManager,
        timeout_sec: int = 15,
    ):
        self.device_registry = device_registry
        self.connection_manager = connection_manager
        self.timeout = timedelta(seconds=timeout_sec)
        self.running = False

    async def start(self):
        self.running = True
        asyncio.create_task(self._run())

    async def stop(self):
        self.running = False

    async def _run(self):
        while self.running:
            now = datetime.utcnow()
            devices = await self.device_registry.get_all_devices()

            for d in devices:
                if not d.last_heartbeat:
                    continue

                if now - d.last_heartbeat > self.timeout:
                    await self.device_registry.mark_offline(d.device_id)
                    await self.connection_manager.disconnect(d.device_id)

            await asyncio.sleep(5)
