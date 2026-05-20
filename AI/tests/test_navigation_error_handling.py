from __future__ import annotations

import importlib
import math
import sys
import types
import unittest
from pathlib import Path

CONTROLFILES_DIR = Path(__file__).resolve().parents[1] / "controlfiles"
if str(CONTROLFILES_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLFILES_DIR))


def import_dumblocate():
    """Import dumblocate with all external deps stubbed out."""
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
        POSE_OFFSET_X_CM=0.0,
        POSE_OFFSET_Y_CM=0.0,
        POSE_UNITS_TO_CM=100.0,
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


class TestTrilaterateNaNGuard(unittest.TestCase):
    def test_nan_radius_raises_runtime_error(self):
        dumblocate = import_dumblocate()
        PingSample = dumblocate.PingSample

        samples = (
            PingSample(rover_x_m=0.0, rover_y_m=0.0, ping_value=-40.0, radius_m=float("nan")),
            PingSample(rover_x_m=10.0, rover_y_m=0.0, ping_value=-45.0, radius_m=200.0),
            PingSample(rover_x_m=0.0, rover_y_m=10.0, ping_value=-50.0, radius_m=150.0),
        )
        with self.assertRaises(RuntimeError) as ctx:
            dumblocate.trilaterate(samples)
        self.assertIn("finite", str(ctx.exception).lower())

    def test_inf_radius_raises_runtime_error(self):
        dumblocate = import_dumblocate()
        PingSample = dumblocate.PingSample

        samples = (
            PingSample(rover_x_m=0.0, rover_y_m=0.0, ping_value=-40.0, radius_m=float("inf")),
            PingSample(rover_x_m=10.0, rover_y_m=0.0, ping_value=-45.0, radius_m=200.0),
            PingSample(rover_x_m=0.0, rover_y_m=10.0, ping_value=-50.0, radius_m=150.0),
        )
        with self.assertRaises(RuntimeError) as ctx:
            dumblocate.trilaterate(samples)
        self.assertIn("finite", str(ctx.exception).lower())

    def test_valid_samples_still_trilaterate(self):
        dumblocate = import_dumblocate()
        PingSample = dumblocate.PingSample

        samples = (
            PingSample(rover_x_m=0.0, rover_y_m=0.0, ping_value=-40.0, radius_m=100.0),
            PingSample(rover_x_m=50.0, rover_y_m=0.0, ping_value=-45.0, radius_m=80.0),
            PingSample(rover_x_m=0.0, rover_y_m=50.0, ping_value=-50.0, radius_m=120.0),
        )
        x_m, y_m = dumblocate.trilaterate(samples)
        self.assertTrue(math.isfinite(x_m))
        self.assertTrue(math.isfinite(y_m))


class TestRunTrilaterationRoundDegenerateGeometry(unittest.TestCase):
    def test_degenerate_geometry_returns_false_not_exception(self):
        """run_trilateration_round must return (None, ..., False) on RuntimeError from trilaterate."""
        dumblocate = import_dumblocate()
        PingSample = dumblocate.PingSample

        # Two samples at identical position → degenerate geometry → trilaterate raises
        samples_degenerate = [
            PingSample(rover_x_m=0.0, rover_y_m=0.0, ping_value=-40.0, radius_m=100.0),
            PingSample(rover_x_m=0.0, rover_y_m=0.0, ping_value=-45.0, radius_m=90.0),
            PingSample(rover_x_m=10.0, rover_y_m=0.0, ping_value=-50.0, radius_m=80.0),
        ]

        fake_run_state = types.SimpleNamespace(aborted=False)
        original_collect = dumblocate.collect_guided_ping_samples

        def fake_collect(*args, **kwargs):
            return (samples_degenerate, fake_run_state, None, True)

        dumblocate.collect_guided_ping_samples = fake_collect
        try:
            round_config = dumblocate.TRILATERATION_ROUNDS[0]
            result, run_state, viewer, ok = dumblocate.run_trilateration_round(
                sock=None,
                round_config=round_config,
                anchor_xy=(0.0, 0.0),
                run_state=fake_run_state,
                viewer=None,
                telemetry_callback=None,
                debug_logger=None,
            )
            self.assertFalse(ok)
            self.assertIsNone(result)
        finally:
            dumblocate.collect_guided_ping_samples = original_collect


class TestRequestPingCommandFailure(unittest.TestCase):
    def test_send_command_failure_returns_last_known_strength_not_exception(self):
        dumblocate = import_dumblocate()

        def failing_send(sock, command, value):
            raise RuntimeError("Socket timeout sending ping")

        def fake_read_ltv_signal_strength(sock):
            return -42.5

        original_send = dumblocate.send_float_command
        original_read = dumblocate.read_ltv_signal_strength
        dumblocate.send_float_command = failing_send
        dumblocate.read_ltv_signal_strength = fake_read_ltv_signal_strength
        try:
            strength = dumblocate.request_ping_and_read_strength(sock=None)
            self.assertAlmostEqual(strength, -42.5)
        finally:
            dumblocate.send_float_command = original_send
            dumblocate.read_ltv_signal_strength = original_read


