"""Device Pydantic Schemas"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DeviceRegistration(BaseModel):
    """Device Registration Schema"""
    device_id: str
    device_type: str


class DeviceResponse(BaseModel):
    """Device Response Schema"""
    device_id: str
    device_type: str
    is_online: bool
    last_heartbeat: Optional[datetime] = None
    connected_at: Optional[datetime] = None
    metadata: dict = {}


class DeviceListResponse(BaseModel):
    """Device List Response Schema"""
    total: int
    devices: list[DeviceResponse]
