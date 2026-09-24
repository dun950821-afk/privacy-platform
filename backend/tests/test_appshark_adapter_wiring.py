import asyncio
from types import SimpleNamespace

from app.engine.adapters.appshark import AppSharkAdapter

RULE_DIR = "/home/user/privacy-platform/backend/appshark/rules"


def _context(tmp_path, **config):
    return SimpleNamespace(task_id=1, apk_path=str(tmp_path / "app.apk"),
                           package_name="com.example", rule_pack_version="1.0", config=config)


def test_adapter_honors_rule_groups(tmp_path):
    (tmp_path / "app.apk").write_bytes(b"stub")
    adapter = AppSharkAdapter({
        "java_path": "/bin/true", "jar_path": "/bin/true", "home_path": str(tmp_path),
        "rule_dir": RULE_DIR, "sdk_path": RULE_DIR,
    })
    result = asyncio.run(adapter.execute(_context(tmp_path, rule_groups=["privacy_identity"])))
    assert result.success is True
    config_path = f"/tmp/appshark_cfg_1.json5"
    import json
    with open(config_path) as f:
        generated = json.load(f)
    assert generated["rules"] == "api_device_id.json"


def test_adapter_uses_executor_logs(tmp_path):
    (tmp_path / "app.apk").write_bytes(b"stub")
    adapter = AppSharkAdapter({
        "java_path": "/bin/true", "jar_path": "/bin/true", "home_path": str(tmp_path),
        "rule_dir": RULE_DIR, "sdk_path": RULE_DIR,
    })
    result = asyncio.run(adapter.execute(_context(tmp_path)))
    assert result.success is True
    assert result.stage_events == ["appshark_preparing", "appshark_analyzing", "appshark_persisting"]
