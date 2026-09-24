from app.engine.runners.androguard_runner import collect_facts


def test_collect_facts_has_facts_schema(sample_apk):
    facts = collect_facts(sample_apk)
    assert facts["schema_version"] == "1.0"
    assert facts["basic_info"]["package_name"]
    assert "activities" in facts["components"]
    assert "declared" in facts["permissions"]


def test_collect_facts_rejects_missing_file(tmp_path):
    import pytest
    with pytest.raises(Exception):
        collect_facts(str(tmp_path / "missing.apk"))
