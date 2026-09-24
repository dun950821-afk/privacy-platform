"""从 Observation 生成 Platform Finding。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import EngineObservation, FindingObservation, PlatformFinding
from app.services.correlation import correlate
from app.services.finding_baseline import apply_mas_mapping, baseline_state


def generate_findings(db: Session, task_id: int) -> list[PlatformFinding]:
    rows = db.query(EngineObservation).filter(EngineObservation.task_id == task_id).all()
    observations = [{
        "id": o.id, "observation_type": o.observation_type, "subject": o.subject if hasattr(o, "subject") else None,
        "payload": o.payload or {}, "engine_type": o.engine_type, "rule_code": o.rule_code,
        "severity": o.severity,
    } for o in rows]
    produced = []
    for finding in correlate(observations):
        apply_mas_mapping(finding)
        existing = db.query(PlatformFinding).filter(
            PlatformFinding.task_id == task_id, PlatformFinding.dedup_key == finding["dedup_key"]
        ).first()
        if existing:
            existing.observation_count = len(finding.get("observation_ids", []))
            produced.append(existing)
            continue
        record = PlatformFinding(
            task_id=task_id, finding_code=finding["finding_code"], title=finding["title"],
            category=finding["category"], severity=finding["severity"], confidence="medium",
            triage_status="needs_review", baseline_state=baseline_state(None, finding),
            recommendation=finding.get("recommendation"),
            masvs_controls=finding.get("masvs_controls", []), maswe_ids=finding.get("maswe_ids", []),
            mastg_test_ids=finding.get("mastg_test_ids", []),
            dedup_key=finding["dedup_key"], observation_count=len(finding.get("observation_ids", [])),
        )
        db.add(record)
        db.flush()
        for observation_id in finding.get("observation_ids", []):
            db.add(FindingObservation(finding_id=record.id, observation_id=observation_id))
        produced.append(record)
    db.commit()
    return produced
