# scripts/prune_generic_suffix_fingerprints.py
"""清理「通用后缀」指纹：**默认干跑，不写库。**

## 问题

`component_fingerprint` 里有 120 条 `match_mode='SUFFIX'`。匹配器对 SUFFIX 的语义是
（`services/component_matcher.py::_match_in_tier`）：

    c = normalize_candidate(cand)      # 剥 AppShark 的 <类: 方法签名> 外壳，**统一小写**
    if c.endswith(value): 命中

候选串是**类全名**（`com.yxz.app.MainActivity`）。所以一条取值 `mainactivity` 的后缀，
会命中**任何 App 的主界面 Activity**；而 `_TIERS = (_TIER_MANIFEST, _TIER_CODE)`
**清单级先试**，于是这类误判还会**压过**本来正确的包名前缀证据。

后缀本身没错——`com.sunyard.photomain` 那种专有命名，后缀等价于确定性证据。
问题只出在**取值是通用名**的那些：一个与该厂商无关的 App 给自己的类起同名，
是完全现实的。

## 判据

删除 = 满足任一条，依据类型标在每行：

    MEASURED  实测：在真实事件/已落库的命中证据里，命中了**非本方**厂商的类
    NAMING    命名：取值是通用 Android 组件名 / 通用英文词，且该组件另有
              PACKAGE_PREFIX 兜底（删了不会变成认不出来）

实测口径（复现 `normalize_candidate` 后对 `detection_events` 全量候选串比对）
已抓到 10 条确凿误判，其中 2 条**已经落库并会展示给用户**：

    营口银行 com.csii.yk.ui         腾讯云慧眼 OCR 的 CaptureActivity  → 判给了 ZXing
    营行企业银行 com.csii.mobile.iap.ykcb   csii 的 LoginActivity    → 判给了屹通

其它实测误判：快手广告（kwad）的 pay/playback/adwebview、OPPO 的 mcssdk.pushservice、
小米的 xmpushservice、Google Ads 的 mobileadsinitprovider、ML Kit 的 mlkitinitprovider、
百度 OAuth 的 webviewactivity、微博的 sharetransactivity、信雅达的 mainactivity…

## 一处真损失 → 用精确前缀替换，而不是单纯删

删前逐条核对过「是否被该组件自己的 PACKAGE_PREFIX 覆盖」。只有一条**该命中却不再命中**，
它不是误判、是规则原本在干真活，所以补一个精确前缀顶替：

    com.android.dahua       大华移动视频 SDK   （原由 playbackactivity 覆盖：
                                                 com.android.dahua.dhplaymodule.*；
                                                 该组件既有前缀 com.dahuatech / com.mm.dss 盖不住）

**另一处看似损失、实则不是**：`initprovider` 原本还覆盖
`com.huawei.hms.aaid.InitProvider`，而「华为推送服务」的前缀盖不住它。第一版据此给它加了
`com.huawei.hms.aaid` 前缀——**这是错的**：该前缀已属于组件 740「华为 AAID 设备标识」
（weight 40），加过去等于制造重复登记，且会把 AAID 的类判给推送服务。
真相是**这条后缀本来就在误判**——AAID 初始化 Provider 是设备标识组件的类，
不该记在推送服务名下。删掉后它由 740 的前缀正确命中，无损失。

其余命中全部落在组件自己的前缀下，或本身就是要判死的误判。顺带一个副作用是好的：
`com.yitong.common.zxing.CaptureActivity`（屹通自己重新打包的 ZXing）删掉后缀后
会改由 `com.yitong.common` 命中**屹通**——比判给 ZXing 更贴事实。

## 不在这里做的两件事（见报告）

① `oppopushservice` / `oppoapppushservice` 挂在 OPPO 名下，但实测命中的类是
   `com.igexin.sdk.*`（个推的桥接类）——这是**归属方错了**，不是后缀通用，
   改法（重指给个推 vs 直接删）需要产品口径，故只报不改。
② WorkManager 的 4 条（systemalarm/systemjob/systemforeground/reschedulereceiver）
   取值通用，但实测**归属正确**（命中 androidx.work.impl.*）。删它是降噪、留它是召回，
   同一个选择留给人拍板。
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                                    # noqa: E402
from app.models.kb import KBComponent, KBComponentFingerprint                 # noqa: E402

# (fingerprint_id, 取值, 组件名, 依据类型, 依据)
# 组件名只用于**校验**——id 对不上组件就不动它，防止改错行。
DELETIONS = [
    # ---- MEASURED：实测命中了别家的类 ----
    (3887, "mainactivity", "屹通移动银行框架 (Ares 平台)", "MEASURED",
     "命中 com.sunyard...customerivcollectsysmainactivity（信雅达）、"
     "com.uusense.uuspeed...MainActivity（3 条里 2 条非屹通）"),
    (3888, "loginactivity", "屹通移动银行框架 (Ares 平台)", "MEASURED",
     "命中 com.csii.iap.ui.LoginActivity（营行企业银行，已落库）、"
     "com.uusense.uuspeed...LoginActivity（3 条里 2 条非屹通）"),
    (3889, "webviewactivity", "屹通移动银行框架 (Ares 平台)", "MEASURED",
     "命中 com.baidu.oauth.sdkbqt...、com.kwad...AdWebViewActivity（快手广告）、"
     "com.uusense...miguwebviewactivity（5 条里 4 条非屹通）"),
    (3682, "captureactivity", "ZXing", "MEASURED",
     "命中 com.tencent.cloud.huiyansdkocr.ui.CaptureActivity（腾讯云慧眼 OCR，已落库）"),
    (3690, "resultactivity", "Face++ 活体检测 SDK", "MEASURED",
     "命中 com.kwad.sdk.api.proxy.app.PayResultActivity（快手广告）"),
    (3760, "playbackactivity", "大华移动视频 SDK", "MEASURED",
     "命中 com.kwad.sdk...$GoodsPlaybackActivity（快手广告）"),
    (3771, "pushservice", "个推消息推送 SDK", "MEASURED",
     "命中 com.heytap.mcssdk.PushService（OPPO）、"
     "com.xiaomi.push.service.XMPushService（小米）（6 条里 5 条非个推；"
     "个推自己的三个桥接类由前缀 com.igexin.sdk 覆盖）"),
    (3796, "pushreceiver", "华为推送服务", "MEASURED",
     "命中 com.igexin.sdk.MiuiPushReceiver（个推）"),
    (3798, "transactivity", "华为推送服务", "MEASURED",
     "命中 com.sina.weibo.sdk.share.ShareTransActivity（微博）"),
    (3799, "initprovider", "华为推送服务", "MEASURED",
     "命中 com.google.android.gms.ads.MobileAdsInitProvider（Google Ads）、"
     "com.google.mlkit...MlKitInitProvider（ML Kit）（3 条里 2 条非华为）"),

    # ---- NAMING：通用 Android 组件名 / 通用英文词，组件另有前缀兜底 ----
    (4008, "schemeactivity", "神策分析 Android SDK", "NAMING",
     "SchemeActivity 是深链（scheme）的通用落地页命名，与神策无绑定"),
    (3956, "authactivity", "QQ 互联 SDK", "NAMING",
     "AuthActivity 是凡有登录/授权流程的 App 都可能取的名字"),
    (3894, "callingactivity", "SANA 音视频通话 SDK", "NAMING",
     "CallingActivity 是通用通话页命名"),
    (3896, "callbroadcastreceiver", "SANA 音视频通话 SDK", "NAMING",
     "CallBroadcastReceiver 是通用通话广播命名"),
    (3739, "imagechooseactivity", "MultiPhotoPicker", "NAMING",
     "ImageChooseActivity 是通用选图页命名"),
    (3740, "imagealbumactivity", "MultiPhotoPicker", "NAMING",
     "ImageAlbumActivity 是通用相册页命名"),
    (3786, "messagehandleservice", "小米推送 SDK", "NAMING",
     "MessageHandleService 是通用消息服务命名，各家推送都可能取同名"),
    (4020, "statservice", "百度移动统计", "NAMING",
     "StatService 是通用统计服务命名——**同一取值被腾讯 MTA 也登记了**，本身即证明它不具区分度"),
    (4113, "statservice", "腾讯移动分析 MTA（旧版）", "NAMING",
     "同上；两条 StatService 是跨厂商撞名，一并清掉"),
    (3797, "pushprovider", "华为推送服务", "NAMING",
     "PushProvider 是通用推送 Provider 命名（华为自己的那条由前缀覆盖）"),
    (3958, "tencent", "QQ 互联 SDK", "NAMING",
     "取值为厂商英文名本身，任何 endswith('tencent') 的类都会命中"),
    (4094, "subscribe", "EventBus", "NAMING",
     "Subscribe 是通用英文词（EventBus 的注解类由前缀 org.greenrobot.eventbus 覆盖）"),
    (4098, "route", "ARouter", "NAMING",
     "Route 是通用英文词（ARouter 的注解类由前缀 com.alibaba.android.arouter 覆盖）"),
    (4090, "typeadapter", "Gson", "NAMING",
     "TypeAdapter 是序列化库通用命名（Gson 自己的由前缀 com.google.gson 覆盖）"),
    (4021, "autotrack", "百度移动统计", "NAMING",
     "AutoTrack 是多家统计 SDK 共用的埋点术语（神策、GrowingIO 均有同名类）"),
    (3922, "crashreport", "腾讯 Bugly", "NAMING",
     "CrashReport 是崩溃采集库通用命名（Bugly 自己的由前缀 com.tencent.bugly 覆盖）"),
]

# (组件名, 新增前缀, 依据)：顶替被删后缀原本覆盖到的、前缀没盖住的真实类。
# 注意：像 com.huawei.hms.aaid 这种**已经属于别的组件**的前缀不要往这里加——
# 那会制造重复登记，且是错判；正确做法是让那条后缀消失（它本来就在误判）。
PREFIX_ADDITIONS = [
    ("大华移动视频 SDK", "com.android.dahua",
     "被删的 playbackactivity/playonlineactivity 原本覆盖 com.android.dahua.dhplaymodule.*，"
     "而该组件既有前缀只有 com.dahuatech / com.mm.dss，盖不住"),
]

# 本脚本第一版（已执行过一次）把 com.huawei.hms.aaid 错加到了「华为推送服务」上，
# 而该前缀已属于组件 740「华为 AAID 设备标识」。这里把它撤掉——**记录在案，不静默删**。
# (fingerprint_id, 值, 组件名)：三者任一不符就不动。
UNDO_BAD_ADDITION = [
    (13989, "com.huawei.hms.aaid", "华为推送服务",
     "AAID 前缀本属于组件 740「华为 AAID 设备标识」（weight 40）；加到推送服务上是重复登记，"
     "且会把设备标识的类判给推送服务。见模块文档「一处真损失」一节。"),
]

# 已落库、且**整条 component_hit 都建立在该误判之上**的命中，一并清掉。
# (component_hit_id, 期望命中值)：**不要用 fingerprint_id 做查询键**——删除步骤会先把
# `hit_evidence.fingerprint_id` 置 NULL（FK 无 ON DELETE，必须先摘引用），置空后就找不到了。
FALSE_HIT_PURGE = [
    (5559, "com.tencent.cloud.huiyansdkocr.ui.CaptureActivity",
     "营口银行 com.csii.yk.ui：腾讯云慧眼 OCR 的 CaptureActivity 被判成 ZXing，"
     "该 hit 唯一证据即此条（evidence_count=1）"),
    (5571, "com.csii.iap.ui.LoginActivity",
     "营行企业银行 com.csii.mobile.iap.ykcb：csii 的 LoginActivity 被判成屹通移动银行框架，"
     "该 hit 唯一证据即此条（evidence_count=1）"),
]

# 只报告、不改的数据问题
REPORT_ONLY = """\
① 「X Push(Y Proxy)」口径那条之外，另有**归属方错**的一组（不是后缀通用问题）：
     oppopushservice      同时挂在 OPPO/HeyTap 推送 SDK 与 个推消息推送 SDK
     oppoapppushservice   挂在 OPPO/HeyTap 推送 SDK
   实测命中的类都是 com.igexin.sdk.*（个推的 OPPO 通道桥接类），**归属方应为个推**。
   改法（把 OPPO 名下那两条重指给个推 vs 直接删）取决于「通道方 vs 指纹方」的口径，
   与 2026-09-29 已定的 Proxy 口径有关，需要产品拍板，故不改。

