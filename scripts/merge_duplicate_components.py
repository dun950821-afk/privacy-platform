# scripts/merge_duplicate_components.py
"""合并「同一实体、两个条目」的重复组件。**默认干跑，不写库。**

## 怎么找到这批的

先按 Jaccard（指纹重合度）找——**错的**。它只抓「指纹相同」，
而真实世界里同一实体的两个条目往往**指纹不同但互相覆盖**：

    Jetpack WebKit   androidx.webkit.dropdatacontentprovider （精确）
    AndroidX WebKit  androidx.webkit                          （前缀，已覆盖上面那条）

所以改用**覆盖判定**：B 的每条指纹是否都能被 A 命中。全命中才考虑合并。

覆盖对里有 **118/123 是「伞形覆盖模块」**（`Huawei HMS Core` ⊇ `HUAWEI Health Kit`、
`Google Play services` ⊇ `Google Analytics`），**那些不合并**——设计上早定了
「取更细的身份，用关系表达包含」。这里只处理**名字即同一实体**的。

## 合并三步，都可逆

1. **迁指纹**：把被弃方**独有的**指纹挪到保留方（已被覆盖的不动，
   否则会造出重复登记——本仓库一路在治的正是这个）
2. **停用**被弃方（`is_active=false`，**不删行**——历史 Finding 与证据可能指向它）
3. 记 `REPLACES` 关系：保留方 → 被弃方，说明依据

## 环境限制

`WebFetch` 在本环境被拦，无法逐页核实。所以本脚本用的是**已入仓的人工核对结果**
（`data/kb/component_merge_list.tsv`），不在这里做新的判断。
"""
import argparse
import collections
import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.models.kb import (KBComponent, KBComponentFingerprint,                # noqa: E402
                           KBComponentRelation)
from app.services.component_matcher import MATCHABLE_TYPES, ComponentIndex     # noqa: E402
from app.core.database import SessionLocal                                     # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIST = ROOT / "data" / "kb" / "component_merge_list.tsv"


def load_merges() -> list[tuple[str, str, str]]:
    if not LIST.exists():
        raise SystemExit(f"缺少合并清单: {LIST}")
    out = []
    for line in LIST.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("keep\t"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            out.append((parts[0], parts[1], parts[2]))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    merges = load_merges()
    db = SessionLocal()
    try:
        comps = {c.name: c for c in db.query(KBComponent).all()}
        fps = collections.defaultdict(list)
        for f in db.query(KBComponentFingerprint).all():
            fps[f.component_id].append(f)

        def build_index(cid):
            idx = ComponentIndex()
            for f in fps[cid]:
                if f.fingerprint_type in MATCHABLE_TYPES and f.normalized_value:
                    idx._add(f.normalized_value, f.match_mode, {
                        "id": 0, "component_id": 0, "name": "", "vendor": None,
                        "component_kind": None, "category_l1": None, "sensitivity_level": None,
                        "fingerprint_id": 0, "fingerprint_type": f.fingerprint_type, "weight": 0})
            idx._freeze()
            return idx

        stats = collections.Counter()
        print(f"合并清单 {len(merges)} 对\n")
        for keep_name, drop_name, basis in merges:
            keep, drop = comps.get(keep_name), comps.get(drop_name)
            if not keep or not drop:
                print(f"  !! 查不到组件: {keep_name} / {drop_name}")
                continue
            idx = build_index(keep.id)
            movers = [f for f in fps[drop.id]
                      if f.fingerprint_type in MATCHABLE_TYPES and f.normalized_value
                      and not idx.match(f.normalized_value)]
            conflict = db.query(KBComponentRelation).filter(
                KBComponentRelation.parent_component_id == keep.id,
                KBComponentRelation.child_component_id == drop.id,
                KBComponentRelation.relation_type == "REPLACES").first()
            print(f"  {drop_name[:30]:30} -> {keep_name[:30]:30}")
            print(f"      独有指纹需迁移 {len(movers)} 条；"
                  f"{'已合并过' if conflict else '未合并'}；保留方已停用={not keep.is_active}")
            if args.apply:
                for f in movers:
                    f.component_id = keep.id
                    stats["fingerprints_moved"] += 1
                drop.is_active = False
                stats["components_deactivated"] += 1
                if not conflict:
                    db.add(KBComponentRelation(
                        parent_component_id=keep.id, child_component_id=drop.id,
                        relation_type="REPLACES",
                        description=f"同一实体的重复条目，合并进「{keep_name}」。依据：{basis}"))
                    stats["relations_created"] += 1
        if args.apply:
            db.commit()
            print("\n=== 已写入 ===")
        else:
            db.rollback()
            print("\n=== 干跑（未写库，已回滚）===")
        for k in sorted(stats):
            print(f"  {k}: {stats[k]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
