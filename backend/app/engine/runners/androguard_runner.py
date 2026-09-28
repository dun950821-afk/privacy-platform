"""Androguard Facts Runner：独立进程执行 APK 基础事实提取。"""
import hashlib
import json
import os
import re
import signal
import struct
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

SENSITIVE_PERMISSIONS = {
    "LOCATION": ["ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"],
    "PHONE_STATE": ["READ_PHONE_STATE", "CALL_PHONE", "READ_PHONE_NUMBERS"],
    "CONTACTS": ["READ_CONTACTS", "WRITE_CONTACTS"],
    "CAMERA": ["CAMERA"],
    "MICROPHONE": ["RECORD_AUDIO"],
    "STORAGE": ["READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"],
    "SMS": ["READ_SMS", "SEND_SMS"],
}

# 敏感 API 分类：只做事实归类，不在此层做风险判定
SENSITIVE_APIS = {
    "device_id": ["getDeviceId", "getImei", "getAndroidId", "getSerial", "getSubscriberId"],
    "location": ["getLastKnownLocation", "requestLocationUpdates", "getLatitude", "getLongitude"],
    "contacts": ["ContactsContract", "queryContacts", "getContacts"],
    "camera": ["Camera.open", "CameraManager", "setPreviewCallback"],
    "microphone": ["MediaRecorder", "AudioRecord", "startRecording"],
    "clipboard": ["ClipboardManager", "getPrimaryClip"],
    "network": ["HttpURLConnection", "OkHttpClient", "URLConnection", "Socket"],
    "crypto": ["Cipher.getInstance", "MessageDigest", "Mac.getInstance"],
    "webview": ["WebView", "addJavascriptInterface", "setJavaScriptEnabled"],
    "file": ["openFileOutput", "FileOutputStream", "getExternalStorageDirectory"],
}

