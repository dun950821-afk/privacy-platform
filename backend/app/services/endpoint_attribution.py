"""按「引用该端点的类 / so」推导域名归属：这个域名属于谁在采集。

## 归属线索平台已经有了，只是没人用

`engine_observations` 里 `observation_type='security.endpoint'` 的 payload **同时**存了
URL 和引用它的那个类或 `.so`：

    {"api": "http://hmma.baidu.com/app.gif",
     "url": {"path": "com/baidu/mobstat/Config.java",
             "urls": ["http://hmma.baidu.com/app.gif", ...]}}

实测 131 个 host **100% 都有 `path`**。`com.baidu.mobstat` 正是知识库里「百度移动统计」
的包前缀——所以归属是**读出来的，不是猜的**。

## 为什么复用 component_matcher，而不是另建一张静态映射表

两个理由：

1. **匹配口径只此一处。** 本仓库一路在治「两处各写一份」，域名归属不该再开一份。
2. **知识库一长进，归属自动跟着长。** 静态表会腐化：`com.fhuvideo`（飞虎的真实命名
   空间）现在推不出来，是因为库里写的是 `com.fhvideo`；库里补对之后，
   这里不用改一行代码就跟着对。

实测覆盖率：只按 Java 类路径匹配 → 56/131（43%）；**加上 `.so` 文件名走 `NATIVE_SO`
指纹 → 94/131（71%）**。`path` 并不都是类路径，还有 `apktool_out/lib/arm64-v8a/
libAMapSDK_MAP_v9_2_1.so` 这种 so 路径，所以两路都要走。

## 推不出的怎么办

分三类，都交给人工语料 `data/kb/domain_attribution.tsv` 兜底与覆盖：

    path 根本不是路径   （`Android String Resource`）
    知识库缺前缀        （`com/baidu/platform`、`com.fhuvideo`）
    非代码归属          （平台命名空间 `www.w3.org`、App 自研服务器 `mportal.njcb.com.cn`）

**查不到就不标**——审计人员按错误的归属去查隐私政策是白查（计划 §5.4 的谨慎在
未知部分继续成立）。

## 语料行不都有 `component_name` / `vendor`

非代码归属那类（平台命名空间、App 自研业务服务器）在知识库里**没有**逐字对应的
组件或厂商，所以那两列**故意留白**；它们的断语写在 `label` 列（`平台命名空间` /
`应用自研`）。这类行同样算「有明确断语」，**照样压过与之冲突的推导**——否则
`www.w3.org` 会被 `libflutter.so` 推成「Flutter · low」，而语料里明明写着它是
XML 命名空间、根本不是网络端点。真正「查不到依据」的行三列全空：既不压过推导，
也不落地成一个空归属盒（见 `attribute_hosts`）。
"""
from __future__ import annotations

import pathlib
import re

from sqlalchemy.orm import Session

from app.models import EngineObservation
from app.services.component_matcher import ComponentIndex

# 人工语料：推不出来的那些，入仓即为准（与 data/kb 下其它人工资产同规矩）
ATTRIBUTION_TSV = (pathlib.Path(__file__).resolve().parents[3]
                   / "data" / "kb" / "domain_attribution.tsv")

_SO_RE = re.compile(r"([^/\\]+\.so)$", re.IGNORECASE)


def host_candidates(path: str):
    """从一个 `path` 里取出所有可能指认归属的候选串。

    两条路都要走：`path` 不都是类路径，还有 `.so` 路径。
    """
    if not path:
        return
    if "/" in path or "." in path:
        fqcn = path.replace("/", ".").removesuffix(".java")
        if fqcn and " " not in fqcn:
            yield fqcn
    m = _SO_RE.search(path)
    if m:
        yield m.group(1)


def endpoint_rows(db: Session, task_id: int) -> list:
    """该任务的全部 `security.endpoint` 观测。

    单独抽出来是为了让 `/endpoints` 路由与 `host_paths` **共用同一次查询**：
    路由本来就要读这批行拿 URL，归属推导再读一遍就成了一次多余的全表扫。
    """
    return db.query(EngineObservation).filter(
        EngineObservation.task_id == task_id,
        EngineObservation.observation_type == "security.endpoint",
    ).all()


