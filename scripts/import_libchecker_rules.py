# scripts/import_libchecker_rules.py
"""评估 / 导入 LibChecker-Rules 到组件指纹知识库。**默认干跑，不写库。**

## 为什么先干跑

LibChecker 的规则是**另一套来源**。我们刚花一轮查明知识库已有 15 处
「同一取值被多个组件登记」的真实冲突（见 `docs/kb-dedup-report.md`），
而导入新来源最可能的后果就是**把冲突面放大**。所以先算清楚：会新增多少、
会和现有条目撞多少、撞的时候是同组件还是不同组件。看清了再决定写不写。

## 来源与许可

`LibChecker/LibChecker-Rules`，**Apache-2.0**（与我们已引的 AppShark 同许可）。
用的是仓库里的编译产物 `cloud/rules/v4/rules.db`（176KB，单文件 2832 条），
不必逐个拉 `libraries/*.json`。

## type → 我们的指纹类型

LibChecker 靠 `type` 区分规则对象（v5 契约文档）：

    0 native          1491  ← 我们没有 native 指纹类型，也不从 APK 取库名 → 本期不收
    1 service          288  → MANIFEST_SERVICE
    2 activity         554  → MANIFEST_ACTIVITY
    3 receiver         137  → MANIFEST_RECEIVER
    4 provider         167  → MANIFEST_PROVIDER
    5 DEX               82  → PACKAGE_PREFIX
    9 intent action     99  ← **不缺类型（INTENT_ACTION 在约束词表里就有），缺候选来源** → 不收
    6 未知              14  ← 与 type 9 同类（也是 action 串，另 1 条是包名）→ 同 type 9

## intent action 为什么不收（2026-09-29 实测，改正了原先的理由）

原先这里写的是「我们也没有对应类型」——**不准确**。实测后理由换了方向，而且要
与 PERMISSION 的教训分清楚：

它们**并不通用**（与权限相反）。绝大多数是带厂商命名空间的专有串
（`cn.jpush.android.intent.REGISTER`、`com.huawei.android.push.intent.RECEIVE`），
一旦能匹配是很强的证据。

但它们**一条也匹配不上**：99 条里只有 1 条能命中真实事件，而那条本身是类名、
已由小米推送的 MANIFEST_ACTIVITY/EXACT 覆盖。根因是管线**没有 intent action
这个候选来源**——`detection_events` 的 caller/api/event_data 里 action 串为 0 条，
`privacy_scan.manifest_component` 也没有 intent-filter 字段。

所以要用起来，先得做生产者侧（解析 AndroidManifest 的
`<intent-filter><action android:name>`）。在那之前导入只会得到死数据，还会诱使人
为了「让它生效」去放宽 `MATCHABLE_TYPES`。详见 `docs/libchecker-import-eval.md` §3.1。

## regex 只收「可证明等价」的

LibChecker 的 regex 是**锚定**语义（`re.fullmatch`），所以形如 `X(.*)` 的模式
与我们的 PREFIX `X` 等价。只接受这一种形状，其余一律**拒收并列出**——
不做尽力而为的翻译，误译一条就等于往库里塞一条错指纹。
"""
import argparse
import json
import pathlib
import re
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                      # noqa: E402
from app.models.kb import KBComponent, KBComponentFingerprint   # noqa: E402

# LibChecker type → 我们的 fingerprint_type。不收的 type 不在这里出现，
# 收的时候会因为查不到映射被计入「未映射」并打印出来。
TYPE_MAP = {
    1: "MANIFEST_SERVICE",
    2: "MANIFEST_ACTIVITY",
    3: "MANIFEST_RECEIVER",
    4: "MANIFEST_PROVIDER",
    5: "PACKAGE_PREFIX",
    0: "NATIVE_SO",   # .so 文件名；候选来自 APK 的 lib/**，2026-09-29 接上
}

TYPE_CN = {0: "native", 1: "service", 2: "activity", 3: "receiver",
           4: "provider", 5: "DEX", 6: "未知6", 9: "intent action"}

# `X(.*)`、`X\.(.*)`、`^X(.*)$` —— 锚定语义下等价于前缀 `X`
_PREFIX_RE = re.compile(r"^\^?(?P<lit>(?:[^\\()|\[\]?+{}^$]|\\.)*?)(?:\\?\.)?\(\.\*\)\$?$")


def _unescape(literal: str) -> str:
    """把 regex 字面量里的转义还原：`com\\.foo` -> `com.foo`。"""
    return re.sub(r"\\(.)", r"\1", literal)


