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
# （= 更严 / 更不可达，见 Ruling G）。
#
# 这里**有意不看 `|` 后的 appop 标志**：同名被声明成 `signature|appop` 与 `signature`
# 两回时，保守取 `signature`（不可达）。理由与 Ruling G 一致——宁可少报可达，
# 不要把签名级权限报成普通 App 能申请；`is_applicable` 直接吃这个判定，
# 报错方向朝「可达」会让默认视图混进申请不到的条目。
# 代价：这种情况会低估个别条目的可达性。实测真实清单里 22 处 appop 声明对应
# **22 个互不重复的权限名**，归并路径一次也没有走到 appop 上，所以当前数据不受影响。
# 若将来 AOSP 出现同名跨 appop 的声明，改这里一处即可（`map_android_protection_level`
# 已经把 appop 的语义定在词表里了）。
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


# 名字段容许 `.`：`ohos.permission.kernel.X` / `cli.*` / `securityguard.*` / `hsdr.*` /
# `sec.*` / `radio.*` / `vehicle.*` / `atomicService.*` 都是多段名。写成 `[A-Za-z0-9_]+`
# 会把它们**整批静默跳过**（实测真实文档因此丢了 41 条，742 应为 783）——
# 而「解析条数 > 0」这种断言挡不住部分丢失。
_HARMONY_SECTION = re.compile(r"^##\s+(ohos\.permission\.[A-Za-z0-9_.]+)\s*$", re.M)
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


_IOS_REF = ("https://developer.apple.com/documentation/bundleresources/"
            "information-property-list/")


def parse_ios_protected_resources(json_text: str) -> list[dict]:
    """解析 Apple「Protected resources」文档 JSON 里的用法描述键。

    只收 `*UsageDescription`。entitlements（`com.apple.developer.*`）与 TCC 服务名
    不收——它们是「能力授权」而非「用户隐私授权」，混进来会让 permission_type 的
    语义变浑（见 spec §3.3）。

    注意 `NFCReaderUsageDescription` 不带 `NS` 前缀，所以用后缀匹配而非前缀匹配。
    """
    data = json.loads(json_text)
    out = []
    seen = set()
    for ref in (data.get("references") or {}).values():
        title = (ref.get("title") or "").strip()
        if not title.endswith("UsageDescription") or title in seen:
            continue
        seen.add(title)
        abstract = ref.get("abstract") or []
        text = "".join(p.get("text", "") for p in abstract if isinstance(p, dict)).strip()
        out.append({
            "permission_name": title,
            "permission_type": "用法描述键",
            "capability": text or None,
            "grant_mode": None,
            "official_reference": _IOS_REF + title.lower(),
            "raw_data": {"platform_source": "apple_protected_resources"},
        })
    return sorted(out, key=lambda r: r["permission_name"])
