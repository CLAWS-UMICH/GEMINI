"""
Pygame visualization for LTV Search v2: dark-mode UI with trilateration ring overlays,
estimate marker, sidebar event log, and control buttons.
"""
import math
from typing import List, Optional, Tuple

import pygame

from .config import Config
from .search import SharedState
from .test_simulator import TestSimulatorAdapter

# ---------------------------------------------------------------------------
# Dark-mode palette
# ---------------------------------------------------------------------------
COL_BG = (24, 26, 32)
COL_PANEL = (32, 35, 44)
COL_BORDER = (58, 62, 74)
COL_TEXT = (200, 205, 215)
COL_TEXT_DIM = (130, 135, 145)
COL_ACCENT = (90, 160, 230)
COL_GREEN = (80, 200, 120)
COL_AMBER = (230, 180, 60)
COL_PATH = (160, 165, 180)

# Distinct ring colors for each ping (cycle if > len)
_RING_COLORS = [
    (100, 180, 240),
    (240, 160, 100),
    (140, 220, 140),
    (220, 130, 220),
    (220, 220, 100),
    (100, 220, 220),
    (220, 140, 140),
    (180, 160, 240),
    (160, 240, 180),
    (240, 200, 140),
]


def _world_to_screen(
    x: float, y: float,
    gx_min: float, gx_max: float, gy_min: float, gy_max: float,
    w: int, h: int,
    ox: int = 0, oy: int = 0,
) -> Tuple[int, int]:
    sx = int((x - gx_min) / (gx_max - gx_min) * w) if gx_max != gx_min else w // 2
    sy = int((gy_max - y) / (gy_max - gy_min) * h) if gy_max != gy_min else h // 2
    return (ox + max(0, min(w, sx)), oy + max(0, min(h, sy)))


def _world_radius_to_pixels(
    radius: float,
    gx_min: float, gx_max: float,
    w: int,
) -> int:
    if gx_max == gx_min:
        return 10
    return max(1, int(radius / (gx_max - gx_min) * w))


