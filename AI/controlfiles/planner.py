from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

CELL_EMPTY = 0
CELL_OBSTACLE = 1
CELL_LOW_CLEARANCE_OBSTACLE = 2


@dataclass(slots=True)
class PlannerConfig:
    cell_size_cm: float = 5.0
    obstacle_padding_cells: int = 2
    allow_diagonal: bool = True
    use_jump_point_search: bool = False
    nearest_free_search_cm: float = 1000.0
    evidence_cost_scale: float = 0.75
    clearance_cost_scale: float = 1.0
    evidence_min_value: float = -3.0
    evidence_max_value: float = 8.0
    clearance_min_value: float = 0.0
    clearance_max_value: float = 12.0


class OccupancyPlanner:
    def __init__(
        self,
        origin_x_cm: float,
        origin_y_cm: float,
        width_cells: int,
        height_cells: int,
        config: PlannerConfig | None = None,
    ) -> None:
        self.origin_x_cm = float(origin_x_cm)
        self.origin_y_cm = float(origin_y_cm)
        self.width_cells = int(width_cells)
        self.height_cells = int(height_cells)
        self.config = config or PlannerConfig()
        self._obstacle_version = 0
        self.grid = [[CELL_EMPTY for _ in range(self.width_cells)] for _ in range(self.height_cells)]
        self.evidence_grid = [[0.0 for _ in range(self.width_cells)] for _ in range(self.height_cells)]
        self.clearance_grid = [[0.0 for _ in range(self.width_cells)] for _ in range(self.height_cells)]
        self._padded_block_counts = [[0 for _ in range(self.width_cells)] for _ in range(self.height_cells)]
        pad = max(0, self.config.obstacle_padding_cells)
        self._padding_offsets = [(dx, dy) for dy in range(-pad, pad + 1) for dx in range(-pad, pad + 1)]
        if self.config.allow_diagonal:
            self._neighbor_deltas = [
                (1, 0, 1.0),
                (-1, 0, 1.0),
                (0, 1, 1.0),
                (0, -1, 1.0),
                (1, 1, math.sqrt(2.0)),
                (1, -1, math.sqrt(2.0)),
                (-1, 1, math.sqrt(2.0)),
                (-1, -1, math.sqrt(2.0)),
            ]
        else:
            self._neighbor_deltas = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0)]

    def in_bounds(self, cell: tuple[int, int]) -> bool:
        x, y = cell
        return 0 <= x < self.width_cells and 0 <= y < self.height_cells

    def world_to_cell(self, x_cm: float, y_cm: float) -> tuple[int, int]:
        cx = int(math.floor((x_cm - self.origin_x_cm) / self.config.cell_size_cm))
        cy = int(math.floor((y_cm - self.origin_y_cm) / self.config.cell_size_cm))
        return (cx, cy)

    def cell_to_world_center(self, cell: tuple[int, int]) -> tuple[float, float]:
        cx, cy = cell
        x_cm = self.origin_x_cm + (cx + 0.5) * self.config.cell_size_cm
        y_cm = self.origin_y_cm + (cy + 0.5) * self.config.cell_size_cm
        return (x_cm, y_cm)

    def mark_obstacle_cell(self, cell: tuple[int, int], cell_value: int = CELL_OBSTACLE) -> bool:
        if not self.in_bounds(cell):
            return False
        cx, cy = cell
        current = self.grid[cy][cx]
        if current == CELL_OBSTACLE:
            return False
        if current == CELL_LOW_CLEARANCE_OBSTACLE and cell_value == CELL_LOW_CLEARANCE_OBSTACLE:
            return False
        if current == CELL_LOW_CLEARANCE_OBSTACLE and cell_value == CELL_OBSTACLE:
            self.grid[cy][cx] = CELL_OBSTACLE
            self._obstacle_version += 1
            return False
        self.grid[cy][cx] = int(cell_value)
        self._apply_padding_block(cell)
        self._obstacle_version += 1
        return True

    def mark_obstacle_world(self, x_cm: float, y_cm: float, cell_value: int = CELL_OBSTACLE) -> bool:
        return self.mark_obstacle_cell(self.world_to_cell(x_cm, y_cm), cell_value=cell_value)

    def add_evidence_cell(self, cell: tuple[int, int], delta: float) -> bool:
        if not self.in_bounds(cell):
            return False
        cx, cy = cell
        current = float(self.evidence_grid[cy][cx])
        updated = max(
            float(self.config.evidence_min_value),
            min(float(self.config.evidence_max_value), current + float(delta)),
        )
        if abs(updated - current) <= 1e-9:
            return False
        self.evidence_grid[cy][cx] = updated
        return True

    def add_evidence_world(self, x_cm: float, y_cm: float, delta: float) -> bool:
        return self.add_evidence_cell(self.world_to_cell(x_cm, y_cm), delta)

    def cell_evidence(self, cell: tuple[int, int]) -> float:
        if not self.in_bounds(cell):
            return float(self.config.evidence_max_value)
        cx, cy = cell
        return float(self.evidence_grid[cy][cx])

    def add_clearance_cell(self, cell: tuple[int, int], delta: float) -> bool:
        if not self.in_bounds(cell):
            return False
        cx, cy = cell
        current = float(self.clearance_grid[cy][cx])
        updated = max(
            float(self.config.clearance_min_value),
            min(float(self.config.clearance_max_value), current + float(delta)),
        )
        if abs(updated - current) <= 1e-9:
            return False
        self.clearance_grid[cy][cx] = updated
        return True

    def add_clearance_world(self, x_cm: float, y_cm: float, delta: float) -> bool:
        return self.add_clearance_cell(self.world_to_cell(x_cm, y_cm), delta)

    def cell_clearance(self, cell: tuple[int, int]) -> float:
        if not self.in_bounds(cell):
            return float(self.config.clearance_max_value)
        cx, cy = cell
        return float(self.clearance_grid[cy][cx])

    def world_line_cells(
        self,
        start_world_cm: tuple[float, float],
        end_world_cm: tuple[float, float],
    ) -> list[tuple[int, int]]:
        start = self.world_to_cell(*start_world_cm)
        end = self.world_to_cell(*end_world_cm)
        return self._rasterized_line_cells(start, end)

    def mark_lidar_hit(
        self,
        rover_x_cm: float,
        rover_y_cm: float,
        rover_heading_deg: float,
        sensor_local_x_cm: float,
        sensor_local_y_cm: float,
        sensor_yaw_deg: float,
        hit_distance_cm: float,
    ) -> bool:
        sensor_world_x, sensor_world_y = _local_to_world_2d(
            rover_x_cm,
            rover_y_cm,
            rover_heading_deg,
            sensor_local_x_cm,
            sensor_local_y_cm,
        )
        hit_heading = rover_heading_deg + sensor_yaw_deg
        rad = math.radians(hit_heading)
        hit_x = sensor_world_x + hit_distance_cm * math.cos(rad)
        hit_y = sensor_world_y + hit_distance_cm * math.sin(rad)
        return self.mark_obstacle_world(hit_x, hit_y)

    def is_padded_obstacle(self, cell: tuple[int, int]) -> bool:
        if not self.in_bounds(cell):
            return True
        cx, cy = cell
        return self._padded_block_counts[cy][cx] > 0

    def plan_path(
        self,
        start_world_cm: tuple[float, float],
        goal_world_cm: tuple[float, float],
    ) -> list[tuple[float, float]]:
        start = self.world_to_cell(*start_world_cm)
        goal = self.world_to_cell(*goal_world_cm)
        if not self.in_bounds(start) or not self.in_bounds(goal):
            return []

        start = self._nearest_free_cell(start)
        goal = self._nearest_free_cell(goal)
        if start is None or goal is None:
            return []

        if self.config.use_jump_point_search:
            cell_path = self._jump_point_search_cells(start, goal)
        else:
            cell_path = self._astar_cells(start, goal)
        return [self.cell_to_world_center(cell) for cell in cell_path]

    def _nearest_free_cell(self, start: tuple[int, int], max_radius_cm: float | None = None) -> tuple[int, int] | None:
        if not self.is_padded_obstacle(start):
            return start

        search_cm = float(self.config.nearest_free_search_cm) if max_radius_cm is None else float(max_radius_cm)
        cell_size = max(1.0, float(self.config.cell_size_cm))
        max_radius = max(1, int(math.ceil(search_cm / cell_size)))

        sx, sy = start
        for radius in range(1, max_radius + 1):
            for y in range(sy - radius, sy + radius + 1):
                for x in range(sx - radius, sx + radius + 1):
                    if abs(x - sx) != radius and abs(y - sy) != radius:
                        continue
                    cell = (x, y)
                    if self.in_bounds(cell) and not self.is_padded_obstacle(cell):
                        return cell
        return None

    def _neighbors(self, cell: tuple[int, int]) -> list[tuple[tuple[int, int], float]]:
        x, y = cell
        neighbors: list[tuple[tuple[int, int], float]] = []
        for dx, dy, cost in self._neighbor_deltas:
            nxt = (x + dx, y + dy)
            if self.in_bounds(nxt) and not self.is_padded_obstacle(nxt):
                neighbors.append((nxt, cost * self._cell_traversal_cost_multiplier(nxt)))
        return neighbors

    def _apply_padding_block(self, cell: tuple[int, int]) -> None:
        cx, cy = cell
        for dx, dy in self._padding_offsets:
            nx = cx + dx
            ny = cy + dy
            if 0 <= nx < self.width_cells and 0 <= ny < self.height_cells:
                self._padded_block_counts[ny][nx] += 1

    @staticmethod
    def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _cell_traversal_cost_multiplier(self, cell: tuple[int, int]) -> float:
        evidence = max(0.0, self.cell_evidence(cell))
        clearance = max(0.0, self.cell_clearance(cell))
        return (
            1.0
            + evidence * float(self.config.evidence_cost_scale)
            + clearance * float(self.config.clearance_cost_scale)
        )

    def _rasterized_line_cells(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> list[tuple[int, int]]:
        x0, y0 = start
        x1, y1 = end
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        cells: list[tuple[int, int]] = []

        while True:
            cell = (x0, y0)
            if self.in_bounds(cell):
                if not cells or cells[-1] != cell:
                    cells.append(cell)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
        return cells

    def _astar_cells(self, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
        frontier: list[tuple[float, tuple[int, int]]] = []
        heapq.heappush(frontier, (0.0, start))
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        cost_so_far: dict[tuple[int, int], float] = {start: 0.0}

        while frontier:
            _, current = heapq.heappop(frontier)
            if current == goal:
                break

            for nxt, step_cost in self._neighbors(current):
                new_cost = cost_so_far[current] + step_cost
                if nxt not in cost_so_far or new_cost < cost_so_far[nxt]:
                    cost_so_far[nxt] = new_cost
                    priority = new_cost + self._heuristic(nxt, goal)
                    heapq.heappush(frontier, (priority, nxt))
                    came_from[nxt] = current

        if goal not in came_from:
            return []

        path = []
        cur: tuple[int, int] | None = goal
        while cur is not None:
            path.append(cur)
            cur = came_from[cur]
        path.reverse()
        return path

    def _is_walkable(self, cell: tuple[int, int]) -> bool:
        return self.in_bounds(cell) and not self.is_padded_obstacle(cell)

    @staticmethod
    def _direction_between(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        return (
            0 if dx == 0 else (1 if dx > 0 else -1),
            0 if dy == 0 else (1 if dy > 0 else -1),
        )

    def _step_cost(self, from_cell: tuple[int, int], to_cell: tuple[int, int]) -> float:
        dx = abs(to_cell[0] - from_cell[0])
        dy = abs(to_cell[1] - from_cell[1])
        base_cost = math.sqrt(2.0) if dx == 1 and dy == 1 else 1.0
        return base_cost * self._cell_traversal_cost_multiplier(to_cell)

    def _pruned_neighbor_directions(
        self,
        cell: tuple[int, int],
        parent: tuple[int, int] | None,
    ) -> list[tuple[int, int]]:
        if parent is None:
            return [(dx, dy) for dx, dy, _ in self._neighbor_deltas if self._is_walkable((cell[0] + dx, cell[1] + dy))]

        x, y = cell
        dx, dy = self._direction_between(parent, cell)
        directions: list[tuple[int, int]] = []

        def add_direction(step_dx: int, step_dy: int) -> None:
            nxt = (x + step_dx, y + step_dy)
            if self._is_walkable(nxt) and (step_dx, step_dy) not in directions:
                directions.append((step_dx, step_dy))

        if dx != 0 and dy != 0:
            add_direction(dx, dy)
            add_direction(dx, 0)
            add_direction(0, dy)
            if not self._is_walkable((x - dx, y)):
                add_direction(-dx, dy)
            if not self._is_walkable((x, y - dy)):
                add_direction(dx, -dy)
        elif dx != 0:
            add_direction(dx, 0)
            if not self._is_walkable((x, y + 1)):
                add_direction(dx, 1)
            if not self._is_walkable((x, y - 1)):
                add_direction(dx, -1)
        else:
            add_direction(0, dy)
            if not self._is_walkable((x + 1, y)):
                add_direction(1, dy)
            if not self._is_walkable((x - 1, y)):
                add_direction(-1, dy)

        return directions

    def _has_forced_neighbor(self, cell: tuple[int, int], direction: tuple[int, int]) -> bool:
        x, y = cell
        dx, dy = direction
        if dx != 0 and dy != 0:
            return (
                (not self._is_walkable((x - dx, y)) and self._is_walkable((x - dx, y + dy)))
                or (not self._is_walkable((x, y - dy)) and self._is_walkable((x + dx, y - dy)))
            )
        if dx != 0:
            return (
                (not self._is_walkable((x, y + 1)) and self._is_walkable((x + dx, y + 1)))
                or (not self._is_walkable((x, y - 1)) and self._is_walkable((x + dx, y - 1)))
            )
        return (
            (not self._is_walkable((x + 1, y)) and self._is_walkable((x + 1, y + dy)))
            or (not self._is_walkable((x - 1, y)) and self._is_walkable((x - 1, y + dy)))
        )

    def _jump(
        self,
        current: tuple[int, int],
        direction: tuple[int, int],
        goal: tuple[int, int],
    ) -> tuple[tuple[int, int], float] | None:
        dx, dy = direction
        x, y = current
        next_cell = (x + dx, y + dy)
        if not self._is_walkable(next_cell):
            return None

        total_cost = 0.0
        prev_cell = current
        while self._is_walkable(next_cell):
            total_cost += self._step_cost(prev_cell, next_cell)
            if next_cell == goal:
                return (next_cell, total_cost)
            if self._has_forced_neighbor(next_cell, direction):
                return (next_cell, total_cost)
            if dx != 0 and dy != 0:
                if self._jump(next_cell, (dx, 0), goal) is not None:
                    return (next_cell, total_cost)
                if self._jump(next_cell, (0, dy), goal) is not None:
                    return (next_cell, total_cost)
            prev_cell = next_cell
            next_cell = (next_cell[0] + dx, next_cell[1] + dy)
        return None

    def _expand_jump_path(
        self,
        jump_path: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        if not jump_path:
            return []
        expanded: list[tuple[int, int]] = [jump_path[0]]
        for idx in range(1, len(jump_path)):
            segment = self._rasterized_line_cells(jump_path[idx - 1], jump_path[idx])
            if segment:
                expanded.extend(segment[1:])
        return expanded

    def _jump_point_search_cells(self, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
        frontier: list[tuple[float, tuple[int, int]]] = []
        heapq.heappush(frontier, (0.0, start))
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        cost_so_far: dict[tuple[int, int], float] = {start: 0.0}

        while frontier:
            _, current = heapq.heappop(frontier)
            if current == goal:
                break

            parent = came_from[current]
            for direction in self._pruned_neighbor_directions(current, parent):
                jump_result = self._jump(current, direction, goal)
                if jump_result is None:
                    continue
                jump_cell, jump_cost = jump_result
                new_cost = cost_so_far[current] + jump_cost
                if jump_cell not in cost_so_far or new_cost < cost_so_far[jump_cell]:
                    cost_so_far[jump_cell] = new_cost
                    priority = new_cost + self._heuristic(jump_cell, goal)
                    heapq.heappush(frontier, (priority, jump_cell))
                    came_from[jump_cell] = current

        if goal not in came_from:
            return []

        jump_path: list[tuple[int, int]] = []
        cur: tuple[int, int] | None = goal
        while cur is not None:
            jump_path.append(cur)
            cur = came_from[cur]
        jump_path.reverse()
        return self._expand_jump_path(jump_path)


def _local_to_world_2d(
    base_x_cm: float,
    base_y_cm: float,
    heading_deg: float,
    local_x_cm: float,
    local_y_cm: float,
) -> tuple[float, float]:
    rad = math.radians(heading_deg)
    cos_h = math.cos(rad)
    sin_h = math.sin(rad)
    wx = base_x_cm + local_x_cm * cos_h - local_y_cm * sin_h
    wy = base_y_cm + local_x_cm * sin_h + local_y_cm * cos_h
    return (wx, wy)
