"""AppShark 平台规则组到已验证规则文件的映射。"""
from pathlib import Path
from hashlib import sha256

RULE_GROUPS = {
    "privacy_identity": ["api_device_id.json"],
    "privacy_location": ["location_to_network.json"],
    "privacy_network": ["device_id_to_network.json", "location_to_network.json"],
    # 原 api_camera_mic.json 拆成两条：能确证是摄像头的（Camera.open）与不能确证的
    # （MediaRecorder 的音源/视频源是通配参数，AudioRecord 的音源在构造时决定）。
    # 组名不改，仍是「相机与麦克风」这个覆盖范围。
    "privacy_camera_microphone": ["api_camera.json", "api_media.json"],
}


def resolve_rule_groups(rule_dir: str, groups: list[str] | None) -> list[str]:
    """把平台规则组解析为规则文件列表。

    未指定规则组时返回空列表，由调用方回退到「目录下全部规则」。
    这里不能默认返回 RULE_GROUPS 的并集——那会让调用方的兜底成为死代码，
    使规则目录里未被任何组引用的规则（含官方安全规则）永不加载。
    """
    if not groups:
        return []
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
