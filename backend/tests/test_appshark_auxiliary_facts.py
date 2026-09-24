from app.engine.adapters.appshark import AppSharkAdapter


def test_auxiliary_events_extract_facts():
    events = AppSharkAdapter._auxiliary_events({
        "UsePermissions": ["android.permission.INTERNET"],
        "HTTP_API": ["https://api.example.com"],
        "DeepLinkInfo": ["demo://open"],
        "JsBridgeInfo": ["JSBridge"],
    })
    types = {e["event_type"] for e in events}
    assert "static_permission" in types
    assert "static_url" in types
    assert "static_deeplink" in types
    assert "security_observation" in types


def test_auxiliary_events_handle_missing_sections():
    assert AppSharkAdapter._auxiliary_events({}) == []
