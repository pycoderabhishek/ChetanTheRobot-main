from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from datetime import datetime
from collections import deque
from threading import Lock
import logging
import os
import json
import time

from app.config import settings
from app.websocket.manager import ConnectionManager
from app.dependencies import (
    get_connection_manager,
    get_device_registry,
    get_state_manager,
    get_heartbeat_monitor,
)
from app.persistence.database import init_db, get_db
from app.persistence import crud
from app.audio.routes import router as audio_router
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SYSTEM_LOGS: deque[dict] = deque(maxlen=2000)
SYSTEM_LOGS_LOCK = Lock()
LAST_WS_ACCEPT: dict[str, float] = {}
WS_ACCEPT_DEBOUNCE_SEC = 2.0


class _InMemoryLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            with SYSTEM_LOGS_LOCK:
                SYSTEM_LOGS.append(entry)
        except Exception:
            return


_root_logger = logging.getLogger()
if not any(isinstance(h, _InMemoryLogHandler) for h in _root_logger.handlers):
    _mem_handler = _InMemoryLogHandler()
    _mem_handler.setLevel(logging.INFO)
    _root_logger.addHandler(_mem_handler)

# ================= LIFESPAN =================

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized")

    # Ensure command routing is available for REST endpoints like /servo/pose/*
    from app.commands.router import CommandRouter
    app.state.command_router = CommandRouter(
        get_connection_manager(),
        get_device_registry(),
    )
    logger.info("Command router initialized")

    heartbeat_monitor = get_heartbeat_monitor()
    await heartbeat_monitor.start()
    logger.info("Heartbeat monitor started")

    yield

    await heartbeat_monitor.stop()
    logger.info("Heartbeat monitor stopped")

# ================= APP =================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= WEBSOCKET =================

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    # ✅ ACCEPT ONCE — FIRST LINE
    await websocket.accept()

    # Prevent browsers/dashboards from taking over a device_id.
    # Only the ESP32 should use /ws/servoscontroller.
    if device_id in {"servo", "dashboard", "browser"}:
        logger.info(f"Rejecting non-device websocket id: {device_id}")
        await websocket.close(code=1008)
        return

    logger.info(f"WebSocket accepted: {device_id}")

    connection_manager: ConnectionManager = get_connection_manager()
    device_registry = get_device_registry()
    state_manager = get_state_manager()
    db_gen = get_db()
    db = next(db_gen)

    now = time.monotonic()
    last_seen = LAST_WS_ACCEPT.get(device_id)
    if last_seen and now - last_seen < WS_ACCEPT_DEBOUNCE_SEC:
        await websocket.close(code=1008)
        return
    LAST_WS_ACCEPT[device_id] = now
    if await connection_manager.is_connected(device_id):
        await websocket.close(code=1008)
        return

    await connection_manager.add(device_id, websocket)

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(msg.get("code", 1000))

            text = msg.get("text")
            if not text:
                continue

            try:
                data = json.loads(text)
            except Exception:
                logger.warning(f"Non-JSON WS message from {device_id}: {text[:200]}")
                continue

            message_type = data.get("message_type")
            device_type = data.get("device_type")

            if not device_type:
                await websocket.send_json({"error": "device_type required"})
                continue

            # ===== REGISTRATION =====
            if message_type == "registration":
                metadata = data.get("metadata", {})

                # Register device (NO metadata argument)
                await device_registry.register_device(
                    device_id=device_id,
                    device_type=device_type
                )

                # Persist device + metadata in DB
                await crud.create_or_update_device(
                    db=db,
                    device_id=device_id,
                    device_type=device_type,
                    is_online=True,
                    metadata=metadata  # ✅ DB layer supports metadata
                )

                await crud.create_connection_log(
                    db=db,
                    device_id=device_id,
                    device_type=device_type,
                    event="connected"
                )

                logger.info(f"Device registered: {device_id}")

            # ===== HEARTBEAT =====
            elif message_type == "heartbeat":
                await device_registry.mark_online(device_id)

            # ===== STATE UPDATE =====
            elif message_type == "status":
                payload = data.get("payload", {})
                await state_manager.update_state(device_id, device_type, payload)
                await crud.create_state_snapshot(
                    db=db,
                    device_id=device_id,
                    device_type=device_type,
                    state_data=payload
                )

            # ===== COMMAND ACK =====
            elif message_type == "command_ack":
                command_id = data.get("command_id")
                status = data.get("status", "success")

                await crud.update_command_status(
                    db=db,
                    command_id=command_id,
                    status=f"ack_{status}"
                )

            else:
                logger.warning(
                    f"Unknown message type from {device_id}: {message_type}"
                )

    except WebSocketDisconnect as e:
        await connection_manager.remove(device_id)
        await device_registry.mark_offline(device_id)

        device = await device_registry.get_device(device_id)
        if device:
            await crud.mark_device_offline(db, device_id)
            await crud.create_connection_log(
                db=db,
                device_id=device_id,
                device_type=device.device_type,
                event="disconnected"
            )

        logger.info(f"Device disconnected: {device_id} (code={getattr(e, 'code', None)})")

    except Exception as e:
        logger.exception(f"WebSocket error for {device_id}")
        await connection_manager.remove(device_id)

    finally:
        try:
            db_gen.close()
        except Exception:
            pass

# ================= REST API =================

# API router
api_router = APIRouter(prefix="/api", tags=["API"])

