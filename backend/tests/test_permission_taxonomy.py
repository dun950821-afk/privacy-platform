"""平台词表与「普通 App 可达」判定。

Android 实测 1018 处带 protectionLevel 的声明里 855 处是签名/特殊级——普通 App
声明了也拿不到。可达性判定收敛在这个模块，API 与页面共用，不各自硬编码。
"""
import pytest

from app.services.permission_taxonomy import (
    ANDROID_PROTECTION_LEVEL_MAP, PARSER_PRODUCIBLE_TYPES,
    PERMISSION_TYPES_BY_PLATFORM, PLATFORMS,
    is_applicable, map_android_protection_level, validate_permission_type,
)


def test_platforms_are_exactly_three():
    assert PLATFORMS == ("ANDROID", "IOS", "HARMONYOS")
    assert set(PERMISSION_TYPES_BY_PLATFORM) == set(PLATFORMS)


def test_android_map_covers_the_four_real_levels():
    # 实测清单里出现的主级别就这些
    assert map_android_protection_level("dangerous") == "危险权限"
    assert map_android_protection_level("normal") == "普通权限"
    assert map_android_protection_level("signature") == "签名权限"
    assert map_android_protection_level("internal") == "特殊权限"
    # 映射的每个落点都必须是受控词表里的取值——否则导入侧 validate 会把整批跳过
    assert set(ANDROID_PROTECTION_LEVEL_MAP.values()) <= set(PERMISSION_TYPES_BY_PLATFORM["ANDROID"])


def test_android_map_ignores_trailing_flags():
    # 清单里有 `dangerous|privileged` 这种形态，附加标志不影响主级别
    assert map_android_protection_level("dangerous|privileged") == "危险权限"
    assert map_android_protection_level("signature|privileged") == "签名权限"


def test_android_map_of_unknown_level_is_undecided_not_fabricated():
    """没见过的级别标「未标注」，不猜。"""
    assert map_android_protection_level("brand_new_level") == "未标注"


def test_applicable_true_for_dangerous_and_normal():
    assert is_applicable("ANDROID", "危险权限", None) is True
    assert is_applicable("ANDROID", "危险权限（受限）", None) is True
    assert is_applicable("ANDROID", "普通权限", None) is True


def test_applicable_false_for_signature_and_special():
    assert is_applicable("ANDROID", "签名权限", None) is False
    assert is_applicable("ANDROID", "特殊权限", None) is False


def test_appop_flag_lifts_signature_level_to_reachable():
    """`signature|appop` 不是签名权限：AppOps 让普通 App 能在设置页拿到它。

    只认 `|` 前的主级别会把 SYSTEM_ALERT_WINDOW / WRITE_SETTINGS / SCHEDULE_EXACT_ALARM
    这类整批判成「签名权限」→ 不可达 → 被界面默认的「只看应用可申请」隐藏。
    """
    assert map_android_protection_level("signature|appop|pre23|development") \
        == "特殊权限（AppOps 可授权）"
    assert is_applicable("ANDROID", "特殊权限（AppOps 可授权）", None) is True
    # 主级别是 internal 的那一处（CAPTURE_CONSENTLESS_BUGREPORT_ON_USERDEBUG_BUILD）同理
    assert map_android_protection_level("internal|appop") == "特殊权限（AppOps 可授权）"


def test_appop_does_not_override_an_already_reachable_main_level():
    """`dangerous|appop` 该按主级别走，不能被 appop 规则改成第三种取值。"""
    assert map_android_protection_level("dangerous|appop") == "危险权限"
    assert map_android_protection_level("normal|appop|instant") == "普通权限"
    assert map_android_protection_level("normal|appop") == "普通权限"


def test_signature_without_appop_stays_unreachable():
    """没有 appop 就是签名权限，不能被上一条测试的规则顺手放过。"""
    assert map_android_protection_level("signature") == "签名权限"
    assert map_android_protection_level("signature|privileged") == "签名权限"
    assert is_applicable("ANDROID", "签名权限", None) is False


def test_appop_type_is_parser_producible():
    """新取值必须算「机器推得出来」，否则 M' 保护会把它当成人工值而永久冻结。"""
    assert "特殊权限（AppOps 可授权）" in PARSER_PRODUCIBLE_TYPES["ANDROID"]


def test_deprecated_permission_is_still_reachable():
    """弃用是时间维度，可达是授权维度，两者正交。

    最尖锐的例子：`android.permission.BLUETOOTH` 在 AOSP 里是 `normal`（安装即授），
    无数 App 至今仍在声明。把「已弃用」当成「拿不到」会得出「普通 App 申请不到蓝牙」。
    """
    assert is_applicable("ANDROID", "已弃用权限", None) is True


def test_harmonyos_applicable_needs_user_grant_or_normal():
    assert is_applicable("HARMONYOS", "normal", "用户授权（user_grant）") is True
    assert is_applicable("HARMONYOS", "system_basic", "用户授权（user_grant）") is True
    assert is_applicable("HARMONYOS", "system_basic", "系统授权（system_grant）") is False


def test_ios_usage_keys_are_all_applicable():
    assert is_applicable("IOS", "用法描述键", None) is True


def test_validate_rejects_android_type_on_ios():
    with pytest.raises(ValueError):
        validate_permission_type("IOS", "危险权限")
    validate_permission_type("IOS", "用法描述键")  # 不抛


def test_validate_rejects_unknown_platform():
    with pytest.raises(ValueError):
        validate_permission_type("WINDOWS", "普通权限")
