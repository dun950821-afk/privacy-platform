"""Pydantic Schemas"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime, date


# ============ Auth ============

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: "UserInfo"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    full_name: Optional[str] = None
    email: Optional[str] = None


# ============ Project ============

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectMemberAdd(BaseModel):
    user_id: int
    role: str = "tester"


# ============ App ============

class AppCreate(BaseModel):
    project_id: int
    package_name: str
    app_name: str
    app_type: str = "android"
    category: Optional[str] = None
    department: Optional[str] = None
    vendor: Optional[str] = None
    description: Optional[str] = None


class AppUpdate(BaseModel):
    app_name: Optional[str] = None
    category: Optional[str] = None
    department: Optional[str] = None
    vendor: Optional[str] = None
    description: Optional[str] = None


class VersionUploadInfo(BaseModel):
    version_name: str
    version_code: int
    channel: Optional[str] = None
    upload_notes: Optional[str] = None


class PrivacyPolicyCreate(BaseModel):
    app_id: int
    version: Optional[str] = None
    effective_date: Optional[date] = None
    raw_text: Optional[str] = None


# ============ Task ============

class TaskCreate(BaseModel):
    app_version_id: int
    detection_type: str = "full"
    rule_pack_version: str = "1.0"
    config: dict = Field(default_factory=dict)
    privacy_policy_id: Optional[int] = None


class TaskConfig(BaseModel):
    dynamic_scenarios: list[str] = Field(default_factory=lambda: ["first_launch", "rejected", "consented"])
    device_requirements: dict = Field(default_factory=dict)
    timeout_minutes: int = 30
    retry_policy: dict = Field(default_factory=dict)


class ScenarioUpdate(BaseModel):
    status: Optional[str] = None
    consent_status: Optional[str] = None
    notes: Optional[str] = None
    operator_id: Optional[int] = None


# ============ Finding ============

class FindingAssign(BaseModel):
    assigned_to: int
    due_date: Optional[date] = None


class FindingClose(BaseModel):
    closed_reason: str
    notes: Optional[str] = None


class RemediationCreate(BaseModel):
    remediation_type: str
    description: str
    fix_version_id: Optional[int] = None


# ============ Rule ============

class RuleCreate(BaseModel):
    rule_key: str
    name: str
    category: str
    description: Optional[str] = None


class RuleVersionCreate(BaseModel):
    rule_id: int
    version: str
    rule_content: dict
    changelog: Optional[str] = None


# ============ SDK ============

class SDKCreate(BaseModel):
    name: str
    vendor: Optional[str] = None
    category: Optional[str] = None
    official_url: Optional[str] = None
    privacy_policy_url: Optional[str] = None
    description: Optional[str] = None
    privacy_behaviors: list[dict] = Field(default_factory=list)
    config_capabilities: dict = Field(default_factory=dict)


class SDKFingerprintCreate(BaseModel):
    fingerprint_type: str
    fingerprint_value: str
    weight: float = 1.0
    version_range: Optional[str] = None


# ============ Agent ============

class AgentRegister(BaseModel):
    agent_id: Optional[str] = None
    node_name: str
    node_type: str = "dynamic_agent"
    version: str = "1.0.0"
    capabilities: list[str] = Field(default_factory=list)
    tools_info: dict = Field(default_factory=dict)
    devices: list[dict] = Field(default_factory=list)


class AgentHeartbeat(BaseModel):
    agent_id: str
    timestamp: datetime
    status: str = "idle"
    current_task_id: Optional[int] = None
    devices: list[dict] = Field(default_factory=list)
    resources: dict = Field(default_factory=dict)


class AgentProgress(BaseModel):
    agent_id: str
    sub_task_id: int
    stage: str
    percent: int
    message: Optional[str] = None
    scenario_id: Optional[int] = None
    timestamp: datetime


class AgentEvent(BaseModel):
    event_uid: str
    scenario_id: Optional[int] = None
    event_type: str
    timestamp: datetime
    consent_status: Optional[str] = None
    data_type: Optional[str] = None
    api: Optional[str] = None
    caller: Optional[str] = None
    trace_id: Optional[str] = None
    value_fingerprint: Optional[str] = None
    event_data: dict = Field(default_factory=dict)
    engine_name: Optional[str] = None
    engine_version: Optional[str] = None


class AgentEventBatch(BaseModel):
    agent_id: str
    events: list[AgentEvent]


class AgentResult(BaseModel):
    agent_id: str
    task_id: int
    status: str
    summary: dict = Field(default_factory=dict)
    error_message: Optional[str] = None


# ============ System ============

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str = "viewer"


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None


class DictCreate(BaseModel):
    dict_type: str
    dict_key: str
    dict_value: str
    sort_order: int = 0
    remark: Optional[str] = None


# Update forward refs
TokenResponse.model_rebuild()
