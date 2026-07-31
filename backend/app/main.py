"""FastAPI应用入口"""
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.api.v1 import api_router
from app.api.agent.v1 import router as agent_router
from app.api.deps import get_request_id

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="App个人信息保护检测与治理平台 API",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """为每个请求添加request_id"""
    response = await call_next(request)
    response.headers["X-Request-ID"] = get_request_id(request)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = logging.getLogger(__name__)
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 50001, "message": f"服务器内部错误: {str(exc)}",
                 "data": None, "request_id": get_request_id(request)}
    )


# 健康检查
@app.get("/health")
def health():
    return {"status": "ok", "version": settings.APP_VERSION}


# 注册路由
app.include_router(api_router, prefix=settings.API_PREFIX)
app.include_router(agent_router, prefix=settings.AGENT_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
