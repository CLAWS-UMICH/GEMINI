from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path


CONTROLFILES_DIR = Path(__file__).resolve().parents[1] / "controlfiles"
if str(CONTROLFILES_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLFILES_DIR))


def install_import_stubs():
    fake_numpy = types.SimpleNamespace(
        ndarray=object,
        linspace=lambda start, stop, count: [start, stop][:count],
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
        choose_drive_command=lambda *args, **kwargs: (0.0, 0.0, 0.0, 0.0),
        create_planner=lambda *args, **kwargs: None,
        distance_cm=lambda *args, **kwargs: 0.0,
        local_to_world_2d=lambda *args, **kwargs: (0.0, 0.0),
        parse_lidar=lambda *args, **kwargs: [],
        parse_pose=lambda *args, **kwargs: (0.0, 0.0, 0.0, 0.0),
        plan_path_for_following=lambda *args, **kwargs: (None, []),
        stop_rover=lambda *args, **kwargs: None,
        select_local_path_target=lambda *args, **kwargs: (0.0, 0.0, 0),
    )
    fake_rover_control = types.SimpleNamespace(
        SERVER_HOST=None,
        SERVER_PORT=None,
        configured=[],
        build_occupancy_matrix=lambda *args, **kwargs: None,
        close_rover_socket=lambda *args, **kwargs: None,
        configure_remote_server=lambda enabled, url=None: fake_rover_control.configured.append((enabled, url)),
        fetch_rover_json=lambda *args, **kwargs: {},
        open_rover_socket=lambda *args, **kwargs: None,
        sanitize_lidar_scan=lambda *args, **kwargs: None,
        send_occupancy_matrix=lambda *args, **kwargs: False,
        set_brakes=lambda *args, **kwargs: False,
        set_steering=lambda *args, **kwargs: False,
        set_throttle=lambda *args, **kwargs: False,
        wait_for_dust=lambda *args, **kwargs: False,
    )
    sys.modules["numpy"] = fake_numpy
    sys.modules["main"] = fake_main
    sys.modules["rover_control"] = fake_rover_control
    return fake_rover_control


def import_dumbdrive():
    sys.modules.pop("dumbdrive", None)
    install_import_stubs()
    return importlib.import_module("dumbdrive")


class DumbdriveTransportConfigTest(unittest.TestCase):
    def test_default_transport_uses_backend_socket(self):
        dumbdrive = import_dumbdrive()

        config = dumbdrive.load_transport_config({})

        self.assertTrue(config.remote_enabled)
        self.assertEqual(config.backend_url, "http://127.0.0.1:5001")

    def test_udp_transport_uses_tss_host_and_port(self):
        dumbdrive = import_dumbdrive()

        config = dumbdrive.load_transport_config(
            {
                "DUMBDRIVE_TRANSPORT": "udp",
                "DUMBDRIVE_TSS_HOST": "10.1.2.3",
                "DUMBDRIVE_TSS_PORT": "15151",
            }
        )
        dumbdrive.apply_transport_config(config)

        self.assertFalse(config.remote_enabled)
        self.assertEqual(dumbdrive.rover_control.SERVER_HOST, "10.1.2.3")
        self.assertEqual(dumbdrive.rover_control.SERVER_PORT, 15151)
        self.assertEqual(dumbdrive.rover_control.configured[-1], (False, None))

    def test_socket_transport_uses_backend_url(self):
        dumbdrive = import_dumbdrive()

        config = dumbdrive.load_transport_config(
            {
                "DUMBDRIVE_TRANSPORT": "backend",
                "DUMBDRIVE_BACKEND_URL": "http://backend.local:5001",
            }
        )
        dumbdrive.apply_transport_config(config)

        self.assertTrue(config.remote_enabled)
        self.assertEqual(config.backend_url, "http://backend.local:5001")
        self.assertEqual(dumbdrive.rover_control.configured[-1], (True, "http://backend.local:5001"))


if __name__ == "__main__":
    unittest.main()
