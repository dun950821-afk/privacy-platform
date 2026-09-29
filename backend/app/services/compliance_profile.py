"""把各引擎的结果聚合成「这个 App 的隐私合规画像」。

**这是平台存在的理由**：单个引擎只会罗列自己看到的观察，而合规审阅要回答的是
「谁在收集、收集了什么、在哪收集」，这需要跨引擎合并 —— 引擎只是证据来源的标注。

结构与字段照 T/GZHLW 团体标准的第 4 章《App 检测详情》：

    4.1 个人信息收集详情   4.1.1 App 自身收集   4.1.2 App 嵌入第三方 SDK 收集
    4.2 App 权限使用详情   4.2.1 App 自身使用   4.2.2 App 嵌入第三方 SDK 使用

二分「应用自身 / 第三方 SDK」是本模块的核心：同一处个人信息采集，是应用自己写的还是
某个 SDK 干的，合规含义完全不同 —— 第三方 SDK 的采集行为要在隐私政策里逐一声明，
而用户往往不知道这些 SDK 存在。实测某银行 App 的采集点里厂商自有代码只占 80 处、
第三方 SDK 占 3000 余处。

字段缺口（**一律返回 None，不编造**）：
- 「是否在隐私政策中声明」：privacy_policies 表结构齐全但至今 0 条数据、0 个任务关联
- 「必要 / 非必要」：同上，需要政策 + 业务功能清单才能判定
界面必须把 None 显示为「无数据」而不是「否」——「没声明」和「不知道有没有声明」
在合规上不是一回事。
"""
import re
from collections import defaultdict

from sqlalchemy.orm import Session

# 不需要权限即可采集的数据类目（按 Android 权限模型）
NO_PERMISSION_CATEGORIES = {
    "device_information", "installed_apps", "network_information", "sensor",
    "clipboard", "media", "advertising_identifier",
}

# 个人信息敏感度：个保法意义上的敏感个人信息 + 常见高敏感类目
#
# `cell` 纳入：基站/小区信息（LAC/CID/基站 ID）能反推行踪轨迹，属个保法的敏感个人信息。
# `bluetooth` 不纳入：蓝牙设备名/适配器名的识别力与 device_information 同级，
# 而 device_information 本就不在这一档，单把它提上来会让两档失去可比性。
SENSITIVE_CATEGORIES = {
    "contacts", "location", "camera", "microphone", "sms", "phone",
    "files", "photos", "biometric", "calendar", "account", "clipboard",
    "cell",
}

DATA_CATEGORY_CN = {
    "device_information": "设备标识信息",
    "installed_apps": "已安装应用列表",
    "network_information": "网络信息（WiFi/运营商）",
    "location": "位置信息",
    "contacts": "通讯录",
    "camera": "摄像头",
    "microphone": "麦克风",
    "media": "音视频采集",
    "sensor": "传感器数据",
    "clipboard": "剪贴板",
    "files": "外部存储文件",
    "phone": "电话状态",
    "sms": "短信",
    "photos": "相册图片",
    "calendar": "日历",
    "account": "账号信息",
    "biometric": "生物识别",
    "advertising_identifier": "广告标识符",
    "cell": "基站与小区信息",
    "bluetooth": "蓝牙设备信息",
    "personal_information": "个人信息",
    "unknown": "未知",
}

# 引擎观察 → 收集方式的诚实映射：只说引擎证明了的那一层
COLLECT_MODE_CN = {
    "sensitive_api": "读取（调用 API）",
    "network": "外传（网络）",
    "file": "存储（文件）",
    "log": "写入日志",
    "ipc": "进程间传递",
    "database": "存储（数据库）",
    "webview": "WebView",
}

# 「应用自身」只认一件事：调用点落在 App 自己的包名下。
#
# 不能拿知识库的 VENDOR_COMPONENT 当「应用自身」——那一类里同时装着 App 的开发方
# （易通科技）和第三方供应商（信雅达科技）。实测某银行 App：把 VENDOR_COMPONENT 算自身
# 会把「信雅达影像采集（读位置/相机）」写成应用自己的代码，而它是要在隐私政策里声明的
# 第三方模块。要精确合并开发方，得先把 app_assets.vendor（开发方）填上——该字段存在但全空。
SELF_KINDS = {"VENDOR_COMPONENT", "APP_MODULE"}

