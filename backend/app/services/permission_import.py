"""把解析出来的权限行写进知识库。

两条硬规则：

1. **幂等**——按 permission_name UPSERT，重跑不重复插入。
2. **不覆盖人工编辑**——说明文本是人工在界面上维护的资产。判定基线取
   `import_batch` 里该平台最近一次导入的 finished_at；updated_at 晚于基线即视为
   人工改过，跳过。
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.kb import KBImportBatch, KBPermission
from app.services.permission_taxonomy import PLATFORMS, validate_permission_type

logger = logging.getLogger(__name__)

SOURCE_LABEL = "permission-import:{platform}"

_UPDATABLE = ("permission_type", "category", "capability", "grant_mode",
              "compliance_focus", "official_reference")


def _last_import_finished_at(db: Session, platform: str):
    return db.query(KBImportBatch.finished_at).filter(
        KBImportBatch.source_file == SOURCE_LABEL.format(platform=platform),
        KBImportBatch.finished_at.isnot(None),
    ).order_by(KBImportBatch.finished_at.desc()).limit(1).scalar()


def import_platform(db: Session, platform: str, rows: list[dict]) -> dict:
    """把一个平台的行 UPSERT 进库。自行 commit 并写审计批次。"""
    if platform not in PLATFORMS:
        raise ValueError(f"platform 只能是：{'、'.join(PLATFORMS)}")

    batch = KBImportBatch(source_file=SOURCE_LABEL.format(platform=platform),
                          import_mode="UPSERT", status="RUNNING",
                          statistics={"platform": platform})
    db.add(batch)
    db.flush()

    baseline = _last_import_finished_at(db, platform)
    inserted = updated = skipped = 0

    for row in rows:
        # 词表外的取值：跳过并计数，**不中止整批**。1018 行的导入不该死在最后一行；
        # 但也不能放它进库——受控词表就是这么失控的。API 侧（用户写）保持严格抛错。
        try:
            validate_permission_type(platform, row.get("permission_type"))
        except ValueError as exc:
            logger.warning("skip %s: %s", row.get("permission_name"), exc)
            skipped += 1
            continue

        name = (row.get("permission_name") or "").strip()
        if not name:
            continue

        existing = db.query(KBPermission).filter(KBPermission.permission_name == name).first()
        if existing is None:
            db.add(KBPermission(
                permission_name=name,
                normalized_name=name.lower(),
                platform=platform,
                permission_type=row.get("permission_type"),
                category=row.get("category"),
                capability=row.get("capability"),
                grant_mode=row.get("grant_mode"),
                compliance_focus=row.get("compliance_focus"),
                official_reference=row.get("official_reference"),
                raw_data=row.get("raw_data") or {},
            ))
            inserted += 1
            continue

        if existing.platform != platform:
            # 同名跨平台：三个平台的命名空间本不该重叠，撞上说明来源有问题，跳过并留痕
            logger.warning("skip %s: 已存在且 platform=%s", name, existing.platform)
            skipped += 1
            continue

        # 解析结果为 None 的字段**不动既有值**。这不是洁癖：AOSP 解析器按设计输出
        # capability=None（清单不提供描述文本），而库里 103 行 ANDROID 的 capability 与
        # grant_mode **全部**是人工/早期整理的成果，其中 81 行的权限名与 AOSP 清单重叠。
        # 少了这层过滤，首次导入会把它们静默抹成 NULL——而首次导入没有基线可挡。
        incoming = {f: row[f] for f in _UPDATABLE if f in row and row[f] is not None}
        incoming_raw = row.get("raw_data") or {}

        # 与库中完全一致 → 无操作。幂等**靠内容比较，不靠时间戳**：
        # updated_at 是 default=utcnow 且没有 onupdate，ORM 的 setattr 不会推进它，
        # 拿它当「导入自己写过」的标志会让每次重跑都算成 updated。
        if all(getattr(existing, f) == v for f, v in incoming.items()) \
                and (existing.raw_data or {}) == incoming_raw:
            skipped += 1
            continue

        if baseline is not None and existing.updated_at and existing.updated_at > baseline:
            skipped += 1        # 内容确有差异，但这一行在上次导入之后被人改过，不覆盖
            continue

        for field, value in incoming.items():
            setattr(existing, field, value)
        existing.raw_data = incoming_raw
        updated += 1

    # **先落盘本批的行，再盖 finished_at。** 顺序不能反：行的 updated_at 要么由
    # Python 默认值在 flush 时求值、要么由 trg_permission_updated_at 取
    # CURRENT_TIMESTAMP（= 本事务开始时刻），两者都早于「盖章」——只要盖章发生在
    # 落盘之后。反过来（沿用 brief 里的原顺序）行的 updated_at 会**晚于**自己这批的
    # finished_at，于是下一轮把本导入自己写的行判成「上次导入之后被人改过」而永远
    # 不再更新——「第一版写错了就永远修不回来」。
    db.flush()
    batch.status = "SUCCESS"
    batch.statistics = {"platform": platform, "inserted": inserted,
                        "updated": updated, "skipped": skipped}
    batch.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}
