"""
WebSocket connection manager for servo controller.

Handles:
- Device registration and authentication
- Message routing between backend and ESP32
- Connection state tracking
- Message serialization/deserialization
"""

from typing import Optional, Dict, Set
from dataclasses import dataclass
from datetime import datetime
import json
import asyncio

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.devices.servo_state import ServoStateManager
from app.devices.servo_config import ServoState


# =============================================================================
# MESSAGE MODELS (WebSocket Protocol)
# =============================================================================

class DeviceRegistration(BaseModel):
    """Device registration message from ESP32."""
    device_id: str
    device_type: str
    firmware_version: str = "unknown"
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "device_id": "servoscontroller",
                "device_type": "esp32s3",
                "firmware_version": "1.0.0"
            }
        }
    }


class ServoCommand(BaseModel):
    """Command to servo from backend."""
    channel: int
    angle: float
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "channel": 0,
                "angle": 90.0
            }
        }
    }


class ServoFeedback(BaseModel):
    """Servo state feedback from ESP32 (works with PCA9685 or GPIO PWM)."""
    channel: int
    current_angle: float
    pulse_width_us: int
    pwm_ticks: int  # Generic PWM ticks (PCA9685: 0-4095, GPIO: 0-65535)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "channel": 0,
                "current_angle": 90.0,
                "pulse_width_us": 1500,
                "pwm_ticks": 50000
            }
        }
    }


class ErrorReport(BaseModel):
    """Error report from ESP32."""
    channel: int
    error: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "channel": 0,
                "error": "PCA9685 I2C communication failed"
            }
        }
    }


# =============================================================================
# WEBSOCKET MESSAGE WRAPPER
# =============================================================================

class WebSocketMessage(BaseModel):
    """
    Generic WebSocket message wrapper.
    
    All messages follow this format:
    {
        "type": "register|command|feedback|error|ack",
        "data": {...}
    }
    """
    type: str
    data: Dict = {}
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return self.model_dump_json()
    
    @staticmethod
    def from_json(json_str: str) -> "WebSocketMessage":
        """Deserialize from JSON."""
        return WebSocketMessage.model_validate_json(json_str)


# =============================================================================
# CONNECTION MANAGER
# =============================================================================

@dataclass
class ServoWebSocketConnection:
    """
    Represents active WebSocket connection to ESP32.
    
    Attributes:
        websocket: FastAPI WebSocket
        device_id: ESP32 device identifier
        device_type: Hardware type
        connected_at: Connection timestamp
        last_heartbeat: Last message time
        is_registered: Device registration status
    """
    
    websocket: WebSocket
    device_id: Optional[str] = None
    device_type: Optional[str] = None
    connected_at: datetime = None
    last_heartbeat: datetime = None
    is_registered: bool = False
    
    def __post_init__(self):
        if self.connected_at is None:
            self.connected_at = datetime.now()


