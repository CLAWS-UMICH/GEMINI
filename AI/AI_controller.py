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
BACKEND_URL = "http://127.0.0.1:5001"
LOCATE_TRANSPORT = "udp"  # "socket" or "udp"
TSS_HOST = "172.24.119.191"
TSS_PORT = 14141


# -----------------------------
# Orchestration
# -----------------------------
def main() -> None:
    backend = backend_bridge.connect(BACKEND_URL)
    alert_runner = alerts.start(
        {"backend_url": BACKEND_URL},
        lambda alert: backend_bridge.send_alert(backend, alert),
    )
    aia_runner = aia.start({"backend_url": BACKEND_URL})
    locate_runner = locate.start(
        {
            "mode": LOCATE_TRANSPORT,
            "backend_url": BACKEND_URL,
            "tss_host": TSS_HOST,
            "tss_port": TSS_PORT,
        },
        on_path_update=lambda update: backend_bridge.send_matrix(backend, update["matrix"]),
        on_eta_update=alert_runner.update_path_eta,
    )

    try:
        locate_runner.join()
    except KeyboardInterrupt:
        pass
    finally:
        locate_runner.stop()
        alert_runner.stop()
        aia_runner.stop()
        backend.disconnect()


if __name__ == "__main__":
    main()
