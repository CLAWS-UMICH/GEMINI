from __future__ import annotations

import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

CONTROLFILES_DIR = Path(__file__).resolve().parents[1] / "controlfiles"
if str(CONTROLFILES_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLFILES_DIR))

import rover_control
from dumblocate import STOP_AT_LAST_KNOWN_ONLY, drive_to_last_known_ltv, run_ltv_trilateration_search
from rover_control import close_rover_socket, configure_remote_server, open_rover_socket, set_lights, wait_for_dust


# Retry/backoff for transient DUST/TSS/backend failures. Long enough not to spam
# the simulator while it resets, short enough that recovery feels responsive.
BACKOFF_INITIAL_SEC = 1.0
BACKOFF_MAX_SEC = 30.0
BACKOFF_FACTOR = 2.0
WAIT_FOR_DUST_TIMEOUT_SEC = 20.0
WAIT_FOR_DUST_POLL_SEC = 0.5

# Exceptions we treat as transient simulator/backend issues. Other exceptions
# (TypeError, ValueError from bad config, etc.) still get logged loudly so
# programmer errors stay visible, but the thread keeps the controller alive.
_RECOVERABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    RuntimeError,
    OSError,
    ConnectionError,
    socket.timeout,
)


# -----------------------------
# Locate runner
# -----------------------------
def start(connection: dict, on_path_update=None, on_eta_update=None):
    state: dict = {"sock": None}
    stop_event = threading.Event()
    thread = threading.Thread(
        target=run,
        args=(connection, state, on_path_update, on_eta_update, stop_event),
        name="locate",
        daemon=True,
    )
    thread.start()

    def _stop() -> None:
        stop_event.set()
        close_socket(state)

    return SimpleNamespace(
        join=thread.join,
        stop=_stop,
        is_alive=thread.is_alive,
        stop_event=stop_event,
    )


def run(
    connection: dict,
    state: dict,
    on_path_update,
    on_eta_update,
    stop_event: threading.Event | None = None,
) -> None:
    if stop_event is None:
        stop_event = threading.Event()
    run_start_wall = time.time()
    print(f"AI controller locate start: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(run_start_wall))}")

    backoff = BACKOFF_INITIAL_SEC
    while not stop_event.is_set():
        try:
            completed = _run_once(connection, state, on_path_update, on_eta_update, stop_event)
        except KeyboardInterrupt:
            break
        except _RECOVERABLE_EXCEPTIONS as exc:
            print(
                f"Locate: waiting for DUST/TSS/backend to recover "
                f"({type(exc).__name__}: {exc}); retrying in {backoff:.1f}s.",
                file=sys.stderr,
            )
            close_socket(state)
            if stop_event.wait(backoff):
                break
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_SEC)
            continue
        except Exception:
            print(
                f"Locate: unexpected exception; retrying in {backoff:.1f}s.",
                file=sys.stderr,
            )
            traceback.print_exc()
            close_socket(state)
            if stop_event.wait(backoff):
                break
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_SEC)
            continue

        close_socket(state)
        if completed:
            return
        backoff = BACKOFF_INITIAL_SEC

    close_socket(state)


def _run_once(
    connection: dict,
    state: dict,
    on_path_update,
    on_eta_update,
    stop_event: threading.Event,
) -> bool:
    """Run one full locate cycle. Returns True on successful completion, False if
    aborted/stopped. Raises on transient failures so run() can back off and retry."""
    run_start_monotonic = time.monotonic()

    configure_transport(connection)
    state["sock"] = open_rover_socket()
    sock = state["sock"]

    if not wait_for_dust(
        sock,
        timeout_seconds=WAIT_FOR_DUST_TIMEOUT_SEC,
        poll_seconds=WAIT_FOR_DUST_POLL_SEC,
    ):
        raise RuntimeError("DUST is not connected to TSS.")

    if stop_event.is_set():
        return False

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

    if run_state.aborted:
        return False
    if STOP_AT_LAST_KNOWN_ONLY:
        return True

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

    return search_completed and not run_state.aborted


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
        try:
            close_rover_socket(state["sock"])
        except Exception:
            pass
        state["sock"] = None
