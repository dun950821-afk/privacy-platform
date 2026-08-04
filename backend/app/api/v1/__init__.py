"""API v1 路由聚合"""
from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.projects import router as projects_router
from app.api.v1.apps import router as apps_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.findings import router as findings_router
from app.api.v1.rules import router as rules_router
from app.api.v1.sdks import router as sdks_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.reports import router as reports_router
from app.api.v1.system import router as system_router
from app.api.v1.engines import router as engines_router
from app.api.v1.appshark_rules import router as appshark_rules_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(apps_router)
api_router.include_router(tasks_router)
api_router.include_router(findings_router)
api_router.include_router(rules_router)
api_router.include_router(sdks_router)
api_router.include_router(evidence_router)
api_router.include_router(reports_router)
api_router.include_router(system_router)
api_router.include_router(engines_router)
api_router.include_router(appshark_rules_router)
