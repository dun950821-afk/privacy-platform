"""FastAPI依赖注入"""
from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token, has_permission, generate_request_id
from app.models import User


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """从JWT获取当前用户"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未认证")
    
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token无效或已过期")
    
    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    
    return user


def require_permission(permission: str):
    """权限检查依赖工厂"""
    def checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(status_code=403, detail=f"无权限: {permission}")
        return user
    return checker


def get_request_id(request: Request) -> str:
    """获取或生成请求ID"""
    return request.headers.get("X-Request-ID") or generate_request_id()
