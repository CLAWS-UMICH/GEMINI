from __future__ import annotations

import importlib
import sys
import threading
import time
import types

import pytest


def _build_fake_modules(
    *,
    wait_for_dust,
    open_rover_socket,
    drive_to_last_known_ltv,
    run_ltv_trilateration_search=None,
):
    fake_rover_control = types.SimpleNamespace(
        close_rover_socket=lambda *a, **kw: None,
        configure_remote_server=lambda *a, **kw: None,
        open_rover_socket=open_rover_socket,
        set_lights=lambda *a, **kw: None,
        wait_for_dust=wait_for_dust,
        SERVER_HOST="0.0.0.0",
        SERVER_PORT=14141,
    )
    # Minimal PingBudget stand-in so service.py can import it and the post-run
    # log line ("budget at end: ... left ...") can read its attributes.
    class _FakeBudget:
        def __init__(self, *, remaining=10, total=10):
            self.remaining = remaining
            self.total = total
            self.successful_pings = 0
            self.rejected_pings = 0

    fake_dumblocate = types.SimpleNamespace(
        PING_BUDGET_TOTAL=10,
        PingBudget=_FakeBudget,
        drive_to_last_known_ltv=drive_to_last_known_ltv,
        run_ltv_trilateration_search=(
            run_ltv_trilateration_search
            if run_ltv_trilateration_search is not None
            else (lambda *a, **kw: (
                types.SimpleNamespace(aborted=False), None, True, _FakeBudget(), True
            ))
        ),
    )
    return fake_rover_control, fake_dumblocate


@pytest.fixture
def make_service(monkeypatch):
    """Return a factory that loads a fresh locate.service with stubbed deps."""

    def factory(
        *,
        wait_for_dust,
        open_rover_socket=lambda *a, **kw: object(),
        drive_to_last_known_ltv=None,
        run_ltv_trilateration_search=None,
        backoff_initial=0.01,
        backoff_max=0.05,
        last_known_hold_sec=0.0,
    ):
        if drive_to_last_known_ltv is None:
            drive_to_last_known_ltv = lambda *a, **kw: (
                types.SimpleNamespace(aborted=False),
                (0.0, 0.0),
                (0.0, 0.0),
            )
        fake_rover_control, fake_dumblocate = _build_fake_modules(
            wait_for_dust=wait_for_dust,
            open_rover_socket=open_rover_socket,
            drive_to_last_known_ltv=drive_to_last_known_ltv,
            run_ltv_trilateration_search=run_ltv_trilateration_search,
        )

        monkeypatch.setitem(sys.modules, "rover_control", fake_rover_control)
        monkeypatch.setitem(sys.modules, "dumblocate", fake_dumblocate)

        sys.modules.pop("locate.service", None)
        sys.modules.pop("locate", None)
        from locate import service as _service

        importlib.reload(_service)
        # Fast retries in tests; production defaults stay long.
        monkeypatch.setattr(_service, "BACKOFF_INITIAL_SEC", backoff_initial, raising=False)
        monkeypatch.setattr(_service, "BACKOFF_MAX_SEC", backoff_max, raising=False)
        # Skip the post-arrival hold so resilience tests don't take 30s each.
        monkeypatch.setattr(_service, "LAST_KNOWN_HOLD_SEC", last_known_hold_sec, raising=False)
        return _service

    return factory


def _drain(runner, timeout: float = 1.0) -> None:
    runner.stop()
    runner.join(timeout=timeout)


def test_dust_disconnect_keeps_thread_alive_and_retries(make_service):
    """If wait_for_dust keeps returning False, the locate thread must NOT exit.
    It should keep retrying so the controller stays up when DUST/TSS is down."""
    call_count = {"n": 0}

    def fake_wait_for_dust(sock, timeout_seconds=20.0, poll_seconds=0.5):
        call_count["n"] += 1
        return False  # DUST never connects

    service = make_service(wait_for_dust=fake_wait_for_dust)
    runner = service.start({"mode": "udp", "backend_url": "x", "tss_host": "h", "tss_port": 1})
    try:
        # Wait until we see at least 3 retries; if the thread died, we'd be stuck at 1.
        deadline = time.monotonic() + 2.0
        while call_count["n"] < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert call_count["n"] >= 3, f"thread stopped retrying after {call_count['n']} attempts"
        assert runner.is_alive(), "locate thread died on DUST disconnect"
    finally:
        _drain(runner)


def test_drive_runtime_error_does_not_kill_thread(make_service):
    """A RuntimeError raised by drive_to_last_known_ltv (telemetry stale, rover stuck, etc.)
    must trigger a retry instead of killing the thread."""
    state = {"calls": 0}

    def flaky_drive(*a, **kw):
        state["calls"] += 1
        if state["calls"] < 3:
            raise RuntimeError("ROVER.json did not contain pr_telemetry")
        return (types.SimpleNamespace(aborted=False), (0.0, 0.0), (0.0, 0.0))

    service = make_service(
        wait_for_dust=lambda *a, **kw: True,
        drive_to_last_known_ltv=flaky_drive,
    )
    runner = service.start({"mode": "udp", "backend_url": "x", "tss_host": "h", "tss_port": 1})
    try:
        deadline = time.monotonic() + 2.0
        while state["calls"] < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        # Getting to call #3 (the successful one) proves the thread did not die
        # after the RuntimeError on call #1. After success the thread exits cleanly.
        assert state["calls"] >= 3, f"thread did not retry after RuntimeError; calls={state['calls']}"
    finally:
        _drain(runner)


