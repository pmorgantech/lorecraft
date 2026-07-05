"""Admin REST API router — mounts per-resource routers under a shared prefix."""

from __future__ import annotations

from fastapi import APIRouter

from lorecraft.webui.admin.auth import auth_router
from lorecraft.webui.admin.routers.accounts import router as accounts_router
from lorecraft.webui.admin.routers.analytics import router as analytics_router
from lorecraft.webui.admin.routers.audit import router as audit_router
from lorecraft.webui.admin.routers.clock import router as clock_router
from lorecraft.webui.admin.routers.help import router as help_router
from lorecraft.webui.admin.routers.issues import router as issues_router
from lorecraft.webui.admin.routers.news import router as news_router
from lorecraft.webui.admin.routers.players import router as players_router
from lorecraft.webui.admin.routers.world import router as world_router

admin_router = APIRouter(tags=["admin"])
admin_router.include_router(auth_router)
admin_router.include_router(players_router)
admin_router.include_router(audit_router)
admin_router.include_router(world_router)
admin_router.include_router(clock_router)
admin_router.include_router(accounts_router)
admin_router.include_router(issues_router)
admin_router.include_router(news_router)
admin_router.include_router(help_router)
admin_router.include_router(analytics_router)
