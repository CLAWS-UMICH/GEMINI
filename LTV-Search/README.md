# LTV Search

Trilateration-based localization for finding a missing Lunar Terrain Vehicle (LTV) using range-only beacon pings. Built for the NASA SUITS pressurized rover challenge.

## Quick Start

```bash
pip install /path/to/LTV-Search          # core (numpy only)
pip install /path/to/LTV-Search[viz]     # includes Pygame visualization
```

```python
from ltv_search import LTVSearcher

searcher = LTVSearcher(lkp_x=-5839.0, lkp_y=-10460.0)
```

## Tutorial: Finding the LTV

This walks through the full search flow from start to finish. Replace `drive_to()` and `ping()` with your rover interface.

### 1. Create the searcher

Pass the Last Known Position (LKP) from TSS. If you've already calibrated (see below), use `from_calibration()` instead.

```python
from ltv_search import LTVSearcher

searcher = LTVSearcher(lkp_x=-5839.0, lkp_y=-10460.0)
```

### 2. Drive to the LKP

```python
first_waypoint = searcher.get_initial_waypoint()  # returns (lkp_x, lkp_y)
drive_to(first_waypoint)
```

### 3. Ping and loop

After arriving at each waypoint, ping the LTV beacon and feed the result back to the searcher. It returns a `SearchAction` telling you what to do next.

```python
while True:
    rover_x, rover_y = get_rover_position()
    rssi = ping()  # RSSI in dBm from LTV.json

    action = searcher.report_ping(rover_x, rover_y, rssi)

    if action.action_type == "found":
        print(f"LTV located near {action.estimate}")
        break

    # "move_and_ping" (triangulating) or "move_to_estimate" (approaching)
    drive_to(action.target)
```

### Complete example

```python
from ltv_search import LTVSearcher

searcher = LTVSearcher(lkp_x=-5839.0, lkp_y=-10460.0)

# Step 1: drive to last known position
drive_to(searcher.get_initial_waypoint())

# Step 2: ping-move loop
while True:
    rx, ry = get_rover_position()
    rssi = ping()

    action = searcher.report_ping(rx, ry, rssi)

    if action.action_type == "found":
        print(f"LTV found at {action.estimate}")
        break

    drive_to(action.target)
```

The searcher handles everything internally: it picks triangulation positions for the first 3 pings, solves trilateration, then guides the rover toward the estimate while refining it with each additional ping.

## RSSI Calibration

The searcher converts RSSI (signal strength) to distance using a linear model: `rssi = intercept + slope * distance`. The defaults (`slope=-0.075`, `intercept=0.0`) work for the test simulator but **must be calibrated for real DUST**.

### Calibration procedure (one-time)

1. Open DUST and note the **LTV position** shown in the TSS interface
2. Drive the rover to **3-4 known distances** from the LTV (e.g. ~100m, ~300m, ~600m, ~1000m)
3. At each position, read the rover coordinates from TSS and compute distance:
   `d = sqrt((x2 - x1)^2 + (y2 - y1)^2)`
4. **Ping** and record the RSSI value from `LTV.json`
5. Collect the (distance, RSSI) pairs:

```python
calibration_data = [
    (100,  -7.5),   # (distance_m, rssi_dbm)
    (300, -22.5),
    (600, -45.0),
    (1000, -75.0),
]
```

6. Create the searcher with `from_calibration()`:

```python
searcher = LTVSearcher.from_calibration(
    lkp_x=-5839.0,
    lkp_y=-10460.0,
    known_points=calibration_data,
)
```

This auto-fits the slope and intercept. You only need to do this once -- the values are properties of the antenna and simulator, not the LTV's position.

### Manual alternative

If you already know the slope and intercept, pass them directly:

```python
searcher = LTVSearcher(
    lkp_x=-5839.0,
    lkp_y=-10460.0,
    rssi_linear_slope=-0.075,       # dBm lost per meter of distance
    rssi_linear_intercept=0.0,      # RSSI at zero distance
)
```

## API Reference

### `LTVSearcher`

