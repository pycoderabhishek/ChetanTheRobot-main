"""Dependency Injection"""

from typing import Optional
from app.websocket.manager import ConnectionManager
from app.devices.registry import DeviceRegistry
from app.state.manager import StateManager
from app.heartbeat.monitor import HeartbeatMonitor
from app.config import settings


# Singleton instances
_connection_manager: Optional[ConnectionManager] = None
_device_registry: Optional[DeviceRegistry] = None
_state_manager: Optional[StateManager] = None
_heartbeat_monitor: Optional[HeartbeatMonitor] = None

def get_connection_manager() -> ConnectionManager:
    """Get WebSocket Connection Manager"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager


def get_device_registry() -> DeviceRegistry:
    """Get Device Registry"""
    global _device_registry
    if _device_registry is None:
        _device_registry = DeviceRegistry()
    return _device_registry


def get_state_manager() -> StateManager:
    """Get State Manager"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


def get_heartbeat_monitor() -> HeartbeatMonitor:
    """Get Heartbeat Monitor"""
    global _heartbeat_monitor
    if _heartbeat_monitor is None:
        _heartbeat_monitor = HeartbeatMonitor(
            device_registry=get_device_registry(),
            connection_manager=get_connection_manager(),
            timeout_sec=settings.WS_HEARTBEAT_TIMEOUT
        )
    return _heartbeat_monitor
