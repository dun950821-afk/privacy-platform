"""Provider 语义注册表。

把 Provider 的规则/分类归一化为平台一等语义字段，使关联器可以用共享键连接，
而不必再用字符串匹配去「猜」语义。

这是**代码 + 测试**，不是可在 UI 编辑的规则：改错一个映射会让关联静默失效
（join key 对不上，不报错），必须像代码一样评审。

覆盖两个 Provider，键不同——这也是当初「只用一个 category 字段」不够用的原因：
- AppShark：键是 `payload.rule`（规则名），见 REGISTRY
- Androguard：事件里没有 rule，键是 `payload.category`（敏感权限分组）

覆盖范围：各自的取值全集。缺失即测试失败——宁可显式报错，也不要
静默降级成「无语义」。
"""

RESULT_DIRECT = "direct_finding"
RESULT_SUPPORTING = "supporting_evidence"
RESULT_FACT = "fact"

# provider_rule_id -> semantics
# data_category 为 None 是合法取值（安全类规则没有数据类目），不是缺失。
REGISTRY = {
    # ---- 自有规则：L2 API 调用（事实，不是结论）----
    # 相机与音视频采集分属两条规则：Camera.open 确证是摄像头；MediaRecorder 的
    # 音源/视频源是可传 Surface 或 REMOTE_SUBMIX 的通配参数，不能据此判定用了
    # 摄像头或麦克风，因此只标到「音视频采集」这一层（media）。
    # 把能确证的映射成不能确证的，与把不能确证的声称为能确证的，都是错的（设计 §4.2）。
    "Camera_APICall":         dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="camera",              sink_type=None),
    "Media_APICall":          dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="media",               sink_type=None),
    "Clipboard_APICall":      dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="clipboard",           sink_type=None),
    "DeviceId_APICall":       dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="device_information",  sink_type=None),
    "InstalledApps_APICall":  dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="installed_apps",      sink_type=None),
    "Location_APICall":       dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="location",            sink_type=None),
    "Network_APICall":        dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="network_information", sink_type=None),
    "Sensor_APICall":         dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="sensor",              sink_type=None),
    "Wifi_APICall":           dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="network_information", sink_type=None),

    # ---- 自有规则：L3 数据流（完整 source→sink，直接成结论）----
    "Clipboard_Log":            dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="clipboard",          sink_type="log"),
    "DeviceId_FileWrite":       dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="file"),
    "DeviceId_Log":             dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="log"),
    "DeviceId_NetworkTransfer": dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="network"),
    "Location_NetworkTransfer": dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="location",           sink_type="network"),

    # ---- 官方安全规则：无数据类目，但仍是完整结论 ----
    "ContentProviderPathTraversal": dict(result_type=RESULT_DIRECT, observation_type="security.other", data_category=None, sink_type="file"),
    "IntentRedirectionBabyVersion": dict(result_type=RESULT_DIRECT, observation_type="security.other", data_category=None, sink_type="ipc"),
    "PendingIntentMutable":         dict(result_type=RESULT_DIRECT, observation_type="security.other", data_category=None, sink_type="ipc"),
    "IMEI_SendBroadcast":           dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="ipc"),
    "serial_Log":                   dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="log"),
    "MAC":                          dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="device_information", sink_type=None),
    "unZipSlip":                    dict(result_type=RESULT_DIRECT, observation_type="security.other", data_category=None, sink_type="file"),
}


# ---------- Androguard：敏感权限分组 → data_category ----------
# 取值来自 runner 的 SENSITIVE_PERMISSIONS 分组（app/engine/runners/androguard_runner.py），
# 键必须与其**完全一致**：runner 新增一个分组而这里没跟上，那个分组的观察会静默失去
# 类目，join 不报错也不命中。test_androguard_categories_cover_runner 拦这一类。
#
# 映射到设计文档 §4.3 的枚举取值，不向 AppShark 的粗粒度看齐：Androguard 能区分
# 相机与麦克风，AppShark 的 CameraMic_APICall 区分不了。把能区分的映射成区分不了的，
# 属于主动丢信息（见设计 §4.2 命名不得放宽）。
ANDROGUARD_PERMISSION_CATEGORIES = {
    "LOCATION": "location",
    "PHONE_STATE": "phone",
    "CONTACTS": "contacts",
    "CAMERA": "camera",
    "MICROPHONE": "microphone",
    "STORAGE": "files",
    "SMS": "sms",
}


# 已退役的 Provider 规则 → 语义。**仅供历史产物重新归一化使用**：task 553 回归基线
# （tests/fixtures/appshark/task_553）与库中既有观察都记着 `CameraMic_APICall`，
# 该规则已按 G2 拆成 Camera_APICall / Media_APICall，当前规则目录里不再有它。
#
# 不留这张表的话，重新归一化历史产物会得到「无语义」——同一个文件名、同一份产物，
# 改造前后归一化结果不同，历史结论就不可复现了。新事件不会再带这些规则名。
RETIRED_REGISTRY = {
    "CameraMic_APICall": dict(result_type=RESULT_SUPPORTING,
                              observation_type="security.sensitive_api",
                              data_category="media", sink_type=None),
}


class MissingSemanticsError(KeyError):
    """规则缺少语义标注。必须显式失败，不得静默降级。"""


def androguard_permission_semantics(category: str) -> dict | None:
    """Androguard 敏感权限分组的平台语义；未登记分组返回 None。

    与 AppShark 的 `semantics_for` 有意不同：那边未登记即抛错（规则是我们自己写进
    目录的，缺标注是遗漏）；这里的取值来自第三方 runner 的既有分组，未登记只说明
    这个分组还没有对应的平台类目，不该让整个任务失败。
    """
    data_category = ANDROGUARD_PERMISSION_CATEGORIES.get(category)
    if not data_category:
        return None
    return dict(result_type=RESULT_SUPPORTING,
                observation_type="fact.sensitive_permission",
                data_category=data_category, sink_type=None)


def semantics_for(provider_rule_id: str) -> dict:
    """返回规则的平台语义。未注册即抛错。"""
    for table in (REGISTRY, RETIRED_REGISTRY):
        if provider_rule_id in table:
            return table[provider_rule_id]
    raise MissingSemanticsError(
        "规则 %s 未在语义注册表中标注；新增规则必须同时登记语义，"
        "否则它不会参与任何关联" % provider_rule_id)


def is_direct_finding(provider_rule_id: str) -> bool:
    return semantics_for(provider_rule_id)["result_type"] == RESULT_DIRECT


def enrich_observation(observation: dict, provider_rule_id: str) -> dict:
    """把语义字段写入观察（原地不修改传入对象）。"""
    sem = semantics_for(provider_rule_id)
    out = dict(observation)
    out["data_category"] = sem["data_category"]
    out["sink_type"] = sem["sink_type"]
    out["result_semantics"] = sem["result_type"]
    out["provider_rule_id"] = provider_rule_id
    keys = {"app_version": observation.get("app_version_id")}
    if sem["data_category"]:
        keys["data_category"] = sem["data_category"]
    out["entity_keys"] = {k: v for k, v in keys.items() if v is not None}
    return out
