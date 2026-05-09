#!/usr/bin/env python3
"""Simple TSS rover socket helpers.

This talks to TSS over UDP. DUST should already be connected to TSS.
"""

from __future__ import annotations

import csv
import json
import math
import socket
import struct
import threading
import time
from datetime import datetime
from pathlib import Path

import socketio


SERVER_HOST = "172.24.119.191"
SERVER_PORT = 14141
SOCKET_TIMEOUT = 1.0
REMOTE_INITIAL_TELEMETRY_TIMEOUT = 3.0
REMOTE_SERVER_ENABLED = False
REMOTE_SERVER_URL = "http://127.0.0.1:5001"

LIDAR_LOG_PATH = "lidar_log.csv"
LIDAR_LOG_HZ = 0.0
LIDAR_LOG_ALL = False
LIDAR_MAX_VALID_CM = 1000.0

GET_ROVER_JSON = 0
GET_EVA_JSON = 1
GET_LTV_JSON = 2
GET_LTV_ERRORS_JSON = 3
JSON_DEBUG_DIR = Path("runs") / "json_decode_failures"
JSON_FETCH_RETRIES = 3

CMD_CABIN_HEATING = 1103
CMD_CABIN_COOLING = 1104
CMD_LIGHTS = 1106
CMD_BRAKES = 1107
CMD_THROTTLE = 1109
CMD_STEERING = 1110
STEERING_COMMAND_SIGN = -1.0
CMD_PING = 2050
CMD_DEBUG_PING = 2051

REMOTE_COMMAND_EVENT_BY_ID = {
    CMD_CABIN_HEATING: "rover-heating",
    CMD_CABIN_COOLING: "rover-cooling",
    CMD_LIGHTS: "rover-headlights",
    CMD_BRAKES: "rover-brakes",
    CMD_THROTTLE: "rover-throttle",
    CMD_STEERING: "rover-steering",
    CMD_PING: "rover-ping",
    CMD_DEBUG_PING: "rover-debug-ping",
}


def configure_remote_server(enabled: bool, url: str | None = None) -> None:
    global REMOTE_SERVER_ENABLED, REMOTE_SERVER_URL
    REMOTE_SERVER_ENABLED = bool(enabled)
    if url:
        REMOTE_SERVER_URL = str(url)


class RemoteRoverClient:
    def __init__(self, url: str) -> None:
        self.url = str(url)
        self.sio = socketio.Client(reconnection=True)
        self._state_lock = threading.Lock()
        self._matrix_emit_lock = threading.Lock()
        self._last_matrix_emit_monotonic = 0.0
        self._connected_event = threading.Event()
        self._rover_event = threading.Event()
        self._ltv_event = threading.Event()
        self._eva_event = threading.Event()
        self._ltv_errors_event = threading.Event()
        self._latest_rover: dict | None = None
        self._latest_ltv: dict | None = None
        self._latest_eva: dict | None = None
        self._latest_ltv_errors: dict | None = None

        @self.sio.event
        def connect() -> None:
            self._connected_event.set()

        @self.sio.event
        def disconnect() -> None:
            self._connected_event.clear()

        @self.sio.on("rover-telemetry")
        def on_rover_telemetry(data) -> None:
            payload = dict(data) if isinstance(data, dict) else {}
            with self._state_lock:
                self._latest_rover = payload
            self._rover_event.set()

        @self.sio.on("ltv-telemetry")
        def on_ltv_telemetry(data) -> None:
            payload = dict(data) if isinstance(data, dict) else {}
            with self._state_lock:
                self._latest_ltv = payload
            self._ltv_event.set()

        @self.sio.on("eva-telemetry")
        def on_eva_telemetry(data) -> None:
            payload = dict(data) if isinstance(data, dict) else {}
            with self._state_lock:
                self._latest_eva = payload
            self._eva_event.set()

        @self.sio.on("ltv-errors-telemetry")
        def on_ltv_errors_telemetry(data) -> None:
            payload = dict(data) if isinstance(data, dict) else {}
            with self._state_lock:
                self._latest_ltv_errors = payload
            self._ltv_errors_event.set()

    def connect(self, timeout_seconds: float = 5.0) -> None:
        self.sio.connect(self.url, wait=True, wait_timeout=timeout_seconds)
        if not self._connected_event.wait(timeout_seconds):
            raise RuntimeError(f"Timed out connecting to remote rover server at {self.url}")

    def close(self) -> None:
        if self.sio.connected:
            self.sio.disconnect()

    def emit(self, event_name: str, payload=None) -> bool:
        self.sio.emit(event_name, payload)
        return True

    def _payload_event_for_get(self, command: int) -> tuple[str, threading.Event, str]:
        mapping = {
            GET_ROVER_JSON: ("_latest_rover", self._rover_event, "rover"),
            GET_LTV_JSON: ("_latest_ltv", self._ltv_event, "ltv"),
            GET_EVA_JSON: ("_latest_eva", self._eva_event, "eva"),
            GET_LTV_ERRORS_JSON: ("_latest_ltv_errors", self._ltv_errors_event, "ltv-errors"),
        }
        if command not in mapping:
            raise RuntimeError(f"Remote server does not support GET command {command}")
        return mapping[command]

    def get_json_for_command(self, command: int, timeout_seconds: float = SOCKET_TIMEOUT) -> dict:
        attr_name, ready_event, label = self._payload_event_for_get(command)
        with self._state_lock:
            payload = getattr(self, attr_name)
            if isinstance(payload, dict):
                return dict(payload)
        effective_timeout = max(float(timeout_seconds), REMOTE_INITIAL_TELEMETRY_TIMEOUT)
        if not ready_event.wait(effective_timeout):
            raise RuntimeError(f"Timed out waiting for remote {label} telemetry from {self.url}")
        with self._state_lock:
            payload = getattr(self, attr_name)
            if not isinstance(payload, dict):
                raise RuntimeError(f"Remote {label} telemetry is unavailable")
            return dict(payload)


