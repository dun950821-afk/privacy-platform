"""统一响应模型"""
from typing import Any, Optional, Generic, TypeVar
from pydantic import BaseModel


T = TypeVar("T")


class ResponseBase(BaseModel):
    code: int = 0
    message: str = "success"
    request_id: Optional[str] = None


class ResponseData(ResponseBase):
    data: Any = None


class PageData(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


class ResponsePage(ResponseBase):
    data: PageData


def success(data: Any = None, request_id: str = None) -> dict:
    return {"code": 0, "message": "success", "data": data, "request_id": request_id}


def error(code: int = 50001, message: str = "error", request_id: str = None) -> dict:
    return {"code": code, "message": message, "data": None, "request_id": request_id}


def page(items: list, total: int, page: int, page_size: int, request_id: str = None) -> dict:
    return {
        "code": 0, "message": "success", "request_id": request_id,
        "data": {"items": items, "total": total, "page": page, "page_size": page_size}
    }