@api_router.get("/devices")
async def list_devices():
    """Get all registered devices"""
    device_registry = get_device_registry()
    devices = await device_registry.get_all_devices()
    
    return {
        "total": len(devices),
        "devices": [
            {
                "device_id": d.device_id,
                "device_type": d.device_type,
                "is_online": d.is_online,
                "last_heartbeat": d.last_heartbeat.isoformat() if d.last_heartbeat else None,
                "connected_at": d.connected_at.isoformat() if d.connected_at else None,
                "metadata": d.metadata or {}
            }
            for d in devices
        ]
    }


@api_router.get("/system/logs")
async def get_system_logs(limit: int = 200, level: str | None = None):
    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000
    with SYSTEM_LOGS_LOCK:
        items = list(SYSTEM_LOGS)
    if level:
        level_upper = level.strip().upper()
        items = [x for x in items if (x.get("level") or "").upper() == level_upper]
    return {"logs": items[-limit:]}

@api_router.get("/devices/{device_id}")
async def get_device(device_id: str):
    """Get device details"""
    device_registry = get_device_registry()
    device = await device_registry.get_device(device_id)
    
    if not device:
        return {"error": "Device not found"}, 404
    
    return {
        "device_id": device.device_id,
        "device_type": device.device_type,
        "is_online": device.is_online,
        "last_heartbeat": device.last_heartbeat.isoformat() if device.last_heartbeat else None,
        "connected_at": device.connected_at.isoformat() if device.connected_at else None,
        "metadata": device.metadata or {}
    }

@api_router.post("/command")
async def send_command(
    request: Request,
    device_type: str,
    command_name: str,
    payload: dict = None,
    db: Session = Depends(get_db)
):
    """Send a command to all devices of a specific type"""
    if payload is None:
        payload = {}
    
    if not hasattr(request.app.state, "command_router"):
        return {"error": "Command router not initialized"}, 500
    
    command_router = request.app.state.command_router
    device_registry = get_device_registry()
    
    # Route command to devices
    command = await command_router.route_command(device_type, command_name, payload)
    
    # Persist to database
    target_devices = await device_registry.get_devices_by_type(device_type)
    await crud.create_command_log(
        db=db,
        command_id=command.command_id,
        device_type=device_type,
        command_name=command_name,
        payload=payload,
        target_device_count=len(target_devices)
    )
    
    return {
        "command_id": command.command_id,
        "device_type": command.device_type,
        "command_name": command.command_name,
        "payload": command.payload,
        "status": command.status,
        "created_at": command.created_at.isoformat()
    }

@api_router.get("/state-history/{device_id}")
async def get_state_history(
    device_id: str,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get state history for a device"""
    history = await crud.get_state_history(db, device_id, limit)
    return {
        "device_id": device_id,
        "total": len(history),
        "states": [
            {
                "state_data": s.state_data,
                "timestamp": s.timestamp.isoformat()
            }
            for s in history
        ]
    }

@api_router.get("/command-logs")
async def get_command_logs(
    device_type: str = None,
    status: str = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get command execution logs"""
    if status:
        logs = await crud.get_commands_by_status(db, status, limit)
    elif device_type:
        logs = await crud.get_commands_by_device_type(db, device_type, limit)
    else:
        logs = await crud.get_all_command_logs(db, limit)
    
    return {
        "total": len(logs),
        "logs": [
            {
                "command_id": log.command_id,
                "device_type": log.device_type,
                "command_name": log.command_name,
                "status": log.status,
                "created_at": log.created_at.isoformat(),
                "executed_at": log.executed_at.isoformat() if log.executed_at else None,
                "target_device_count": log.target_device_count,
                "success_count": log.success_count
            }
            for log in logs
        ]
    }

@api_router.get("/device-connection-history/{device_id}")
async def get_connection_history(
    device_id: str,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get connection history for a device"""
    history = await crud.get_device_connection_history(db, device_id, limit)
    return {
        "device_id": device_id,
        "total": len(history),
        "events": [
            {
                "event": h.event,
                "timestamp": h.timestamp.isoformat(),
                "details": h.details
            }
            for h in history
        ]
    }

app.include_router(api_router)
app.include_router(audio_router)

# ================= SERVO CONTROLLER ROUTES (STEP 2) =================

# Import servo routes
from app.devices.routes import router as servo_router
app.include_router(servo_router)

logger.info("Servo controller routes registered")

# ================= DASHBOARD =================

# Mount static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "dashboard", "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(f"Static files mounted from {STATIC_DIR}")

@app.get("/")
async def dashboard():
    """Serve dashboard HTML"""
    dashboard_file = os.path.join(STATIC_DIR, "index.html")
    logger.info(f"Dashboard request - File path: {dashboard_file}, Exists: {os.path.exists(dashboard_file)}")
    if os.path.exists(dashboard_file):
        return FileResponse(
            dashboard_file,
            media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )
    logger.error(f"Dashboard file not found at {dashboard_file}")
    return {"error": "Dashboard not found"}


# Backwards-compatible static asset routes (older cached HTML used /style.css and /app.js)
@app.get("/style.css")
async def style_css():
    css_file = os.path.join(STATIC_DIR, "style.css")
    if os.path.exists(css_file):
        return FileResponse(
            css_file,
            media_type="text/css",
            headers={"Cache-Control": "no-store"},
        )
    return {"error": "style.css not found"}


@app.get("/app.js")
async def app_js():
    js_file = os.path.join(STATIC_DIR, "app.js")
    if os.path.exists(js_file):
        return FileResponse(
            js_file,
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )
    return {"error": "app.js not found"}

# ================= HEALTH =================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/favicon.ico")
async def favicon():
    # Avoid noisy 404s from the dashboard
    return FileResponse(os.path.join(STATIC_DIR, "favicon.ico")) if os.path.exists(os.path.join(STATIC_DIR, "favicon.ico")) else {"ok": True}
