"""认证路由"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.models import User
from app.schemas import LoginRequest, RefreshRequest
from app.api.deps import get_current_user, get_request_id

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="账号已禁用")
    
    access = create_access_token(user.username, user.role)
    refresh = create_refresh_token(user.username)
    
    from datetime import datetime, timezone
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "code": 0, "request_id": get_request_id(request),
        "data": {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": 3600,
            "user": {
                "id": user.id, "username": user.username,
                "role": user.role, "full_name": user.full_name,
                "email": user.email
            }
        }
    }


@router.post("/refresh")
def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token无效")
    
    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    access = create_access_token(user.username, user.role)
    return {"code": 0, "data": {"access_token": access, "token_type": "bearer", "expires_in": 3600}}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"code": 0, "data": {
        "id": user.id, "username": user.username, "role": user.role,
        "full_name": user.full_name, "email": user.email, "phone": user.phone
    }}


@router.post("/logout")
def logout():
    return {"code": 0, "message": "已登出"}
