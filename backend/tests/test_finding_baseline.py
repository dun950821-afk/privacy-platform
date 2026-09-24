from app.services.finding_baseline import apply_mas_mapping, baseline_state


def test_mas_mapping_adds_standard_ids():
    result = apply_mas_mapping({"finding_code": "PRIVACY_CONTACTS_NETWORK"})
    assert result["masvs_controls"]
    assert result["maswe_ids"]
    assert result["mastg_test_ids"]


def test_baseline_states():
    current = {"dedup_key": "x"}
    assert baseline_state(None, current) == "new"
    assert baseline_state({"dedup_key": "x"}, current) == "unchanged"
    assert baseline_state({"dedup_key": "y"}, current) == "changed"
