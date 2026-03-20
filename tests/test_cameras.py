"""Tests for ue_eyes.cameras -- camera discovery, presets, tracking, ad-hoc spawn.

All tests use mocked UERemoteExecution and do NOT require a running UE instance.
"""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from ue_eyes.cameras import (
    CameraInfo,
    DEFAULT_ADHOC_NAME,
    _CAMERA_CONTROL_SCRIPT,
    _SCENE_INFO_SCRIPT,
    _compute_follow_position,
    _compute_look_at_rotation,
    _query_target_transform,
    apply_preset,
    destroy_camera,
    discover_cameras,
    move_camera,
    spawn_camera,
)
from ue_eyes.config import CameraPreset, UEEyesConfig


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def mock_ue():
    """Return a mock UERemoteExecution that succeeds on all calls."""
    ue = MagicMock()
    ue.execute.return_value = {"success": True, "output": "", "result": ""}
    ue.execute_file.return_value = {"success": True, "output": "{}", "result": ""}
    return ue


def _make_config(presets: dict[str, CameraPreset] | None = None) -> UEEyesConfig:
    """Build a UEEyesConfig with the given camera presets."""
    return UEEyesConfig(cameras=presets or {})


# ======================================================================
# 1. CameraInfo dataclass
# ======================================================================


class TestCameraInfo:
    def test_camera_info_dataclass(self):
        """CameraInfo can be constructed with name, location, rotation."""
        cam = CameraInfo(name="Cam1", location=[1.0, 2.0, 3.0], rotation=[10.0, 20.0, 0.0])
        assert cam.name == "Cam1"
        assert cam.location == [1.0, 2.0, 3.0]
        assert cam.rotation == [10.0, 20.0, 0.0]


# ======================================================================
# 2-3. discover_cameras
# ======================================================================


class TestDiscoverCameras:
    def test_discover_cameras_parses_response(self, mock_ue):
        """discover_cameras parses JSON with 2 cameras from UE output."""
        cameras_data = {
            "action": "discover_cameras",
            "count": 2,
            "cameras": [
                {"name": "FrontCam", "location": [100.0, 0.0, 200.0],
                 "rotation": [0.0, 90.0, 0.0]},
                {"name": "SideCam", "location": [0.0, 300.0, 150.0],
                 "rotation": [-10.0, 0.0, 0.0]},
            ],
        }
        mock_ue.execute_file.return_value = {
            "success": True,
            "output": json.dumps(cameras_data),
            "result": "",
        }

        result = discover_cameras(mock_ue)

        assert len(result) == 2
        assert result[0].name == "FrontCam"
        assert result[0].location == [100.0, 0.0, 200.0]
        assert result[0].rotation == [0.0, 90.0, 0.0]
        assert result[1].name == "SideCam"

        # Verify correct script and action were used
        mock_ue.execute_file.assert_called_once()
        call_args = mock_ue.execute_file.call_args
        assert call_args[0][0] == str(_SCENE_INFO_SCRIPT)
        assert call_args[1]["action"] == "discover_cameras"

    def test_discover_cameras_empty(self, mock_ue):
        """discover_cameras returns empty list when UE reports no cameras."""
        mock_ue.execute_file.return_value = {
            "success": True,
            "output": json.dumps({"action": "discover_cameras", "count": 0, "cameras": []}),
            "result": "",
        }

        result = discover_cameras(mock_ue)

        assert result == []


# ======================================================================
# 4-7. apply_preset
# ======================================================================


