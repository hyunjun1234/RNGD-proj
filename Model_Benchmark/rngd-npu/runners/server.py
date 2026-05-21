"""furiosa-llm serve 라이프사이클 관리 (Furiosa RNGD NPU).

`furiosa-llm serve`로 OpenAI 호환 API 서버를 띄우고, /v1/models 로 모델 id 일치까지
대기, stop()으로 정리. 컨텍스트 매니저로 사용 권장.

bench-gpu의 VllmServer와 동등한 인터페이스 — 측정 러너(tps/sweep/swebench/embed)는
OpenAI 호환 API 위에서 동작하므로 서버 계층만 바꾸면 그대로 돈다.
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
        startup_timeout: float = 1200.0,
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

    @property
    def models_url(self) -> str:
        return f"{self.base_url}/models"

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
        self._ensure_port_free()
        cmd = self._build_cmd()
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_fh = open(self.log_path, "w")
            stdout = stderr = self._log_fh
        else:
            stdout = stderr = subprocess.DEVNULL
        env = {**os.environ}
        self._proc = subprocess.Popen(
            cmd, stdout=stdout, stderr=stderr, start_new_session=True, env=env,
        )
        try:
            self._wait_ready()
        except Exception:
            self.stop()
            raise

    def _served_model_ids(self) -> list[str]:
        r = httpx.get(self.models_url, timeout=5.0)
        r.raise_for_status()
        data = r.json().get("data") or []
        ids: list[str] = []
        for item in data:
            for key in ("id", "root"):
                value = item.get(key)
                if value and value not in ids:
                    ids.append(value)
        return ids

    def _ensure_port_free(self) -> None:
        try:
            r = httpx.get(self.models_url, timeout=1.0)
        except Exception:
            return
        if r.status_code != 200:
            return
        try:
            ids = self._served_model_ids()
        except Exception:
            ids = []
        detail = f" serving {ids}" if ids else ""
        raise RuntimeError(
            f"{self.models_url} is already occupied{detail}. "
            "Stop the existing furiosa-llm server or use a different --port."
        )

    def _wait_ready(self) -> None:
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"furiosa-llm server exited prematurely with code {self._proc.returncode}. "
                    f"check log: {self.log_path}"
                )
            try:
                r = httpx.get(self.models_url, timeout=3.0)
                if r.status_code == 200:
                    ids = self._served_model_ids()
                    if self.model in ids:
                        return
                    if ids:
                        raise RuntimeError(
                            f"server is ready but serves {ids}, expected {self.model}. "
                            f"check log: {self.log_path}"
                        )
            except RuntimeError:
                raise
            except Exception:
                pass
            time.sleep(3.0)
        self.stop()
        raise TimeoutError(f"furiosa-llm server didn't become ready within {self.startup_timeout}s")

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            try:
                self._proc.wait(timeout=40)
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
