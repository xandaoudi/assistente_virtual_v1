import socket
import subprocess
import sys
import time

import httpx
import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_up(base_url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: httpx.HTTPError | None = None
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base_url}/health", timeout=1)
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(0.2)
        else:
            return
    raise TimeoutError("aplicação não respondeu a tempo") from last_error


@pytest.mark.e2e
def test_aplicacao_sobe_e_responde_nas_duas_rotas() -> None:
    port = _free_port()
    process = subprocess.Popen(  # noqa: S603 — comando fixo, sem entrada externa
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--port",
            str(port),
            "--loop",
            "app.core.asyncio_loop:loop_factory",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        _wait_until_up(base_url)

        health_response = httpx.get(f"{base_url}/health", timeout=5)
        ready_response = httpx.get(f"{base_url}/health/ready", timeout=5)

        assert health_response.status_code == 200
        assert ready_response.status_code == 200
    finally:
        process.terminate()
        process.wait(timeout=10)
