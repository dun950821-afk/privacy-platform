# scripts/apply_component_enrichment.py
"""把并行调研产出的组件元数据合并、校验并落库。**默认干跑，不写库。**

## 数据从哪来

`/tmp/enrich_out_*.tsv` —— 13 个批次文件中已产出的那些。每批由独立 agent 调研，
要求：受控词表、留空不编、写来源 URL、标 confidence、**用本地指纹库消歧而不是望文生义**。

本脚本把它们合并成 `data/kb/component_enrichment.tsv`（入仓、可评审），再落库。

## 三道校验，任何一道不过就中止

1. **词表**：`component_kind` / `category_l1` / `sensitivity_level` 必须落在受控词表内
2. **对得上**：每行的 `id` + `name` 必须与知识库里现存组件一致（防止串行）
3. **不覆盖**：只填**当前为空**的字段。已有值的（人工整理过的）不动——
   调研产出是**推导**，不该盖掉人工资产

## 落库时记什么

- `attributes` 追加依据：批次、来源 URL、confidence —— 「这条是谁在什么依据下写的」可回查
- `verification_status` 保持 `PENDING`：**调研不是核实**
"""
import argparse
import collections
import csv
import hashlib
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                    # noqa: E402
from app.models.kb import KBComponent, KBVendor               # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MERGED = ROOT / "data" / "kb" / "component_enrichment.tsv"

COLUMNS = ["id", "name", "vendor", "component_kind", "category_l1",
           "sensitivity_level", "primary_purpose", "description",
           "compliance_note", "sources", "confidence"]

CATEGORIES = {
    "AndroidX与系统框架", "Web与内核", "即时通讯与音视频", "厂商移动服务",
    "可观测性与APM", "图片编辑", "图片选择", "图片音视频与文档", "地图与定位",
    "安全与密码", "安全与风控", "广告与变现", "开发调试", "异步与基础库",
    "影像采集", "扫码识别", "推送与消息", "支付与金融", "数据序列化与基础库",
    "数据库与本地存储", "机器学习", "机器视觉与生物识别", "权限管理", "架构与路由",
    "电子签名", "界面与基础库", "社交登录与分享", "移动门户", "系统增强与工具",
    "统计分析与归因", "网络与云服务", "行业框架", "视频监控", "设备标识与基础服务",
    "语音与智能交互", "跨平台与游戏", "身份认证", "通知", "通讯录",
}
KINDS = {"SDK", "OPEN_SOURCE_LIBRARY", "FRAMEWORK", "VENDOR_COMPONENT", "SYSTEM_COMPONENT"}
SENSITIVITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
CONFIDENCES = {"high", "medium", "low"}


# 跨语言/别名的厂商，归一化抓不到（`微软` 与 `Microsoft` 去掉标点也对不上）。
# 不处理就会给同一家建出第二个厂商行——正是本仓库一路在治的「重复登记」毛病，
# 不该在厂商表里重演。只收**确定无疑**的，拿不准的宁可新建等人工合并。
VENDOR_ALIAS = {
    "微软": "Microsoft", "高通": "Qualcomm", "旷视科技": "旷视科技 Face++",
    "旷视": "旷视科技 Face++", "欢太科技": "OPPO/欢太",
    "字节跳动（火山引擎）": "字节跳动", "阿里巴巴（淘宝）": "阿里巴巴",
    "Xiph.Org 基金会": "Xiph.Org", "谷歌": "Google", "脸书": "Meta",
}


def _vendor_key(name: str) -> str:
    return "vendor:" + hashlib.sha1(name.strip().lower().encode()).hexdigest()[:32]


def _norm_vendor(name: str) -> str:
    """厂商名归一化：去括号补充、去公司/开源后缀、去标点空白。"""
    s = name.lower()
    s = re.sub(r"（[^）]*）|\([^)]*\)", "", s)
    s = re.sub(r"有限公司|股份公司|公司|基金会|开源项目|开源社区|开源作者|个人开源项目", "", s)
    return re.sub(r"[,\s\.\-_、+]+", "", s).strip()


