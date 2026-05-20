"""Tests for the centralized ping budget + decision logic in dumblocate.

These exercise the determinstic, I/O-free pieces (PingBudget, should_ping,
coordinate inverse) and the ACK-aware request_ping wrapper with all
external deps stubbed.
"""
from __future__ import annotations

import importlib
import math
import sys
import time
import types
import unittest
from pathlib import Path

CONTROLFILES_DIR = Path(__file__).resolve().parents[1] / "controlfiles"
if str(CONTROLFILES_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLFILES_DIR))


def import_dumblocate(
    *,
    pose_units_to_cm: float = 100.0,
    pose_offset_x_cm: float = 0.0,
    pose_offset_y_cm: float = 0.0,
):
    """Import dumblocate with external deps stubbed. Returns the fresh module."""
    sys.modules.pop("dumblocate", None)

    fake_dumbdrive = types.SimpleNamespace(
        FrontendTimingLogger=object,
        REMOTE_SERVER=False,
        REMOTE_SERVER_URL="http://localhost:5001",
        drive_to_goal=lambda *a, **kw: None,
        hold_with_ui_updates=lambda *a, **kw: True,
        make_sanitized_telemetry=lambda t: t,
    )
    fake_main = types.SimpleNamespace(
        POSE_OFFSET_X_CM=pose_offset_x_cm,
        POSE_OFFSET_Y_CM=pose_offset_y_cm,
        POSE_UNITS_TO_CM=pose_units_to_cm,
        MapWindow=object,
        parse_pose=lambda t: (0.0, 0.0, 0.0, 0.0),
        stop_rover=lambda *a, **kw: None,
    )
    fake_rover_control = types.SimpleNamespace(
        close_rover_socket=lambda *a, **kw: None,
        configure_remote_server=lambda *a, **kw: None,
        fetch_ltv_json=lambda *a, **kw: {},
        fetch_rover_json=lambda *a, **kw: {"pr_telemetry": {}},
        open_rover_socket=lambda *a, **kw: None,
        send_float_command=lambda *a, **kw: True,
        set_brakes=lambda *a, **kw: None,
        set_lights=lambda *a, **kw: None,
        set_steering=lambda *a, **kw: None,
        set_throttle=lambda *a, **kw: None,
        wait_for_dust=lambda *a, **kw: True,
    )
    sys.modules["dumbdrive"] = fake_dumbdrive
    sys.modules["main"] = fake_main
    sys.modules["rover_control"] = fake_rover_control
    return importlib.import_module("dumblocate")


class TestPingBudgetHardCap(unittest.TestCase):
    def test_hard_cap_is_ten(self):
        dumblocate = import_dumblocate()
        self.assertEqual(dumblocate.PING_BUDGET_TOTAL, 10)
        budget = dumblocate.PingBudget(
            remaining=dumblocate.PING_BUDGET_TOTAL,
            total=dumblocate.PING_BUDGET_TOTAL,
        )
        self.assertEqual(budget.remaining, 10)
        self.assertEqual(budget.total, 10)

    def test_consume_eleven_times_raises_on_eleventh(self):
        """Hard cap: the 11th consume must raise. Cannot exceed 10."""
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(remaining=10, total=10)
        for i in range(10):
            budget.consume_fresh(
                strength=-50.0 - i, rover_x_m=0.0, rover_y_m=0.0, sentinel=False
            )
        self.assertEqual(budget.remaining, 0)
        self.assertEqual(budget.successful_pings, 10)
        with self.assertRaises(RuntimeError):
            budget.consume_fresh(
                strength=-60.0, rover_x_m=0.0, rover_y_m=0.0, sentinel=False
            )

    def test_can_spend_false_when_remaining_zero(self):
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(remaining=0, total=10)
        self.assertFalse(budget.can_spend(1))
        self.assertTrue(dumblocate.PingBudget(remaining=1, total=10).can_spend(1))

    def test_rejected_does_not_consume(self):
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(remaining=10, total=10)
        for _ in range(5):
            budget.record_rejected()
        self.assertEqual(budget.remaining, 10)
        self.assertEqual(budget.rejected_pings, 5)
        self.assertEqual(budget.successful_pings, 0)


def _make_ltv_json(*, ping_requested: int, strength: float) -> dict:
    """Shape that mirrors what the real LTV.json fetch returns."""
    return {
        "location": {"last_known_x": 0.0, "last_known_y": 0.0},
        "signal": {
            "strength": strength,
            "ping_requested": ping_requested,
            "ping_unlimited_requested": 0,
        },
    }


