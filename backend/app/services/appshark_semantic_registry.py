"""AppShark 规则的语义注册表。

把 Provider 的规则名归一化为平台一等语义字段，使关联器可以用共享键连接，
而不必再用字符串匹配去「猜」语义。

这是**代码 + 测试**，不是可在 UI 编辑的规则：改错一个映射会让关联静默失效
（join key 对不上，不报错），必须像代码一样评审。

覆盖范围：规则目录中每一条规则。缺失即测试失败——宁可显式报错，也不要
静默降级成「无语义」。
"""

RESULT_DIRECT = "direct_finding"
RESULT_SUPPORTING = "supporting_evidence"
RESULT_FACT = "fact"

# provider_rule_id -> semantics
# data_category 为 None 是合法取值（安全类规则没有数据类目），不是缺失。
REGISTRY = {
    # ---- 自有规则：L2 API 调用（事实，不是结论）----
    "CameraMic_APICall":      dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="media",               sink_type=None),
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


class MissingSemanticsError(KeyError):
    """规则缺少语义标注。必须显式失败，不得静默降级。"""


def semantics_for(provider_rule_id: str) -> dict:
    """返回规则的平台语义。未注册即抛错。"""
    try:
        return REGISTRY[provider_rule_id]
    except KeyError:
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
