"""Command Models"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Command:
    """Command Model"""
    
    command_id: str
    device_type: str  # Target device type(s)
    command_name: str
    payload: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"  # pending, sent, ack, error
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "command_id": self.command_id,
            "device_type": self.device_type,
            "command_name": self.command_name,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
        }
