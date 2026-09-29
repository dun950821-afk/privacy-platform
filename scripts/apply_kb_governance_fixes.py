# scripts/apply_kb_governance_fixes.py
"""一次性数据修正：去重遗留 + 归类 + 类目。**默认干跑，不写库。**

每项都写清依据与依据类型（**指纹事实** / **人工判断**），便于复核。

## 覆盖项

① `X Push(Y Proxy)` 厂商口径对齐。全库 24 条里 **19 条按「指纹包名归属方」**，
   5 条按「通道方」。指纹全站在多数那侧，统一到多数口径。
   ⚠️ 这 5 条原本就有值（人工或早期导入所填），**是在覆盖已有数据**，
   与「只填空字段」的原则不同——所以单独成项、单独说明。

② 厂商重复条目合并。跨语言的归一化抓不到（`小米` vs `Xiaomi`），需显式列出。

④ 补 3 个缺失类目并回填（`蓝牙与附近设备` / `压缩与归档` / `广告过滤`）。
   这三个是 agent 逐个撞出来的——它们遇到时**没有硬套错误类目，留空了**，做法是对的。

⑤ `MTDataFilesProvider` 重新归类。它不是第三方 SDK，是 MT 管理器**二次打包**时
   塞进 APK 的 `DocumentsProvider`——是改包痕迹。

⑥ `libmonochrome` 与 `Chromium Webview` 是同一 Chromium 内核的两种构建形态
   （Monochrome 合并构建 vs 经典 android_webview 构建），**不合并**（指纹不同、
   同次扫描不会撞车），改用关系表达。
"""
import argparse
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                                    # noqa: E402
from app.models.kb import KBComponent, KBComponentRelation, KBVendor          # noqa: E402

# ① 指纹包名归属方。依据列写的是**指纹本身**，不是猜测。
PROXY_FIX = {
    "HUAWEI Push(TPNS Proxy)": ("腾讯", "指纹 com.tencent.android.hwpush.*"),
    "vivo Push(TPNS Proxy)": ("腾讯", "指纹 com.tencent.android.vivopush.*"),
    "HUAWEI Push(Aliyun Proxy)": ("阿里云", "指纹 org.android.agoo.*（阿里云移动推送）"),
    "HONOR Push(Aliyun Proxy)": ("阿里云", "指纹 org.android.agoo.*（阿里云移动推送）"),
    "vivo Push(Aliyun Proxy)": ("阿里云", "指纹 org.android.agoo.*（阿里云移动推送）"),
}

# ② 保留方 ← 被合并方。选择依据：保留引用更多、或与库内命名惯例一致的那条。
VENDOR_MERGE = {
    "小米": ["Xiaomi"],                    # 库内中国厂商惯用中文名（腾讯/百度/华为…）
    "哔哩哔哩": ["Bilibili"],
    "AdTiming": ["AdTiming（图数科技）"],   # 两条各 1 引用，取更简洁的品牌名
    # 2026-09-29 补：**品牌名 vs 法定全称**的重复。跨语言的归一化抓不到这种（同上），
    # 只能显式列出。判据是「被弃方的组件名里本来就写着保留方的品牌名」。
    "友盟+": ["友盟同欣"],                  # 友盟同欣是法定实体、友盟+ 是品牌；被弃方旗下
                                          # 组件名是「友盟+智能认证」「友盟+消息推送」——自己写着品牌名
    "MobTech（上海游昆信息技术有限公司）": ["上海游昆信息技术有限公司"],
                                          # 保留方名字里已含法定全称，是更完整的写法
}

# ④ 新增类目 + 回填。回填对象是「agent 明确说了'词表里没有所以留空'」的那些。
NEW_CATEGORY_FILL = {
    "蓝牙与附近设备": ["ABSCL"],
    "压缩与归档": ["zipw"],
    "广告过滤": ["2013"],   # 见下方 _by_id 兜底
}

