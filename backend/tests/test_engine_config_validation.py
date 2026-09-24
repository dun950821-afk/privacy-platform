import pytest

from app.services.engine_config import validate_config, _coerce_number


def test_validate_accepts_numeric_string_timeouts():
    """HTML number controls may reach the API as numeric strings."""
    validate_config("mobsf", {
        "url": "http://127.0.0.1:8001",
        "connect_timeout": "10",
        "scan_timeout": "3000",
    })


def test_validate_rejects_negative_or_non_numeric():
    with pytest.raises(ValueError):
        validate_config("mobsf", {
            "url": "http://127.0.0.1:8001",
            "connect_timeout": "10",
            "scan_timeout": "-5",
        })
    with pytest.raises(ValueError):
        validate_config("mobsf", {
            "url": "http://127.0.0.1:8001",
            "connect_timeout": "10",
            "scan_timeout": "abc",
        })


def test_coerce_number_converts_numeric_string():
    assert _coerce_number("3000") == 3000
    assert _coerce_number("10") == 10
    assert _coerce_number(3000) == 3000
    assert _coerce_number("abc") == "abc"
