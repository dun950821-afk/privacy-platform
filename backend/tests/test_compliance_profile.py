"""合规画像的归并与归因判定。

这是平台区别于「引擎结果罗列」的地方：同一处采集，是应用自身写的还是某个 SDK 干的，
合规含义完全不同。判定错了不是显示问题，是结论错 —— 所以每条规则都要有测试。
"""
import pytest

from app.services.compliance_profile import build_profile, component_prefixes

APP_PKG = "cn.com.bank.app"

SDKS = [
    {"name": "合合信息图像处理 SDK", "component_kind": "SDK", "vendor": "上海合合信息科技",
     "prefix": "com.intsig.pdf"},
    {"name": "信雅达影像采集 SDK", "component_kind": "VENDOR_COMPONENT", "vendor": "信雅达科技",
     "prefix": "com.sunyard.photomain"},
    {"name": "易通定位调度模块", "component_kind": "VENDOR_COMPONENT", "vendor": "易通科技",
     "prefix": "com.yitong.mbank"},
    {"name": "某 SDK 的具体子模块", "component_kind": "SDK", "vendor": "X",
     "prefix": "com.intsig.pdf.sdk.key"},
]

KB = {
    "android.permission.READ_PHONE_STATE": {"category": "电话与设备标识", "capability": "读取设备标识",
                                            "permission_type": "危险权限", "risk_level": "HIGH",
                                            "compliance_focus": "需说明用途"},
    "android.permission.ACCESS_FINE_LOCATION": {"category": "位置信息", "capability": "获取精确位置",
                                                "permission_type": "危险权限", "risk_level": "HIGH",
                                                "compliance_focus": "仅核心功能使用"},
}


def obs(oid, caller, category, otype="security.sensitive_api", sink=None, engine="appshark"):
    return {"id": oid, "observation_type": otype, "data_category": category,
            "sink_type": sink, "provider_rule_id": "DeviceId_APICall", "engine_type": engine,
            "subject": caller, "payload": {"caller": caller, "permission": None, "url": "/tmp/x.html"}}


def perm(oid, name, engine="androguard"):
    return {"id": oid, "observation_type": "fact.permission", "data_category": None,
            "sink_type": None, "provider_rule_id": None, "engine_type": engine,
            "subject": name, "payload": {"permission": name}}


def profile(observations, app_pkg=APP_PKG):
    return build_profile(observations, SDKS, KB, app_pkg)


# ---------- 归因：谁在采集 ----------

def test_call_site_under_app_package_is_app_self():
    p = profile([obs(1, "<cn.com.bank.app.ui.Main: void a()>", "location")])
    assert len(p["collect_app_self"]) == 1
    assert p["collect_app_self"][0]["owner"]["kind"] == "self"


def test_call_site_under_sdk_prefix_is_third_party_with_identity():
    """第三方组件必须带上身份与厂商——「某 SDK 采集了位置」和「百度定位采集了位置」不是一回事。"""
    p = profile([obs(1, "<com.intsig.pdf.reader.A: void b()>", "device_information")])
    assert not p["collect_app_self"]
    item = p["collect_third_party"][0]
    assert item["owner"]["name"] == "合合信息图像处理 SDK"
    assert item["owner"]["vendor"] == "上海合合信息科技"


def test_longest_prefix_wins():
    """com.intsig.pdf 与 com.intsig.pdf.sdk.key 同时命中时，取更具体的那个。"""
    p = profile([obs(1, "<com.intsig.pdf.sdk.key.AppkeySDK: String getDeviceId()>", "device_information")])
    assert p["collect_third_party"][0]["owner"]["name"] == "某 SDK 的具体子模块"


def test_vendor_component_is_not_counted_as_app_self():
    """知识库把 App 的开发方与第三方供应商都标成 VENDOR_COMPONENT，不能因此算作「应用自身」。

    实测某银行 App：信雅达影像采集读位置/相机，若算作应用自身，就等于在合规报告里
    说「应用自己采集的，无需第三方声明」—— 而它必须声明。
    """
    p = profile([obs(1, "<com.sunyard.photomain.util.Camera: void c()>", "location")])
    assert not p["collect_app_self"], "厂商组件 ≠ 应用自身"
    assert p["collect_third_party"][0]["owner"]["name"] == "信雅达影像采集 SDK"


def test_unattributed_call_site_goes_to_unidentified_bucket():
    """认不出来的一律进「待分析」，不得默默算成应用自身。"""
    p = profile([obs(1, "<com.unknown.thing.A: void d()>", "installed_apps")])
    assert not p["collect_app_self"]
    assert not p["collect_third_party"]
    assert p["collect_unidentified"][0]["call_site_count"] == 1


def test_sensitive_and_permission_required_flags():
    p = profile([obs(1, "<com.intsig.pdf.a.B: void e()>", "location"),
                 obs(2, "<com.intsig.pdf.a.B: void f()>", "installed_apps")])
    by_cat = {i["data_category"]: i for i in p["collect_third_party"]}
    assert by_cat["location"]["sensitive"] is True
    assert by_cat["location"]["requires_permission"] is True
    assert by_cat["installed_apps"]["sensitive"] is False
    assert by_cat["installed_apps"]["requires_permission"] is False, "应用列表无需权限即可读取"


