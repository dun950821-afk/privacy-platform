# scripts/enrich_imported_components.py
"""给 LibChecker 导入进来的组件补「有据可查」的元数据。**默认干跑，不写库。**

## 为什么只补这么点

那批组件导入时只带了名字和指纹，厂商/分类/敏感度/用途/描述/合规说明全空。
**这些字段 LibChecker 里没有**——它的 `sdk-details/` 只有 `sdk_id` 与探针定义，
规则库只有「标识 → 名称 + 类型」。所以补不出来不是没做，是**没有来源**。

试过三条路，覆盖都有限：

    从标签机械推厂商        82 / 746
    从标签关键词推分类     108 / 746
    对 Exodus tracker 库    31 / 746

**本脚本只做有依据的那部分**：标签里出现已知厂商名的，挂上厂商。
这是 746 个组件里唯一有可靠依据的一类，只有 65 个；其余**保持空白**——用
「看着像那么回事」的中文把 700 个组件填满就是编造，正是本项目一路在防的
（禁止让覆盖度看起来是够的）。

也**不做**「拿标签回填描述」那种事（`Stripe SDK` → 「Stripe SDK（第三方库）」）：
那不是补内容，是把空白填成废话，会让界面看起来「整理过了」。

## 补出来的值算「推导」不算「核实」

`verification_status` 保持 `PENDING` 不动，依据写进 `attributes`，可回查。
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                      # noqa: E402
from app.models.kb import KBComponent, KBVendor            # noqa: E402

# 曾经想用 Exodus 的 `categories` 推分类，**实测放弃**：
#
#   1) 覆盖极低——746 个组件里只命中 3 个；
#   2) 命中里还有错的——`AppLovin` 被 Exodus 标成 `Analytics`，而它是广告网络，
#      映射到「统计分析与归因」就是一条错分类。
#
# 宁可空着，也不要往 746 个组件里塞 3 条、其中一条还是错的。Exodus 的类目口径
# （它关心的是「这个 tracker 干什么」）与我们的（「这个组件属于哪一类」）不是一回事。

# 标签 → 厂商。只收**确定无疑**的：厂商名或其通用英文名出现在标签里。
VENDOR_ALIAS = {
    "腾讯": "腾讯", "tencent": "腾讯", "百度": "百度", "baidu": "百度",
    "阿里": "阿里", "alibaba": "阿里", "华为": "华为", "huawei": "华为",
    "小米": "小米", "xiaomi": "小米", "vivo": "vivo", "oppo": "OPPO/欢太",
    "google": "Google", "微软": "Microsoft", "microsoft": "Microsoft",
    "个推": "每日互动（个推）", "getui": "每日互动（个推）",
    "旷视": "旷视科技 Face++", "合合": "上海合合信息科技", "信雅达": "信雅达科技",
    "网易": "网易", "新浪": "新浪",
}

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="真正写库")
    args = p.parse_args()

    db = SessionLocal()
    try:
        vendors = {v.name: v.id for v in db.query(KBVendor).all()}
        targets = db.query(KBComponent).filter(
            KBComponent.source_type == "开源规则库",
            KBComponent.verification_status == "PENDING").all()
        print(f"待整理的组件: {len(targets)}")

        # ---- 规则 B：标签 → 厂商 ----
        ven_fill, ven_examples = 0, []
        for c in targets:
            if c.vendor_id:
                continue
            lab = (c.name or "").lower()
            alias = next((VENDOR_ALIAS[k] for k in VENDOR_ALIAS if k in lab), None)
            if not alias or alias not in vendors:
                continue
            ven_examples.append((c.name, alias))
            if args.apply:
                c.vendor_id = vendors[alias]
                c.attributes = (f"{c.attributes}；" if c.attributes else "") + \
                    f"来源依据：标签含厂商名「{alias}」"
            ven_fill += 1
        print(f"\n规则 B（标签含厂商名）可填: {ven_fill}")
        for n, v in ven_examples[:8]:
            print(f"   {n[:30]:30} -> {v}")

        if args.apply:
            db.commit()
            print(f"\n已写入：厂商 {ven_fill}")
        else:
            print(f"\n这是干跑，未写库。合计会填 {ven_fill} 个字段，"
                  f"其余 {len(targets)} 个组件的其余字段**保持空白**——没有来源，不编。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