def _install_fetch_ltv_sequence(dumblocate, sequence: list[dict]) -> dict:
    """Replace fetch_ltv_json with one that yields each entry in `sequence`
    on successive calls, then sticks on the last entry. Returns a dict whose
    'n' key counts calls — useful for tightness assertions."""
    state = {"n": 0}
    seq = list(sequence)

    def fake_fetch(_sock):
        idx = min(state["n"], len(seq) - 1)
        state["n"] += 1
        return seq[idx]

    dumblocate.fetch_ltv_json = fake_fetch
    return state


class TestRequestPingAckHandling(unittest.TestCase):
    def test_ack_false_returns_rejected_without_polling(self):
        """server.c:212 cooldown reject path. Client snapshots LTV once for
        baseline but performs no post-ACK polling."""
        dumblocate = import_dumblocate()

        call_counter = _install_fetch_ltv_sequence(
            dumblocate,
            [_make_ltv_json(ping_requested=1, strength=-42.0)],
        )
        dumblocate.send_float_command = lambda sock, command, value: False

        budget = dumblocate.PingBudget(remaining=10, total=10)
        t0 = time.monotonic()
        result = dumblocate.request_ping(
            sock=None, rover_x_m=0.0, rover_y_m=0.0, budget=budget
        )
        elapsed = time.monotonic() - t0
        self.assertTrue(result.rejected)
        self.assertFalse(result.fresh)
        self.assertEqual(budget.remaining, 10)
        self.assertEqual(budget.rejected_pings, 1)
        self.assertAlmostEqual(result.strength, -42.0)
        # One read (pre-fire snapshot). No polling loop after ACK=false.
        self.assertEqual(call_counter["n"], 1)
        self.assertLess(elapsed, 0.5, f"rejected ping took {elapsed:.2f}s; should be near-instant")

    def test_runtime_error_returns_rejected_not_propagated(self):
        dumblocate = import_dumblocate()
        _install_fetch_ltv_sequence(
            dumblocate,
            [_make_ltv_json(ping_requested=0, strength=-50.0)],
        )

        def boom(sock, command, value):
            raise RuntimeError("socket dead")

        dumblocate.send_float_command = boom

        budget = dumblocate.PingBudget(remaining=10, total=10)
        result = dumblocate.request_ping(
            sock=None, rover_x_m=0.0, rover_y_m=0.0, budget=budget
        )
        self.assertTrue(result.rejected)
        self.assertEqual(budget.remaining, 10)

    def test_ack_true_no_evidence_is_not_fresh(self):
        """ACK=true but ping_requested never clears AND strength never changes
        from the pre-fire snapshot — no proof the server fired. Must NOT
        consume budget, must NOT advance the server-cooldown mirror."""
        dumblocate = import_dumblocate()
        dumblocate.PING_ACK_OBSERVE_TIMEOUT_SEC = 0.1
        dumblocate.PING_RESPONSE_POLL_SEC = 0.01

        _install_fetch_ltv_sequence(
            dumblocate,
            [_make_ltv_json(ping_requested=1, strength=-55.0)],
        )
        dumblocate.send_float_command = lambda sock, command, value: True

        budget = dumblocate.PingBudget(remaining=10, total=10)
        result = dumblocate.request_ping(
            sock=None, rover_x_m=0.0, rover_y_m=0.0, budget=budget
        )
        self.assertFalse(result.fresh)
        self.assertFalse(result.rejected)
        self.assertFalse(result.sentinel)
        self.assertEqual(budget.remaining, 10)
        self.assertEqual(budget.successful_pings, 0)
        self.assertIsNone(budget.last_ack_monotonic)

    def test_flag_transition_alone_is_enough(self):
        """ping_requested transitions 1 -> 0 even though strength stays
        identical. The flag clear is authoritative; the ping is fresh and
        budget is consumed. Covers the first-ping case (no meaningful prior
        strength) and the legitimate-identical-strength case."""
        dumblocate = import_dumblocate()
        dumblocate.PING_ACK_OBSERVE_TIMEOUT_SEC = 0.5
        dumblocate.PING_STRENGTH_TRAIL_TIMEOUT_SEC = 0.05
        dumblocate.PING_RESPONSE_POLL_SEC = 0.01

        _install_fetch_ltv_sequence(
            dumblocate,
            [
                _make_ltv_json(ping_requested=1, strength=-55.0),  # pre-fire snapshot
                _make_ltv_json(ping_requested=0, strength=-55.0),  # post-forward, no strength change
            ],
        )
        dumblocate.send_float_command = lambda sock, command, value: True

        budget = dumblocate.PingBudget(remaining=10, total=10)
        result = dumblocate.request_ping(
            sock=None, rover_x_m=1.0, rover_y_m=2.0, budget=budget
        )
        self.assertTrue(result.fresh)
        self.assertAlmostEqual(result.strength, -55.0)
        self.assertEqual(budget.remaining, 9)
        self.assertEqual(budget.successful_pings, 1)
        self.assertIsNotNone(budget.last_ack_monotonic)

    def test_strength_change_alone_is_enough(self):
        """signal.strength changes from the pre-fire snapshot value even
        though the flag transition wasn't observed (backend pushed the LTV
        update after Unreal already responded). Strength change implies
        forward; treat as fresh."""
        dumblocate = import_dumblocate()
        dumblocate.PING_ACK_OBSERVE_TIMEOUT_SEC = 0.5
        dumblocate.PING_STRENGTH_TRAIL_TIMEOUT_SEC = 0.05
        dumblocate.PING_RESPONSE_POLL_SEC = 0.01

        _install_fetch_ltv_sequence(
            dumblocate,
            [
                _make_ltv_json(ping_requested=1, strength=-50.0),  # pre-fire
                _make_ltv_json(ping_requested=1, strength=-42.5),  # backend missed the 1->0 window
            ],
        )
        dumblocate.send_float_command = lambda sock, command, value: True

        budget = dumblocate.PingBudget(remaining=10, total=10)
        result = dumblocate.request_ping(
            sock=None, rover_x_m=0.0, rover_y_m=0.0, budget=budget
        )
        self.assertTrue(result.fresh)
        self.assertAlmostEqual(result.strength, -42.5)
        self.assertEqual(budget.remaining, 9)
        self.assertIsNotNone(budget.last_ack_monotonic)

    def test_forward_then_strength_arrives(self):
        """Realistic happy path: flag clears first (server forwarded), then a
        couple polls later strength updates (Unreal responded)."""
        dumblocate = import_dumblocate()
        dumblocate.PING_ACK_OBSERVE_TIMEOUT_SEC = 0.5
        dumblocate.PING_STRENGTH_TRAIL_TIMEOUT_SEC = 0.5
        dumblocate.PING_RESPONSE_POLL_SEC = 0.01

        _install_fetch_ltv_sequence(
            dumblocate,
            [
                _make_ltv_json(ping_requested=1, strength=-50.0),  # pre-fire
                _make_ltv_json(ping_requested=0, strength=-50.0),  # forwarded, strength not yet updated
                _make_ltv_json(ping_requested=0, strength=-50.0),
                _make_ltv_json(ping_requested=0, strength=-42.5),  # Unreal wrote
            ],
        )
        dumblocate.send_float_command = lambda sock, command, value: True

        budget = dumblocate.PingBudget(remaining=10, total=10)
        result = dumblocate.request_ping(
            sock=None, rover_x_m=0.0, rover_y_m=0.0, budget=budget
        )
        self.assertTrue(result.fresh)
        self.assertAlmostEqual(result.strength, -42.5)
        self.assertEqual(budget.remaining, 9)

    def test_fresh_sentinel_consumes_and_flags(self):
        """A fresh ping that arrives equal to the 1.0 sentinel is genuinely
        out-of-range and DOES consume the budget — that's information earned."""
        dumblocate = import_dumblocate()
        dumblocate.PING_ACK_OBSERVE_TIMEOUT_SEC = 0.5
        dumblocate.PING_STRENGTH_TRAIL_TIMEOUT_SEC = 0.2
        dumblocate.PING_RESPONSE_POLL_SEC = 0.01

        _install_fetch_ltv_sequence(
            dumblocate,
            [
                _make_ltv_json(ping_requested=1, strength=-50.0),
                _make_ltv_json(ping_requested=0, strength=1.0),  # sentinel
            ],
        )
        dumblocate.send_float_command = lambda sock, command, value: True

        budget = dumblocate.PingBudget(remaining=10, total=10)
        result = dumblocate.request_ping(
            sock=None, rover_x_m=0.0, rover_y_m=0.0, budget=budget
        )
        self.assertTrue(result.fresh)
        self.assertTrue(result.sentinel)
        self.assertEqual(budget.remaining, 9)
        self.assertTrue(budget.last_was_sentinel)

    def test_persistent_ltv_read_errors_treated_as_not_fresh(self):
        """If fetch_ltv_json keeps raising, request_ping bails out of the
        observe loop instead of looping forever."""
        dumblocate = import_dumblocate()
        dumblocate.PING_ACK_OBSERVE_TIMEOUT_SEC = 2.0
        dumblocate.PING_RESPONSE_POLL_SEC = 0.005

        # First call (pre-fire snapshot) succeeds; subsequent calls fail.
        state = {"n": 0}

        def flaky_fetch(_sock):
            state["n"] += 1
            if state["n"] == 1:
                return _make_ltv_json(ping_requested=1, strength=-50.0)
            raise RuntimeError("LTV channel broken")

        dumblocate.fetch_ltv_json = flaky_fetch
        dumblocate.send_float_command = lambda sock, command, value: True

        budget = dumblocate.PingBudget(remaining=10, total=10)
        t0 = time.monotonic()
        result = dumblocate.request_ping(
            sock=None, rover_x_m=0.0, rover_y_m=0.0, budget=budget
        )
        elapsed = time.monotonic() - t0
        self.assertFalse(result.fresh)
        self.assertFalse(result.rejected)
        self.assertEqual(budget.remaining, 10)
        # Should give up well before the observe timeout.
        self.assertLess(elapsed, 1.0, f"flaky LTV read held the loop for {elapsed:.2f}s")


