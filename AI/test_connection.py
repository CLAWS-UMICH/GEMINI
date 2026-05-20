#!/usr/bin/env python3
"""
UDP rover/TSS socket diagnostic.

Run:
  python udp_rover_diag.py

Notes:
- UDP "connect" does not prove the server is alive. It only sets the default
  remote address and lets the OS report some ICMP errors as socket errors.
- This script logs every send/recv, timeout, and socket OSError so you can see
  exactly which command or idle interval triggers the issue.
"""

import json
import socket
import struct
import time
import traceback
from datetime import datetime


# =============================
# Config
# =============================
TSS_HOST = "192.168.50.110"
TSS_PORT = 14141

SOCKET_TIMEOUT_SECONDS = 3.0
INITIAL_WAIT_SECONDS = 60.0
BETWEEN_TESTS_SECONDS = 60.0

USE_CONNECTED_UDP = True
REOPEN_SOCKET_AFTER_SOCKET_ERROR = True

# Set this True only if it is safe for the rover to receive movement commands.
ENABLE_MOVEMENT_TESTS = False

# Optional local bind. Leave None for normal ephemeral source port.
LOCAL_BIND = None
# LOCAL_BIND = ("0.0.0.0", 0)

RECV_SIZE = 8192


# =============================
# TSS command IDs from rover_control.py
# =============================
GET_ROVER_JSON = 0
GET_EVA_JSON = 1
GET_LTV_JSON = 2
GET_LTV_ERRORS_JSON = 3

CMD_CABIN_HEATING = 1103
CMD_CABIN_COOLING = 1104
CMD_LIGHTS = 1106
CMD_BRAKES = 1107
CMD_THROTTLE = 1109
CMD_STEERING = 1110
CMD_PING = 2050
CMD_DEBUG_PING = 2051


# =============================
# Logging/helpers
# =============================
def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] {msg}", flush=True)


def sleep_with_log(seconds, reason):
    log(f"waiting {seconds:.1f}s: {reason}")
    end = time.monotonic() + seconds
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(5.0, remaining))


def make_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(SOCKET_TIMEOUT_SECONDS)

    if LOCAL_BIND is not None:
        sock.bind(LOCAL_BIND)
        log(f"bound local UDP socket to {sock.getsockname()}")

    if USE_CONNECTED_UDP:
        log(f"UDP connect() to {(TSS_HOST, TSS_PORT)}")
        sock.connect((TSS_HOST, TSS_PORT))
        log(f"local socket after connect: {sock.getsockname()}")
    else:
        log(f"using UDP sendto() to {(TSS_HOST, TSS_PORT)}")
        log(f"local socket before first send: {sock.getsockname()}")

    return sock


def close_socket(sock):
    try:
        log("closing socket")
        sock.close()
    except Exception as exc:
        log(f"socket close failed: {type(exc).__name__}: {exc}")


def send_packet(sock, packet, label, expect_response=True, response_size=RECV_SIZE):
    started = time.monotonic()
    log(f"SEND {label}: {len(packet)} bytes: {packet.hex(' ')}")

    try:
        if USE_CONNECTED_UDP:
            sent = sock.send(packet)
        else:
            sent = sock.sendto(packet, (TSS_HOST, TSS_PORT))
        log(f"SENT {label}: {sent} bytes")

        if not expect_response:
            log(f"NO-RECV {label}: configured not to wait for response")
            return None

        response = sock.recv(response_size)
        elapsed_ms = (time.monotonic() - started) * 1000.0
        log(f"RECV {label}: {len(response)} bytes after {elapsed_ms:.1f}ms: {response[:160].hex(' ')}")

        if response:
            preview = response[:300]
            try:
                decoded = preview.decode("utf-8", errors="replace")
                log(f"TEXT {label}: {decoded!r}")
                if decoded[:1] in "{[":
                    parsed = json.loads(response.decode("utf-8", errors="replace"))
                    if isinstance(parsed, dict):
                        log(f"JSON {label}: keys={list(parsed.keys())[:20]}")
            except Exception:
                pass

        return response

    except socket.timeout:
        elapsed_ms = (time.monotonic() - started) * 1000.0
        log(f"TIMEOUT {label}: no response after {elapsed_ms:.1f}ms")
        return None

    except OSError as exc:
        elapsed_ms = (time.monotonic() - started) * 1000.0
        log(f"SOCKET-ERROR {label}: after {elapsed_ms:.1f}ms: {type(exc).__name__}: errno={getattr(exc, 'errno', None)} msg={exc}")
        log(traceback.format_exc().rstrip())
        raise

    except Exception as exc:
        elapsed_ms = (time.monotonic() - started) * 1000.0
        log(f"ERROR {label}: after {elapsed_ms:.1f}ms: {type(exc).__name__}: {exc}")
        log(traceback.format_exc().rstrip())
        raise


