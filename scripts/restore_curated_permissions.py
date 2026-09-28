# scripts/restore_curated_permissions.py
"""按 data/kb/curated_permission_snapshot.tsv 回填人工判定的权限字段。幂等，不联网。

这是「从仓库里的原始来源文件重建」的一环。AOSP 清单产不出 capability / grant_mode /
category（它不提供描述文本），也产不出 `已弃用权限` / `危险权限（受限）` /
`三方声明权限` 这类 permission_type——它们只存在于这张快照里。少了这一步，重建出来的库
会丢掉这些人工成果，而 `is_applicable` 正是从 permission_type 推的。

回填规则（保守，只填机器推不出来的东西）：

- capability / grant_mode / category：**只在库中为空时填**，不覆盖已有值。
- permission_type：只填快照里**解析器产不出来**的取值（不在 PARSER_PRODUCIBLE_TYPES 里），
  且**不覆盖库里已有的人工值**；机器算得出来的值留给导入器去更新（Ruling M'）——
  在这里回填会把它挡在门外，正是 M' 要修的那个全库冻结。
- 快照里有、库里没有的行会被**创建**：103 行里有 20 行不在 AOSP 清单里
  （`com.*` 三方声明权限、若干已废弃的 `android.permission.*`），不建则重建不全。

用法：`/tmp/venv/bin/python scripts/restore_curated_permissions.py`
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                     # noqa: E402
from app.models.kb import KBImportBatch, KBPermission          # noqa: E402
from app.services.permission_taxonomy import (                  # noqa: E402
    PARSER_PRODUCIBLE_TYPES,
)

KB = pathlib.Path(__file__).resolve().parent.parent / "data" / "kb"
SNAPSHOT = KB / "curated_permission_snapshot.tsv"
# 快照是 Android 权限的人工整理成果（103 行全是 android.* / com.* 命名）
PLATFORM = "ANDROID"
# 只有解析器产不出来的字段才需要回填；permission_type 另按可产出性判定
FILL_IF_EMPTY = ("capability", "grant_mode", "category")
COLUMNS = ("permission_name", "capability", "grant_mode", "category", "permission_type")


def read_snapshot(path: pathlib.Path) -> list[dict]:
    """读快照。`|` 分隔（**不是** tab），`#` 起首为注释行。"""
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) != len(COLUMNS):
            raise SystemExit(
                f"{path.name}:{lineno} 期望 {len(COLUMNS)} 列（`|` 分隔），实际 {len(parts)} 列")
        rows.append(dict(zip(COLUMNS, parts)))
    return rows


def main():
    rows = read_snapshot(SNAPSHOT)
    producible = PARSER_PRODUCIBLE_TYPES[PLATFORM]
    db = SessionLocal()
    created = filled = 0
    try:
        for row in rows:
            name = row["permission_name"].strip()
            if not name:
                continue
            perm = db.query(KBPermission).filter(
                KBPermission.permission_name == name).first()

            if perm is None:
                db.add(KBPermission(
                    permission_name=name, normalized_name=name.lower(), platform=PLATFORM,
                    permission_type=row["permission_type"] or None,
                    category=row["category"] or None,
                    capability=row["capability"] or None,
                    grant_mode=row["grant_mode"] or None,
                    raw_data={"platform_source": "curated_snapshot"},
                ))
                created += 1
                continue

            changed = False
            for field in FILL_IF_EMPTY:
                if row[field] and not getattr(perm, field):
                    setattr(perm, field, row[field])
                    changed = True

            wanted = row["permission_type"]
            # 解析器能算出来的取值不回填：回填会把 AOSP 的重新分类挡在门外（见 Ruling M'）
            if wanted and wanted not in producible:
                current = perm.permission_type
                # 库里已有别的人工值就不动——那是比这份快照更新的人工判定
                if current != wanted and (not current or current in producible):
                    perm.permission_type = wanted
                    changed = True

            if changed:
                filled += 1

        db.add(KBImportBatch(
            source_file="manual-corr:curated-snapshot 回填人工判定的权限字段",
            import_mode="UPSERT", status="SUCCESS",
            statistics={"reason": "从入仓的 curated_permission_snapshot.tsv 回填"
                                  "capability/grant_mode/category 与机器推不出的 permission_type",
                        "rows": len(rows), "created": created, "filled": filled},
            created_by="claude-code"))
        db.commit()
    finally:
        db.close()
    print(f"快照 {len(rows)} 行：新建 {created} 行，回填 {filled} 行")


if __name__ == "__main__":
    main()
