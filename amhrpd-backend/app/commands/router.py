"""
WebSocket Connection Manager + Command Router
Manages active ESP device connections and command routing

NOTE:
- websocket.accept() MUST be called ONLY in WebSocket endpoint
"""

import asyncio
import uuid
from typing import Dict, List
from fastapi import WebSocket

from app.commands.models import Command
from app.websocket.manager import ConnectionManager


class CommandRouter:
    """Routes commands to appropriate devices via WebSocket"""

    def __init__(self, connection_manager: ConnectionManager, device_registry):
        self.connection_manager = connection_manager
        self.device_registry = device_registry
        self._system_locked = False

    async def _send_lock_command(self, lock: bool):
        """Send lock/unlock signal to Wheel Controller"""
        cmd = "lock" if lock else "unlock"
        message = {
            "message_type": "command",
            "command_id": str(uuid.uuid4()),
            "command_name": cmd,
            "payload": {}
        }
        # Send to all wheel controllers (device_type='esp32')
        wheels = await self.device_registry.get_devices_by_type("esp32")
        for w in wheels:
            if w.is_online:
                await self.connection_manager.send_to_device(w.device_id, message)

    async def route_command(
        self,
        device_type: str,
        command_name: str,
        payload: dict = None
    ) -> Command:
        """
        Route a command to all devices of the specified type.
        """
        if payload is None:
            payload = {}

        # --- INTERLOCK LOGIC ---
        
        # 1. Check Lock for Wheel Movement
        wheel_cmds = ["forward", "backward", "left", "right", "MOVE_FORWARD", "MOVE_BACKWARD", "TURN_LEFT", "TURN_RIGHT"]
        if device_type == "esp32" and command_name in wheel_cmds:
            if self._system_locked:
                return Command(
                    command_id=str(uuid.uuid4()),
                    device_type=device_type,
                    command_name=command_name,
                    payload=payload,
                    status="rejected_system_locked"
                )

        # 2. Engage Lock for Servo Actions
        if device_type == "esp32s3" and command_name in ["handsup", "resetposition", "headup", "headleft"]:
            self._system_locked = True
            await self._send_lock_command(True)
            # Schedule Unlock (Simulated duration - ideally should come from feedback)
            asyncio.create_task(self._auto_unlock(5.0))

        command_id = str(uuid.uuid4())
        command = Command(
            command_id=command_id,
            device_type=device_type,
            command_name=command_name,
            payload=payload,
            status="pending"
        )
        
        # ... (rest of function) ...
        
        # Build the message to send
        message = {
            "message_type": "command",
            "command_id": command_id,
            "command_name": command_name,
            "payload": payload
        }

        # Get target devices
        target_devices = await self.device_registry.get_devices_by_type(device_type)
        sent_count = 0

        for device in target_devices:
            if device.is_online:
                success = await self.connection_manager.send_to_device(
                    device.device_id, message
                )
                if success:
                    sent_count += 1

        if sent_count > 0:
            command.status = "sent"
        else:
            command.status = "no_devices"

        return command

    async def _auto_unlock(self, delay: float):
        await asyncio.sleep(delay)
        self._system_locked = False
        await self._send_lock_command(False)

