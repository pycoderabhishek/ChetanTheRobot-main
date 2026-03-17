"""Dashboard Routes - Serve HTML dashboard and API endpoints"""

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os

router = APIRouter()

# Get the directory of this file
DASHBOARD_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DASHBOARD_DIR, "static")


@router.get("/", tags=["Dashboard"])
async def serve_dashboard():
    """Serve the main dashboard HTML"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), media_type="text/html")


@router.get("/dashboard", tags=["Dashboard"])
async def redirect_dashboard():
    """Redirect /dashboard to /"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), media_type="text/html")