def test_collect_mode_only_claims_what_engine_proved():
    """调用 API 只证明「读取」，不能写成「已获取」；数据流才证明流向。"""
    p = profile([obs(1, "<com.intsig.pdf.a.B: void g()>", "location"),
                 obs(2, "<com.intsig.pdf.a.B: void h()>", "location",
                     otype="dataflow.privacy", sink="network")])
    modes = p["collect_third_party"][0]["collect_modes"]
    assert "读取（调用 API）" in modes
    assert "外传（网络）" in modes
    assert not any("已获取" in m for m in modes)


# ---------- 4.2 权限 ----------

def test_permission_name_is_normalized_across_engines():
    """Androguard 报短名、AppShark 报全名，同一条权限不能出现两行。"""
    p = profile([perm(1, "ACCESS_FINE_LOCATION", engine="androguard"),
                 perm(2, "android.permission.ACCESS_FINE_LOCATION", engine="appshark")])
    assert [r["permission"] for r in p["permissions"]] == ["ACCESS_FINE_LOCATION"]
    assert p["permissions"][0]["declared_by"] == ["androguard", "appshark"]


def test_phone_state_guards_device_information_too():
    """READ_PHONE_STATE 同时守护设备标识。

    只把它连到 phone，页面就会在「设备标识」那行显示「无对应权限」——
    读 IMEI 明明就靠它，这是合规报告里的硬伤。
    """
    p = profile([perm(1, "READ_PHONE_STATE"),
                 obs(2, "<com.intsig.pdf.a.B: String getDeviceId()>", "device_information"),
                 obs(3, "<com.intsig.pdf.a.B: String getDeviceId()>", "device_information")])
    row = p["permissions"][0]
    assert set(row["guards"]) >= {"phone", "device_information"}
    assert row["call_site_count"] == 2, "设备标识的调用点必须算进这条权限"


def test_unmapped_permission_is_not_reported_as_unused():
    """映射未覆盖的权限不得显示成「申请了没用」——那只是我们不知道它守护什么。"""
    p = profile([perm(1, "android.permission.INTERNET")])
    row = p["permissions"][0]
    assert row["guard_mapped"] is False
    assert row["call_site_count"] == 0
    assert row["guards"] == []


def test_permission_carries_kb_description():
    p = profile([perm(1, "android.permission.ACCESS_FINE_LOCATION")])
    row = p["permissions"][0]
    assert row["category_cn"] == "位置信息"
    assert row["capability"] == "获取精确位置"
    assert row["kb_available"] is True


def test_permission_without_kb_entry_is_flagged():
    p = profile([perm(1, "com.vendor.permission.SPECIAL")])
    assert p["permissions"][0]["kb_available"] is False


# ---------- 政策字段：没有就说没有 ----------

def test_policy_fields_are_none_not_false():
    """「是否在隐私政策中声明」没有数据时必须是 None。

    显示成「否」= 断言违规；显示成 null = 我们不知道。二者在合规上不是一回事。
    """
    p = profile([obs(1, "<com.intsig.pdf.a.B: void i()>", "location")])
    assert p["collect_third_party"][0]["declared_in_policy"] is None
    assert p["collect_third_party"][0]["necessary"] is None
    assert p["policy_available"] is False


def test_no_collection_observations_yields_empty_profile():
    p = profile([perm(1, "CAMERA")])
    assert p["collect_app_self"] == []
    assert p["collect_third_party"] == []
    assert p["collect_unidentified"] == []


def test_caller_in_stringified_list_is_still_attributed():
    """调用点有时是字符串化的列表：`['<com.a.B: void c()>->$r5']`。

    按 `<` 剥前缀会漏掉这种形态（它以 `['` 开头），类名带着 `['` 去比对就全部失配 ——
    实测踩到过：百度定位 SDK 的 284 处采集因此掉进了「未识别」。
    """
    caller = "['<com.intsig.pdf.sdk.key.AppkeySDK: java.lang.String getDeviceId(android.content.Context)>->$r8']"
    p = profile([obs(1, caller, "device_information")])
    assert not p["collect_unidentified"], "列表形态的调用点必须也能归因"
    assert p["collect_third_party"][0]["owner"]["name"] == "某 SDK 的具体子模块"


def test_class_fingerprint_is_used_as_package_prefix():
    """只登记了 CLASS 指纹的组件（如百度定位 SDK）也要能归因。

    它的包前缀由类名退一级推出，依据标为 CLASS_INFERRED —— 推断要与确证区分。
    """
    from app.services.compliance_profile import component_prefixes
    comps = [{"name": "百度定位 SDK", "component_kind": "SDK", "vendor": "百度",
              "class_name": "com.baidu.location.f"}]
    prefixes = component_prefixes(comps)
    assert prefixes[0][0] == "com.baidu.location"
    assert prefixes[0][2] == "CLASS_INFERRED"

    # 归因依据不同，界面上要与确证区分
    p = build_profile([obs(1, "<com.baidu.location.b: void a()>", "location")], comps, KB, APP_PKG)
    assert p["collect_third_party"][0]["owner"]["attribution_basis"] == "CLASS_INFERRED"
