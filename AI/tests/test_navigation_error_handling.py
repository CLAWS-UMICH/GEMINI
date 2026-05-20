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


if __name__ == "__main__":
    unittest.main()
