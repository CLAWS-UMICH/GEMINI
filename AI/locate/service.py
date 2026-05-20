from __future__ import annotations

from types import SimpleNamespace
import sys
import threading
import time
from pathlib import Path

CONTROLFILES_DIR = Path(__file__).resolve().parents[1] / "controlfiles"
if str(CONTROLFILES_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLFILES_DIR))

import rover_control
from dumblocate import STOP_AT_LAST_KNOWN_ONLY, drive_to_last_known_ltv, run_ltv_trilateration_search
from rover_control import close_rover_socket, configure_remote_server, open_rover_socket, set_lights, wait_for_dust


# -----------------------------
# Locate runner
# -----------------------------
def start(connection: dict, on_path_update=None, on_eta_update=None):
    state = {"sock": None}
    thread = threading.Thread(
        target=run,
        args=(connection, state, on_path_update, on_eta_update),
        name="locate",
        daemon=True,
    )
    thread.start()
    return SimpleNamespace(
        join=thread.join,
        stop=lambda: close_socket(state),
    )


def run(connection: dict, state: dict, on_path_update, on_eta_update) -> None:
    import sys as _sys
    run_start_wall = time.time()
    run_start_monotonic = time.monotonic()
    print(f"AI controller locate start: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(run_start_wall))}")

    try:
        configure_transport(connection)
        state["sock"] = open_rover_socket()
        sock = state["sock"]

        if not wait_for_dust(sock, timeout_seconds=20.0, poll_seconds=0.5):
            raise RuntimeError("DUST is not connected to TSS.")

        def on_telemetry(*, raw_telemetry: dict, goal_distance_cm: float, **_ignored) -> None:
            if on_eta_update is None:
                return
            speed_mps = abs(float(raw_telemetry.get("speed", 0.0)))
            on_eta_update(None if speed_mps == 0.0 else goal_distance_cm / (speed_mps * 100.0))

        set_lights(sock, True)
        run_state, goal_xy, _last_known_xy_m = drive_to_last_known_ltv(
            sock,
            viewer=None,
            telemetry_callback=on_telemetry,
            path_callback=on_path_update,
            debug_logger=None,
            debug_mode="dumblocate_drive_last_known",
        )

        if run_state.aborted or STOP_AT_LAST_KNOWN_ONLY:
            return

        run_state, _viewer, ltv_found, _remaining_ping_budget, search_completed = run_ltv_trilateration_search(
            sock,
            run_state=run_state,
            anchor_xy=goal_xy,
            viewer=None,
            telemetry_callback=on_telemetry,
            path_callback=on_path_update,
            debug_logger=None,
            hold_verify_debug_mode="dumblocate_hold_verify_estimate",
        )

        if search_completed and not run_state.aborted and ltv_found:
            elapsed_sec = time.monotonic() - run_start_monotonic
            print(
                f"Reached LTV in {elapsed_sec:.1f}s "
                f"({elapsed_sec / 60.0:.2f} min)"
            )

    except Exception as exc:
        print(
            f"Locate thread failed with unhandled exception: {exc!r}",
            file=_sys.stderr,
        )
    finally:
        close_socket(state)


# -----------------------------
# Transport
# -----------------------------
def configure_transport(connection: dict) -> None:
    if connection["mode"] == "udp":
        rover_control.SERVER_HOST = connection["tss_host"]
        rover_control.SERVER_PORT = int(connection["tss_port"])
        configure_remote_server(False, None)
    else:
        configure_remote_server(True, connection["backend_url"])


def close_socket(state: dict) -> None:
    if state["sock"] is not None:
        close_rover_socket(state["sock"])
        state["sock"] = None
