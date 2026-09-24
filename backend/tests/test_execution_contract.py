from app.engine.artifacts import LocalArtifactStore
from app.engine.base import EngineExecutionContext


def test_artifact_store_lifecycle(tmp_path):
    source = tmp_path / "raw.json"
    source.write_text('{"ok":true}')
    store = LocalArtifactStore(tmp_path / "store")
    ref = store.put(source, task_id=1, execution_id=2, artifact_type="raw", content_type="application/json")
    assert store.exists(ref.uri)
    assert store.get(ref.uri).exists()
    assert store.get_download_url(ref.uri) == ref.uri
    store.delete(ref.uri)
    assert not store.exists(ref.uri)


def test_context_has_cancel_token():
    ctx = EngineExecutionContext(1, 2, "mobsf", "4.5.4", "/tmp/a.apk")
    assert not ctx.is_cancelled()