② WorkManager 的 4 条后缀取值通用，但实测归属**正确**（命中 androidx.work.impl.*）：
     systemalarmservice / systemjobservice / systemforegroundservice / reschedulereceiver
   删它降噪、留它召回，利弊相当，留给产品决定。

③ 未删但同属「通用词」的 6 条（实测各命中 1 条且都正确，暂留观察）：
     assistactivity(QQ) pushmessagehandler(小米) servicediscovery(华为 AGC)
     appmeasurement(Firebase) paytask/authtask(支付宝) realcall(OkHttp)
"""


def main() -> None:
    p = argparse.ArgumentParser(description="清理通用后缀指纹")
    p.add_argument("--apply", action="store_true", help="真写库；缺省为干跑")
    args = p.parse_args()

    db = SessionLocal()
    try:
        comps = {c.id: c for c in db.query(KBComponent).all()}
        comp_by_name = {c.name: c for c in comps.values()}
        deleted = added = purged = skipped = undone = 0

        print("== 删除通用后缀指纹 ==")
        for fid, value, comp_name, kind, basis in DELETIONS:
            fp = db.get(KBComponentFingerprint, fid)
            # 校验：id 必须仍然指向「那个组件的那个取值」，否则不动
            if fp is None or fp.normalized_value != value or fp.match_mode != "SUFFIX" \
                    or comps.get(fp.component_id) is None \
                    or comps[fp.component_id].name != comp_name:
                got = "不存在" if fp is None else \
                    f"{fp.normalized_value}/{fp.match_mode}/" \
                    f"{comps[fp.component_id].name if fp.component_id in comps else '?'}"
                print(f"   !! 跳过 id={fid}（期望 {value}/{comp_name}，实为 {got}）")
                skipped += 1
                continue
            print(f"   [{kind}] id={fid:<5} {value:<26} {comp_name}")
            print(f"          依据：{basis}")
            if args.apply:
                # hit_evidence.fingerprint_id 是 FK 且无 ON DELETE：先摘引用再删
                from sqlalchemy import text
                db.execute(text(
                    "UPDATE privacy_scan.hit_evidence SET fingerprint_id = NULL "
                    "WHERE fingerprint_id = :fid"), {"fid": fid})
                db.delete(fp)
                deleted += 1

        print("\n== 补精确前缀（顶替被删后缀覆盖到的真实类）==")
        for comp_name, prefix, basis in PREFIX_ADDITIONS:
            comp = comp_by_name.get(comp_name)
            if comp is None:
                print(f"   !! 找不到组件 {comp_name}")
                skipped += 1
                continue
            dup = db.query(KBComponentFingerprint).filter(
                KBComponentFingerprint.component_id == comp.id,
                KBComponentFingerprint.fingerprint_type == "PACKAGE_PREFIX",
                KBComponentFingerprint.normalized_value == prefix,
                KBComponentFingerprint.match_mode == "PREFIX").first()
            print(f"   {comp_name:<22} + PACKAGE_PREFIX {prefix}"
                  f"{'（已存在，跳过）' if dup else ''}")
            print(f"          依据：{basis}")
            if args.apply and not dup:
                db.add(KBComponentFingerprint(
                    component_id=comp.id, fingerprint_type="PACKAGE_PREFIX",
                    value=prefix, normalized_value=prefix, match_mode="PREFIX",
                    evidence_role="PRIMARY", weight=30,
                    raw_data={"added_by": "prune_generic_suffix_fingerprints",
                              "basis": basis}))
                added += 1

        print("\n== 撤销本脚本第一版加错的前缀 ==")
        for fid, value, comp_name, why in UNDO_BAD_ADDITION:
            fp = db.get(KBComponentFingerprint, fid)
            if fp is None or fp.normalized_value != value or fp.match_mode != "PREFIX" \
                    or comps.get(fp.component_id) is None \
                    or comps[fp.component_id].name != comp_name:
                print(f"   -- id={fid} 不在库中（已撤销或从未写入），跳过")
                continue
            print(f"   id={fid} 删除 {comp_name} 下的 {value}")
            print(f"          {why}")
            if args.apply:
                db.delete(fp)
                undone += 1

        print("\n== 清掉建立在误判之上的已落库命中 ==")
        from sqlalchemy import text
        for hit_id, want_value, why in FALSE_HIT_PURGE:
            # 按 (hit, 证据值) 找，**不按 fingerprint_id**：上一步已把它置 NULL。
            row = db.execute(text(
                "SELECT he.id, he.evidence_value, kc.name AS comp "
                "FROM privacy_scan.hit_evidence he "
                "JOIN privacy_scan.component_hit ch ON ch.id = he.component_hit_id "
                "JOIN privacy_kb.component kc ON kc.id = ch.component_id "
                "WHERE he.component_hit_id = :hit AND he.evidence_value = :val"),
                {"hit": hit_id, "val": want_value}).first()
            if row is None:
                print(f"   !! 跳过 hit={hit_id}（找不到该误判证据，可能已清理）")
                skipped += 1
                continue
            n_ev = db.execute(text(
                "SELECT count(*) FROM privacy_scan.hit_evidence WHERE component_hit_id = :h"),
                {"h": hit_id}).scalar()
            print(f"   hit={hit_id} 判给「{row.comp}」，证据 {n_ev} 条")
            print(f"          {why}")
            if args.apply:
                # 该 hit 的唯一证据就是这条误判 → hit 本身一并删（否则会留下空壳归属）
                db.execute(text("DELETE FROM privacy_scan.component_hit WHERE id = :h"),
                           {"h": hit_id})
                purged += 1

        if args.apply:
            db.commit()
            print("\n=== 已写入 ===")
        else:
            db.rollback()
            print("\n=== 干跑（未写库，已回滚）===")
        print(f"  删除后缀指纹 : {deleted}"
              f"{'' if args.apply else ' (dry)'}")
        print(f"  新增前缀     : {added}{'' if args.apply else ' (dry)'}")
        print(f"  撤销加错前缀 : {undone}{'' if args.apply else ' (dry)'}")
        print(f"  清理误判命中 : {purged}{'' if args.apply else ' (dry)'}")
        print(f"  跳过         : {skipped}")
        print(f"\n{REPORT_ONLY}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
