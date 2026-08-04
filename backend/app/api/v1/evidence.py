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
    """证据预览: 图片直接返回文件流, 文本类返回内容, 其他返回不支持"""
    IMAGE_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
    TEXT_EXTS = {".json", ".txt", ".log", ".xml", ".md", ".csv",
                 ".yaml", ".yml", ".html", ".htm", ".java", ".smali"}
    MAX_TEXT_SIZE = 512 * 1024  # 512KB

    e = db.query(Evidence).get(eid)
    if not e:
        raise HTTPException(status_code=404, detail="证据不存在")
    if not e.artifact_path or not Path(e.artifact_path).exists():
        raise HTTPException(status_code=404, detail="证据文件不存在")

    path = Path(e.artifact_path)
    ext = path.suffix.lower()

    if ext in IMAGE_EXTS:
        return FileResponse(str(path), media_type=IMAGE_EXTS[ext])

    if ext in TEXT_EXTS or e.evidence_type in ("engine_output", "log_file", "api_call_stack"):
        size = path.stat().st_size
        truncated = size > MAX_TEXT_SIZE
        with open(path, "rb") as f:
            raw = f.read(MAX_TEXT_SIZE)
        content = raw.decode("utf-8", errors="replace")
        return {"code": 0, "data": {
            "kind": "text", "content": content, "truncated": truncated,
            "filename": path.name, "size": size,
        }}

    return {"code": 0, "data": {"kind": "unsupported", "filename": path.name}}
