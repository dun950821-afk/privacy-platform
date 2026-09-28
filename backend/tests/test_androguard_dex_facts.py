import struct
import zipfile

from app.engine.runners.androguard_runner import _dex_class_count, _scan_dex, collect_facts

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
