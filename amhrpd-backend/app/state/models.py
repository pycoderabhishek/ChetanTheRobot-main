"""State Models"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DeviceState:
    """Device State"""
    
    device_id: str
    device_type: str
    state_data: dict = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "state_data": self.state_data,
            "last_updated": self.last_updated.isoformat(),
        }
