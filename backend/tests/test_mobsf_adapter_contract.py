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


def test_raw_sections_cover_sections_that_have_no_event_mapping():
    """MobSF 的 53 个段落里只有 4 个有事件映射，其余原本等于不存在。

    这里挑几个从未被提取、但明显有后续价值的段落，锁住它们能被拆出来。
    """
    from app.services.raw_section_service import split_sections

    raw = {
        "appsec": {"security_score": 47, "high": [{"title": "x"}], "warning": []},
        "manifest_analysis": {"manifest_findings": [{"rule": "vulnerable_os_version"}],
                              "manifest_summary": {}},
        "secrets": ["Private key: -----BEGIN EC PRIVATE KEY-----"],
        "sbom": {"sbom_versioned": ["androidx.appcompat:appcompat@1.0.0"], "sbom_packages": []},
        "certificate_analysis": {"certificate_info": "Binary is signed\nv1 signature: True"},
        "trackers": {"detected_trackers": 0, "total_trackers": 432, "trackers": []},
    }
    rows = {s["path"]: s for s in split_sections(raw)}
    for want in ("appsec.high", "manifest_analysis.manifest_findings", "secrets",
                 "sbom.sbom_versioned", "certificate_analysis", "trackers.trackers"):
        assert want in rows, f"{want} 没被拆出来——这一段又会变成『不存在』"
    # 标量随父行：security_score / certificate_info 分别在各自父行的 payload 里
    assert rows["appsec"]["payload"]["security_score"] == 47
    assert "Binary is signed" in rows["certificate_analysis"]["payload"]["certificate_info"]