def paths_from_rows(rows) -> dict[str, set[str]]:
    """从 `security.endpoint` 观测里取出 域名 → {引用它的类/so 路径}。"""
    out: dict[str, set[str]] = {}
    for obs in rows:
        payload = obs.payload or {}
        url = payload.get("url") if isinstance(payload, dict) else None
        if not isinstance(url, dict):
            continue
        path = url.get("path")
        if not path:
            continue
        for raw in url.get("urls") or []:
            host = _host_of(raw)
            if host:
                out.setdefault(host, set()).add(path)
    return out


def host_paths(db: Session, task_id: int) -> dict[str, set[str]]:
    """该任务的 域名 → {引用它的类/so 路径}。"""
    return paths_from_rows(endpoint_rows(db, task_id))


_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
                      r"|^\d{1,3}(\.\d{1,3}){3}$")


def valid_host(host: str) -> bool:
    """这个「host」像不像一个真的主机名/IP。

    **必须挡**：观测数据里混着格式串与占位符——`%s`、`%1$s`、`%s%s%s`、空串。
    它们来自代码里的 `String.format("http://%s/...")` 这类模板，被 `urlsplit`
    当成了主机名。不挡就会进前端列表、进人工语料（实测已经污染过一份）。
    """
    if not host or "%" in host or " " in host:
        return False
    if len(host) > 253 or "." not in host:
        return False
    return bool(_HOST_RE.match(host))


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        host = (urlsplit(url.strip()).hostname or "").lower()
    except ValueError:
        return ""
    return host if valid_host(host) else ""