@dataclass
class ServoWebSocketManager:
    """
    Manages WebSocket connections and message routing.
    
    Responsibilities:
    - Accept device registration
    - Route servo commands to ESP32
    - Handle servo feedback updates
    - Track connection state
    - Error propagation
    """
    
    state_manager: ServoStateManager
    active_connections: Dict[str, ServoWebSocketConnection] = None
    devices_lock: asyncio.Lock = None
    
    def __post_init__(self):
        if self.active_connections is None:
            self.active_connections = {}
        if self.devices_lock is None:
            self.devices_lock = asyncio.Lock()
    
    async def register_device(
        self,
        websocket: WebSocket,
        registration: DeviceRegistration,
    ) -> bool:
        """
        Register a new ESP32 device.
        
        Args:
            websocket: WebSocket connection
            registration: Device registration data
            
        Returns:
            True if registered successfully
        """
        async with self.devices_lock:
            # Only one servo controller device allowed
            if registration.device_id == "servoscontroller":
                if registration.device_id in self.active_connections:
                    # Disconnect existing connection
                    old_conn = self.active_connections[registration.device_id]
                    try:
                        await old_conn.websocket.close()
                    except:
                        pass
            
            # Register new connection
            connection = ServoWebSocketConnection(
                websocket=websocket,
                device_id=registration.device_id,
                device_type=registration.device_type,
                is_registered=True,
            )
            self.active_connections[registration.device_id] = connection
        
        return True
    
    async def unregister_device(self, device_id: str):
        """Unregister a device (on disconnect)."""
        async with self.devices_lock:
            if device_id in self.active_connections:
                del self.active_connections[device_id]
    
    async def get_device(self, device_id: str) -> Optional[ServoWebSocketConnection]:
        """Get device connection by ID."""
        async with self.devices_lock:
            return self.active_connections.get(device_id)
    
    async def send_command(
        self,
        device_id: str,
        channel: int,
        angle: float,
    ) -> bool:
        """
        Send servo command to ESP32.
        
        Args:
            device_id: Target device
            channel: Servo channel
            angle: Target angle in degrees
            
        Returns:
            True if sent successfully
        """
        device = await self.get_device(device_id)
        if not device or not device.is_registered:
            return False
        
        try:
            command = ServoCommand(channel=channel, angle=angle)
            msg = WebSocketMessage(type="command", data=command.model_dump())
            await device.websocket.send_text(msg.to_json())
            device.last_heartbeat = datetime.now()
            return True
        except Exception as e:
            print(f"Failed to send command: {e}")
            return False
    
    async def handle_feedback(
        self,
        device_id: str,
        feedback: ServoFeedback,
    ) -> bool:
        """
        Process servo feedback from ESP32.
        
        Updates state manager with current servo position.
        
        Args:
            device_id: Source device
            feedback: Servo state feedback
            
        Returns:
            True if processed
        """
        device = await self.get_device(device_id)
        if not device:
            return False
        
        try:
            # Update state manager
            await self.state_manager.update_current_angle(
                feedback.channel,
                feedback.current_angle,
            )
            device.last_heartbeat = datetime.now()
            return True
        except Exception as e:
            print(f"Failed to handle feedback: {e}")
            return False
    
    async def handle_error(
        self,
        device_id: str,
        error_report: ErrorReport,
    ) -> bool:
        """
        Process error report from ESP32.
        
        Args:
            device_id: Source device
            error_report: Error information
            
        Returns:
            True if processed
        """
        device = await self.get_device(device_id)
        if not device:
            return False
        
        try:
            # Record error in state manager
            await self.state_manager.set_error(
                error_report.channel,
                error_report.error,
            )
            device.last_heartbeat = datetime.now()
            return True
        except Exception as e:
            print(f"Failed to handle error: {e}")
            return False
    
    async def send_registration_ack(
        self,
        device_id: str,
        config_json: Dict,
    ) -> bool:
        """
        Send registration acknowledgement with servo configs.
        
        Args:
            device_id: Target device
            config_json: Servo configuration JSON
            
        Returns:
            True if sent successfully
        """
        device = await self.get_device(device_id)
        if not device:
            return False
        
        try:
            msg = WebSocketMessage(type="ack", data=config_json)
            await device.websocket.send_text(msg.to_json())
            device.last_heartbeat = datetime.now()
            return True
        except Exception as e:
            print(f"Failed to send ACK: {e}")
            return False
    
    async def get_connection_status(self) -> Dict:
        """Get status of all connections."""
        async with self.devices_lock:
            status = {}
            for device_id, conn in self.active_connections.items():
                status[device_id] = {
                    "connected": conn.is_registered,
                    "device_type": conn.device_type,
                    "connected_at": conn.connected_at.isoformat(),
                    "last_heartbeat": (
                        conn.last_heartbeat.isoformat() 
                        if conn.last_heartbeat 
                        else None
                    ),
                }
            return status


def create_websocket_manager(
    state_manager: ServoStateManager,
) -> ServoWebSocketManager:
    """Factory: Create WebSocket manager."""
    return ServoWebSocketManager(state_manager=state_manager)
