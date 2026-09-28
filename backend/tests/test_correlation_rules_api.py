from sqlalchemy import text
from app.services.rule_seed import BUILTIN_CORRELATION_RULES, seed_correlation_rules

BUILTIN_RULE_KEY = "PRIVACY_CONTACTS_NETWORK"
LIFECYCLE_RULE_KEY = "TEST_LIFECYCLE"
PREVIEW_RULE_KEY = "TEST_PREVIEW"
BAD_RULE_KEY = "BAD_RULE"
NON_CORRELATION_RULE_KEY = "TEST_NON_CORRELATION"
INVALID_CONTENT_RULE_KEY = "TEST_INVALID_CONTENT"


def _delete_rule(db, rule_key):
    """删除指定规则的版本与规则本身，先删版本（引用 rules.id）再删规则。"""
    db.execute(text("delete from rule_versions where rule_id in (select id from rules where rule_key=:key)"), {"key": rule_key})
    db.execute(text("delete from rules where rule_key=:key"), {"key": rule_key})
    db.commit()


def _seed_status(rule_key):
    """内置规则在种子里声明的启用状态。"""
    return next(r.get("status", "active") for r in BUILTIN_CORRELATION_RULES
                if r["rule_key"] == rule_key)


def _builtin_rule_rows(db):
    """内置规则的行数与状态。测试只读取、不删除共享的内置规则行。"""
    return db.execute(text(
        "select id, status, current_version_id from rules where rule_key=:key"
    ), {"key": BUILTIN_RULE_KEY}).all()


def test_seed_is_idempotent(db):
    """种子幂等：先确保内置规则存在，再次调用不得新建、不得改变已有行。"""
    seed_correlation_rules(db)

    rows = _builtin_rule_rows(db)
    assert len(rows) == 1, "内置规则必须唯一"
    before = rows[0]

    assert seed_correlation_rules(db) == 0

    rows = _builtin_rule_rows(db)
    assert len(rows) == 1
    # 幂等 = 重复执行不改动任何已有行。这里不断言具体状态：内置规则的启用与否是
    # 种子的声明（PRIVACY_CONTACTS_NETWORK 已停用，见设计 §10），把状态写死会把
    # 「幂等」和「当前状态恰好是什么」混为一谈。
    assert (rows[0].id, rows[0].status, rows[0].current_version_id) == (before.id, before.status, before.current_version_id)
    assert rows[0].status == _seed_status(BUILTIN_RULE_KEY)


def test_seed_database_wires_builtin_correlation_rule(db, monkeypatch):
    """`seed_database()` 必须调用关联规则种子，否则全新/已部署环境里关联静默失效。

    用间谍替换 `app.seed.seed_correlation_rules` 只观察调用，不改动共享的内置规则行。
    """
    import app.seed as seed_module
    from app.services.correlation import load_active_rules

    calls = []
    real_seed = seed_module.seed_correlation_rules

    def spy(session):
        calls.append(session)
        return real_seed(session)

    monkeypatch.setattr(seed_module, "seed_correlation_rules", spy)
    seed_module.seed_database()

    assert len(calls) == 1, "seed_database() 没有调用 seed_correlation_rules()"

    # 接线后关联链路不再空转：内置规则按种子声明的状态存在，且启用中的那些能被关联逻辑读到
    for item in BUILTIN_CORRELATION_RULES:
        row = db.execute(text("select status, current_version_id from rules where rule_key=:key"),
                         {"key": item["rule_key"]}).first()
        assert row is not None, f"{item['rule_key']} 没有被种子写入"
        assert row.status == item.get("status", "active"), f"{item['rule_key']} 的状态与种子声明不符"
        assert row.current_version_id is not None

    active = {entry["rule"].rule_key for entry in load_active_rules(db)}
    assert active >= {r["rule_key"] for r in BUILTIN_CORRELATION_RULES
                      if r.get("status", "active") == "active"}, \
        "启用中的内置规则必须能被关联逻辑读到，否则会静默少跑规则"


