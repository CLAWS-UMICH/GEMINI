from __future__ import annotations

import io
import json
import math
import re
import time
import zipfile
from pathlib import Path

import numpy as np

try:
    import torch
    from torch import nn
except Exception:
    torch = None
    nn = None

try:
    from train import (
        DEFAULT_LIDAR_MAX_RANGE_CM,
        GRULidarInferencer,
        NormStats,
        load_checkpoint_for_device,
        load_gru_lidar_inferencer,
        load_model_state_with_compat,
        select_runtime_device,
    )
except Exception:
    load_gru_lidar_inferencer = None
    DEFAULT_LIDAR_MAX_RANGE_CM = 1000.0
    GRULidarInferencer = None
    NormStats = None
    load_checkpoint_for_device = None
    load_model_state_with_compat = None
    select_runtime_device = None


REPO_DIR = Path(__file__).resolve().parent
RUNS_DIR = REPO_DIR / "runs"
SIMPLE_RUNS_DIR = REPO_DIR / "simpleruns"
BUNDLE_DIR = REPO_DIR / "lidar_model_bundle"
MASSIVE_PACKAGE_ZIP_PATH = REPO_DIR / "lidar_model_package_massive_improvements.zip"
MASSIVE_PACKAGE_CHECKPOINT_MEMBER = (
    "lidar_model_package_massive_improvements/best_models/bev_query_decoder_best.pt"
)
MASSIVE_PACKAGE_SUMMARY_MEMBER = (
    "lidar_model_package_massive_improvements/summaries/bev_query_fast/summary.json"
)

LEGACY_CHECKPOINT_PATH = RUNS_DIR / "gru_lidar_classifier.pt"
SIMPLE_CHECKPOINT_PATH = SIMPLE_RUNS_DIR / "pose_aligned_beam_transformer.pt"
BUNDLE_CHECKPOINT_PATH = BUNDLE_DIR / "best_model_checkpoint.pt"
BUNDLE_METADATA_PATH = BUNDLE_DIR / "model_metadata.json"

MAX_HISTORY = 64
DEFAULT_OBSTACLE_LOGIT_BIAS = 0.0
FALLBACK_OBSTACLE_MAX_CM = 1000.0
FALLBACK_MODEL_BACKEND = "legacy_gru"

INFERENCE_BACKEND_LEGACY_GRU = "legacy_gru"
INFERENCE_BACKEND_SIMPLE_TRANSFORMER = "simple_transformer"
INFERENCE_BACKEND_BUNDLE_CNN = "bundle_cnn"
VALID_INFERENCE_BACKENDS = {
    INFERENCE_BACKEND_LEGACY_GRU,
    INFERENCE_BACKEND_SIMPLE_TRANSFORMER,
    INFERENCE_BACKEND_BUNDLE_CNN,
}

CNN_MAX_LIDAR_CM = 5000.0
CNN_POSE_X_SCALE = 20000.0
CNN_POSE_Y_SCALE = 20000.0
CNN_POSE_Z_SCALE = 2000.0
CNN_DELTA_X_SCALE = 1000.0
CNN_DELTA_Y_SCALE = 1000.0
CNN_DELTA_Z_SCALE = 100.0
CNN_PITCH_ROLL_SCALE = 45.0

_INFERENCER = None
_ACTIVE_BACKEND = FALLBACK_MODEL_BACKEND

_FEATURE_HISTORY: list[np.ndarray] = []
_SIGNATURE_HISTORY: list[np.ndarray] = []


def _parse_angle_token(value: str) -> float:
    if value.startswith("p"):
        return float(value[1:])
    if value.startswith("n"):
        return -float(value[1:])
    return float(value)


def _parse_beam_angles(beam_names: list[str]) -> np.ndarray:
    yaw_re = re.compile(r"yaw_([pn]?\d+|-?\d+)")
    pitch_re = re.compile(r"pitch_([pn]?\d+|-?\d+)")
    directions: list[list[float]] = []
    for name in beam_names:
        yaw_tokens = yaw_re.findall(name)
        pitch_tokens = pitch_re.findall(name)
        if not yaw_tokens or not pitch_tokens:
            raise ValueError(f"Could not parse beam yaw/pitch from {name!r}")
        yaw_rad = math.radians(_parse_angle_token(yaw_tokens[-1]))
        pitch_rad = math.radians(_parse_angle_token(pitch_tokens[-1]))
        cos_pitch = math.cos(pitch_rad)
        directions.append(
            [
                cos_pitch * math.cos(yaw_rad),
                cos_pitch * math.sin(yaw_rad),
                math.sin(pitch_rad),
            ]
        )
    return np.asarray(directions, dtype=np.float32)


