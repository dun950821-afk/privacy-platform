"""证据路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse
from app.core.database import get_db
from app.models import Evidence, User
from app.api.deps import get_current_user, require_permission
from pathlib import Path

router = APIRouter(prefix="/evidence", tags=["证据管理"])


@router.get("/{eid}")
def get_evidence(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = db.query(Evidence).get(eid)
    if not e:
        raise HTTPException(status_code=404, detail="证据不存在")
    return {"code": 0, "data": {
        "id": e.id, "evidence_uid": e.evidence_uid, "evidence_type": e.evidence_type,
        "artifact_hash": e.artifact_hash, "artifact_size": e.artifact_size,
        "metadata_json": e.metadata_json, "created_at": str(e.created_at),
        "task_id": e.task_id
    }}


@router.get("/{eid}/download")
def download_evidence(eid: int, user: User = Depends(require_permission("evidence:download")),
                      db: Session = Depends(get_db)):
    e = db.query(Evidence).get(eid)
    if not e:
        raise HTTPException(status_code=404, detail="证据不存在")
    if not e.artifact_path or not Path(e.artifact_path).exists():
        raise HTTPException(status_code=404, detail="证据文件不存在")
    return FileResponse(e.artifact_path, filename=Path(e.artifact_path).name)


@router.get("/{eid}/preview")
def preview_evidence(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = db.query(Evidence).get(eid)
    if not e:
        raise HTTPException(status_code=404, detail="证据不存在")
    if e.evidence_type == "screenshot" and e.artifact_path and Path(e.artifact_path).exists():
        return FileResponse(e.artifact_path, media_type="image/png")
    return {"code": 0, "data": {"metadata": e.metadata_json}}