def test_preview_without_observations_writes_nothing(client, admin_headers, db):
    """预览一个没有任何 Observation 的任务：不命中，且不写库。"""
    rule_id = db.execute(text(
        "select id from rules where rule_key=:key"), {"key": BUILTIN_RULE_KEY}).scalar()
    assert rule_id is not None

    missing_task_id = 999999
    before = db.execute(text(
        "select count(*) from platform_findings where task_id=:tid"), {"tid": missing_task_id}).scalar()

    resp = client.post(f"/api/v1/correlation-rules/{rule_id}/preview", headers=admin_headers,
                       json={"task_id": missing_task_id})
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["would_match"] is False
    assert data["matched_observation_ids"] == []
    assert data["writes"] is False

    db.rollback()
    after = db.execute(text(
        "select count(*) from platform_findings where task_id=:tid"), {"tid": missing_task_id}).scalar()
    assert after == before == 0


def test_create_rule_validates_content(client, admin_headers, db):
    bad = {"rule_key": BAD_RULE_KEY, "name": "坏规则", "content": {"schema_version": "1.0"}}
    try:
        resp = client.post("/api/v1/correlation-rules", headers=admin_headers, json=bad)
        assert resp.status_code == 422
    finally:
        _delete_rule(db, BAD_RULE_KEY)


def test_rule_lifecycle(client, admin_headers, db):
    try:
        content = dict(BUILTIN_CORRELATION_RULES[0]["content"])
        content = {**content, "produce": {**content["produce"], "finding_code": "TEST_LIFECYCLE"}}
        created = client.post("/api/v1/correlation-rules", headers=admin_headers, json={
            "rule_key": LIFECYCLE_RULE_KEY, "name": "生命周期", "description": "", "content": content})
        assert created.status_code == 200
        rid = created.json()["data"]["id"]

        listed = client.get("/api/v1/correlation-rules", headers=admin_headers)
        assert listed.status_code == 200
        assert any(item["rule_key"] == LIFECYCLE_RULE_KEY for item in listed.json()["data"])

        saved = client.put(f"/api/v1/correlation-rules/{rid}/versions", headers=admin_headers,
                           json={"version": "1.1", "content": content, "changelog": "调整"})
        assert saved.status_code == 200
        vid = saved.json()["data"]["id"]

        # 新版本默认不启用
        detail = client.get(f"/api/v1/correlation-rules/{rid}", headers=admin_headers).json()["data"]
        assert detail["status"] == "disabled"
        assert detail["current_version"] is None
        assert len(detail["versions"]) == 2

        published = client.post(f"/api/v1/correlation-rules/{rid}/versions/{vid}/publish", headers=admin_headers)
        assert published.status_code == 200
        detail = client.get(f"/api/v1/correlation-rules/{rid}", headers=admin_headers).json()["data"]
        assert detail["status"] == "active"
        assert detail["current_version"] == "1.1"

        disabled = client.post(f"/api/v1/correlation-rules/{rid}/disable", headers=admin_headers)
        assert disabled.status_code == 200
        assert disabled.json()["data"]["status"] == "disabled"
    finally:
        _delete_rule(db, LIFECYCLE_RULE_KEY)


