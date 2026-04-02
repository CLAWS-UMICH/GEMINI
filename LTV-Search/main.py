#!/usr/bin/env python3
"""LTV Search v2: run the trilateration search with test simulation or TSS."""
import argparse
import random
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ltv_search.config import load_config
from ltv_search.search import SharedState, run_search
from ltv_search.test_simulator import TestSimulatorAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description="LTV Search v2 (trilateration)")
    parser.add_argument("--no-viz", action="store_true", help="Run without Pygame visualization")
    parser.add_argument("--config", type=Path, default=None, help="Path to config YAML")
    parser.add_argument("--test-sim", action="store_true", help="Use test simulation (default)")
    parser.add_argument("--no-test-sim", action="store_false", dest="test_sim", help="Use TSS backend")
    parser.set_defaults(test_sim=True)
    args = parser.parse_args()

    config_path = args.config or (Path(__file__).parent / "config.yaml")
    config = load_config(config_path if config_path.exists() else None)
    config.enable_viz = not args.no_viz
    config.generate_test_simulation = args.test_sim
    if config.generate_test_simulation:
        config.ping_min_interval_sec = config.test_sim_ping_interval_sec

    if not config.enable_viz:
        adapter = TestSimulatorAdapter(config)
        shared = SharedState()
        shared.ping_limit = config.max_pings
        run_search(adapter, config, shared)
        if shared.found and shared.found_coords:
            print("LTV found at", shared.found_coords)
        else:
            print(f"LTV not found (phase: {shared.phase})")
        print("Press Enter to exit.")
        input()
        sys.exit(0)

    from ltv_search.visualization import run_visualization

    user_seed = config.test_sim_seed
    while True:
        seed = user_seed if user_seed is not None else random.randint(0, 999999)
        config.test_sim_seed = seed

        adapter = TestSimulatorAdapter(config)

        shared = SharedState()
        shared.ping_limit = config.max_pings
        shared.seed = seed
        shared.advance_requested = threading.Event()
        shared.autoplay = False

        search_thread = threading.Thread(target=run_search, args=(adapter, config, shared))
        search_thread.daemon = True
        search_thread.start()

        result = run_visualization(config, shared, adapter if config.generate_test_simulation else None)

        if shared.found and shared.found_coords:
            print(f"[seed={seed}] LTV found at", shared.found_coords)
        else:
            print(f"[seed={seed}] LTV not found (phase: {shared.phase})")

        if result == "restart":
            user_seed = None
            continue
        break

    print("Press Enter to exit.")
    input()
    sys.exit(0)


if __name__ == "__main__":
    main()
