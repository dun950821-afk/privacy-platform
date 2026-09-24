# Correlation 规则体系与规则管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把硬编码的关联规则改造成可持久化、可版本化、可在界面查看与维护的规则体系，并保证历史结论可复现。

**Architecture:** 复用现有 `rules` / `rule_versions` 表，`category="correlation"` 区分关联规则，`rule_content` 存放结构化规则 JSON。新增受控条件求值器负责校验与匹配，`correlation` 与 `finding_service` 改为读取数据库中的启用规则。发布采用「保存即新版本、新版本默认不启用」，Finding 记录 `finding_uid` 与 `rule_snapshot` 以支持历史复现。

**Tech Stack:** FastAPI、SQLAlchemy/PostgreSQL、Alembic、Pydantic、pytest、Vue 3、Element Plus、Vite。

**Spec:** `docs/superpowers/specs/2026-09-24-correlation-rules-design.md`

## Global Constraints

- 条件能力限定为 `logic ∈ {all, any}`、`operator ∈ {equals, contains, exists}`、`field ∈ {subject, location, payload.<路径>}`。
- `exists` 操作符不使用 `value` 字段；`payload.<路径>` 路径不存在视为不匹配。
- 复用 `rules` / `rule_versions`，不新建规则表；`rules.category = "correlation"`。
- 保存规则产生草稿版本；新版本默认不启用，必须显式发布才生效。
- 停用规则不删除历史 Finding。
- 标准映射内联在规则内容中，删除 `finding_baseline.py` 的硬编码映射字典。
- `finding_uid` 由 `finding_code` 与 `dedup_key` 派生，同一逻辑结论重复计算保持稳定。
- 预览接口不得写入数据库。
- 迁移必须检查列是否已存在，保持可重复执行。
- 本期不做嵌套条件、引用式关联、灰度发布、隔离测试队列、AI 判定。

---

## 文件地图

- Create `backend/app/services/rule_evaluator.py`: 规则校验与条件求值。
- Create `backend/app/services/rule_seed.py`: 内置关联规则种子。
- Create `backend/app/api/v1/correlation_rules.py`: 关联规则 CRUD / 发布 / 停用 / 预览。
- Modify `backend/app/services/correlation.py`: 改为读取数据库规则。
- Modify `backend/app/services/finding_service.py`: 写入 `finding_uid` 与 `rule_snapshot`。
- Modify `backend/app/services/finding_baseline.py`: 删除硬编码映射。
- Modify `backend/app/models/__init__.py`: `PlatformFinding` 增加两个字段。
- Modify `backend/app/api/v1/__init__.py`: 注册新路由。
- Modify `backend/app/schemas/__init__.py`: 关联规则请求模型。
- Create `backend/alembic/versions/20260924_finding_reproducibility.py`: 新增列。
- Create `backend/tests/test_rule_evaluator.py`, `backend/tests/test_correlation_rules_api.py`, `backend/tests/test_finding_reproducibility.py`。
- Create `backend/tests/fixtures/correlation/*/positive.json` 与 `negative.json`。
- Create `frontend/src/views/CorrelationRules.vue`、`frontend/src/api/correlationRules.ts`。
- Modify `frontend/src/router/index.ts`。

---

### Task 1: 规则校验器与条件求值器

**Files:**
- Create: `backend/app/services/rule_evaluator.py`
- Test: `backend/tests/test_rule_evaluator.py`

**Interfaces:**
- `validate_rule_content(content: dict) -> None` 校验失败抛 `RuleValidationError`。
- `evaluate_rule(content: dict, observations: list[dict]) -> list[dict] | None` 命中返回 Observation 列表，未命中返回 `None`。
- `class RuleValidationError(ValueError)`。

- [ ] **Step 1: 写失败测试**

