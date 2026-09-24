from types import SimpleNamespace
from app.services.execution_retry import can_retry_execution


def test_retry_policy_only_allows_terminal_execution():
    assert can_retry_execution(SimpleNamespace(status="failed", retryable=True))
    assert not can_retry_execution(SimpleNamespace(status="completed", retryable=False))
    assert not can_retry_execution(SimpleNamespace(status="failed", retryable=False))