def packet_get(command_id):
    return struct.pack(">II", int(time.time()), int(command_id))


def packet_float(command_id, value):
    return struct.pack(">IIf", int(time.time()), int(command_id), float(value))


def ack_ok(response):
    if response is None:
        return False
    if len(response) < 4:
        return False
    return any(response[:4])


def run_test(sock, test):
    name = test["name"]
    kind = test["kind"]
    command = test["command"]
    value = test.get("value")

    if kind == "get":
        packet = packet_get(command)
        response = send_packet(sock, packet, name)
        return response is not None

    if kind == "float":
        packet = packet_float(command, value)
        response = send_packet(sock, packet, name, response_size=64)
        ok = ack_ok(response)
        log(f"ACK {name}: {'OK' if ok else 'BAD/MISSING'}")
        return ok

    raise ValueError(f"unknown test kind: {kind}")


def main():
    tests = [
        # Basic telemetry reads. These are usually safest and reveal whether
        # request/response UDP is working before command ACKs are involved.
        {"name": "get rover json", "kind": "get", "command": GET_ROVER_JSON},
        {"name": "get ltv json", "kind": "get", "command": GET_LTV_JSON},
        {"name": "get eva json", "kind": "get", "command": GET_EVA_JSON},
        {"name": "get ltv errors json", "kind": "get", "command": GET_LTV_ERRORS_JSON},

        # Low-risk actuator commands.
        {"name": "lights on", "kind": "float", "command": CMD_LIGHTS, "value": 1.0},
        {"name": "lights off", "kind": "float", "command": CMD_LIGHTS, "value": 0.0},
        {"name": "brakes on", "kind": "float", "command": CMD_BRAKES, "value": 1.0},
        {"name": "brakes off", "kind": "float", "command": CMD_BRAKES, "value": 0.0},
        {"name": "heating off", "kind": "float", "command": CMD_CABIN_HEATING, "value": 0.0},
        {"name": "cooling off", "kind": "float", "command": CMD_CABIN_COOLING, "value": 0.0},
        {"name": "ping", "kind": "float", "command": CMD_PING, "value": 1.0},
        {"name": "debug ping", "kind": "float", "command": CMD_DEBUG_PING, "value": 1.0},

        # Zero movement commands, normally safe.
        {"name": "steering zero", "kind": "float", "command": CMD_STEERING, "value": 0.0},
        {"name": "throttle zero", "kind": "float", "command": CMD_THROTTLE, "value": 0.0},
    ]

    movement_tests = [
        {"name": "steering small left", "kind": "float", "command": CMD_STEERING, "value": -0.2},
        {"name": "steering zero after left", "kind": "float", "command": CMD_STEERING, "value": 0.0},
        {"name": "steering small right", "kind": "float", "command": CMD_STEERING, "value": 0.2},
        {"name": "steering zero after right", "kind": "float", "command": CMD_STEERING, "value": 0.0},
        {"name": "throttle tiny forward", "kind": "float", "command": CMD_THROTTLE, "value": 5.0},
        {"name": "throttle zero after forward", "kind": "float", "command": CMD_THROTTLE, "value": 0.0},
    ]

    combos = [
        [
            {"name": "combo safe brakes on", "kind": "float", "command": CMD_BRAKES, "value": 1.0},
            {"name": "combo safe throttle zero", "kind": "float", "command": CMD_THROTTLE, "value": 0.0},
            {"name": "combo safe steering zero", "kind": "float", "command": CMD_STEERING, "value": 0.0},
            {"name": "combo safe lights on", "kind": "float", "command": CMD_LIGHTS, "value": 1.0},
        ],
        [
            {"name": "combo telemetry rover", "kind": "get", "command": GET_ROVER_JSON},
            {"name": "combo ping", "kind": "float", "command": CMD_PING, "value": 1.0},
            {"name": "combo telemetry ltv", "kind": "get", "command": GET_LTV_JSON},
        ],
        [
            {"name": "combo restore lights off", "kind": "float", "command": CMD_LIGHTS, "value": 0.0},
            {"name": "combo restore brakes off", "kind": "float", "command": CMD_BRAKES, "value": 0.0},
            {"name": "combo restore throttle zero", "kind": "float", "command": CMD_THROTTLE, "value": 0.0},
            {"name": "combo restore steering zero", "kind": "float", "command": CMD_STEERING, "value": 0.0},
        ],
    ]

    if ENABLE_MOVEMENT_TESTS:
        tests.extend(movement_tests)

    log("starting UDP diagnostic")
    log(f"target={(TSS_HOST, TSS_PORT)} timeout={SOCKET_TIMEOUT_SECONDS}s connected_udp={USE_CONNECTED_UDP}")

    sock = make_socket()

    try:
        sleep_with_log(INITIAL_WAIT_SECONDS, "initial idle period after UDP connect")

        results = []

        for test in tests:
            try:
                ok = run_test(sock, test)
                results.append((test["name"], ok, None))
            except OSError as exc:
                results.append((test["name"], False, f"{type(exc).__name__}: {exc}"))
                if REOPEN_SOCKET_AFTER_SOCKET_ERROR:
                    close_socket(sock)
                    sleep_with_log(2.0, "reopening after socket error")
                    sock = make_socket()
                else:
                    raise

            sleep_with_log(BETWEEN_TESTS_SECONDS, f"interval after {test['name']}")

        for combo_index, combo in enumerate(combos, start=1):
            log(f"START COMBO {combo_index}: {len(combo)} commands back-to-back")
            combo_ok = True

            for test in combo:
                try:
                    ok = run_test(sock, test)
                    combo_ok = combo_ok and ok
                except OSError as exc:
                    combo_ok = False
                    results.append((f"combo {combo_index}: {test['name']}", False, f"{type(exc).__name__}: {exc}"))
                    if REOPEN_SOCKET_AFTER_SOCKET_ERROR:
                        close_socket(sock)
                        sleep_with_log(2.0, "reopening after combo socket error")
                        sock = make_socket()
                    else:
                        raise
                    break

                # Short pause inside combos: enough to avoid packet pileups,
                # but still tests command sequences more aggressively.
                time.sleep(1.0)

            results.append((f"combo {combo_index}", combo_ok, None))
            sleep_with_log(BETWEEN_TESTS_SECONDS, f"interval after combo {combo_index}")

        log("SUMMARY")
        for name, ok, err in results:
            if err:
                log(f"  FAIL {name}: {err}")
            else:
                log(f"  {'PASS' if ok else 'WARN'} {name}")

    finally:
        # Try to leave rover in a neutral-ish state.
        try:
            log("final neutral commands")
            send_packet(sock, packet_float(CMD_THROTTLE, 0.0), "final throttle zero", response_size=64)
            send_packet(sock, packet_float(CMD_STEERING, 0.0), "final steering zero", response_size=64)
            send_packet(sock, packet_float(CMD_BRAKES, 0.0), "final brakes off", response_size=64)
        except Exception as exc:
            log(f"final neutral commands failed: {type(exc).__name__}: {exc}")

        close_socket(sock)
        log("done")


if __name__ == "__main__":
    main()