from __future__ import annotations

import sys
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
BACKEND_URL = "http://192.168.4.230:5001"
LOCATE_TRANSPORT = "socket"  # "socket" or "udp"
TSS_HOST = "192.168.4.230"
TSS_PORT = 14141


# -----------------------------
# Orchestration
# -----------------------------
def main() -> None:
    use_udp = LOCATE_TRANSPORT.lower() == "udp"
    backend = None
    alert_runner = None
    aia_runner = None

    if not use_udp:
        backend = backend_bridge.connect(BACKEND_URL)

        def handle_alert(alert: dict) -> None:
            recommendation = aia.recommend_procedure(alert)
            if recommendation is not None:
                alert = {**alert, "procedure": recommendation}
            backend_bridge.send_alert(backend, alert)

        alert_runner = alerts.start(
            {"backend_url": BACKEND_URL},
            handle_alert,
        )
        aia_runner = aia.start({"backend_url": BACKEND_URL})

    locate_runner = locate.start(
        {
            "mode": LOCATE_TRANSPORT,
            "backend_url": BACKEND_URL,
            "tss_host": TSS_HOST,
            "tss_port": TSS_PORT,
        },
        on_path_update=None if use_udp else lambda update: backend_bridge.send_matrix(backend, update["matrix"]),
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