# 权限 → 它守护的数据类目（多对多）。
# 关键的一条是 READ_PHONE_STATE 同时守护设备标识：只把它连到 phone，页面就会在
# 「设备标识」那一行得出「无权限」的结论 —— 放在合规报告里是硬伤。
# 不在此表里的权限一律标「映射未覆盖」，不推断它有没有被使用。
PERMISSION_GUARDS = {
    "location": {"ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION", "ACCESS_BACKGROUND_LOCATION"},
    "contacts": {"READ_CONTACTS", "WRITE_CONTACTS", "GET_ACCOUNTS"},
    "camera": {"CAMERA"},
    "microphone": {"RECORD_AUDIO"},
    "phone": {"READ_PHONE_STATE", "CALL_PHONE", "READ_PHONE_NUMBERS"},
    "device_information": {"READ_PHONE_STATE"},      # IMEI 等设备标识靠它
    "sms": {"READ_SMS", "SEND_SMS", "RECEIVE_SMS"},
    "files": {"READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "MANAGE_EXTERNAL_STORAGE"},
    "media": {"READ_EXTERNAL_STORAGE"},
    "photos": {"READ_MEDIA_IMAGES", "READ_MEDIA_VIDEO", "READ_EXTERNAL_STORAGE"},
    "calendar": {"READ_CALENDAR", "WRITE_CALENDAR"},
    "biometric": {"USE_BIOMETRIC", "USE_FINGERPRINT"},
    "account": {"GET_ACCOUNTS"},
}

UNIDENTIFIED = "未识别三方包（待分析）"


def component_prefixes(components: list[dict]) -> list[tuple[str, dict, str]]:
    """从知识库组件推出可用于归因的包前缀，并记下依据。

    知识库登记了多种指纹，**只有 PACKAGE_PREFIX 能直接当包前缀用**；但不少组件
    （实测百度定位 SDK）只登记了 `CLASS`，如 `com.baidu.location.f` —— 它的包前缀
    `com.baidu.location` 同样能框住 `com.baidu.location.b/.indoor/.e` 这些调用点。
    按类名退一级取包名属于**推断**，因此把依据一并带出来，界面上要与确证区分。
    """
    out = []
    for comp in components:
        if comp.get("prefix"):
            out.append((comp["prefix"], comp, "PACKAGE_PREFIX"))
        elif comp.get("class_name"):
            package = comp["class_name"].rsplit(".", 1)[0]
            if package.count(".") >= 2:      # 至少三段，避免把 com.foo 这种当包名
                out.append((package, comp, "CLASS_INFERRED"))
    return sorted(out, key=lambda x: -len(x[0]))


def _caller_class(caller: str | None) -> str:
    """从调用点里取出类名。

    形态不统一：`<com.a.B: void c()>`，也有字符串化的列表
    `['<com.a.B: void c()>->$r5']`。按 `<` 剥前缀会漏掉后者（列表以 `['` 开头），
    于是类名带着 `['` 去比对、**所有归因静默失配** —— 实测踩到过。
    """
    if not caller:
        return ""
    match = re.search(r"<([A-Za-z0-9_$.]+):", caller)
    if match:
        return match.group(1)
    return caller.strip().lstrip("<").split(":")[0]


def _owner_of(caller: str | None, prefixes: list[tuple[str, dict, str]], app_prefix: str) -> dict:
    """把一个调用点归因到：应用自身 / 某个 SDK / 未识别。

    取**最长匹配**的包前缀——`com.a.b` 与 `com.a.b.c` 同时命中时，后者更具体。
    """
    if not caller:
        return {"kind": "unknown", "name": "（调用点缺失）"}
    cls = _caller_class(caller)
    if app_prefix and cls.startswith(app_prefix):
        return {"kind": "self", "name": "应用自身", "component_kind": None}
    best = None
    for prefix, comp, basis in prefixes:
        if cls.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, comp, basis)
    if not best:
        return {"kind": "unknown", "name": UNIDENTIFIED}
    _, comp, basis = best
    return {"kind": "third_party", "name": comp["name"],
            "vendor": comp.get("vendor"), "component_kind": comp.get("component_kind"),
            "attribution_basis": basis,
            # 匹配强度一并带出：CANDIDATE 只是候选，界面上不得显示得和确证一样确定
            "match_status": comp.get("hit_status")}


def _collect_modes(observations: list[dict]) -> list[str]:
    modes = []
    for o in observations:
        if o["observation_type"] == "security.sensitive_api":
            key = "sensitive_api"
        elif o["observation_type"] == "dataflow.privacy":
            key = o.get("sink_type") or "unknown"
        else:
            continue
        label = COLLECT_MODE_CN.get(key)
        if label and label not in modes:
            modes.append(label)
    return modes


