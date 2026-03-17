"""
MESSAGE CONTRACTS - Pydantic Models for WebSocket Communication

Defines all JSON message types exchanged between FastAPI backend and ESP32-S3 firmware.
Each model is JSON-serializable and validates incoming/outgoing messages.

STEP 5: Complete message contract definitions with examples and validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


# ============================================================================
# MESSAGE ENUMERATIONS
# ============================================================================

class MessageType:
    """WebSocket message type constants"""
    REGISTER = "register"
    ACK = "ack"
    COMMAND = "command"
    FEEDBACK = "feedback"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


# ============================================================================
# 1. DEVICE REGISTRATION (ESP32 → Backend on connection)
# ============================================================================

class DeviceRegistration(BaseModel):
    """
    Message sent by ESP32 on first WebSocket connection.
    
    Backend registers the device and maintains connection tracking.
    Response: Backend sends ACK message.
    
    Example:
    {
        "type": "register",
        "device_id": "servoscontroller",
        "device_type": "esp32s3",
        "firmware_version": "1.0.0",
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "timestamp": "2026-01-26T12:35:00.000000"
    }
    """
    
    type: str = Field(
        default="register",
        description="Message type identifier"
    )
    device_id: str = Field(
        description="Unique device identifier (e.g., 'servoscontroller')",
        min_length=1,
        max_length=64
    )
    device_type: str = Field(
        description="Hardware type (e.g., 'esp32s3', 'esp32', 'esp32-cam')",
        min_length=1,
        max_length=32
    )
    firmware_version: str = Field(
        description="Firmware version string",
        min_length=1,
        max_length=16
    )
    mac_address: str = Field(
        description="Device MAC address (format: AA:BB:CC:DD:EE:FF)",
        min_length=17,
        max_length=17
    )
    timestamp: str = Field(
        description="ISO8601 timestamp when message sent"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "register",
                "device_id": "servoscontroller",
                "device_type": "esp32s3",
                "firmware_version": "1.0.0",
                "mac_address": "A4:CF:12:34:56:78",
                "timestamp": "2026-01-26T12:35:00.000000"
            }
        }


# ============================================================================
# 2. REGISTRATION ACKNOWLEDGEMENT (Backend → ESP32 after registration)
# ============================================================================

class RegistrationAck(BaseModel):
    """
    Acknowledgement sent by backend to confirm device registration.
    
    ESP32 waits for this message before processing commands.
    Sent immediately after receiving DeviceRegistration.
    
    Example:
    {
        "type": "ack",
        "device_id": "servoscontroller",
        "status": "registered",
        "timestamp": "2026-01-26T12:35:00.100000"
    }
    """
    
    type: str = Field(
        default="ack",
        description="Message type identifier"
    )
    device_id: str = Field(
        description="Device being acknowledged"
    )
    status: str = Field(
        description="Status string ('registered', 'updated', 'error')"
    )
    timestamp: str = Field(
        description="ISO8601 timestamp when ACK sent"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "ack",
                "device_id": "servoscontroller",
                "status": "registered",
                "timestamp": "2026-01-26T12:35:00.100000"
            }
        }


# ============================================================================
# 3. SERVO COMMAND (Backend → ESP32 to control servos)
# ============================================================================

class ServoCommand(BaseModel):
    """
    Command to control one or more servos on ESP32.
    
    Backend sends to ESP32 via WebSocket after user moves slider.
    ESP32 applies angle clamping and sends to PCA9685 driver.
    Response: ESP32 sends ServoFeedback when motion complete.
    
    Example (single servo):
    {
        "type": "command",
        "channel": 0,
        "angle": 120.5,
        "duration_ms": 500,
        "timestamp": "2026-01-26T12:35:02.000000"
    }
    """
    
    type: str = Field(
        default="command",
        description="Message type identifier"
    )
    channel: int = Field(
        ge=0,
        le=9,
        description="Servo channel (0-9 for 10 servos)"
    )
    angle: float = Field(
        ge=0.0,
        le=180.0,
        description="Target angle in degrees (0-180)"
    )
    duration_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional motion duration in milliseconds"
    )
    timestamp: str = Field(
        description="ISO8601 timestamp when command sent"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "command",
                "channel": 0,
                "angle": 120.5,
                "duration_ms": 500,
                "timestamp": "2026-01-26T12:35:02.000000"
            }
        }


# ============================================================================
# 4. SERVO FEEDBACK (ESP32 → Backend with servo state update)
# ============================================================================

class ServoFeedback(BaseModel):
    """
    State update sent by ESP32 reporting current servo position and status.
    
    Sent periodically by ESP32 (every ~500ms) or after command execution.
    Backend updates dashboard with live servo positions.
    
    Example:
    {
        "type": "feedback",
        "channel": 0,
        "current_angle": 119.5,
        "target_angle": 120.5,
        "pulse_width_us": 1610,
        "pca9685_ticks": 329,
        "is_moving": false,
        "error": null,
        "timestamp": "2026-01-26T12:35:02.500000"
    }
    """
    
    type: str = Field(
        default="feedback",
        description="Message type identifier"
    )
    channel: int = Field(
        ge=0,
        le=9,
        description="Servo channel (0-9)"
    )
    current_angle: float = Field(
        description="Current servo angle in degrees"
    )
    target_angle: float = Field(
        description="Target angle (from last command)"
    )
    pulse_width_us: float = Field(
        description="PWM pulse width in microseconds (1000-2000)"
    )
    pca9685_ticks: int = Field(
        ge=0,
        le=65535,
        description="PWM tick count (PCA9685: 0-4095, GPIO PWM: 0-65535)"
    )
    is_moving: bool = Field(
        description="True if servo currently in motion"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if servo fault occurred"
    )
    timestamp: str = Field(
        description="ISO8601 timestamp when feedback generated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "feedback",
                "channel": 0,
                "current_angle": 119.5,
                "target_angle": 120.5,
                "pulse_width_us": 1610,
                "pca9685_ticks": 50000,
                "is_moving": False,
                "error": None,
                "timestamp": "2026-01-26T12:35:02.500000"
            }
        }


# ============================================================================
# 5. ERROR REPORT (ESP32 → Backend when error occurs)
# ============================================================================

class ErrorReport(BaseModel):
    """
    Error condition reported by ESP32 to backend.
    
    Sent when ESP32 encounters I2C error, command out of range, etc.
    Backend displays error on dashboard and in logs.
    
    Example (I2C communication failure):
    {
        "type": "error",
        "channel": 0,
        "error_code": 1,
        "error_message": "I2C communication failed",
        "timestamp": "2026-01-26T12:35:03.000000"
    }
    
    Example (angle out of range):
    {
        "type": "error",
        "channel": 3,
        "error_code": 2,
        "error_message": "Angle 250 exceeds max 180",
        "timestamp": "2026-01-26T12:35:03.500000"
    }
    """
    
    type: str = Field(
        default="error",
        description="Message type identifier"
    )
    channel: Optional[int] = Field(
        default=None,
        ge=0,
        le=9,
        description="Servo channel (None if system-level error)"
    )
    error_code: int = Field(
        description="Error code for categorization"
    )
    error_message: str = Field(
        description="Human-readable error description",
        min_length=1,
        max_length=256
    )
    timestamp: str = Field(
        description="ISO8601 timestamp when error occurred"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "error",
                "channel": 0,
                "error_code": 1,
                "error_message": "I2C communication failed",
                "timestamp": "2026-01-26T12:35:03.000000"
            }
        }


# Error code constants
class ErrorCode:
    """Standard error codes"""
    I2C_COMMUNICATION_FAILED = 1
    ANGLE_OUT_OF_RANGE = 2
    SERVO_TIMEOUT = 3
    PWM_DRIVER_ERROR = 4
    WIFI_DISCONNECTED = 5
    WEBSOCKET_DISCONNECTED = 6
    MEMORY_ERROR = 7
    UNKNOWN_ERROR = 99


# ============================================================================
# 6. HEARTBEAT / PING (Backend → ESP32)
# ============================================================================

class HeartbeatPing(BaseModel):
    """
    Periodic heartbeat sent by backend to keep WebSocket alive.
    
    Sent every 10 seconds (configurable).
    ESP32 responds with HeartbeatPong.
    
    Example:
    {
        "type": "ping",
        "timestamp": "2026-01-26T12:35:05.000000"
    }
    """
    
    type: str = Field(
        default="ping",
        description="Message type identifier"
    )
    timestamp: str = Field(
        description="ISO8601 timestamp"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "ping",
                "timestamp": "2026-01-26T12:35:05.000000"
            }
        }


# ============================================================================
# 7. HEARTBEAT / PONG (ESP32 → Backend)
# ============================================================================

class HeartbeatPong(BaseModel):
    """
    Response to heartbeat ping from ESP32.
    
    Echoes the original ping timestamp.
    Backend uses to calculate round-trip time (latency).
    
    Example:
    {
        "type": "pong",
        "timestamp": "2026-01-26T12:35:05.000000"
    }
    """
    
    type: str = Field(
        default="pong",
        description="Message type identifier"
    )
    timestamp: str = Field(
        description="ISO8601 timestamp (echoed from ping)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "pong",
                "timestamp": "2026-01-26T12:35:05.000000"
            }
        }


# ============================================================================
# 8. GENERIC WEBSOCKET MESSAGE WRAPPER
# ============================================================================

class WebSocketMessage(BaseModel):
    """
    Generic wrapper for any WebSocket message.
    
    Used to parse incoming messages and determine type.
    Allows handling of any message type with fallback.
    
    Example:
    {
        "type": "command",
        "channel": 0,
        "angle": 120.5,
        "duration_ms": 500,
        "timestamp": "2026-01-26T12:35:02.000000"
    }
    """
    
    type: str = Field(
        description="Message type: register, ack, command, feedback, error, ping, pong"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Message-specific payload"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "command",
                "data": {
                    "channel": 0,
                    "angle": 120.5,
                    "duration_ms": 500,
                    "timestamp": "2026-01-26T12:35:02.000000"
                }
            }
        }


# ============================================================================
# MESSAGE FACTORY FUNCTIONS
# ============================================================================

def create_register_message(
    device_id: str,
    device_type: str = "esp32s3",
    firmware_version: str = "1.0.0",
    mac_address: str = "00:00:00:00:00:00"
) -> DeviceRegistration:
    """
    Factory function to create a registration message.
    
    Args:
        device_id: Unique device identifier
        device_type: Hardware type (esp32s3, esp32, etc.)
        firmware_version: Firmware version string
        mac_address: Device MAC address
    
    Returns:
        DeviceRegistration message
    """
    return DeviceRegistration(
        device_id=device_id,
        device_type=device_type,
        firmware_version=firmware_version,
        mac_address=mac_address,
        timestamp=datetime.utcnow().isoformat()
    )


def create_command_message(
    channel: int,
    angle: float,
    duration_ms: Optional[int] = None
) -> ServoCommand:
    """
    Factory function to create a servo command message.
    
    Args:
        channel: Servo channel (0-9)
        angle: Target angle (0-180)
        duration_ms: Optional motion duration
    
    Returns:
        ServoCommand message
    """
    return ServoCommand(
        channel=channel,
        angle=angle,
        duration_ms=duration_ms,
        timestamp=datetime.utcnow().isoformat()
    )


def create_feedback_message(
    channel: int,
    current_angle: float,
    target_angle: float,
    pulse_width_us: float,
    pca9685_ticks: int,
    is_moving: bool,
    error: Optional[str] = None
) -> ServoFeedback:
    """
    Factory function to create a servo feedback message.
    
    Args:
        channel: Servo channel (0-9)
        current_angle: Current servo angle
        target_angle: Target angle from last command
        pulse_width_us: PWM pulse width in microseconds
        pca9685_ticks: PCA9685 tick count
        is_moving: Motion status
        error: Optional error message
    
    Returns:
        ServoFeedback message
    """
    return ServoFeedback(
        channel=channel,
        current_angle=current_angle,
        target_angle=target_angle,
        pulse_width_us=pulse_width_us,
        pca9685_ticks=pca9685_ticks,
        is_moving=is_moving,
        error=error,
        timestamp=datetime.utcnow().isoformat()
    )


def create_error_message(
    error_code: int,
    error_message: str,
    channel: Optional[int] = None
) -> ErrorReport:
    """
    Factory function to create an error report message.
    
    Args:
        error_code: Error code
        error_message: Human-readable error description
        channel: Optional servo channel
    
    Returns:
        ErrorReport message
    """
    return ErrorReport(
        channel=channel,
        error_code=error_code,
        error_message=error_message,
        timestamp=datetime.utcnow().isoformat()
    )


def create_ping_message() -> HeartbeatPing:
    """Create a ping heartbeat message."""
    return HeartbeatPing(timestamp=datetime.utcnow().isoformat())


def create_pong_message() -> HeartbeatPong:
    """Create a pong heartbeat message."""
    return HeartbeatPong(timestamp=datetime.utcnow().isoformat())
