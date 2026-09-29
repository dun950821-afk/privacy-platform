# scripts/find_duplicate_candidates.py
"""生成「组件重复」候选对——**只读分析，不写库**。

## 判据

沿用 `merge_duplicate_components.py` 的**覆盖判定**：B 的每条可匹配指纹都能被 A 命中。
不用 Jaccard（指纹重合度）——它只抓「指纹相同」，而同一实体的两个条目往往
**指纹不同但互相覆盖**（`Jetpack WebKit` 与 `AndroidX WebKit` 就是）。

范围收敛到**同厂商**（跨厂商的覆盖几乎都是误报），并排除已处理过的对：
`component_merge_list.tsv` 里已合并的、`component_merge_rejected.tsv` 里已否决的、
以及库里已有 `REPLACES` 关系的。

## 为什么要有「已否决」清单

覆盖判定**分不出**「名字即同一实体」与「伞形覆盖模块」——但前者该合并、后者
**按设计不合并**（取更细的身份，用关系表达包含）。上一轮人工分拣完只落盘了合并项，
否决理由没落盘，于是重跑会把上百对伞形覆盖重新翻出来。见 `component_merge_rejected.tsv`。

## 输出里怎么看

    drop 取值  被覆盖方的指纹取值
    keep 前缀  保留候选的包名前缀

若 **drop 取值全部落在 keep 前缀下**，通常就是同一实体（旧条目 + 新导入的重复条目）；
若 drop 是 keep 命名空间下的**某个子模块**（如 gms → analytics），那是伞形覆盖，不合并。

`★` 标记说「被弃方是 2026-09-29 那次导入新增的」——去重清单早于它，这一类必漏。
"""
import argparse
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                                     # noqa: E402
from app.models.kb import (KBComponent, KBComponentFingerprint,                # noqa: E402
                           KBComponentRelation, KBVendor)
from app.services.component_matcher import MATCHABLE_TYPES, ComponentIndex     # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MERGE_LIST = ROOT / "data" / "kb" / "component_merge_list.tsv"
REJECT_LIST = ROOT / "data" / "kb" / "component_merge_rejected.tsv"
IMPORT_DATE = "2026-09-29"          # LibChecker / native 导入那天


def _pairs(path: pathlib.Path) -> set[frozenset]:
    """读 keep/drop 型清单的前两列（含已否决清单），返回无序对集合。"""
    out = set()
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("keep\t"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] and parts[1]:
            out.add(frozenset((parts[0], parts[1])))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="生成组件重复候选对（只读）")
    p.add_argument("--all", action="store_true",
                   help="不限定「新导入产生的」，输出全部候选")
    args = p.parse_args()

    db = SessionLocal()
    try:
        comps = {c.id: c for c in db.query(KBComponent).all()}
        vendors = {v.id: v.name for v in db.query(KBVendor).all()}
        fps: dict[int, list] = collections.defaultdict(list)
        for f in db.query(KBComponentFingerprint).all():
            fps[f.component_id].append(f)

        handled = _pairs(MERGE_LIST) | _pairs(REJECT_LIST)
        for r in db.query(KBComponentRelation).filter(
                KBComponentRelation.relation_type == "REPLACES").all():
            a, b = comps.get(r.parent_component_id), comps.get(r.child_component_id)
            if a and b:
                handled.add(frozenset((a.name, b.name)))

        def index_for(cid: int) -> ComponentIndex:
            idx = ComponentIndex()
            for f in fps[cid]:
                if f.fingerprint_type in MATCHABLE_TYPES and f.normalized_value:
                    idx._add(f.normalized_value, f.match_mode, {
                        "id": 0, "component_id": 0, "name": "", "vendor": None,
                        "component_kind": None, "category_l1": None,
                        "sensitivity_level": None, "fingerprint_id": 0,
                        "fingerprint_type": f.fingerprint_type, "weight": 0})
            idx._freeze()
            return idx

        def covers(a_id: int, b_id: int) -> tuple[bool, int]:
            """a 是否覆盖 b 的全部可匹配指纹 → (是否覆盖, b 的可匹配指纹数)"""
            vals = [f.normalized_value for f in fps[b_id]
                    if f.fingerprint_type in MATCHABLE_TYPES and f.normalized_value]
            if not vals:
                return False, 0
            idx = index_for(a_id)
            return all(idx.match(v) for v in vals), len(vals)

        by_vendor: dict = collections.defaultdict(list)
        for c in comps.values():
            if c.is_active:
                by_vendor[c.vendor_id].append(c)

        rows = []
        for vid, group in by_vendor.items():
            if len(group) < 2:
                continue
            for a in group:
                for b in group:
                    if a.id >= b.id or frozenset((a.name, b.name)) in handled:
                        continue
                    a_cov, n_b = covers(a.id, b.id)
                    b_cov, n_a = covers(b.id, a.id)
                    if not (a_cov or b_cov):
                        continue
                    if a_cov:
                        keep, drop, nfp, both = a, b, n_b, b_cov
                    else:
                        keep, drop, nfp, both = b, a, n_a, False
                    fresh = drop.created_at.strftime("%Y-%m-%d") == IMPORT_DATE
                    if fresh or args.all:
                        rows.append((fresh, both, vendors.get(vid), keep, drop, nfp))

        rows.sort(key=lambda r: (not r[0], r[3].name))
        print(f"候选对 {len(rows)} 组"
              f"{'' if args.all else f'（仅 {IMPORT_DATE} 导入产生的）'}\n")
        for fresh, both, vendor, keep, drop, nfp in rows:
            drop_vals = sorted({f.normalized_value for f in fps[drop.id]
                               if f.fingerprint_type in MATCHABLE_TYPES})
            keep_pfx = sorted({f.normalized_value for f in fps[keep.id]
                              if f.fingerprint_type == "PACKAGE_PREFIX"})
            print(f"{'★' if fresh else ' '} [{vendor}] 保留候选：{keep.name}"
                  f"   ←   可能多余：{drop.name}"
                  f"  （{'双向覆盖' if both else '单向覆盖'}，{nfp} 条指纹）")
            print(f"     drop 取值: {drop_vals[:5]}")
            print(f"     keep 前缀: {keep_pfx[:5]}")
        print(f"\n★ = 被弃方是 {IMPORT_DATE} 新导入的（去重清单早于它，必漏）")
        print("逐条核对：drop 取值全落在 keep 前缀下 → 多半同一实体；"
              "drop 是 keep 命名空间下的子模块 → 伞形覆盖，不合并。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
