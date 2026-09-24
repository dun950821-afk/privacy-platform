"""V1.0 版本化多引擎任务配置。"""
from copy import deepcopy
from hashlib import sha256
import json

ENGINE_KEYS = ("androguard", "appshark", "mobsf")
SECRET_KEYS = {"api_key", "token", "password", "authorization", "secret"}


def normalize_task_config(config: dict | None) -> dict:
    config = deepcopy(config or {})
    static = config.get("static") or {}
    engines = static.get("engines")
    if engines is None:
        legacy = config.get("engines")
        if legacy is not None:
            engines = {name: {"enabled": True, "config": {}} for name in legacy if name in ENGINE_KEYS}
        else:
            engines = {name: {"enabled": True, "config": {}} for name in ENGINE_KEYS}
    elif isinstance(engines, list):
        engines = {name: {"enabled": True, "config": {}} for name in engines if name in ENGINE_KEYS}
    config["schema_version"] = "1.0"
    config["static"] = {"engines": engines}
    config["dynamic"] = config.get("dynamic") or {
        "enabled": bool(config.get("dynamic_scenarios")),
        "scenarios": config.get("dynamic_scenarios") or [],
    }
    config.pop("engines", None)
    config.pop("dynamic_scenarios", None)
    return config


def enabled_engine_types(config: dict | None, registry_types=ENGINE_KEYS) -> list[str]:
    normalized = normalize_task_config(config)
    engines = normalized.get("static", {}).get("engines", {})
    return [name for name in registry_types if engines.get(name, {}).get("enabled", False)]


def resolved_task_config(config: dict | None, defaults: dict | None = None) -> dict:
    resolved = normalize_task_config(config)
    for name, default in (defaults or {}).items():
        current = resolved["static"]["engines"].setdefault(name, {"enabled": False, "config": {}})
        values = dict(default.get("config", {}))
        values.update(current.get("config", {}))
        current["config"] = values
    return resolved


def redact_task_config(config: dict | None) -> dict:
    def clean(value, key=""):
        if isinstance(value, dict):
            return {k: ("********" if any(secret in k.lower() for secret in SECRET_KEYS) else clean(v, k)) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v, key) for v in value]
        return value
    return clean(normalize_task_config(config))


def task_config_hash(config: dict | None) -> str:
    canonical = json.dumps(redact_task_config(config), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(canonical.encode()).hexdigest()
