"""迁移后旧行必须全部落在 ANDROID 上——它们确实全是 Android 权限。"""
from sqlalchemy import text


def test_platform_column_is_backfilled_to_android(db):
    """迁移时已有的行全部回填 ANDROID。

    **不断言「全表只有 ANDROID」**——后续任务会导入鸿蒙/iOS 的行，那样断言会让
    这条测试在导入之后必然失败（T1 与 T7 都会跑全套回归）。
    """
    nulls = db.execute(text("""
        select count(*) from privacy_kb.permission
        where platform is null or platform = ''
    """)).scalar()
    assert nulls == 0, "不允许有 platform 为空的行"

    legacy = db.execute(text("""
        select platform from privacy_kb.permission
        where permission_name = 'android.permission.CAMERA'
    """)).scalar()
    assert legacy == "ANDROID", "迁移时已存在的旧行必须回填为 ANDROID"


def test_platform_column_is_not_nullable(db):
    nullable = db.execute(text("""
        select is_nullable from information_schema.columns
        where table_schema='privacy_kb' and table_name='permission' and column_name='platform'
    """)).scalar()
    assert nullable == "NO"
