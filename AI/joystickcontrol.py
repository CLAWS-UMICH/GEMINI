#!/usr/bin/env python3
"""Minimal joystick control for the rover over TSS."""

from __future__ import annotations

import time

import pygame

from rover_control import (
    close_rover_socket,
    open_rover_socket,
    set_brakes,
    set_steering,
    set_throttle,
    wait_for_dust,
)


DEADZONE = 0.12
MAX_THROTTLE = 100.0
LOOP_HZ = 20.0
AXIS_STEERING = 0
AXIS_THROTTLE = 1


def apply_deadzone(value: float, deadzone: float = DEADZONE) -> float:
    return 0.0 if abs(value) < deadzone else value


def main() -> None:
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        raise RuntimeError("No joystick detected.")

    joystick = pygame.joystick.Joystick(0)
    joystick.init()

    sock = open_rover_socket()
    last_throttle = None
    last_steering = None
    delay = 1.0 / LOOP_HZ

    try:
        if not wait_for_dust(sock):
            raise RuntimeError("DUST is not connected to TSS.")

        print(f"Joystick: {joystick.get_name()}")
        print("Left stick Y = throttle, left stick X = steering, Ctrl+C to stop.")

        while True:
            pygame.event.pump()

            steering = -apply_deadzone(joystick.get_axis(AXIS_STEERING))
            throttle = -apply_deadzone(joystick.get_axis(AXIS_THROTTLE)) * MAX_THROTTLE

            if last_throttle is None or abs(throttle - last_throttle) >= 1.0:
                set_throttle(sock, throttle)
                last_throttle = throttle

            if last_steering is None or abs(steering - last_steering) >= 0.02:
                set_steering(sock, steering)
                last_steering = steering

            set_brakes(sock, abs(throttle) < 1.0)
            time.sleep(delay)
    finally:
        try:
            set_throttle(sock, 0.0)
            set_steering(sock, 0.0)
            set_brakes(sock, True)
        finally:
            close_rover_socket(sock)
            pygame.quit()


if __name__ == "__main__":
    main()