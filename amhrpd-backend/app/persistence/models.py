"""SQLAlchemy ORM Models"""

from sqlalchemy import Column, String, Boolean, DateTime, JSON, Integer, Float, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class DeviceRecord(Base):
    """Device Connection Status Record"""
    
    __tablename__ = "devices"
    
    device_id = Column(String(255), primary_key=True, index=True)
    device_type = Column(String(50), nullable=False, index=True)
    is_online = Column(Boolean, default=False, nullable=False)
    last_heartbeat = Column(DateTime, nullable=True)
    connected_at = Column(DateTime, default=datetime.now, nullable=False)
    disconnected_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default={}, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index("idx_device_type_online", "device_type", "is_online"),
    )
    
    def __repr__(self):
        return f"<DeviceRecord {self.device_id} ({self.device_type}) - Online: {self.is_online}>"


class DeviceStateSnapshot(Base):
    """Hardware State Snapshot Record"""
    
    __tablename__ = "device_state_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(255), ForeignKey("devices.device_id"), nullable=False, index=True)
    device_type = Column(String(50), nullable=False)
    state_data = Column(JSON, nullable=False)
    timestamp = Column(DateTime, default=datetime.now, nullable=False, index=True)
    
    # Indexes
    __table_args__ = (
        Index("idx_device_timestamp", "device_id", "timestamp"),
    )
    
    def __repr__(self):
        return f"<DeviceStateSnapshot {self.device_id} at {self.timestamp}>"


class CommandLog(Base):
    """Command Execution Log Record"""
    
    __tablename__ = "command_logs"
    
    command_id = Column(String(255), primary_key=True, index=True)
    device_type = Column(String(50), nullable=False, index=True)
    command_name = Column(String(255), nullable=False)
    payload = Column(JSON, default={}, nullable=False)
    status = Column(String(50), default="pending", nullable=False, index=True)  # pending, sent, ack_success, ack_error
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    executed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    response_data = Column(JSON, nullable=True)
    target_device_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index("idx_status_created", "status", "created_at"),
        Index("idx_device_type_created", "device_type", "created_at"),
    )
    
    def __repr__(self):
        return f"<CommandLog {self.command_id} ({self.command_name}) - Status: {self.status}>"


class DeviceConnectionLog(Base):
    """Device Connection History Log"""
    
    __tablename__ = "device_connection_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(255), ForeignKey("devices.device_id"), nullable=False, index=True)
    device_type = Column(String(50), nullable=False)
    event = Column(String(50), nullable=False)  # connected, disconnected, timeout
    timestamp = Column(DateTime, default=datetime.now, nullable=False, index=True)
    details = Column(JSON, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index("idx_device_event_time", "device_id", "event", "timestamp"),
    )
    
    def __repr__(self):
        return f"<DeviceConnectionLog {self.device_id} - {self.event}>"
