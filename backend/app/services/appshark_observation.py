"""AppShark 原始结果到 DataFlow Observation。"""

def appshark_observations(raw: dict, *, task_id: int, execution_id: int, engine_version: str = "0.1.2") -> list[dict]:
    observations = []
    for section in ("ComplianceInfo", "SecurityInfo"):
        groups = raw.get(section) or {}
        if not isinstance(groups, dict):
            continue
        for category, rules in groups.items():
            if not isinstance(rules, dict):
                continue
            for rule_id, group in rules.items():
                if not isinstance(group, dict):
                    continue
                for vuln in group.get("vulners", []) or []:
                    details = vuln.get("details") or {}
                    source = details.get("Source")
                    sink = details.get("Sink")
                    if not source and not sink:
                        continue
                    observations.append({
                        "task_id": task_id, "execution_id": execution_id,
                        "engine_type": "appshark", "engine_version": engine_version,
                        "observation_type": "dataflow.privacy",
                        "category": category, "rule_id": rule_id,
                        "severity": group.get("level"), "confidence": "medium",
                        "evidence_level": "potential",
                        "payload": {"source": source, "sink": sink, "path": details.get("path") or details.get("taintPath") or [], "details": details},
                        "evidence_refs": [], "schema_version": "1.0",
                    })
    return observations
