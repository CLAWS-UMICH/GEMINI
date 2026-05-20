from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path

CONTROLFILES_DIR = Path(__file__).resolve().parents[1] / "controlfiles"
if str(CONTROLFILES_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLFILES_DIR))


def _import_main():
    """Import controlfiles.main with heavy external deps (model, rover_control)
    stubbed out via sys.modules. The pure-Python `planner` module is left
    unstubbed and imported for real."""
    sys.modules.pop("main", None)

    fake_model = types.SimpleNamespace(
        inferencer_backend=lambda *a, **kw: None,
        ingest_lidar=lambda *a, **kw: None,
        reset_history=lambda *a, **kw: None,
    )
    fake_rover_control = types.SimpleNamespace(
        close_rover_socket=lambda *a, **kw: None,
        fetch_rover_telemetry=lambda *a, **kw: {},
        open_rover_socket=lambda *a, **kw: None,
        set_brakes=lambda *a, **kw: None,
        set_steering=lambda *a, **kw: None,
        set_throttle=lambda *a, **kw: None,
        wait_for_dust=lambda *a, **kw: True,
    )
    sys.modules["model"] = fake_model
    sys.modules["rover_control"] = fake_rover_control

    return importlib.import_module("main")


# Hub rectangle, mirrored from SPACE_HUB_RECT_CM in controlfiles/main.py.
# Duplicated here because importing `main` at module scope would fail —
# main imports model/rover_control, which are only stubbed inside _import_main().
# Keep in sync with controlfiles/main.py::SPACE_HUB_RECT_CM.
HUB_X_MIN_CM = -5670.0
HUB_X_MAX_CM = -5660.0
HUB_Y_MIN_CM = -10045.0
HUB_Y_MAX_CM = -10025.0
HUB_CENTER_X_CM = (HUB_X_MIN_CM + HUB_X_MAX_CM) / 2.0
HUB_CENTER_Y_CM = (HUB_Y_MIN_CM + HUB_Y_MAX_CM) / 2.0
SPAWN_XY = (-5669.6, -10076.9)
NORTH_GOAL_XY = (-5665.0, -9900.0)


class TestSpaceHubObstacle(unittest.TestCase):
    def test_hub_center_is_padded_obstacle_in_planner(self):
        main = _import_main()
        planner = main.create_planner(SPAWN_XY, NORTH_GOAL_XY)
        center_cell = planner.world_to_cell(HUB_CENTER_X_CM, HUB_CENTER_Y_CM)
        self.assertTrue(
            planner.is_padded_obstacle(center_cell),
            "Hub center cell must be a padded obstacle after create_planner.",
        )

    def test_hub_corners_marked(self):
        main = _import_main()
        planner = main.create_planner(SPAWN_XY, NORTH_GOAL_XY)
        for x in (HUB_X_MIN_CM, HUB_X_MAX_CM):
            for y in (HUB_Y_MIN_CM, HUB_Y_MAX_CM):
                cell = planner.world_to_cell(x, y)
                self.assertTrue(
                    planner.is_padded_obstacle(cell),
                    f"Hub corner ({x}, {y}) must be a padded obstacle.",
                )

    def test_does_not_raise_when_grid_excludes_hub(self):
        main = _import_main()
        far_start = (10_000.0, 10_000.0)
        far_goal = (10_500.0, 10_500.0)
        try:
            main.create_planner(far_start, far_goal)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"create_planner raised when grid excludes hub: {exc!r}")


class TestSpaceHubPathAvoidance(unittest.TestCase):
    def _path_crosses_hub(self, path):
        for x, y in path:
            if HUB_X_MIN_CM <= x <= HUB_X_MAX_CM and HUB_Y_MIN_CM <= y <= HUB_Y_MAX_CM:
                return True
        return False

    def test_path_from_spawn_to_north_goal_avoids_hub(self):
        main = _import_main()
        planner = main.create_planner(SPAWN_XY, NORTH_GOAL_XY)
        path = planner.plan_path(SPAWN_XY, NORTH_GOAL_XY)
        self.assertTrue(path, "Planner returned empty path; expected a route.")
        self.assertFalse(
            self._path_crosses_hub(path),
            f"Path passes through hub rectangle. Path: {path}",
        )


if __name__ == "__main__":
    unittest.main()
