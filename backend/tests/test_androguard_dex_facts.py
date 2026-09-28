import struct
import zipfile

import pytest

from app.engine.runners.androguard_runner import (
    _dex_class_count, _dex_declared_classes, _dex_method_count, _missing_component_classes,
    _scan_dex, collect_facts)

# DEX 头部里 class_defs_size 在 0x60，class_defs_off 在 0x64。两者相邻、同为 4 字节
# 小端，因此**必须给它们不同的值**，否则读错位置照样通过——本文件此前正是这样：
# 假 DEX 把类数写进 0x64，与实现的错误偏移互相印证，测试全绿而线上数值是字节偏移。
CLASS_DEFS_SIZE_OFF = 0x60
CLASS_DEFS_OFF_OFF = 0x64
SENTINEL_OFFSET = 0x00BADBAD


def _fake_dex(class_count: int, payload: bytes = b"") -> bytes:
    header = bytearray(112)
    header[0:8] = b"dex\n035\x00"
    header[CLASS_DEFS_SIZE_OFF:CLASS_DEFS_SIZE_OFF + 4] = struct.pack("<I", class_count)
    header[CLASS_DEFS_OFF_OFF:CLASS_DEFS_OFF_OFF + 4] = struct.pack("<I", SENTINEL_OFFSET)
    return bytes(header) + payload


def test_dex_class_count_reads_header():
    assert _dex_class_count(_fake_dex(1234)) == 1234
    assert _dex_class_count(b"not a dex") == 0


def test_dex_class_count_is_not_the_byte_offset_field():
    """读成相邻的 class_defs_off 会得到一个「像数字的」字节偏移，不会报错。

    真实样本上就这么错过一次：某加固 APK 的 classes.dex 真实类数是 4，被读成 9784
    ——9784 正是该 DEX 里类定义区的起始偏移。这条断言把两个字段区分开。
    """
    data = _fake_dex(4)
    assert _dex_class_count(data) == 4
    assert _dex_class_count(data) != SENTINEL_OFFSET


def test_real_dex_header_is_read_correctly():
    """用规范里的真实字段互相印证：类数不该等于同头部里的字节偏移。"""
    header = bytearray(112)
    header[0:8] = b"dex\n035\x00"
    struct.pack_into("<I", header, 0x38, 699)     # string_ids_size
    struct.pack_into("<I", header, 0x58, 381)     # method_ids_size
    struct.pack_into("<I", header, CLASS_DEFS_SIZE_OFF, 4)
    struct.pack_into("<I", header, CLASS_DEFS_OFF_OFF, 9784)
    assert _dex_class_count(bytes(header)) == 4


def test_scan_dex_extracts_endpoints_and_native_libs(tmp_path):
    apk = tmp_path / "app.apk"
    dex = _fake_dex(42, b"https://api.example.com/v1 android.telephony.TelephonyManager getDeviceId")
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("classes.dex", dex)
        zf.writestr("lib/arm64-v8a/libnative.so", b"\x7fELF")
    facts = _scan_dex(str(apk), {})
    assert facts["class_count"] == 42
    assert "https://api.example.com/v1" in facts["urls"]
    assert "libnative.so" in facts["native_libraries"]
    assert any(a["api"] == "getDeviceId" for a in facts["sensitive_apis"])


def test_scan_dex_respects_disabled_flags(tmp_path):
    apk = tmp_path / "app.apk"
    dex = _fake_dex(1, b"https://api.example.com")
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("classes.dex", dex)
    facts = _scan_dex(str(apk), {"extract_endpoints": False, "analyze_sensitive_apis": False})
    assert facts["urls"] == []
    assert facts["sensitive_apis"] == []


# ---------- DEX 类名表：与 manifest 组件类比对 ----------

