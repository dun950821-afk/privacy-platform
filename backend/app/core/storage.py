"""文件存储服务 - MVP使用本地文件系统"""
import os
import hashlib
import shutil
from pathlib import Path
from fastapi import UploadFile
from app.core.config import settings


class StorageService:
    """本地文件存储服务"""

    def __init__(self, root: str = None):
        self.root = Path(root or settings.STORAGE_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    def _task_dir(self, task_id: int, subdir: str = "") -> Path:
        d = self.root / f"task_{task_id}" / subdir
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _general_dir(self, subdir: str) -> Path:
        d = self.root / subdir
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def save_upload(self, upload_file: UploadFile, task_id: int = None,
                          subdir: str = "uploads") -> dict:
        """保存上传文件，返回路径和哈希"""
        if task_id:
            dest_dir = self._task_dir(task_id, subdir)
        else:
            dest_dir = self._general_dir(subdir)

        filename = upload_file.filename or "unnamed"
        # 防路径穿越
        filename = os.path.basename(filename)
        dest_path = dest_dir / filename

        # 如果文件已存在，添加后缀
        if dest_path.exists():
            stem, ext = os.path.splitext(filename)
            dest_path = dest_dir / f"{stem}_{os.urandom(4).hex()}{ext}"

        sha256 = hashlib.sha256()
        size = 0

        with open(dest_path, "wb") as f:
            while chunk := await upload_file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)
                sha256.update(chunk)
                size += len(chunk)

        return {
            "path": str(dest_path),
            "hash": sha256.hexdigest(),
            "size": size,
            "filename": filename,
        }

    def save_bytes(self, data: bytes, task_id: int, subdir: str, filename: str) -> dict:
        dest_dir = self._task_dir(task_id, subdir)
        filename = os.path.basename(filename)
        dest_path = dest_dir / filename

        sha256 = hashlib.sha256(data).hexdigest()

        with open(dest_path, "wb") as f:
            f.write(data)

        return {
            "path": str(dest_path),
            "hash": sha256,
            "size": len(data),
            "filename": filename,
        }

    def save_text(self, text: str, task_id: int, subdir: str, filename: str) -> str:
        """保存文本文件，返回路径"""
        dest_dir = self._task_dir(task_id, subdir)
        filename = os.path.basename(filename)
        dest_path = dest_dir / filename
        dest_path.write_text(text, encoding="utf-8")
        return str(dest_path)

    def get_file_path(self, relative_path: str) -> Path:
        """安全获取文件路径，防止路径穿越"""
        full = self.root / relative_path
        # 确保在根目录内
        try:
            full.resolve().relative_to(self.root.resolve())
        except ValueError:
            raise ValueError("Invalid path")
        return full

    def file_exists(self, path: str) -> bool:
        return Path(path).exists()

    def delete_file(self, path: str) -> bool:
        try:
            Path(path).unlink()
            return True
        except FileNotFoundError:
            return False

    def compute_hash(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                sha256.update(chunk)
        return sha256.hexdigest()


storage = StorageService()
