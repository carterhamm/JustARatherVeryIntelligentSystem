"""API v1 — aggregate router that includes all sub-routers."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.voice import router as voice_router
from app.api.v1.vision import router as vision_router
from app.api.v1.mcp import router as mcp_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.data_import import router as data_import_router
from app.api.v1.smart_home import router as smart_home_router
from app.api.v1.twilio_routes import router as twilio_router
from app.api.v1.cron import router as cron_router
from app.api.v1.google_oauth import router as google_oauth_router
from app.api.v1.vnc import router as vnc_router
from app.api.v1.widgets import router as widgets_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.health import router as health_router
from app.api.v1.focus import router as focus_router
from app.api.v1.habits import router as habits_router
from app.api.v1.landmarks import router as landmarks_router

v1_router = APIRouter()
v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
v1_router.include_router(chat_router, tags=["chat"])
v1_router.include_router(voice_router, tags=["voice"])
v1_router.include_router(vision_router, tags=["vision"])
v1_router.include_router(mcp_router, tags=["MCP"])
v1_router.include_router(knowledge_router, tags=["knowledge"])
v1_router.include_router(data_import_router, tags=["Data Import"])
v1_router.include_router(smart_home_router, tags=["smart-home"])
v1_router.include_router(twilio_router, tags=["Twilio"])
v1_router.include_router(cron_router, tags=["Cron"])
v1_router.include_router(google_oauth_router, tags=["Google OAuth"])
v1_router.include_router(vnc_router, tags=["VNC"])
v1_router.include_router(widgets_router, tags=["Widgets"])
v1_router.include_router(contacts_router, prefix="/contacts", tags=["Contacts"])
v1_router.include_router(health_router, prefix="/health", tags=["Health"])
v1_router.include_router(focus_router, prefix="/focus", tags=["Focus Sessions"])
v1_router.include_router(habits_router, prefix="/habits", tags=["Habits"])
v1_router.include_router(landmarks_router, prefix="/landmarks", tags=["Landmarks"])