def _uleb(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _fake_dex_with_classes(descriptors: list[str], method_ids: int = 0) -> bytes:
    """构造一个只含 headers/三张表的最小 DEX，用于验证类名解析。"""
    blob, offsets = b"", []
    for name in descriptors:
        offsets.append(112 + len(blob))
        raw = name.encode()
        blob += _uleb(len(raw)) + raw + b"\0"
    str_ids_off = 112 + len(blob)
    str_ids = b"".join(struct.pack("<I", off) for off in offsets)
    type_ids_off = str_ids_off + len(str_ids)
    type_ids = b"".join(struct.pack("<I", i) for i in range(len(descriptors)))   # type i → string i
    class_defs_off = type_ids_off + len(type_ids)
    class_defs = b"".join(struct.pack("<I", i) + b"\0" * 28 for i in range(len(descriptors)))

    header = bytearray(112)
    header[0:8] = b"dex\n035\0"
    struct.pack_into("<I", header, 0x38, len(descriptors))
    struct.pack_into("<I", header, 0x3C, str_ids_off)
    struct.pack_into("<I", header, 0x40, len(descriptors))
    struct.pack_into("<I", header, 0x44, type_ids_off)
    struct.pack_into("<I", header, 0x58, method_ids)
    struct.pack_into("<I", header, 0x60, len(descriptors))
    struct.pack_into("<I", header, 0x64, class_defs_off)
    return bytes(header) + blob + str_ids + type_ids + class_defs


def test_dex_method_count_reads_its_own_field():
    """方法数在 0x58，与 0x60 的类数相邻——同样必须区分开。"""
    dex = _fake_dex_with_classes(["Lcom/a/B;"], method_ids=777)
    assert _dex_method_count(dex) == 777
    assert _dex_class_count(dex) == 1
    assert _dex_method_count(_fake_dex_with_classes(["Lcom/a/B;"], method_ids=1)) == 1


def test_declared_classes_are_returned_as_descriptors():
    names = {"Lcom/example/a/A;", "Lcom/example/a/B;", "Landroidx/core/C;"}
    assert _dex_declared_classes(_fake_dex_with_classes(sorted(names))) == names


def test_declared_classes_returns_none_when_unreadable():
    """读不出来必须返回 None，不能返回空集——空集会被当成"没有类"，从而把正常的说成异常。"""
    assert _dex_declared_classes(b"not a dex") is None
    assert _dex_declared_classes(b"") is None
    # 表规模明显不合理（等于文件被破坏）时放弃
    broken = bytearray(_fake_dex_with_classes(["Lcom/a/B;"]))
    struct.pack_into("<I", broken, 0x60, 10 ** 7)
    assert _dex_declared_classes(bytes(broken)) is None


def test_missing_component_classes_distinguishes_all_missing_from_normal():
    """全部缺失 = 加固壳；部分缺失 ≠ 分析没覆盖到（活动别名、插件包都会造成个别缺失）。"""
    all_classes = {"Lcom/a/A;", "Lcom/b/B;"}
    components = {"com.a.A", "com.b.B"}
    assert _missing_component_classes(components, all_classes, readable=True) == set()

    shell = _missing_component_classes(components, {"Lcom/shell/S;"}, readable=True)
    assert shell == components, "DEX 里没有应用自己的类时，组件类应全部缺失"


def test_missing_component_classes_returns_none_when_not_readable():
    """读不出类名表时返回 None——**不是空集**。空集表示"全都找到了"，会把未知伪装成正常。"""
    result = _missing_component_classes({"com.a.A"}, set(), readable=False)
    assert result is None


def test_packed_sample_has_no_component_class_in_dex(sample_apk):
    """真实加固样本：manifest 声明的组件类一个都不在 DEX 里。

    app_version 8（360 加固）：classes.dex 只声明 4 个类，而 manifest 声明 225 个组件。
    """
    facts = collect_facts(sample_apk, {"extract_endpoints": False, "analyze_sensitive_apis": False})
    stats = facts["stats"]
    assert stats["component_class_total"] > 100
    assert stats["component_class_missing"] == stats["component_class_total"], \
        "加固样本的组件类应全部不在 DEX 中"
    assert stats["class_count"] == 4
    assert stats["method_count"] == 381
