"""AppShark 独立进程执行器。"""
from dataclasses import dataclass
from pathlib import Path
import os
import signal
import subprocess
import time


@dataclass
class ProcessResult:
    returncode: int
    stdout_path: str
    stderr_path: str
    duration_ms: int


class AppSharkExecutor:
    def __init__(self, java_path="java", jar_path="", home_path="/tmp", java_opts=None):
        self.java_path = java_path
        self.jar_path = jar_path
        self.home_path = home_path
        self.java_opts = java_opts or []
        self.process: subprocess.Popen | None = None

    def run(self, config_path: str, out_dir: str, timeout: int = 1800) -> ProcessResult:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stdout_path, stderr_path = out / "stdout.log", out / "stderr.log"
        start = time.monotonic()
        with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
            self.process = subprocess.Popen(
                [self.java_path, *self.java_opts, "-jar", self.jar_path, config_path],
                cwd=self.home_path, stdout=stdout, stderr=stderr,
                start_new_session=True,
            )
            try:
                code = self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.cancel()
                raise TimeoutError("AppShark process timeout")
        return ProcessResult(code, str(stdout_path), str(stderr_path), int((time.monotonic() - start) * 1000))

    def cancel(self) -> bool:
        if not self.process or self.process.poll() is not None:
            return True
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
            return True
        except ProcessLookupError:
            return True
