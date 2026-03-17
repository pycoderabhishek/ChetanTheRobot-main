"""WebSocket Event Models"""

from pydantic import BaseModel
from typing import Optional, Any


class WebSocketMessage(BaseModel):
    """Base WebSocket Message"""
    message_type: str
    device_id: str
    timestamp: str
    payload: dict = {}


class HeartbeatMessage(WebSocketMessage):
    """Heartbeat Message from Device"""
    message_type: str = "heartbeat"


class CommandAckMessage(WebSocketMessage):
    """Command Acknowledgment Message from Device"""
    message_type: str = "command_ack"
    command_id: Optional[str] = None
    status: str = "success"  # success, error


class StatusMessage(WebSocketMessage):
    """Device Status Message"""
    message_type: str = "status"
