"""AppShark 规则文件管理路由

规则以 JSON 文件存放在规则目录(默认 backend/appshark/rules, 可用 APPSHARK_RULE_DIR 覆盖),
AppShark 引擎运行时加载目录下全部 *.json。禁用规则 = 重命名为 *.json.disabled。
"""
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, require_permission
from app.models import User
from app.engine.adapters.appshark import APPSHARK_RULE_DIR

router = APIRouter(prefix="/appshark-rules", tags=["AppShark规则"])

RULE_DIR = Path(APPSHARK_RULE_DIR)
# 文件名白名单：字母(含大写)/数字/下划线/连字符 + .json 结尾。
# **必须容纳规则库里已有的名字**：上游规则的命名是 ContentProviderPathTraversal.json、
# unZipSlip.json 这种驼峰，早先只允许小写，于是那批文件在界面上根本打不开
# （读取即 400「文件名不合法」）。防路径穿越靠下面的 resolve/parent 校验，不靠这里的大小写。
FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.json$")
FILENAME_HINT = "文件名只能用字母/数字/下划线/连字符，且以 .json 结尾"


class RuleFileIn(BaseModel):
    filename: str
    content: dict


def _rule_mode(rule: dict) -> str:
    if rule.get("APIMode"):
        return "APIMode"
    if rule.get("SliceMode"):
        return "SliceMode"
    if rule.get("DirectMode"):
        return "DirectMode"
    return "-"


def _summarize(path: Path) -> dict:
    """解析规则文件, 返回文件级摘要"""
    try:
        with open(path) as f:
            content = json.load(f)
    except Exception as e:
        return {"filename": path.name, "enabled": path.suffix == ".json",
                "rule_count": 0, "rules": [], "parse_error": str(e)}
    rules = []
    for key, r in content.items():
        if not isinstance(r, dict):
            continue
        desc = r.get("desc") or {}
        source = r.get("source") or {}
        sink = r.get("sink") or {}
        source_count = sum(len(v) for v in source.values() if isinstance(v, list))
        rules.append({
            "key": key,
            "name": desc.get("name") or key,
            "mode": _rule_mode(r),
            "detail": desc.get("detail") or "",
            "category": desc.get("complianceCategory") or desc.get("category") or "",
            "category_detail": desc.get("complianceCategoryDetail") or "",
            "level": str(desc.get("level") or ""),
            "source_count": source_count,
            "sink_count": len(sink),
        })
    return {"filename": path.name, "enabled": path.suffix == ".json",
            "rule_count": len(rules), "rules": rules}


def _safe_path(filename: str) -> Path:
    """校验文件名(防路径穿越), 返回完整路径"""
    base = filename[:-len(".disabled")] if filename.endswith(".disabled") else filename
    if not FILENAME_RE.match(base):
        raise HTTPException(status_code=400, detail=FILENAME_HINT)
    path = (RULE_DIR / filename).resolve()
    if path.parent != RULE_DIR.resolve():
        raise HTTPException(status_code=400, detail=FILENAME_HINT)
    return path


def _validate_content(content) -> None:
    if not isinstance(content, dict) or not content:
        raise HTTPException(status_code=400, detail="规则内容必须是非空 JSON 对象")
    for key, r in content.items():
        if not isinstance(r, dict):
            raise HTTPException(status_code=400, detail=f"规则 {key} 必须是对象")
        desc = r.get("desc")
        if not isinstance(desc, dict) or not desc.get("name"):
            raise HTTPException(status_code=400, detail=f"规则 {key} 缺少 desc.name")
        if not isinstance(r.get("sink"), dict) or not r["sink"]:
            raise HTTPException(status_code=400, detail=f"规则 {key} 缺少 sink 定义")


@router.get("")
def list_rule_files(user: User = Depends(get_current_user)):
    """规则文件列表(含禁用), 每个文件内逐条规则的摘要"""
    items = [_summarize(p) for p in sorted(RULE_DIR.glob("*.json"))]
    items += [_summarize(p) for p in sorted(RULE_DIR.glob("*.json.disabled"))]
    return {"code": 0, "data": items}


@router.get("/{filename}")
def get_rule_file(filename: str, user: User = Depends(get_current_user)):
    path = _safe_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="规则文件不存在")
    try:
        with open(path) as f:
            content = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"规则文件解析失败: {e}")
    return {"code": 0, "data": {
        "filename": path.name, "enabled": path.suffix == ".json", "content": content}}


@router.post("")
def create_rule_file(req: RuleFileIn, user: User = Depends(require_permission("rule:write"))):
    path = _safe_path(req.filename)
    if not req.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="新规则文件必须以 .json 结尾")
    if path.exists() or Path(str(path) + ".disabled").exists():
        raise HTTPException(status_code=400, detail="同名规则文件已存在")
    _validate_content(req.content)
    RULE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(req.content, f, ensure_ascii=False, indent=2)
    return {"code": 0, "data": {"filename": req.filename}}


@router.put("/{filename}")
def update_rule_file(filename: str, req: RuleFileIn,
                     user: User = Depends(require_permission("rule:write"))):
    path = _safe_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="规则文件不存在")
    _validate_content(req.content)
    with open(path, "w") as f:
        json.dump(req.content, f, ensure_ascii=False, indent=2)
    return {"code": 0, "data": {"filename": path.name}}


@router.delete("/{filename}")
def delete_rule_file(filename: str, user: User = Depends(require_permission("rule:write"))):
    path = _safe_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="规则文件不存在")
    path.unlink()
    return {"code": 0, "data": {"filename": path.name}}


@router.post("/{filename}/toggle")
def toggle_rule_file(filename: str, user: User = Depends(require_permission("rule:write"))):
    """启用/禁用: .json <-> .json.disabled"""
    path = _safe_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="规则文件不存在")
    if path.suffix == ".json":
        target = Path(str(path) + ".disabled")
    else:
        target = Path(str(path)[:-len(".disabled")])
    if target.exists():
        raise HTTPException(status_code=400, detail="目标文件已存在, 无法切换状态")
    path.rename(target)
    return {"code": 0, "data": {"filename": target.name, "enabled": target.suffix == ".json"}}
