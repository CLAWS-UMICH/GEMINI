"""Trilateration solver: estimate a 2D position from 3+ range circles."""
import math
from typing import List, Tuple

import numpy as np


def solve(circles: List[Tuple[float, float, float]]) -> Tuple[float, float, float]:
    """
    Solve for (x, y) given >= 3 circles [(cx, cy, radius), ...].

    Uses the standard linearization trick: subtract the reference circle's
    equation from each other circle to get a linear system  A @ [x, y] = b.
    The circle with the smallest radius is used as reference since it has the
    lowest absolute distance error.  Each equation is weighted by the inverse
    of its distance-error variance so that close-range measurements dominate
    over noisy far-away ones.

    Returns (est_x, est_y, residual) where residual is the RMS of
    |dist(est, center_i) - radius_i| across all circles.
    """
    if len(circles) < 3:
        raise ValueError("Need at least 3 circles for trilateration")

    n = len(circles)

    ref_idx = min(range(n), key=lambda i: circles[i][2])
    x1, y1, d1 = circles[ref_idx]
    others = [c for i, c in enumerate(circles) if i != ref_idx]

    A = np.zeros((len(others), 2))
    b_vec = np.zeros(len(others))
    for i, (xi, yi, di) in enumerate(others):
        # Variance of (d1² - di²) ≈ (2·d1·σ1)² + (2·di·σi)²; with σ∝d this
        # simplifies to ∝ d1⁴ + di⁴.  Weight = 1/σ.
        w = 1.0 / math.sqrt(d1**4 + di**4 + 1e-12)
        A[i, 0] = 2.0 * (xi - x1) * w
        A[i, 1] = 2.0 * (yi - y1) * w
        b_vec[i] = (d1**2 - di**2 + xi**2 - x1**2 + yi**2 - y1**2) * w

    result, _, _, _ = np.linalg.lstsq(A, b_vec, rcond=None)
    est_x, est_y = float(result[0]), float(result[1])

    rms = 0.0
    for cx, cy, r in circles:
        err = math.hypot(est_x - cx, est_y - cy) - r
        rms += err * err
    rms = math.sqrt(rms / n)

    return (est_x, est_y, rms)
