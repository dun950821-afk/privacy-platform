from sqlalchemy import text
from app.services.rule_seed import BUILTIN_CORRELATION_RULES, seed_correlation_rules

BUILTIN_RULE_KEY = "PRIVACY_CONTACTS_NETWORK"
LIFECYCLE_RULE_KEY = "TEST_LIFECYCLE"
PREVIEW_RULE_KEY = "TEST_PREVIEW"
BAD_RULE_KEY = "BAD_RULE"


def _delete_rule(db, rule_key):
    """删除指定规则的版本与规则本身，先删版本（引用 rules.id）再删规则。"""
    db.execute(text("delete from rule_versions where rule_id in (select id from rules where rule_key=:key)"), {"key": rule_key})
    db.execute(text("delete from rules where rule_key=:key"), {"key": rule_key})
    db.commit()


def _delete_builtin_rule(db):
    """删除内置规则及其版本，先删版本（引用 rules.id）再删规则。"""
    db.execute(text("delete from rule_versions where rule_id in (select id from rules where rule_key=:key)"), {"key": BUILTIN_RULE_KEY})
    db.execute(text("delete from rules where rule_key=:key"), {"key": BUILTIN_RULE_KEY})
    db.commit()


def test_seed_is_idempotent(db):
    _delete_builtin_rule(db)
    try:
        first = seed_correlation_rules(db)
        second = seed_correlation_rules(db)
        assert first == 1
        assert second == 0
        row = db.execute(text("select status, current_version_id from rules where rule_key='PRIVACY_CONTACTS_NETWORK'")).first()
        assert row.status == "active"
        assert row.current_version_id is not None
    finally:
        _delete_builtin_rule(db)


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

        permission = EngineObservation(
            task_id=execution.task_id, execution_id=execution.id, engine_type="mobsf",
            observation_type="fact.permission", subject="android.permission.READ_CONTACTS", payload={})
        dataflow = EngineObservation(
            task_id=execution.task_id, execution_id=execution.id, engine_type="mobsf",
            observation_type="dataflow.privacy", subject="ContactsContract",
            payload={"sink": {"category": "network"}})
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
