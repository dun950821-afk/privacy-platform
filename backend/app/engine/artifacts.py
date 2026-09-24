"""可替换的原始结果制品存储。"""
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from shutil import copy2
from urllib.parse import urljoin
import uuid


@dataclass
class ArtifactRef:
    artifact_id: str
    uri: str
    sha256: str
    size: int
    content_type: str
    storage_backend: str = "local"
    metadata: dict = field(default_factory=dict)


class ArtifactStore:
    def put(self, source_path, *, task_id: int, execution_id: int, artifact_type: str, content_type: str) -> ArtifactRef:
        raise NotImplementedError

    def exists(self, uri: str) -> bool:
        raise NotImplementedError

    def get(self, uri: str) -> Path:
        raise NotImplementedError

    def open(self, uri: str, mode="rb"):
        return self.get(uri).open(mode)

    def delete(self, uri: str) -> None:
        path = self.get(uri)
        if path.exists():
            path.unlink()

    def get_download_url(self, uri: str) -> str:
        return uri


class LocalArtifactStore(ArtifactStore):
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, source_path, *, task_id: int, execution_id: int, artifact_type: str, content_type: str) -> ArtifactRef:
        source = Path(source_path)
        digest = sha256(source.read_bytes()).hexdigest()
        artifact_id = uuid.uuid4().hex
        target_dir = self.root / f"task_{task_id}" / f"execution_{execution_id}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{artifact_id}_{source.name}"
        copy2(source, target)
        return ArtifactRef(artifact_id, target.resolve().as_uri(), digest, target.stat().st_size, content_type, metadata={"artifact_type": artifact_type})

    def exists(self, uri: str) -> bool:
        return Path(uri.removeprefix("file://")).exists()

    def get(self, uri: str) -> Path:
        return Path(uri.removeprefix("file://"))
