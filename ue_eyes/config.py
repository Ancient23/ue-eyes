"""Configuration loader for ue-eyes.

Loads settings from ``ue-eyes.toml``, walking up from a start directory to the
git root.  Returns sensible defaults when no config file is found, enabling
zero-config operation during development.
"""

from __future__ import annotations

import logging
import tomllib
import warnings
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

CONFIG_FILENAME: str = "ue-eyes.toml"
CONFIG_VERSION: int = 1

DEFAULT_MULTICAST_GROUP: str = "239.0.0.1"
DEFAULT_MULTICAST_PORT: int = 6766
DEFAULT_TIMEOUT: float = 30.0
DEFAULT_CAPTURE_MODE: str = "snap"
DEFAULT_RESOLUTION: list[int] = [1920, 1080]
DEFAULT_SEQUENCE_PATH: str = ""
DEFAULT_MAP_PATH: str = ""
DEFAULT_METRICS: list[str] = ["ssim"]
DEFAULT_COMPOSITE_WEIGHTS: dict[str, float] = {"ssim": 1.0}
DEFAULT_PARAMS_FILE: str = "tune_params.json"

DEFAULT_CAMERA_LOCATION: list[float] = [0.0, 0.0, 0.0]
DEFAULT_CAMERA_ROTATION: list[float] = [0.0, 0.0, 0.0]
DEFAULT_TRACKING_MODE: str = "fixed"
DEFAULT_TARGET_ACTOR: str = ""
DEFAULT_TARGET_BONE: str = ""
DEFAULT_CAMERA_OFFSET: list[float] = [0.0, 0.0, 0.0]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CameraPreset:
    """A single named camera preset."""

    name: str
    location: list[float] = field(default_factory=lambda: DEFAULT_CAMERA_LOCATION.copy())
    rotation: list[float] = field(default_factory=lambda: DEFAULT_CAMERA_ROTATION.copy())
    tracking_mode: str = DEFAULT_TRACKING_MODE
    target_actor: str = DEFAULT_TARGET_ACTOR
    target_bone: str = DEFAULT_TARGET_BONE
    offset: list[float] = field(default_factory=lambda: DEFAULT_CAMERA_OFFSET.copy())


@dataclass
class UEEyesConfig:
    """Top-level configuration — every field has a default."""

    # Connection
    multicast_group: str = DEFAULT_MULTICAST_GROUP
    multicast_port: int = DEFAULT_MULTICAST_PORT
    timeout: float = DEFAULT_TIMEOUT
    # Capture
    capture_mode: str = DEFAULT_CAPTURE_MODE
    default_resolution: list[int] = field(default_factory=lambda: DEFAULT_RESOLUTION.copy())
    sequence_path: str = DEFAULT_SEQUENCE_PATH
    map_path: str = DEFAULT_MAP_PATH
    # Cameras
    cameras: dict[str, CameraPreset] = field(default_factory=dict)
    # Scoring
    metrics: list[str] = field(default_factory=lambda: DEFAULT_METRICS.copy())
    composite_weights: dict[str, float] = field(
        default_factory=lambda: DEFAULT_COMPOSITE_WEIGHTS.copy()
    )
    # Parameters
    params_file: str = DEFAULT_PARAMS_FILE


# ---------------------------------------------------------------------------
# Config discovery
# ---------------------------------------------------------------------------


def _find_config(start_dir: Path) -> Path | None:
    """Walk *start_dir* and its parents looking for *CONFIG_FILENAME*.

    Stops when it reaches the git root (a directory containing ``.git``) or the
    filesystem root.  Returns ``None`` if the file is not found.
    """
    current = start_dir.resolve()
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        # Stop walking if this directory is a git root.
        if (current / ".git").exists():
            return None
        parent = current.parent
        if parent == current:
            # Filesystem root reached.
            return None
        current = parent


# ---------------------------------------------------------------------------
# TOML parsing helpers
# ---------------------------------------------------------------------------


def _parse_camera_preset(name: str, data: dict) -> CameraPreset:
    """Build a :class:`CameraPreset` from a TOML ``[cameras.<name>]`` table."""
    return CameraPreset(
        name=name,
        location=data.get("location", DEFAULT_CAMERA_LOCATION.copy()),
        rotation=data.get("rotation", DEFAULT_CAMERA_ROTATION.copy()),
        tracking_mode=data.get("tracking_mode", DEFAULT_TRACKING_MODE),
        target_actor=data.get("target_actor", DEFAULT_TARGET_ACTOR),
        target_bone=data.get("target_bone", DEFAULT_TARGET_BONE),
        offset=data.get("offset", DEFAULT_CAMERA_OFFSET.copy()),
    )


def _parse_toml(raw: dict) -> UEEyesConfig:
    """Convert a parsed TOML dict into a :class:`UEEyesConfig`."""
    # Version validation
    version = raw.get("version")
    if version is not None:
        if version != CONFIG_VERSION:
            raise ValueError(
                f"Unsupported config version {version!r} "
                f"(expected {CONFIG_VERSION})"
            )
    else:
        warnings.warn(
            f"No 'version' field in {CONFIG_FILENAME}; assuming version {CONFIG_VERSION}",
            stacklevel=3,
        )

    conn = raw.get("connection", {})
    cap = raw.get("capture", {})
    cams_raw = raw.get("cameras", {})
    scoring = raw.get("scoring", {})
    params = raw.get("parameters", {})

    cameras: dict[str, CameraPreset] = {
        name: _parse_camera_preset(name, table)
        for name, table in cams_raw.items()
    }

    return UEEyesConfig(
        multicast_group=conn.get("multicast_group", DEFAULT_MULTICAST_GROUP),
        multicast_port=conn.get("multicast_port", DEFAULT_MULTICAST_PORT),
        timeout=conn.get("timeout", DEFAULT_TIMEOUT),
        capture_mode=cap.get("mode", DEFAULT_CAPTURE_MODE),
        default_resolution=cap.get("default_resolution", DEFAULT_RESOLUTION.copy()),
        sequence_path=cap.get("sequence_path", DEFAULT_SEQUENCE_PATH),
        map_path=cap.get("map_path", DEFAULT_MAP_PATH),
        cameras=cameras,
        metrics=scoring.get("metrics", DEFAULT_METRICS.copy()),
        composite_weights=scoring.get("composite_weights", DEFAULT_COMPOSITE_WEIGHTS.copy()),
        params_file=params.get("file", DEFAULT_PARAMS_FILE),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(start_dir: Path | None = None) -> UEEyesConfig:
    """Load configuration from ``ue-eyes.toml``.

    Walks up from *start_dir* (defaults to the current working directory) until
    the file is found or the git root / filesystem root is reached.  Returns an
    :class:`UEEyesConfig` with all defaults if no config file exists.
    """
    if start_dir is None:
        start_dir = Path.cwd()

    config_path = _find_config(start_dir)

    if config_path is None:
        logger.debug("No %s found; using defaults", CONFIG_FILENAME)
        return UEEyesConfig()

    logger.debug("Loading config from %s", config_path)
    with open(config_path, "rb") as fh:
        raw = tomllib.load(fh)

    return _parse_toml(raw)
