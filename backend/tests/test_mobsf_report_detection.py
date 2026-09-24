from app.engine.adapters.mobsf import MobSFAdapter


def test_complete_report_is_recognized():
    assert MobSFAdapter.looks_like_report({
        "app_name": "Demo", "package_name": "com.demo", "title": "Static Analysis",
        "version": "v4.5.4", "md5": "abc",
    })


def test_scan_acknowledgement_is_not_a_report():
    # 异步模式下 /scan 可能只返回排队确认，不能当成扫描完成
    assert not MobSFAdapter.looks_like_report({"status": "queued", "hash": "abc"})
    assert not MobSFAdapter.looks_like_report({})
    assert not MobSFAdapter.looks_like_report(None)


def test_partial_report_is_rejected():
    assert not MobSFAdapter.looks_like_report({"app_name": "Demo"})
