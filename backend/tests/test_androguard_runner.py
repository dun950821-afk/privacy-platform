from app.engine.adapters.androguard import AndroguardAdapter
from app.engine.runners.androguard_runner import collect_facts


def test_collect_facts_has_facts_schema(sample_apk):
    facts = collect_facts(sample_apk)
    assert facts["schema_version"] == "1.0"
    assert facts["basic_info"]["package_name"]
    assert "activities" in facts["components"]
    assert "declared" in facts["permissions"]


def test_adapter_reads_the_permission_key_the_runner_actually_writes():
    """runner 写 `declared`，适配器曾读 `dangerous` —— 这个键从来不存在。

    两者只差一个字符串，没有类型检查、没有报错、没有日志：声明权限被静默丢弃，
    表现为「权限知识库里只有 AppShark 报的那几条」。上面那条契约测试
    （`assert "declared" in facts["permissions"]`）就是 runner 侧的真相。

    这里用 runner 的真实字段名构造输入，锁住两边不会再走偏。
    """
    facts = {
        "permissions": {
            "declared": ["android.permission.CALL_PHONE", "android.permission.VIBRATE"],
            "sensitive_matched": [{"category": "LOCATION", "permission": "ACCESS_FINE_LOCATION"}],
        },
        "components": {},
    }
    events = AndroguardAdapter({}).normalize_events(facts)
    perms = {e["api"] for e in events if e["event_type"] == "static_permission"}
    assert perms == {"android.permission.CALL_PHONE", "android.permission.VIBRATE"}, \
        "声明权限必须真的变成事件；为空说明又读错了键名"
    sensitive = {e["api"] for e in events if e["event_type"] == "static_sensitive_permission"}
    assert sensitive == {"ACCESS_FINE_LOCATION"}


def test_execute_returns_raw_sections_for_worker_to_persist(monkeypatch):
    """适配器要把原始结果拆段带上，供 worker 落 `engine_raw_sections`。

    锁的是**接线**：`execute()` 真的把 raw_sections 填进 AdapterResult。
    拆段规则本身由 tests/test_raw_section_service.py 覆盖。

    这几段正是历史上被整段丢弃的——`endpoints` 里含隐私政策 URL。
    """
    import asyncio
    import json as _json
    from app.engine.adapters import androguard as mod
    from app.engine.base import TaskContext

    facts = {
        "schema_version": "1.0",
        "basic_info": {"package_name": "com.example", "app_name": "Demo"},
        "permissions": {"declared": ["android.permission.CAMERA"], "sensitive_matched": []},
        "components": {"activities": ["com.example.MainActivity"]},
        "certificate": {"subject": "CN=Demo", "issuer": "CN=Demo", "serial": "1"},
        "endpoints": {"urls": ["https://mbank.example.com/PrivacyC.html"], "domains": [], "ips": []},
        "sensitive_apis": [{"category": "device_id", "api": "getDeviceId"}],
        "native_libraries": [],
        "stats": {},
    }

    def fake_run_in_process(apk_path, raw_path, **kwargs):
        with open(raw_path, "w") as f:
            _json.dump(facts, f)
        return facts

    monkeypatch.setattr(mod, "run_in_process", fake_run_in_process)

    ctx = TaskContext(task_id=1, apk_path="/nonexistent.apk",
                      package_name="com.example", rule_pack_version="1")
    result = asyncio.run(AndroguardAdapter({}).execute(ctx))

    assert result.success
    rows = {s["path"]: s for s in result.raw_sections}
    # endpoints 的子项全是 list，所以它自己不占行，由 endpoints.urls 等承载
    for want in ("endpoints.urls", "endpoints.domains", "certificate", "sensitive_apis"):
        assert want in rows, f"execute() 没带上 {want}，worker 就落不了这一段"
    assert rows["endpoints.urls"]["payload"] == ["https://mbank.example.com/PrivacyC.html"]


def test_collect_facts_rejects_missing_file(tmp_path):
    import pytest
    with pytest.raises(Exception):
        collect_facts(str(tmp_path / "missing.apk"))