def test_socket_open_failure_retries(make_service):
    """If open_rover_socket raises an OSError (backend Socket.IO not reachable),
    the locate thread must retry rather than terminate."""
    state = {"calls": 0}

    def flaky_open(*a, **kw):
        state["calls"] += 1
        if state["calls"] < 3:
            raise OSError("Connection refused")
        return object()

    service = make_service(
        wait_for_dust=lambda *a, **kw: True,
        open_rover_socket=flaky_open,
    )
    runner = service.start({"mode": "socket", "backend_url": "http://x", "tss_host": "h", "tss_port": 1})
    try:
        deadline = time.monotonic() + 2.0
        while state["calls"] < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert state["calls"] >= 3, f"thread did not retry after OSError; calls={state['calls']}"
    finally:
        _drain(runner)


def test_stop_unblocks_backoff_promptly(make_service):
    """runner.stop() must wake the backoff sleep so shutdown stays responsive."""

    def fake_wait_for_dust(sock, timeout_seconds=20.0, poll_seconds=0.5):
        return False

    service = make_service(
        wait_for_dust=fake_wait_for_dust,
        backoff_initial=2.0,
        backoff_max=2.0,
    )
    runner = service.start({"mode": "udp", "backend_url": "x", "tss_host": "h", "tss_port": 1})
    # Let it enter the first backoff sleep.
    time.sleep(0.1)
    t0 = time.monotonic()
    runner.stop()
    runner.join(timeout=1.0)
    elapsed = time.monotonic() - t0
    assert not runner.is_alive(), "stop() did not terminate the locate thread"
    assert elapsed < 1.0, f"stop() waited for full backoff ({elapsed:.2f}s); should be near-instant"


def test_retries_use_backoff_not_tight_loop(make_service):
    """Verify retries are spaced by the backoff, not a CPU-burning tight loop."""
    call_count = {"n": 0}

    def fake_wait_for_dust(sock, timeout_seconds=20.0, poll_seconds=0.5):
        call_count["n"] += 1
        return False

    service = make_service(
        wait_for_dust=fake_wait_for_dust,
        backoff_initial=0.05,
        backoff_max=0.05,
    )
    runner = service.start({"mode": "udp", "backend_url": "x", "tss_host": "h", "tss_port": 1})
    try:
        time.sleep(0.3)
        # With 50ms backoff over ~300ms we should see far fewer than a tight-loop count.
        # A tight loop would easily hit hundreds; backoff should keep this in single/low-double digits.
        assert call_count["n"] <= 20, f"retry loop appears tight ({call_count['n']} calls in 300ms)"
        assert call_count["n"] >= 2, "expected at least 2 retries in 300ms with 50ms backoff"
    finally:
        _drain(runner)


def test_recovers_after_simulation_reset(make_service):
    """End-to-end: simulation reset is modeled as wait_for_dust=False for a few cycles
    then True, plus drive succeeding. Thread must survive and complete a successful run."""
    wait_calls = {"n": 0}
    drive_calls = {"n": 0}

    def fake_wait_for_dust(sock, timeout_seconds=20.0, poll_seconds=0.5):
        wait_calls["n"] += 1
        return wait_calls["n"] >= 4  # reset clears after 3 failed checks

    def good_drive(*a, **kw):
        drive_calls["n"] += 1
        return (types.SimpleNamespace(aborted=False), (0.0, 0.0), (0.0, 0.0))

    service = make_service(
        wait_for_dust=fake_wait_for_dust,
        drive_to_last_known_ltv=good_drive,
    )
    runner = service.start({"mode": "udp", "backend_url": "x", "tss_host": "h", "tss_port": 1})
    try:
        deadline = time.monotonic() + 2.0
        while drive_calls["n"] < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        # 3 failed DUST checks then a real drive proves the thread bridged the simulator reset.
        assert drive_calls["n"] >= 1, "controller never recovered after simulated reset"
        assert wait_calls["n"] >= 4, f"expected to retry through reset; wait_calls={wait_calls['n']}"
    finally:
        _drain(runner)


def test_runner_exposes_is_alive(make_service):
    """The runner returned by start() must expose is_alive() so callers can detect
    silent thread death."""
    service = make_service(wait_for_dust=lambda *a, **kw: True)
    runner = service.start({"mode": "udp", "backend_url": "x", "tss_host": "h", "tss_port": 1})
    try:
        assert hasattr(runner, "is_alive")
        assert callable(runner.is_alive)
        assert runner.is_alive() in (True, False)
    finally:
        _drain(runner)
