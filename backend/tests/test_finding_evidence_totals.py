"""结论的证据计数必须等于它**实际关联**的证据行数。

## 改这个的由来（2026-10-08）

前端报「卡片上写『证据 30 处』，展开却有 351 条」。查下来是间歇性的：被
`generate_direct_findings` 重置过、又没被 `apply_enrichments` 回写的那些结论会少算。

    finding 61: count=27  直接=2   增强=25  关联行=27   ✓
    finding 91: count=2   直接=2   增强=25  关联行=27   ✗ 少算 25

根因：列表接口每次读取都跑 `generate_direct_findings`，它的「已存在」分支把
`observation_count` 重置为**直接证据数**；随后 `apply_enrichments` 看到
`added` 已为空就 `continue`，不再回写。而 `finding_observations` 里的
`enriched_evidence` 行一直在。

## 为什么用「关联行数」当判据

先前的验证是 `sum(provider_level_summary) == observation_count`——**两者同源**，
所以那是同义反复，测不出这一类错。这里改用一个**独立**口径：
计数必须等于 `finding_observations` 的实际行数。详情接口返回的
`observations[]` 也正是这个集合，两边必须一致。
"""
import pytest
from sqlalchemy import text

from app.models import FindingObservation, PlatformFinding


def _linked(db, finding_id: int) -> int:
    return db.query(FindingObservation).filter(
        FindingObservation.finding_id == finding_id).count()


def test_counts_match_linked_rows_after_regeneration(db):
    """跑一遍生成流程后，每个结论的计数都应等于它的关联行数。"""
    from app.services.finding_service import generate_findings

    task_ids = [r[0] for r in db.query(PlatformFinding.task_id).group_by(
        PlatformFinding.task_id).limit(12).all()]
    if not task_ids:
        pytest.skip("库里没有结论，跳过")
    for tid in task_ids:
        generate_findings(db, tid)

    # **只断言跑过的任务**：没跑生成的结论不在本次修复范围内（它们的计数由各自的
    # 读取路径刷新），拿全库断言会把无关结论算进来。
    rows = db.query(PlatformFinding).filter(PlatformFinding.task_id.in_(task_ids)).all()
    bad = [(f.id, f.observation_count, _linked(db, f.id))
           for f in rows if f.observation_count != _linked(db, f.id)]
    assert not bad, (
        "以下结论的 observation_count 与实际关联的证据行数不符（id, 记的数, 实际行数）：\n"
        + "\n".join(f"  {i}: {c} vs {n}" for i, c, n in bad[:10])
        + f"\n共 {len(bad)}/{len(rows)} 条不符")


def test_summary_covers_the_same_evidence_as_the_count(db):
    """构成说明是**有 level 的子集**，不得超过计数。

    注意这里**不能**断言 `sum(summary) == observation_count`：计数包含全部关联证据
    （含 `fact.*` 这类无 provider_level 的），说明只统计有 level 的。先前我就是用
    「sum == count」验证的——两者同源，所以那是**同义反复**，测不出任何东西。
    """
    rows = db.query(PlatformFinding).filter(PlatformFinding.observation_count > 0).all()
    bad = []
    for f in rows:
        if not f.provider_level_summary:
            continue
        total = sum(f.provider_level_summary.values())
        if total > f.observation_count:
            bad.append((f.id, total, f.observation_count))
    assert not bad, (
        "构成说明的合计大于计数（id, 说明合计, 计数）——说明覆盖了不属于本结论的证据：\n"
        + "\n".join(f"  {i}: {t} vs {c}" for i, t, c in bad[:10])
        + f"\n共 {len(bad)} 条不符")
