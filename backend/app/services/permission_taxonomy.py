"""权限的平台维度：受控词表与「普通 App 可达」判定。

三个平台的权限命名体系与级别体系都不同，所以词表按平台各一套：

    Android    android.permission.CAMERA
    鸿蒙        ohos.permission.CAMERA
    iOS        NSCameraUsageDescription

`permission_type` 曾是 39 个自由文本取值，收敛成 Android 那 8 个之后又被加平台撑开，
所以这里按平台分别受控，写入侧校验只在 validate_permission_type 一处做。
"""

PLATFORMS = ("ANDROID", "IOS", "HARMONYOS")

# 每个平台的 permission_type 受控词表
PERMISSION_TYPES_BY_PLATFORM: dict[str, tuple[str, ...]] = {
    "ANDROID": ("危险权限", "危险权限（受限）", "普通权限", "签名权限",
                "特殊权限", "已弃用权限", "三方声明权限", "未标注"),
    # 鸿蒙文档给的是「权限级别」；授权方式（user_grant/system_grant）走 grant_mode
    "HARMONYOS": ("normal", "system_basic", "system_core"),
    "IOS": ("用法描述键",),
}

# Android protectionLevel 主级别 → permission_type。
# `|` 之后的附加标志（privileged / development / instant 等）只记进 raw_data，
# 不影响主级别。
ANDROID_PROTECTION_LEVEL_MAP = {
    "dangerous": "危险权限",
    "normal": "普通权限",
    "signature": "签名权限",
    "internal": "特殊权限",
    "system": "特殊权限",
    "role": "特殊权限",
    "module": "特殊权限",
}

# 普通 App 真能申请的 Android 类型。实测 1018 条里只有 143 条落在这里。
_ANDROID_APPLICABLE = {"危险权限", "危险权限（受限）", "普通权限"}

# 各平台**解析器自己能产出**的 permission_type 取值。
#
# 导入时用它判「库里已有的值要不要让机器覆盖」：值在集合里 → 机器能自己算出来，
# 让它更新（否则 AOSP 的重新分类永远进不来，全库冻结）；不在集合里 → 那是人工判定的、
# 机器推不出来的知识（如 `已弃用权限`/`危险权限（受限）`/`三方声明权限`），不得覆盖。
PARSER_PRODUCIBLE_TYPES: dict[str, set[str]] = {
    "ANDROID": set(ANDROID_PROTECTION_LEVEL_MAP.values()) | {"未标注"},
    "HARMONYOS": set(PERMISSION_TYPES_BY_PLATFORM["HARMONYOS"]),
    "IOS": set(PERMISSION_TYPES_BY_PLATFORM["IOS"]),
}


def map_android_protection_level(raw: str | None) -> str:
    """protectionLevel → permission_type。

    没见过的级别返回「未标注」——**不猜**。清单里出现过 role/system/module 这类
    只占个位数的级别，猜错比留白更糟。
    """
    if not raw:
        return "未标注"
    main = raw.split("|")[0].strip().lower()
    return ANDROID_PROTECTION_LEVEL_MAP.get(main, "未标注")


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