```python
import pytest
from app.services.rule_evaluator import RuleValidationError, evaluate_rule, validate_rule_content

VALID = {
    "schema_version": "1.0",
    "match": {"logic": "all", "conditions": [
        {"observation_type": "fact.permission", "field": "subject", "operator": "contains",
         "value": "android.permission.READ_CONTACTS"},
        {"observation_type": "dataflow.privacy", "field": "payload.sink.category",
         "operator": "equals", "value": "network"},
    ]},
    "produce": {"finding_code": "PRIVACY_CONTACTS_NETWORK", "title": "通讯录外传",
                "category": "privacy", "severity": "high", "confidence": "medium",
                "recommendation": "确认授权与披露。"},
    "standards": {"masvs": ["MASVS-PRIVACY-1"], "maswe": ["MASWE-0001"],
                  "mastg": ["MASTG-TEST-PRIVACY-1"], "cwe": []},
}


def test_valid_content_passes():
    validate_rule_content(VALID)


def test_rejects_unknown_operator():
    bad = {**VALID, "match": {"logic": "all", "conditions": [
        {"observation_type": "fact.permission", "field": "subject", "operator": "regex", "value": "x"}]}}
    with pytest.raises(RuleValidationError):
        validate_rule_content(bad)


def test_rejects_malformed_maswe_id():
    bad = {**VALID, "standards": {**VALID["standards"], "maswe": ["MASWE-1"]}}
    with pytest.raises(RuleValidationError):
        validate_rule_content(bad)


def test_all_logic_requires_every_condition():
    observations = [
        {"id": 1, "observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}},
    ]
    assert evaluate_rule(VALID, observations) is None


def test_all_logic_matches_when_every_condition_met():
    observations = [
        {"id": 1, "observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}},
        {"id": 2, "observation_type": "dataflow.privacy", "subject": "Contacts",
         "payload": {"sink": {"category": "network"}}},
    ]
    matched = evaluate_rule(VALID, observations)
    assert sorted(o["id"] for o in matched) == [1, 2]


def test_any_logic_matches_with_single_condition():
    content = {**VALID, "match": {"logic": "any", "conditions": [VALID["match"]["conditions"][0]]}}
    observations = [{"id": 1, "observation_type": "fact.permission",
                     "subject": "android.permission.READ_CONTACTS", "payload": {}}]
    assert [o["id"] for o in evaluate_rule(content, observations)] == [1]


def test_missing_payload_path_does_not_match():
    observations = [{"id": 1, "observation_type": "dataflow.privacy", "subject": "x", "payload": {}}]
    content = {**VALID, "match": {"logic": "all", "conditions": [VALID["match"]["conditions"][1]]}}
    assert evaluate_rule(content, observations) is None


def test_exists_operator_needs_no_value():
    content = {**VALID, "match": {"logic": "all", "conditions": [
        {"observation_type": "fact.permission", "field": "subject", "operator": "exists"}]}}
    observations = [{"id": 1, "observation_type": "fact.permission", "subject": "android.permission.CAMERA", "payload": {}}]
    assert [o["id"] for o in evaluate_rule(content, observations)] == [1]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_rule_evaluator.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.rule_evaluator'`

- [ ] **Step 3: 实现求值器**

```python
"""关联规则的受控校验与条件求值。"""
import re

ALLOWED_LOGIC = {"all", "any"}
ALLOWED_OPERATORS = {"equals", "contains", "exists"}
ALLOWED_FIELDS = {"subject", "location"}
MASVS_RE = re.compile(r"^MASVS-[A-Z]+-\d+$")
MASWE_RE = re.compile(r"^MASWE-\d{4}$")
MASTG_RE = re.compile(r"^MASTG-[A-Z]+-[A-Z0-9-]+$")
FINDING_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


class RuleValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuleValidationError(message)


def _is_payload_field(field: str) -> bool:
    return field.startswith("payload.") and len(field) > len("payload.")


def _resolve_field(observation: dict, field: str):
    if _is_payload_field(field):
        value = observation.get("payload") or {}
        for part in field[len("payload."):].split("."):
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return value
    return observation.get(field)


def validate_rule_content(content: dict) -> None:
    _require(isinstance(content, dict), "规则内容必须是对象")
    _require(content.get("schema_version") == "1.0", "不支持的 schema_version")
    match = content.get("match") or {}
    _require(match.get("logic") in ALLOWED_LOGIC, "logic 只能是 all 或 any")
    conditions = match.get("conditions") or []
    _require(len(conditions) > 0, "至少需要一个匹配条件")
    for condition in conditions:
        operator = condition.get("operator")
        _require(operator in ALLOWED_OPERATORS, f"不支持的操作符: {operator}")
        field = condition.get("field")
        _require(field in ALLOWED_FIELDS or _is_payload_field(field), f"不支持的字段: {field}")
        _require(bool(condition.get("observation_type")), "条件缺少 observation_type")
        if operator != "exists":
            _require(condition.get("value") not in (None, ""), "该操作符需要 value")
    produce = content.get("produce") or {}
    _require(bool(FINDING_CODE_RE.match(str(produce.get("finding_code") or ""))), "finding_code 格式错误")
    _require(bool(produce.get("title")), "produce.title 不能为空")
    _require(bool(produce.get("category")), "produce.category 不能为空")
    standards = content.get("standards") or {}
    for value in standards.get("masvs") or []:
        _require(bool(MASVS_RE.match(value)), f"MASVS 标识格式错误: {value}")
    for value in standards.get("maswe") or []:
        _require(bool(MASWE_RE.match(value)), f"MASWE 标识格式错误: {value}")
    for value in standards.get("mastg") or []:
        _require(bool(MASTG_RE.match(value)), f"MASTG 标识格式错误: {value}")


def _condition_matches(condition: dict, observation: dict) -> bool:
    if observation.get("observation_type") != condition["observation_type"]:
        return False
    value = _resolve_field(observation, condition["field"])
    if condition["operator"] == "exists":
        return value is not None
    if value is None:
        return False
    text = str(value)
    if condition["operator"] == "equals":
        return text == str(condition["value"])
    return str(condition["value"]) in text


def evaluate_rule(content: dict, observations: list[dict]) -> list[dict] | None:
    validate_rule_content(content)
    match = content["match"]
    conditions = match["conditions"]
    if match["logic"] == "any":
        for observation in observations:
            if any(_condition_matches(c, observation) for c in conditions):
                return [observation]
        return None
    matched = []
    for condition in conditions:
        hit = [o for o in observations if _condition_matches(condition, o)]
        if not hit:
            return None
        matched.extend(hit)
    unique = {o.get("id", id(o)): o for o in matched}
    return list(unique.values())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_rule_evaluator.py -q`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/rule_evaluator.py backend/tests/test_rule_evaluator.py
