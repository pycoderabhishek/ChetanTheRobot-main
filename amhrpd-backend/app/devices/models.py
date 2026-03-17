"""Device Data Models"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Device:
    """Device Model"""
    
    device_id: str
    device_type: str  # e.g., "ESP32", "ESP32-S3", "ESP32-CAM"
    is_online: bool = False
    last_heartbeat: Optional[datetime] = None
    connected_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "is_online": self.is_online,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "metadata": self.metadata,
        }
