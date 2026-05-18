"""furiosa-llm serve 라이프사이클 관리.

start()로 띄우고 healthcheck 통과까지 대기, stop()으로 정리.
컨텍스트 매니저로 사용 권장.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx


class FuriosaServer:
    def __init__(
        self,
        model: str,
        revision: Optional[str] = None,
        devices: str = "npu:0",
        host: str = "0.0.0.0",
        port: int = 8000,
        extra_args: Optional[list[str]] = None,
        log_path: Optional[Path] = None,
        startup_timeout: float = 600.0,
    ):
        self.model = model
        self.revision = revision
        self.devices = devices
        self.host = host
        self.port = port
        self.extra_args = list(extra_args or [])
        self.log_path = log_path
        self.startup_timeout = startup_timeout
        self._proc: Optional[subprocess.Popen] = None
        self._log_fh = None

    @property
    def base_url(self) -> str:
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{host}:{self.port}/v1"

    def _build_cmd(self) -> list[str]:
        cmd = ["furiosa-llm", "serve", self.model]
        if self.revision:
            cmd += ["--revision", self.revision]
        cmd += ["--devices", self.devices, "--host", self.host, "--port", str(self.port)]
        cmd += self.extra_args
        return cmd

    def start(self) -> None:
        if self._proc is not None:
            raise RuntimeError("server already started")
        cmd = self._build_cmd()
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_fh = open(self.log_path, "w")
            stdout = stderr = self._log_fh
        else:
            stdout = stderr = subprocess.DEVNULL
        # start_new_session=True로 자식 프로세스를 별도 프로세스 그룹에 둬서 SIGTERM 일괄 처리
        self._proc = subprocess.Popen(
            cmd,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            env={**os.environ},
        )
        self._wait_ready()

    def _wait_ready(self) -> None:
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"server exited prematurely with code {self._proc.returncode}. "
                    f"check log: {self.log_path}"
                )
            try:
                r = httpx.get(f"{self.base_url}/models", timeout=2.0)
                if r.status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(2.0)
        self.stop()
        raise TimeoutError(f"server didn't become ready within {self.startup_timeout}s")

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            try:
                self._proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
                self._proc.wait(timeout=10)
        except ProcessLookupError:
            pass
        finally:
            if self._log_fh:
                self._log_fh.close()
                self._log_fh = None
            self._proc = None

    def __enter__(self) -> "FuriosaServer":
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
