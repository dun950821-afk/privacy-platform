"""SQLAlchemy数据模型"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, Float, Date,
    DateTime, JSON, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ============ 组织与认证 ============

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True)
    full_name = Column(String(100))
    phone = Column(String(20))
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="viewer")
    status = Column(String(20), nullable=False, default="active")
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    projects = relationship("ProjectMember", back_populates="user")


class Project(Base):
    __tablename__ = "projects"
    id = Column(BigInteger, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    owner_id = Column(BigInteger, ForeignKey("users.id"))
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    apps = relationship("AppAsset", back_populates="project", cascade="all, delete-orphan")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    __tablename__ = "project_members"
    id = Column(BigInteger, primary_key=True)
    project_id = Column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), nullable=False, default="tester")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    project = relationship("Project", back_populates="members")
    user = relationship("User", back_populates="projects")


# ============ App资产 ============

class AppAsset(Base):
    __tablename__ = "app_assets"
    id = Column(BigInteger, primary_key=True)
    project_id = Column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    package_name = Column(String(255), nullable=False)
    app_name = Column(String(200), nullable=False)
    app_alias = Column(String(200))
    app_type = Column(String(50), default="android")
    category = Column(String(100))
    department = Column(String(200))
    vendor = Column(String(200))
    owner_id = Column(BigInteger, ForeignKey("users.id"))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("project_id", "package_name"),)

    project = relationship("Project", back_populates="apps")
    versions = relationship("AppVersion", back_populates="app", cascade="all, delete-orphan")
    privacy_policies = relationship("PrivacyPolicy", back_populates="app", cascade="all, delete-orphan")


class AppVersion(Base):
    __tablename__ = "app_versions"
    id = Column(BigInteger, primary_key=True)
    app_id = Column(BigInteger, ForeignKey("app_assets.id", ondelete="CASCADE"), nullable=False)
    version_name = Column(String(100), nullable=False)
    version_code = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    file_size = Column(BigInteger)
    min_sdk = Column(Integer)
    target_sdk = Column(Integer)
    signature_info = Column(JSONB)
    artifact_path = Column(String(500))
    channel = Column(String(100))
    build_time = Column(DateTime(timezone=True))
    upload_notes = Column(Text)
    uploaded_by = Column(BigInteger, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    app = relationship("AppAsset", back_populates="versions")
    tasks = relationship("DetectionTask", back_populates="app_version")
    __table_args__ = (
        Index("idx_app_versions_app", "app_id"),
        Index("idx_app_versions_sha", "sha256"),
    )


class PrivacyPolicy(Base):
    __tablename__ = "privacy_policies"
    id = Column(BigInteger, primary_key=True)
    app_id = Column(BigInteger, ForeignKey("app_assets.id", ondelete="CASCADE"), nullable=False)
    version = Column(String(100))
    effective_date = Column(Date)
    raw_text = Column(Text)
    raw_artifact_path = Column(String(500))
    parsed_json = Column(JSONB)
    parse_status = Column(String(20), default="pending")
    parse_model = Column(String(100))
    parse_confidence = Column(Float)
    reviewed_by = Column(BigInteger, ForeignKey("users.id"))
    reviewed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    app = relationship("AppAsset", back_populates="privacy_policies")


# ============ 检测任务 ============

class DetectionTask(Base):
    __tablename__ = "detection_tasks"
    id = Column(BigInteger, primary_key=True)
    task_code = Column(String(50), unique=True, nullable=False)
    app_version_id = Column(BigInteger, ForeignKey("app_versions.id"), nullable=False)
    privacy_policy_id = Column(BigInteger, ForeignKey("privacy_policies.id"))
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    detection_type = Column(String(50), nullable=False, default="full")
    rule_pack_version = Column(String(50), nullable=False, default="1.0")
    status = Column(String(30), nullable=False, default="draft")
    priority = Column(Integer, default=5)
    config_json = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    failed_reason = Column(Text)
    created_by = Column(BigInteger, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    app_version = relationship("AppVersion", back_populates="tasks")
    sub_tasks = relationship("SubTask", back_populates="task", cascade="all, delete-orphan")
    scenarios = relationship("DetectionScenario", back_populates="task", cascade="all, delete-orphan")
    events = relationship("DetectionEvent", back_populates="task", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="task", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="task", cascade="all, delete-orphan")
    __table_args__ = (
        Index("idx_tasks_project", "project_id"),
        Index("idx_tasks_status", "status"),
    )


class SubTask(Base):
    __tablename__ = "sub_tasks"
    id = Column(BigInteger, primary_key=True)
    task_id = Column(BigInteger, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False)
    sub_task_code = Column(String(50), unique=True, nullable=False)
    engine_type = Column(String(50), nullable=False)
    stage = Column(String(50), nullable=False, default="prepare")
    status = Column(String(30), nullable=False, default="pending")
    assigned_node_id = Column(BigInteger)
    config_json = Column(JSONB)
    result_summary = Column(JSONB)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    task = relationship("DetectionTask", back_populates="sub_tasks")


class DetectionScenario(Base):
    __tablename__ = "detection_scenarios"
    id = Column(BigInteger, primary_key=True)
    task_id = Column(BigInteger, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False)
    scenario_type = Column(String(50), nullable=False)
    consent_status = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    device_id = Column(BigInteger)
    operator_id = Column(BigInteger, ForeignKey("users.id"))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    task = relationship("DetectionTask", back_populates="scenarios")
    events = relationship("DetectionEvent", back_populates="scenario")


# ============ 事件与证据 ============

class DetectionEvent(Base):
    __tablename__ = "detection_events"
    id = Column(BigInteger, primary_key=True)
    event_uid = Column(String(50), unique=True, nullable=False)
    task_id = Column(BigInteger, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False)
    scenario_id = Column(BigInteger, ForeignKey("detection_scenarios.id"))
    event_type = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    consent_status = Column(String(30))
    data_type = Column(String(100))
    api = Column(String(500))
    caller = Column(String(500))
    sdk_id = Column(BigInteger, ForeignKey("privacy_kb.component.id"))
    trace_id = Column(String(100))
    value_fingerprint = Column(String(64))
    event_data = Column(JSONB, nullable=False, default=dict)
    engine_name = Column(String(100))
    engine_version = Column(String(50))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    task = relationship("DetectionTask", back_populates="events")
    scenario = relationship("DetectionScenario", back_populates="events")
    __table_args__ = (
        Index("idx_events_task", "task_id"),
        Index("idx_events_scenario", "scenario_id"),
        Index("idx_events_type", "event_type"),
        Index("idx_events_timestamp", "timestamp"),
    )


class Evidence(Base):
    __tablename__ = "evidence"
    id = Column(BigInteger, primary_key=True)
    evidence_uid = Column(String(50), unique=True, nullable=False)
    task_id = Column(BigInteger, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False)
    evidence_type = Column(String(50), nullable=False)
    artifact_path = Column(String(500))
    artifact_hash = Column(String(64))
    artifact_size = Column(BigInteger)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    task = relationship("DetectionTask", back_populates="evidence")
    __table_args__ = (Index("idx_evidence_task", "task_id"),)


class EventEvidence(Base):
    __tablename__ = "event_evidence"
    id = Column(BigInteger, primary_key=True)
    event_id = Column(BigInteger, ForeignKey("detection_events.id", ondelete="CASCADE"), nullable=False)
    evidence_id = Column(BigInteger, ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(50))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("event_id", "evidence_id"),)


# ============ 规则与问题 ============

class Rule(Base):
    __tablename__ = "rules"
    id = Column(BigInteger, primary_key=True)
    rule_key = Column(String(100), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(Text)
    current_version_id = Column(BigInteger)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    versions = relationship("RuleVersion", back_populates="rule", cascade="all, delete-orphan")


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    id = Column(BigInteger, primary_key=True)
    rule_id = Column(BigInteger, ForeignKey("rules.id", ondelete="CASCADE"), nullable=False)
    version = Column(String(20), nullable=False)
    rule_content = Column(JSONB, nullable=False)
    changelog = Column(Text)
    status = Column(String(20), default="draft")
    published_by = Column(BigInteger, ForeignKey("users.id"))
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("rule_id", "version"),)

    rule = relationship("Rule", back_populates="versions")


class Finding(Base):
    __tablename__ = "findings"
    id = Column(BigInteger, primary_key=True)
    finding_uid = Column(String(50), unique=True, nullable=False)
    task_id = Column(BigInteger, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(BigInteger, ForeignKey("rules.id"))
    rule_version_id = Column(BigInteger, ForeignKey("rule_versions.id"))
    scenario_id = Column(BigInteger, ForeignKey("detection_scenarios.id"))
    severity = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False, default="open")
    confidence = Column(String(20), default="confirmed")
    title = Column(String(500), nullable=False)
    description = Column(Text)
    data_type = Column(String(100))
    sdk_id = Column(BigInteger, ForeignKey("privacy_kb.component.id"))
    network_domain = Column(String(255))
    api_path = Column(String(500))
    remediation_advice = Column(Text)
    assigned_to = Column(BigInteger, ForeignKey("users.id"))
    assigned_at = Column(DateTime(timezone=True))
    due_date = Column(Date)
    closed_reason = Column(String(50))
    closed_by = Column(BigInteger, ForeignKey("users.id"))
    closed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    task = relationship("DetectionTask", back_populates="findings")
    remediations = relationship("Remediation", back_populates="finding", cascade="all, delete-orphan")
    __table_args__ = (
        Index("idx_findings_task", "task_id"),
        Index("idx_findings_severity", "severity"),
        Index("idx_findings_status", "status"),
    )


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    id = Column(BigInteger, primary_key=True)
    finding_id = Column(BigInteger, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False)
    evidence_id = Column(BigInteger, ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(50))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("finding_id", "evidence_id"),)


class FindingEvent(Base):
    __tablename__ = "finding_events"
    id = Column(BigInteger, primary_key=True)
    finding_id = Column(BigInteger, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False)
    event_id = Column(BigInteger, ForeignKey("detection_events.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("finding_id", "event_id"),)


# ============ SDK知识库(旧模型已迁移至 privacy_kb，见 app/models/kb.py) ============


# ============ 整改与复测 ============

class Remediation(Base):
    __tablename__ = "remediations"
    id = Column(BigInteger, primary_key=True)
    finding_id = Column(BigInteger, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False)
    remediation_type = Column(String(50))
    description = Column(Text)
    fix_version_id = Column(BigInteger, ForeignKey("app_versions.id"))
    attachments = Column(JSONB, default=list)
    submitted_by = Column(BigInteger, ForeignKey("users.id"))
    submitted_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    status = Column(String(30), default="pending_retest")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    finding = relationship("Finding", back_populates="remediations")


class RetestRecord(Base):
    __tablename__ = "retest_records"
    id = Column(BigInteger, primary_key=True)
    original_finding_id = Column(BigInteger, ForeignKey("findings.id"), nullable=False)
    retest_task_id = Column(BigInteger, ForeignKey("detection_tasks.id"))
    result = Column(String(30))
    notes = Column(Text)
    tested_by = Column(BigInteger, ForeignKey("users.id"))
    tested_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


# ============ 系统管理 ============

class AgentNode(Base):
    __tablename__ = "agent_nodes"
    id = Column(BigInteger, primary_key=True)
    node_uid = Column(String(50), unique=True, nullable=False)
    node_name = Column(String(200))
    node_type = Column(String(50), nullable=False)
    status = Column(String(30), default="offline")
    capabilities = Column(JSONB, default=list)
    tools_info = Column(JSONB, default=dict)
    last_heartbeat_at = Column(DateTime(timezone=True))
    config_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    devices = relationship("Device", back_populates="agent")


class Device(Base):
    __tablename__ = "devices"
    id = Column(BigInteger, primary_key=True)
    agent_id = Column(BigInteger, ForeignKey("agent_nodes.id"))
    serial = Column(String(100), unique=True, nullable=False)
    brand = Column(String(100))
    model = Column(String(100))
    android_version = Column(String(20))
    is_rooted = Column(Boolean, default=False)
    is_frida_ready = Column(Boolean, default=False)
    status = Column(String(30), default="idle")
    capabilities = Column(JSONB, default=dict)
    last_seen_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    agent = relationship("AgentNode", back_populates="devices")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(BigInteger, primary_key=True)
    actor_id = Column(BigInteger, ForeignKey("users.id"))
    actor_name = Column(String(100))
    action = Column(String(100), nullable=False)
    target_type = Column(String(50))
    target_id = Column(BigInteger)
    before_json = Column(JSONB)
    after_json = Column(JSONB)
    source_ip = Column(String(50))
    request_id = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        Index("idx_audit_actor", "actor_id"),
        Index("idx_audit_target", "target_type", "target_id"),
        Index("idx_audit_time", "created_at"),
    )


class SysDict(Base):
    __tablename__ = "sys_dict"
    id = Column(BigInteger, primary_key=True)
    dict_type = Column(String(100), nullable=False)
    dict_key = Column(String(100), nullable=False)
    dict_value = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0)
    status = Column(String(20), default="active")
    remark = Column(String(500))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("dict_type", "dict_key"),)


# ============ 引擎管理 ============

class EngineExecution(Base):
    """引擎执行记录 - 每次引擎运行产生一条"""
    __tablename__ = "engine_executions"
    id = Column(BigInteger, primary_key=True)
    task_id = Column(BigInteger, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False)
    sub_task_id = Column(BigInteger, ForeignKey("sub_tasks.id", ondelete="CASCADE"), nullable=False)
    engine_type = Column(String(50), nullable=False)  # androguard/appshark/mobsf/jadx/frida_agent/mitmproxy
    engine_name = Column(String(100), nullable=False)
    engine_version = Column(String(50))
    node_id = Column(BigInteger, ForeignKey("agent_nodes.id"))
    status = Column(String(30), nullable=False, default="pending")
    # queued/preparing/validating/running/collecting/normalizing/canceling/completed/failed/timed_out/canceled/skipped
    stage = Column(String(80))
    stage_message = Column(Text)
    progress = Column(Integer)
    config_json = Column(JSONB, default=dict)
    result_summary = Column(JSONB, default=dict)
    error_code = Column(String(60))
    error_message = Column(Text)
    debug_message = Column(Text)
    retryable = Column(Boolean, default=False)
    provider_status = Column(Integer)
    queued_at = Column(DateTime(timezone=True))
    stage_changed_at = Column(DateTime(timezone=True))
    heartbeat_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    worker_id = Column(String(120))
    lease_token = Column(String(120))
    lease_expires_at = Column(DateTime(timezone=True))
    state_version = Column(Integer, nullable=False, default=0)
    attempt_no = Column(Integer, nullable=False, default=1)
    parent_execution_id = Column(BigInteger, ForeignKey("engine_executions.id"))
    is_latest = Column(Boolean, nullable=False, default=True)
    execution_fingerprint = Column(String(64))
    cache_scope = Column(String(200))
    cancel_requested = Column(Boolean, nullable=False, default=False)
    provider_scan_id = Column(String(200))
    provider_scan_hash = Column(String(200))
    raw_result_hash = Column(String(64))
    raw_result_size = Column(BigInteger)
    parser_version = Column(String(50))
    parser_status = Column(String(30))
    parser_error = Column(Text)
    normalized_at = Column(DateTime(timezone=True))
    normalized_event_count = Column(Integer, default=0)
    normalized_finding_count = Column(Integer, default=0)
    # {events_count, artifacts_count, findings_count, duration_seconds}
    event_count = Column(Integer, default=0)
    artifact_count = Column(Integer, default=0)
    log_path = Column(String(500))
    raw_output_path = Column(String(500))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))  # compatibility alias of finished_at
    duration_ms = Column(Integer)  # 执行耗时(毫秒)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        Index("idx_engine_exec_task", "task_id"),
        Index("idx_engine_exec_engine", "engine_type"),
        Index("idx_engine_exec_status", "status"),
    )


class EngineArtifact(Base):
    """引擎原始输出或日志制品。"""
    __tablename__ = "engine_artifacts"
    id = Column(BigInteger, primary_key=True)
    execution_id = Column(BigInteger, ForeignKey("engine_executions.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String(60), nullable=False)
    artifact_uri = Column(String(1000), nullable=False)
    sha256 = Column(String(64), nullable=False)
    size = Column(BigInteger, nullable=False, default=0)
    content_type = Column(String(200))
    storage_backend = Column(String(40), nullable=False, default="local")
    schema_version = Column(String(30))
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (Index("idx_engine_artifact_execution", "execution_id"),)


class EngineObservation(Base):
    """从引擎原始结果解析出的客观观察。"""
    __tablename__ = "engine_observations"
    id = Column(BigInteger, primary_key=True)
    task_id = Column(BigInteger, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False)
    execution_id = Column(BigInteger, ForeignKey("engine_executions.id", ondelete="CASCADE"), nullable=False)
    engine_type = Column(String(50), nullable=False)
    observation_type = Column(String(80), nullable=False)
    category = Column(String(80))
    rule_code = Column(String(120))
    rule_version = Column(String(30))
    severity = Column(String(30))
    confidence = Column(String(30))
    evidence_level = Column(String(30), nullable=False, default="observed")
    subject = Column(String(500))
    location = Column(String(500))
    fingerprint = Column(String(64))
    evidence_refs = Column(JSONB, default=list)
    payload = Column(JSONB, default=dict)
    schema_version = Column(String(30), nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (Index("idx_engine_observation_task", "task_id"), Index("idx_engine_observation_execution", "execution_id"))


class FindingObservationRelation(Base):
    __tablename__ = "finding_observation_relations"
    finding_id = Column(BigInteger, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)
    observation_id = Column(BigInteger, ForeignKey("engine_observations.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
class PlatformFinding(Base):
    """平台规则层生成的统一风险结论。"""
    __tablename__ = "platform_findings"
    id = Column(BigInteger, primary_key=True)
    task_id = Column(BigInteger, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False)
    finding_code = Column(String(120), nullable=False)
    title = Column(String(300), nullable=False)
    category = Column(String(80), nullable=False)
    subcategory = Column(String(80))
    severity = Column(String(30), nullable=False, default="medium")
    confidence = Column(String(30), nullable=False, default="medium")
    triage_status = Column(String(30), nullable=False, default="needs_review")
    baseline_state = Column(String(30), nullable=False, default="new")
    description = Column(Text)
    impact = Column(Text)
    recommendation = Column(Text)
    masvs_controls = Column(JSONB, default=list)
    maswe_ids = Column(JSONB, default=list)
    mastg_test_ids = Column(JSONB, default=list)
    cwe_ids = Column(JSONB, default=list)
    correlation_rule_id = Column(String(120))
    correlation_rule_version = Column(String(30))
    dedup_key = Column(String(200), nullable=False)
    observation_count = Column(Integer, default=0)
    schema_version = Column(String(30), nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("idx_platform_finding_task", "task_id"), Index("idx_platform_finding_dedup", "task_id", "dedup_key"))


class FindingObservation(Base):
    __tablename__ = "finding_observations"
    finding_id = Column(BigInteger, ForeignKey("platform_findings.id", ondelete="CASCADE"), primary_key=True)
    observation_id = Column(BigInteger, ForeignKey("engine_observations.id", ondelete="CASCADE"), primary_key=True)
    relation_type = Column(String(40), nullable=False, default="evidence")
    weight = Column(Float, default=1.0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class EngineConfig(Base):
    """全局检测引擎配置，敏感字段独立加密保存。"""
    __tablename__ = "engine_configs"
    id = Column(BigInteger, primary_key=True)
    engine_type = Column(String(50), nullable=False, unique=True)
    config_json = Column(JSONB, nullable=False, default=dict)
    secret_json = Column(JSONB, nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True)
    last_health_status = Column(String(30))
    last_health_message = Column(Text)
    last_checked_at = Column(DateTime(timezone=True))
    updated_by = Column(BigInteger, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("idx_engine_config_health", "last_health_status"),)


# 注册 privacy_kb / privacy_scan 模型（供 create_all 与查询使用）
from app.models import kb  # noqa: F401,E402
