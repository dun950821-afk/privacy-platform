"""原始 JSON 拆段服务：把引擎输出变成可查询的段落。

## 为什么需要

引擎原始产物**已经**持久化在归档层（`engine_artifacts`，带 sha256），但提取是**一次性的**：
适配器 `normalize_events()` 取完事件，raw dict 就当局部变量丢掉了。于是没被提取的段落等于不存在。

实测 task 2216 的后果：Androguard 的 `endpoints`（41 URL + 12 域名 + 3 IP，含**隐私政策 URL**
`https://mbank.bankofyk.com:1443/clients/useruploads/iap/other/PrivacyC.html`）整段丢弃；
MobSF 的 53 个段落只用了 4 个（`appsec` / `manifest_findings` / `secrets` / `sbom` 全丢）。

本服务把每个节点原样拆成一行，让「以后才想到要问的问题」也能查。

## 拆分规则（唯一的语义约定）

1. 对 dict **递归下钻**；每个节点产出一行（父与子都产出——宁可重复，也不丢兄弟标量）
2. **list 是终点**：整列表作为一行 payload，**不展开元素**（MobSF 的 `files` 有 944 个元素，
   展开会炸；不展开则一行装下）
3. 深度上限 `max_depth=4`，防御畸形嵌套导致行数爆炸；超限时截断而非报错
4. `payload` 原样保存，绝不裁剪——这是本表存在的意义

路径用 `.` 连接。**注意 MobSF 的键本身可能含点号**（如 `permissions` 下是
`android.permission.CALL_PHONE`），所以路径**只供人读与 like 匹配，不做反解析**；
真正精确定位靠 `payload` 上的 GIN 索引。
"""
import json

import pytest

from app.services.raw_section_service import split_sections


def by_path(rows: list[dict]) -> dict[str, dict]:
    return {r["path"]: r for r in rows}


# ── 规则 1：dict 下钻，每节点一行 ──────────────────────────────────────

def test_flat_dict_yields_one_row_per_key():
    rows = split_sections({"a": 1, "b": "x", "c": True})
    assert set(by_path(rows)) == {"a", "b", "c"}
    assert all(r["kind"] == "scalar" for r in rows)
    assert by_path(rows)["a"]["payload"] == 1


def test_parent_keeps_scalars_and_containers_get_their_own_rows():
    """标量留在父行，容器各自成行——值只存一次。"""
    rows = split_sections({"appsec": {"security_score": 47, "high": [{"x": 1}]}})
    paths = by_path(rows)
    assert paths["appsec"]["payload"] == {"security_score": 47}, "标量归父行"
    assert paths["appsec.high"]["payload"] == [{"x": 1}], "list 另成一行"
    assert "appsec.security_score" not in paths, "标量不重复成行"


def test_container_is_not_duplicated_in_parent_payload():
    """**放大倍数的护栏。** 曾经每个节点都存整棵子树，实测 3.0×——
    MobSF 单任务 3MB 变 9MB。父行只装标量后回到 1.0×。"""
    raw = {"ComplianceInfo": {"Cat": {"Rule": {"level": "L3", "vulners": list(range(2000))}}}}
    rows = split_sections(raw)
    # 2000 个元素的列表只能在一个 payload 里出现
    carriers = [r["path"] for r in rows if isinstance(r["payload"], list)]
    assert carriers == ["ComplianceInfo.Cat.Rule.vulners"], f"列表被存了多份：{carriers}"
    total = sum(len(json.dumps(r["payload"])) for r in rows)
    original = len(json.dumps(raw))
    assert total < original * 1.3, f"放大 {total/original:.1f}×，值又被重复存了"


def test_all_data_is_recoverable_from_rows():
    """无损：把行按路径拼回去必须等于原文。"""
    raw = {
        "AppInfo": {"AppName": "营行企业银行", "PackageName": "com.x", "min_sdk": 16},
        "ComplianceInfo": {"Cat": {"Rule": {"level": "L3", "note": None,
                                            "vulners": [{"hash": "h"}]}}},
        "DeepLinkInfo": {},
        "UsePermissions": ["android.permission.INTERNET"],
    }
    rows = split_sections(raw)
    rebuilt: dict = {}
    for r in sorted(rows, key=lambda r: r["path"]):
        cur = rebuilt
        segs = r["path"].split(".")
        for s in segs[:-1]:
            cur = cur.setdefault(s, {})
        cur[segs[-1]] = r["payload"]
    assert rebuilt == raw


# ── 规则 2：list 是终点 ────────────────────────────────────────────────

def test_list_is_terminal_and_not_expanded():
    rows = split_sections({"urls": ["a", "b", "c"]})
    assert len(rows) == 1
    assert rows[0]["path"] == "urls"
    assert rows[0]["kind"] == "array"
    assert rows[0]["item_count"] == 3
    assert rows[0]["payload"] == ["a", "b", "c"]


def test_large_list_still_yields_exactly_one_row():
    """MobSF 的 files 实测 944 个元素——展开会炸，一行装下才对。"""
    rows = split_sections({"files": [{"name": f"f{i}"} for i in range(944)]})
    assert len(rows) == 1
    assert rows[0]["item_count"] == 944
    assert len(rows[0]["payload"]) == 944