class TestShouldPingDecision(unittest.TestCase):
    """The decision function is pure: same inputs → same output. Verify each
    gate independently so future changes don't regress eligibility."""

    def test_exhausted_budget_refuses(self):
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(remaining=0, total=10)
        decision = dumblocate.should_ping(budget, rover_x_m=0.0, rover_y_m=0.0)
        self.assertFalse(decision.should_ping)
        self.assertIn("budget", decision.reason)

    def test_first_ping_allowed_with_no_history(self):
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(remaining=10, total=10)
        decision = dumblocate.should_ping(budget, rover_x_m=0.0, rover_y_m=0.0)
        self.assertTrue(decision.should_ping)

    def test_cooldown_gate_blocks(self):
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(remaining=8, total=10)
        # Cooldown is gated on the server-forward clock (last_ack_monotonic),
        # not the last fresh ping. Server just fired = cooldown active.
        budget.last_ack_monotonic = time.monotonic()
        budget.last_ping_monotonic = time.monotonic()
        budget.last_pos_m = (0.0, 0.0)
        decision = dumblocate.should_ping(budget, rover_x_m=0.0, rover_y_m=0.0)
        self.assertFalse(decision.should_ping)
        self.assertIn("cooldown", decision.reason)

    def test_cooldown_uses_ack_clock_not_ping_clock(self):
        """If the server fired a ping but Unreal failed to write back a new
        strength (i.e., not-fresh), the budget's last_ping_monotonic stays
        stale but last_ack_monotonic advances. Cooldown must still block."""
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(remaining=8, total=10)
        # last_ping_monotonic far in the past (never had a fresh ping in this
        # session), but server just forwarded a request → cooldown active.
        budget.last_ping_monotonic = None
        budget.last_ack_monotonic = time.monotonic()
        decision = dumblocate.should_ping(budget, rover_x_m=0.0, rover_y_m=0.0)
        self.assertFalse(decision.should_ping)
        self.assertIn("cooldown", decision.reason)

    def test_post_sentinel_requires_movement(self):
        """Pinging from the same spot after a sentinel is guaranteed sentinel.
        Decision must block until the rover moved meaningfully."""
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(remaining=8, total=10)
        # Past the server cooldown.
        past = time.monotonic() - (dumblocate.SERVER_PING_COOLDOWN_SEC + 1.0)
        budget.last_ping_monotonic = past
        budget.last_ack_monotonic = past
        budget.last_pos_m = (0.0, 0.0)
        budget.last_was_sentinel = True

        # Barely moved.
        decision_close = dumblocate.should_ping(
            budget, rover_x_m=1.0, rover_y_m=1.0
        )
        self.assertFalse(decision_close.should_ping)
        self.assertIn("sentinel", decision_close.reason)

        # Moved well past MIN_MOVE_AFTER_SENTINEL_M.
        decision_far = dumblocate.should_ping(
            budget,
            rover_x_m=dumblocate.MIN_MOVE_AFTER_SENTINEL_M + 5.0,
            rover_y_m=0.0,
        )
        self.assertTrue(decision_far.should_ping)

    def test_conservative_band_requires_strong_justification(self):
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(remaining=1, total=10)
        past = time.monotonic() - (dumblocate.SERVER_PING_COOLDOWN_SEC + 1.0)
        budget.last_ping_monotonic = past
        budget.last_ack_monotonic = past
        budget.last_pos_m = (0.0, 0.0)

        # Tiny move, fresh recent ping -> conserve.
        decision_conserve = dumblocate.should_ping(
            budget, rover_x_m=2.0, rover_y_m=0.0
        )
        self.assertFalse(decision_conserve.should_ping)
        self.assertIn("conserv", decision_conserve.reason.lower())

        # Big move -> spend the final ping.
        decision_spend = dumblocate.should_ping(
            budget,
            rover_x_m=dumblocate.CONSERVATIVE_MIN_MOVE_M + 10.0,
            rover_y_m=0.0,
        )
        self.assertTrue(decision_spend.should_ping)

    def test_aggressive_band_pings_freely(self):
        dumblocate = import_dumblocate()
        budget = dumblocate.PingBudget(
            remaining=dumblocate.BUDGET_AGGRESSIVE_THRESHOLD, total=10
        )
        past = time.monotonic() - (dumblocate.SERVER_PING_COOLDOWN_SEC + 1.0)
        budget.last_ping_monotonic = past
        budget.last_ack_monotonic = past
        budget.last_pos_m = (0.0, 0.0)
        # Even tiny movement is fine in the aggressive band.
        decision = dumblocate.should_ping(budget, rover_x_m=0.1, rover_y_m=0.0)
        self.assertTrue(decision.should_ping)


