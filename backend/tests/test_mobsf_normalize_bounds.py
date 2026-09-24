from app.engine.adapters.mobsf import MobSFAdapter


def test_url_entries_never_exceed_column_limit():
    adapter = MobSFAdapter({})
    events = adapter.normalize_events({"urls": [{"urls": ["https://a.test/" + "x" * 900], "path": "assets/x.so"}]})
    assert events
    assert all(len(e.get("api") or "") <= 480 for e in events)


def test_noise_exported_components_are_skipped():
    adapter = MobSFAdapter({})
    events = adapter.normalize_events({"exported_activities": ["'", "]", "", "com.example.MainActivity"]})
    components = [e["api"] for e in events if e["event_type"] == "security_observation"]
    assert components == ["com.example.MainActivity"]
