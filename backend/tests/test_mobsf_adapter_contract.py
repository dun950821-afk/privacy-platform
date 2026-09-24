import json
from app.engine.adapters.mobsf import MobSFAdapter


def test_mobsf_provider_metadata_from_response():
    adapter = MobSFAdapter({"url": "http://127.0.0.1:8001", "api_key": "x"})
    metadata = adapter.provider_metadata({"version": "v4.5.4", "title": "Static Analysis"})
    assert metadata["provider"] == "mobsf"
    assert metadata["provider_version"] == "v4.5.4"


def test_mobsf_normalizes_security_observations():
    adapter = MobSFAdapter({})
    raw = {
        "trackers": {"trackers": [{"name": "ExampleTracker", "url": "https://tracker.test"}]},
        "urls": [{"url": "https://api.test"}],
        "permissions": {"android.permission.READ_CONTACTS": {"status": "dangerous"}},
        "exported_activities": ["com.example.MainActivity"],
    }
    events = adapter.normalize_events(raw)
    types = {event["event_type"] for event in events}
    assert "static_tracker" in types
    assert "static_url" in types
    assert "security_observation" in types
