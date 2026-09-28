"""AppShark 规则文件管理接口的文件名校验。

线上故障（2026-09-28）：规则文件名的白名单只允许小写，而规则库里**有 6 个上游命名的
文件是驼峰**（`ContentProviderPathTraversal.json`、`unZipSlip.json` …）。于是那批规则在
界面上一打开就是 400「文件名不合法」——校验器比自己发布的规则库还严。

教训是「白名单必须以真实数据为准」，所以下面第一条断言直接对着规则目录跑，
而不是构造几个字符串试。
"""
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v1.appshark_rules import RULE_DIR, _safe_path

REAL_RULE_NAMES = sorted(p.name for p in RULE_DIR.glob("*.json"))


def test_every_shipped_rule_file_passes_the_validator():
    """校验器必须放行规则库里的每一个文件。

    这条断言会跟着规则目录一起长：以后新增规则文件若名字不合规，测试当场失败，
    而不是等用户在界面上点开才发现打不开。
    """
    assert REAL_RULE_NAMES, "规则目录为空，断言失去意义"
    for name in REAL_RULE_NAMES:
        _safe_path(name)  # 不抛异常即为通过


def test_upstream_camel_case_names_are_accepted():
    """上游命名的驼峰文件必须能打开——这正是报障的那些。"""
    camel = [n for n in REAL_RULE_NAMES if any(c.isupper() for c in n)]
    assert camel, "规则库里应当存在上游命名的驼峰文件，否则这条断言无意义"
    for name in camel:
        assert _safe_path(name).name == name


@pytest.mark.parametrize("name", [
    "../../etc/passwd",
    "../rules/api_device_id.json",
    "sub/api_device_id.json",
    "api_device_id.txt",       # 非 .json
    "api device id.json",      # 含空格
    "api;rm -rf.json",         # 含 shell 元字符
    "",
])
def test_traversal_and_bad_names_are_rejected(name):
    """放开大小写不等于放开路径：穿越与非白名单字符仍要挡住。"""
    with pytest.raises(HTTPException) as exc:
        _safe_path(name)
    assert exc.value.status_code == 400


def test_disabled_suffix_is_allowed():
    """禁用规则靠重命名成 .json.disabled 实现，这个形态必须能通过。"""
    name = REAL_RULE_NAMES[0] + ".disabled"
    assert _safe_path(name).name == name