class ResidualBlock2D(nn.Module):
    def __init__(self, channels: int, kernel_t: int, kernel_b: int, dropout: float, dilation_t: int = 1) -> None:
        super().__init__()
        padding = (dilation_t * (kernel_t // 2), kernel_b // 2)
        self.block = nn.Sequential(
            nn.Conv2d(
                channels,
                channels,
                kernel_size=(kernel_t, kernel_b),
                padding=padding,
                dilation=(dilation_t, 1),
            ),
            nn.BatchNorm2d(channels),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Conv2d(
                channels,
                channels,
                kernel_size=(kernel_t, kernel_b),
                padding=padding,
                dilation=(dilation_t, 1),
            ),
            nn.BatchNorm2d(channels),
        )
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(x + self.block(x))


class ResidualBeamCNN(nn.Module):
    def __init__(self, in_channels: int, width: int, depth: int, kernel_t: int, kernel_b: int, dropout: float) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, width, kernel_size=(kernel_t, kernel_b), padding=(kernel_t // 2, kernel_b // 2)),
            nn.BatchNorm2d(width),
            nn.GELU(),
        )
        dilations = [1, 2, 4, 1, 2, 4]
        self.encoder = nn.Sequential(
            *[
                ResidualBlock2D(
                    width,
                    kernel_t=kernel_t,
                    kernel_b=kernel_b,
                    dropout=dropout,
                    dilation_t=dilations[idx % len(dilations)],
                )
                for idx in range(depth)
            ]
        )
        self.head = nn.Sequential(
            nn.Conv1d(width, width, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Conv1d(width, width // 2, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Conv1d(width // 2, 1, kernel_size=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.encoder(self.stem(x))
        current = features[:, :, -1, :]
        return self.head(current).squeeze(1)


class BeamTemporalCNN(nn.Module):
    def __init__(self, in_channels: int, widths: tuple[int, ...], kernel_t: int, kernel_b: int, dropout: float) -> None:
        super().__init__()
        blocks: list[nn.Module] = []
        channels = in_channels
        for width in widths:
            blocks.extend(
                [
                    nn.Conv2d(
                        channels,
                        width,
                        kernel_size=(kernel_t, kernel_b),
                        padding=(kernel_t // 2, kernel_b // 2),
                    ),
                    nn.BatchNorm2d(width),
                    nn.GELU(),
                    nn.Dropout(dropout),
                ]
            )
            channels = width
        self.encoder = nn.Sequential(*blocks)
        self.head = nn.Sequential(
            nn.Conv1d(channels, channels, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Conv1d(channels, 1, kernel_size=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.encoder(x)
        current = features[:, :, -1, :]
        return self.head(current).squeeze(1)


class BestPackageCrossAttentionBlock(nn.Module):
    def __init__(self, width: int, num_heads: int, dropout: float) -> None:
        super().__init__()
        self.query_norm = nn.LayerNorm(width)
        self.memory_norm = nn.LayerNorm(width)
        self.attn = nn.MultiheadAttention(width, num_heads=num_heads, dropout=dropout, batch_first=True)
        self.mlp = nn.Sequential(
            nn.LayerNorm(width),
            nn.Linear(width, width * 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(width * 4, width),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, query: torch.Tensor, memory: torch.Tensor) -> torch.Tensor:
        attended, _ = self.attn(
            self.query_norm(query),
            self.memory_norm(memory),
            self.memory_norm(memory),
            need_weights=False,
        )
        query = query + self.dropout(attended)
        return query + self.dropout(self.mlp(query))


class BestPackageBevQueryDecoder(nn.Module):
    def __init__(self, in_channels: int, width: int, depth: int, dropout: float, num_beams: int, bev_channels: int) -> None:
        super().__init__()
        bev_width = width // 2
        bev_groups = max(1, bev_width // 16)
        layers: list[nn.Module] = [
            nn.Conv2d(bev_channels, bev_width, kernel_size=3, padding=1, bias=False),
            nn.GroupNorm(max(1, bev_groups), bev_width),
            nn.SiLU(),
        ]
        for _ in range(depth):
            layers.extend(
                [
                    nn.Conv2d(bev_width, bev_width, kernel_size=3, padding=1, bias=False),
                    nn.GroupNorm(max(1, bev_groups), bev_width),
                    nn.SiLU(),
                ]
            )
        self.bev_encoder = nn.Sequential(*layers)
        self.token_proj = nn.Sequential(
            nn.Linear(in_channels, width),
            nn.LayerNorm(width),
            nn.GELU(),
        )
        self.query_proj = nn.Sequential(
            nn.Linear(in_channels, width),
            nn.LayerNorm(width),
            nn.GELU(),
        )
        self.beam_embed = nn.Parameter(torch.randn(1, num_beams, width) * 0.02)
        self.blocks = nn.ModuleList(
            [
                BestPackageCrossAttentionBlock(
                    width=width,
                    num_heads=max(1, min(8, width // 16)),
                    dropout=dropout,
                )
                for _ in range(depth)
            ]
        )
        self.memory_proj = nn.Linear(bev_width, width)
        self.head = nn.Sequential(
            nn.LayerNorm(width * 2),
            nn.Linear(width * 2, width),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(width, 1),
        )

    def forward(self, x: torch.Tensor, bev: torch.Tensor) -> torch.Tensor:
        batch_size, channels, history, beam_count = x.shape
        token_memory = self.token_proj(x.permute(0, 2, 3, 1).reshape(batch_size, history * beam_count, channels))
        bev_memory = self.memory_proj(self.bev_encoder(bev).flatten(2).transpose(1, 2))
        memory = torch.cat([token_memory, bev_memory], dim=1)
        query = self.query_proj(x[:, :, -1, :].permute(0, 2, 1)) + self.beam_embed[:, :beam_count, :]
        for block in self.blocks:
            query = block(query, memory)
        scene = memory.mean(dim=1, keepdim=True).expand(-1, beam_count, -1)
        return self.head(torch.cat([query, scene], dim=-1)).squeeze(-1)


class BundleCnnInferencer:
    binary_obstacle_only = True

    def __init__(
        self,
        model: nn.Module,
        device: torch.device,
        threshold: float,
        context_len: int,
        beam_count: int,
    ) -> None:
        self.model = model
        self.device = device
        self.threshold = float(threshold)
        self.context_len = int(context_len)
        self.beam_count = int(beam_count)
        self.max_history = max(0, self.context_len - 1)
        self._beam_index = np.linspace(-1.0, 1.0, self.beam_count, dtype=np.float32)
        self._prev_pose_xyz_cm: np.ndarray | None = None

    def reset(self) -> None:
        self._prev_pose_xyz_cm = None

    def featurize_timestep(
        self,
        pose_xyz_cm: np.ndarray,
        lidar_cm: np.ndarray,
        basis: np.ndarray | None = None,
    ) -> np.ndarray:
        pose_arr = np.asarray(pose_xyz_cm, dtype=np.float32).reshape(3)
        lidar_arr = np.asarray(lidar_cm, dtype=np.float32).reshape(self.beam_count)
        sanitized_lidar, valid_mask = _sanitize_cnn_lidar(lidar_arr)
        heading_deg = _heading_deg_from_basis(basis)
        heading_rad = math.radians(heading_deg)
        orient = np.asarray(
            [
                math.sin(heading_rad),
                math.cos(heading_rad),
                0.0,
                0.0,
            ],
            dtype=np.float32,
        )
        deltas = np.zeros(3, dtype=np.float32)
        if self._prev_pose_xyz_cm is not None:
            deltas = pose_arr - self._prev_pose_xyz_cm
        pose_scaled = pose_arr.copy()
        pose_scaled[0] /= CNN_POSE_X_SCALE
        pose_scaled[1] /= CNN_POSE_Y_SCALE
        pose_scaled[2] /= CNN_POSE_Z_SCALE
        delta_scaled = deltas.copy()
        delta_scaled[0] /= CNN_DELTA_X_SCALE
        delta_scaled[1] /= CNN_DELTA_Y_SCALE
        delta_scaled[2] /= CNN_DELTA_Z_SCALE

        channels = [sanitized_lidar, valid_mask]
        for value in pose_scaled:
            channels.append(np.full(self.beam_count, value, dtype=np.float32))
        for value in orient:
            channels.append(np.full(self.beam_count, value, dtype=np.float32))
        for value in delta_scaled:
            channels.append(np.full(self.beam_count, value, dtype=np.float32))
        channels.append(self._beam_index.copy())
        self._prev_pose_xyz_cm = pose_arr.copy()
        return np.stack(channels, axis=0).astype(np.float32, copy=False)

    def predict_current_obstacle_logits_from_feature_history(self, history: np.ndarray) -> np.ndarray:
        history_arr = np.asarray(history, dtype=np.float32)
        if history_arr.ndim != 3:
            raise ValueError(f"Expected history shape [time, channels, beams], got {history_arr.shape}")
        if history_arr.shape[0] < self.context_len:
            return np.zeros(self.beam_count, dtype=np.float32)

        context = history_arr[-self.context_len :]
        model_input = np.transpose(context, (1, 0, 2))[None, :, :, :]
        with torch.no_grad():
            logits = self.model(torch.from_numpy(model_input).to(self.device))
        return logits.detach().cpu().numpy().reshape(-1).astype(np.float32, copy=False)

    def predict_current_obstacle_mask_from_feature_history_with_bias(
        self,
        history: np.ndarray,
        obstacle_logit_bias: float = DEFAULT_OBSTACLE_LOGIT_BIAS,
    ) -> np.ndarray:
        logits = self.predict_current_obstacle_logits_from_feature_history(history)
        logits = logits + float(obstacle_logit_bias)
        probs = 1.0 / (1.0 + np.exp(-logits))
        return probs >= self.threshold


class BestPackageInferencer:
    binary_obstacle_only = True

    def __init__(
        self,
        model: nn.Module,
        device: torch.device,
        threshold: float,
        context_len: int,
        beam_names: list[str],
        bev_extent_xy: float = 2000.0,
        bev_extent_z: float = 250.0,
        bev_size: int = 32,
    ) -> None:
        self.model = model
        self.device = device
        self.threshold = float(threshold)
        self.context_len = int(context_len)
        self.beam_names = list(beam_names)
        self.beam_count = len(self.beam_names)
        self.beam_dirs = _parse_beam_angles(self.beam_names)
        self.max_history = max(0, self.context_len - 1)
        self.bev_extent_xy = float(bev_extent_xy)
        self.bev_extent_z = float(bev_extent_z)
        self.bev_size = int(bev_size)

    def reset(self) -> None:
        return None

    def featurize_timestep(
        self,
        pose_xyz_cm: np.ndarray,
        lidar_cm: np.ndarray,
        basis: np.ndarray | None = None,
    ) -> np.ndarray:
        pose_arr = np.asarray(pose_xyz_cm, dtype=np.float32).reshape(3)
        lidar_arr = np.asarray(lidar_cm, dtype=np.float32).reshape(self.beam_count)
        basis_arr = np.eye(3, dtype=np.float32) if basis is None else np.asarray(basis, dtype=np.float32).reshape(3, 3)
        timestamp = np.asarray([time.monotonic()], dtype=np.float32)
        return np.concatenate([pose_arr, lidar_arr, basis_arr.reshape(-1), timestamp]).astype(np.float32, copy=False)

    def _unpack_history(self, history: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        history_arr = np.asarray(history, dtype=np.float32)
        pose = history_arr[:, :3]
        lidar = history_arr[:, 3 : 3 + self.beam_count]
        basis = history_arr[:, 3 + self.beam_count : 12 + self.beam_count].reshape(-1, 3, 3)
        timestamps = history_arr[:, 12 + self.beam_count]
        return pose, lidar, basis, timestamps

    def _build_feature_tensor(self, history: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        pose, lidar, basis, timestamps = self._unpack_history(history[-self.context_len :])
        valid = ((lidar > 0.0) & np.isfinite(lidar) & (lidar < 10000.0)).astype(np.float32)
        ranges = np.where(valid > 0.0, lidar, 0.0).astype(np.float32)
        local_points = ranges[..., None] * self.beam_dirs[None, :, :]
        world = np.einsum("tij,tkj->tki", basis, local_points) + pose[:, None, :]
        world *= valid[..., None]

        current_pos = pose[-1]
        current_basis_t = basis[-1].T.astype(np.float32, copy=False)
        delta = world - current_pos[None, None, :]
        current_local = np.einsum("ij,tkj->tki", current_basis_t, delta)

        ego_translation_local = np.einsum("ij,tj->ti", current_basis_t, pose - current_pos[None, :])
        ego_translation_local = np.repeat(ego_translation_local[:, None, :], self.beam_count, axis=1)

        velocity = np.zeros_like(world, dtype=np.float32)
        delta_time = np.maximum(np.diff(timestamps, prepend=timestamps[0]).astype(np.float32), 1e-3)
        velocity[1:] = (world[1:] - world[:-1]) / delta_time[1:, None, None]
        velocity *= valid[..., None]

        history_len = ranges.shape[0]
        age = np.linspace(-(history_len - 1), 0, history_len, dtype=np.float32)[:, None]
        age = np.repeat(age / max(history_len - 1, 1), self.beam_count, axis=1)
        features = np.concatenate(
            [
                world / np.array([10000.0, 10000.0, 100.0], dtype=np.float32),
                delta / np.array([2000.0, 2000.0, 200.0], dtype=np.float32),
                current_local / np.array([2000.0, 2000.0, 200.0], dtype=np.float32),
                np.clip(velocity / np.array([500.0, 500.0, 50.0], dtype=np.float32), -5.0, 5.0),
                valid[..., None],
                np.clip(ranges[..., None] / 2000.0, -1.0, 1.0),
                np.log1p(np.clip(ranges[..., None], 0.0, None)) / 8.0,
                age[..., None],
                np.repeat(self.beam_dirs[None, :, :], history_len, axis=0),
                ego_translation_local / np.array([500.0, 500.0, 50.0], dtype=np.float32),
            ],
            axis=-1,
        ).astype(np.float32, copy=False)
        bev = self._make_bev(current_local=current_local, valid=valid, age=age[:, :1])
        return np.transpose(features, (2, 0, 1)), bev

    def _paint_free_space(
        self,
        grid: np.ndarray,
        ix: np.ndarray,
        iy: np.ndarray,
        valid: np.ndarray,
        hit_weight: np.ndarray,
    ) -> None:
        center = self.bev_size // 2
        for time_idx in range(ix.shape[0]):
            for beam_idx in range(ix.shape[1]):
                if valid[time_idx, beam_idx] <= 0.5:
                    continue
                x1 = int(ix[time_idx, beam_idx])
                y1 = int(iy[time_idx, beam_idx])
                steps = max(abs(x1 - center), abs(y1 - center))
                if steps <= 1:
                    continue
                xs = np.rint(np.linspace(center, x1, steps, endpoint=False)).astype(np.int32)
                ys = np.rint(np.linspace(center, y1, steps, endpoint=False)).astype(np.int32)
                mask = (xs >= 0) & (xs < self.bev_size) & (ys >= 0) & (ys < self.bev_size)
                if not np.any(mask):
                    continue
                np.add.at(grid[4], (ys[mask], xs[mask]), 1.0)
                np.add.at(grid[5], (ys[mask], xs[mask]), float(hit_weight[time_idx, beam_idx]))

    def _make_bev(self, current_local: np.ndarray, valid: np.ndarray, age: np.ndarray) -> np.ndarray:
        grid = np.zeros((6, self.bev_size, self.bev_size), dtype=np.float32)
        xy = current_local[..., :2]
        z = current_local[..., 2]
        scale = self.bev_size / (2.0 * self.bev_extent_xy)
        ix = np.floor((xy[..., 0] + self.bev_extent_xy) * scale).astype(np.int32)
        iy = np.floor((xy[..., 1] + self.bev_extent_xy) * scale).astype(np.int32)
        mask = (
            (valid > 0.5)
            & (ix >= 0)
            & (ix < self.bev_size)
            & (iy >= 0)
            & (iy < self.bev_size)
        )
        hit_weight = np.repeat((age + 1.0).astype(np.float32), current_local.shape[1], axis=1)
        self._paint_free_space(grid, ix, iy, valid, hit_weight)
        if not np.any(mask):
            return grid
        np.add.at(grid[0], (iy[mask], ix[mask]), 1.0)
        np.add.at(grid[1], (iy[mask], ix[mask]), hit_weight[mask].reshape(-1))
        # Training code appears to include a label-derived BEV channel. That signal is unavailable online.
        np.add.at(grid[3], (iy[mask], ix[mask]), np.clip((z[mask] + self.bev_extent_z) / (2.0 * self.bev_extent_z), 0.0, 1.0))
        grid[0] = np.log1p(grid[0]) / 3.0
        grid[1] = grid[1] / max(current_local.shape[0], 1)
        grid[3] = np.where(grid[0] > 0, grid[3] / np.maximum(grid[0] * 3.0, 1e-6), 0.0)
        grid[4] = np.log1p(grid[4]) / 3.0
        grid[5] = grid[5] / max(current_local.shape[0], 1)
        return grid

    def predict_current_obstacle_logits_from_feature_history(self, history: np.ndarray) -> np.ndarray:
        history_arr = np.asarray(history, dtype=np.float32)
        if history_arr.ndim != 2:
            raise ValueError(f"Expected packed history shape [time, features], got {history_arr.shape}")
        if history_arr.shape[0] < self.context_len:
            return np.zeros(self.beam_count, dtype=np.float32)
        x, bev = self._build_feature_tensor(history_arr)
        model_x = torch.from_numpy(x[None, :, :, :]).to(self.device)
        model_bev = torch.from_numpy(bev[None, :, :, :]).to(self.device)
        with torch.no_grad():
            logits = self.model(model_x, model_bev)
        return logits.detach().cpu().numpy().reshape(-1).astype(np.float32, copy=False)

    def predict_current_obstacle_mask_from_feature_history_with_bias(
        self,
        history: np.ndarray,
        obstacle_logit_bias: float = DEFAULT_OBSTACLE_LOGIT_BIAS,
    ) -> np.ndarray:
        logits = self.predict_current_obstacle_logits_from_feature_history(history)
        logits = logits + float(obstacle_logit_bias)
        probs = 1.0 / (1.0 + np.exp(-logits))
        return probs >= self.threshold


def _sanitize_cnn_lidar(distances_cm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    valid = (distances_cm > 0.0) & np.isfinite(distances_cm) & (distances_cm <= CNN_MAX_LIDAR_CM)
    clipped = np.where(valid, np.clip(distances_cm, 0.0, CNN_MAX_LIDAR_CM), 0.0).astype(np.float32)
    normalized = np.log1p(clipped) / np.log1p(CNN_MAX_LIDAR_CM)
    return normalized.astype(np.float32, copy=False), valid.astype(np.float32, copy=False)


def _heading_deg_from_basis(basis: np.ndarray | None) -> float:
    if basis is None:
        return 0.0
    basis_arr = np.asarray(basis, dtype=np.float32).reshape(3, 3)
    return float(math.degrees(math.atan2(float(basis_arr[1, 0]), float(basis_arr[0, 0]))))


def _active_checkpoint_path() -> Path:
    if _ACTIVE_BACKEND == INFERENCE_BACKEND_BUNDLE_CNN:
        return MASSIVE_PACKAGE_ZIP_PATH if MASSIVE_PACKAGE_ZIP_PATH.exists() else BUNDLE_CHECKPOINT_PATH
    if _ACTIVE_BACKEND == INFERENCE_BACKEND_SIMPLE_TRANSFORMER:
        return SIMPLE_CHECKPOINT_PATH
    return LEGACY_CHECKPOINT_PATH


def _bundle_assets_available() -> bool:
    return MASSIVE_PACKAGE_ZIP_PATH.exists() or (BUNDLE_CHECKPOINT_PATH.exists() and BUNDLE_METADATA_PATH.exists())


def _load_massive_package_checkpoint_and_threshold() -> tuple[dict[str, object], float]:
    with zipfile.ZipFile(MASSIVE_PACKAGE_ZIP_PATH) as archive:
        checkpoint = torch.load(
            io.BytesIO(archive.read(MASSIVE_PACKAGE_CHECKPOINT_MEMBER)),
            map_location="cpu",
        )
        threshold = float(checkpoint.get("val_metrics", {}).get("valid_best_threshold", 0.5))
        try:
            summary = json.loads(archive.read(MASSIVE_PACKAGE_SUMMARY_MEMBER).decode("utf-8"))
            for result in summary.get("results", []):
                config = result.get("config", {})
                if config.get("name") == "bev_query_decoder":
                    threshold = float(result.get("locked_test", {}).get("valid_best_threshold", threshold))
                    break
        except Exception:
            pass
    return checkpoint, threshold


def _load_pose_aligned_transformer_inferencer(checkpoint_path: Path) -> GRULidarInferencer:
    if any(
        value is None
        for value in (
            GRULidarInferencer,
            NormStats,
            load_checkpoint_for_device,
            load_model_state_with_compat,
            select_runtime_device,
        )
    ):
        raise RuntimeError("Local train.py helpers are unavailable for simple-model inference.")

    import importlib.util

    external_simpletrain_path = REPO_DIR.parent / "lidarmodeltesting" / "simpletrain.py"
    if not external_simpletrain_path.exists():
        raise FileNotFoundError(f"Simple model loader not found: {external_simpletrain_path}")
    spec = importlib.util.spec_from_file_location("_external_simpletrain", external_simpletrain_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to create import spec for {external_simpletrain_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    PoseAlignedBeamTransformerClassifier = module.PoseAlignedBeamTransformerClassifier
    device_t, device_kind = select_runtime_device("auto")
    ckpt = load_checkpoint_for_device(checkpoint_path, device_t, device_kind)
    cfg = dict(ckpt["model_config"])
    model = PoseAlignedBeamTransformerClassifier(
        input_dim=int(cfg["input_dim"]),
        num_sensors=int(cfg["num_sensors"]),
        num_classes=int(cfg["num_classes"]),
        hidden_dim=int(cfg["hidden_dim"]),
        dropout=float(cfg["dropout"]),
        max_range_cm=float(cfg.get("no_hit_range_cm", DEFAULT_LIDAR_MAX_RANGE_CM)),
        transformer_layers=int(cfg.get("transformer_layers", 4)),
        attention_heads=int(cfg.get("attention_heads", 4)),
        ff_mult=int(cfg.get("ff_mult", 4)),
        decoder_hidden_dim=int(cfg["decoder_hidden_dim"]),
    ).to(device_t)
    load_model_state_with_compat(model, ckpt["model_state_dict"])
    model.eval()

    norm = ckpt["norm"]
    stats = NormStats(
        pose_mean=np.asarray(norm["pose_mean"], dtype=np.float32),
        pose_std=np.asarray(norm["pose_std"], dtype=np.float32),
        dist_mean=float(norm["dist_mean"]),
        dist_std=float(norm["dist_std"]),
    )
    max_history = int(ckpt.get("meta", {}).get("max_history", MAX_HISTORY))
    return GRULidarInferencer(
        model=model,
        stats=stats,
        device=device_t,
        num_sensors=int(cfg["num_sensors"]),
        input_dim=int(cfg["input_dim"]),
        max_history=max_history,
        binary_obstacle_only=bool(ckpt.get("meta", {}).get("binary_obstacle_only", False)),
        no_hit_range_cm=float(ckpt.get("meta", {}).get("no_hit_range_cm", DEFAULT_LIDAR_MAX_RANGE_CM)),
    )


def _build_bundle_cnn_model(meta: dict[str, object], in_channels: int) -> nn.Module:
    cfg = dict(meta["model_config"])
    model_type = str(cfg["model_type"])
    widths = tuple(int(value) for value in cfg["widths"])
    kernel_t = int(cfg["kernel_t"])
    kernel_b = int(cfg["kernel_b"])
    dropout = float(cfg["dropout"])
    if model_type == "plain":
        return BeamTemporalCNN(
            in_channels=in_channels,
            widths=widths,
            kernel_t=kernel_t,
            kernel_b=kernel_b,
            dropout=dropout,
        )
    return ResidualBeamCNN(
        in_channels=in_channels,
        width=int(widths[0]),
        depth=len(widths),
        kernel_t=kernel_t,
        kernel_b=kernel_b,
        dropout=dropout,
    )


def _load_bundle_cnn_inferencer() -> BundleCnnInferencer:
    if torch is None or nn is None:
        raise RuntimeError("PyTorch is unavailable for bundle CNN inference.")

    if MASSIVE_PACKAGE_ZIP_PATH.exists():
        checkpoint, threshold = _load_massive_package_checkpoint_and_threshold()
        config = dict(checkpoint["config"])
        beam_names = [str(name) for name in checkpoint["beam_names"]]
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = BestPackageBevQueryDecoder(
            in_channels=int(checkpoint.get("in_channels", 22)),
            width=int(config["width"]),
            depth=int(config["depth"]),
            dropout=float(config["dropout"]),
            num_beams=len(beam_names),
            bev_channels=int(checkpoint.get("bev_channels", 6)),
        ).to(device)
        model.load_state_dict(checkpoint["model_state"])
        model.eval()
        return BestPackageInferencer(
            model=model,
            device=device,
            threshold=threshold,
            context_len=int(config["history"]),
            beam_names=beam_names,
        )

    meta = json.loads(BUNDLE_METADATA_PATH.read_text(encoding="utf-8"))
    beam_count = int(meta["feature_schema"]["num_beams"])
    feature_channels = 2 + 3 + 4 + 3 + 1
    context_len = int(meta["model_config"]["context_len"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(BUNDLE_CHECKPOINT_PATH, map_location=device)
    model = _build_bundle_cnn_model(meta, in_channels=feature_channels).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return BundleCnnInferencer(
        model=model,
        device=device,
        threshold=float(meta["recommended_threshold"]),
        context_len=context_len,
        beam_count=beam_count,
    )


def _load_inferencer():
    checkpoint_path = _active_checkpoint_path()
    if _ACTIVE_BACKEND == INFERENCE_BACKEND_BUNDLE_CNN:
        return _load_bundle_cnn_inferencer()
    if _ACTIVE_BACKEND == INFERENCE_BACKEND_SIMPLE_TRANSFORMER:
        return _load_pose_aligned_transformer_inferencer(checkpoint_path)
    if load_gru_lidar_inferencer is None:
        raise RuntimeError("Local GRU loader is unavailable.")
    return load_gru_lidar_inferencer(checkpoint_path, max_history=MAX_HISTORY)


def configure_inference(use_simple_model: bool = False, backend: str | None = None) -> None:
    global _ACTIVE_BACKEND, _INFERENCER
    requested_backend = backend
    if requested_backend is None:
        requested_backend = INFERENCE_BACKEND_SIMPLE_TRANSFORMER if use_simple_model else INFERENCE_BACKEND_LEGACY_GRU
    if requested_backend not in VALID_INFERENCE_BACKENDS:
        raise ValueError(f"Unsupported inference backend: {requested_backend}")
    if _ACTIVE_BACKEND == requested_backend and (_INFERENCER is not None or not _FEATURE_HISTORY):
        return
    _ACTIVE_BACKEND = requested_backend
    _INFERENCER = None
    reset_history()


def _ensure_inferencer_loaded() -> None:
    global _INFERENCER
    if _INFERENCER is not None:
        return
    checkpoint_path = _active_checkpoint_path()
    if _ACTIVE_BACKEND == INFERENCE_BACKEND_BUNDLE_CNN:
        if not _bundle_assets_available():
            return
    elif not checkpoint_path.exists():
        return
    try:
        _INFERENCER = _load_inferencer()
    except Exception:
        _INFERENCER = None


def inferencer_backend() -> str:
    _ensure_inferencer_loaded()
    checkpoint_path = _active_checkpoint_path()
    if _INFERENCER is not None:
        if _ACTIVE_BACKEND == INFERENCE_BACKEND_BUNDLE_CNN:
            if MASSIVE_PACKAGE_ZIP_PATH.exists():
                return "best_package_loaded:bev_query_decoder_best.pt"
            return f"bundle_cnn_loaded:{checkpoint_path.name}"
        if _ACTIVE_BACKEND == INFERENCE_BACKEND_SIMPLE_TRANSFORMER:
            return f"simple_pt_loaded:{checkpoint_path.name}"
        return "gru_pt_loaded:local_train_py"
    if _ACTIVE_BACKEND == INFERENCE_BACKEND_BUNDLE_CNN:
        return "fallback_bundle_assets_missing" if not _bundle_assets_available() else "fallback_bundle_inferencer_unavailable"
    if checkpoint_path.exists() and _ACTIVE_BACKEND == INFERENCE_BACKEND_LEGACY_GRU and load_gru_lidar_inferencer is None:
        return "fallback_no_local_train_loader"
    if checkpoint_path.exists():
        if _ACTIVE_BACKEND == INFERENCE_BACKEND_SIMPLE_TRANSFORMER:
            return "fallback_simple_inferencer_unavailable"
        return "fallback_inferencer_unavailable"
    return "fallback_no_checkpoint"


def reset_history() -> None:
    _FEATURE_HISTORY.clear()
    _SIGNATURE_HISTORY.clear()
    if _INFERENCER is not None and hasattr(_INFERENCER, "reset"):
        _INFERENCER.reset()


def _build_history_signature(
    lidar_arr: np.ndarray,
    pose_arr: np.ndarray,
    basis_arr: np.ndarray | None,
) -> np.ndarray:
    parts = [pose_arr.reshape(-1), lidar_arr.reshape(-1)]
    if basis_arr is not None:
        parts.append(basis_arr.reshape(-1))
    return np.concatenate(parts).astype(np.float32, copy=False)


def _history_delta(signature_t: np.ndarray) -> float:
    if not _SIGNATURE_HISTORY:
        return float("inf")
    return float(np.max(np.abs(signature_t - _SIGNATURE_HISTORY[-1])))


def ingest_lidar(
    lidar_cm: np.ndarray,
    pose_xyz_cm: np.ndarray,
    basis: np.ndarray | None = None,
    obstacle_logit_bias: float = DEFAULT_OBSTACLE_LOGIT_BIAS,
    min_history_delta: float = 0.0,
    min_history_frames: int = 0,
) -> dict[str, np.ndarray | bool | int | float]:
    _ensure_inferencer_loaded()
    lidar_arr = np.asarray(lidar_cm, dtype=np.float32).reshape(-1)
    pose_arr = np.asarray(pose_xyz_cm, dtype=np.float32).reshape(-1)
    basis_arr = None if basis is None else np.asarray(basis, dtype=np.float32).reshape(3, 3)
    signature_t = _build_history_signature(lidar_arr, pose_arr, basis_arr)
    history_delta = _history_delta(signature_t)
    accept_current = history_delta >= max(0.0, float(min_history_delta))
    if not _SIGNATURE_HISTORY:
        accept_current = True
    effective_history_len = len(_FEATURE_HISTORY) + (1 if accept_current else 0)
    history_ready = effective_history_len >= max(0, int(min_history_frames))

    if _INFERENCER is None:
        obstacle_mask = (lidar_arr >= 0.0) & (lidar_arr <= FALLBACK_OBSTACLE_MAX_CM)
        class_ids = np.where(obstacle_mask, 1, 0).astype(np.int64)
        output: dict[str, np.ndarray | bool | int | float] = {
            "class_ids": class_ids,
            "obstacle_mask": obstacle_mask,
            "obstacle_logits": obstacle_mask.astype(np.float32),
            "history_len": effective_history_len,
            "history_ready": history_ready,
            "history_accepted": accept_current,
            "history_delta": history_delta,
        }
        if accept_current:
            _FEATURE_HISTORY.append(signature_t)
            _SIGNATURE_HISTORY.append(signature_t)
            if MAX_HISTORY > 0 and len(_FEATURE_HISTORY) > MAX_HISTORY:
                del _FEATURE_HISTORY[:-MAX_HISTORY]
                del _SIGNATURE_HISTORY[:-MAX_HISTORY]
        if not history_ready:
            output["class_ids"] = np.zeros_like(class_ids)
            output["obstacle_mask"] = np.zeros_like(obstacle_mask, dtype=bool)
            output["obstacle_logits"] = np.zeros_like(output["obstacle_logits"], dtype=np.float32)
        return output

    feature_t = _INFERENCER.featurize_timestep(
        pose_arr,
        lidar_arr,
        basis=basis_arr,
    )
    history = np.asarray([*_FEATURE_HISTORY, feature_t], dtype=np.float32)

    if _INFERENCER.binary_obstacle_only:
        obstacle_logits = _INFERENCER.predict_current_obstacle_logits_from_feature_history(history)
        obstacle_mask = _INFERENCER.predict_current_obstacle_mask_from_feature_history_with_bias(
            history,
            obstacle_logit_bias=float(obstacle_logit_bias),
        )
        class_ids = np.where(obstacle_mask, 1, 0).astype(np.int64)
        output = {
            "class_ids": class_ids,
            "obstacle_mask": obstacle_mask,
            "obstacle_logits": obstacle_logits,
        }
    else:
        class_ids = _INFERENCER.predict_current_from_feature_history(history).astype(np.int64)
        output = {
            "class_ids": class_ids,
            "obstacle_mask": (class_ids == 1),
        }

    output["history_len"] = effective_history_len
    output["history_ready"] = history_ready
    output["history_accepted"] = accept_current
    output["history_delta"] = history_delta

    if accept_current:
        _FEATURE_HISTORY.append(feature_t)
        _SIGNATURE_HISTORY.append(signature_t)
    if _INFERENCER.max_history > 0 and len(_FEATURE_HISTORY) > _INFERENCER.max_history:
        del _FEATURE_HISTORY[:-_INFERENCER.max_history]
        del _SIGNATURE_HISTORY[:-_INFERENCER.max_history]
    if not history_ready:
        output["class_ids"] = np.zeros_like(np.asarray(output["class_ids"]))
        output["obstacle_mask"] = np.zeros_like(np.asarray(output["obstacle_mask"]), dtype=bool)
        if "obstacle_logits" in output:
            output["obstacle_logits"] = np.zeros_like(np.asarray(output["obstacle_logits"]), dtype=np.float32)

    return output
