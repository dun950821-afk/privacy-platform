"""引擎原始 JSON 拆段：让归档的原始结果变成可查询的段落。

## 为什么需要

引擎原始产物**已经**持久化在归档层（`engine_artifacts`，带 sha256），但提取是**一次性的**：
适配器 `normalize_events()` 取完事件，raw dict 就当局部变量丢掉（`AdapterResult` 上从来没有
`raw_result` 字段）。于是**没被提取的段落等于不存在**——原始文件在盘上，但没人再去看它第二眼。

实测 task 2216 的后果：

    Androguard  endpoints（41 URL + 12 域名 + 3 IP）  整段丢弃
                 其中含隐私政策 URL
                 https://mbank.bankofyk.com:1443/clients/useruploads/iap/other/PrivacyC.html
    MobSF       53 个段落只用了 4 个
                appsec(security_score 47) / manifest_findings(7) / secrets(22，含私钥)
                / sbom(31 个带版本依赖) / certificate_analysis / binary_analysis(30) 全丢

同一批数据里，我们**入库**的 24 条 MobSF URL 去重后只有 3 个值——是 OpenSSL 文档链接
在 8 个 ABI 目录的 .so 里各出现一次。**噪声进了库，信号被丢掉。**

本服务把每个节点原样拆成一行，让「以后才想到要问的问题」也能查。

## 拆分规则（唯一的语义约定，改这里要同步改 tests/test_raw_section_service.py）

1. 对 dict **递归下钻**，每个节点产出一行。父与子**都**产出——只留叶子会丢掉父节点上的
   兄弟标量（如 `appsec.security_score` 与 `appsec.high` 并列，只留叶子就没有 score 那行）。
2. **list 是终点**：整个列表作为一行 payload，**不展开元素**。MobSF 的 `files` 实测 944 个元素，
   展开会炸；不展开则一行装下。
3. 深度上限 `max_depth=4`，防御畸形嵌套导致行数爆炸。**超限时截断但保留原文**——
   深度保护不能变成数据丢失。
4. `payload` **原样**保存，绝不裁剪。这是本表存在的全部意义。

## 关于路径里的点号

路径用 `.` 连接。但引擎的键本身可能含点号（MobSF 的 `permissions` 下是
`android.permission.CALL_PHONE`），所以路径**只供人读与 like 匹配，不做反解析**。
精确定位靠 `payload` 上的 GIN 索引，以及父节点行里完整的原文。
"""
import hashlib
import json
from typing import Any

# 深度上限。AppShark 的合规信息是「分类 -> 规则 -> 明细」三层，
# 加上顶层容器共 4 层，够用；再深多半是畸形结构。
DEFAULT_MAX_DEPTH = 4


def split_sections(raw: Any, *, max_depth: int = DEFAULT_MAX_DEPTH) -> list[dict]:
    """把一份引擎原始结果拆成可入库的段落行。

    返回 `[{path, kind, item_count, payload, payload_hash}, ...]`。
    非 dict 输入返回空列表（不抛异常）——适配器不该因为引擎吐了个怪东西就整个失败。
    """
    if not isinstance(raw, dict) or not raw:
        return []
    rows: list[dict] = []
    for key, value in raw.items():
        _walk(str(key), value, rows, depth=1, max_depth=max_depth)
    return rows


def _walk(path: str, value: Any, rows: list[dict], *, depth: int, max_depth: int) -> None:
    rows.append(_row(path, value))
    if not isinstance(value, dict) or not value:
        return
    if depth >= max_depth:
        # 截断处这一行已经带上了整棵子树，所以内容不丢
        return
    for key, child in value.items():
        _walk(f"{path}.{key}", child, rows, depth=depth + 1, max_depth=max_depth)


def _row(path: str, value: Any) -> dict:
    if isinstance(value, dict):
        kind = "object"
    elif isinstance(value, list):
        kind = "array"
    else:
        kind = "scalar"
    return {
        "path": path,
        "kind": kind,
        "item_count": len(value) if isinstance(value, list) else None,
        "payload": value,
        "payload_hash": payload_hash(value),
    }


def payload_hash(value: Any) -> str:
    """内容哈希。**键序不敏感**——两次扫描只要内容一样，哈希就该一样，
    这样跨次扫描比对才有意义（sorted_keys）。"""
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
