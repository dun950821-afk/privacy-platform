"""从 Observation 生成 Platform Finding。"""
import hashlib
from datetime import datetime, timezone

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
            existing.observation_count = len(obs_ids)
            produced.append(existing)
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


def generate_findings(db: Session, task_id: int) -> list[PlatformFinding]:
    from app.services.correlation import correlate, load_active_rules

    # 先产出直接结论，再跑关联器做证据增强
    direct = generate_direct_findings(db, task_id)

    rows = db.query(EngineObservation).filter(EngineObservation.task_id == task_id).all()
    observations = [{
        "id": o.id, "observation_type": o.observation_type,
        "subject": o.subject, "payload": o.payload or {},
        "location": o.location, "engine_type": o.engine_type,
    } for o in rows]
    produced = []
    for finding in correlate(observations, load_active_rules(db)):
        existing = db.query(PlatformFinding).filter(
            PlatformFinding.task_id == task_id, PlatformFinding.dedup_key == finding["dedup_key"]
        ).first()
        if existing:
            existing.observation_count = len(finding.get("observation_ids", []))
            produced.append(existing)
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
        )
        record.finding_uid = compute_finding_uid(record.finding_code, record.dedup_key)
        db.add(record)
        db.flush()
        for observation_id in finding.get("observation_ids", []):
            db.add(FindingObservation(finding_id=record.id, observation_id=observation_id))
        produced.append(record)
    db.commit()
    # 直接结论 + 关联结论一并返回。二者 dedup_key 不同域，不会互相覆盖。
    return direct + produced
