from app.engine.runners.appshark_rules import RULE_GROUPS, resolve_rule_groups

RULE_DIR = "appshark/rules"


def test_unspecified_groups_returns_empty_so_caller_loads_all():
    """未指定规则组时返回空，交由调用方回退到目录下全部规则。

    历史 bug：这里曾返回 RULE_GROUPS 的并集（非空），导致调用方的
    「全部规则」兜底成为死代码，20 条规则里只有 4 条被加载。
    """
    assert resolve_rule_groups(RULE_DIR, None) == []
    assert resolve_rule_groups(RULE_DIR, []) == []


def test_named_group_resolves_to_its_files():
    assert resolve_rule_groups(RULE_DIR, ["privacy_identity"]) == ["api_device_id.json"]


def test_unknown_group_yields_nothing():
    assert resolve_rule_groups(RULE_DIR, ["no_such_group"]) == []


def test_every_group_member_file_exists():
    """规则组引用的文件必须真实存在，否则规则静默不加载。"""
    import os
    missing = [name for names in RULE_GROUPS.values() for name in names
               if not os.path.exists(os.path.join(RULE_DIR, name))]
    assert missing == []