git commit -m "feat: add correlation rule evaluator"
```

---

### Task 2: Finding 可复现字段与迁移

**Files:**
- Modify: `backend/app/models/__init__.py`（`PlatformFinding`）
- Create: `backend/alembic/versions/20260924_finding_reproducibility.py`
- Test: `backend/tests/test_finding_reproducibility.py`

**Interfaces:**
- `PlatformFinding.finding_uid: str`（64 位十六进制，重复计算稳定）
- `PlatformFinding.rule_snapshot: dict`（命中时规则内容快照）
- `compute_finding_uid(finding_code: str, dedup_key: str) -> str`

- [ ] **Step 1: 写失败测试**

```python
from app.services.finding_service import compute_finding_uid


def test_finding_uid_is_stable():
    a = compute_finding_uid("PRIVACY_CONTACTS_NETWORK", "abc")
    b = compute_finding_uid("PRIVACY_CONTACTS_NETWORK", "abc")
    assert a == b
    assert len(a) == 64


def test_finding_uid_changes_with_dedup_key():
    assert compute_finding_uid("X_CODE", "a") != compute_finding_uid("X_CODE", "b")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_finding_reproducibility.py -q`
Expected: FAIL with `ImportError: cannot import name 'compute_finding_uid'`

- [ ] **Step 3: 模型加字段**

在 `PlatformFinding` 中 `dedup_key` 之后加入：

```python
    finding_uid = Column(String(64))
    rule_snapshot = Column(JSONB, default=dict)
