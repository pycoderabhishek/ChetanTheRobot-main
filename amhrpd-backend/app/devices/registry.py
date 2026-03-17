import asyncio
from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class Device:
    device_id: str
    device_type: str
    is_online: bool
    connected_at: datetime
    last_heartbeat: datetime
    metadata: dict | None = None


class DeviceRegistry:
    def __init__(self):
        self.devices: Dict[str, Device] = {}
        self._lock = asyncio.Lock()

    async def register_device(self, device_id: str, device_type: str) -> Device:
        async with self._lock:
            now = datetime.utcnow()
            device = self.devices.get(device_id)

            if not device:
                device = Device(
                    device_id=device_id,
                    device_type=device_type,
                    is_online=True,
                    connected_at=now,
                    last_heartbeat=now,
                )
                self.devices[device_id] = device
            else:
                device.is_online = True
                device.last_heartbeat = now

            return device

    async def get_device(self, device_id: str) -> Optional[Device]:
        async with self._lock:
            return self.devices.get(device_id)

    async def get_all_devices(self) -> list[Device]:
        async with self._lock:
            return list(self.devices.values())

    async def get_devices_by_type(self, device_type: str) -> list[Device]:
        async with self._lock:
            return [
                d for d in self.devices.values()
                if d.device_type == device_type and d.is_online
            ]

    async def mark_online(self, device_id: str):
        async with self._lock:
            if device_id in self.devices:
                self.devices[device_id].is_online = True
                self.devices[device_id].last_heartbeat = datetime.utcnow()

    async def mark_offline(self, device_id: str):
        async with self._lock:
            if device_id in self.devices:
                self.devices[device_id].is_online = False
