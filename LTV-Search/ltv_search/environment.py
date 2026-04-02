"""Environment adapter interface for LTV Search v2."""
from abc import ABC, abstractmethod
from typing import Tuple


class EnvironmentAdapter(ABC):

    @abstractmethod
    def get_lkp(self) -> Tuple[float, float]:
        """Return last known position (x, y) in meters."""
        ...

    @abstractmethod
    def get_rover_position(self) -> Tuple[float, float]:
        """Return current rover position (x, y) in meters."""
        ...

    @abstractmethod
    def ping(self) -> float:
        """Trigger a ping and return RSSI (dBm). Caller handles rate limiting."""
        ...

    @abstractmethod
    def set_target_waypoint(self, x: float, y: float) -> None:
        """Set rover target waypoint."""
        ...

    @abstractmethod
    def is_arrived(self) -> bool:
        """True if rover is at or near the current target waypoint."""
        ...

    @abstractmethod
    def get_pings_left(self) -> int:
        """Remaining pings allowed (-1 for unlimited)."""
        ...

    def get_ping_interval_sec(self) -> float:
        return 20.0
