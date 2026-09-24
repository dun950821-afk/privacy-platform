"""确定性执行 fingerprint。"""
import hashlib
import json


def canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def execution_fingerprint(payload: dict) -> str:
    safe = dict(payload)
    safe.pop("api_key", None)
    safe.pop("secret", None)
    safe.pop("secrets", None)
    return hashlib.sha256(canonical_json(safe).encode()).hexdigest()