```

- [ ] **Step 4: 迁移**

创建 `backend/alembic/versions/20260924_finding_reproducibility.py`：

```python
"""为 Platform Finding 增加可复现字段。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260924_finding_reproducibility"
down_revision = "20260924_platform_findings"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(sa.text(
        "select column_name from information_schema.columns where table_name='platform_findings'"))}
    if "finding_uid" not in existing:
        op.add_column("platform_findings", sa.Column("finding_uid", sa.String(64)))
    if "rule_snapshot" not in existing:
        op.add_column("platform_findings", sa.Column("rule_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")))
    indexes = {r[0] for r in bind.execute(sa.text(
        "select indexname from pg_indexes where schemaname='public' and tablename='platform_findings'"))}
    if "idx_platform_finding_uid" not in indexes:
        op.create_index("idx_platform_finding_uid", "platform_findings", ["task_id", "finding_uid"])


def downgrade():
    op.drop_index("idx_platform_finding_uid", table_name="platform_findings")
    op.drop_column("platform_findings", "rule_snapshot")
    op.drop_column("platform_findings", "finding_uid")
```

- [ ] **Step 5: 实现 `compute_finding_uid`**

在 `finding_service.py` 顶部加入：

```python
import hashlib


def compute_finding_uid(finding_code: str, dedup_key: str) -> str:
    """逻辑结论 ID：同一结论重复计算保持稳定。"""
    return hashlib.sha256(f"{finding_code}|{dedup_key}".encode()).hexdigest()
```

- [ ] **Step 6: 运行测试与迁移**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_finding_reproducibility.py -q && /tmp/venv/bin/python -m alembic upgrade head`
Expected: 2 passed；迁移输出 `Running upgrade 20260924_platform_findings -> 20260924_finding_reproducibility`

- [ ] **Step 7: 提交**

```bash
git add backend/app/models/__init__.py backend/alembic/versions/20260924_finding_reproducibility.py backend/app/services/finding_service.py backend/tests/test_finding_reproducibility.py
git commit -m "feat: add finding reproducibility fields"
```

---

### Task 3: 内置规则种子

**Files:**
- Create: `backend/app/services/rule_seed.py`
- Test: `backend/tests/test_correlation_rules_api.py`（种子部分）

**Interfaces:**
- `BUILTIN_CORRELATION_RULES: list[dict]` 每项含 `rule_key`、`name`、`description`、`content`。
- `seed_correlation_rules(db: Session) -> int` 幂等：已存在 `rule_key` 则跳过，返回新建数量。

- [ ] **Step 1: 写失败测试**

```python
from sqlalchemy import text
from app.services.rule_seed import seed_correlation_rules


def test_seed_is_idempotent(db):
    first = seed_correlation_rules(db)
    second = seed_correlation_rules(db)
    assert first >= 1
    assert second == 0
    row = db.execute(text("select status, current_version_id from rules where rule_key='PRIVACY_CONTACTS_NETWORK'")).first()
    assert row.status == "active"
    assert row.current_version_id is not None
    db.execute(text("delete from rule_versions where rule_id in (select id from rules where rule_key='PRIVACY_CONTACTS_NETWORK')"))
    db.execute(text("delete from rules where rule_key='PRIVACY_CONTACTS_NETWORK'"))
    db.commit()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_correlation_rules_api.py::test_seed_is_idempotent -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.rule_seed'`

- [ ] **Step 3: 实现种子**

```python
"""内置关联规则种子。"""
from sqlalchemy.orm import Session

from app.models import Rule, RuleVersion
from app.services.rule_evaluator import validate_rule_content

BUILTIN_CORRELATION_RULES = [
    {
        "rule_key": "PRIVACY_CONTACTS_NETWORK",
        "name": "通讯录信息网络传输",
        "description": "同时存在通讯录权限与通讯录数据流才成立。",
        "content": {
            "schema_version": "1.0",
            "match": {"logic": "all", "conditions": [
                {"observation_type": "fact.permission", "field": "subject",
                 "operator": "contains", "value": "android.permission.READ_CONTACTS"},
                {"observation_type": "dataflow.privacy", "field": "payload.sink.category",
                 "operator": "equals", "value": "network"},
            ]},
            "produce": {
                "finding_code": "PRIVACY_CONTACTS_NETWORK",
                "title": "通讯录信息存在潜在网络传输路径",
                "category": "privacy", "severity": "high", "confidence": "medium",
                "recommendation": "确认用户授权与隐私政策披露，并对传输数据做最小化与保护。",
            },
            "standards": {"masvs": ["MASVS-PRIVACY-1"], "maswe": ["MASWE-0001"],
                          "mastg": ["MASTG-TEST-PRIVACY-1"], "cwe": []},
        },
    },
]


def seed_correlation_rules(db: Session) -> int:
    created = 0
    for item in BUILTIN_CORRELATION_RULES:
        if db.query(Rule).filter(Rule.rule_key == item["rule_key"]).first():
            continue
        validate_rule_content(item["content"])
        rule = Rule(rule_key=item["rule_key"], name=item["name"],
                    category="correlation", description=item["description"], status="active")
        db.add(rule)
        db.flush()
        version = RuleVersion(rule_id=rule.id, version="1.0", rule_content=item["content"],
                              changelog="内置规则初始化", status="published")
        db.add(version)
        db.flush()
        rule.current_version_id = version.id
        created += 1
    db.commit()
    return created
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_correlation_rules_api.py::test_seed_is_idempotent -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/rule_seed.py backend/tests/test_correlation_rules_api.py
git commit -m "feat: add builtin correlation rule seed"
```

---

### Task 4: 改造关联与 Finding 生成读取数据库规则

**Files:**
- Modify: `backend/app/services/correlation.py`
- Modify: `backend/app/services/finding_service.py`
- Modify: `backend/app/services/finding_baseline.py`
- Test: `backend/tests/test_correlation.py`, `backend/tests/test_finding_auto_trigger.py`

**Interfaces:**
- `load_active_rules(db) -> list[dict]` 返回 `{"rule": Rule, "version": RuleVersion, "content": dict}`。
- `correlate(observations: list[dict], rules: list[dict]) -> list[dict]` 第二个参数为规则列表。
- `generate_findings(db, task_id)` 写入 `finding_uid`、`rule_snapshot`、`correlation_rule_id`、`correlation_rule_version`。

- [ ] **Step 1: 改造 `correlation.py`**

```python
"""跨引擎 Observation 关联和去重规则。"""
from hashlib import sha256
import json

from sqlalchemy.orm import Session

from app.models import Rule, RuleVersion
from app.services.rule_evaluator import evaluate_rule


def observation_dedup_key(observation: dict) -> str:
    payload = {"type": observation.get("observation_type"), "subject": observation.get("subject"),
               "payload": observation.get("payload")}
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def load_active_rules(db: Session) -> list[dict]:
    """读取已发布的关联规则。"""
    rows = db.query(Rule, RuleVersion).join(
        RuleVersion, Rule.current_version_id == RuleVersion.id
    ).filter(Rule.category == "correlation", Rule.status == "active").all()
    return [{"rule": rule, "version": version, "content": version.rule_content or {}}
            for rule, version in rows]


def correlate(observations: list[dict], rules: list[dict]) -> list[dict]:
    findings = []
    for entry in rules:
        content = entry["content"]
        matched = evaluate_rule(content, observations)
        if not matched:
            continue
        produce = content.get("produce") or {}
        standards = content.get("standards") or {}
        key = sha256((produce.get("finding_code", "") + "|" + "|".join(
            str(o.get("id", observation_dedup_key(o))) for o in matched)).encode()).hexdigest()
        findings.append({
            "finding_code": produce.get("finding_code"),
            "title": produce.get("title"),
            "category": produce.get("category"),
            "severity": produce.get("severity", "medium"),
            "confidence": produce.get("confidence", "medium"),
            "recommendation": produce.get("recommendation"),
            "masvs_controls": standards.get("masvs", []),
            "maswe_ids": standards.get("maswe", []),
            "mastg_test_ids": standards.get("mastg", []),
            "cwe_ids": standards.get("cwe", []),
            "correlation_rule_id": str(entry["rule"].id),
            "correlation_rule_version": entry["version"].version,
            "rule_snapshot": content,
            "dedup_key": key,
            "observation_ids": [o.get("id") for o in matched if o.get("id")],
        })
    return findings
```

- [ ] **Step 2: 改造 `finding_service.generate_findings`**

```python
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
```

- [ ] **Step 3: 删除 `finding_baseline.py` 中的硬编码映射**

`MAS_MAPPINGS` 与 `apply_mas_mapping` 删除，仅保留 `baseline_state`。

- [ ] **Step 4: 更新受影响的测试**

`tests/test_correlation.py` 改为传入规则列表：

```python
from app.services.correlation import correlate
from app.services.rule_seed import BUILTIN_CORRELATION_RULES

RULES = [{"rule": type("R", (), {"id": 1})(), "version": type("V", (), {"version": "1.0"})(),
          "content": BUILTIN_CORRELATION_RULES[0]["content"]}]


def test_correlation_requires_both_permission_and_flow():
    permission = {"id": 1, "observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}}
    flow = {"id": 2, "observation_type": "dataflow.privacy", "subject": "Contacts",
            "payload": {"sink": {"category": "network"}}}
    assert correlate([permission], RULES) == []
    findings = correlate([permission, flow], RULES)
    assert len(findings) == 1
    assert findings[0]["finding_code"] == "PRIVACY_CONTACTS_NETWORK"
```

`tests/test_finding_auto_trigger.py` 在生成前调用 `seed_correlation_rules(db)`。

- [ ] **Step 5: 运行测试**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_correlation.py tests/test_finding_auto_trigger.py tests/test_rule_evaluator.py -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/correlation.py backend/app/services/finding_service.py backend/app/services/finding_baseline.py backend/tests
git commit -m "feat: drive correlation from persisted rules"
```

---

### Task 5: 关联规则管理 API

**Files:**
- Create: `backend/app/api/v1/correlation_rules.py`
- Modify: `backend/app/api/v1/__init__.py`
- Modify: `backend/app/schemas/__init__.py`
- Test: `backend/tests/test_correlation_rules_api.py`

**Interfaces:**
- `CorrelationRuleCreate(rule_key, name, description, content)`
- `CorrelationRuleVersionCreate(version, content, changelog)`
- 路由前缀 `/correlation-rules`。

- [ ] **Step 1: 写失败测试**

```python
def test_create_rule_validates_content(client, admin_headers):
    bad = {"rule_key": "BAD_RULE", "name": "坏规则", "content": {"schema_version": "1.0"}}
    resp = client.post("/api/v1/correlation-rules", headers=admin_headers, json=bad)
    assert resp.status_code == 422


def test_rule_lifecycle(client, admin_headers):
    content = dict(BUILTIN_CORRELATION_RULES[0]["content"])
    content = {**content, "produce": {**content["produce"], "finding_code": "TEST_LIFECYCLE"}}
    created = client.post("/api/v1/correlation-rules", headers=admin_headers, json={
        "rule_key": "TEST_LIFECYCLE", "name": "生命周期", "description": "", "content": content})
    assert created.status_code == 200
    rid = created.json()["data"]["id"]

    saved = client.put(f"/api/v1/correlation-rules/{rid}/versions", headers=admin_headers,
                       json={"version": "1.1", "content": content, "changelog": "调整"})
    assert saved.status_code == 200
    vid = saved.json()["data"]["id"]

    # 新版本默认不启用
    detail = client.get(f"/api/v1/correlation-rules/{rid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "disabled"

    published = client.post(f"/api/v1/correlation-rules/{rid}/versions/{vid}/publish", headers=admin_headers)
    assert published.status_code == 200
    detail = client.get(f"/api/v1/correlation-rules/{rid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "active"
    assert detail["current_version"] == "1.1"

    disabled = client.post(f"/api/v1/correlation-rules/{rid}/disable", headers=admin_headers)
    assert disabled.status_code == 200
```

- [ ] **Step 2: 补充测试夹具**

当前 `backend/tests/conftest.py` 没有 HTTP 客户端与鉴权夹具，需要新增：

```python
@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture
def admin_headers(client):
    resp = client.post("/api/v1/auth/login",
                       json={"username": "admin", "password": "admin123"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_correlation_rules_api.py -q`
Expected: FAIL（`/correlation-rules` 路由不存在，返回 404）

- [ ] **Step 4: 增加 schemas**

在 `backend/app/schemas/__init__.py` 的规则模型后加入：

```python
class CorrelationRuleCreate(BaseModel):
    rule_key: str
    name: str
    description: Optional[str] = None
    content: dict


class CorrelationRuleVersionCreate(BaseModel):
    version: str
    content: dict
    changelog: Optional[str] = None


class CorrelationRulePreview(BaseModel):
    task_id: int
```

- [ ] **Step 5: 实现路由**

创建 `backend/app/api/v1/correlation_rules.py`：

```python
"""关联规则管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.models import EngineObservation, PlatformFinding, Rule, RuleVersion, User
from app.schemas import CorrelationRuleCreate, CorrelationRulePreview, CorrelationRuleVersionCreate
from app.services.correlation import correlate, load_active_rules
from app.services.rule_evaluator import RuleValidationError, evaluate_rule, validate_rule_content