def test_preview_reports_match_and_writes_nothing(client, admin_headers, db, execution):
    from sqlalchemy import event

    from app.core.database import engine
    from app.models import EngineObservation

    statements = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    try:
        content = dict(BUILTIN_CORRELATION_RULES[0]["content"])
        content = {**content, "produce": {**content["produce"], "finding_code": "TEST_PREVIEW"}}
        created = client.post("/api/v1/correlation-rules", headers=admin_headers, json={
            "rule_key": PREVIEW_RULE_KEY, "name": "预览", "description": "", "content": content})
        assert created.status_code == 200
        rid = created.json()["data"]["id"]
        vid = created.json()["data"]["version_id"]
        published = client.post(f"/api/v1/correlation-rules/{rid}/versions/{vid}/publish",
                                headers=admin_headers)
        assert published.status_code == 200

        # 形状取自真实引擎产物（端到端任务 465）
        permission = EngineObservation(
            task_id=execution.task_id, execution_id=execution.id, engine_type="androguard",
            observation_type="fact.sensitive_permission", subject="READ_CONTACTS",
            payload={"api": "READ_CONTACTS", "category": "CONTACTS", "permission": "READ_CONTACTS"})
        dataflow = EngineObservation(
            task_id=execution.task_id, execution_id=execution.id, engine_type="appshark",
            observation_type="dataflow.privacy",
            subject="['<com.baidu.mobstat.ba: java.net.HttpURLConnection a(android.content.Context,java.lang.String,int,int)>->$r0']",
            payload={"section": "ComplianceInfo", "rule": "DeviceId_NetworkTransfer", "level": "L3",
                     "sink": ["<com.baidu.mobstat.ba: java.net.HttpURLConnection a(android.content.Context,java.lang.String,int,int)>->$r0"]})
        db.add_all([permission, dataflow])
        db.commit()
        db.refresh(permission)
        db.refresh(dataflow)

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            resp = client.post(f"/api/v1/correlation-rules/{rid}/preview", headers=admin_headers,
                               json={"task_id": execution.task_id})
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["rule_key"] == PREVIEW_RULE_KEY
        assert data["would_match"] is True
        assert set(data["matched_observation_ids"]) == {permission.id, dataflow.id}
        assert data["finding_code"] == "TEST_PREVIEW"
        assert data["existing_findings"] == []
        assert data["writes"] is False

        writes = [s for s in statements if s in ("INSERT", "UPDATE", "DELETE")]
        assert writes == [], f"预览接口不应写库，实际写操作: {statements}"
    finally:
        _delete_rule(db, PREVIEW_RULE_KEY)


def test_publish_rejects_non_correlation_rule(client, admin_headers, db):
    from app.models import Rule, RuleVersion

    try:
        rule = Rule(rule_key=NON_CORRELATION_RULE_KEY, name="非关联规则", category="consent",
                    status="disabled")
        db.add(rule)
        db.flush()
        current = RuleVersion(rule_id=rule.id, version="1.0", rule_content={"schema_version": "1.0"},
                              changelog="", status="draft")
        draft = RuleVersion(rule_id=rule.id, version="1.1", rule_content={"schema_version": "1.0"},
                            changelog="", status="draft")
        db.add_all([current, draft])
        db.flush()
        rule.current_version_id = current.id
        db.commit()
        rid, current_id, draft_id = rule.id, current.id, draft.id

        resp = client.post(f"/api/v1/correlation-rules/{rid}/versions/{draft_id}/publish",
                           headers=admin_headers)
        assert resp.status_code == 404

        # 非关联规则必须原封不动
        db.expire_all()
        persisted = db.query(Rule).get(rid)
        assert persisted.status == "disabled"
        assert persisted.current_version_id == current_id
        assert db.query(RuleVersion).get(draft_id).status == "draft"
    finally:
        _delete_rule(db, NON_CORRELATION_RULE_KEY)


def test_preview_rejects_invalid_stored_content(client, admin_headers, db, execution):
    from app.models import RuleVersion

    try:
        content = dict(BUILTIN_CORRELATION_RULES[0]["content"])
        content = {**content, "produce": {**content["produce"], "finding_code": "TEST_INVALID_CONTENT"}}
        created = client.post("/api/v1/correlation-rules", headers=admin_headers, json={
            "rule_key": INVALID_CONTENT_RULE_KEY, "name": "非法内容", "description": "", "content": content})
        assert created.status_code == 200
        rid = created.json()["data"]["id"]
        vid = created.json()["data"]["version_id"]
        published = client.post(f"/api/v1/correlation-rules/{rid}/versions/{vid}/publish",
                                headers=admin_headers)
        assert published.status_code == 200

        # 绕过写接口的校验，模拟库里已存在的非法内容
        db.query(RuleVersion).filter(RuleVersion.id == vid).update(
            {"rule_content": {"schema_version": "1.0"}})
        db.commit()

        resp = client.post(f"/api/v1/correlation-rules/{rid}/preview", headers=admin_headers,
                           json={"task_id": execution.task_id})
        # 客户端可见的校验失败必须是 4xx，不能变成 500
        assert resp.status_code == 422, resp.text
    finally:
        _delete_rule(db, INVALID_CONTENT_RULE_KEY)
