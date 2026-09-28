"""平台权限来源文件的解析器。

纯函数：输入是文件文本，输出是可直接入库的行字典。不联网、不碰数据库，
所以能拿样本文件单测。

每行统一形状：
    {"permission_name", "permission_type", "capability",
     "grant_mode", "official_reference", "raw_data"}
"""
import json
import re
import xml.etree.ElementTree as ET

from app.services.permission_taxonomy import map_android_protection_level

_ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
_ANDROID_REF = ("https://developer.android.com/reference/android/Manifest.permission#")

# Android protectionLevel 的「宽窄」：归并同名条目时取更宽的那个做主级别
_LEVEL_WIDTH = {"normal": 1, "dangerous": 2, "internal": 3,
                "system": 3, "role": 3, "module": 3, "signature": 4}


def _android_level_width(raw: str) -> int:
    return _LEVEL_WIDTH.get((raw or "").split("|")[0].strip().lower(), 0)


def parse_android_manifest(xml_text: str) -> list[dict]:
    """解析 AOSP `core/res/AndroidManifest.xml`。

    注意 capability 恒为 None：实测 1018 条里只有 16 条引用的
    `@string/permdesc_*` 能在 core 的 strings.xml 解出来，绝大多数描述定义在各
    模块自己的资源里。**不编造描述**，留空。
    """
    root = ET.fromstring(xml_text)
    merged: dict[str, dict] = {}
    for el in root:
        if el.tag != "permission":
            continue
        name = el.get(_ANDROID_NS + "name")
        if not name:
            continue
        level = el.get(_ANDROID_NS + "protectionLevel") or ""
        group = el.get(_ANDROID_NS + "permissionGroup")
        hit = merged.get(name)
        if hit is None:
            merged[name] = {
                "permission_name": name,
                "permission_type": map_android_protection_level(level),
                "capability": None,
                "grant_mode": None,
                "official_reference": _ANDROID_REF + name.split(".")[-1],
                "raw_data": {"platform_source": "aosp_core_manifest",
                             "protection_levels_seen": [level] if level else [],
                             "permission_group": group},
                "_width": _android_level_width(level),
            }
            continue
        if level and level not in hit["raw_data"]["protection_levels_seen"]:
            hit["raw_data"]["protection_levels_seen"].append(level)
        if _android_level_width(level) > hit["_width"]:
            hit["_width"] = _android_level_width(level)
            hit["permission_type"] = map_android_protection_level(level)
        if group and not hit["raw_data"].get("permission_group"):
            hit["raw_data"]["permission_group"] = group
    for row in merged.values():
        row.pop("_width", None)
        row["raw_data"]["protection_levels_seen"].sort()
    return [merged[k] for k in sorted(merged)]
