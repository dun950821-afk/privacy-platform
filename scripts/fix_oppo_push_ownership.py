# scripts/fix_oppo_push_ownership.py
"""修正 OPPO 推送的两条后缀归属方。**默认干跑，不写库。**

## 问题（与前一次「清通用后缀」不同类）

`prune_generic_suffix_fingerprints.py` 处理的是**取值不具区分度**。这里处理的是
**归属方错了**——取值本身没问题，是挂错了组件：

    id=3817  MANIFEST_SERVICE/SUFFIX  oppopushservice     → OPPO/HeyTap 推送 SDK
    id=3818  MANIFEST_SERVICE/SUFFIX  oppoapppushservice  → OPPO/HeyTap 推送 SDK

实测这两个取值命中的类都是：

    com.igexin.sdk.OppoPushService
    com.igexin.sdk.OppoAppPushService

`com.igexin.*` 是**个推**的命名空间。这两个类是个推为「OPPO 通道」做的**桥接类**——
App 集成了个推、个推再走 OPPO 的通道，类仍在个推名下。OPPO 自己的推送类是
`com.heytap.mcs.*` / `com.heytap.msp.push.*` / `com.coloros.mcs.*`。

## 依据

① **指纹事实**：命中值为 `com.igexin.sdk.*`（见上）。
② **OPPO 组件自己的证据里没有任何一条指向这个类名**——它全部 9 条指纹是：
   3 条 PACKAGE_PREFIX（com.heytap.mcs / com.heytap.msp.push / com.coloros.mcs）、
   1 条 MAVEN_COORDINATE（com.heytap.msp:push）、
   3 条 PERMISSION（不参与匹配）、
   以及**就是这两条 SUFFIX**。也就是说这两条是凭空多出来的，与其余证据不同源。
③ **口径一致**：与 2026-09-29 已定的 Proxy 口径同侧——取「指纹包名归属方」，
   不取「通道方」。同口径下 `HUAWEI Push(Aliyun Proxy)` 也是判给阿里云的。

## 为什么是「删」而不是「改指给个推」

- `oppopushservice` 个推**已有**同值登记（id=3775），改指会撞唯一约束。
- `oppoapppushservice` 虽只此一条，但**不需要**保留后缀：两个类都在
  `com.igexin.sdk` 下，个推已有该 PACKAGE_PREFIX，删后缀不掉召回。
- 个推自己的 `oppopushservice`(3775) 保留——它是本方真实命名，取值不具跨厂商歧义
  （直连 OPPO 的 App 只会是 `com.heytap.mcs.PushService`，不会叫 `OppoPushService`）。

## 顺带发现的重复组件（另做，不在本脚本里）

翻 OPPO 组件的指纹时发现「396 OPPO/HeyTap 推送 SDK」与「1302 OPPO Push」是**同一个 SDK**：
同厂商（欢太）、同类目、同 is_active，被拆成两条。1302 是 2026-09-29 LibChecker 导入进来的，
396 是 2026-08-03 的原始精编条目（元数据丰富得多）——所以**保留 396、停用 1302**。

上一轮去重（`merge_duplicate_components.py`）没抓到它，原因是**它的候选清单早于导入**：
清单建立在字符串重合/覆盖上，而 1302 当时还不存在。**这是一类系统性问题**——LibChecker
那次导入新增了 267 个组件，清单却没跟着重建。详见脚本末尾报告。

合并走既有三步（迁指纹 / 停用 / 记 REPLACES），判断依据写进
`data/kb/component_merge_list.tsv`，不另写脚本。1302 的 5 条取值全被 396 的前缀覆盖，
故零迁移。

验证方式见脚本末尾：删后两个类仍应命中「个推消息推送 SDK」。
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                                    # noqa: E402
from app.models.kb import KBComponent, KBComponentFingerprint                 # noqa: E402

OPPO = "OPPO/HeyTap 推送 SDK"

# (fingerprint_id, 取值, 归属方组件名, 依据)
WRONG_OWNER = [
    (3817, "oppopushservice", OPPO,
     "命中 com.igexin.sdk.OppoPushService（个推的 OPPO 通道桥接类）；"
     "个推已有同值登记(id=3775)，此处是同一条被挂到了通道方名下"),
    (3818, "oppoapppushservice", OPPO,
     "命中 com.igexin.sdk.OppoAppPushService（同上）；OPPO 组件其余全部证据都是 "
     "com.heytap.* / com.coloros.*，与这个类名不同源"),
]

# 删完后仍应命中的用例：(候选类名, 期望归属)
#
# 注意最后一条：改动前它命中的是**另一个组件**「OPPO Push」(id=1302)——那不是本脚本造成的，
# 是库里存在重复组件（396 与 1302 是同一个 OPPO 推送 SDK）。该重复已按既有做法合并
# （`data/kb/component_merge_list.tsv` 加一行 + `merge_duplicate_components.py --apply`），
# 1302 停用后这一条才落到 396。所以**本脚本的复核要在合并之后跑**才全绿。
MUST_STILL_HIT = [
    ("com.igexin.sdk.OppoPushService", "个推消息推送 SDK"),
    ("com.igexin.sdk.OppoAppPushService", "个推消息推送 SDK"),
    ("com.heytap.mcs.PushService", OPPO),
    ("com.heytap.mcssdk.PushService", OPPO),
    ("com.coloros.mcssdk.PushService", OPPO),
]


def main() -> None:
    p = argparse.ArgumentParser(description="修正 OPPO 推送后缀归属方")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    try:
        comps = {c.id: c for c in db.query(KBComponent).all()}
        deleted = skipped = 0

        print("== 删掉挂在通道方名下的个推桥接类后缀 ==")
        for fid, value, comp_name, basis in WRONG_OWNER:
            fp = db.get(KBComponentFingerprint, fid)
            owner = comps.get(fp.component_id).name if fp and fp.component_id in comps else None
            # 校验：id 必须仍指向「该组件名下的那个取值」
            if fp is None or fp.normalized_value != value or owner != comp_name:
                print(f"   !! 跳过 id={fid}（期望 {value}/{comp_name}，"
                      f"实为 {getattr(fp, 'normalized_value', None)}/{owner}）")
                skipped += 1
                continue
            print(f"   id={fid:<5} {value:<20} 从「{comp_name}」删除")
            print(f"          依据：{basis}")
            if args.apply:
                from sqlalchemy import text
                # hit_evidence.fingerprint_id 是 FK 且无 ON DELETE，先摘引用
                db.execute(text(
                    "UPDATE privacy_scan.hit_evidence SET fingerprint_id = NULL "
                    "WHERE fingerprint_id = :fid"), {"fid": fid})
                db.delete(fp)
                deleted += 1

        if args.apply:
            db.commit()
            print("\n=== 已写入 ===")
            # 立刻用真实匹配器复核：两个类仍应归个推
            from app.services.component_matcher import load_component_index
            idx = load_component_index(db)
            print("\n== 复核（真实匹配器）==")
            for cand, want in MUST_STILL_HIT:
                hit = idx.match(cand)
                got = hit["name"] if hit else None
                mark = "OK  " if got == want else "FAIL"
                if got != want:
                    skipped += 1
                print(f"   [{mark}] {cand:<42} 期望 {want:<18} 实得 {got}")
        else:
            db.rollback()
            print("\n=== 干跑（未写库，已回滚）===")
        print(f"  删除 : {deleted}{'' if args.apply else ' (dry)'}")
        print(f"  跳过 : {skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
