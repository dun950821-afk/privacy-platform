"""Androguard Facts Runner：独立进程执行 APK 基础事实提取。"""
import hashlib
import json
import os
import re
import signal
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


def _dex_class_count(data: bytes) -> int:
    """读取 DEX 头部 class_defs_size（偏移 100），避免为计数做完整反编译。"""
    if len(data) < 112 or not data.startswith(b"dex\n"):
        return 0
    return int.from_bytes(data[100:104], "little")


def _scan_dex(apk_path: str, flags: dict, max_strings: int = MAX_STRINGS) -> dict:
    urls, domains, ips = [], set(), set()
    api_hits = []
    class_count = 0
    native_libs = set()
    try:
        with zipfile.ZipFile(apk_path) as zf:
            names = zf.namelist()
            native_libs.update(Path(n).name for n in names if n.startswith("lib/") and n.endswith(".so"))
            for name in [n for n in names if n.endswith(".dex")]:
                data = zf.read(name)
                class_count += _dex_class_count(data)
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
        "urls": sorted(set(urls))[:max_strings],
        "domains": sorted(domains)[:max_strings],
        "ips": sorted(ips)[:max_strings],
        "sensitive_apis": api_hits,
        "native_libraries": sorted(native_libs),
    }


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
        "dex": {"class_count": 0, "method_count": None},
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
    facts["endpoints"] = {"urls": dex["urls"], "domains": dex["domains"], "ips": dex["ips"]}
    facts["sensitive_apis"] = dex["sensitive_apis"]
    facts["native_libraries"] = dex["native_libraries"]
    facts["stats"].update({
        "class_count": dex["class_count"],
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
