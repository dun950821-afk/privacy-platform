"""安全: JWT、密码哈希、权限检查"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, role: str, extra: dict = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire, "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def generate_request_id() -> str:
    return f"req_{secrets.token_hex(12)}"


def generate_uid(prefix: str = "obj") -> str:
    """生成ULID风格的唯一ID"""
    import time
    ts = int(time.time() * 1000)
    rand = secrets.token_hex(8)
    return f"{prefix}_{ts:013x}{rand}"


# Role permissions
ROLE_PERMISSIONS = {
    "platform_admin": {"*": True},
    "rule_admin": {
        "rule:read", "rule:write", "rule:publish", "sdk:read", "sdk:write",
        "permission:read", "permission:write",
        "project:read", "app:read", "task:read", "finding:read",
    },
    "project_owner": {
        "project:read", "project:write",
        "app:read", "app:write", "app:upload",
        "task:read", "task:write", "task:submit",
        "finding:read", "finding:write", "finding:assign",
        "evidence:read", "evidence:download",
        "report:read", "report:generate",
        "sdk:read", "rule:read", "permission:read",
    },
    "tester": {
        "project:read", "app:read", "app:upload",
        "task:read", "task:write", "task:submit",
        "finding:read", "finding:write",
        "evidence:read", "evidence:download",
        "report:read", "report:generate",
        "sdk:read", "rule:read", "permission:read",
    },
    "developer": {
        "project:read", "app:read",
        "task:read",
        "finding:read", "finding:remediate",
        "evidence:read",
        "report:read",
        "sdk:read", "rule:read", "permission:read",
    },
    "compliance": {
        "project:read", "app:read",
        "task:read",
        "finding:read",
        "evidence:read", "evidence:download",
        "report:read", "report:generate",
        "sdk:read", "rule:read", "permission:read",
    },
    "auditor": {
        "project:read", "app:read",
        "task:read",
        "finding:read",
        "report:read",
        "sdk:read", "rule:read", "permission:read",
        "system:audit:read", "engine:read", "engine:health-check",
    },
}


def has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, {})
    return perms.get("*", False) or permission in perms
