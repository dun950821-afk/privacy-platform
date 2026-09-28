"""平台词表与「普通 App 可达」判定。

Android 实测 1018 条里 875 条是签名/系统级——普通 App 声明了也拿不到。
可达性判定收敛在这个模块，API 与页面共用，不各自硬编码。
"""
import pytest

from app.services.permission_taxonomy import (
    ANDROID_PROTECTION_LEVEL_MAP, PERMISSION_TYPES_BY_PLATFORM, PLATFORMS,
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