def convert_regex(pattern: str) -> tuple[str, str] | None:
    """可证明等价时返回 (值, match_mode)，否则 None。

    只认「字面前缀 + (.*)」这一种形状。带分支、字符类、量词的都不碰——
    它们可能等价于别的东西，但需要证明，没证明就不收。
    """
    m = _PREFIX_RE.match(pattern)
    if not m:
        return None
    value = _unescape(m.group("lit")).strip()
    # 前缀必须真的像前缀：不能为空，也不能只是几个字符
    if len(value) < 4:
        return None
    return value, "PREFIX"


# 各指纹类型的分值，沿用知识库既有约定（见 component_fingerprint 的 weight 分布）
WEIGHT_BY_TYPE = {
    "PACKAGE_PREFIX": 40,
    # .so 文件名是很强的标识（一个库就那几个文件名），与包名前缀同级
    "NATIVE_SO": 40,
    "MANIFEST_ACTIVITY": 35, "MANIFEST_SERVICE": 35,
    "MANIFEST_RECEIVER": 35, "MANIFEST_PROVIDER": 35,
}

# 知识库里已有这一行来源登记（source:577e149c…，类型「开源规则库」，信任度「中高」），
# 不是本轮新建的。用它当指纹的 source_id，来源可追。
SOURCE_NAME = "LibChecker Rules"


def _component_key(name: str) -> str:
    """确定性组件 key：同名同 key，重复导入不会建出第二个组件。

    既有 506 个组件的 key 是 `component:<hex>`，但那套派生方式已不可考
    （原始导入脚本与权限 xlsx 一样已丢），复现不出来。所以新组件用
    归一化名的 sha1，**确定性**比沿用一套猜不出的规则更重要。
    """
    import hashlib
    return "component:" + hashlib.sha1(name.strip().lower().encode()).hexdigest()[:32]


def apply_import(db, usable_rules, cmap, source_sha: str) -> dict:
    """写库。幂等：组件按名查、指纹按 (组件, 类型, 值, 模式) 查，已存在则跳过。

    **跳过 PROXY_DEPENDS_ON**：定这条口径时还不知道那些指纹长什么样。实际查下来
    它们全在 `com.igexin.sdk.*` 命名空间下——**那是个推自己的代码**（igexin = 个推），
    LibChecker 的 `OPPO Push(GeTui Proxy)` 描述的是「这个类干什么」（OPPO 通道的
    个推实现），不是「它属于谁」。所以归给个推本来就对，不该搬走、也不该另建组件
    （那些组件会没有指纹、永远匹配不到）。

    这条与先前的口径决定冲突，**留给人重新拍板**，不在这里替它决定。
    """
    from app.models.kb import (KBComponent as C, KBComponentFingerprint as F,
                               KBComponentRelation as R, KBImportBatch as B,
                               KBSource as S)

    batch = B(source_file="libchecker-rules:v4", source_sha256=source_sha,
              import_mode="UPSERT", status="RUNNING", created_by="import_libchecker_rules")
    db.add(batch)
    db.flush()

    source = db.query(S).filter(S.name == SOURCE_NAME).first()
    by_name = {c.normalized_name: c for c in db.query(C).all()}
    stats = {"components_created": 0, "fingerprints_created": 0,
             "fingerprints_skipped": 0, "relations_created": 0}

    def ensure_component(name: str):
        key = name.strip().lower()
        comp = by_name.get(key)
        if comp:
            return comp, False
        comp = C(component_key=_component_key(name), name=name, normalized_name=key,
                 component_kind="UNKNOWN", verification_status="PENDING",
                 source_type="开源规则库")
        db.add(comp)
        db.flush()
        by_name[key] = comp
        stats["components_created"] += 1
        return comp, True

    stats["deferred_proxy"] = 0
    # **批内也要去重**：库里有唯一约束 (component_id, fingerprint_type,
    # normalized_value, match_mode)，但只查库挡不住同一批里的重复——两条都"库里没有"，
    # 第二条插入时才撞约束（实测 libYUV 的 libyuv.so 在 rules.db 里就是两条）。
    seen: set[tuple] = set()
    for u in usable_rules:
        m = cmap.get(u["label"])
        if m and m["relation"] == "PROXY_DEPENDS_ON":
            stats["deferred_proxy"] += 1
            continue
        # SAME：并入库里已有组件，不新建；其余：以 LibChecker 的 label 建组件
        target_name = m["our_component"] if (m and m["relation"] == "SAME") else u["label"]
        comp, _ = ensure_component(target_name)

        key = (comp.id, u["fingerprint_type"], u["value"], u["match_mode"])
        if key in seen:
            stats["fingerprints_skipped"] += 1
            continue
        exists = db.query(F).filter(
            F.component_id == comp.id, F.fingerprint_type == u["fingerprint_type"],
            F.normalized_value == u["value"], F.match_mode == u["match_mode"]).first()
        if exists:
            seen.add(key)
            stats["fingerprints_skipped"] += 1
            continue
        seen.add(key)

        db.add(F(component_id=comp.id, fingerprint_type=u["fingerprint_type"],
                 value=u["value"], normalized_value=u["value"],
                 match_mode=u["match_mode"],
                 weight=WEIGHT_BY_TYPE.get(u["fingerprint_type"], 30),
                 evidence_role="PRIMARY", source_id=source.id if source else None,
                 source_batch_id=batch.id,
                 raw_data={"import": "libchecker-rules", "rule_type": u["type"],
                           "libchecker_label": u["label"]}))
        stats["fingerprints_created"] += 1

    # 关系：伞形 --BUNDLES--> 我们的模块（PROXY 类已在上面的循环里跳过）
    for label, m in cmap.items():
        if m["relation"] != "UMBRELLA_BUNDLES":
            continue
        rtype = "BUNDLES"
        parent, _ = ensure_component(label)
        child = by_name.get(m["our_component"].strip().lower())
        if not child:
            continue
        dup = db.query(R).filter(R.parent_component_id == parent.id,
                                 R.child_component_id == child.id,
                                 R.relation_type == rtype).first()
        if dup:
            continue
        db.add(R(parent_component_id=parent.id, child_component_id=child.id,
                 relation_type=rtype, source_batch_id=batch.id,
                 description=f"LibChecker 规则导入：{label} {rtype} {m['our_component']}"))
        stats["relations_created"] += 1

    batch.status = "SUCCESS"
    batch.statistics = stats
    batch.finished_at = db.execute(__import__("sqlalchemy").text("select now()")).scalar()
    db.commit()
    return stats


