from dataclasses import dataclass, field


@dataclass
class PlatformFindingData:
    task_id: int
    finding_code: str
    title: str
    category: str
    severity: str = "medium"
    confidence: str = "medium"
    triage_status: str = "needs_review"
    baseline_state: str = "new"
    description: str = ""
    recommendation: str = ""
    masvs_controls: list[str] = field(default_factory=list)
    maswe_ids: list[str] = field(default_factory=list)
    mastg_test_ids: list[str] = field(default_factory=list)
    cwe_ids: list[str] = field(default_factory=list)
    correlation_rule_id: str | None = None
    correlation_rule_version: str | None = None
    dedup_key: str = ""
    schema_version: str = "1.0"
