"""Camera discovery, presets with tracking, and ad-hoc camera management.

Orchestrates camera operations by sending scripts to UE via
:class:`~ue_eyes.remote_exec.UERemoteExecution`.  All tracking math runs
host-side; only spawn/move/destroy and transform queries are delegated to UE.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import CameraPreset, UEEyesConfig
from .remote_exec import UERemoteExecution

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

DEFAULT_ADHOC_NAME: str = "ue_eyes_adhoc"

# Paths to UE-side scripts
_SCRIPTS_DIR: Path = Path(__file__).resolve().parent / "unreal_scripts"
_SCENE_INFO_SCRIPT: Path = _SCRIPTS_DIR / "scene_info.py"
_CAMERA_CONTROL_SCRIPT: Path = _SCRIPTS_DIR / "camera_control.py"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CameraInfo:
    """Lightweight description of a camera discovered in the UE scene."""

    name: str
    location: list[float]
    rotation: list[float]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_look_at_rotation(camera_pos: list[float],
                              target_pos: list[float]) -> list[float]:
    """Compute ``[pitch, yaw, roll]`` to look from *camera_pos* toward *target_pos*.

    Uses the UE coordinate system: X = forward, Y = right, Z = up.
    """
    dx = target_pos[0] - camera_pos[0]
    dy = target_pos[1] - camera_pos[1]
    dz = target_pos[2] - camera_pos[2]
    dist_xy = np.sqrt(dx * dx + dy * dy)
    pitch = -np.degrees(np.arctan2(dz, dist_xy))  # UE pitch is inverted
    yaw = np.degrees(np.arctan2(dy, dx))
    return [float(pitch), float(yaw), 0.0]


def _query_target_transform(ue: UERemoteExecution, target_actor: str,
                            target_bone: str = "") -> tuple[list[float], list[float]]:
    """Query UE for the current world transform of a target actor or bone.

    Returns ``(location, rotation)`` where each is ``[x, y, z]`` /
    ``[pitch, yaw, roll]``.
    """
    if target_bone:
        result = ue.execute_file(
            str(_SCENE_INFO_SCRIPT),
            action="get_bone_transform",
            actor_name=target_actor,
            bone_name=target_bone,
        )
    else:
        result = ue.execute_file(
            str(_SCENE_INFO_SCRIPT),
            action="get_actor_transform",
            actor_name=target_actor,
        )

    data = json.loads(result["output"])
    return data["location"], data["rotation"]


def _compute_follow_position(target_pos: list[float],
                             offset: list[float]) -> list[float]:
    """Compute camera position as *target_pos* + *offset*."""
    return [
        target_pos[0] + offset[0],
        target_pos[1] + offset[1],
        target_pos[2] + offset[2],
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_cameras(ue: UERemoteExecution) -> list[CameraInfo]:
    """Query the UE scene for all ``CameraActor`` instances."""
    result = ue.execute_file(str(_SCENE_INFO_SCRIPT), action="discover_cameras")
    data = json.loads(result["output"])
    return [
        CameraInfo(name=c["name"], location=c["location"], rotation=c["rotation"])
        for c in data["cameras"]
    ]


def apply_preset(preset_name: str, config: UEEyesConfig,
                 ue: UERemoteExecution) -> None:
    """Apply the camera preset *preset_name* from *config*.

    Tracking modes:

    * **fixed** -- Spawn/move camera to preset location/rotation.
    * **look_at** -- Spawn/move camera to preset location; compute rotation
      toward the live target position queried from UE.
    * **follow** -- Compute camera position as ``target_position + offset``;
      rotate toward the live target position.
    """
    preset: CameraPreset = config.cameras[preset_name]
    mode = preset.tracking_mode

    if mode == "fixed":
        spawn_camera(ue, preset.location, preset.rotation, name=preset_name)

    elif mode == "look_at":
        target_loc, _target_rot = _query_target_transform(
            ue, preset.target_actor, preset.target_bone,
        )
        rotation = _compute_look_at_rotation(preset.location, target_loc)
        spawn_camera(ue, preset.location, rotation, name=preset_name)

    elif mode == "follow":
        target_loc, _target_rot = _query_target_transform(
            ue, preset.target_actor, preset.target_bone,
        )
        cam_pos = _compute_follow_position(target_loc, preset.offset)
        rotation = _compute_look_at_rotation(cam_pos, target_loc)
        spawn_camera(ue, cam_pos, rotation, name=preset_name)

    else:
        raise ValueError(f"Unknown tracking mode '{mode}' in preset '{preset_name}'")


def spawn_camera(ue: UERemoteExecution, location: list[float],
                 rotation: list[float],
                 name: str = DEFAULT_ADHOC_NAME) -> str:
    """Spawn a transient camera in UE.  Returns the camera name."""
    ue.execute_file(
        str(_CAMERA_CONTROL_SCRIPT),
        action="spawn",
        name=name,
        location=location,
        rotation=rotation,
    )
    return name


def move_camera(ue: UERemoteExecution, name: str, location: list[float],
                rotation: list[float]) -> None:
    """Move an existing camera to a new position/rotation."""
    ue.execute_file(
        str(_CAMERA_CONTROL_SCRIPT),
        action="move",
        name=name,
        location=location,
        rotation=rotation,
    )


def destroy_camera(ue: UERemoteExecution, name: str) -> None:
    """Destroy a camera by name."""
    ue.execute_file(
        str(_CAMERA_CONTROL_SCRIPT),
        action="destroy",
        name=name,
    )
