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
