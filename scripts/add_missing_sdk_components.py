# scripts/add_missing_sdk_components.py
"""给「库里没有、因此认不出归属」的 SDK 建组件。**默认干跑，不写库。**

## 为什么做这两个

A3 的标的。三个候选里只做**证据充分的两个**，第三个查不到依据、如实留着：

| 标的 | 事件数 | 做不做 | 依据 |
|---|---|---|---|
| 腾讯图灵盾 | 362 | **做** | 包名在事件里（`com.tencent.turingcam` 334 / `com.tencent.turingface.sdk.mfa` 28）＋公开资料确认产品与厂商 |
| 网易云信 NRTC | 388 | **做** | 包名在事件里（`com.netease.nrtc.*`）＋厂商文档确认是「音视频通话 1.0」 |
| `com.android.business` | 42 | **不做** | 两次检索零结果；南京银行披露的第三方 SDK 清单里也没有。**证据不足以建组件，不猜** |

## 一处「查了才知道」的坑：nrtc ≠ nertc

`com.netease.nrtc` 与库里已有的 `com.netease.nertc` **只差一个 e**，最初怀疑是笔误、
打算把前缀加到既有 NERTC 组件上。**查证后推翻**：两者是网易云信**两代不同产品**——

    nrtc  = 音视频通话 1.0，Gradle 依赖 com.netease.nimlib:nrtc，jar nrtc-sdk.jar
    nertc = 音视频通话 2.0，全新架构的升级品

所以必须**新建独立组件**，不能挂到 NERTC 名下——那样会把两代产品糊成一个，
正是本项目一路在治的错。这条是「先查再改」的又一例。

## 只加有证据的指纹

图灵盾加两条包前缀（两条都出现在真实事件里）；NRTC 加一条包前缀 + 一条 Maven 坐标。
**不加 .so 指纹**：资料里提到 `libnrtc_sdk.so`/`libnrtc_mp4v2.so`，但本地 native
事件（`static_native_lib`）里**没有**它们——没有本地证据就不塞，
往库里加一条没验证过的 .so 前缀就是一条潜在误报。

`com.tencent.turingfd` 同理不加：公开资料里只是顺带提了一句，本地无任何证据。
"""
import argparse
import pathlib
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                                    # noqa: E402
from app.models.kb import (KBComponent, KBComponentFingerprint, KBImportBatch, # noqa: E402
                           KBVendor)

BATCH_SOURCE = "manual-research:missing-sdk-components-2026-09-29"

W_PREFIX, W_MAVEN = 40, 55      # 与库内既有约定一致（PACKAGE_PREFIX=40、MAVEN=55）

# (name, vendor, category_l1, sensitivity, source_type, prefixes, maven, note, attributes)
COMPONENTS = [
    dict(
        name="腾讯图灵盾",
        vendor="腾讯",
        category_l1="安全与风控",
        sensitivity="HIGH",
        source_type="事件特征+公开SDK清单",
        prefixes=["com.tencent.turingcam", "com.tencent.turingface"],
        maven=None,
        note="人脸防攻击／风控 SDK，常用于实名认证与人脸核身环节，与腾讯优图 FaceIn "
             "配合出现。除常规设备信息外还读取已安装应用列表（读指定包名）、"
             "SIM 卡状态与光线传感器，须逐项披露。",
        attributes="调研依据：本地事件特征（com.tencent.turingcam 334 条、"
                   "com.tencent.turingface.sdk.mfa 28 条，均在 南京银行门户 App "
                   "cn.com.njcb.android.mobilehome.test 上）+ 公开第三方 SDK 清单"
                   "（腾讯官方隐私文档 privacy.qq.com/document/preview/5331f064a91a47eb93993fdacb91c8f7）",
    ),
    dict(
        name="网易云信 NRTC（音视频通话 1.0）",
        vendor="网易云信",
        category_l1="即时通讯与音视频",
        sensitivity="CRITICAL",
        source_type="事件特征+厂商文档",
        prefixes=["com.netease.nrtc"],
        maven="com.netease.nimlib:nrtc",
        note="网易云信音视频通话 1.0（NRTC），与库里既有的「网易云信 NERTC」"
             "（音视频通话 2.0）是**两代不同产品**，不可合并。回调摄像头、麦克风与"
             "传感器，属高敏感个人信息。",
        attributes="调研依据：本地事件特征（com.netease.nrtc.* 388 条）+ 网易云信官方"
                   "文档 doc.netease.im（音视频通话 1.0 集成方式：Gradle "
                   "com.netease.nimlib:nrtc，jar nrtc-sdk.jar）",
    ),
]