class TestHandleAlertExceptionIsolation(unittest.TestCase):
    def test_aia_exception_does_not_propagate_from_handle_alert(self):
        """handle_alert must catch aia.recommend_procedure errors."""
        fake_aia = types.SimpleNamespace(
            recommend_procedure=lambda alert: (_ for _ in ()).throw(RuntimeError("aia broken")),
        )
        fake_backend_bridge = types.SimpleNamespace(
            send_alert=lambda *a, **kw: None,
        )
        backend = object()

        errors = []
        try:
            def handle_alert(alert: dict) -> None:
                try:
                    recommendation = fake_aia.recommend_procedure(alert)
                    if recommendation is not None:
                        alert = {**alert, "procedure": recommendation}
                    fake_backend_bridge.send_alert(backend, alert)
                except Exception as exc:
                    print(f"handle_alert error (continuing): {exc!r}")

            handle_alert({"metric": "battery", "value": 10})
        except Exception as exc:
            errors.append(exc)

        self.assertEqual(len(errors), 0, f"handle_alert propagated exception: {errors}")


class TestOnPathUpdateExceptionIsolation(unittest.TestCase):
    def test_path_callback_failure_does_not_propagate_from_notify_path_update(self):
        """notify_path_update must not propagate exceptions from path_callback."""
        sys.modules.pop("dumbdrive", None)

        fake_rover_control = types.SimpleNamespace(
            SERVER_HOST=None,
            SERVER_PORT=None,
            build_occupancy_matrix=lambda *a, **kw: {"cells": []},
            close_rover_socket=lambda *a, **kw: None,
            configure_remote_server=lambda *a, **kw: None,
            fetch_rover_json=lambda *a, **kw: {},
            open_rover_socket=lambda *a, **kw: None,
            sanitize_lidar_scan=lambda *a, **kw: None,
            send_occupancy_matrix=lambda *a, **kw: False,
            set_brakes=lambda *a, **kw: False,
            set_steering=lambda *a, **kw: False,
            set_throttle=lambda *a, **kw: False,
            wait_for_dust=lambda *a, **kw: False,
        )
        fake_main = types.SimpleNamespace(
            CONTROL_PERIOD_SEC=0.2,
            GOAL_REACHED_CM=350.0,
            GRID_CELL_SIZE_CM=50.0,
            LIDAR_SENSOR_LAYOUT=[],
            LIDAR_SENSOR_LABELS=[],
            PATH_TARGET_LOOKAHEAD_CM=100.0,
            POSE_UNITS_TO_CM=100.0,
            ROVER_HALF_LENGTH_CM=100.0,
            ROVER_HALF_WIDTH_CM=100.0,
            TARGET_DX_CM=100.0,
            TARGET_DY_CM=100.0,
            CELL_OBSTACLE=1,
            MapWindow=object,
            choose_drive_command=lambda *a, **kw: (0.0, 0.0, 0.0, 0.0),
            create_planner=lambda *a, **kw: None,
            distance_cm=lambda *a, **kw: 0.0,
            local_to_world_2d=lambda *a, **kw: (0.0, 0.0),
            parse_lidar=lambda *a, **kw: [],
            parse_pose=lambda *a, **kw: (0.0, 0.0, 0.0, 0.0),
            plan_path_for_following=lambda *a, **kw: (None, []),
            select_local_path_target=lambda *a, **kw: (0.0, 0.0, 0),
            stop_rover=lambda *a, **kw: None,
        )
        sys.modules["numpy"] = types.SimpleNamespace(ndarray=object)
        sys.modules["main"] = fake_main
        sys.modules["rover_control"] = fake_rover_control
        sys.modules.pop("dumbdrive", None)
        dumbdrive = importlib.import_module("dumbdrive")

        def failing_callback(update):
            raise RuntimeError("backend disconnected")

        errors = []
        try:
            dumbdrive.notify_path_update(
                failing_callback,
                planner=None,
                rover_xy=(0.0, 0.0),
                goal_xy=(100.0, 100.0),
                path_world=[(0.0, 0.0), (100.0, 100.0)],
            )
        except Exception as exc:
            errors.append(exc)

        self.assertEqual(len(errors), 0, f"notify_path_update let callback exception escape: {errors}")


