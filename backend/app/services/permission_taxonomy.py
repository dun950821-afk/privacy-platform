"""权限的平台维度：受控词表与「普通 App 可达」判定。

三个平台的权限命名体系与级别体系都不同，所以词表按平台各一套：

    Android    android.permission.CAMERA
    鸿蒙        ohos.permission.CAMERA
    iOS        NSCameraUsageDescription

`permission_type` 曾是 39 个自由文本取值，收敛成 Android 那一套之后又被加平台撑开，
所以这里按平台分别受控，写入侧校验只在 validate_permission_type 一处做。
"""

PLATFORMS = ("ANDROID", "IOS", "HARMONYOS")

# 每个平台的 permission_type 受控词表
PERMISSION_TYPES_BY_PLATFORM: dict[str, tuple[str, ...]] = {
    "ANDROID": ("危险权限", "危险权限（受限）", "普通权限", "签名权限",
                "特殊权限", "特殊权限（AppOps 可授权）", "已弃用权限", "三方声明权限", "未标注"),
    # 鸿蒙文档给的是「权限级别」；授权方式（user_grant/system_grant）走 grant_mode
    "HARMONYOS": ("normal", "system_basic", "system_core"),
    "IOS": ("用法描述键",),
}

# Android protectionLevel 主级别 → permission_type。
# `|` 之后的附加标志（privileged / development / instant 等）只记进 raw_data，
# 不影响主级别——**唯一的例外是 appop**，见 _APPOP_TYPE 与 map_android_protection_level。
ANDROID_PROTECTION_LEVEL_MAP = {
    "dangerous": "危险权限",
    "normal": "普通权限",
    "signature": "签名权限",
    "internal": "特殊权限",
    "system": "特殊权限",
    "role": "特殊权限",
    "module": "特殊权限",
}

# `protectionLevel="signature|appop"` 这类声明的落点。
#
# appop 不是又一个「主级别」，而是「这条权限另有 AppOps 开关」这个事实：主级别说
# 「声明者得是签名应用」，appop 说「系统设置页/AppOps 可以让普通应用拿到它」。
# 真实清单里 appop 出现在 22 处声明上，其中 19 处主级别是 signature——只认主级别
# 会把 SYSTEM_ALERT_WINDOW / WRITE_SETTINGS / SCHEDULE_EXACT_ALARM /
# REQUEST_INSTALL_PACKAGES / PACKAGE_USAGE_STATS / MANAGE_EXTERNAL_STORAGE 这些
# **普通 App 明明能在设置页申请到**的权限判成「签名权限」→ 不可达 → 被界面默认的
# 「只看应用可申请」整批隐藏。所以它必须有自己的一格，且算可达。
_APPOP_TYPE = "特殊权限（AppOps 可授权）"

# 普通 App 真能申请的 Android 类型。AOSP 清单里 1018 处带 protectionLevel 的声明，
# 只有 163 处落在这里——补上 appop 与已弃用两档之前是 143 处（差的 20 处就是那批
# 「主级别 signature、但带 appop 标志」的权限）。
#
# `已弃用权限` 也在集合里：**弃用是时间维度，可达是授权维度，两者正交。**
# 最尖锐的例子是 `android.permission.BLUETOOTH`——AOSP 里它就是 `normal`
# （安装即授），无数 App 至今还在声明，只是被 BLUETOOTH_SCAN/CONNECT 等细分权限
# 取代了。把「已弃用」当成「拿不到」会得出「普通 App 申请不到蓝牙」这种假结论。
# 弃用该由 raw_data / 人工说明去表达，不该借可达性这一格来藏。
_ANDROID_APPLICABLE = {"危险权限", "危险权限（受限）", "普通权限",
                       _APPOP_TYPE, "已弃用权限"}

# 各平台**解析器自己能产出**的 permission_type 取值。
#
# 导入时用它判「库里已有的值要不要让机器覆盖」：值在集合里 → 机器能自己算出来，
# 让它更新（否则 AOSP 的重新分类永远进不来，全库冻结）；不在集合里 → 那是人工判定的、
# 机器推不出来的知识（如 `已弃用权限`/`危险权限（受限）`/`三方声明权限`），不得覆盖。
PARSER_PRODUCIBLE_TYPES: dict[str, set[str]] = {
    "ANDROID": set(ANDROID_PROTECTION_LEVEL_MAP.values()) | {_APPOP_TYPE, "未标注"},
    "HARMONYOS": set(PERMISSION_TYPES_BY_PLATFORM["HARMONYOS"]),
    "IOS": set(PERMISSION_TYPES_BY_PLATFORM["IOS"]),
}


def map_android_protection_level(raw: str | None) -> str:
    """protectionLevel → permission_type。

    没见过的级别返回「未标注」——**不猜**。清单里出现过 role/system/module 这类
    只占个位数的级别，猜错比留白更糟。

    **唯一不是「只看 `|` 前」的地方是 appop**：主级别映射出的类型不可达、而标志里
    有 appop 时，落 `特殊权限（AppOps 可授权）`。主级别本就可达的（`dangerous|appop`、
    `normal|appop|instant`）仍按主级别走，不被这条覆盖——appop 只用来把「签名级别
    但 AppOps 可授权」的这批从不可达里捞出来，不该改写已经可达的判定。
    """
    if not raw:
        return "未标注"
    parts = [p.strip().lower() for p in raw.split("|")]
    mapped = ANDROID_PROTECTION_LEVEL_MAP.get(parts[0], "未标注")
    if mapped not in _ANDROID_APPLICABLE and "appop" in parts[1:]:
        return _APPOP_TYPE
    return mapped


def is_applicable(platform: str, permission_type: str | None, grant_mode: str | None) -> bool:
    """这条权限普通 App 有没有可能申请到。

    Android：签名/系统级普通 App 声明了也拿不到，不算可达。
    鸿蒙：用户授权类可达；系统授权类不可达。
    iOS：用法描述键都是开发者要声明的，全可达。
    """
    if platform == "ANDROID":
        return (permission_type or "") in _ANDROID_APPLICABLE
    if platform == "HARMONYOS":
        if grant_mode and "user_grant" in grant_mode:
            return True
        return (permission_type or "") == "normal"
    if platform == "IOS":
        return True
    return False


def validate_permission_type(platform: str, permission_type: str | None) -> None:
    """写入侧校验。非法值抛 ValueError，由 API 层转成 400。"""
    if platform not in PERMISSION_TYPES_BY_PLATFORM:
        raise ValueError(f"platform 只能是：{'、'.join(PLATFORMS)}")
    if permission_type is None:
        return
    allowed = PERMISSION_TYPES_BY_PLATFORM[platform]
    if permission_type not in allowed:
        raise ValueError(
            f"{platform} 的 permission_type 只能是：{'、'.join(allowed)}")
