"""人工整理的权限快照：它是「从仓库重建」的输入，缺一列就会静默改变下游输出。

这张快照曾经只有 5 列，没有 `risk_level` / `compliance_focus`——而它俩喂给
`compliance_profile`（按 `risk_level != "CRITICAL"` 归一）与 `sdk_analysis`
（按 `risk_level in ("HIGH", "CRITICAL")` 判敏感权限）。从零重建会得到这两列全 NULL 的库，
两处输出静默变样，没有任何报错。这里的用例把「列齐、且值非空」钉住。
"""
import importlib.util
import pathlib

import pytest
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SNAPSHOT = ROOT / "data" / "kb" / "curated_permission_snapshot.tsv"
EXPECTED_ROWS = 103
P = "test.curated.snapshot."


def _restore_module():
    """加载回填脚本本身——列定义以它为唯一来源，测试不再抄一份。"""
    path = ROOT / "scripts" / "restore_curated_permissions.py"
    spec = importlib.util.spec_from_file_location("restore_curated_permissions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_has_the_columns_the_restore_script_writes():
    """列数由 read_snapshot 校验（对不上直接 SystemExit），这里钉住行数与列名。"""
    mod = _restore_module()
    rows = mod.read_snapshot(SNAPSHOT)
    assert len(rows) == EXPECTED_ROWS
    assert set(mod.COLUMNS) >= {"permission_name", "capability", "grant_mode",
                                "category", "permission_type", "risk_level",
                                "compliance_focus"}
    assert {"risk_level", "compliance_focus"} <= set(mod.FILL_IF_EMPTY), \
        "这两列必须真的会被回填，只是读出来没用"


def test_snapshot_carries_risk_level_and_compliance_focus_for_every_row():
    mod = _restore_module()
    rows = mod.read_snapshot(SNAPSHOT)
    empty = [r["permission_name"] for r in rows
             if not r["risk_level"] or not r["compliance_focus"]]
    assert empty == [], f"这些行的 risk_level/compliance_focus 是空的：{empty[:5]}"
    assert {r["risk_level"] for r in rows} <= {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def _row(name, **kw):
    base = {"permission_name": name, "capability": "能力说明", "grant_mode": "运行时授权",
            "category": "分类", "permission_type": "三方声明权限",
            "risk_level": "HIGH", "compliance_focus": "关注点"}
    base.update(kw)
    return base


def _purge(db, *names):
    db.execute(text("delete from privacy_kb.permission where permission_name = any(:n)"),
               {"n": list(names)})
    db.commit()


def test_upsert_row_creates_a_missing_row_with_every_field(db):
    """快照里有、库里没有的行（20 行 `com.*` 与废弃权限）必须建出来，六列一个不能漏。

    从零重建时这 20 行只经过这条路径——漏掉 risk_level/compliance_focus 的话
    `compliance_profile` 与 `sdk_analysis` 的输出会静默变样。
    """
    mod = _restore_module()
    name = P + "create"
    _purge(db, name)
    try:
        outcome = mod.upsert_row(db, _row(name), mod.PARSER_PRODUCIBLE_TYPES[mod.PLATFORM])
        db.commit()
        assert outcome == "created"
        got = db.execute(text("""
            select platform, permission_type, capability, grant_mode, category,
                   risk_level, compliance_focus
            from privacy_kb.permission where permission_name = :n
        """), {"n": name}).mappings().first()
        assert dict(got) == {"platform": "ANDROID", "permission_type": "三方声明权限",
                             "capability": "能力说明", "grant_mode": "运行时授权",
                             "category": "分类", "risk_level": "HIGH",
                             "compliance_focus": "关注点"}
    finally:
        _purge(db, name)


def test_upsert_row_fills_empty_fields_and_keeps_newer_human_values(db):
    """只填空字段；库里已有的人工值（比快照新的判定）不动。"""
    mod = _restore_module()
    name = P + "fill"
    _purge(db, name)
    try:
        db.execute(text("""
            insert into privacy_kb.permission
              (permission_name, normalized_name, platform, permission_type, category,
               risk_level, raw_data)
            values (:n, :n, 'ANDROID', '已弃用权限', '人工改过的分类', 'CRITICAL', '{}')
        """), {"n": name})
        db.commit()

        row = _row(name, permission_type="危险权限（受限）")
        outcome = mod.upsert_row(db, row, mod.PARSER_PRODUCIBLE_TYPES[mod.PLATFORM])
        db.commit()
        assert outcome == "filled"

        got = db.execute(text("""
            select permission_type, category, risk_level, capability, grant_mode,
                   compliance_focus
            from privacy_kb.permission where permission_name = :n
        """), {"n": name}).mappings().first()
        # 空的三列被填上
        assert got["capability"] == "能力说明"
        assert got["grant_mode"] == "运行时授权"
        assert got["compliance_focus"] == "关注点"
        # 已有的值一律不动——哪怕快照写的是另一个取值
        assert got["category"] == "人工改过的分类"
        assert got["risk_level"] == "CRITICAL"
        assert got["permission_type"] == "已弃用权限"
    finally:
        _purge(db, name)


def test_snapshot_reader_rejects_a_type_outside_the_vocabulary(tmp_path):
    """回填脚本是自由文本进入受控词表的最后一条路径，必须自己校验。"""
    mod = _restore_module()
    bad = tmp_path / "bad.tsv"
    bad.write_text("android.permission.X|能力|授权|分类|危险/已弱化|HIGH|关注点\n",
                   encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.read_snapshot(bad)


def test_snapshot_reader_rejects_a_truncated_row(tmp_path):
    """少列（比如把 7 列的老格式喂回来）要炸，不能静默按位错读。"""
    mod = _restore_module()
    bad = tmp_path / "short.tsv"
    bad.write_text("android.permission.X|能力|授权|分类|普通权限\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.read_snapshot(bad)