# ⑤ 归类修正
RECLASSIFY = {
    "MTDataFilesProvider": ("VENDOR_COMPONENT", "系统增强与工具",
                            "不是第三方 SDK：MT 管理器二次打包时塞进 APK 的 DocumentsProvider，属改包痕迹"),
}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    try:
        comps = {c.name: c for c in db.query(KBComponent).all()}
        vendors = {v.name: v for v in db.query(KBVendor).all()}
        stats = collections.Counter()

        # ---- ① Proxy 厂商口径 ----
        print("① X Push(Y Proxy) 厂商口径对齐（覆盖已有值）")
        for name, (want, basis) in PROXY_FIX.items():
            c = comps.get(name)
            if not c:
                print(f"   !! 找不到 {name}")
                continue
            cur = next((v.name for v in vendors.values() if v.id == c.vendor_id), None)
            if cur == want:
                continue
            print(f"   {name:30} {cur} -> {want}   依据：{basis}")
            if args.apply and want in vendors:
                c.vendor_id = vendors[want].id
                c.attributes = (f"{c.attributes}；" if c.attributes else "") + \
                    f"厂商口径对齐（指纹包名归属方）：{basis}"
                stats["proxy_fixed"] += 1

        # ---- ② 厂商重复 ----
        print("\n② 厂商重复条目合并")
        for keep_name, drops in VENDOR_MERGE.items():
            keep = vendors.get(keep_name)
            if not keep:
                print(f"   !! 找不到保留方 {keep_name}")
                continue
            for dn in drops:
                d = vendors.get(dn)
                if not d:
                    continue
                refs = db.query(KBComponent).filter(KBComponent.vendor_id == d.id).count()
                print(f"   {dn} -> {keep_name}（需重指 {refs} 个组件）")
                if args.apply:
                    db.query(KBComponent).filter(KBComponent.vendor_id == d.id) \
                        .update({"vendor_id": keep.id}, synchronize_session=False)
                    db.delete(d)
                    stats["vendor_merged"] += 1
                    stats["vendor_refs_repointed"] += refs

        # ---- ④ 类目 ----
        print("\n④ 新增类目并回填")
        for cat, names in NEW_CATEGORY_FILL.items():
            print(f"   [{cat}] <- {names}")
            for n in names:
                c = comps.get(n) or (db.query(KBComponent).get(int(n)) if str(n).isdigit() else None)
                if not c:
                    print(f"      !! 找不到组件 {n}")
                    continue
                if not c.category_l1 and args.apply:
                    c.category_l1 = cat
                    c.attributes = (f"{c.attributes}；" if c.attributes else "") + \
                        f"类目为 2026-09-29 新增（{cat}）"
                    stats["category_filled"] += 1

        # ---- ⑤ 归类修正 ----
        print("\n⑤ 归类修正")
        for name, (kind, cat, why) in RECLASSIFY.items():
            c = comps.get(name)
            if not c:
                print(f"   !! 找不到 {name}")
                continue
            print(f"   {name}: kind={c.component_kind}->{kind} cat={c.category_l1}->{cat}")
            print(f"      依据：{why}")
            if args.apply:
                c.component_kind, c.category_l1 = kind, cat
                c.compliance_note = why
                stats["reclassified"] += 1

        # ---- ⑥ 同内核两种构建形态：建关系，不合并 ----
        print("\n⑥ libmonochrome 与 Chromium Webview 建关系")
        a, b = comps.get("Chromium Webview"), comps.get("libmonochrome")
        if a and b:
            dup = db.query(KBComponentRelation).filter(
                KBComponentRelation.parent_component_id == a.id,
                KBComponentRelation.child_component_id == b.id,
                KBComponentRelation.relation_type == "VARIANT_OF").first()
            print(f"   Chromium Webview --VARIANT_OF--> libmonochrome"
                  f"（{'已存在' if dup else '将新建'}）")
            if args.apply and not dup:
                db.add(KBComponentRelation(
                    parent_component_id=a.id, child_component_id=b.id,
                    relation_type="VARIANT_OF",
                    description="同一 Chromium 内核的两种构建形态（Monochrome 合并构建 vs 经典 "
                                "android_webview）。指纹不同、同次扫描不会撞车，故不合并，用关系表达。"))
                stats["relation_created"] += 1

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
