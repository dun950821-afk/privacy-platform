import struct
import zipfile

from app.engine.runners.androguard_runner import _dex_class_count, _scan_dex, collect_facts


def _fake_dex(class_count: int, payload: bytes = b"") -> bytes:
    header = bytearray(112)
    header[0:8] = b"dex\n035\x00"
    header[100:104] = struct.pack("<I", class_count)
    return bytes(header) + payload


def test_dex_class_count_reads_header():
    assert _dex_class_count(_fake_dex(1234)) == 1234
    assert _dex_class_count(b"not a dex") == 0


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
