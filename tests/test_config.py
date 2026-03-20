"""Tests for ue_eyes.config — TOML discovery, parsing, and defaults."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ue_eyes.config import (
    CONFIG_FILENAME,
    DEFAULT_CAPTURE_MODE,
    DEFAULT_COMPOSITE_WEIGHTS,
    DEFAULT_METRICS,
    DEFAULT_MULTICAST_GROUP,
    DEFAULT_MULTICAST_PORT,
    DEFAULT_PARAMS_FILE,
    DEFAULT_RESOLUTION,
    DEFAULT_TIMEOUT,
    CameraPreset,
    UEEyesConfig,
    load_config,
)


# ------------------------------------------------------------------
# 1. test_defaults
# ------------------------------------------------------------------

def test_defaults() -> None:
    """UEEyesConfig() has correct default values for all fields."""
    cfg = UEEyesConfig()
    assert cfg.multicast_group == DEFAULT_MULTICAST_GROUP
    assert cfg.multicast_port == DEFAULT_MULTICAST_PORT
    assert cfg.timeout == DEFAULT_TIMEOUT
    assert cfg.capture_mode == DEFAULT_CAPTURE_MODE
    assert cfg.default_resolution == DEFAULT_RESOLUTION
    assert cfg.sequence_path == ""
    assert cfg.map_path == ""
    assert cfg.cameras == {}
    assert cfg.metrics == DEFAULT_METRICS
    assert cfg.composite_weights == DEFAULT_COMPOSITE_WEIGHTS
    assert cfg.params_file == DEFAULT_PARAMS_FILE


# ------------------------------------------------------------------
# 2. test_camera_preset_defaults
# ------------------------------------------------------------------

def test_camera_preset_defaults() -> None:
    """CameraPreset(name='x') has correct defaults."""
    cam = CameraPreset(name="x")
    assert cam.name == "x"
    assert cam.location == [0.0, 0.0, 0.0]
    assert cam.rotation == [0.0, 0.0, 0.0]
    assert cam.tracking_mode == "fixed"
    assert cam.target_actor == ""
    assert cam.target_bone == ""
    assert cam.offset == [0.0, 0.0, 0.0]


# ------------------------------------------------------------------
# 3. test_load_no_file_returns_defaults
# ------------------------------------------------------------------

def test_load_no_file_returns_defaults(tmp_path: Path) -> None:
    """load_config returns defaults when no toml file exists."""
    cfg = load_config(tmp_path)
    assert cfg == UEEyesConfig()


# ------------------------------------------------------------------
# 4. test_load_from_toml
# ------------------------------------------------------------------

def test_load_from_toml(tmp_path: Path) -> None:
    """Write a full toml file, load it, verify all fields parsed."""
    toml_text = textwrap.dedent("""\
        version = 1

        [connection]
        multicast_group = "239.0.0.2"
        multicast_port = 7000
        timeout = 60

        [capture]
        mode = "render"
        default_resolution = [3840, 2160]
        sequence_path = "/Game/Seq"
        map_path = "/Game/Map"

        [cameras.top]
        location = [0, 0, 500]
        rotation = [-90, 0, 0]
        tracking_mode = "fixed"

        [scoring]
        metrics = ["ssim", "psnr"]
        composite_weights = { ssim = 0.7, psnr = 0.3 }

        [parameters]
        file = "my_params.json"
    """)
    (tmp_path / CONFIG_FILENAME).write_text(toml_text)

    cfg = load_config(tmp_path)
    assert cfg.multicast_group == "239.0.0.2"
    assert cfg.multicast_port == 7000
    assert cfg.timeout == 60
    assert cfg.capture_mode == "render"
    assert cfg.default_resolution == [3840, 2160]
    assert cfg.sequence_path == "/Game/Seq"
    assert cfg.map_path == "/Game/Map"
    assert "top" in cfg.cameras
    assert cfg.cameras["top"].location == [0, 0, 500]
    assert cfg.cameras["top"].rotation == [-90, 0, 0]
    assert cfg.cameras["top"].tracking_mode == "fixed"
    assert cfg.metrics == ["ssim", "psnr"]
    assert cfg.composite_weights == {"ssim": 0.7, "psnr": 0.3}
    assert cfg.params_file == "my_params.json"


# ------------------------------------------------------------------
# 5. test_discovery_walks_up
# ------------------------------------------------------------------

def test_discovery_walks_up(tmp_path: Path) -> None:
    """Config in parent dir is found when load_config starts in child dir."""
    toml_text = textwrap.dedent("""\
        version = 1

        [connection]
        timeout = 99
    """)
    (tmp_path / CONFIG_FILENAME).write_text(toml_text)
    child = tmp_path / "a" / "b" / "c"
    child.mkdir(parents=True)

    cfg = load_config(child)
    assert cfg.timeout == 99


# ------------------------------------------------------------------
# 6. test_discovery_stops_at_git_root
# ------------------------------------------------------------------

def test_discovery_stops_at_git_root(tmp_path: Path) -> None:
    """Config above a .git boundary is not found."""
    # Structure:  tmp/ue-eyes.toml  (should NOT be found)
    #             tmp/repo/.git/    (git root)
    #             tmp/repo/sub/     (start_dir)
    (tmp_path / CONFIG_FILENAME).write_text('version = 1\n[connection]\ntimeout = 42\n')
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()  # marks git root
    sub = repo / "sub"
    sub.mkdir()

    cfg = load_config(sub)
    # Should NOT have found the toml above .git
    assert cfg.timeout == DEFAULT_TIMEOUT
    assert cfg == UEEyesConfig()


# ------------------------------------------------------------------
# 7. test_version_validation
# ------------------------------------------------------------------

def test_version_validation(tmp_path: Path) -> None:
    """version=2 raises ValueError."""
    (tmp_path / CONFIG_FILENAME).write_text("version = 2\n")

    with pytest.raises(ValueError, match="Unsupported config version"):
        load_config(tmp_path)


# ------------------------------------------------------------------
# 8. test_camera_presets_parsed
# ------------------------------------------------------------------

def test_camera_presets_parsed(tmp_path: Path) -> None:
    """Multiple [cameras.X] sections become a dict of CameraPreset."""
    toml_text = textwrap.dedent("""\
        version = 1

        [cameras.front]
        location = [0, -200, 100]
        tracking_mode = "look_at"
        target_actor = "BP_Char"
        target_bone = "head"

        [cameras.side]
        location = [200, 0, 100]
        tracking_mode = "fixed"

        [cameras.top]
        location = [0, 0, 500]
        rotation = [-90, 0, 0]
    """)
    (tmp_path / CONFIG_FILENAME).write_text(toml_text)

    cfg = load_config(tmp_path)
    assert len(cfg.cameras) == 3
    assert set(cfg.cameras.keys()) == {"front", "side", "top"}

    front = cfg.cameras["front"]
    assert isinstance(front, CameraPreset)
    assert front.name == "front"
    assert front.location == [0, -200, 100]
    assert front.tracking_mode == "look_at"
    assert front.target_actor == "BP_Char"
    assert front.target_bone == "head"

    side = cfg.cameras["side"]
    assert side.name == "side"
    assert side.tracking_mode == "fixed"

    top = cfg.cameras["top"]
    assert top.rotation == [-90, 0, 0]


# ------------------------------------------------------------------
# 9. test_partial_config
# ------------------------------------------------------------------

def test_partial_config(tmp_path: Path) -> None:
    """Config with only [connection]; everything else uses defaults."""
    toml_text = textwrap.dedent("""\
        version = 1

        [connection]
        multicast_port = 9999
    """)
    (tmp_path / CONFIG_FILENAME).write_text(toml_text)

    cfg = load_config(tmp_path)
    assert cfg.multicast_port == 9999
    # All other fields are defaults
    assert cfg.multicast_group == DEFAULT_MULTICAST_GROUP
    assert cfg.timeout == DEFAULT_TIMEOUT
    assert cfg.capture_mode == DEFAULT_CAPTURE_MODE
    assert cfg.default_resolution == DEFAULT_RESOLUTION
    assert cfg.cameras == {}
    assert cfg.metrics == DEFAULT_METRICS
    assert cfg.composite_weights == DEFAULT_COMPOSITE_WEIGHTS
    assert cfg.params_file == DEFAULT_PARAMS_FILE


# ------------------------------------------------------------------
# 10. test_camera_tracking_modes
# ------------------------------------------------------------------

def test_camera_tracking_modes(tmp_path: Path) -> None:
    """All three tracking modes (fixed, look_at, follow) parse correctly."""
    toml_text = textwrap.dedent("""\
        version = 1

        [cameras.cam_fixed]
        tracking_mode = "fixed"
        location = [100, 0, 0]

        [cameras.cam_look_at]
        tracking_mode = "look_at"
        target_actor = "ActorA"
        target_bone = "spine_03"

        [cameras.cam_follow]
        tracking_mode = "follow"
        target_actor = "ActorB"
        offset = [0, -300, 80]
    """)
    (tmp_path / CONFIG_FILENAME).write_text(toml_text)

    cfg = load_config(tmp_path)
    assert cfg.cameras["cam_fixed"].tracking_mode == "fixed"
    assert cfg.cameras["cam_fixed"].location == [100, 0, 0]

    assert cfg.cameras["cam_look_at"].tracking_mode == "look_at"
    assert cfg.cameras["cam_look_at"].target_actor == "ActorA"
    assert cfg.cameras["cam_look_at"].target_bone == "spine_03"

    assert cfg.cameras["cam_follow"].tracking_mode == "follow"
    assert cfg.cameras["cam_follow"].target_actor == "ActorB"
    assert cfg.cameras["cam_follow"].offset == [0, -300, 80]
