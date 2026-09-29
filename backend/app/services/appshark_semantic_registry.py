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
    # 广告标识符原先混在 DeviceId_APICall 里（OAID/VAID/AAID/GAID 四个 sink 都是它）。
    # 拆出来的理由是证据强度：getOAID / getAdvertisingIdInfo 的返回值就是广告标识符，
    # 没有歧义——不像 G2 那次的 MediaRecorder 音源是通配参数、拆不动。
    # 归到 device_information 会让 advertising_identifier 这一格永远亮不起来，
    # 而它在 compliance_profile 的 SENSITIVE_CATEGORIES 里是有份量的。
    # 拆分只动归类：同一个 API 调用点仍会被检出，只是从此算广告标识符而不是设备标识符。
    "AdvertisingId_APICall":  dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="advertising_identifier", sink_type=None),
    # account 类目原先在枚举里但没有任何规则产出（覆盖度矩阵 §5）。只收**直接返回
    # Account[] 的三个取账号列表方法**；getAccountsByTypeAndFeatures 返回的是
    # AccountManagerFuture，未经验证不写进来。
    "Account_APICall":        dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="account",             sink_type=None),
    # 以下四条来自 camile.json（AppShark tag v0.1.2 的规则包，8 条规则 52 个 sink），
    # 但**没有按上游的分组原样引入**：上游「获取电话相关信息」把设备标识与基站信息
    # 装在同一条规则里、「获取系统信息」把 WiFi MAC 与剪贴板装在一起，照搬会重演
    # OAID 混进设备标识那种错误归类。这里只取上游的 sink 签名，按平台自己的
    # data_category 重新分组。
    "Bluetooth_APICall":      dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="bluetooth",           sink_type=None),
    "Cell_APICall":           dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="cell",                sink_type=None),
    "Carrier_APICall":        dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="network_information", sink_type=None),
    # 权限申请不是「采集了某类数据」，所以 data_category 留空——它记录的是
    # 「发起过运行时权限申请」这个事实，供后续判「非业务场景提前索权」用。
    # 空类目意味着它不参与任何 join，只做证据。
    "PermissionRequest_APICall": dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category=None,               sink_type=None),
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
    # 补上三个原先没有任何规则产出的流向：database / webview / clipboard。
    # 覆盖度矩阵 §5 把它们列为「未覆盖」——不是待验证，是当时根本没有规则。
    "DeviceId_Database":        dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="database"),
    "DeviceId_WebView":         dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="webview"),
    "DeviceId_Clipboard":       dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="clipboard"),
    "DeviceId_NetworkTransfer": dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="network"),

    # ---- 自有规则：L3 数据流，广告标识符 ----
    # 与上面 device_id_to_* 六条一一镜像，source 换成广告标识符、类目换成
    # advertising_identifier。原先 OAID/GAID 是混在 device_id_to_* 的 source 里的，
    # 于是 OAID 流向网络会被报成「设备标识外传」——按平台自己的枚举，OAID 属于
    # advertising_identifier，这是错误归因（与 L2 那处同源，只是更深一层：
    # 用户看到的是结论而不是证据）。拆分是**等价替换**：只挪走那两个 source，
    # 不加新 sink，六条 device 规则的检出集合减去广告标识符后与原来完全一致。
    "AdvertisingId_FileWrite":       dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="advertising_identifier", sink_type="file"),
    "AdvertisingId_Log":             dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="advertising_identifier", sink_type="log"),
    "AdvertisingId_Database":        dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="advertising_identifier", sink_type="database"),
    "AdvertisingId_WebView":         dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="advertising_identifier", sink_type="webview"),
    "AdvertisingId_Clipboard":       dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="advertising_identifier", sink_type="clipboard"),
    "AdvertisingId_NetworkTransfer": dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="advertising_identifier", sink_type="network"),
    "Location_NetworkTransfer": dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="location",           sink_type="network"),

    # ---- 官方规则：论断是「存在某个漏洞」→ 只做证据，不直接成结论 ----
    # 依据是**论断类型**，不是「来源是官方」：这四条声称的是「存在路径穿越 / Intent 重定向 /
    # 可变 PendingIntent」这类弱点，而污点分析只证明了「外部输入流到了某个 sink」。
    # AppShark 不进被调用方实现，校验可能就在接口实现里（实测 ContentProviderPathTraversal
    # 的命中即为误报：校验在 FileProvider$b.a(Uri) 里，见 docs/appshark-rule-capability.md
    # 能力边界 2）。命中是真阳性还是误报，必须在实现字节码上核实，平台不得直接发布成结论。
    "ContentProviderPathTraversal": dict(result_type=RESULT_SUPPORTING, observation_type="security.other", data_category=None, sink_type="file"),
    "IntentRedirectionBabyVersion": dict(result_type=RESULT_SUPPORTING, observation_type="security.other", data_category=None, sink_type="ipc"),
    "PendingIntentMutable":         dict(result_type=RESULT_SUPPORTING, observation_type="security.other", data_category=None, sink_type="ipc"),
    "unZipSlip":                    dict(result_type=RESULT_SUPPORTING, observation_type="security.other", data_category=None, sink_type="file"),

    # ---- 官方规则：论断是「存在 source→sink 路径」→ 命中即论断，仍直接成结论 ----
    # 与上面的区别在于：一条数据流路径存在与否，命中本身就是证据，无需再看实现内部。
    "IMEI_SendBroadcast":           dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="ipc"),
    "serial_Log":                   dict(result_type=RESULT_DIRECT, observation_type="dataflow.privacy", data_category="device_information", sink_type="log"),
    "MAC":                          dict(result_type=RESULT_SUPPORTING, observation_type="security.sensitive_api", data_category="device_information", sink_type=None),
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
