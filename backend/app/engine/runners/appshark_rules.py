"""AppShark 平台规则组到已验证规则文件的映射。"""
from pathlib import Path
from hashlib import sha256

RULE_GROUPS = {
    "privacy_identity": ["api_device_id.json"],
    "privacy_location": ["location_to_network.json"],
    "privacy_network": ["device_id_to_network.json", "location_to_network.json"],
    "privacy_camera_microphone": ["api_camera_mic.json"],
}


def resolve_rule_groups(rule_dir: str, groups: list[str] | None) -> list[str]:
    groups = groups or list(RULE_GROUPS)
    result = []
    for group in groups:
        for name in RULE_GROUPS.get(group, []):
            path = Path(rule_dir) / name
            if path.exists() and name not in result:
                result.append(name)
    return result


def rule_pack_hash(rule_dir: str, rules: list[str]) -> str:
    digest = sha256()
    for name in sorted(rules):
        digest.update(name.encode())
        digest.update((Path(rule_dir) / name).read_bytes())
    return digest.hexdigest()
