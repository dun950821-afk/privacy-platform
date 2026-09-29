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
    """entries: (value, match_mode, component_id) 或
                (value, match_mode, component_id, fingerprint_type)

    默认按代码级（PACKAGE_PREFIX）登记；要造清单级/权限级指纹就显式给第四个参数。
    """
    idx = ComponentIndex()
    for ent in entries:
        value, mode, cid = ent[0], ent[1], ent[2]
        ftype = ent[3] if len(ent) > 3 else "PACKAGE_PREFIX"
        idx._add(value, mode, {
            "id": cid, "component_id": cid, "name": f"组件{cid}",
            "vendor": None, "component_kind": "SDK", "category_l1": None,
            "sensitivity_level": None, "fingerprint_id": cid,
            "fingerprint_type": ftype, "weight": 10,
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


def test_duplicate_manifest_registration_broken_by_code_specificity():
    """**同一个类名被两个组件都登记为清单组件时，归属该给更具体的那个。**

    这是真实数据里的形状，库里这类重复登记有 744 处：某个类既被笼统的上游 SDK
    登记（Flutter / 腾讯 X5），又被具体的插件组件登记（Flutter Image Picker 插件 /
    TBS 文件预览封装组件）。两者登记的是**同一个字符串**，靠清单本身分不出来。

    判据是**代码级指纹对这个类的匹配长度**——谁在命名空间上更贴近它，谁更具体。
    实测 4 条争议事件（TBSFileViewActivity、ContactsActivity、PortalFlutterActivity、
    ImagePickerFileProvider）全部由此落到具体组件上。
    """
    act = "com.specific.plugin.lib.MainActivity"
    idx = _index(
        (act, "EXACT", 1, "MANIFEST_ACTIVITY"),        # 笼统组件也登记了同一个类
        (act, "EXACT", 2, "MANIFEST_ACTIVITY"),        # 具体组件同样登记
        ("com", "PREFIX", 1),                          # 笼统组件的代码级指纹很宽
        ("com.specific.plugin.lib", "PREFIX", 2),      # 具体组件的代码级指纹更贴近
    )
    m = idx.match(act)
    assert m["component_id"] == 2, "归属被更笼统的组件拿走了"
    assert m["fingerprint_type"] == "MANIFEST_ACTIVITY", "机制应走清单登记，不是被前缀接管"


def test_duplicate_without_code_evidence_falls_back_deterministically():
    """两个组件登记同一个值、都没有代码级证据时，结果仍要确定——不能取决于
    数据库返回的行序（最初用 setdefault 正是栽在这里）。

    这条只保证「确定」，不代表「更正确」：判不出更具体时，靠组件 id 定序。
    """
    act = "com.a.Big"
    forward = _index((act, "EXACT", 7, "MANIFEST_ACTIVITY"), (act, "EXACT", 3, "MANIFEST_ACTIVITY"))
    backward = _index((act, "EXACT", 3, "MANIFEST_ACTIVITY"), (act, "EXACT", 7, "MANIFEST_ACTIVITY"))
    assert forward.match(act)["component_id"] == 3
    assert backward.match(act)["component_id"] == 3
    assert forward.duplicate_count == 1


def test_manifest_tier_runs_before_code_tier():
    """清单登记说的是「这个组件声明使用/暴露了这个类」，比「类定义在谁的命名空间下」
    更贴「谁在采集」。所以清单级先于代码级尝试。"""
    idx = _index(
        ("com.a.Lib.Act", "EXACT", 1, "MANIFEST_ACTIVITY"),
        ("com.a.Lib", "PREFIX", 2),
    )
    assert idx.match("com.a.Lib.Act")["component_id"] == 1


def test_code_tier_still_wins_when_no_manifest_match():
    """层级不是「禁用代码指纹」——清单级没命中时，代码级照常给归属。"""
    idx = _index(("com.a.lib", "PREFIX", 2))
    assert idx.match("com.a.lib.Thing")["component_id"] == 2


def test_permission_tier_is_last_resort():
    """权限名与类名/包名不同域，放最后；且只有权限串才该走到它。"""
    idx = _index(
        ("android.permission.nfc", "EXACT", 9, "PERMISSION"),
        ("android", "PREFIX", 8),
    )
    # 代码级（"android" 前缀）先命中，权限级不会抢到
    assert idx.match("android.permission.nfc")["component_id"] == 8


def test_id_is_kept_for_frontend_contract():
    """事件接口把匹配结果直接塞进响应，前端按 `id` 取组件；`id` 与
    `component_id` 必须同值，否则界面上的 SDK 角标会消失。"""
    idx = _index(("com.foo", "PREFIX", 42))
    m = idx.match("com.foo.bar")
    assert m["id"] == m["component_id"] == 42