def _code_locations(observations: list[dict], limit: int = 200) -> list[dict]:
    """代码位置：类.方法 + 该位置上的观察 id（前端据此下钻引擎代码）。"""
    seen = {}
    for o in observations:
        caller = (o.get("payload") or {}).get("caller") or o.get("subject")
        if not caller:
            continue
        if caller not in seen:
            seen[caller] = {"location": caller, "observation_id": o["id"],
                            "has_code": bool((o.get("payload") or {}).get("url"))}
    return list(seen.values())[:limit]


def build_profile(observations: list[dict], sdk_components: list[dict],
                  permission_kb: dict[str, dict], app_package: str = "") -> dict:
    """聚合成合规画像。

    `observations` 需要带平台语义字段（data_category/sink_type/provider_rule_id…）；
    `sdk_components` 是知识库匹配到的组件（含 PACKAGE_PREFIX 前缀）；
    `permission_kb` 是 权限名 → 知识库条目（中文类别/能力/合规要点/风险等级）。
    """
    prefixes = component_prefixes(sdk_components)
    app_prefix = app_package or ""

    # 逐条观察归因
    buckets = defaultdict(list)          # (owner_key, data_category) -> [obs]
    owners = {}
    for o in observations:
        category = o.get("data_category")
        if not category or o["observation_type"] not in ("dataflow.privacy", "security.sensitive_api"):
            continue
        owner = _owner_of((o.get("payload") or {}).get("caller"), prefixes, app_prefix)
        key = (owner["kind"], owner["name"])
        owners[key] = owner
        buckets[(key, category)].append(o)

    def group(kind: str) -> list[dict]:
        items = []
        for (owner_key, category), obs in buckets.items():
            if owner_key[0] != kind:
                continue
            items.append({
                "data_category": category,
                "data_category_cn": DATA_CATEGORY_CN.get(category, category),
                "sensitive": category in SENSITIVE_CATEGORIES,
                "requires_permission": category not in NO_PERMISSION_CATEGORIES,
                "collect_modes": _collect_modes(obs),
                "call_site_count": len(obs),
                "method_count": len({(o.get("payload") or {}).get("caller") for o in obs
                                     if (o.get("payload") or {}).get("caller")}),
                "declared_in_policy": None,   # 无数据，不编造
                "necessary": None,
                "owner": owners[owner_key],
                "code_locations": _code_locations(obs),
            })
        return sorted(items, key=lambda x: -x["call_site_count"])

    # 4.2 权限：声明的权限 × 实际调用点（按权限守护的数据类目连接）
    permissions = _permission_rows(observations, permission_kb)

    return {
        "collect_app_self": group("self"),
        "collect_third_party": group("third_party"),
        "collect_unidentified": group("unknown"),
        "unattributed_packages": _unattributed_packages(buckets),
        "permissions": permissions,
        "policy_available": False,
        "notes": [
            "「是否在隐私政策中声明」「必要/非必要」需要隐私政策解析，平台当前无该数据，"
            "一律显示为「无数据」——不得显示为「否」。",
            "收集方式只声明引擎证明了的那一层：调用 API 只是「读取」的证据，不等同于数据已被取走。",
        ],
    }


def _canonical_permission(name: str) -> str:
    """权限名归一化：Androguard 报短名（ACCESS_FINE_LOCATION），AppShark/MobSF 报全名
    （android.permission.ACCESS_FINE_LOCATION）。不归一化的话同一条权限会出现两行，
    一行有知识库说明、一行没有 —— 看起来像两条不同的权限。"""
    short = name.strip()
    for prefix in ("android.permission.", "com.android.permission."):
        if short.startswith(prefix):
            short = short[len(prefix):]
    return short


def _unattributed_packages(buckets: dict) -> list[dict]:
    """把「未归因」的调用点按包前缀聚合。

    这是「暂时无法识别」的第二个层面：**调用点的包不在知识库里**（SdkPanel 展示的
    「未识别包簇」是另一回事——那是 manifest 组件没匹配上）。两个层面都要给用户看，
    否则 595 处采集点就是一片「未识别」，看不出集中在哪几个包。
    """
    agg: dict[str, dict] = {}
    for (owner_key, category), obs in buckets.items():
        if owner_key[0] != "unknown":
            continue
        for o in obs:
            cls = _caller_class((o.get("payload") or {}).get("caller"))
            if not cls:
                continue
            parts = cls.split(".")
            prefix = ".".join(parts[:3]) if len(parts) >= 3 else cls
            item = agg.setdefault(prefix, {"package_prefix": prefix, "call_site_count": 0,
                                           "categories": set(), "sample": cls})
            item["call_site_count"] += 1
            item["categories"].add(category)
    out = [dict(v, categories=sorted(v["categories"])) for v in agg.values()]
    return sorted(out, key=lambda x: -x["call_site_count"])


