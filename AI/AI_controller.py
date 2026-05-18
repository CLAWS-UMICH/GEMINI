from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

CONTROLFILES_DIR = Path(__file__).with_name("controlfiles")
if str(CONTROLFILES_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLFILES_DIR))

import alerts
import aia
import locate
import backend_bridge


# -----------------------------
# Config
# -----------------------------
BACKEND_URL = "http://127.0.0.1:5001"
LOCATE_TRANSPORT = "socket"  # "socket" or "udp"
TSS_HOST = "192.168.4.231"
TSS_PORT = 14141


@dataclass(frozen=True)
class ControllerConfig:
    transport: str
    remote_enabled: bool
    backend_url: str
    tss_host: str
    tss_port: int


def load_controller_config(environ: dict[str, str] | None = None) -> ControllerConfig:
    env = os.environ if environ is None else environ
    transport = str(env.get("AI_CONTROLLER_TRANSPORT", LOCATE_TRANSPORT)).strip().lower()
    backend_url = str(env.get("AI_CONTROLLER_BACKEND_URL", BACKEND_URL)).strip()
    tss_host = str(env.get("AI_CONTROLLER_TSS_HOST", TSS_HOST)).strip()
    try:
        tss_port = int(env.get("AI_CONTROLLER_TSS_PORT", str(TSS_PORT)))
    except (TypeError, ValueError):
        tss_port = TSS_PORT

    return ControllerConfig(
        transport=transport,
        remote_enabled=transport in ("socket", "backend", "remote"),
        backend_url=backend_url,
        tss_host=tss_host,
        tss_port=tss_port,
    )


def describe_controller_config(config: ControllerConfig) -> str:
    if config.remote_enabled:
        return f"AI controller transport: backend Socket.IO at {config.backend_url}"
    return f"AI controller transport: direct TSS UDP at {config.tss_host}:{config.tss_port}"


# -----------------------------
# Orchestration
# -----------------------------
def main() -> None:
    config = load_controller_config()
    print(describe_controller_config(config))
    backend = None
    alert_runner = None
    aia_runner = None

    if config.remote_enabled:
        backend = backend_bridge.connect(config.backend_url)

        def handle_alert(alert: dict) -> None:
            recommendation = aia.recommend_procedure(alert)
            if recommendation is not None:
                alert = {**alert, "procedure": recommendation}
            backend_bridge.send_alert(backend, alert)

        alert_runner = alerts.start(
            {"backend_url": config.backend_url},
            handle_alert,
        )
        aia_runner = aia.start({"backend_url": config.backend_url})

    locate_runner = locate.start(
        {
            "mode": config.transport,
            "backend_url": config.backend_url,
            "tss_host": config.tss_host,
            "tss_port": config.tss_port,
        },
        on_path_update=None if backend is None else lambda update: backend_bridge.send_matrix(backend, update["matrix"]),
        on_eta_update=None if alert_runner is None else alert_runner.update_path_eta,
    )

    try:
        locate_runner.join()
    except KeyboardInterrupt:
        pass
    finally:
        locate_runner.stop()
        if alert_runner is not None:
            alert_runner.stop()
        if aia_runner is not None:
            aia_runner.stop()
        if backend is not None:
            backend.disconnect()


if __name__ == "__main__":
    main()
