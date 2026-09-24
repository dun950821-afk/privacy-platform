"""从 Observation 生成 Platform Finding。"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import EngineObservation, FindingObservation, PlatformFinding
from app.services.finding_baseline import baseline_state


def compute_finding_uid(finding_code: str, dedup_key: str) -> str:
    """逻辑结论 ID：同一结论重复计算保持稳定。"""
    return hashlib.sha256(f"{finding_code}|{dedup_key}".encode()).hexdigest()


def generate_findings(db: Session, task_id: int) -> list[PlatformFinding]:
    from app.services.correlation import correlate, load_active_rules

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
    return produced
