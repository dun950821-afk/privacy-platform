from app.engine.runners.appshark_executor import AppSharkExecutor


def test_executor_builds_process_command(tmp_path):
    executor = AppSharkExecutor(java_path="/bin/true", jar_path="fake.jar", home_path=str(tmp_path))
    result = executor.run("config.json5", str(tmp_path / "out"), timeout=5)
    assert result.returncode == 0
    assert (tmp_path / "out" / "stdout.log").exists()


def test_executor_rejects_timeout(tmp_path):
    import pytest
    executor = AppSharkExecutor(java_path="/bin/sh", jar_path="", home_path=str(tmp_path), java_opts=["-c", "sleep 5"])
    with pytest.raises(TimeoutError):
        executor.run("", str(tmp_path / "out"), timeout=1)
