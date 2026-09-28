"""三个平台的来源文件解析器。纯函数：文本进、行字典出，不碰 IO 也不碰库。"""
from pathlib import Path

from app.services.permission_sources import parse_android_manifest

FIXTURES = Path(__file__).parent / "fixtures" / "permission_sources"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_android_parse_dedupes_by_name():
    """同一权限名在清单里可能出现多次（不同 protectionLevel），按名归并。"""
    rows = parse_android_manifest(_read("android_manifest_sample.xml"))
    names = [r["permission_name"] for r in rows]
    assert len(names) == len(set(names)), "同名不该出两行"
    assert names.count("android.permission.CAMERA") == 1


def test_android_parse_maps_protection_level():
    rows = {r["permission_name"]: r for r in parse_android_manifest(_read("android_manifest_sample.xml"))}
    assert rows["android.permission.CAMERA"]["permission_type"] == "危险权限"
    assert rows["android.permission.ACCESS_NETWORK_STATE"]["permission_type"] == "普通权限"
    assert rows["android.permission.BIND_ACCESSIBILITY_SERVICE"]["permission_type"] == "签名权限"
    assert rows["android.permission.CONFIGURE_WIFI_DISPLAY"]["permission_type"] == "特殊权限"


def test_android_parse_keeps_all_protection_levels_in_raw_data():
    """归并时取更宽的主级别，但出现过哪些级别要留在 raw_data 里备查。"""
    rows = {r["permission_name"]: r for r in parse_android_manifest(_read("android_manifest_sample.xml"))}
    raw = rows["android.permission.CAMERA"]["raw_data"]
    assert sorted(raw["protection_levels_seen"]) == ["dangerous", "dangerous|privileged"]


def test_android_parse_leaves_capability_empty():
    """AOSP core 清单不提供描述文本。留空是正确结果，不填占位。"""
    rows = parse_android_manifest(_read("android_manifest_sample.xml"))
    assert all(r["capability"] is None for r in rows)


def test_android_parse_sets_official_reference():
    rows = {r["permission_name"]: r for r in parse_android_manifest(_read("android_manifest_sample.xml"))}
    assert rows["android.permission.CAMERA"]["official_reference"].startswith(
        "https://developer.android.com/reference/android/Manifest.permission#")


def test_android_parse_duplicate_name_keeps_the_more_restrictive_level():
    """同名但主级别不同时，取**更严**的那一级。

    方向是刻意的：`is_applicable` 拿 `permission_type` 决定「普通 App 能不能申请」，
    把签名级权限报成可达，会让默认视图里混进根本申请不到的条目。

    fixture 里那条 CAMERA 重复项两次声明的主级别都是 `dangerous`，**触发不了这个分支**
    ——所以必须在这里用不同主级别的重名钉住它，否则把 `>` 写成 `<` 也不会有测试变红。
    """
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="android">'
        '<permission android:name="android.permission.DUP" android:protectionLevel="normal" />'
        '<permission android:name="android.permission.DUP" android:protectionLevel="signature" />'
        '</manifest>'
    )
    rows = {r["permission_name"]: r for r in parse_android_manifest(xml)}
    assert rows["android.permission.DUP"]["permission_type"] == "签名权限"
    assert rows["android.permission.DUP"]["raw_data"]["protection_levels_seen"] == ["normal", "signature"]


from app.services.permission_sources import parse_harmonyos_doc


def test_harmonyos_parse_extracts_name_and_level():
    rows = {r["permission_name"]: r for r in parse_harmonyos_doc(_read("harmonyos_sample.md"))}
    assert set(rows) == {"ohos.permission.ACCESS_BLUETOOTH", "ohos.permission.MEDIA_LOCATION"}
    assert rows["ohos.permission.ACCESS_BLUETOOTH"]["permission_type"] == "normal"


def test_harmonyos_parse_captures_description_and_grant_mode():
    rows = {r["permission_name"]: r for r in parse_harmonyos_doc(_read("harmonyos_sample.md"))}
    bt = rows["ohos.permission.ACCESS_BLUETOOTH"]
    assert bt["capability"].startswith("允许应用接入蓝牙")
    assert "user_grant" in bt["grant_mode"]
    assert bt["raw_data"]["since_api"] == "10"


def test_harmonyos_parse_skips_section_without_fields():
    """缺结构化字段的小节跳过——宁可少收，不编造级别。"""
    rows = parse_harmonyos_doc(_read("harmonyos_sample.md"))
    assert all(r["permission_name"] != "ohos.permission.NOT_A_REAL_EXAMPLE_WITHOUT_FIELDS" for r in rows)
