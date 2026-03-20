"""Tests for ue_eyes.capture — frame capture orchestration.

All tests use mocked UERemoteExecution and do NOT require a running UE instance.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from ue_eyes.capture import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MANIFEST_FILENAME,
    _detect_plugin,
    _SNAP_SCRIPT,
    _RENDER_SCRIPT,
    snap_frame,
    render_sequence,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def mock_ue():
    """Return a mock UERemoteExecution that succeeds on all calls."""
    ue = MagicMock()
    ue.execute.return_value = {"success": True, "output": "False", "result": ""}
    ue.execute_file.return_value = {"success": True, "output": "", "result": ""}
    return ue


@pytest.fixture
def output_dir(tmp_path):
    """Return a temporary output directory path as a string."""
    return str(tmp_path / "captures")


# ======================================================================
# snap_frame tests
# ======================================================================


class TestSnapFrame:
    def test_snap_creates_output_dir(self, mock_ue, tmp_path):
        """snap_frame creates output_dir if it does not exist."""
        out = tmp_path / "new_dir" / "nested"
        snap_frame(str(out), ue=mock_ue)
        assert out.exists()
        assert out.is_dir()

    def test_snap_calls_execute_file_with_correct_script(self, mock_ue, output_dir):
        """snap_frame passes the capture_frame.py script to execute_file."""
        snap_frame(output_dir, ue=mock_ue)
        mock_ue.execute_file.assert_called_once()
        script_arg = mock_ue.execute_file.call_args[0][0]
        assert script_arg == str(_SNAP_SCRIPT)

    def test_snap_passes_params(self, mock_ue, output_dir):
        """snap_frame passes width, height, and camera_name as kwargs."""
        snap_frame(output_dir, camera="FrontCam", width=800, height=600, ue=mock_ue)
        kwargs = mock_ue.execute_file.call_args[1]
        assert kwargs["width"] == 800
        assert kwargs["height"] == 600
        assert kwargs["camera_name"] == "FrontCam"

    def test_snap_manifest_keys(self, mock_ue, output_dir):
        """Returned manifest dict has required keys."""
        manifest = snap_frame(output_dir, camera="Cam1", ue=mock_ue)
        assert manifest["type"] == "snap"
        assert "timestamp" in manifest
        assert manifest["camera"] == "Cam1"
        assert manifest["resolution"] == [DEFAULT_WIDTH, DEFAULT_HEIGHT]
        assert "frame_count" in manifest
        assert "frames" in manifest
        assert "output_dir" in manifest
        assert "ue_output" in manifest

    def test_snap_writes_manifest_file(self, mock_ue, output_dir):
        """capture_manifest.json is written to output_dir."""
        snap_frame(output_dir, ue=mock_ue)
        manifest_path = Path(output_dir).resolve() / MANIFEST_FILENAME
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["type"] == "snap"

    def test_snap_no_camera_uses_viewport(self, mock_ue, output_dir):
        """When camera=None, camera_name is not in the execute_file kwargs."""
        snap_frame(output_dir, ue=mock_ue)
        kwargs = mock_ue.execute_file.call_args[1]
        assert "camera_name" not in kwargs

    def test_snap_manifest_camera_none_when_no_camera(self, mock_ue, output_dir):
        """When camera=None, manifest camera field is None."""
        manifest = snap_frame(output_dir, ue=mock_ue)
        assert manifest["camera"] is None

    def test_snap_default_resolution(self, mock_ue, output_dir):
        """Default resolution uses named constants."""
        manifest = snap_frame(output_dir, ue=mock_ue)
        assert manifest["resolution"] == [DEFAULT_WIDTH, DEFAULT_HEIGHT]
        assert DEFAULT_WIDTH == 1920
        assert DEFAULT_HEIGHT == 1080


# ======================================================================
# render_sequence tests
# ======================================================================


class TestRenderSequence:
    def test_render_calls_execute_file(self, mock_ue, output_dir):
        """render_sequence passes the render_sequence.py script to execute_file."""
        render_sequence(
            output_dir, "/Game/Seq/Test", "/Game/Maps/TestMap", ue=mock_ue,
        )
        mock_ue.execute_file.assert_called_once()
        script_arg = mock_ue.execute_file.call_args[0][0]
        assert script_arg == str(_RENDER_SCRIPT)

    def test_render_passes_frame_params(self, mock_ue, output_dir):
        """render_sequence passes frames, frame_range, frame_step, resolution."""
        render_sequence(
            output_dir,
            "/Game/Seq/Test",
            "/Game/Maps/TestMap",
            frames=[0, 5, 10],
            frame_range=(0, 100),
            frame_step=5,
            width=3840,
            height=2160,
            ue=mock_ue,
        )
        kwargs = mock_ue.execute_file.call_args[1]
        assert kwargs["frames"] == [0, 5, 10]
        assert kwargs["frame_range"] == [0, 100]
        assert kwargs["frame_step"] == 5
        assert kwargs["resolution"] == [3840, 2160]

    def test_render_manifest_keys(self, mock_ue, output_dir):
        """Returned render manifest has all required keys."""
        manifest = render_sequence(
            output_dir, "/Game/Seq/Test", "/Game/Maps/TestMap", ue=mock_ue,
        )
        assert manifest["type"] == "render"
        assert manifest["sequence_path"] == "/Game/Seq/Test"
        assert manifest["map_path"] == "/Game/Maps/TestMap"
        assert "timestamp" in manifest
        assert "resolution" in manifest
        assert "frame_count" in manifest
        assert "frames" in manifest
        assert "ue_output" in manifest

    def test_render_creates_output_dir(self, mock_ue, tmp_path):
        """render_sequence creates output_dir if it does not exist."""
        out = tmp_path / "render_out"
        render_sequence(str(out), "/Game/Seq/X", "/Game/Maps/Y", ue=mock_ue)
        assert out.exists()

    def test_render_optional_params_omitted(self, mock_ue, output_dir):
        """When frames and frame_range are None, they are not in kwargs."""
        render_sequence(
            output_dir, "/Game/Seq/Test", "/Game/Maps/TestMap", ue=mock_ue,
        )
        kwargs = mock_ue.execute_file.call_args[1]
        assert "frames" not in kwargs
        assert "frame_range" not in kwargs

    def test_render_writes_manifest_file(self, mock_ue, output_dir):
        """capture_manifest.json is written to output_dir for renders."""
        render_sequence(
            output_dir, "/Game/Seq/Test", "/Game/Maps/TestMap", ue=mock_ue,
        )
        manifest_path = Path(output_dir).resolve() / MANIFEST_FILENAME
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["type"] == "render"


# ======================================================================
# _detect_plugin tests
# ======================================================================


class TestDetectPlugin:
    def test_detect_plugin_returns_false_no_service(self):
        """Returns False when UE responds with 'False' (no CaptureService)."""
        ue = MagicMock()
        ue.execute.return_value = {"success": True, "output": "False", "result": ""}
        assert _detect_plugin(ue) is False

    def test_detect_plugin_returns_true(self):
        """Returns True when UE responds with 'True'."""
        ue = MagicMock()
        ue.execute.return_value = {"success": True, "output": "True", "result": ""}
        assert _detect_plugin(ue) is True

    def test_detect_plugin_returns_false_on_error(self):
        """Returns False when execute raises an exception."""
        ue = MagicMock()
        ue.execute.side_effect = RuntimeError("connection lost")
        assert _detect_plugin(ue) is False

    def test_detect_plugin_returns_false_on_empty_output(self):
        """Returns False when UE returns empty output."""
        ue = MagicMock()
        ue.execute.return_value = {"success": True, "output": "", "result": ""}
        assert _detect_plugin(ue) is False


# ======================================================================
# UE connection management
# ======================================================================


class TestConnectionManagement:
    @patch("ue_eyes.capture.UERemoteExecution")
    def test_snap_creates_ue_connection_when_none(self, MockUE, output_dir):
        """When ue=None, snap_frame creates a UERemoteExecution and connects."""
        mock_instance = MagicMock()
        mock_instance.execute.return_value = {
            "success": True, "output": "False", "result": "",
        }
        mock_instance.execute_file.return_value = {
            "success": True, "output": "", "result": "",
        }
        MockUE.return_value = mock_instance

        snap_frame(output_dir)

        MockUE.assert_called_once()
        mock_instance.connect.assert_called_once()
        mock_instance.close.assert_called_once()

    @patch("ue_eyes.capture.UERemoteExecution")
    def test_render_creates_ue_connection_when_none(self, MockUE, output_dir):
        """When ue=None, render_sequence creates a UERemoteExecution and connects."""
        mock_instance = MagicMock()
        mock_instance.execute_file.return_value = {
            "success": True, "output": "", "result": "",
        }
        MockUE.return_value = mock_instance

        render_sequence(output_dir, "/Game/Seq/X", "/Game/Maps/Y")

        MockUE.assert_called_once()
        mock_instance.connect.assert_called_once()
        mock_instance.close.assert_called_once()

    @patch("ue_eyes.capture.UERemoteExecution")
    def test_snap_closes_connection_on_error(self, MockUE, output_dir):
        """When ue=None and execute_file raises, close is still called."""
        mock_instance = MagicMock()
        mock_instance.execute.return_value = {
            "success": True, "output": "False", "result": "",
        }
        mock_instance.execute_file.side_effect = RuntimeError("UE crashed")
        MockUE.return_value = mock_instance

        with pytest.raises(RuntimeError, match="UE crashed"):
            snap_frame(output_dir)

        mock_instance.close.assert_called_once()

    def test_snap_does_not_close_provided_connection(self, mock_ue, output_dir):
        """When ue is provided, snap_frame does NOT close it."""
        snap_frame(output_dir, ue=mock_ue)
        mock_ue.close.assert_not_called()
        mock_ue.connect.assert_not_called()


# ======================================================================
# Plugin-based capture path
# ======================================================================


class TestPluginCapture:
    def test_snap_uses_plugin_when_detected(self, output_dir):
        """When plugin is detected, snap_frame delegates to CaptureService."""
        ue = MagicMock()
        # First call: _detect_plugin -> "True"
        # Second call: plugin capture command
        ue.execute.side_effect = [
            {"success": True, "output": "True", "result": ""},
            {"success": True, "output": "captured", "result": ""},
        ]

        manifest = snap_frame(output_dir, ue=ue)

        # Two execute calls: detect + capture
        assert ue.execute.call_count == 2
        # execute_file should NOT be called (plugin path skips the script)
        ue.execute_file.assert_not_called()
        assert manifest["type"] == "snap"

    def test_snap_uses_plugin_with_camera(self, output_dir):
        """When plugin is detected and camera is set, uses CaptureFromPreset."""
        ue = MagicMock()
        ue.execute.side_effect = [
            {"success": True, "output": "True", "result": ""},
            {"success": True, "output": "captured", "result": ""},
        ]

        snap_frame(output_dir, camera="TopCam", ue=ue)

        capture_code = ue.execute.call_args_list[1][0][0]
        assert "CaptureFromPreset" in capture_code
        assert "TopCam" in capture_code

    def test_snap_uses_script_when_plugin_not_detected(self, mock_ue, output_dir):
        """When plugin is NOT detected, snap_frame uses execute_file with script."""
        snap_frame(output_dir, ue=mock_ue)

        # _detect_plugin called execute once (returned "False")
        mock_ue.execute.assert_called_once()
        # Then the script path was used
        mock_ue.execute_file.assert_called_once()