**Constructor**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lkp_x` | float | *required* | Last known X coordinate |
| `lkp_y` | float | *required* | Last known Y coordinate |
| `found_distance_m` | float | 30.0 | RSSI-estimated distance threshold to declare LTV found |
| `offset_scale` | float | 0.5 | Controls triangulation spread (fraction of estimated distance) |
| `search_radius_m` | float | 1500.0 | Max distance from LKP for estimates and clamping |
| `rssi_model` | str | "linear" | `"linear"` or `"path_loss"` |
| `rssi_linear_intercept` | float | 0.0 | Linear model: RSSI at zero distance |
| `rssi_linear_slope` | float | -0.075 | Linear model: dBm per meter |
| `rssi_ref_dbm` | float | -30.0 | Path-loss model: reference RSSI |
| `d_ref_m` | float | 100.0 | Path-loss model: reference distance |
| `path_loss_n` | float | 2.5 | Path-loss model: exponent |
| `rssi_noise_std` | float | 1.0 | Expected RSSI noise std deviation (dBm) |

**Methods**

| Method | Returns | Description |
|--------|---------|-------------|
| `get_initial_waypoint()` | `(x, y)` | The LKP -- drive here first before pinging |
| `report_ping(rover_x, rover_y, rssi_dbm)` | `SearchAction` | Feed a ping result, get back what to do next |
| `reset(lkp_x=None, lkp_y=None)` | None | Clear all state; optionally set a new LKP. Keeps RSSI model config |
| `from_calibration(lkp_x, lkp_y, known_points, **kwargs)` | `LTVSearcher` | Class method: fit linear model from measured (distance, rssi) pairs |

### `SearchAction`

Returned by `report_ping()`.

| Field | Type | Description |
|-------|------|-------------|
| `action_type` | str | `"move_and_ping"`, `"move_to_estimate"`, or `"found"` |
| `target` | (x, y) or None | Where to drive next (None when found) |
| `estimate` | (x, y) or None | Current best estimate of LTV position (available after 3 pings) |
| `phase` | str | `"triangulating"`, `"approaching"`, or `"found"` |
| `confidence` | float or None | RMS residual of trilateration fit (lower is better) |

### How "found" works

The searcher declares `action_type="found"` when the **RSSI-estimated distance** from the latest ping is within `found_distance_m`. This is not the true distance -- it depends on your RSSI model being well-calibrated. If the searcher isn't finding the LTV, try:

- Re-calibrating the RSSI model (see above)
- Increasing `found_distance_m` (e.g. 50.0) if your RSSI readings are noisy

## Test Simulation

A built-in test simulator lets you try the search without DUST or TSS. It requires the optional `[viz]` dependencies.

```bash
pip install /path/to/LTV-Search[viz]
```

```bash
python main.py                           # visualization + test sim (default)
python main.py --no-viz                  # headless
python main.py --config config.yaml      # custom config
```

### CLI options

| Flag | Description |
|------|-------------|
| `--no-viz` | Run without Pygame window |
| `--config PATH` | Path to YAML config file |
| `--test-sim` | Use test simulator (default) |
| `--no-test-sim` | Use TSS backend |

### Environment variables

| Variable | Description |
|----------|-------------|
| `LTV_TEST_SIM_UNLIMITED_PINGS=1` | Unlimited pings in test sim |
| `LTV_TEST_SIM_SEED=42` | Reproducible seed |
| `LTV_MAX_PINGS=10` | Max ping count |
| `LTV_FOUND_DISTANCE_M=30` | Distance threshold for found |
| `LTV_RSSI_MODEL=linear` | RSSI model type |
| `LTV_RSSI_LINEAR_SLOPE=-0.075` | Linear model slope |
| `LTV_RSSI_LINEAR_INTERCEPT=0.0` | Linear model intercept |
| `LTV_RSSI_NOISE_STD=1.0` | RSSI noise std deviation |
| `LTV_SEARCH_RADIUS_M=1500` | Search area radius |

## How It Works

1. **Ping at LKP** -- get distance estimate from RSSI
2. **Move to two more positions** forming a triangle -- ping at each to get three range circles
3. **Solve trilateration** -- intersect the circles to estimate LTV location
4. **Drive toward estimate, ping to refine** -- each additional ping adds a circle and re-solves via weighted least-squares
5. **LTV found** when estimated distance drops below `found_distance_m`

## Project Layout

| File | Description |
|------|-------------|
| `ltv_search/searcher.py` | **Public API**: `LTVSearcher` class (standalone, no Pygame) |
| `ltv_search/rssi.py` | RSSI to/from distance (linear and path-loss models) |
| `ltv_search/trilateration.py` | Weighted circle intersection solver |
| `ltv_search/search.py` | Search state machine + `SharedState` (uses `LTVSearcher` internally) |
| `ltv_search/visualization.py` | Pygame dark-mode UI |
| `ltv_search/environment.py` | Adapter interface (ABC) |
| `ltv_search/test_simulator.py` | Test simulation adapter |
| `ltv_search/config.py` | Configuration loading |
| `main.py` | Entry point (config, adapter, viz, restart loop) |
| `tests/` | Unit tests |

## Tests

```bash
python -m unittest discover -s tests -v
```