def open_rover_socket() -> socket.socket:
    if REMOTE_SERVER_ENABLED:
        client = RemoteRoverClient(REMOTE_SERVER_URL)
        client.connect(timeout_seconds=max(5.0, SOCKET_TIMEOUT))
        return client
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(SOCKET_TIMEOUT)
    return sock


def close_rover_socket(sock: socket.socket) -> None:
    if isinstance(sock, RemoteRoverClient):
        sock.close()
        return
    sock.close()


def server_address() -> tuple[str, int]:
    return (SERVER_HOST, SERVER_PORT)


def unix_timestamp() -> int:
    return int(time.time())


def clamp_throttle(value: float) -> float:
    return max(-100.0, min(100.0, float(value)))


def clamp_steering(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def send_packet(sock: socket.socket, packet: bytes, response_size: int = 8192) -> bytes:
    sock.sendto(packet, server_address())
    response, _ = sock.recvfrom(response_size)
    return response


def send_float_command(sock: socket.socket, command: int, value: float) -> bool:
    if isinstance(sock, RemoteRoverClient):
        event_name = REMOTE_COMMAND_EVENT_BY_ID.get(int(command))
        if event_name is None:
            raise RuntimeError(f"Remote server does not support command {command}")
        payload = float(value)
        if int(command) == CMD_BRAKES:
            return sock.emit(event_name, bool(payload >= 0.5))
        if int(command) in (CMD_PING, CMD_DEBUG_PING) and abs(payload - 1.0) <= 1e-6:
            return sock.emit(event_name, None)
        return sock.emit(event_name, payload)
    packet = struct.pack(">IIf", unix_timestamp(), command, float(value))
    response = send_packet(sock, packet, response_size=64)
    if len(response) < 4:
        raise RuntimeError(f"Incomplete ACK for command {command}: {response!r}")
    return any(response[:4])


def send_get_command(sock: socket.socket, command: int) -> bytes:
    if isinstance(sock, RemoteRoverClient):
        payload = sock.get_json_for_command(int(command), timeout_seconds=SOCKET_TIMEOUT)
        return json.dumps(payload).encode("utf-8")
    packet = struct.pack(">II", unix_timestamp(), command)
    return send_packet(sock, packet)


def send_occupancy_matrix(
    sock: socket.socket,
    *,
    planner,
    rover_xy: tuple[float, float],
    goal_xy: tuple[float, float] | None = None,
    path_world: list[tuple[float, float]] | None = None,
    min_interval_seconds: float = 1.0,
) -> bool:
    if not isinstance(sock, RemoteRoverClient):
        return False

    now = time.monotonic()
    with sock._matrix_emit_lock:
        if (now - sock._last_matrix_emit_monotonic) < float(min_interval_seconds):
            return False

        width = int(getattr(planner, "width_cells", 0))
        height = int(getattr(planner, "height_cells", 0))
        grid = getattr(planner, "grid", None)
        if width <= 0 or height <= 0 or not isinstance(grid, list):
            return False

        matrix = [
            [
                1 if int(grid[row_idx][col_idx]) != 0 else 0
                for col_idx in range(width)
            ]
            for row_idx in range(height)
        ]

        for point_x, point_y in path_world or []:
            cell_x, cell_y = planner.world_to_cell(float(point_x), float(point_y))
            if 0 <= cell_x < width and 0 <= cell_y < height:
                matrix[cell_y][cell_x] = 2

        if goal_xy is not None:
            goal_cell_x, goal_cell_y = planner.world_to_cell(float(goal_xy[0]), float(goal_xy[1]))
            if 0 <= goal_cell_x < width and 0 <= goal_cell_y < height:
                matrix[goal_cell_y][goal_cell_x] = 3

        rover_cell_x, rover_cell_y = planner.world_to_cell(float(rover_xy[0]), float(rover_xy[1]))
        if 0 <= rover_cell_x < width and 0 <= rover_cell_y < height:
            matrix[rover_cell_y][rover_cell_x] = 4

        emitted = sock.emit("matrix", matrix)
        if emitted:
            sock._last_matrix_emit_monotonic = now
        return emitted


def extract_json_bytes(response: bytes) -> bytes:
    stripped = response.lstrip()
    payload = stripped if stripped.startswith(b"{") else (response[8:] if len(response) > 8 else response)
    start = -1
    search_at = 0
    while True:
        candidate = payload.find(b"{", search_at)
        if candidate == -1:
            break
        next_idx = candidate + 1
        while next_idx < len(payload) and payload[next_idx] in b" \t\r\n":
            next_idx += 1
        if next_idx < len(payload) and payload[next_idx] in (ord('"'), ord("}")):
            start = candidate
            break
        search_at = candidate + 1
    if start == -1:
        raise RuntimeError(f"Could not locate JSON payload in response: {response[:32]!r}")
    return payload[start:].split(b"\x00", 1)[0]


class JsonResponseDecodeError(RuntimeError):
    pass


def dump_json_decode_failure(
    *,
    response: bytes,
    payload: bytes,
    command: int,
    label: str,
    exc: BaseException,
) -> None:
    JSON_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    stem = JSON_DEBUG_DIR / f"{label}_{command}_{timestamp}_{time.monotonic_ns()}"
    (stem.with_suffix(".bin")).write_bytes(response)
    (stem.with_suffix(".json_fragment")).write_bytes(payload)
    control_bytes = [
        (idx, byte)
        for idx, byte in enumerate(payload)
        if byte < 0x20 and byte not in (0x09, 0x0A, 0x0D)
    ][:20]
    print(
        f"JSON decode failed for {label} command {command}: {exc}. "
        f"response_len={len(response)} payload_len={len(payload)} "
        f"payload_prefix={payload[:16]!r} first_control_bytes={control_bytes} dump={stem}"
    )


def decode_json_response(response: bytes, *, command: int, label: str) -> dict:
    try:
        payload = extract_json_bytes(response)
    except RuntimeError as exc:
        dump_json_decode_failure(
            response=response,
            payload=response,
            command=command,
            label=label,
            exc=exc,
        )
        raise JsonResponseDecodeError(str(exc)) from exc

    try:
        text = payload.decode("utf-8")
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        text = payload.decode("utf-8", errors="replace")
        decoder = json.JSONDecoder()
        starts = [idx for idx, char in enumerate(text) if char == "{"]
        for start in starts[1:]:
            try:
                parsed, end = decoder.raw_decode(text[start:])
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(parsed, dict):
                print(
                    f"Recovered malformed {label} JSON for command {command}: "
                    f"skipped {start} leading chars before valid object; trailing_chars={len(text) - start - end}"
                )
                return parsed

        dump_json_decode_failure(
            response=response,
            payload=payload,
            command=command,
            label=label,
            exc=exc,
        )
        raise JsonResponseDecodeError(str(exc)) from exc


def fetch_json_with_retries(sock: socket.socket, command: int, label: str) -> dict:
    last_exc: JsonResponseDecodeError | None = None
    for attempt_idx in range(JSON_FETCH_RETRIES + 1):
        response = send_get_command(sock, command)
        try:
            return decode_json_response(response, command=command, label=label)
        except JsonResponseDecodeError as exc:
            last_exc = exc
            if attempt_idx >= JSON_FETCH_RETRIES:
                break
            print(
                f"Retrying {label} JSON command {command} after malformed response "
                f"({attempt_idx + 1}/{JSON_FETCH_RETRIES})"
            )
            time.sleep(0.02)
    raise last_exc if last_exc is not None else RuntimeError(f"Could not fetch {label} JSON")


def fetch_rover_json(sock: socket.socket) -> dict:
    return fetch_json_with_retries(sock, GET_ROVER_JSON, "ROVER")


def fetch_ltv_json(sock: socket.socket) -> dict:
    return fetch_json_with_retries(sock, GET_LTV_JSON, "LTV")


def sanitize_lidar_value(raw_value: object) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return -1.0

    if math.isnan(value) or math.isinf(value):
        return -1.0
    if value == -1.0:
        return -1.0
    if value < 0.0:
        return -1.0
    if value > LIDAR_MAX_VALID_CM:
        return -1.0
    return value


def sanitize_lidar_scan(raw_lidar: object) -> list[float] | None:
    if not isinstance(raw_lidar, list):
        return None
    return [sanitize_lidar_value(value) for value in raw_lidar]


def fetch_rover_telemetry(sock: socket.socket) -> dict:
    rover = fetch_rover_json(sock)
    telemetry = rover.get("pr_telemetry")
    if not isinstance(telemetry, dict):
        raise RuntimeError("ROVER.json did not contain pr_telemetry")
    sanitized_lidar = sanitize_lidar_scan(telemetry.get("lidar"))
    if sanitized_lidar is not None:
        telemetry["lidar"] = sanitized_lidar
    return telemetry


def is_dust_connected(sock: socket.socket) -> bool:
    return bool(fetch_rover_telemetry(sock).get("dust_connected", False))


def wait_for_dust(sock: socket.socket, timeout_seconds: float = 15.0, poll_seconds: float = 0.5) -> bool:
    end_time = time.monotonic() + timeout_seconds
    while time.monotonic() < end_time:
        try:
            if is_dust_connected(sock):
                return True
        except RuntimeError:
            pass
        time.sleep(max(0.0, poll_seconds))
    try:
        return is_dust_connected(sock)
    except RuntimeError:
        return False


def set_throttle(sock: socket.socket, value: float) -> bool:
    return send_float_command(sock, CMD_THROTTLE, clamp_throttle(value))


def set_steering(sock: socket.socket, value: float) -> bool:
    # DUST steering command sign is opposite the math/control convention used locally.
    return send_float_command(sock, CMD_STEERING, clamp_steering(value) * STEERING_COMMAND_SIGN)


def set_brakes(sock: socket.socket, enabled: bool) -> bool:
    return send_float_command(sock, CMD_BRAKES, 1.0 if enabled else 0.0)


def set_lights(sock: socket.socket, enabled: bool) -> bool:
    return send_float_command(sock, CMD_LIGHTS, 1.0 if enabled else 0.0)


def set_cabin_heating(sock: socket.socket, enabled: bool) -> bool:
    return send_float_command(sock, CMD_CABIN_HEATING, 1.0 if enabled else 0.0)


def set_cabin_cooling(sock: socket.socket, enabled: bool) -> bool:
    return send_float_command(sock, CMD_CABIN_COOLING, 1.0 if enabled else 0.0)


def read_lidar(sock: socket.socket) -> list[float]:
    lidar = fetch_rover_telemetry(sock).get("lidar")
    if not isinstance(lidar, list):
        raise RuntimeError("ROVER.json did not contain a lidar array")
    return [float(value) for value in lidar]


def log_lidar_fast(sock: socket.socket, output_path: str, poll_hz: float = 0.0, log_all: bool = False) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    delay = 0.0 if poll_hz <= 0 else 1.0 / poll_hz
    last_scan: list[float] | None = None

    with path.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        if csv_file.tell() == 0:
            writer.writerow(["unix_time", "iso_time", "lidar_json"])

        while True:
            scan = read_lidar(sock)
            if log_all or scan != last_scan:
                now = time.time()
                iso_time = datetime.now().isoformat(timespec="milliseconds")
                writer.writerow([f"{now:.3f}", iso_time, json.dumps(scan, separators=(",", ":"))])
                csv_file.flush()
                print(f"{iso_time} lidar={scan}")
                last_scan = scan

            if delay > 0:
                time.sleep(delay)


def run_example() -> None:
    sock = open_rover_socket()
    try:
        print(f"Logging lidar to {LIDAR_LOG_PATH}")
        log_lidar_fast(sock, LIDAR_LOG_PATH, poll_hz=LIDAR_LOG_HZ, log_all=LIDAR_LOG_ALL)
    finally:
        close_rover_socket(sock)


if __name__ == "__main__":
    run_example()
