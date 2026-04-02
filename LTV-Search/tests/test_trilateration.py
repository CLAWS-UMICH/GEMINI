"""Tests for the trilateration solver."""
import math
import unittest

from ltv_search.trilateration import solve


class TestTrilateration(unittest.TestCase):

    def test_exact_3_circles(self):
        """Three noiseless circles should solve exactly."""
        target = (300.0, 400.0)
        circles = [
            (0.0, 0.0, math.hypot(300, 400)),
            (500.0, 0.0, math.hypot(200, 400)),
            (0.0, 800.0, math.hypot(300, 400)),
        ]
        ex, ey, residual = solve(circles)
        self.assertAlmostEqual(ex, target[0], delta=1.0)
        self.assertAlmostEqual(ey, target[1], delta=1.0)
        self.assertLess(residual, 1.0)

    def test_overdetermined_4_circles(self):
        """Four noiseless circles (overdetermined) should also work."""
        target = (100.0, -200.0)
        centers = [(0, 0), (300, 0), (0, -500), (300, -500)]
        circles = [
            (cx, cy, math.hypot(target[0] - cx, target[1] - cy))
            for cx, cy in centers
        ]
        ex, ey, residual = solve(circles)
        self.assertAlmostEqual(ex, target[0], delta=1.0)
        self.assertAlmostEqual(ey, target[1], delta=1.0)
        self.assertLess(residual, 1.0)

    def test_noisy_radii(self):
        """With +-5% noise on radii, solution should still be close."""
        target = (200.0, 300.0)
        import random
        random.seed(42)
        centers = [(0, 0), (400, 0), (200, 600)]
        circles = [
            (cx, cy, math.hypot(target[0] - cx, target[1] - cy) * random.uniform(0.95, 1.05))
            for cx, cy in centers
        ]
        ex, ey, residual = solve(circles)
        err = math.hypot(ex - target[0], ey - target[1])
        self.assertLess(err, 50.0)

    def test_requires_3_circles(self):
        with self.assertRaises(ValueError):
            solve([(0, 0, 100), (100, 0, 100)])


if __name__ == "__main__":
    unittest.main()