def test_list_of_dicts_is_not_descended_into():
    rows = split_sections({"vulners": [{"details": {"url": "u"}, "hash": "h"}]})
    assert [r["path"] for r in rows] == ["vulners"]


# ── 规则 3：深度上限 ───────────────────────────────────────────────────

def test_depth_limit_truncates_without_raising():
    deep = {"l1": {"l2": {"l3": {"l4": {"l5": {"l6": "bottom"}}}}}}
    rows = split_sections(deep)  # 不抛异常
    paths = by_path(rows)
    assert "l1.l2.l3.l4" in paths
    assert "l1.l2.l3.l4.l5" not in paths, "超限不再下钻"
    # 截断处仍要保留原文，否则深度保护会变成数据丢失
    assert paths["l1.l2.l3.l4"]["payload"] == {"l5": {"l6": "bottom"}}


def test_empty_dict_yields_a_row():
    rows = split_sections({"DeepLinkInfo": {}})
    assert len(rows) == 1
    assert rows[0]["kind"] == "object"
    assert rows[0]["payload"] == {}


# ── 真实引擎结构 ───────────────────────────────────────────────────────

def test_appshark_compliance_path_reaches_the_vulnerability_list():
    """AppShark 是 分类 -> 规则 -> 明细 三层，要能一路定位到 vulners。"""
    raw = {
        "ComplianceInfo": {
            "PersonalDeviceInformation_APICall": {
                "DeviceId_APICall": {
                    "category": "PersonalDeviceInformation",
                    "detail": "设备标识符读取",
                    "name": "DeviceId_APICall",
                    "level": "L3",
                    "vulners": [{"details": {"Source": ["s"]}, "hash": "h"}],
                }
            }
        }
    }
    paths = by_path(split_sections(raw))
    want = "ComplianceInfo.PersonalDeviceInformation_APICall.DeviceId_APICall.vulners"
    assert want in paths, f"应能定位到规则下的漏洞列表，实际路径：{sorted(paths)}"
    assert paths[want]["item_count"] == 1
    # 规则自身的标量留在规则那一行（不再各自成路径，但数据在）
    rule_row = paths["ComplianceInfo.PersonalDeviceInformation_APICall.DeviceId_APICall"]
    assert rule_row["payload"] == {"category": "PersonalDeviceInformation",
                                   "detail": "设备标识符读取",
                                   "name": "DeviceId_APICall",
                                   "level": "L3"}


def test_mobsf_key_sections_are_reachable():
    raw = {
        "trackers": {"detected_trackers": 0, "total_trackers": 432, "trackers": []},
        "appsec": {"security_score": 47, "high": [], "warning": []},
        "sbom": {"sbom_versioned": ["androidx.appcompat:appcompat@1.0.0"], "sbom_packages": []},
        "urls": ["u1"],
    }
    paths = by_path(split_sections(raw))
    for want in ("trackers.trackers", "appsec.high", "sbom.sbom_versioned", "urls"):
        assert want in paths, f"缺 {want}"
    # 标量随父行：查询时读 payload 字段
    assert paths["appsec"]["payload"] == {"security_score": 47}
    assert paths["trackers"]["payload"]["total_trackers"] == 432


def test_path_with_dots_in_keys_is_still_queryable():
    """MobSF 的 permissions 键是 android.permission.XXX，路径会被点号切碎——
    这是可接受的（路径只供人读），但 payload 必须原样可查。"""
    raw = {"permissions": {"android.permission.CALL_PHONE": {"status": "dangerous"}}}
    paths = by_path(split_sections(raw))
    assert "permissions.android.permission.CALL_PHONE" in paths
    assert paths["permissions.android.permission.CALL_PHONE"]["payload"] == {"status": "dangerous"}
    # 歧义靠 like 匹配绕开：查这条权限用 payload 而不是路径
    assert paths["permissions.android.permission.CALL_PHONE"]["payload"]["status"] == "dangerous"


# ── 哈希与健壮性 ───────────────────────────────────────────────────────

def test_payload_hash_is_stable_and_content_sensitive():
    a1 = split_sections({"a": {"x": 1, "y": 2}})
    a2 = split_sections({"a": {"y": 2, "x": 1}})   # 键序不同
    b = split_sections({"a": {"x": 1, "y": 3}})
    ha1 = by_path(a1)["a"]["payload_hash"]
    ha2 = by_path(a2)["a"]["payload_hash"]
    hb = by_path(b)["a"]["payload_hash"]
    assert ha1 == ha2, "同一内容不同键序应得同一哈希（跨次扫描才可比）"
    assert ha1 != hb, "内容变了哈希要变"


def test_non_dict_input_returns_empty_without_raising():
    assert split_sections([]) == []
    assert split_sections(None) == []
    assert split_sections("oops") == []


def test_empty_input():
    assert split_sections({}) == []


def test_payload_roundtrips_through_json():
    """payload 要能进 JSONB——不能塞进不可序列化的东西。"""
    rows = split_sections({"a": {"b": [1, 2, {"c": None}]}, "t": True})
    for r in rows:
        json.dumps(r["payload"])  # 不抛即通过