class TestCoordinateTransformInverse(unittest.TestCase):
    """`raw_world_m_to_local_cm` and `local_cm_to_raw_world_m` must be exact
    inverses. A drift here would silently corrupt LKL targeting."""

    def test_inverse_round_trip(self):
        dumblocate = import_dumblocate(
            pose_units_to_cm=100.0,
            pose_offset_x_cm=-566700.0,
            pose_offset_y_cm=-1009190.039,
        )
        # Realistic LTV.json values.
        for x_m, y_m in [
            (-5839.3, -10460.6),
            (-6047.30, -10769.3),
            (0.0, 0.0),
            (123.456, -789.012),
        ]:
            x_cm, y_cm = dumblocate.raw_world_m_to_local_cm(x_m, y_m)
            back_x, back_y = dumblocate.local_cm_to_raw_world_m(x_cm, y_cm)
            self.assertAlmostEqual(back_x, x_m, places=6)
            self.assertAlmostEqual(back_y, y_m, places=6)


class TestPingBudgetIntegrationCap(unittest.TestCase):
    """End-to-end: simulate many ping attempts and assert the cap holds."""

    def test_many_attempts_capped_at_ten(self):
        dumblocate = import_dumblocate()
        dumblocate.PING_ACK_OBSERVE_TIMEOUT_SEC = 0.1
        dumblocate.PING_STRENGTH_TRAIL_TIMEOUT_SEC = 0.05
        dumblocate.PING_RESPONSE_POLL_SEC = 0.005

        counter = {"n": 0}

        def fake_send(sock, command, value):
            return True

        def fake_fetch(_sock):
            counter["n"] += 1
            # Strength evolves with each call so every ping looks fresh.
            return {
                "signal": {
                    "ping_requested": 0,
                    "strength": -50.0 - 0.01 * counter["n"],
                }
            }

        dumblocate.send_float_command = fake_send
        dumblocate.fetch_ltv_json = fake_fetch

        budget = dumblocate.PingBudget(remaining=10, total=10)
        # Try 25 attempts; only the first 10 should consume. The 11th
        # iteration is short-circuited by the loop's can_spend check.
        for i in range(25):
            if not budget.can_spend(1):
                break
            dumblocate.request_ping(
                sock=None, rover_x_m=float(i * 100), rover_y_m=0.0, budget=budget
            )
        self.assertEqual(budget.successful_pings, 10)
        self.assertEqual(budget.remaining, 0)


if __name__ == "__main__":
    unittest.main()
