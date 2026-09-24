from app.engine.base import CancelToken
from app.engine.errors import AdapterError, should_retry


def test_live_cancel_token():
    state = {"cancelled": False}
    token = CancelToken(lambda: state["cancelled"])
    assert not token.is_cancelled()
    state["cancelled"] = True
    assert token.is_cancelled()


def test_retry_policy():
    assert not should_retry("ENGINE_AUTH_FAILED", "mobsf", "mobsf_uploading", 1, 4)
    assert should_retry("SCAN_START_FAILED", "mobsf", "mobsf_scan_starting", 1, 4)
    assert not should_retry("SCAN_START_FAILED", "mobsf", "mobsf_scan_starting", 4, 4)


def test_structured_error():
    error = AdapterError("FILE_TOO_LARGE", "APK 文件过大", provider_status=413)
    assert error.as_dict()["provider_status"] == 413