def run_visualization(
    config: Config,
    shared: SharedState,
    adapter: Optional[TestSimulatorAdapter] = None,
) -> str:
    """Run Pygame window. Returns 'restart' or 'quit'."""
    pygame.init()
    win_w, win_h = 1100, 720
    screen = pygame.display.set_mode((win_w, win_h))
    pygame.display.set_caption("LTV Search v2")
    font = pygame.font.Font(None, 22)
    font_sm = pygame.font.Font(None, 18)
    big_font = pygame.font.Font(None, 44)
    clock = pygame.time.Clock()
    is_test_sim = adapter is not None

    SIDEBAR_W = 240
    BOTTOM_H = 80
    MAP_PAD = 8

    map_x = MAP_PAD
    map_y = MAP_PAD
    map_w = win_w - SIDEBAR_W - MAP_PAD * 3
    map_h = win_h - BOTTOM_H - MAP_PAD * 2

    sidebar_x = win_w - SIDEBAR_W - MAP_PAD
    sidebar_y = MAP_PAD
    sidebar_w = SIDEBAR_W
    sidebar_h = win_h - BOTTOM_H - MAP_PAD * 2

    bottom_y = win_h - BOTTOM_H

    btn_next = pygame.Rect(MAP_PAD, bottom_y + 36, 180, 32)
    btn_autoplay = pygame.Rect(MAP_PAD + 190, bottom_y + 36, 120, 32)
    btn_path = pygame.Rect(MAP_PAD + 320, bottom_y + 36, 120, 32)
    btn_restart = pygame.Rect(MAP_PAD + 450, bottom_y + 36, 120, 32)

    MAX_SIDEBAR_EVENTS = 30
    show_path = True
    restart_requested = False
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if is_test_sim and btn_next.collidepoint(event.pos):
                    shared.request_advance()
                if is_test_sim and btn_autoplay.collidepoint(event.pos):
                    with shared._lock:
                        shared.autoplay = not shared.autoplay
                    if shared.autoplay:
                        shared.request_advance()
                if btn_path.collidepoint(event.pos):
                    show_path = not show_path
                if is_test_sim and btn_restart.collidepoint(event.pos):
                    restart_requested = True
                    running = False

        screen.fill(COL_BG)
        with shared._lock:
            phase = shared.phase
            lkp = shared.lkp
            rover = shared.rover
            pings = list(shared.pings)
            waypoint = shared.waypoint
            found = shared.found
            found_coords = shared.found_coords
            circles = list(shared.circles)
            estimate = shared.estimate
            ping_count = shared.ping_count
            ping_limit = shared.ping_limit
            autoplay_on = shared.autoplay
            history: List[Tuple[str, float, float]] = list(shared.waypoint_history)
            seed = shared.seed

        # Dynamic viewport bounds: LKP +/- search_radius_m
        r = config.search_radius_m
        gx_min = lkp[0] - r
        gx_max = lkp[0] + r
        gy_min = lkp[1] - r
        gy_max = lkp[1] + r

        def pt(sx: float, sy: float) -> Tuple[int, int]:
            return _world_to_screen(sx, sy, gx_min, gx_max, gy_min, gy_max, map_w, map_h, map_x, map_y)

        def rad_px(radius: float) -> int:
            return _world_radius_to_pixels(radius, gx_min, gx_max, map_w)

        # =====================================================================
        # MAP VIEWPORT
        # =====================================================================
        pygame.draw.rect(screen, COL_PANEL, (map_x, map_y, map_w, map_h))
        pygame.draw.rect(screen, COL_BORDER, (map_x, map_y, map_w, map_h), 1)

        # Clip drawing to map area
        map_clip = pygame.Rect(map_x, map_y, map_w, map_h)
        screen.set_clip(map_clip)

        # Trilateration rings
        for i, (cx, cy, d) in enumerate(circles):
            color = _RING_COLORS[i % len(_RING_COLORS)]
            center = pt(cx, cy)
            rpx = rad_px(d)
            if rpx > 1:
                pygame.draw.circle(screen, color, center, rpx, 1)

        # Rover path
        if show_path:
            wp_pts = [pt(ex, ey) for kind, ex, ey in history if kind == "waypoint"]
            for i in range(len(wp_pts) - 1):
                ax, ay = wp_pts[i]
                bx, by = wp_pts[i + 1]
                dx, dy = bx - ax, by - ay
                seg_len = max(1, int(math.hypot(dx, dy)))
                dash = 4
                for t in range(0, seg_len, dash * 2):
                    t2 = min(t + dash, seg_len)
                    x1 = ax + dx * t // seg_len
                    y1 = ay + dy * t // seg_len
                    x2 = ax + dx * t2 // seg_len
                    y2 = ay + dy * t2 // seg_len
                    pygame.draw.line(screen, COL_PATH, (x1, y1), (x2, y2), 1)

        # LKP — minimal crosshair
        lkp_pt = pt(lkp[0], lkp[1])
        lkp_col = (200, 190, 100)
        pygame.draw.line(screen, lkp_col, (lkp_pt[0] - 5, lkp_pt[1]), (lkp_pt[0] + 5, lkp_pt[1]), 1)
        pygame.draw.line(screen, lkp_col, (lkp_pt[0], lkp_pt[1] - 5), (lkp_pt[0], lkp_pt[1] + 5), 1)
        pygame.draw.circle(screen, lkp_col, lkp_pt, 4, 1)

        # Estimate marker — diamond
        if estimate:
            ex, ey = pt(estimate[0], estimate[1])
            sz = 6
            pygame.draw.polygon(screen, (255, 255, 255), [
                (ex, ey - sz), (ex + sz, ey), (ex, ey + sz), (ex - sz, ey)
            ], 2)

        # Ping dots
        for i, (px, py, _d) in enumerate(pings):
            color = _RING_COLORS[i % len(_RING_COLORS)]
            pygame.draw.circle(screen, color, pt(px, py), 4)

        # Current waypoint target
        if waypoint:
            pygame.draw.circle(screen, COL_ACCENT, pt(waypoint[0], waypoint[1]), 5, 2)

        # Rover
        rover_pt = pt(rover[0], rover[1])
        pygame.draw.circle(screen, (255, 255, 255), rover_pt, 9, 2)
        pygame.draw.circle(screen, COL_GREEN, rover_pt, 7)

        # True LTV (test sim only)
        if is_test_sim and hasattr(adapter, "get_true_ltv_position"):
            tx, ty = adapter.get_true_ltv_position()
            center = pt(tx, ty)
            pygame.draw.circle(screen, (255, 255, 255), center, 7, 2)
            pygame.draw.circle(screen, (220, 70, 70), center, 5)

        screen.set_clip(None)
        pygame.draw.rect(screen, COL_BORDER, (map_x, map_y, map_w, map_h), 1)

        # =====================================================================
        # SIDEBAR — event history
        # =====================================================================
        pygame.draw.rect(screen, COL_PANEL, (sidebar_x, sidebar_y, sidebar_w, sidebar_h))
        pygame.draw.rect(screen, COL_BORDER, (sidebar_x, sidebar_y, sidebar_w, sidebar_h), 1)
        header = font.render("Event Log", True, COL_TEXT)
        screen.blit(header, (sidebar_x + 10, sidebar_y + 8))
        pygame.draw.line(screen, COL_BORDER, (sidebar_x + 6, sidebar_y + 28), (sidebar_x + sidebar_w - 6, sidebar_y + 28))

        visible = history[-MAX_SIDEBAR_EVENTS:]
        for i, (kind, ex, ey) in enumerate(visible):
            y_off = sidebar_y + 34 + i * 18
            if y_off + 16 > sidebar_y + sidebar_h:
                break
            if kind == "waypoint":
                col = COL_ACCENT
                label = f"WP  ({ex:.0f}, {ey:.0f})"
            else:
                dist_str = ""
                ping_idx = sum(1 for k, _, _ in history[:history.index((kind, ex, ey)) + 1] if k == "ping") - 1
                if 0 <= ping_idx < len(pings):
                    dist_str = f" d={pings[ping_idx][2]:.0f}m"
                col = COL_AMBER
                label = f"PNG ({ex:.0f}, {ey:.0f}){dist_str}"
            screen.blit(font_sm.render(label, True, col), (sidebar_x + 12, y_off))

        # =====================================================================
        # BOTTOM BAR
        # =====================================================================
        pygame.draw.rect(screen, COL_PANEL, (0, bottom_y, win_w, BOTTOM_H))
        pygame.draw.line(screen, COL_BORDER, (0, bottom_y), (win_w, bottom_y))

        seed_str = f"   |   Seed: {seed}" if seed is not None else ""
        phase_txt = font.render(f"Phase: {phase}   |   Pings: {ping_count}/{ping_limit}{seed_str}", True, COL_TEXT)
        screen.blit(phase_txt, (MAP_PAD, bottom_y + 8))

        # Marker legend
        legend_x = win_w - 320
        legend_y = bottom_y + 8
        lx = legend_x
        pygame.draw.line(screen, lkp_col, (lx - 3, legend_y + 6), (lx + 3, legend_y + 6), 1)
        pygame.draw.line(screen, lkp_col, (lx, legend_y + 3), (lx, legend_y + 9), 1)
        screen.blit(font_sm.render("LKP", True, COL_TEXT_DIM), (lx + 8, legend_y - 1))
        pygame.draw.circle(screen, (255, 255, 255), (lx + 42, legend_y + 6), 5, 1)
        pygame.draw.circle(screen, COL_GREEN, (lx + 42, legend_y + 6), 4)
        screen.blit(font_sm.render("Rover", True, COL_TEXT_DIM), (lx + 50, legend_y - 1))
        pygame.draw.circle(screen, COL_AMBER, (lx + 92, legend_y + 6), 3)
        screen.blit(font_sm.render("Ping", True, COL_TEXT_DIM), (lx + 100, legend_y - 1))
        pygame.draw.circle(screen, (220, 70, 70), (lx + 140, legend_y + 6), 4)
        screen.blit(font_sm.render("LTV", True, COL_TEXT_DIM), (lx + 148, legend_y - 1))
        # Estimate diamond
        edx = lx + 188
        edy = legend_y + 6
        pygame.draw.polygon(screen, (255, 255, 255), [(edx, edy - 4), (edx + 4, edy), (edx, edy + 4), (edx - 4, edy)], 1)
        screen.blit(font_sm.render("Est", True, COL_TEXT_DIM), (lx + 196, legend_y - 1))
        # Ring
        pygame.draw.circle(screen, _RING_COLORS[0], (lx + 228, legend_y + 6), 5, 1)
        screen.blit(font_sm.render("Ring", True, COL_TEXT_DIM), (lx + 236, legend_y - 1))
        if show_path:
            pygame.draw.line(screen, COL_PATH, (lx + 270, legend_y + 6), (lx + 280, legend_y + 6), 1)
            pygame.draw.line(screen, COL_PATH, (lx + 284, legend_y + 6), (lx + 294, legend_y + 6), 1)
            screen.blit(font_sm.render("Path", True, COL_TEXT_DIM), (lx + 298, legend_y - 1))

        # Found / not-found overlays
        if found and found_coords:
            s = big_font.render("LTV FOUND", True, COL_GREEN)
            sw = s.get_width()
            cx = map_x + map_w // 2 - sw // 2
            screen.blit(s, (cx, map_y + 12))
            c = font.render(f"({found_coords[0]:.1f}, {found_coords[1]:.1f})", True, (180, 230, 180))
            screen.blit(c, (cx + sw // 2 - c.get_width() // 2, map_y + 50))

        if phase == "pings_exhausted":
            s = big_font.render("LTV NOT FOUND", True, COL_AMBER)
            sw = s.get_width()
            screen.blit(s, (map_x + map_w // 2 - sw // 2, map_y + 12))
            c = font.render("Max pings used", True, COL_TEXT_DIM)
            screen.blit(c, (map_x + map_w // 2 - c.get_width() // 2, map_y + 50))

        # Buttons
        if is_test_sim:
            pygame.draw.rect(screen, (50, 110, 170), btn_next, border_radius=4)
            ap_col = (55, 120, 65) if autoplay_on else (100, 55, 55)
            pygame.draw.rect(screen, ap_col, btn_autoplay, border_radius=4)
            screen.blit(font_sm.render("Go to next waypoint", True, (220, 225, 235)), (btn_next.x + 10, btn_next.y + 8))
            screen.blit(font_sm.render("Autoplay: " + ("ON" if autoplay_on else "OFF"), True, (220, 225, 235)), (btn_autoplay.x + 10, btn_autoplay.y + 8))
        path_col = (55, 120, 65) if show_path else (100, 55, 55)
        pygame.draw.rect(screen, path_col, btn_path, border_radius=4)
        screen.blit(font_sm.render("Path: " + ("ON" if show_path else "OFF"), True, (220, 225, 235)), (btn_path.x + 10, btn_path.y + 8))
        if is_test_sim:
            pygame.draw.rect(screen, (140, 90, 50), btn_restart, border_radius=4)
            screen.blit(font_sm.render("Restart", True, (220, 225, 235)), (btn_restart.x + 10, btn_restart.y + 8))

        pygame.display.flip()
        clock.tick(15)

    pygame.quit()
    return "restart" if restart_requested else "quit"
