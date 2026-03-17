from dataclasses import dataclass
from typing import Dict
import asyncio


@dataclass
class ServoState:
    channel: int
    current_angle: float
    target_angle: float
    is_moving: bool


class ServoStateManager:
    def __init__(self):
        self.states: Dict[int, ServoState] = {}
        self.lock = asyncio.Lock()

    async def set_target(self, channel: int, angle: float):
        async with self.lock:
            self.states[channel] = ServoState(
                channel=channel,
                current_angle=angle,
                target_angle=angle,
                is_moving=False,
            )

    async def get_all_states(self):
        async with self.lock:
            return self.states
