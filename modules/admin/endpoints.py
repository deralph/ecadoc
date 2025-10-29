"""Admin API endpoints"""
from fastapi import APIRouter, HTTPException

from modules.admin.service import admin_metrics_service


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics/overview")
def metrics_overview(range: str = "30d"):
    """Return the dataset used by the admin dashboard graphs"""
    try:
        return admin_metrics_service.get_overview(range)
    except Exception as exc:  # pragma: no cover - defensive logging only
        raise HTTPException(status_code=500, detail=str(exc))