def load_batches(pattern: str = "/tmp/enrich_out_*.tsv") -> tuple[list[dict], list[str]]:
    rows, problems = [], []
    for path in sorted(pathlib.Path("/").glob(pattern.lstrip("/"))):
        with open(path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            if reader.fieldnames != COLUMNS:
                problems.append(f"{path.name}: 表头不符 {reader.fieldnames}")
                continue
            for r in reader:
                r["_batch"] = path.name
                rows.append(r)
    return rows, problems


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="真正写库")
    args = p.parse_args()

    rows, problems = load_batches()
    print(f"读入 {len(rows)} 行，来自 {len({r['_batch'] for r in rows})} 个批次")
    for x in problems:
        print("  !!", x)

    # 同一 id 出现多次：保留 confidence 高的那条（high > medium > low）
    rank = {"high": 0, "medium": 1, "low": 2, "": 3}
    best: dict[str, dict] = {}
    for r in rows:
        cur = best.get(r["id"])
        if cur is None or rank.get(r["confidence"], 3) < rank.get(cur["confidence"], 3):
            best[r["id"]] = r
    dup = len(rows) - len(best)

    db = SessionLocal()
    try:
        by_id = {str(c.id): c for c in db.query(KBComponent).all()}

        # ---- 校验 ----
        bad_vocab, bad_id = [], []
        for r in best.values():
            if r["category_l1"] and r["category_l1"] not in CATEGORIES:
                bad_vocab.append((r["id"], "category_l1", r["category_l1"]))
            if r["component_kind"] and r["component_kind"] not in KINDS:
                bad_vocab.append((r["id"], "component_kind", r["component_kind"]))
            if r["sensitivity_level"] and r["sensitivity_level"] not in SENSITIVITIES:
                bad_vocab.append((r["id"], "sensitivity_level", r["sensitivity_level"]))
            if r["confidence"] and r["confidence"] not in CONFIDENCES:
                bad_vocab.append((r["id"], "confidence", r["confidence"]))
            comp = by_id.get(r["id"])
            if not comp or comp.name != r["name"]:
                bad_id.append((r["id"], r["name"], comp.name if comp else "<不存在>"))

        print(f"  去重后 {len(best)} 条（重复 {dup} 条，保留 confidence 高的）")
        print(f"  词表越界 {len(bad_vocab)} 处")
        for b in bad_vocab[:6]:
            print(f"     {b}")
        print(f"  id/名称对不上 {len(bad_id)} 处")
        for b in bad_id[:6]:
            print(f"     {b}")
        if bad_vocab or bad_id:
            raise SystemExit("校验未过，中止——不写库。先修对应的批次产出。")

        # ---- 合并入仓 ----
        MERGED.write_text(
            "# 组件元数据调研产出（并行 agent 分批调研，见 scripts/apply_component_enrichment.py）\n"
            "# 每行都带来源 URL 与 confidence；空字段表示**没查到，未编造**。\n"
            "# 落库时只填知识库里当前为空的字段，不覆盖已有的人工整理值。\n"
            + "\t".join(COLUMNS) + "\n"
            + "\n".join("\t".join(r[c] for c in COLUMNS) for r in
                        sorted(best.values(), key=lambda x: -int(x["id"]))),
            encoding="utf-8")
        print(f"\n  合并文件 -> {MERGED.relative_to(ROOT)}")

        # ---- 落库 ----
        stats = collections.Counter()
        # 同时按 normalized_name 与「归一化形式」建索引：前者处理大小写，
        # 后者处理「上海屹通信息科技发展有限公司」这种带后缀的同名。
        vendors: dict[str, KBVendor] = {}
        for v in db.query(KBVendor).all():
            vendors.setdefault(v.normalized_name, v)
            vendors.setdefault(_norm_vendor(v.name), v)
        for r in best.values():
            comp = by_id[r["id"]]
            basis = (f"调研依据：{r['_batch']} confidence={r['confidence']}"
                     f" sources={r['sources'][:200]}")
            if r["vendor"] and not comp.vendor_id:
                raw_name = r["vendor"]
                alias = VENDOR_ALIAS.get(raw_name, raw_name)
                # 先按名找，再按归一化名找（去掉括号、公司后缀、标点）
                v = vendors.get(alias.strip().lower())
                if not v:
                    v = vendors.get(_norm_vendor(alias))
                if not v:
                    v = KBVendor(vendor_key=_vendor_key(alias),
                                 name=alias, normalized_name=alias.strip().lower(),
                                 verification_status="UNVERIFIED", raw_data={"source": "调研"})
                    db.add(v)
                    db.flush()
                    vendors.setdefault(v.normalized_name, v)
                    vendors.setdefault(_norm_vendor(v.name), v)
                    stats["vendor_created"] += 1
                comp.vendor_id = v.id
                stats["vendor_set"] += 1
                comp.attributes = (f"{comp.attributes}；" if comp.attributes else "") + basis
            for field in ("component_kind", "category_l1", "sensitivity_level",
                          "primary_purpose", "description", "compliance_note"):
                val = r[field]
                if not val:
                    continue
                cur = getattr(comp, field)
                # 只填空的；component_kind 例外——UNKNOWN 是导入时的占位，算空
                if cur and not (field == "component_kind" and cur == "UNKNOWN"):
                    stats[f"{field}_skipped"] += 1
                    continue
                setattr(comp, field, val)
                stats[field] += 1
                if field == "component_kind" and not comp.attributes:
                    comp.attributes = basis

        print("\n=== 落库统计 ===")
        for k in sorted(stats):
            print(f"  {k}: {stats[k]}")
        if args.apply:
            db.commit()
            print("\n已写入。")
        else:
            db.rollback()
            print("\n这是干跑，未写库（已回滚）。确认后加 --apply。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