def load_rules(db_path: pathlib.Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "select name, label, type, isRegexRule from rules_table").fetchall()
    conn.close()
    return [{"name": (r[0] or "").strip(), "label": (r[1] or "").strip(),
             "type": r[2], "is_regex": bool(r[3])} for r in rows]


def load_component_map() -> dict[str, dict]:
    """读组件映射表（`data/kb/libchecker_component_map.tsv`）。

    这张表是**人工资产**（同类先例：`data/kb/curated_permission_snapshot.tsv`）。
    它回答的是「LibChecker 的这个组件名，对应我们哪一个」——中英对照这类知识
    （MiPush = 小米推送、旷视 = Face++）推不出来，所以不能自动生成。
    """
    path = (pathlib.Path(__file__).resolve().parent.parent
            / "data" / "kb" / "libchecker_component_map.tsv")
    mapping: dict[str, dict] = {}
    if not path.exists():
        return mapping
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("libchecker_label"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            mapping[parts[0]] = {"our_component": parts[1], "relation": parts[2]}
    return mapping


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rules-db", default="/tmp/lc_rules2.db",
                   help="LibChecker 的 cloud/rules/v4/rules.db")
    p.add_argument("--report", help="把完整报告写到这个 JSON 文件")
    p.add_argument("--apply", action="store_true",
                   help="真正写库。**本期没有实现写入**，加了只会报错")
    args = p.parse_args()

    import hashlib
    rules_db = pathlib.Path(args.rules_db)
    if not rules_db.exists():
        raise SystemExit(f"找不到规则库: {rules_db}")
    rules_sha = hashlib.sha256(rules_db.read_bytes()).hexdigest()

    rules = load_rules(pathlib.Path(args.rules_db))
    print(f"LibChecker 规则 {len(rules)} 条（来源 rules.db）")

    usable, unmapped, regex_rejected = [], [], []
    for r in rules:
        ftype = TYPE_MAP.get(r["type"])
        if not ftype:
            unmapped.append(r)
            continue
        if r["is_regex"]:
            conv = convert_regex(r["name"])
            if not conv:
                regex_rejected.append(r)
                continue
            value, mode = conv
        else:
            value = r["name"].lower()
            # DEX 类规则存的是包名，语义上是前缀；清单类存的是完整类名，语义上是精确
            mode = "PREFIX" if ftype == "PACKAGE_PREFIX" else "EXACT"
        if not value:
            continue
        usable.append({"value": value, "label": r["label"], "type": r["type"],
                       "fingerprint_type": ftype, "match_mode": mode})

    print(f"  可直接映射 {len(usable)} 条")
    print(f"  类型未映射 {len(unmapped)} 条（" +
          "、".join(f"{TYPE_CN.get(t, t)} {n}" for t, n in
                    sorted({t: sum(1 for u in unmapped if u['type'] == t)
                            for t in {u['type'] for u in unmapped}}.items())) + "）")
    print(f"  regex 无法证明等价而拒收 {len(regex_rejected)} 条")

    # ---- 与现有知识库对照 ----
    db = SessionLocal()
    try:
        have = {}          # (fingerprint_type, value) -> [组件名]
        for fp, comp in db.query(KBComponentFingerprint, KBComponent).join(
                KBComponent, KBComponentFingerprint.component_id == KBComponent.id).all():
            v = (fp.normalized_value or "").strip().lower()
            if v:
                have.setdefault((fp.fingerprint_type, v), []).append(comp.name)
        known_names = {c.name for c in db.query(KBComponent).all()}

        same, conflict, is_new = [], [], []
        for u in usable:
            key = (u["fingerprint_type"], u["value"])
            if key in have:
                owners = have[key]
                if u["label"] in owners:
                    same.append(u)
                else:
                    conflict.append({**u, "existing_owners": owners})
            else:
                is_new.append(u)

        new_labels = {u["label"] for u in is_new} - known_names

        # 过一遍组件映射表。三类都能落地，只是落地方式不同：
        #   SAME              → 并入现有组件，不新建
        #   UMBRELLA_BUNDLES  → 新建 LibChecker 那个伞形，关系 BUNDLES → 我们的模块
        #   PROXY_DEPENDS_ON  → 新建代理通道组件，关系 DEPENDS_ON → 聚合方
        # 映射表里查不到的才算「仍需处理」。
        cmap = load_component_map()
        RELATION_OF = {"UMBRELLA_BUNDLES": "BUNDLES", "PROXY_DEPENDS_ON": "DEPENDS_ON"}
        merged, related, unresolved = [], [], []
        for c in conflict:
            m = cmap.get(c["label"])
            if not m:
                unresolved.append({**c, "relation": None})
                continue
            rel = m["relation"]
            if rel == "SAME" and m["our_component"] in c["existing_owners"]:
                merged.append({**c, "mapped_to": m["our_component"]})
            elif rel in RELATION_OF:
                related.append({**c, "relation": RELATION_OF[rel],
                                "target": m["our_component"]})
            else:
                unresolved.append({**c, "relation": rel})

        print()
        print("=== 干跑结果（未写库）===")
        print(f"  与我们已有条目完全一致（同组件）: {len(same)}")
        print(f"  冲突：取值已存在、归属别的组件: {len(conflict)}")
        print(f"     经映射表判定为同一实体，并入现有组件: {len(merged)}")
        print(f"     经映射表判定为**另建组件 + 建关系**:   {len(related)}")
        print(f"     仍需处理: {len(unresolved)}")
        print(f"  新增指纹（我们库里没有这个取值）: {len(is_new)}")
        print(f"     其中涉及的**新组件名** {len(new_labels)} 个")

        if related:
            by_rel = {}
            for c in related:
                by_rel.setdefault(c["relation"], set()).add((c["label"], c["target"]))
            print("\n  要新建的组件与关系：")
            for rel, pairs in sorted(by_rel.items()):
                for label, target in sorted(pairs):
                    print(f"    {label[:30]:30} --{rel}--> {target}")

        if unresolved:
            print("\n  仍需处理的冲突（按组件名）：")
            by_label = {}
            for c in unresolved:
                by_label.setdefault(c["label"], []).append(c)
            for label, items in sorted(by_label.items()):
                print(f"    [未映射] {label[:30]:30} 撞 {items[0]['existing_owners']}"
                      f"（{len(items)} 条指纹）")

        report = {
            "source": "LibChecker/LibChecker-Rules v4 cloud/rules/v4/rules.db",
            "license": "Apache-2.0",
            "total_rules": len(rules),
            "usable": len(usable), "unmapped": len(unmapped),
            "regex_rejected": [r["name"] for r in regex_rejected],
            "same": len(same), "conflict": conflict, "new": is_new,
            "conflict_merged": len(merged),
            "conflict_new_component_with_relation": related,
            "conflict_unresolved": unresolved,
            "new_component_labels": sorted(new_labels),
        }
        if args.report:
            pathlib.Path(args.report).write_text(
                json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"\n  完整报告 -> {args.report}")

        if regex_rejected:
            print(f"\n  regex 拒收样例（前 8，全部见报告）：")
            for r in regex_rejected[:8]:
                print(f"    {r['name'][:62]}")

        if args.apply:
            print("\n=== 写库（--apply）===")
            stats = apply_import(db, usable, cmap, rules_sha)
            for k, v in stats.items():
                print(f"  {k}: {v}")
        else:
            print("\n这是干跑，未写库。确认无误后加 --apply 重跑。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