def load_profile(db: Session, task) -> dict:
    """从库里装配合规画像（供接口调用）。

    SDK 归因依赖「组件 → 包名前缀」指纹：知识库里匹配到组件、且该组件登记了
    PACKAGE_PREFIX 的，才能把调用点归到它头上；没登记的进「未识别三方包」。
    这是**刻意保守**的：宁可说不知道，也不要把某个 SDK 的采集算成应用自身。
    """
    from sqlalchemy import text

    from app.models import AppVersion, EngineObservation
    from app.services.observation_service import observation_view

    observations = []
    for row in db.query(EngineObservation).filter(EngineObservation.task_id == task.id).all():
        view = observation_view(row)
        view["payload"] = row.payload or {}
        observations.append(view)

    components = [dict(r) for r in db.execute(text("""
        SELECT c.name, c.component_kind, v.name AS vendor, h.hit_status,
               max(f.value) FILTER (WHERE f.fingerprint_type = 'PACKAGE_PREFIX') AS prefix,
               max(f.value) FILTER (WHERE f.fingerprint_type = 'CLASS') AS class_name
        FROM privacy_scan.app_build b
        JOIN privacy_scan.scan_job j ON j.app_build_id = b.id
        JOIN privacy_scan.component_hit h ON h.scan_job_id = j.id
             AND h.hit_status <> 'REJECTED'
        JOIN privacy_kb.component c ON c.id = h.component_id
        LEFT JOIN privacy_kb.vendor v ON v.id = c.vendor_id
        JOIN privacy_kb.component_fingerprint f ON f.component_id = c.id
             AND f.fingerprint_type IN ('PACKAGE_PREFIX', 'CLASS')
        WHERE b.build_key = :key
        GROUP BY c.name, c.component_kind, v.name, h.hit_status
    """), {"key": f"task:{task.id}"}).mappings().all()]

    permission_kb = {
        r[0]: dict(zip(("category", "capability", "permission_type", "risk_level",
                        "compliance_focus"), r[1:]))
        for r in db.execute(text(
            "SELECT permission_name, category, capability, permission_type, risk_level, "
            "compliance_focus FROM privacy_kb.permission")).all()}

    version = db.query(AppVersion).get(task.app_version_id)
    package = version.app.package_name if version and version.app else ""
    return build_profile(observations, components, permission_kb, package or "")


def _permission_rows(observations: list[dict], permission_kb: dict) -> list[dict]:
    """权限行：知识库给中文说明，观察给「实际调用点」。

    「可能使用」= 权限被声明（引擎从 manifest 解析出来）；
    「实际使用」= 有调用点落在该权限守护的数据类目上。两者并列才看得出权限是否过量。

    **权限不在守护映射里时，绝不能推出「申请了没用」**——那只是我们不知道它守护什么。
    `guard_mapped=False` 就是给界面看的：这一行只能显示「无法判定」。
    """
    declared: dict[str, set[str]] = defaultdict(set)   # 权限名 -> 来源引擎
    for o in observations:
        if o["observation_type"] in ("fact.permission", "security.permission",
                                     "fact.sensitive_permission"):
            raw = (o.get("payload") or {}).get("permission") or o.get("subject")
            if raw:
                declared[_canonical_permission(raw)].add(o.get("engine_type") or "unknown")

    by_category = defaultdict(list)
    for o in observations:
        if o.get("data_category"):
            by_category[o["data_category"]].append(o)

    rows = []
    for name, engines in declared.items():
        short = name
        kb = permission_kb.get("android.permission." + short) or permission_kb.get(short) or {}
        guards = sorted(cat for cat, perms in PERMISSION_GUARDS.items() if short in perms)
        obs = [o for c in guards for o in by_category.get(c, [])]
        rows.append({
            "permission": short,
            "permission_full": "android.permission." + short,
            "category_cn": kb.get("category"),
            "capability": kb.get("capability"),
            "permission_type": kb.get("permission_type"),
            "risk_level": kb.get("risk_level"),
            "compliance_focus": kb.get("compliance_focus"),
            "kb_available": bool(kb),
            "declared_by": sorted(engines),
            "guards": guards,
            "guard_mapped": bool(guards),
            "call_site_count": len(obs),
            "method_count": len({(o.get("payload") or {}).get("caller") for o in obs
                                 if (o.get("payload") or {}).get("caller")}),
            "code_locations": _code_locations(obs),
            "declared_in_policy": None,   # 无政策数据，不编造
        })
    return sorted(rows, key=lambda r: (not r["guard_mapped"],
                                       r["risk_level"] != "CRITICAL",
                                       -r["call_site_count"]))
