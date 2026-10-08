"""从 Observation 生成 Platform Finding。"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import EngineObservation, FindingObservation, PlatformFinding
from app.services.finding_baseline import baseline_state


def compute_finding_uid(finding_code: str, dedup_key: str) -> str:
    """逻辑结论 ID：同一结论重复计算保持稳定。"""
    return hashlib.sha256(f"{finding_code}|{dedup_key}".encode()).hexdigest()


# ============ Direct Finding ============
# 具备完整风险语义的观察（如 AppShark 的完整 source→sink 数据流）直接成结论，
# 不经过关联器。关联器只负责证据增强与组合推导（见设计文档 §3）。

def _field(observation, name):
    """同时接受 dict 与 ORM 对象，避免调用方因来源不同而踩坑。"""
    if isinstance(observation, dict):
        return observation.get(name)
    return getattr(observation, name, None)


def _refresh_totals(db: Session, finding: PlatformFinding) -> None:
    """把证据计数与 level 分布**重算成与关联行一致**。

    为什么不直接用调用方手里那份 obs_ids：列表接口每次读取都会跑
    `generate_direct_findings`，而它手里只有「**直接证据**」那一批；**增强证据**
    （`finding_observations.relation_type='enriched_evidence'`）是 `apply_enrichments`
    后来挂上的、也在同一张表里。用 obs_ids 会把已挂上的增强证据算漏，于是卡片上的
    「证据 N 处」小于展开后实际列出的条数。

    实测（2026-10-08）**87/118 条结论**如此，例如 finding 154：记 44、实有 137。
    前端先发现的——卡片写「证据 30 处」，展开却有 351 条。

    `finding_observations` 才是证据的**唯一真相**：详情接口返回的 `observations[]`
    就是它，计数与构成说明都必须与它一致。
    """
    ids = [r.observation_id for r in db.query(FindingObservation).filter(
        FindingObservation.finding_id == finding.id).all()]
    finding.observation_count = len(ids)
    finding.provider_level_summary = _level_summary(db, ids)


def _level_summary(db: Session, observation_ids) -> dict | None:
    """关联 observation 按 `provider_level` 的分布，如 `{"L2": 18, "L3": 2}`。

    **口径只此一处**：`generate_direct_findings` 的新建/已存在两支、
    `generate_findings` 的关联结论两支、以及 `apply_enrichments` 都调它，
    避免五份实现各写各的。

    只统计 `provider_level` 非空的：实测空值里绝大多数是**非隐私的 fact 类**
    （`fact.component` 3792、`fact.permission` 1581、`security.endpoint` 668…），
    它们本来就不属于 L2/L3/L4 三族，计进去只会让构成说明对不上
    `observation_count`。隐私类也有少量空值（`security.sensitive_api` 约 6%），
    所以**展示层不要假设 sum(summary) == observation_count**。

    接受 id 列表而不是 finding_id：新建分支在 flush 之前就要写这一列，
    那时还没有 finding_id。全空时返回 None 而不是 `{}`——展示层据此决定**整行不渲染**
    （显示「由 构成」比不显示更糟）。
    """
    ids = [i for i in observation_ids if i]
    if not ids:
        return None
    rows = db.query(EngineObservation.provider_level, func.count()).filter(
        EngineObservation.id.in_(ids),
        EngineObservation.provider_level.isnot(None),
    ).group_by(EngineObservation.provider_level).all()
    return {level: count for level, count in rows if level} or None


def is_direct_finding_observation(observation) -> bool:
    return _field(observation, "result_semantics") == "direct_finding"


def _slug(value: str) -> str:
    """转成结论码可用的 ASCII 片段；非字母数字一律折为下划线。"""
    import re
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value)).strip("_").upper()


def direct_finding_code(observation: dict) -> str:
    """结论码由平台语义字段构成，**不含 Provider 规则名**。

    命名依据类目与流向，因此换引擎（AppShark → FlowDroid）时结论码不变。
    无数据类目的安全规则退回用规则名，因为那是它唯一的稳定标识。
    """
    category = observation.get("data_category")
    sink = observation.get("sink_type")
    if category and sink:
        return "PRIVACY_%s_%s" % (_slug(category), _slug(sink))
    provider_rule = observation.get("provider_rule_id")
    if provider_rule:
        return "SECURITY_%s" % _slug(provider_rule)
    return "SECURITY_UNKNOWN"


def generate_direct_findings(db: Session, task_id: int) -> list[PlatformFinding]:
    """把具备完整风险语义的观察直接转成 Finding。

    AppShark 的一条 source→sink 数据流本身就是「某类数据流向某处」这一完整结论。
    要求它再经过关联器才能出现，正是「12 条规则命中、0 条结论」的成因。
    """
    rows = db.query(EngineObservation).filter(
        EngineObservation.task_id == task_id,
        EngineObservation.result_semantics == "direct_finding",
    ).order_by(EngineObservation.id).all()

    groups: dict[str, list] = {}
    for o in rows:
        groups.setdefault(direct_finding_code({
            "data_category": o.data_category, "sink_type": o.sink_type,
            "provider_rule_id": o.provider_rule_id}), []).append(o)

    produced = []
    for code, items in groups.items():
        obs_ids = sorted(i.id for i in items)
        dedup_key = hashlib.sha256(
            ("%s|%s" % (code, "|".join(str(i) for i in obs_ids))).encode()).hexdigest()
        existing = db.query(PlatformFinding).filter(
            PlatformFinding.task_id == task_id,
            PlatformFinding.dedup_key == dedup_key).first()
        if existing:
            produced.append(existing)   # 计数与分布由末尾的 refresh_totals 统一重算
            continue
        head = items[0]
        record = PlatformFinding(
            task_id=task_id,
            finding_code=code,
            title=_direct_title(head),
            category="privacy" if head.data_category else "security",
            severity="high" if head.data_category else "medium",
            confidence="medium",
            triage_status="needs_review",
            baseline_state="new",
            correlation_rule_id=None,          # 直接结论不来自关联规则
            correlation_rule_version=None,
            rule_snapshot={"source": "direct_finding",
                           "provider_rule_id": head.provider_rule_id,
                           "data_category": head.data_category,
                           "sink_type": head.sink_type},
            dedup_key=dedup_key,
            observation_count=len(obs_ids),
            provider_level_summary=_level_summary(db, obs_ids),
        )
        record.finding_uid = compute_finding_uid(record.finding_code, record.dedup_key)
        db.add(record)
        db.flush()
        for oid in obs_ids:
            db.add(FindingObservation(finding_id=record.id, observation_id=oid))
        produced.append(record)
    db.commit()
    return produced


def _direct_title(observation) -> str:
    if observation.data_category and observation.sink_type:
        return "%s 数据经 %s 外传" % (observation.data_category, observation.sink_type)
    return "安全风险: %s" % (observation.provider_rule_id or "未知规则")


# ============ Evidence Join ============
# 跨引擎关联只做两件事：增强已有结论（enrich），或推导单个证据不具备的新结论
# （composite，V1 未实现）。**增强绝不新增 Finding**（设计文档 §3.2）。

def apply_enrichments(db: Session, task_id: int, enrichments: list[dict]) -> int:
    """把证据增强挂到已有结论上，返回被增强的结论数。

    找不到锚点对应的结论时**什么都不做**：这说明该结论不存在（例如负向样本上
    数据流规则本来就没命中），此时凭空造一条结论就是设计文档明令禁止的同义重复。
    """
    from app.services.correlation import stronger_confidence

    # 聚合的粒度是**结论**，不是「结论 + 规则」：一条规则可能有多个锚点命中同一条
    # 结论（实测 app_version 12：设备标识的落盘结论有 2 个数据流锚点），两条规则也
    # 可能命中同一批证据。按结论聚合才既保证证据不重复 INSERT，又保证计数正确。
    # 每条规则各自留一条审计记录，用 by_rule 记下它贡献了哪些证据。
    targets: dict[int, dict] = {}
    for item in enrichments:
        anchor_id = item.get("anchor_observation_id")
        evidence_ids = item.get("evidence_observation_ids") or []
        if not anchor_id or not evidence_ids:
            continue
        target = db.query(PlatformFinding).join(
            FindingObservation, FindingObservation.finding_id == PlatformFinding.id
        ).filter(
            PlatformFinding.task_id == task_id,
            FindingObservation.observation_id == anchor_id,
            FindingObservation.relation_type == "evidence",
        ).order_by(PlatformFinding.id).first()
        if not target:
            continue
        bucket = targets.setdefault(target.id, {"finding": target, "confidence": None,
                                                "evidence": set(), "by_rule": {}})
        bucket["evidence"].update(evidence_ids)
        bucket["confidence"] = stronger_confidence(bucket["confidence"], item["confidence"])
        rule_key = (item["correlation_rule_id"], item["correlation_rule_version"])
        bucket["by_rule"].setdefault(rule_key, set()).update(evidence_ids)

    enriched = 0
    for finding_id, bucket in targets.items():
        finding = bucket["finding"]
        linked = {row.observation_id for row in db.query(FindingObservation).filter(
            FindingObservation.finding_id == finding_id)}
        added = bucket["evidence"] - linked
        if not added:
            continue
        for oid in sorted(added):
            db.add(FindingObservation(finding_id=finding_id, observation_id=oid,
                                      relation_type="enriched_evidence"))
        finding.confidence = stronger_confidence(finding.confidence, bucket["confidence"])
        finding.observation_count = len(linked) + len(added)
        # 增强会挂上新的证据 observation，level 分布要跟着重算——否则构成说明
        # 停在增强之前，与 observation_count 越差越多。
        finding.provider_level_summary = _level_summary(db, linked | added)
        # 增强来源记进 rule_snapshot 的 enrichments，不动结论本身的来源（source/规则）。
        # 不记的话，一个结论为什么是 medium_high 就无从复现了。
        snapshot = dict(finding.rule_snapshot or {})
        records = [{"correlation_rule_id": rule_id, "correlation_rule_version": rule_version,
                    "confidence": bucket["confidence"],
                    "evidence_observation_ids": sorted(added & contributed)}
                   for (rule_id, rule_version), contributed in bucket["by_rule"].items()
                   if added & contributed]
        replayed = {r["correlation_rule_id"] for r in records}
        history = [r for r in snapshot.get("enrichments", [])
                   if r["correlation_rule_id"] not in replayed]
        snapshot["enrichments"] = history + records
        finding.rule_snapshot = snapshot
        enriched += 1
    db.commit()
    return enriched


def generate_findings(db: Session, task_id: int) -> list[PlatformFinding]:
    from app.services.correlation import correlate, load_active_rules
    from app.services.observation_service import observation_view

    # 先产出直接结论，再跑关联器做证据增强
    direct = generate_direct_findings(db, task_id)

    rows = db.query(EngineObservation).filter(EngineObservation.task_id == task_id).all()
    observations = [observation_view(o) for o in rows]
    correlation = correlate(observations, load_active_rules(db))
    apply_enrichments(db, task_id, correlation.enrichments)
    produced = []
    for finding in correlation.findings:
        existing = db.query(PlatformFinding).filter(
            PlatformFinding.task_id == task_id, PlatformFinding.dedup_key == finding["dedup_key"]
        ).first()
        if existing:
            produced.append(existing)   # 同上
            continue
        record = PlatformFinding(
            task_id=task_id, finding_code=finding["finding_code"], title=finding["title"],
            category=finding["category"], severity=finding["severity"],
            confidence=finding["confidence"], triage_status="needs_review",
            baseline_state=baseline_state(None, finding),
            recommendation=finding.get("recommendation"),
            masvs_controls=finding.get("masvs_controls", []), maswe_ids=finding.get("maswe_ids", []),
            mastg_test_ids=finding.get("mastg_test_ids", []), cwe_ids=finding.get("cwe_ids", []),
            correlation_rule_id=finding.get("correlation_rule_id"),
            correlation_rule_version=finding.get("correlation_rule_version"),
            rule_snapshot=finding.get("rule_snapshot", {}),
            dedup_key=finding["dedup_key"], observation_count=len(finding.get("observation_ids", [])),
            provider_level_summary=_level_summary(db, finding.get("observation_ids", [])),
        )
        record.finding_uid = compute_finding_uid(record.finding_code, record.dedup_key)
        db.add(record)
        db.flush()
        for observation_id in finding.get("observation_ids", []):
            db.add(FindingObservation(finding_id=record.id, observation_id=observation_id))
        produced.append(record)
    # 末尾统一重算：**按 finding_observations 的实际行**刷新证据计数与 level 分布。
    #
    # 为什么不能只在「新建/已存在」两个分支里各自赋值：**当前规则不再产出的结论**
    # 两个分支都走不到，计数会一直停在旧值（实测 87/118 条结论曾如此，
    # 如 finding 1216 记 40、实有 133）。`finding_observations` 才是证据的唯一真相，
    # 而详情接口返回的 observations[] 就是它——两边必须一致。
    #
    # **必须先 flush**：本项目的 session 是 `autoflush=False`（core/database.py:14），
    # 上面刚 `db.add()` 的关联行还在 pending，不 flush 就查不到——会把计数算成 0。
    db.flush()
    for f in db.query(PlatformFinding).filter(PlatformFinding.task_id == task_id).all():
        _refresh_totals(db, f)
    db.commit()
    # 直接结论 + 关联结论一并返回。二者 dedup_key 不同域，不会互相覆盖。
    return direct + produced
