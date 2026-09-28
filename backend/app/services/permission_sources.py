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


_HARMONY_SECTION = re.compile(r"^##\s+(ohos\.permission\.[A-Za-z0-9_]+)\s*$", re.M)
_HARMONY_ANY_HEADING = re.compile(r"^(?=##\s)", re.M)
_HARMONY_LEVEL = re.compile(r"\*\*权限级别\*\*\s*[：:]\s*([A-Za-z_]+)")
_HARMONY_GRANT = re.compile(r"\*\*授权方式\*\*\s*[：:]\s*(\S+)")
_HARMONY_SINCE = re.compile(r"\*\*起始版本\*\*\s*[：:]\s*(\S+)")


def parse_harmonyos_doc(md_text: str) -> list[dict]:
    """解析 OpenHarmony 文档里的权限小节（`## ohos.permission.X` + 结构化字段）。

    文档在 `openharmony/docs` 的 AccessToken 目录下按授权级别分文件：
    permissions-for-all.md / -all-user.md / -system-apps*.md / -enterprise-apps.md /
    -mdm-apps.md / restricted-permissions.md。

    **小节里没有「权限级别」字段的跳过**——那多半是说明性内容而非权限条目，
    给这种小节编一个级别会让整批数据不可信。

    **正文一律被下一个 `##` 标题收口，不管那个标题是不是权限**。只认
    `## ohos.permission.X` 会让夹在中间的非权限小节被吞进上一段，而级别是
    `.search()` 在整段里找的——于是一个自己没有「权限级别」的权限小节会**继承邻居的级别**，
    正是「宁可少收，不编造」要挡的事。
    """
    out = []
    for block in _HARMONY_ANY_HEADING.split(md_text):
        m = _HARMONY_SECTION.match(block)      # 必须以 ## ohos.permission.X 开头
        if not m:
            continue
        name = m.group(1)
        body = block[m.end():]
        level_m = _HARMONY_LEVEL.search(body)
        if not level_m:
            continue
        grant_m = _HARMONY_GRANT.search(body)
        since_m = _HARMONY_SINCE.search(body)
        # 正文取到级别字段**匹配到的位置**为止。不用字面量 split：文档若写成
        # `**权限级别:**`（冒号在加粗内），字面量找不到，capability 会变成整段。
        desc = body[:level_m.start()].strip()
        out.append({
            "permission_name": name,
            "permission_type": level_m.group(1).strip(),
            "capability": desc or None,
            "grant_mode": grant_m.group(1).strip() if grant_m else None,
            # 不拼 URL：拼出来的 huawei 文档链接是猜的，很可能 404，
            # 而「错误的官方链接」比没有更误导。溯源信息留在 raw_data。见 Ruling I。
            "official_reference": None,
            "raw_data": {"platform_source": "openharmony_docs",
                         "since_api": since_m.group(1).strip() if since_m else None},
        })
    return out
