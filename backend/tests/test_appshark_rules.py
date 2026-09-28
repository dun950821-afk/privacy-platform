from app.engine.runners.appshark_rules import resolve_rule_groups, rule_pack_hash

RULE_DIR = "/home/user/privacy-platform/backend/appshark/rules"


def test_resolve_rule_groups_returns_existing_rules():
    rules = resolve_rule_groups(RULE_DIR, ["privacy_identity"])
    assert rules == ["api_device_id.json"]


def test_unknown_group_returns_empty():
    assert resolve_rule_groups(RULE_DIR, ["no_such_group"]) == []


def test_rule_pack_hash_changes_with_selection():
    a = rule_pack_hash(RULE_DIR, ["api_device_id.json"])
    b = rule_pack_hash(RULE_DIR, ["api_device_id.json", "api_media.json"])
    assert a != b


def test_camera_microphone_group_covers_both_files():
    """相机与麦克风组由两条规则承载（G2 拆分），两条都要在组里。"""
    rules = resolve_rule_groups(RULE_DIR, ["privacy_camera_microphone"])
    assert rules == ["api_camera.json", "api_media.json"]