# 复核用：(候选串, 期望归属组件名)
MUST_HIT = [
    ("com.tencent.turingcam.HnGHR", "腾讯图灵盾"),
    ("com.tencent.turingcam.a2zkO", "腾讯图灵盾"),
    ("com.tencent.turingface.sdk.mfa.abc", "腾讯图灵盾"),
    ("com.netease.nrtc.base.c.a", "网易云信 NRTC（音视频通话 1.0）"),
    ("com.netease.nrtc.utility.d.g.b", "网易云信 NRTC（音视频通话 1.0）"),
    # 反向：既有 NERTC / IM 不能被抢走
    ("com.netease.nertc.abc", "网易云信 NERTC"),
    ("com.netease.nimlib.service.NimService", "网易云信 IM SDK"),
]


def main() -> None:
    p = argparse.ArgumentParser(description="给缺失的 SDK 建组件")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    try:
        vendors = {v.name: v for v in db.query(KBVendor).all()}
        created = skipped = 0
        names = {c.name for c in db.query(KBComponent).all()}

        # 记账：知识库没有 git，改动要能在库里查到（惯例见 kb-lives-only-in-local-db）
        batch = None
        if args.apply:
            batch = KBImportBatch(
                source_file=BATCH_SOURCE, import_mode="UPSERT", status="RUNNING",
                created_by="add_missing_sdk_components",
                statistics={"components": [s["name"] for s in COMPONENTS]})
            db.add(batch)
            db.flush()

        for spec in COMPONENTS:
            if spec["name"] in names:
                print(f"   -- 「{spec['name']}」已存在，跳过")
                skipped += 1
                continue
            vendor = vendors.get(spec["vendor"])
            if vendor is None:
                print(f"   !! 找不到厂商「{spec['vendor']}」，跳过 {spec['name']}")
                skipped += 1
                continue
            print(f"   + {spec['name']}   厂商={spec['vendor']}  类目={spec['category_l1']}  "
                  f"敏感度={spec['sensitivity']}")
            print(f"       前缀 {spec['prefixes']}" + (f"  Maven {spec['maven']}" if spec['maven'] else ""))
            print(f"       {spec['note']}")
            if not args.apply:
                continue
            comp = KBComponent(
                component_key=f"component:{uuid.uuid4().hex}",
                name=spec["name"], normalized_name=spec["name"].strip().lower(),
                vendor_id=vendor.id, component_kind="SDK",
                category_l1=spec["category_l1"], sensitivity_level=spec["sensitivity"],
                source_type=spec["source_type"], verification_status="VERIFIED",
                confidence_level="HIGH", compliance_note=spec["note"],
                attributes=spec["attributes"], is_active=True,
                last_verified_at=datetime.now(timezone.utc),
                raw_data={"added_by": "add_missing_sdk_components",
                          "basis": spec["attributes"]},
            )
            db.add(comp)
            db.flush()
            for pfx in spec["prefixes"]:
                db.add(KBComponentFingerprint(
                    component_id=comp.id, fingerprint_type="PACKAGE_PREFIX",
                    value=pfx, normalized_value=pfx, match_mode="PREFIX",
                    evidence_role="PRIMARY", weight=W_PREFIX,
                    raw_data={"basis": "出现在真实事件中"}))
            if spec["maven"]:
                db.add(KBComponentFingerprint(
                    component_id=comp.id, fingerprint_type="MAVEN_COORDINATE",
                    value=spec["maven"], normalized_value=spec["maven"],
                    match_mode="EXACT", evidence_role="PRIMARY", weight=W_MAVEN,
                    raw_data={"basis": "厂商文档给出的 Gradle 依赖坐标"}))
            created += 1

        if args.apply:
            if batch is not None:
                batch.status = "SUCCESS"
                batch.finished_at = datetime.now(timezone.utc)
                batch.statistics = {**batch.statistics, "components_created": created}
            db.commit()
            print("\n=== 已写入 ===")
            from app.services.component_matcher import load_component_index
            idx = load_component_index(db)
            print(f"\n== 复核（真实匹配器，索引 {idx.size}）==")
            bad = 0
            for cand, want in MUST_HIT:
                hit = idx.match(cand)
                got = hit["name"] if hit else None
                ok = got == want
                bad += 0 if ok else 1
                print(f"   [{'OK  ' if ok else 'FAIL'}] {cand:<44} 期望 {want:<32} 实得 {got}")
            skipped += bad
        else:
            db.rollback()
            print("\n=== 干跑（未写库，已回滚）===")
        print(f"  新建组件 : {created}{'' if args.apply else ' (dry)'}")
        print(f"  跳过/未过: {skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