class TestApplyPreset:
    def test_apply_preset_fixed(self, mock_ue):
        """Fixed mode spawns camera at preset location/rotation without querying target."""
        preset = CameraPreset(
            name="front",
            location=[100.0, 0.0, 200.0],
            rotation=[-15.0, 90.0, 0.0],
            tracking_mode="fixed",
        )
        config = _make_config({"front": preset})

        apply_preset("front", config, mock_ue)

        # Should call execute_file once (spawn), not query target
        mock_ue.execute_file.assert_called_once()
        call_args = mock_ue.execute_file.call_args
        assert call_args[0][0] == str(_CAMERA_CONTROL_SCRIPT)
        assert call_args[1]["action"] == "spawn"
        assert call_args[1]["name"] == "front"
        assert call_args[1]["location"] == [100.0, 0.0, 200.0]
        assert call_args[1]["rotation"] == [-15.0, 90.0, 0.0]

    def test_apply_preset_look_at(self, mock_ue):
        """look_at mode queries target transform, computes rotation toward it."""
        preset = CameraPreset(
            name="look_cam",
            location=[0.0, 0.0, 100.0],
            rotation=[0.0, 0.0, 0.0],  # ignored -- will be computed
            tracking_mode="look_at",
            target_actor="MyCharacter",
        )
        config = _make_config({"look_cam": preset})

        # First call: scene_info query returns target transform
        # Second call: camera_control spawn
        target_data = {
            "action": "get_actor_transform",
            "actor_name": "MyCharacter",
            "location": [100.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        }
        mock_ue.execute_file.side_effect = [
            {"success": True, "output": json.dumps(target_data), "result": ""},
            {"success": True, "output": "{}", "result": ""},
        ]

        apply_preset("look_cam", config, mock_ue)

        assert mock_ue.execute_file.call_count == 2

        # First call: query target
        query_call = mock_ue.execute_file.call_args_list[0]
        assert query_call[0][0] == str(_SCENE_INFO_SCRIPT)
        assert query_call[1]["action"] == "get_actor_transform"
        assert query_call[1]["actor_name"] == "MyCharacter"

        # Second call: spawn with computed rotation
        spawn_call = mock_ue.execute_file.call_args_list[1]
        assert spawn_call[1]["action"] == "spawn"
        assert spawn_call[1]["location"] == [0.0, 0.0, 100.0]
        # Rotation should point from [0,0,100] toward [100,0,0]
        rot = spawn_call[1]["rotation"]
        expected = _compute_look_at_rotation([0.0, 0.0, 100.0], [100.0, 0.0, 0.0])
        assert pytest.approx(rot, abs=1e-6) == expected

    def test_apply_preset_follow(self, mock_ue):
        """follow mode queries target, positions camera at target+offset, looks at target."""
        preset = CameraPreset(
            name="follow_cam",
            location=[0.0, 0.0, 0.0],  # ignored in follow mode
            rotation=[0.0, 0.0, 0.0],  # ignored -- computed
            tracking_mode="follow",
            target_actor="MyCharacter",
            offset=[0.0, -200.0, 50.0],
        )
        config = _make_config({"follow_cam": preset})

        target_data = {
            "action": "get_actor_transform",
            "actor_name": "MyCharacter",
            "location": [100.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        }
        mock_ue.execute_file.side_effect = [
            {"success": True, "output": json.dumps(target_data), "result": ""},
            {"success": True, "output": "{}", "result": ""},
        ]

        apply_preset("follow_cam", config, mock_ue)

        assert mock_ue.execute_file.call_count == 2

        spawn_call = mock_ue.execute_file.call_args_list[1]
        assert spawn_call[1]["action"] == "spawn"
        # Camera position = target [100,0,0] + offset [0,-200,50] = [100,-200,50]
        assert spawn_call[1]["location"] == [100.0, -200.0, 50.0]
        # Rotation should look from [100,-200,50] toward [100,0,0]
        expected_rot = _compute_look_at_rotation([100.0, -200.0, 50.0], [100.0, 0.0, 0.0])
        assert pytest.approx(spawn_call[1]["rotation"], abs=1e-6) == expected_rot

    def test_apply_preset_look_at_with_bone(self, mock_ue):
        """look_at with target_bone uses get_bone_transform instead of get_actor_transform."""
        preset = CameraPreset(
            name="bone_cam",
            location=[0.0, 0.0, 200.0],
            tracking_mode="look_at",
            target_actor="MyCharacter",
            target_bone="head",
        )
        config = _make_config({"bone_cam": preset})

        target_data = {
            "action": "get_bone_transform",
            "actor_name": "MyCharacter",
            "bone_name": "head",
            "location": [50.0, 0.0, 170.0],
            "rotation": [0.0, 0.0, 0.0],
        }
        mock_ue.execute_file.side_effect = [
            {"success": True, "output": json.dumps(target_data), "result": ""},
            {"success": True, "output": "{}", "result": ""},
        ]

        apply_preset("bone_cam", config, mock_ue)

        # Verify bone transform query
        query_call = mock_ue.execute_file.call_args_list[0]
        assert query_call[1]["action"] == "get_bone_transform"
        assert query_call[1]["actor_name"] == "MyCharacter"
        assert query_call[1]["bone_name"] == "head"


# ======================================================================
# 8-10. spawn / move / destroy
# ======================================================================


class TestCameraLifecycle:
    def test_spawn_camera_calls_script(self, mock_ue):
        """spawn_camera calls camera_control.py with action=spawn and correct params."""
        result = spawn_camera(mock_ue, [10.0, 20.0, 30.0], [-5.0, 45.0, 0.0], name="TestCam")

        assert result == "TestCam"
        mock_ue.execute_file.assert_called_once()
        call_args = mock_ue.execute_file.call_args
        assert call_args[0][0] == str(_CAMERA_CONTROL_SCRIPT)
        assert call_args[1]["action"] == "spawn"
        assert call_args[1]["name"] == "TestCam"
        assert call_args[1]["location"] == [10.0, 20.0, 30.0]
        assert call_args[1]["rotation"] == [-5.0, 45.0, 0.0]

    def test_spawn_camera_default_name(self, mock_ue):
        """spawn_camera uses DEFAULT_ADHOC_NAME when name is not provided."""
        result = spawn_camera(mock_ue, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])

        assert result == DEFAULT_ADHOC_NAME
        assert mock_ue.execute_file.call_args[1]["name"] == DEFAULT_ADHOC_NAME

    def test_move_camera_calls_script(self, mock_ue):
        """move_camera calls camera_control.py with action=move."""
        move_camera(mock_ue, "MyCam", [50.0, 60.0, 70.0], [-10.0, 180.0, 0.0])

        mock_ue.execute_file.assert_called_once()
        call_args = mock_ue.execute_file.call_args
        assert call_args[0][0] == str(_CAMERA_CONTROL_SCRIPT)
        assert call_args[1]["action"] == "move"
        assert call_args[1]["name"] == "MyCam"
        assert call_args[1]["location"] == [50.0, 60.0, 70.0]
        assert call_args[1]["rotation"] == [-10.0, 180.0, 0.0]

    def test_destroy_camera_calls_script(self, mock_ue):
        """destroy_camera calls camera_control.py with action=destroy."""
        destroy_camera(mock_ue, "OldCam")

        mock_ue.execute_file.assert_called_once()
        call_args = mock_ue.execute_file.call_args
        assert call_args[0][0] == str(_CAMERA_CONTROL_SCRIPT)
        assert call_args[1]["action"] == "destroy"
        assert call_args[1]["name"] == "OldCam"


# ======================================================================
# 11-12. Look-at rotation math
# ======================================================================


class TestLookAtRotation:
    def test_look_at_rotation_math(self):
        """Camera at [0,0,100] looking at [100,0,0] produces correct pitch/yaw."""
        rot = _compute_look_at_rotation([0.0, 0.0, 100.0], [100.0, 0.0, 0.0])
        # dx=100, dy=0, dz=-100 -> dist_xy=100
        # pitch = -atan2(-100, 100) = -(-pi/4) = 45°
        # yaw = atan2(0, 100) = 0°
        assert pytest.approx(rot[0], abs=1e-6) == 45.0   # pitch
        assert pytest.approx(rot[1], abs=1e-6) == 0.0     # yaw
        assert rot[2] == 0.0                               # roll

    def test_look_at_rotation_straight_down(self):
        """Camera directly above target -> pitch=-90 (looking straight down)."""
        rot = _compute_look_at_rotation([0.0, 0.0, 500.0], [0.0, 0.0, 0.0])
        # dx=0, dy=0, dz=-500 -> dist_xy=0
        # pitch = -atan2(-500, 0) = -(- pi/2) = 90
        # yaw = atan2(0, 0) = 0
        assert pytest.approx(rot[0], abs=1e-6) == 90.0
        assert pytest.approx(rot[1], abs=1e-6) == 0.0
        assert rot[2] == 0.0

    def test_look_at_rotation_horizontal(self):
        """Camera at same height as target -> pitch=0."""
        rot = _compute_look_at_rotation([0.0, 0.0, 0.0], [100.0, 100.0, 0.0])
        # dx=100, dy=100, dz=0 -> pitch=0, yaw=45°
        assert pytest.approx(rot[0], abs=1e-6) == 0.0
        assert pytest.approx(rot[1], abs=1e-6) == 45.0
        assert rot[2] == 0.0


# ======================================================================
# 13. Follow position math
# ======================================================================


class TestFollowPosition:
    def test_follow_position_math(self):
        """Target at [100,0,0] with offset [0,-200,50] -> camera at [100,-200,50]."""
        pos = _compute_follow_position([100.0, 0.0, 0.0], [0.0, -200.0, 50.0])
        assert pos == [100.0, -200.0, 50.0]

    def test_follow_position_zero_offset(self):
        """Zero offset places camera at target position."""
        pos = _compute_follow_position([42.0, 13.0, 7.0], [0.0, 0.0, 0.0])
        assert pos == [42.0, 13.0, 7.0]


# ======================================================================
# 14-15. _query_target_transform
# ======================================================================


class TestQueryTargetTransform:
    def test_query_target_transform_actor(self, mock_ue):
        """Calls scene_info with get_actor_transform when no bone is specified."""
        target_data = {
            "action": "get_actor_transform",
            "actor_name": "Hero",
            "location": [10.0, 20.0, 30.0],
            "rotation": [0.0, 90.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        }
        mock_ue.execute_file.return_value = {
            "success": True,
            "output": json.dumps(target_data),
            "result": "",
        }

        loc, rot = _query_target_transform(mock_ue, "Hero")

        assert loc == [10.0, 20.0, 30.0]
        assert rot == [0.0, 90.0, 0.0]

        call_args = mock_ue.execute_file.call_args
        assert call_args[0][0] == str(_SCENE_INFO_SCRIPT)
        assert call_args[1]["action"] == "get_actor_transform"
        assert call_args[1]["actor_name"] == "Hero"
        assert "bone_name" not in call_args[1]

    def test_query_target_transform_bone(self, mock_ue):
        """Calls scene_info with get_bone_transform when bone is specified."""
        target_data = {
            "action": "get_bone_transform",
            "actor_name": "Hero",
            "bone_name": "spine_03",
            "location": [10.0, 20.0, 90.0],
            "rotation": [5.0, 10.0, 0.0],
        }
        mock_ue.execute_file.return_value = {
            "success": True,
            "output": json.dumps(target_data),
            "result": "",
        }

        loc, rot = _query_target_transform(mock_ue, "Hero", target_bone="spine_03")

        assert loc == [10.0, 20.0, 90.0]
        assert rot == [5.0, 10.0, 0.0]

        call_args = mock_ue.execute_file.call_args
        assert call_args[0][0] == str(_SCENE_INFO_SCRIPT)
        assert call_args[1]["action"] == "get_bone_transform"
        assert call_args[1]["actor_name"] == "Hero"
        assert call_args[1]["bone_name"] == "spine_03"
