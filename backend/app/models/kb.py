"""隐私知识库(privacy_kb)与扫描结果(privacy_scan)数据模型

对应 app_privacy_kb_schema_postgresql.sql 建表结构：
- privacy_kb: SDK/开源库/框架等统一组件知识库、指纹、权限、个人信息能力、识别规则
- privacy_scan: 每次APK检测产生的扫描运行数据
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String, Text, Boolean,
    DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ============ privacy_kb 知识库 ============

class KBImportBatch(Base):
    """知识库导入批次"""
    __tablename__ = "import_batch"
    __table_args__ = {"schema": "privacy_kb"}

    id = Column(BigInteger, primary_key=True)
    source_file = Column(Text, nullable=False)
    source_sha256 = Column(String(64))
    import_mode = Column(String(20), nullable=False, default="UPSERT")
    status = Column(String(20), nullable=False, default="RUNNING")
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = Column(DateTime(timezone=True))
    statistics = Column(JSONB, nullable=False, default=dict)
    error_message = Column(Text)
    created_by = Column(String(100))


class KBVendor(Base):
    """厂商"""
    __tablename__ = "vendor"
    __table_args__ = {"schema": "privacy_kb"}

    id = Column(BigInteger, primary_key=True)
    vendor_key = Column(String(160), unique=True, nullable=False)
    name = Column(String(300), nullable=False)
    normalized_name = Column(String(300), nullable=False)
    official_website = Column(Text)
    country_or_region = Column(String(100))
    verification_status = Column(String(30), nullable=False, default="UNVERIFIED")
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    components = relationship("KBComponent", back_populates="vendor")


class KBSource(Base):
    """数据来源"""
    __tablename__ = "source"
    __table_args__ = {"schema": "privacy_kb"}

    id = Column(BigInteger, primary_key=True)
    source_key = Column(String(180), unique=True, nullable=False)
    name = Column(String(500), nullable=False)
    source_type = Column(String(80))
    coverage = Column(Text)
    url = Column(Text)
    kb_usage = Column(Text)
    trust_level = Column(String(20))
    maintenance_advice = Column(Text)
    source_version = Column(String(100))
    published_at = Column(DateTime(timezone=True))
    fetched_at = Column(DateTime(timezone=True))
    snapshot_sha256 = Column(String(64))
    is_active = Column(Boolean, nullable=False, default=True)
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class KBComponent(Base):
    """统一软件组件: SDK/开源库/框架/系统组件/厂商组件/应用模块"""
    __tablename__ = "component"
    __table_args__ = {"schema": "privacy_kb"}

    id = Column(BigInteger, primary_key=True)
    component_key = Column(String(180), unique=True, nullable=False)
    name = Column(String(500), nullable=False)
    normalized_name = Column(String(500), nullable=False)
    english_name = Column(String(500))
    vendor_id = Column(BigInteger, ForeignKey("privacy_kb.vendor.id"))
    component_kind = Column(String(50), nullable=False, default="UNKNOWN")
    category_l1 = Column(String(150))
    category_l2 = Column(String(150))
    primary_purpose = Column(Text)
    description = Column(Text)
    attributes = Column(Text)
    license_name = Column(String(200))
    sensitivity_level = Column(String(20))
    confidence_level = Column(String(20))
    verification_status = Column(String(40), nullable=False, default="PENDING")
    source_type = Column(String(200))
    recommended_match_rule = Column(Text)
    obfuscation_handling = Column(Text)
    false_positive_note = Column(Text)
    compliance_note = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    record_version = Column(Integer, nullable=False, default=1)
    first_seen_at = Column(DateTime(timezone=True))
    last_verified_at = Column(DateTime(timezone=True))
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    vendor = relationship("KBVendor", back_populates="components")
    aliases = relationship("KBComponentAlias", back_populates="component",
                           cascade="all, delete-orphan")
    fingerprints = relationship("KBComponentFingerprint", back_populates="component",
                                cascade="all, delete-orphan")
    data_claims = relationship("KBComponentDataClaim", back_populates="component",
                               cascade="all, delete-orphan")
    permission_links = relationship("KBComponentPermission", back_populates="component",
                                    cascade="all, delete-orphan")


class KBComponentAlias(Base):
    """组件别名"""
    __tablename__ = "component_alias"
    __table_args__ = (
        UniqueConstraint("component_id", "normalized_alias"),
        {"schema": "privacy_kb"},
    )

    id = Column(BigInteger, primary_key=True)
    component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id", ondelete="CASCADE"), nullable=False)
    alias_name = Column(String(500), nullable=False)
    normalized_alias = Column(String(500), nullable=False)
    alias_type = Column(String(30), nullable=False, default="OTHER")
    language_code = Column(String(20))
    source_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    component = relationship("KBComponent", back_populates="aliases")


class KBComponentFingerprint(Base):
    """组件识别指纹: 包名前缀/类名/Manifest组件/Maven坐标/SO/权限/API/域名等"""
    __tablename__ = "component_fingerprint"
    __table_args__ = (
        UniqueConstraint("component_id", "fingerprint_type", "normalized_value", "match_mode"),
        {"schema": "privacy_kb"},
    )

    id = Column(BigInteger, primary_key=True)
    component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id", ondelete="CASCADE"), nullable=False)
    fingerprint_type = Column(String(50), nullable=False)
    value = Column(Text, nullable=False)
    normalized_value = Column(Text, nullable=False)
    match_mode = Column(String(20), nullable=False, default="EXACT")
    manifest_component_type = Column(String(20))
    evidence_role = Column(String(20), nullable=False, default="SUPPORTING")
    weight = Column(SmallInteger, nullable=False, default=10)
    confidence_level = Column(String(20))
    is_negative = Column(Boolean, nullable=False, default=False)
    is_stable = Column(Boolean)
    version_from = Column(String(100))
    version_to = Column(String(100))
    source_id = Column(BigInteger, ForeignKey("privacy_kb.source.id"))
    source_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    component = relationship("KBComponent", back_populates="fingerprints")


class KBComponentRelation(Base):
    """组件间关系: 依赖/捆绑/推送通道/替代等"""
    __tablename__ = "component_relation"
    __table_args__ = (
        UniqueConstraint("parent_component_id", "child_component_id", "relation_type"),
        {"schema": "privacy_kb"},
    )

    id = Column(BigInteger, primary_key=True)
    parent_component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id", ondelete="CASCADE"), nullable=False)
    child_component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(30), nullable=False)
    description = Column(Text)
    source_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class KBPermission(Base):
    """权限知识库"""
    __tablename__ = "permission"
    # 索引必须在这里也声明一份：迁移建了 `idx_permission_platform`（数据库里有），
    # 模型不写就会 model/DB 漂移——autogenerate 会想把它删掉，而权限页按平台筛选
    # 正是走这个索引。
    __table_args__ = (
        Index("idx_permission_platform", "platform"),
        {"schema": "privacy_kb"},
    )

    id = Column(BigInteger, primary_key=True)
    permission_name = Column(String(500), unique=True, nullable=False)
    platform = Column(String(20), nullable=False, default="ANDROID", server_default="ANDROID")
    normalized_name = Column(String(500), nullable=False)
    category = Column(String(150))
    capability = Column(Text)
    permission_type = Column(String(100))
    risk_level = Column(String(20))
    grant_mode = Column(Text)
    compliance_focus = Column(Text)
    official_reference = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class KBComponentPermission(Base):
    """组件-权限关系"""
    __tablename__ = "component_permission"
    __table_args__ = {"schema": "privacy_kb"}

    component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id", ondelete="CASCADE"), primary_key=True)
    permission_id = Column(BigInteger, ForeignKey("privacy_kb.permission.id", ondelete="CASCADE"), primary_key=True)
    relation_type = Column(String(20), nullable=False, default="TYPICAL", primary_key=True)
    evidence_weight = Column(SmallInteger, nullable=False, default=5)
    notes = Column(Text)
    source_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    component = relationship("KBComponent", back_populates="permission_links")
    permission = relationship("KBPermission")


class KBDataItem(Base):
    """移动端个人信息/系统能力项"""
    __tablename__ = "data_item"
    __table_args__ = {"schema": "privacy_kb"}

    id = Column(BigInteger, primary_key=True)
    data_key = Column(String(180), unique=True, nullable=False)
    category_l1 = Column(String(150), nullable=False)
    category_l2 = Column(String(200))
    item_name = Column(String(300), nullable=False)
    typical_fields = Column(Text)
    possible_data = Column(Text)
    personal_info_type = Column(Text)
    sensitivity_level = Column(String(20))
    compliance_focus = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class KBDataDetectionPattern(Base):
    """个人信息检测模式"""
    __tablename__ = "data_detection_pattern"
    __table_args__ = (
        UniqueConstraint("data_item_id", "pattern_type", "normalized_value", "detection_stage"),
        {"schema": "privacy_kb"},
    )

    id = Column(BigInteger, primary_key=True)
    data_item_id = Column(BigInteger, ForeignKey("privacy_kb.data_item.id", ondelete="CASCADE"), nullable=False)
    pattern_type = Column(String(30), nullable=False)
    value = Column(Text, nullable=False)
    normalized_value = Column(Text, nullable=False)
    match_mode = Column(String(20), nullable=False, default="CONTAINS")
    detection_stage = Column(String(20), nullable=False, default="BOTH")
    weight = Column(SmallInteger, nullable=False, default=10)
    notes = Column(Text)
    source_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class KBComponentDataClaim(Base):
    """组件可能处理的个人信息声明"""
    __tablename__ = "component_data_claim"
    __table_args__ = (
        UniqueConstraint("component_id", "claim_key"),
        {"schema": "privacy_kb"},
    )

    id = Column(BigInteger, primary_key=True)
    component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id", ondelete="CASCADE"), nullable=False)
    claim_key = Column(String(180), nullable=False)
    data_item_id = Column(BigInteger, ForeignKey("privacy_kb.data_item.id"))
    data_description = Column(Text)
    personal_info_category = Column(Text)
    sensitivity_level = Column(String(20))
    collection_mode = Column(String(30), nullable=False, default="POSSIBLE")
    purpose = Column(Text)
    compliance_note = Column(Text)
    source_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    component = relationship("KBComponent", back_populates="data_claims")
    data_item = relationship("KBDataItem")


class KBComponentSource(Base):
    """组件-数据来源关系"""
    __tablename__ = "component_source"
    __table_args__ = {"schema": "privacy_kb"}

    component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id", ondelete="CASCADE"), primary_key=True)
    source_id = Column(BigInteger, ForeignKey("privacy_kb.source.id", ondelete="CASCADE"), primary_key=True)
    source_role = Column(String(30), nullable=False, default="REFERENCE", primary_key=True)
    evidence_note = Column(Text)
    source_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class KBRecognitionRule(Base):
    """识别评分规则"""
    __tablename__ = "recognition_rule"
    __table_args__ = {"schema": "privacy_kb"}

    id = Column(BigInteger, primary_key=True)
    rule_key = Column(String(180), unique=True, nullable=False)
    rule_level = Column(String(100))
    evidence_type = Column(String(100), nullable=False)
    suggested_score = Column(Integer, nullable=False, default=0)
    detection_content = Column(Text)
    applicable_object = Column(Text)
    decision_advice = Column(Text)
    obfuscation_support = Column(Text)
    false_positive_ctrl = Column(Text)
    engine_min_version = Column(String(50))
    rule_version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    source_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class KBMaintenancePolicy(Base):
    """知识库维护策略"""
    __tablename__ = "maintenance_policy"
    __table_args__ = {"schema": "privacy_kb"}

    id = Column(BigInteger, primary_key=True)
    policy_key = Column(String(180), unique=True, nullable=False)
    maintenance_object = Column(String(200), nullable=False)
    unique_key_advice = Column(Text)
    required_version_fields = Column(Text)
    update_trigger = Column(Text)
    quality_control = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    source_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


# ============ privacy_scan 扫描运行数据 ============

class ScanApp(Base):
    """被检测App"""
    __tablename__ = "app"
    __table_args__ = {"schema": "privacy_scan"}

    id = Column(BigInteger, primary_key=True)
    package_name = Column(String(500), unique=True, nullable=False)
    app_name = Column(String(500))
    platform = Column(String(20), nullable=False, default="ANDROID")
    owner_org = Column(String(300))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    builds = relationship("ScanAppBuild", back_populates="app", cascade="all, delete-orphan")


class ScanAppBuild(Base):
    """App版本构建（每个检测任务一条，build_key=task:{id} 唯一；
    不按 (app_id, version_code, sha256) 去重——同一版本可能被多个任务检测）"""
    __tablename__ = "app_build"
    __table_args__ = {"schema": "privacy_scan"}

    id = Column(BigInteger, primary_key=True)
    build_key = Column(String(180), unique=True, nullable=False)
    app_id = Column(BigInteger, ForeignKey("privacy_scan.app.id", ondelete="CASCADE"), nullable=False)
    version_name = Column(String(100))
    version_code = Column(String(100))
    min_sdk = Column(Integer)
    target_sdk = Column(Integer)
    max_sdk = Column(Integer)
    file_size = Column(BigInteger)
    sha256 = Column(String(64))
    source_file = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    app = relationship("ScanApp", back_populates="builds")
    scan_jobs = relationship("ScanJob", back_populates="app_build", cascade="all, delete-orphan")


class ScanJob(Base):
    """扫描任务"""
    __tablename__ = "scan_job"
    __table_args__ = {"schema": "privacy_scan"}

    id = Column(BigInteger, primary_key=True)
    app_build_id = Column(BigInteger, ForeignKey("privacy_scan.app_build.id", ondelete="CASCADE"), nullable=False)
    scan_type = Column(String(30), nullable=False, default="STATIC")
    engine_version = Column(String(100))
    rule_version = Column(String(100))
    status = Column(String(20), nullable=False, default="RUNNING")
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = Column(DateTime(timezone=True))
    summary = Column(JSONB, nullable=False, default=dict)
    import_batch_id = Column(BigInteger, ForeignKey("privacy_kb.import_batch.id"))
    error_message = Column(Text)

    app_build = relationship("ScanAppBuild", back_populates="scan_jobs")
    component_hits = relationship("ScanComponentHit", back_populates="scan_job",
                                  cascade="all, delete-orphan")


class ScanManifestComponent(Base):
    """扫描到的Manifest组件"""
    __tablename__ = "manifest_component"
    __table_args__ = (
        UniqueConstraint("scan_job_id", "component_type", "class_name"),
        {"schema": "privacy_scan"},
    )

    id = Column(BigInteger, primary_key=True)
    scan_job_id = Column(BigInteger, ForeignKey("privacy_scan.scan_job.id", ondelete="CASCADE"), nullable=False)
    component_type = Column(String(20), nullable=False)
    class_name = Column(Text, nullable=False)
    package_name = Column(Text)
    exported = Column(Boolean)
    enabled = Column(Boolean)
    declared_permission = Column(Text)
    matched_component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id"))
    match_confidence = Column(String(20))
    risk_level = Column(String(20))
    purpose = Column(Text)
    data_description = Column(Text)
    personal_info_category = Column(Text)
    review_focus = Column(Text)
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class ScanDeclaredPermission(Base):
    """扫描到的声明权限"""
    __tablename__ = "declared_permission"
    __table_args__ = (
        UniqueConstraint("scan_job_id", "permission_name"),
        {"schema": "privacy_scan"},
    )

    id = Column(BigInteger, primary_key=True)
    scan_job_id = Column(BigInteger, ForeignKey("privacy_scan.scan_job.id", ondelete="CASCADE"), nullable=False)
    permission_name = Column(String(500), nullable=False)
    permission_id = Column(BigInteger, ForeignKey("privacy_kb.permission.id"))
    is_dangerous = Column(Boolean)
    risk_level = Column(String(20))
    compliance_focus = Column(Text)
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class ScanPackageCluster(Base):
    """包簇识别结果"""
    __tablename__ = "package_cluster"
    __table_args__ = (
        UniqueConstraint("scan_job_id", "package_prefix"),
        {"schema": "privacy_scan"},
    )

    id = Column(BigInteger, primary_key=True)
    scan_job_id = Column(BigInteger, ForeignKey("privacy_scan.scan_job.id", ondelete="CASCADE"), nullable=False)
    package_prefix = Column(Text, nullable=False)
    identified_name = Column(Text)
    component_kind = Column(String(50))
    vendor_name = Column(Text)
    category = Column(Text)
    primary_purpose = Column(Text)
    component_count = Column(Integer)
    component_type_stat = Column(JSONB, nullable=False, default=dict)
    matched_component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id"))
    risk_level = Column(String(20))
    confidence_level = Column(String(20))
    evidence_basis = Column(Text)
    review_focus = Column(Text)
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class ScanComponentHit(Base):
    """SDK/组件命中结果"""
    __tablename__ = "component_hit"
    __table_args__ = (
        UniqueConstraint("scan_job_id", "component_id"),
        {"schema": "privacy_scan"},
    )

    id = Column(BigInteger, primary_key=True)
    scan_job_id = Column(BigInteger, ForeignKey("privacy_scan.scan_job.id", ondelete="CASCADE"), nullable=False)
    component_id = Column(BigInteger, ForeignKey("privacy_kb.component.id"), nullable=False)
    total_score = Column(Integer, nullable=False, default=0)
    confidence_level = Column(String(20))
    detected_version = Column(String(100))
    hit_status = Column(String(20), nullable=False, default="CANDIDATE")
    primary_package = Column(Text)
    evidence_count = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    scan_job = relationship("ScanJob", back_populates="component_hits")
    component = relationship("KBComponent")
    evidence = relationship("ScanHitEvidence", back_populates="component_hit",
                            cascade="all, delete-orphan")


class ScanHitEvidence(Base):
    """命中原始证据"""
    __tablename__ = "hit_evidence"
    __table_args__ = (
        UniqueConstraint("component_hit_id", "evidence_type", "evidence_value", "evidence_location"),
        {"schema": "privacy_scan"},
    )

    id = Column(BigInteger, primary_key=True)
    component_hit_id = Column(BigInteger, ForeignKey("privacy_scan.component_hit.id", ondelete="CASCADE"), nullable=False)
    fingerprint_id = Column(BigInteger, ForeignKey("privacy_kb.component_fingerprint.id"))
    event_id = Column(BigInteger, ForeignKey("detection_events.id", ondelete="SET NULL"))
    evidence_type = Column(String(50), nullable=False)
    evidence_value = Column(Text, nullable=False)
    evidence_location = Column(Text)
    score = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    component_hit = relationship("ScanComponentHit", back_populates="evidence")


class ScanDataFinding(Base):
    """个人信息访问/隐私政策差异结果"""
    __tablename__ = "data_finding"
    __table_args__ = {"schema": "privacy_scan"}

    id = Column(BigInteger, primary_key=True)
    scan_job_id = Column(BigInteger, ForeignKey("privacy_scan.scan_job.id", ondelete="CASCADE"), nullable=False)
    data_item_id = Column(BigInteger, ForeignKey("privacy_kb.data_item.id"))
    component_hit_id = Column(BigInteger, ForeignKey("privacy_scan.component_hit.id"))
    finding_type = Column(String(30), nullable=False)
    risk_level = Column(String(20))
    confidence_level = Column(String(20))
    purpose = Column(Text)
    evidence = Column(Text)
    policy_disclosure_status = Column(String(30))
    remediation = Column(Text)
    raw_data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
