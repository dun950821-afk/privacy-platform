"""导入服务：幂等，且不覆盖人工编辑过的行。

权限说明是人工在界面上维护的资产，重跑一次导入就把它冲掉是不可接受的。
"""
import pytest
from sqlalchemy import text

from app.services.permission_import import SOURCE_LABEL, import_platform

P = "test.import.perm."


def _row(name, **kw):
    base = {"permission_name": name, "permission_type": "普通权限", "capability": None,
            "grant_mode": None, "official_reference": None, "raw_data": {}}
    base.update(kw)
    return base


def _cleanup(db):
    db.execute(text("delete from privacy_kb.permission where permission_name like :p"), {"p": P + "%"})
    db.commit()


@pytest.fixture(autouse=True)
def _purge_test_rows_and_batches(db):
    """导入服务**自行 commit**，所以测试造的 import_batch 行不会随事务回滚消失。

    批次不能按 source_file 前缀清：导入写的标签就是 `permission-import:ANDROID`
    / `:IOS`（真实导入用的是同一个，没有 `:test` 之类的区分），按前缀删要么漏掉
    自己造的行、要么误伤真实审计记录。所以取 id 水位线，只删本测试期间新增的批次。
    """
    floor = db.execute(text(
        "select coalesce(max(id), 0) from privacy_kb.import_batch")).scalar()
    try:
        yield
    finally:
        db.rollback()
        db.execute(text("delete from privacy_kb.permission where permission_name like :p"),
                   {"p": P + "%"})
        db.execute(text("delete from privacy_kb.import_batch where id > :floor"),
                   {"floor": floor})
        db.commit()


def test_import_inserts_then_is_idempotent(db):
    """重跑相同内容必须是无操作。

    注意 `KBPermission.updated_at` 是 default=utcnow 且**没有 onupdate**，ORM 的
    setattr 不会推进它——所以幂等不能靠时间戳，必须靠**内容比较**：
    与库中一致就不算更新。
    """
    _cleanup(db)
    try:
        rows = [_row(P + "a"), _row(P + "b")]
        first = import_platform(db, "ANDROID", rows)
        assert first == {"inserted": 2, "updated": 0, "skipped": 0}

        second = import_platform(db, "ANDROID", rows)
        assert second == {"inserted": 0, "updated": 0, "skipped": 2}, "重跑不该有任何变化"
    finally:
        _cleanup(db)


def test_import_does_not_overwrite_human_edited_row(db):
    """人工改过的行必须被跳过——这是这套导入能被反复执行的前提。"""
    _cleanup(db)
    try:
        import_platform(db, "ANDROID", [_row(P + "c", capability="机器写的")])
        db.execute(text("""
            update privacy_kb.permission set capability='人工改的', updated_at=now()
            where permission_name=:n"""), {"n": P + "c"})
        db.commit()

        result = import_platform(db, "ANDROID", [_row(P + "c", capability="机器写的")])
        assert result["skipped"] == 1
        assert result["updated"] == 0

        cap = db.execute(text("select capability from privacy_kb.permission where permission_name=:n"),
                         {"n": P + "c"}).scalar()
        assert cap == "人工改的", "人工编辑被覆盖了"
    finally:
        _cleanup(db)


def test_import_updates_row_that_import_itself_wrote(db):
    """导入自己写的行要能更新（否则第一版写错了就永远修不回来）。"""
    _cleanup(db)
    try:
        import_platform(db, "ANDROID", [_row(P + "d", capability="v1")])
        result = import_platform(db, "ANDROID", [_row(P + "d", capability="v2")])
        assert result == {"inserted": 0, "updated": 1, "skipped": 0}
    finally:
        _cleanup(db)


def test_import_writes_audit_batch_named_per_platform(db):
    _cleanup(db)
    try:
        import_platform(db, "IOS", [_row(P + "e", permission_type="用法描述键")])
        n = db.execute(text("select count(*) from privacy_kb.import_batch where source_file=:s"),
                       {"s": SOURCE_LABEL.format(platform="IOS")}).scalar()
        assert n == 1
    finally:
        _cleanup(db)


def test_import_skips_row_with_type_outside_platform_vocabulary(db):
    """一行脏取值不该毁掉整批，但也不许进库——跳过并计数。

    （API 侧是另一回事：用户手工写非法类型直接 400，见 Task 8。）
    """
    _cleanup(db)
    try:
        result = import_platform(db, "IOS", [_row(P + "f", permission_type="危险权限")])
        assert result == {"inserted": 0, "updated": 0, "skipped": 1}
        left = db.execute(text("select count(*) from privacy_kb.permission where permission_name=:n"),
                          {"n": P + "f"}).scalar()
        assert left == 0, "词表外的行不该进库"
    finally:
        _cleanup(db)


def test_import_accepts_rows_with_empty_capability(db):
    """Android 大多数行没有说明文本——空值必须能正常入库。"""
    _cleanup(db)
    try:
        result = import_platform(db, "ANDROID", [_row(P + "g", capability=None)])
        assert result["inserted"] == 1
        cap = db.execute(text("select capability from privacy_kb.permission where permission_name=:n"),
                         {"n": P + "g"}).scalar()
        assert cap is None
    finally:
        _cleanup(db)


def test_import_survives_duplicate_name_in_one_batch(db):
    """同一批里出现同名，不得让整批回滚。

    `autoflush=False` 让循环里的查询看不到本批 pending 的行，第二次 INSERT 会撞
    `permission_name` 的全局唯一键，把**整批连同审计行**一起回滚——查不到、也不知道
    发生过。上游鸿蒙解析器按计划不做去重（跨文件去重留给调用方），所以这道守卫
    必须在导入器里，不能单点依赖调用方。
    """
    _cleanup(db)
    try:
        rows = [_row(P + "dup", capability="第一次"), _row(P + "dup", capability="第二次")]
        result = import_platform(db, "ANDROID", rows)
        assert result == {"inserted": 1, "updated": 0, "skipped": 1}
        n = db.execute(text("select count(*) from privacy_kb.permission where permission_name=:n"),
                       {"n": P + "dup"}).scalar()
        assert n == 1, "同名只该进库一条"
    finally:
        _cleanup(db)


def test_import_does_not_blank_existing_value_with_none(db):
    """解析结果为 None 的字段不得把库中已有的值抹掉。

    AOSP 解析器按设计输出 capability=None（清单不提供描述文本），而库里 103 行
    ANDROID 的 capability 与 grant_mode **全部**是人工整理的成果，其中 81 行的
    权限名与 AOSP 清单重叠。少了这层保护，首次导入就会把它们静默抹成 NULL——
    而首次导入没有基线可挡。
    """
    _cleanup(db)
    try:
        import_platform(db, "ANDROID", [
            _row(P + "h", capability="人工整理的能力说明", grant_mode="运行时授权")])

        # 模拟 AOSP 解析器：同一权限名，但 capability/grant_mode 都是 None
        result = import_platform(db, "ANDROID",
                                 [_row(P + "h", capability=None, grant_mode=None)])
        assert result == {"inserted": 0, "updated": 0, "skipped": 1}, "内容没有实质变化，不该算更新"

        row = db.execute(text("""
            select capability, grant_mode from privacy_kb.permission where permission_name=:n
        """), {"n": P + "h"}).mappings().first()
        assert row["capability"] == "人工整理的能力说明", "已有值被 NULL 抹掉了"
        assert row["grant_mode"] == "运行时授权", "已有值被 NULL 抹掉了"
    finally:
        _cleanup(db)
