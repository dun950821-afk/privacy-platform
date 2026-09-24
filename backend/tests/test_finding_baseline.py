from app.services.finding_baseline import baseline_state


def test_baseline_states():
    current = {"dedup_key": "x"}
    assert baseline_state(None, current) == "new"
    assert baseline_state({"dedup_key": "x"}, current) == "unchanged"
    assert baseline_state({"dedup_key": "y"}, current) == "changed"
