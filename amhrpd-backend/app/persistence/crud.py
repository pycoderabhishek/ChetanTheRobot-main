"""CRUD Operations for Database Models"""

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from app.persistence.models import (
    DeviceRecord,
    DeviceStateSnapshot,
    CommandLog,
    DeviceConnectionLog
)


# ============================================================================
# Device Record CRUD
# ============================================================================

async def create_or_update_device(
    db: Session,
    device_id: str,
    device_type: str,
    is_online: bool = True,
    metadata: dict = None
) -> DeviceRecord:
    """Create or update device record"""
    if metadata is None:
        metadata = {}
    
    device = db.query(DeviceRecord).filter(DeviceRecord.device_id == device_id).first()
    
    if not device:
        # New device
        device = DeviceRecord(
            device_id=device_id,
            device_type=device_type,
            is_online=is_online,
            last_heartbeat=datetime.now(),
            connected_at=datetime.now(),
            metadata_json=metadata
        )
        db.add(device)
    else:
        # Update existing device
        device.device_type = device_type
        device.is_online = is_online
        device.last_heartbeat = datetime.now()
        device.metadata_json = metadata
        if is_online and not device.connected_at:
            device.connected_at = datetime.now()
        if not is_online and not device.disconnected_at:
            device.disconnected_at = datetime.now()
    
    db.commit()
    db.refresh(device)
    return device


async def get_device(db: Session, device_id: str):
    """Get device by ID"""
    return db.query(DeviceRecord).filter(DeviceRecord.device_id == device_id).first()


async def get_all_devices(db: Session):
    """Get all devices"""
    return db.query(DeviceRecord).all()


async def get_devices_by_type(db: Session, device_type: str):
    """Get devices by type"""
    return db.query(DeviceRecord).filter(DeviceRecord.device_type == device_type).all()


async def get_online_devices(db: Session):
    """Get all online devices"""
    return db.query(DeviceRecord).filter(DeviceRecord.is_online == True).all()


async def mark_device_offline(db: Session, device_id: str):
    """Mark device as offline"""
    device = await get_device(db, device_id)
    if device:
        device.is_online = False
        device.disconnected_at = datetime.now()
        db.commit()
        db.refresh(device)
    return device


async def delete_device(db: Session, device_id: str) -> bool:
    """Delete device record"""
    device = await get_device(db, device_id)
    if device:
        db.delete(device)
        db.commit()
        return True
    return False


# ============================================================================
# Device State Snapshot CRUD
# ============================================================================

async def create_state_snapshot(
    db: Session,
    device_id: str,
    device_type: str,
    state_data: dict
) -> DeviceStateSnapshot:
    """Create device state snapshot"""
    snapshot = DeviceStateSnapshot(
        device_id=device_id,
        device_type=device_type,
        state_data=state_data,
        timestamp=datetime.now()
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


async def get_latest_state(db: Session, device_id: str):
    """Get latest state snapshot for device"""
    return db.query(DeviceStateSnapshot)\
        .filter(DeviceStateSnapshot.device_id == device_id)\
        .order_by(desc(DeviceStateSnapshot.timestamp))\
        .first()


async def get_state_history(
    db: Session,
    device_id: str,
    limit: int = 100
):
    """Get state history for device"""
    return db.query(DeviceStateSnapshot)\
        .filter(DeviceStateSnapshot.device_id == device_id)\
        .order_by(desc(DeviceStateSnapshot.timestamp))\
        .limit(limit)\
        .all()


async def get_device_type_states(
    db: Session,
    device_type: str,
    limit: int = 100
):
    """Get latest state for all devices of a type"""
    return db.query(DeviceStateSnapshot)\
        .filter(DeviceStateSnapshot.device_type == device_type)\
        .order_by(desc(DeviceStateSnapshot.timestamp))\
        .limit(limit)\
        .all()


# ============================================================================
# Command Log CRUD
# ============================================================================

async def create_command_log(
    db: Session,
    command_id: str,
    device_type: str,
    command_name: str,
    payload: dict,
    target_device_count: int = 0
) -> CommandLog:
    """Create command log"""
    log = CommandLog(
        command_id=command_id,
        device_type=device_type,
        command_name=command_name,
        payload=payload,
        status="created",
        target_device_count=target_device_count,
        created_at=datetime.now()
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


async def get_command_log(db: Session, command_id: str):
    """Get command log by ID"""
    return db.query(CommandLog).filter(CommandLog.command_id == command_id).first()


async def update_command_status(
    db: Session,
    command_id: str,
    status: str,
    success_count: int = None,
    response_data: dict = None
) -> CommandLog:
    """Update command log status"""
    log = await get_command_log(db, command_id)
    if log:
        log.status = status
        if status == "sent":
            log.executed_at = datetime.now()
        elif status.startswith("ack_"):
            log.completed_at = datetime.now()
        
        if success_count is not None:
            log.success_count = success_count
        if response_data is not None:
            log.response_data = response_data
        
        db.commit()
        db.refresh(log)
    
    return log


async def get_commands_by_status(db: Session, status: str, limit: int = 100):
    """Get commands by status"""
    return db.query(CommandLog)\
        .filter(CommandLog.status == status)\
        .order_by(desc(CommandLog.created_at))\
        .limit(limit)\
        .all()


async def get_commands_by_device_type(
    db: Session,
    device_type: str,
    limit: int = 100
):
    """Get commands for device type"""
    return db.query(CommandLog)\
        .filter(CommandLog.device_type == device_type)\
        .order_by(desc(CommandLog.created_at))\
        .limit(limit)\
        .all()


async def get_all_command_logs(db: Session, limit: int = 1000):
    """Get all command logs"""
    return db.query(CommandLog)\
        .order_by(desc(CommandLog.created_at))\
        .limit(limit)\
        .all()


# ============================================================================
# Device Connection Log CRUD
# ============================================================================

async def create_connection_log(
    db: Session,
    device_id: str,
    device_type: str,
    event: str,
    details: dict = None
) -> DeviceConnectionLog:
    """Create device connection log"""
    log = DeviceConnectionLog(
        device_id=device_id,
        device_type=device_type,
        event=event,
        details=details or {},
        timestamp=datetime.now()
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


async def get_device_connection_history(
    db: Session,
    device_id: str,
    limit: int = 100
):
    """Get connection history for device"""
    return db.query(DeviceConnectionLog)\
        .filter(DeviceConnectionLog.device_id == device_id)\
        .order_by(desc(DeviceConnectionLog.timestamp))\
        .limit(limit)\
        .all()


async def get_connection_events_by_type(
    db: Session,
    event: str,
    limit: int = 100
):
    """Get connection events by type"""
    return db.query(DeviceConnectionLog)\
        .filter(DeviceConnectionLog.event == event)\
        .order_by(desc(DeviceConnectionLog.timestamp))\
        .limit(limit)\
        .all()
