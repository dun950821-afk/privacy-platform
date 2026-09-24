from sqlalchemy import text
from app.services.rule_seed import seed_correlation_rules

BUILTIN_RULE_KEY = "PRIVACY_CONTACTS_NETWORK"


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