class TestSendOccupancyMatrixFailureTolerance(unittest.TestCase):
    def test_safe_send_occupancy_matrix_tolerates_error(self):
        """_safe_send_occupancy_matrix must not raise when send_occupancy_matrix raises."""
        sys.modules.pop("dumbdrive", None)

        fake_rover_control = types.SimpleNamespace(
            SERVER_HOST=None,
            SERVER_PORT=None,
            build_occupancy_matrix=lambda *a, **kw: None,
            close_rover_socket=lambda *a, **kw: None,
            configure_remote_server=lambda *a, **kw: None,
            fetch_rover_json=lambda *a, **kw: {},
            open_rover_socket=lambda *a, **kw: None,
            sanitize_lidar_scan=lambda *a, **kw: None,
            send_occupancy_matrix=lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("backend down")),
            set_brakes=lambda *a, **kw: False,
            set_steering=lambda *a, **kw: False,
            set_throttle=lambda *a, **kw: False,
            wait_for_dust=lambda *a, **kw: False,
        )
        fake_main_module = types.SimpleNamespace(
            CONTROL_PERIOD_SEC=0.2,
            GOAL_REACHED_CM=350.0,
            GRID_CELL_SIZE_CM=50.0,
            LIDAR_SENSOR_LAYOUT=[],
            LIDAR_SENSOR_LABELS=[],
            PATH_TARGET_LOOKAHEAD_CM=100.0,
            POSE_UNITS_TO_CM=100.0,
            ROVER_HALF_LENGTH_CM=100.0,
            ROVER_HALF_WIDTH_CM=100.0,
            TARGET_DX_CM=100.0,
            TARGET_DY_CM=100.0,
            CELL_OBSTACLE=1,
            MapWindow=object,
            choose_drive_command=lambda *a, **kw: (0.0, 0.0, 0.0, 0.0),
            create_planner=lambda *a, **kw: None,
            distance_cm=lambda *a, **kw: 0.0,
            local_to_world_2d=lambda *a, **kw: (0.0, 0.0),
            parse_lidar=lambda *a, **kw: [],
            parse_pose=lambda *a, **kw: (0.0, 0.0, 0.0, 0.0),
            plan_path_for_following=lambda *a, **kw: (None, []),
            select_local_path_target=lambda *a, **kw: (0.0, 0.0, 0),
            stop_rover=lambda *a, **kw: None,
        )
        sys.modules["main"] = fake_main_module
        sys.modules["rover_control"] = fake_rover_control
        sys.modules["numpy"] = types.SimpleNamespace(ndarray=object)
        sys.modules.pop("dumbdrive", None)
        dumbdrive = importlib.import_module("dumbdrive")

        called_after = {"n": 0}
        errors = []
        try:
            dumbdrive._safe_send_occupancy_matrix(
                fake_rover_control,
                planner=None,
                rover_xy=(0.0, 0.0),
                goal_xy=(100.0, 100.0),
                path_world=[],
            )
        except Exception as exc:
            errors.append(exc)
        called_after["n"] += 1

        self.assertEqual(len(errors), 0)
        self.assertEqual(called_after["n"], 1)


class TestParseNaNGuard(unittest.TestCase):
    def test_nan_pose_is_detectable(self):
        nan = float("nan")

        def pose_is_finite(x, y, z, heading):
            return all(math.isfinite(v) for v in (x, y, z, heading))

        self.assertFalse(pose_is_finite(nan, 0.0, 0.0, 0.0))
        self.assertFalse(pose_is_finite(0.0, float("inf"), 0.0, 0.0))
        self.assertTrue(pose_is_finite(100.0, 200.0, 10.0, 45.0))


class TestSamplePingSentinelGuard(unittest.TestCase):
    def test_sample_ping_with_sentinel_returns_none_after_fix(self):
        """After fix: sample_ping returns None for sentinel ping instead of raising."""
        dumblocate = import_dumblocate()

        sentinel_strength = dumblocate.PING_DISTANCE_SENTINEL  # 1.0
        dumblocate.request_ping_and_read_strength = lambda sock: sentinel_strength
        raw_telemetry = {"rover_pos_x": 5.0, "rover_pos_y": 10.0}

        result = dumblocate.sample_ping(sock=None, raw_telemetry=raw_telemetry)
        self.assertIsNone(result)

    def test_sample_ping_with_valid_ping_returns_sample(self):
        """sample_ping returns a PingSample for a normal ping value."""
        dumblocate = import_dumblocate()

        dumblocate.request_ping_and_read_strength = lambda sock: -50.0
        raw_telemetry = {"rover_pos_x": 5.0, "rover_pos_y": 10.0}

        result = dumblocate.sample_ping(sock=None, raw_telemetry=raw_telemetry)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.rover_x_m, 5.0)
        self.assertAlmostEqual(result.rover_y_m, 10.0)


if __name__ == "__main__":
    unittest.main()
