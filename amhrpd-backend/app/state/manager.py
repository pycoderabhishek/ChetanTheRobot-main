"""State Manager - Manages device state"""

import asyncio
from typing import Dict, Optional
from datetime import datetime
from app.state.models import DeviceState


class StateManager:
    """In-memory device state management"""
    
    def __init__(self):
        self.states: Dict[str, DeviceState] = {}
        self._lock = asyncio.Lock()
    
    async def update_state(self, device_id: str, device_type: str, state_data: dict) -> DeviceState:
        """Update device state"""
        async with self._lock:
            if device_id not in self.states:
                self.states[device_id] = DeviceState(
                    device_id=device_id,
                    device_type=device_type,
                    state_data=state_data,
                    last_updated=datetime.now()
                )
            else:
                self.states[device_id].state_data = state_data
                self.states[device_id].last_updated = datetime.now()
            
            return self.states[device_id]
    
    async def get_state(self, device_id: str) -> Optional[DeviceState]:
        """Get device state"""
        async with self._lock:
            return self.states.get(device_id)
    
    async def get_all_states(self) -> list[DeviceState]:
        """Get all device states"""
        async with self._lock:
            return list(self.states.values())
    
    async def get_states_by_type(self, device_type: str) -> list[DeviceState]:
        """Get states of devices of a specific type"""
        async with self._lock:
            return [s for s in self.states.values() if s.device_type == device_type]
    
    async def clear_state(self, device_id: str) -> bool:
        """Clear device state"""
        async with self._lock:
            if device_id in self.states:
                del self.states[device_id]
                return True
        return False
