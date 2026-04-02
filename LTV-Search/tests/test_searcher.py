"""End-to-end test of LTVSearcher: synthetic pings, verify it converges."""
import math
import unittest

from ltv_search.rssi import distance_to_rssi
from ltv_search.searcher import LTVSearcher


class TestLTVSearcher(unittest.TestCase):

    def test_finds_ltv(self):
        """Feed the searcher pings from known positions, verify it finds the LTV."""
        lkp = (0.0, 0.0)
        true_ltv = (400.0, -300.0)

        searcher = LTVSearcher(
            lkp_x=lkp[0], lkp_y=lkp[1],
            found_distance_m=20.0,
            rssi_noise_std=0.0,
        )

        rover_pos = lkp
        for step in range(10):
            dist = math.hypot(rover_pos[0] - true_ltv[0], rover_pos[1] - true_ltv[1])
            rssi = distance_to_rssi(dist, model="linear", noise_std=0.0)
            action = searcher.report_ping(rover_pos[0], rover_pos[1], rssi)

            if action.action_type == "found":
                self.assertIsNotNone(action.estimate)
                err = math.hypot(action.estimate[0] - true_ltv[0], action.estimate[1] - true_ltv[1])
                self.assertLess(err, 100.0)
                return

            self.assertIsNotNone(action.target)
            rover_pos = action.target

        self.fail("LTV not found within 10 steps")

    def test_first_three_return_move_and_ping(self):
        """The first 3 calls should return move_and_ping (triangulating)."""
        searcher = LTVSearcher(lkp_x=0.0, lkp_y=0.0, rssi_noise_std=0.0)

        positions = [(0, 0), (0, 100), (86.6, 50)]
        for i, (x, y) in enumerate(positions[:2]):
            rssi = distance_to_rssi(500.0, model="linear", noise_std=0.0)
            action = searcher.report_ping(x, y, rssi)
            self.assertEqual(action.action_type, "move_and_ping", f"Step {i}")
            self.assertEqual(action.phase, "triangulating")

    def test_third_ping_triggers_estimate(self):
        """After 3 pings, should have an estimate."""
        searcher = LTVSearcher(lkp_x=0.0, lkp_y=0.0, rssi_noise_std=0.0)
        true_ltv = (300.0, 200.0)

        positions = [(0, 0)]
        for i in range(3):
            x, y = positions[-1]
            dist = math.hypot(x - true_ltv[0], y - true_ltv[1])
            rssi = distance_to_rssi(dist, model="linear", noise_std=0.0)
            action = searcher.report_ping(x, y, rssi)
            if action.target:
                positions.append(action.target)

        self.assertIsNotNone(searcher.estimate)


if __name__ == "__main__":
    unittest.main()
