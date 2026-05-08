import socket
import struct
import json
import time
from typing import Any, Dict, Optional


TSS_DEFAULT_UDP_PORT = 14141


class TSSUdpClient:
    def __init__(self, host: str, port: int = TSS_DEFAULT_UDP_PORT, timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def _send_packet(self, command: int, value: Optional[float] = None) -> bytes:
        # build and send a udp packet using big endian
        # 4 bytes: UNIX timestamp (uint32 big endian)
        # 4 bytes: command number (uint32 big endian)
        # 4 bytes: optional float32 input value

        timestamp = int(time.time())

        if value is None:
            payload = struct.pack(">II", timestamp, command)
            #>II means big endian, int, int
        else:
            payload = struct.pack(">IIf", timestamp, command, float(value))
            #big endian, int, int, float

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout)
            sock.sendto(payload, (self.host, self.port))
            data, _ = sock.recvfrom(65535)
            return data


    def fetch_rover_json(self) -> Dict[str, Any]:
        # fetch the rover.json payload (command 0) and return it as a dict.
        raw = self._send_packet(0)
        return json.loads(raw.decode("utf-8"))

    def fetch_eva_json(self) -> Dict[str, Any]:
        # fetch the eva.json payload (command 1) and return it as a dict.
        raw = self._send_packet(1)
        return json.loads(raw.decode("utf-8"))

    def fetch_ltv_json(self) -> Dict[str, Any]:
        # fetch the ltv.json payload (command 2) and return it as a dict.
        raw = self._send_packet(2)
        return json.loads(raw.decode("utf-8"))
    
    def fetch_ltv_errors_json(self) -> Dict[str, Any]:
        # fetch the ltv.errors.json payload (command 3) and return it as a dict.
        raw = self._send_packet(3)
        return json.loads(raw.decode("utf-8"))

    def set_brakes(self, engaged: bool) -> Dict[str, Any]:
        # command 1107: brakes, float: 0.0 or 1.0.
        value = 1.0 if engaged else 0.0
        return self._send_bool_command(1107, "brakes", value)

    def set_throttle(self, value: float) -> Dict[str, Any]:
        # command 1109: throttle, float: -100.0 to 100.0.
        return self._send_bool_command(1109, "throttle", value)

    def set_steering(self, value: float) -> Dict[str, Any]:
        # command 1110: steering, float: -1.0 to 1.0.
        return self._send_bool_command(1110, "steering", value)

    def set_heating(self, value: float) -> Dict[str, Any]:
        # command 1103: heating, float: 0.0 to 1.0.
        return self._send_bool_command(1103, "heating", value)

    def set_cooling(self, value: float) -> Dict[str, Any]:
        # command 1104: cooling, float: 0.0 to 1.0.
        return self._send_bool_command(1104, "cooling", value)

    def set_headlights(self, value: float) -> Dict[str, Any]:
        # command 1106: headlights, float: 0.0 to 1.0.
        return self._send_bool_command(1106, "headlights", value)

    def send_ping(self, value: float = 1.0) -> Dict[str, Any]:
        # command 2050: ping, float: 1. sending this command updates the json signal strength
        # from fetch rover
        return self._send_bool_command(2050, "ping", value)

    def send_debug_ping(self, value: float = 1.0) -> Dict[str, Any]:
        # command 2051: ping, float: 1. sending this command updates the json signal strength
        # from fetch rover. same as 2050 however no rate limit
        return self._send_bool_command(2051, "ping", value)

    def _send_bool_command(self, command: int, name: str, value: float) -> Dict[str, Any]:
        # helper for rover commands that expect a 4 byte boolean-like response
        # 0x01 00 00 00 => success
        # 0x00 00 00 00 => failure

        raw = self._send_packet(command, value)
        success = bool(raw and raw[0] == 1)
        return {
            "command": name,
            "command_number": command,
            "value": value,
            "success": success,
            "raw_response": list(raw),
            "timestamp": int(time.time()),
        }

