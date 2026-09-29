"""组件指纹匹配的语义约束。

这些断言钉的是 2026-09-29 那轮修复的核心：**match_mode 必须按语义生效**。
修复前两处匹配器都把 EXACT 当 PREFIX 用（查询筛了 match_mode、拿到手却丢掉），
且 55 条 CLASS/SUFFIX 与 993 条 MANIFEST/PERMISSION 指纹因过滤条件从不加载。
把「一律前缀」改回去，这里的用例应当红。
"""
import pytest

from app.services.component_matcher import (
    MATCHABLE_TYPES, MATCH_MODES, ComponentIndex,
)


def _index(*entries):
    """entries: (value, match_mode, component_id, extra?)"""
    idx = ComponentIndex()
    for value, mode, cid in entries:
        idx._add(value, mode, {
            "id": cid, "component_id": cid, "name": f"组件{cid}",
            "vendor": None, "component_kind": "SDK", "category_l1": None,
            "sensitivity_level": None, "fingerprint_id": cid,
            "fingerprint_type": "PACKAGE_PREFIX", "weight": 10,
        })
    idx._freeze()
    return idx


def test_exact_is_not_treated_as_prefix():
    """EXACT 登记的值不得匹配更长的串——这正是修复前的主要症状。"""
    idx = _index(("com.foo.bar", "EXACT", 1))
    assert idx.match("com.foo.bar")["component_id"] == 1
    assert idx.match("com.foo.bar.baz") is None


def test_prefix_matches_longer_strings():
    idx = _index(("com.foo", "PREFIX", 1))
    m = idx.match("com.foo.bar.Baz")
    assert m["component_id"] == 1
    assert m["match_mode"] == "PREFIX"
    assert m["matched_value"] == "com.foo"


def test_suffix_matches_class_names():
    """SUFFIX 指纹此前因为 match_mode 过滤条件从不被加载。"""
    idx = _index(("weibomultimessage", "SUFFIX", 7))
    m = idx.match("com.sina.weibo.sdk.WeiboMultiMessage")
    assert m is not None and m["component_id"] == 7
    assert m["match_mode"] == "SUFFIX"
    assert idx.match("com.other.Thing") is None


def test_longest_value_wins_within_same_candidate():
    """同一候选串内取最长匹配值——短值不得压过长值。"""
    idx = _index(("com.foo", "PREFIX", 1), ("com.foo.bar", "PREFIX", 2))
    assert idx.match("com.foo.bar.Baz")["component_id"] == 2


def test_exact_beats_shorter_prefix():
    idx = _index(("com.foo", "PREFIX", 1), ("com.foo.bar", "EXACT", 2))
    assert idx.match("com.foo.bar")["component_id"] == 2


def test_caller_takes_priority_over_api():
    """候选串按调用方给的顺序，先命中的胜出（调用方优先）。"""
    idx = _index(("com.from.caller", "PREFIX", 1), ("com.from.api", "PREFIX", 2))
    m = idx.match("com.from.caller.X", "com.from.api.Y")
    assert m["component_id"] == 1


def test_first_non_empty_candidate_wins():
    idx = _index(("com.from.api", "PREFIX", 2))
    assert idx.match(None, "", "  ", "com.from.api.Y")["component_id"] == 2


def test_empty_index_and_empty_candidates():
    assert _index().match("com.foo") is None
    assert _index(("com.foo", "PREFIX", 1)).match(None, "") is None


def test_values_are_case_insensitive():
    idx = _index(("com.foo.bar", "EXACT", 1))
    assert idx.match("COM.FOO.BAR")["component_id"] == 1


def test_match_mode_filter_accepts_all_three():
    """MATCH_MODES 必须含三种语义——漏掉 SUFFIX 就是修复前的老毛病。"""
    assert set(MATCH_MODES) == {"EXACT", "PREFIX", "SUFFIX"}


def test_unmatchable_types_are_excluded():
    """API_SIGNATURE 的取值是中文能力标签、MAVEN_COORDINATE 需要构建期坐标，
    都不是可匹配的字符串。它们一旦进了 MATCHABLE_TYPES，匹配器就会拿
    「sqlite/orm/键值存储/加密数据库」去和类名比。"""
    assert "API_SIGNATURE" not in MATCHABLE_TYPES
    assert "MAVEN_COORDINATE" not in MATCHABLE_TYPES
    # 能匹配的类型一个都不能少
    for t in ("PACKAGE_PREFIX", "CLASS", "PERMISSION",
              "MANIFEST_ACTIVITY", "MANIFEST_SERVICE",
              "MANIFEST_RECEIVER", "MANIFEST_PROVIDER"):
        assert t in MATCHABLE_TYPES, f"{t} 应参与匹配"


def test_matched_value_and_mode_are_reported():
    """调用方要靠这两个字段写证据，不能只有组件。"""
    idx = _index(("com.foo", "PREFIX", 1))
    m = idx.match("com.foo.bar")
    for key in ("component_id", "id", "fingerprint_id", "fingerprint_type",
                "weight", "matched_value", "match_mode"):
        assert key in m, f"缺少 {key}"


def test_id_is_kept_for_frontend_contract():
    """事件接口把匹配结果直接塞进响应，前端按 `id` 取组件；`id` 与
    `component_id` 必须同值，否则界面上的 SDK 角标会消失。"""
    idx = _index(("com.foo", "PREFIX", 42))
    m = idx.match("com.foo.bar")
    assert m["id"] == m["component_id"] == 42
