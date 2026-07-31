"""应用配置"""
import os
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "App个人信息保护检测与治理平台"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    SECRET_KEY: str = "privacy-platform-secret-key-change-in-production-2026"
    API_PREFIX: str = "/api/v1"
    AGENT_PREFIX: str = "/agent/v1"

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://privacy:privacy123@localhost:5432/privacy_platform"
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str = "jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Storage
    STORAGE_ROOT: str = "/home/user/privacy-platform/data/evidence"
    STORAGE_MAX_FILE_SIZE: int = 2 * 1024 * 1024 * 1024  # 2GB
    APK_MAX_SIZE: int = 500 * 1024 * 1024  # 500MB MVP

    # Task
    TASK_STATIC_TIMEOUT: int = 1800  # 30min
    TASK_DYNAMIC_TIMEOUT: int = 3600  # 60min
    TASK_MAX_RETRIES: int = 2
    AGENT_HEARTBEAT_INTERVAL: int = 15  # seconds

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure storage directory exists
Path(settings.STORAGE_ROOT).mkdir(parents=True, exist_ok=True)
