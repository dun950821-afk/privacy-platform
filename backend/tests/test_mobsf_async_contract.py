import os
from app.engine.adapters.mobsf import MobSFAdapter


def test_async_preference_comes_from_config():
    adapter = MobSFAdapter({"prefer_async": True})
    assert adapter.prefer_async is True


def test_sync_is_default_fallback():
    adapter = MobSFAdapter({})
    assert adapter.prefer_async is False
