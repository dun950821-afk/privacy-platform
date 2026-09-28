"""把解析出来的权限行写进知识库。

两条硬规则：

1. **幂等**——按 permission_name UPSERT，重跑不重复插入。
2. **不覆盖人工编辑**——说明文本是人工在界面上维护的资产。判定基线取
   `import_batch` 里该平台最近一次导入的 finished_at；updated_at 晚于基线即视为
   人工改过，跳过。
"""
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.kb import KBImportBatch, KBPermission
from app.services.permission_taxonomy import (
    PARSER_PRODUCIBLE_TYPES, PLATFORMS, validate_permission_type,
)

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
    seen_names: set[str] = set()
    # 本事务的数据库时钟。`now()` = **事务开始时刻**，本事务内恒定不变——读一次即可。
    # 本批写下的每一行（INSERT 显式带上它、UPDATE 由触发器写 CURRENT_TIMESTAMP）
    # 与 batch.finished_at 都落在**这同一个 DB 时钟值**上，被比较的两个时间戳不再
    # 一个是应用时钟、一个是数据库时钟。详见函数末尾。
    db_now = db.execute(text("select now()")).scalar()

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
            skipped += 1        # 空名也要计数，否则审计数字对不上 len(rows)
            continue
        if name in seen_names:
            # 同一批里出现同名：`autoflush=False`（core/database.py）让循环里的查询
            # 看不到本批 pending 的行，第二次 INSERT 会撞 permission_name 的全局唯一键，
            # **整批连同审计行一起回滚且不留痕**——查不到、也不知道发生过。
            # 上游解析器（Android/iOS）各自去重，但鸿蒙那支按计划把跨文件去重留给了
            # 调用方；与其单点依赖调用方，不如在这里挡住。
            skipped += 1
            continue
        seen_names.add(name)

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
                # 别让 ORM 的 Python 默认值（应用时钟，在 flush 时才求值）写这个字段：
                # 它必须与 batch.finished_at 同源，否则这一行下一轮会被判成「人工改过」。
                updated_at=db_now,
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
        # grant_mode **全部**是人工/早期整理的成果，其中 83 行的权限名与 AOSP 清单重叠。
        # 少了这层过滤，首次导入会把它们静默抹成 NULL——而首次导入没有基线可挡。
        incoming = {f: row[f] for f in _UPDATABLE if f in row and row[f] is not None}
        # `permission_type` 另有保护，但**只保护解析器产不出来的取值**。
        #
        # 不能写成「只要非空就不覆盖」：解析器从不返回空，首跑之后每一行都非空，
        # 于是 AOSP 的重新分类**永远进不来**，全库冻结在这个字段上——而 `is_applicable`
        # 正是从它推的，错误会是全库级的。
        #
        # 判据：值在 PARSER_PRODUCIBLE_TYPES[platform] 里 → 机器算得出来，让它更新；
        # 不在 → 那是人工判定的知识（`已弃用权限`/`危险权限（受限）`/`三方声明权限`），
        # 覆盖会把信息不可逆地抹掉。实测库里这类值且有 AOSP 判定可对照的共 **16 行**
        # （parser 逐行 diff 活库），且**每一行的 AOSP 判定都不同**：8 行
        # `危险权限（受限）`→`危险权限`、6 行 `已弃用权限`→`普通权限`、2 行
        # `三方声明权限`→`普通权限`。其中 **2 行**连 `is_applicable` 都会翻
        # （`三方声明权限` 不可达 → `普通权限` 可达）；`已弃用权限` 已归入可达
        # （见 permission_taxonomy），覆盖它不翻判定，但仍会永久丢掉「弃用」这层信息。
        if existing.permission_type \
                and existing.permission_type not in PARSER_PRODUCIBLE_TYPES[platform]:
            incoming.pop("permission_type", None)
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

    # **先 flush 落盘，再盖 finished_at。** 顺序反了曾是个真 bug：INSERT 路径的
    # `updated_at` 若由 ORM 的 Python 默认值给出（应用时钟，flush 时才求值），会晚于
    # finished_at（实测 +4.6 ms），于是下一轮把**导入自己写的行**判成「人工改过」而
    # 永不再更新。现在两个时间戳同源于 `db_now`（数据库时钟、本事务内恒定），相等而非
    # 相减——顺序不再承重，但 flush 仍要在前：它保证「所有行都已落盘」才把批次标 SUCCESS，
    # 也让写库错误在盖章之前抛出，批次不会挂着一个骗人的 SUCCESS。
    db.flush()
    batch.status = "SUCCESS"
    batch.statistics = {"platform": platform, "inserted": inserted,
                        "updated": updated, "skipped": skipped}
    # finished_at 与行的 updated_at 取**同一个数据库时钟值**。基线判定是
    # `existing.updated_at > baseline`：
    #   本批写的行   → updated_at == finished_at（同一事务的 now()）→ `>` 不成立，可更新
    #   人工改过的行 → 编辑事务的 now() 严格晚于本批        → `>` 成立，跳过
    # 全程只有数据库时钟，不存在「应用时钟 vs 数据库时钟」的偏差窗口。
    batch.finished_at = db_now
    db.commit()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}
