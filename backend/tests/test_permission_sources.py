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