router = APIRouter(prefix="/correlation-rules", tags=["关联规则"])


def _serialize(rule: Rule, version: RuleVersion | None, hit_count: int = 0) -> dict:
    return {
        "id": rule.id, "rule_key": rule.rule_key, "name": rule.name,
        "description": rule.description, "status": rule.status,
        "current_version_id": rule.current_version_id,
        "current_version": version.version if version else None,
        "current_content": version.rule_content if version else None,
        "hit_count": hit_count,
        "updated_at": str(rule.updated_at) if rule.updated_at else None,
    }


@router.get("")
def list_correlation_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rules = db.query(Rule).filter(Rule.category == "correlation").order_by(Rule.rule_key).all()
    result = []
    for rule in rules:
        version = db.query(RuleVersion).get(rule.current_version_id) if rule.current_version_id else None
        hits = db.query(PlatformFinding).filter(PlatformFinding.correlation_rule_id == str(rule.id)).count()
        result.append(_serialize(rule, version, hits))
    return {"code": 0, "data": result}


@router.get("/{rid}")
def get_correlation_rule(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    if not rule or rule.category != "correlation":
        raise HTTPException(status_code=404, detail="规则不存在")
    versions = db.query(RuleVersion).filter(RuleVersion.rule_id == rid).order_by(RuleVersion.created_at.desc()).all()
    current = db.query(RuleVersion).get(rule.current_version_id) if rule.current_version_id else None
    data = _serialize(rule, current)
    data["versions"] = [{"id": v.id, "version": v.version, "status": v.status, "changelog": v.changelog,
                         "created_at": str(v.created_at) if v.created_at else None} for v in versions]
    return {"code": 0, "data": data}


@router.post("")
def create_correlation_rule(req: CorrelationRuleCreate,
                            user: User = Depends(require_permission("rule:write")),
                            db: Session = Depends(get_db)):
    if db.query(Rule).filter(Rule.rule_key == req.rule_key).first():
        raise HTTPException(status_code=409, detail="规则编号已存在")
    try:
        validate_rule_content(req.content)
    except RuleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    rule = Rule(rule_key=req.rule_key, name=req.name, category="correlation",
                description=req.description, status="disabled")
    db.add(rule)
    db.flush()
    version = RuleVersion(rule_id=rule.id, version="1.0", rule_content=req.content,
                          changelog="初始版本", status="draft")
    db.add(version)
    db.commit()
    db.refresh(rule)
    return {"code": 0, "data": {"id": rule.id, "version_id": version.id}}


@router.put("/{rid}/versions")
def save_correlation_version(rid: int, req: CorrelationRuleVersionCreate,
                             user: User = Depends(require_permission("rule:write")),
                             db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    if not rule or rule.category != "correlation":
        raise HTTPException(status_code=404, detail="规则不存在")
    if db.query(RuleVersion).filter(RuleVersion.rule_id == rid, RuleVersion.version == req.version).first():
        raise HTTPException(status_code=409, detail="版本号已存在")
    try:
        validate_rule_content(req.content)
    except RuleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    version = RuleVersion(rule_id=rid, version=req.version, rule_content=req.content,
                          changelog=req.changelog, status="draft")
    db.add(version)
    # 保存即新版本，新版本默认不启用
    rule.status = "disabled"
    db.commit()
    db.refresh(version)
    return {"code": 0, "data": {"id": version.id, "version": version.version}}


@router.post("/{rid}/versions/{vid}/publish")
def publish_correlation_version(rid: int, vid: int,
                                user=Depends(require_permission("rule:publish")),
                                db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    version = db.query(RuleVersion).get(vid)
    if not rule or not version or version.rule_id != rid:
        raise HTTPException(status_code=404, detail="规则版本不存在")
    version.status = "published"
    version.published_by = user.id
    rule.current_version_id = vid
    rule.status = "active"
    db.commit()
    return {"code": 0, "data": {"id": vid, "status": "active"}}


@router.post("/{rid}/disable")
def disable_correlation_rule(rid: int, user=Depends(require_permission("rule:write")),
                             db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    if not rule or rule.category != "correlation":
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.status = "disabled"
    db.commit()
    return {"code": 0, "data": {"id": rule.id, "status": rule.status}}


@router.post("/{rid}/preview")
def preview_correlation_rule(rid: int, req: CorrelationRulePreview,
                             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    if not rule or rule.category != "correlation":
        raise HTTPException(status_code=404, detail="规则不存在")
    version = db.query(RuleVersion).get(rule.current_version_id) if rule.current_version_id else None
    if not version:
        raise HTTPException(status_code=400, detail="规则没有可预览的版本")
    rows = db.query(EngineObservation).filter(EngineObservation.task_id == req.task_id).all()
    observations = [{"id": o.id, "observation_type": o.observation_type, "subject": o.subject,
                     "payload": o.payload or {}, "location": o.location} for o in rows]
    matched = evaluate_rule(version.rule_content, observations) or []
    current = db.query(PlatformFinding).filter(
        PlatformFinding.task_id == req.task_id,
        PlatformFinding.correlation_rule_id == str(rule.id)).all()
    finding_code = (version.rule_content.get("produce") or {}).get("finding_code")
    return {"code": 0, "data": {
        "rule_key": rule.rule_key,
        "would_match": bool(matched),
        "matched_observation_ids": [o["id"] for o in matched],
        "finding_code": finding_code,
        "existing_findings": [f.finding_code for f in current],
        "writes": False,
    }}
```

- [ ] **Step 6: 注册路由**

在 `backend/app/api/v1/__init__.py` 增加导入与注册：

```python
from app.api.v1.correlation_rules import router as correlation_rules_router
api_router.include_router(correlation_rules_router)
```

- [ ] **Step 7: 运行测试**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_correlation_rules_api.py -q`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add backend/app/api/v1/correlation_rules.py backend/app/api/v1/__init__.py backend/app/schemas/__init__.py backend/tests/test_correlation_rules_api.py
git commit -m "feat: add correlation rule management API"
```

---

### Task 6: 正反例 fixture 回归测试

**Files:**
- Create: `backend/tests/fixtures/correlation/PRIVACY_CONTACTS_NETWORK/positive.json`
- Create: `backend/tests/fixtures/correlation/PRIVACY_CONTACTS_NETWORK/negative.json`
- Create: `backend/tests/test_correlation_fixtures.py`

**Interfaces:**
- fixture 目录名对应 `rule_key`；`positive.json` 为 Observation 列表，必须命中；`negative.json` 必须不命中。

- [ ] **Step 1: 写 fixture 数据**

`positive.json`：

```json
[
  {"observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}},
  {"observation_type": "dataflow.privacy", "subject": "Contacts", "payload": {"sink": {"category": "network"}}}
]
```

`negative.json`（像威胁的良性噪声：有权限但无外传）：

```json
[
  {"observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}},
  {"observation_type": "dataflow.privacy", "subject": "Contacts", "payload": {"sink": {"category": "log"}}}
]
```

- [ ] **Step 2: 写测试**

```python
import json
from pathlib import Path
import pytest

from app.services.rule_evaluator import evaluate_rule
from app.services.rule_seed import BUILTIN_CORRELATION_RULES

FIXTURES = Path(__file__).parent / "fixtures" / "correlation"


@pytest.mark.parametrize("rule", BUILTIN_CORRELATION_RULES, ids=lambda r: r["rule_key"])
def test_positive_fixture_matches(rule):
    observations = json.loads((FIXTURES / rule["rule_key"] / "positive.json").read_text())
    assert evaluate_rule(rule["content"], observations) is not None


@pytest.mark.parametrize("rule", BUILTIN_CORRELATION_RULES, ids=lambda r: r["rule_key"])
def test_negative_fixture_does_not_match(rule):
    observations = json.loads((FIXTURES / rule["rule_key"] / "negative.json").read_text())
    assert evaluate_rule(rule["content"], observations) is None
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_correlation_fixtures.py -q`
Expected: 2 passed

- [ ] **Step 4: 提交**

```bash
git add backend/tests/fixtures/correlation backend/tests/test_correlation_fixtures.py
git commit -m "test: add correlation rule fixtures"
```

---

### Task 7: 前端规则管理界面

**Files:**
- Create: `frontend/src/api/correlationRules.ts`
- Create: `frontend/src/views/CorrelationRules.vue`
- Modify: `frontend/src/router/index.ts`

**Interfaces:**
- 调用 `GET /correlation-rules`、`GET /correlation-rules/{id}`、`POST /correlation-rules`、`PUT /correlation-rules/{id}/versions`、`POST /correlation-rules/{id}/versions/{vid}/publish`、`POST /correlation-rules/{id}/disable`、`POST /correlation-rules/{id}/preview`。

- [ ] **Step 1: API 封装**

```typescript
import api from './index'

export const correlationRuleApi = {
  list: () => api.get('/correlation-rules'),
  get: (id: number) => api.get(`/correlation-rules/${id}`),
  create: (data: any) => api.post('/correlation-rules', data),
  saveVersion: (id: number, data: any) => api.put(`/correlation-rules/${id}/versions`, data),
  publish: (id: number, vid: number) => api.post(`/correlation-rules/${id}/versions/${vid}/publish`),
  disable: (id: number) => api.post(`/correlation-rules/${id}/disable`),
  preview: (id: number, taskId: number) => api.post(`/correlation-rules/${id}/preview`, { task_id: taskId }),
}
```

- [ ] **Step 2: 路由注册**

在 `frontend/src/router/index.ts` 的 `rules` 相邻位置加入：

```typescript
{ path: 'correlation-rules', name: 'CorrelationRules', component: () => import('@/views/CorrelationRules.vue'),
  meta: { title: '关联规则', group: '知识库' } },
```

- [ ] **Step 3: 实现页面**

`CorrelationRules.vue` 结构：

```text
列表区
  表格：规则编号 / 名称 / 状态 / 当前版本 / 命中数 / 最近变更 / 操作
  操作：查看、新建

详情抽屉
  基本信息   名称、描述（可编辑）
  匹配条件   logic 下拉（all/any）+ 条件行表格（观察类型、字段、操作符、值），可增删行
  产出定义   标题、类别、严重性、置信度、整改建议
  标准映射   MASVS / MASWE / MASTG / CWE 标签输入
  版本历史   版本、状态、变更说明、发布时间，含「发布」按钮
  命中预览   输入任务 ID → 展示是否命中、命中 Observation 数、是否写库
```

条件编辑器只使用 `el-select` 与 `el-input`，字段选项固定为：

```text
subject / location / payload.sink.category / payload.source.category / payload.rule
```

操作符固定为 `equals / contains / exists`。`exists` 时隐藏值输入框。

- [ ] **Step 4: 构建**

Run: `cd frontend && npm run build`
Expected: `✓ built`

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/correlationRules.ts frontend/src/views/CorrelationRules.vue frontend/src/router/index.ts
git commit -m "feat: add correlation rule management UI"
```

---

### Task 8: 端到端验收

**Files:**
- Modify: `README.md`
- Modify: `backend/tests/test_correlation_rules_api.py`（补充预览用例）

- [ ] **Step 1: 补充预览测试**

```python
def test_preview_does_not_write(client, admin_headers, db):
    before = db.query(PlatformFinding).count()
    resp = client.post(f"/api/v1/correlation-rules/{rule_id}/preview", headers=admin_headers, json={"task_id": 999999})
    assert resp.status_code == 200
    assert resp.json()["data"]["writes"] is False
    assert db.query(PlatformFinding).count() == before
```

- [ ] **Step 2: 全量测试**

Run:

```bash
cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests -q
cd ../frontend && npm run build
```

Expected: 后端全部通过；前端构建成功。

- [ ] **Step 3: 迁移与种子**

```bash
cd backend
/tmp/venv/bin/python -m alembic upgrade head
/tmp/venv/bin/python -c "from app.core.database import SessionLocal; from app.services.rule_seed import seed_correlation_rules as s; db=SessionLocal(); print('seeded', s(db)); db.close()"
```

- [ ] **Step 4: 真实链路验证**

提交一个包含 androguard + appshark + mobsf 的任务，确认：

```text
GET /api/v1/correlation-rules                 返回内置规则，状态 active
GET /api/v1/tasks/{id}/platform-findings      若命中，Finding 带 finding_uid 与 rule_snapshot
停用规则后重新生成 Finding                     不再产生新 Finding
历史 Finding 的 rule_snapshot                  保持不变
修改规则保存新版本                             状态变为 disabled，需显式发布
```

- [ ] **Step 5: 文档与提交**

README 增加关联规则章节：规则存储位置、发布语义、预览用法、fixture 回归测试命令。

```bash
git add README.md backend/tests
git commit -m "docs: document correlation rules operations"
```

## Self-review coverage

- 规则校验与求值：Task 1。
- Finding 可复现字段与迁移：Task 2。
- 内置规则种子：Task 3。
- 关联与 Finding 生成读取数据库规则、删除硬编码映射：Task 4。
- 规则 CRUD、发布、停用、预览 API：Task 5。
- 正反例 fixture 回归测试：Task 6。
- 前端规则管理界面：Task 7。
- 端到端验收与文档：Task 8。

规格中「保存即新版本且默认不启用」在 Task 5 的 `save_correlation_version` 与测试中体现；「预览不写库」在 Task 5 与 Task 8 中验证；「历史结论可复现」由 Task 2 的 `finding_uid` 与 `rule_snapshot` 加 Task 4 的写入逻辑共同覆盖。