def load_curated(path: pathlib.Path | None = None) -> dict[str, dict]:
    """读人工语料。文件不在就返回空表——**不报错**：它只是兜底，不是必需品。"""
    tsv = path or ATTRIBUTION_TSV
    if not tsv.exists():
        return {}
    out: dict[str, dict] = {}
    for line in tsv.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("domain\t"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        domain, component, vendor, confidence = parts[0], parts[1], parts[2], parts[3]
        sources = parts[4] if len(parts) > 4 else ""
        note = parts[5] if len(parts) > 5 else ""
        label = parts[6] if len(parts) > 6 else ""
        out[domain.strip().lower()] = {
            "component_name": component.strip() or None,
            "vendor": vendor.strip() or None,
            "confidence": confidence.strip() or None,
            "sources": sources.strip() or None,
            "note": note.strip() or None,
            # 非代码归属那类（平台命名空间 / 应用自研）没有组件或厂商，断语落在这里
            "label": label.strip() or None,
            "via": "curated",
        }
    return out


def has_verdict(c: dict | None) -> bool:
    """这行语料有没有**明确断语**可展示？

    三种都算：有组件名、有厂商、或只有 `label`（平台命名空间 / 应用自研）。
    三列全空的才是「查不到依据」——那种行既不压过推导，也不该落地成空盒子。
    """
    return bool(c and (c.get("component_name") or c.get("vendor") or c.get("label")))


# 厂商/组件名里切出来的通用词——它们出现在域名里并不能说明归属，
# 反而会把 `api.somewhere.com` 这类误判成 high（`api` 对上了「XX API SDK」）。
_GENERIC_TOKENS = {
    "sdk", "app", "platform", "library", "lib", "core", "common", "base",
    "tool", "tools", "api", "android", "client", "service", "services",
    "kit", "framework", "module", "plugin", "mobile", "cloud", "open",
}


def _vendor_matches_host(host: str, vendor: str | None, component: str | None) -> bool:
    """域名与厂商**对得上**吗——用来给推导结果定确信度。

    「这个域名出现在某个库的代码/字符串里」不等于「这是那个库的服务端点」。
    实测两类：

        liteav.sdk.qcloud.com  ← libliteavsdk.so   对得上（qcloud ↔ 腾讯云）✅
        www.openssl.org        ← libnrtc_sdk.so   对不上（so 里的文档链接）❌
        www.w3.org             ← libflutter.so    对不上（XML 命名空间）❌

    对得上给 high，对不上给 low 并在 note 里写清疑点——**不因为对不上就丢掉**，
    它仍是一条线索，只是不能当结论用。
    """
    text = (host or "").lower()
    # 把域名拆成「标签」与「标签的连字符片段」：`trtc.tencent-cloud.com` →
    # {trtc, tencent-cloud, tencent, cloud, com}。**逐段相等**比较，不做子串——
    # 子串会让 `qq` 命中 `qqq.com`。
    parts = set()
    for label in text.split("."):
        parts.add(label)
        parts.update(label.split("-"))
    tokens = set()
    for src in (vendor, component):
        if src:
            tokens.update(t for t in re.split(r"[^a-z0-9]+", src.lower())
                          if len(t) >= 3 and t not in _GENERIC_TOKENS)
    # 中文厂商名（腾讯、百度…）本身对不上域名，得映射到它的英文/域名形态。
    # 注意 vendor 常常是**公司级**（「腾讯」）而组件是产品线级（「腾讯云通信 SDK」），
    # 所以腾讯要同时认 qcloud/myqcloud——实测 api.im.qcloud.com 就是这么漏的。
    alias = {
        "腾讯": ("tencent", "qcloud", "myqcloud", "qq", "tim", "weixin", "gtimg"),
        "百度": ("baidu", "bdstatic"), "阿里云": ("aliyun", "alibaba", "myqcloud", "alicdn"),
        "阿里巴巴": ("alibaba", "alicdn", "mmstat", "taobao"), "华为": ("huawei", "hms", "hicloud"),
        "小米": ("xiaomi", "miui", "mi.com"), "网易云信": ("netease", "yunxin", "126.net"),
        "字节跳动": ("bytedance", "toutiao", "snssdk", "pangle"), "快手": ("kuaishou", "kwai", "gifshow"),
        "高德地图开放平台": ("amap", "gaode", "autonavi"),
        "Meta": ("facebook", "fbcdn", "fb.com"), "Google": ("google", "gstatic", "ggpht"),
        "Square": ("squareup", "okhttp"), "Bumptech": ("bumptech", "glide"),
    }
    for key, names in alias.items():
        if vendor and key in vendor:
            tokens.update(names)
    return any(t in parts for t in tokens)


def attribute_hosts(db: Session, index: ComponentIndex, task_id: int,
                    hosts: list[str] | None = None,
                    paths_by_host: dict[str, set[str]] | None = None) -> dict[str, dict]:
    """域名 → 归属。三条路的**优先级**：

        curated 且有断语（组件/厂商/label）  >  derived  >  弃权（不落地）

    为什么「curated 且有断语」压过推导：人工语料是查证过的，而且它能把推导**误判**
    的那些纠正回来——`www.w3.org` 在人工语料里明确写着是 XML 命名空间、**不是网络
    端点**（`label='平台命名空间'`，组件与厂商两列故意留白），而推导会因
    `libflutter.so` 里有这个串把它算成 Flutter。**留白不等于弃权**：断语写在 label
    里，所以这类行也必须能压过推导。

    为什么「三列全空」的语料行不落地：那说明人工查不到依据，而推导也没有命中——
    此时输出一个 `component_name=null, vendor=null` 的空盒子，前端只会渲染成
    一个空的归属框（T7-M7）。宁可不标。

    `hosts` —— 该任务**实际出现**的 host 全集。调用方（`/endpoints` 路由）已经算过，
    传进来即可。**不传则退回 `host_paths` 的 key**——那是只有 AppShark 观测的 host；
    纯 Androguard 任务（三个银行样本）的 host 一个都不在里面，语料会被整批丢掉
    （F1）。路由务必传。
    `paths_by_host` —— 可选的 `host_paths` 结果，避免路由里重复查一遍
    `security.endpoint`。

    返回的每一项都带 `via`（`derived` / `curated`）与 `sources` 说明**凭什么**，
    前端要能展示依据，否则审计人员无从核对。
    """
    curated = load_curated()
    if paths_by_host is None:
        paths_by_host = host_paths(db, task_id)
    host_list = list(hosts) if hosts is not None else list(paths_by_host)
    result: dict[str, dict] = {}
    for host in host_list:
        paths = paths_by_host.get(host, set())
        hit = used = None
        for p in sorted(paths):
            for cand in host_candidates(p):
                m = index.match(cand)
                if m:
                    hit, used = m, cand
                    break
            if hit:
                break

        c = curated.get(host)
        if has_verdict(c):
            result[host] = c                      # 人工查证过的（含只有 label 的）压过推导
            continue
        if hit:
            ok = _vendor_matches_host(host, hit.get("vendor"), hit["name"])
            result[host] = {
                "component_name": hit["name"], "vendor": hit.get("vendor"),
                "confidence": "high" if ok else "low",
                "via": "derived", "sources": f"ir-evidence:{used}",
                "note": None if ok else "域名出现在该库的代码/字符串中，"
                                        "但其归属方与该域名对不上——可能是库里的"
                                        "文档链接或命名空间，未必是该库的服务端点",
            }
            continue
    return result
