from app.services.task_config import enabled_engine_types, normalize_task_config, redact_task_config, task_config_hash


def test_new_engine_map_schema():
    config = {"static": {"engines": {"androguard": {"enabled": True, "config": {}}, "appshark": {"enabled": False, "config": {}}, "mobsf": {"enabled": True, "config": {}}}}}
    assert enabled_engine_types(config) == ["androguard", "mobsf"]


def test_legacy_array_compatibility():
    assert enabled_engine_types({"engines": ["androguard", "mobsf"]}) == ["androguard", "mobsf"]


def test_redaction_and_hash_ignore_secret_value():
    a = {"engines": ["mobsf"], "api_key": "one"}
    b = {"engines": ["mobsf"], "api_key": "two"}
    assert "one" not in str(redact_task_config(a))
    assert task_config_hash(a) == task_config_hash(b)
