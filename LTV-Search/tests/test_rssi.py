"""Tests for RSSI <-> distance models (linear and path-loss)."""
import unittest

from ltv_search.rssi import distance_to_rssi, rssi_to_distance


class TestLinearModel(unittest.TestCase):

    def test_round_trip_500m(self):
        rssi = distance_to_rssi(500.0, model="linear", noise_std=0.0)
        self.assertAlmostEqual(rssi, -37.5, places=2)
        d, sigma = rssi_to_distance(rssi, model="linear")
        self.assertAlmostEqual(d, 500.0, delta=0.5)

    def test_round_trip_1200m(self):
        rssi = distance_to_rssi(1200.0, model="linear", noise_std=0.0)
        self.assertAlmostEqual(rssi, -90.0, places=2)
        d, _ = rssi_to_distance(rssi, model="linear")
        self.assertAlmostEqual(d, 1200.0, delta=0.5)

    def test_sigma_constant(self):
        _, sigma_near = rssi_to_distance(-7.5, model="linear", noise_std=1.0)
        _, sigma_far = rssi_to_distance(-75.0, model="linear", noise_std=1.0)
        self.assertAlmostEqual(sigma_near, sigma_far, delta=0.1)

    def test_distance_increases_as_rssi_decreases(self):
        d1, _ = rssi_to_distance(-10.0, model="linear")
        d2, _ = rssi_to_distance(-50.0, model="linear")
        self.assertGreater(d2, d1)


class TestPathLossModel(unittest.TestCase):

    def test_round_trip_100m(self):
        rssi = distance_to_rssi(100.0, model="path_loss", rssi_ref=-30.0,
                                d_ref=100.0, n=2.5, noise_std=0.0)
        self.assertAlmostEqual(rssi, -30.0, places=2)
        d, _ = rssi_to_distance(rssi, model="path_loss", rssi_ref=-30.0,
                                d_ref=100.0, n=2.5)
        self.assertAlmostEqual(d, 100.0, delta=1.0)

    def test_round_trip_500m(self):
        rssi = distance_to_rssi(500.0, model="path_loss", rssi_ref=-30.0,
                                d_ref=100.0, n=2.5, noise_std=0.0)
        d, _ = rssi_to_distance(rssi, model="path_loss", rssi_ref=-30.0,
                                d_ref=100.0, n=2.5)
        self.assertAlmostEqual(d, 500.0, delta=2.0)

    def test_sigma_positive(self):
        _, sigma = rssi_to_distance(-50.0, model="path_loss")
        self.assertGreater(sigma, 0)


if __name__ == "__main__":
    unittest.main()