URL_RE = re.compile(rb"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{4,200}")
DOMAIN_RE = re.compile(rb"\b(?:[a-zA-Z0-9-]{1,63}\.){1,4}(?:com|cn|net|org|io|gov|edu|xyz|top|info|biz)\b")
IPV4_RE = re.compile(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b")

MAX_STRINGS = 500


# DEX 头部（按 DEX 格式规范）：
#   0x60 (96)  class_defs_size —— 类定义**数量**
#   0x64 (100) class_defs_off  —— 类定义区的**字节偏移**
# 二者相邻且都是 4 字节小端，读错一个位置不会报错、只会得到一个看起来像数字的
# 字节偏移（实测某加固样本：真实类数 4，被读成 9784）。
DEX_CLASS_DEFS_SIZE_OFF = 0x60    # class_defs_size：类定义数量
DEX_METHOD_IDS_SIZE_OFF = 0x58    # method_ids_size：方法 ID 数量
DEX_STRING_IDS_SIZE_OFF = 0x38    # string_ids_size
DEX_STRING_IDS_OFF_OFF = 0x3C     # string_ids_off
DEX_TYPE_IDS_SIZE_OFF = 0x40      # type_ids_size
DEX_TYPE_IDS_OFF_OFF = 0x44       # type_ids_off
DEX_CLASS_DEFS_OFF_OFF = 0x64     # class_defs_off：类定义区起始字节偏移

# 解析上限：超过即认为不是正常 DEX（或文件被破坏），放弃而不是硬读
MAX_DEX_TABLE_ENTRIES = 500_000
CLASS_DEF_ENTRY_SIZE = 32         # class_def 每项 32 字节，首字段是 class_idx


def _dex_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _uleb128(data: bytes, offset: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7


def _dex_header_count(data: bytes, offset: int) -> int:
    if len(data) < 112 or not data.startswith(b"dex\n"):
        return 0
    return int.from_bytes(data[offset:offset + 4], "little")


def _dex_class_count(data: bytes) -> int:
    """读取 DEX 头部 class_defs_size，避免为计数做完整反编译。"""
    return _dex_header_count(data, DEX_CLASS_DEFS_SIZE_OFF)


def _dex_method_count(data: bytes) -> int:
    """读取 DEX 头部 method_ids_size（方法 ID 数量）。"""
    return _dex_header_count(data, DEX_METHOD_IDS_SIZE_OFF)


def _dex_declared_classes(data: bytes) -> set[str] | None:
    """读出 DEX 里**声明的类名**（描述符形式，如 `Lcom/a/B;`）。

    只走头部登记的三张表：class_defs → type_ids → string_ids，不做反编译。
    目的是与 manifest 声明的组件类比对——**加固 APK 的 DEX 里没有应用自己的类**，
    这个比对不需要任何阈值就能说明「分析的不是这个应用」。

    任何解析异常或明显不合理的规模都返回 None（表示"读不出来"），
    调用方据此判 UNKNOWN，而不是猜一个结果。
    """
    if len(data) < 112 or not data.startswith(b"dex\n"):
        return None
    try:
        str_size = _dex_u32(data, DEX_STRING_IDS_SIZE_OFF)
        str_off = _dex_u32(data, DEX_STRING_IDS_OFF_OFF)
        type_size = _dex_u32(data, DEX_TYPE_IDS_SIZE_OFF)
        type_off = _dex_u32(data, DEX_TYPE_IDS_OFF_OFF)
        class_size = _dex_u32(data, DEX_CLASS_DEFS_SIZE_OFF)
        class_off = _dex_u32(data, DEX_CLASS_DEFS_OFF_OFF)
        if max(str_size, type_size, class_size) > MAX_DEX_TABLE_ENTRIES:
            return None
        for table_off, table_size in ((str_off, str_size), (type_off, type_size),
                                      (class_off, class_size)):
            if table_off + 4 * table_size > len(data) or class_off + CLASS_DEF_ENTRY_SIZE * class_size > len(data):
                return None
        type_string_idx = [_dex_u32(data, type_off + 4 * i) for i in range(type_size)]
        names = set()
        for i in range(class_size):
            type_idx = _dex_u32(data, class_off + CLASS_DEF_ENTRY_SIZE * i)
            if type_idx >= type_size:
                continue
            string_idx = type_string_idx[type_idx]
            if string_idx >= str_size:
                continue
            _, pos = _uleb128(data, _dex_u32(data, str_off + 4 * string_idx))
            names.add(data[pos:data.index(b"\0", pos)].decode("utf-8", "replace"))
        return names
    except (struct.error, IndexError, ValueError):
        return None


def _scan_dex(apk_path: str, flags: dict, max_strings: int = MAX_STRINGS) -> dict:
    urls, domains, ips = [], set(), set()
    api_hits = []
    class_count = 0
    method_count = 0
    declared_classes: set[str] = set()
    classes_readable = False
    native_libs = set()
    try:
        with zipfile.ZipFile(apk_path) as zf:
            names = zf.namelist()
            native_libs.update(Path(n).name for n in names if n.startswith("lib/") and n.endswith(".so"))
            for name in [n for n in names if n.endswith(".dex")]:
                data = zf.read(name)
                class_count += _dex_class_count(data)
                method_count += _dex_method_count(data)
                dex_classes = _dex_declared_classes(data)
                if dex_classes is not None:
                    classes_readable = True
                    declared_classes.update(dex_classes)
                if flags.get("extract_endpoints", True):
                    urls.extend(m.decode("utf-8", "ignore") for m in URL_RE.findall(data)[:max_strings])
                    domains.update(m.decode("utf-8", "ignore").lower() for m in DOMAIN_RE.findall(data)[:max_strings])
                    ips.update(m.decode("utf-8", "ignore") for m in IPV4_RE.findall(data)[:max_strings])
                if flags.get("analyze_sensitive_apis", True):
                    for category, apis in SENSITIVE_APIS.items():
                        for api in apis:
                            if api.encode() in data:
                                api_hits.append({"category": category, "api": api})
    except (zipfile.BadZipFile, OSError):
        pass
    return {
        "class_count": class_count,
        "method_count": method_count,
        "declared_classes": declared_classes,
        "classes_readable": classes_readable,
        "urls": sorted(set(urls))[:max_strings],
        "domains": sorted(domains)[:max_strings],
        "ips": sorted(ips)[:max_strings],
        "sensitive_apis": api_hits,
        "native_libraries": sorted(native_libs),
    }


def _descriptor(java_name: str) -> str:
    """Java 类名 → DEX 描述符（`com.a.B` → `Lcom/a/B;`）。"""
    return "L" + java_name.replace(".", "/") + ";"


def _declared_component_classes(activities, services, receivers, providers) -> set[str]:
    classes = set()
    for group in (activities, services, receivers, providers):
        for name in group or []:
            if name:
                classes.add(name)
    return classes


def _missing_component_classes(component_classes: set[str], declared: set[str],
                               *, readable: bool) -> set[str] | None:
    """manifest 声明了、但 DEX 里没有对应类文件的组件类。

    `readable=False`（DEX 类名表读不出来）时返回 None——**不返回空集**：
    空集意味着「全都找到了」，会把读不出来的情况伪装成正常。
    """
    if not readable or not component_classes:
        return None
    return {c for c in component_classes if _descriptor(c) not in declared}


def collect_facts(apk_path: str, config: dict | None = None) -> dict:
    """在独立进程中执行，返回结构化 Facts。"""
    from androguard.core.apk import APK

    apk = APK(apk_path)
    permissions = apk.get_permissions() or []
    activities = apk.get_activities() or []
    services = apk.get_services() or []
    receivers = apk.get_receivers() or []
    providers = apk.get_providers() or []

    matched = []
    for category, names in SENSITIVE_PERMISSIONS.items():
        for name in names:
            if any(name in permission for permission in permissions):
                matched.append({"category": category, "permission": name})

    certificate = {}
    if apk.is_signed():
        for cert in apk.get_certificates() or []:
            certificate = {"subject": str(cert.subject), "issuer": str(cert.issuer), "serial": str(cert.serial_number)}
            break

    facts = {
        "schema_version": "1.0",
        "basic_info": {
            "package_name": apk.get_package(),
            "app_name": apk.get_app_name(),
            "version_name": apk.get_androidversion_name(),
            "version_code": apk.get_androidversion_code(),
            "min_sdk": apk.get_min_sdk_version(),
            "target_sdk": apk.get_target_sdk_version(),
            "max_sdk": apk.get_max_sdk_version(),
            "file_size": os.path.getsize(apk_path),
            "sha256": hashlib.sha256(Path(apk_path).read_bytes()).hexdigest(),
        },
        "permissions": {"declared": permissions, "sensitive_matched": matched},
        "components": {"activities": activities, "services": services, "receivers": receivers, "providers": providers},
        "certificate": certificate,
        "dex": {"class_count": 0, "method_count": 0, "declared_class_count": None},
        "endpoints": {"urls": [], "domains": [], "ips": []},
        "sensitive_apis": [],
        "native_libraries": [],
        "stats": {
            "permission_count": len(permissions),
            "activity_count": len(activities),
            "service_count": len(services),
            "receiver_count": len(receivers),
            "provider_count": len(providers),
        },
    }

    dex = _scan_dex(apk_path, config or {})
    facts["dex"]["class_count"] = dex["class_count"]
    facts["dex"]["method_count"] = dex["method_count"]
    facts["endpoints"] = {"urls": dex["urls"], "domains": dex["domains"], "ips": dex["ips"]}
    facts["sensitive_apis"] = dex["sensitive_apis"]
    facts["native_libraries"] = dex["native_libraries"]

    # 应用声明的组件类是否真的存在于 DEX 里。加固样本的 DEX 里只有壳，
    # 于是「一个组件类都找不到」——这是判断本次静态分析有没有覆盖到应用的
    # 结构性依据，不需要任何阈值（判定逻辑见 analysis_coverage.py）。
    component_classes = _declared_component_classes(activities, services, receivers, providers)
    facts["dex"]["declared_class_count"] = len(dex["declared_classes"]) if dex["classes_readable"] else None
    missing = _missing_component_classes(component_classes, dex["declared_classes"],
                                         readable=dex["classes_readable"])

    facts["stats"].update({
        "class_count": dex["class_count"],
        "method_count": dex["method_count"],
        "declared_class_count": facts["dex"]["declared_class_count"],
        "component_class_total": len(component_classes),
        "component_class_missing": None if missing is None else len(missing),
        "component_class_missing_sample": None if missing is None else sorted(missing)[:5],
        "url_count": len(dex["urls"]),
        "domain_count": len(dex["domains"]),
        "ip_count": len(dex["ips"]),
        "sensitive_api_count": len(dex["sensitive_apis"]),
        "native_library_count": len(dex["native_libraries"]),
    })
    return facts


def run_runner(apk_path: str, out_path: str, config: dict | None = None) -> None:
    facts = collect_facts(apk_path, config)
    Path(out_path).write_text(json.dumps(facts, ensure_ascii=False, default=str))


def run_in_process(apk_path: str, out_path: str, timeout: int = 300, config: dict | None = None) -> dict:
    """独立进程执行，超时后 terminate → kill。"""
    flags = {
        "extract_strings": (config or {}).get("extract_strings", True),
        "extract_endpoints": (config or {}).get("extract_endpoints", True),
        "analyze_sensitive_apis": (config or {}).get("analyze_sensitive_apis", True),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.engine.runners.androguard_runner", apk_path, out_path, json.dumps(flags)],
        start_new_session=True,
    )
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        raise TimeoutError("Androguard facts extraction timeout")
    if proc.returncode != 0 or not Path(out_path).exists():
        raise RuntimeError(f"Androguard runner failed with exit code {proc.returncode}")
    return json.loads(Path(out_path).read_text())


if __name__ == "__main__":
    run_runner(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else None)
