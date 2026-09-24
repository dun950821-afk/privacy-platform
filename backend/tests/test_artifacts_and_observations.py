from app.engine.artifacts import LocalArtifactStore
from app.engine.fingerprint import execution_fingerprint


def test_fingerprint_order_and_scope():
    a = {"engine_type": "mobsf", "config": {"scan_timeout": 300}, "cache_scope": "project:1"}
    b = {"cache_scope": "project:1", "config": {"scan_timeout": 300}, "engine_type": "mobsf"}
    assert execution_fingerprint(a) == execution_fingerprint(b)
    b["cache_scope"] = "project:2"
    assert execution_fingerprint(a) != execution_fingerprint(b)


def test_artifact_store_hash(tmp_path):
    src = tmp_path / "result.json"
    src.write_text('{"ok":true}')
    ref = LocalArtifactStore(tmp_path / "store").put(src, task_id=1, execution_id=2, artifact_type="raw_result", content_type="application/json")
    assert ref.sha256 and ref.size == src.stat().st_size and ref.storage_backend == "local"
