"""Tests for ue_eyes.cli using Click's CliRunner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ue_eyes import __version__
from ue_eyes.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ------------------------------------------------------------------
# Version & help
# ------------------------------------------------------------------


def test_version(runner: CliRunner) -> None:
    """--version prints the version string."""
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    assert "ue-eyes" in result.output


def test_help(runner: CliRunner) -> None:
    """--help shows all commands."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ping", "snap", "render", "cameras", "compare", "score"):
        assert cmd in result.output


# ------------------------------------------------------------------
# ping
# ------------------------------------------------------------------


def test_ping_command_exists(runner: CliRunner) -> None:
    """ping --help works and documents the command."""
    result = runner.invoke(main, ["ping", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output


@patch("ue_eyes.cli.UERemoteExecution")
def test_ping_success(mock_ue_cls: MagicMock, runner: CliRunner) -> None:
    """ping exits 0 and prints success when UE is reachable."""
    mock_ue_cls.return_value.ping.return_value = True
    result = runner.invoke(main, ["ping"])
    assert result.exit_code == 0
    assert "reachable" in result.output


@patch("ue_eyes.cli.UERemoteExecution")
def test_ping_failure(mock_ue_cls: MagicMock, runner: CliRunner) -> None:
    """ping exits 1 and prints failure when UE is not reachable."""
    mock_ue_cls.return_value.ping.return_value = False
    result = runner.invoke(main, ["ping"])
    assert result.exit_code == 1
    assert "NOT reachable" in result.output


# ------------------------------------------------------------------
# snap
# ------------------------------------------------------------------


def test_snap_requires_output(runner: CliRunner) -> None:
    """snap without --output fails."""
    result = runner.invoke(main, ["snap"])
    assert result.exit_code != 0
    assert "Missing" in result.output or "required" in result.output.lower()


@patch("ue_eyes.cli.snap_frame")
def test_snap_command(mock_snap: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    """snap with --output calls snap_frame correctly and prints success."""
    mock_snap.return_value = {
        "frame_count": 1,
        "type": "snap",
        "output_dir": str(tmp_path),
        "frames": [],
    }
    result = runner.invoke(main, ["snap", "--output", str(tmp_path)])
    assert result.exit_code == 0
    assert "Captured 1 frame(s)" in result.output
    mock_snap.assert_called_once_with(
        output_dir=str(tmp_path),
        camera=None,
        width=1920,
        height=1080,
    )


@patch("ue_eyes.cli.snap_frame")
def test_snap_with_camera_and_resolution(
    mock_snap: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    """snap passes camera and resolution options through."""
    mock_snap.return_value = {"frame_count": 1, "frames": []}
    result = runner.invoke(main, [
        "snap", "--output", str(tmp_path),
        "--camera", "CineCam1",
        "--width", "1280",
        "--height", "720",
    ])
    assert result.exit_code == 0
    mock_snap.assert_called_once_with(
        output_dir=str(tmp_path),
        camera="CineCam1",
        width=1280,
        height=720,
    )


# ------------------------------------------------------------------
# render
# ------------------------------------------------------------------


def test_render_requires_options(runner: CliRunner) -> None:
    """render without required options fails."""
    result = runner.invoke(main, ["render"])
    assert result.exit_code != 0


def test_render_requires_sequence(runner: CliRunner, tmp_path: Path) -> None:
    """render without --sequence fails."""
    result = runner.invoke(main, ["render", "--output", str(tmp_path), "--map", "/Game/Map"])
    assert result.exit_code != 0


@patch("ue_eyes.cli.render_sequence")
def test_render_parses_frames(
    mock_render: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    """--frames '1,30,60' is parsed to a list of ints."""
    mock_render.return_value = {"frame_count": 3, "frames": []}
    result = runner.invoke(main, [
        "render",
        "--output", str(tmp_path),
        "--sequence", "/Game/Seq",
        "--map", "/Game/Map",
        "--frames", "1,30,60",
    ])
    assert result.exit_code == 0
    call_kwargs = mock_render.call_args[1]
    assert call_kwargs["frames"] == [1, 30, 60]


@patch("ue_eyes.cli.render_sequence")
def test_render_parses_range(
    mock_render: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    """--range '0-100' is parsed to a (0, 100) tuple."""
    mock_render.return_value = {"frame_count": 101, "frames": []}
    result = runner.invoke(main, [
        "render",
        "--output", str(tmp_path),
        "--sequence", "/Game/Seq",
        "--map", "/Game/Map",
        "--range", "0-100",
    ])
    assert result.exit_code == 0
    call_kwargs = mock_render.call_args[1]
    assert call_kwargs["frame_range"] == (0, 100)


@patch("ue_eyes.cli.render_sequence")
def test_render_default_options(
    mock_render: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    """render passes correct defaults when optional args are omitted."""
    mock_render.return_value = {"frame_count": 0, "frames": []}
    result = runner.invoke(main, [
        "render",
        "--output", str(tmp_path),
        "--sequence", "/Game/Seq",
        "--map", "/Game/Map",
    ])
    assert result.exit_code == 0
    call_kwargs = mock_render.call_args[1]
    assert call_kwargs["frames"] is None
    assert call_kwargs["frame_range"] is None
    assert call_kwargs["frame_step"] == 1
    assert call_kwargs["width"] == 1920
    assert call_kwargs["height"] == 1080


# ------------------------------------------------------------------
# cameras
# ------------------------------------------------------------------


@patch("ue_eyes.cli.discover_cameras")
@patch("ue_eyes.cli.UERemoteExecution")
def test_cameras_command(
    mock_ue_cls: MagicMock,
    mock_discover: MagicMock,
    runner: CliRunner,
) -> None:
    """cameras lists discovered cameras in the expected format."""
    from ue_eyes.cameras import CameraInfo

    mock_discover.return_value = [
        CameraInfo(name="CineCam1", location=[100.0, 200.0, 300.0], rotation=[0.0, 90.0, 0.0]),
        CameraInfo(name="FrontCam", location=[0.0, 0.0, 150.0], rotation=[-15.0, 0.0, 0.0]),
    ]
    # Make the context manager work
    mock_ue_cls.return_value.__enter__ = MagicMock(return_value=mock_ue_cls.return_value)
    mock_ue_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = runner.invoke(main, ["cameras"])
    assert result.exit_code == 0
    assert "CineCam1" in result.output
    assert "FrontCam" in result.output
    assert "location=" in result.output
    assert "rotation=" in result.output


# ------------------------------------------------------------------
# compare
# ------------------------------------------------------------------


def test_compare_requires_options(runner: CliRunner) -> None:
    """compare without --reference fails."""
    result = runner.invoke(main, ["compare"])
    assert result.exit_code != 0


def test_compare_requires_capture(runner: CliRunner, tmp_path: Path) -> None:
    """compare without --capture fails."""
    result = runner.invoke(main, [
        "compare", "--reference", str(tmp_path), "--output", str(tmp_path / "out"),
    ])
    assert result.exit_code != 0


@patch("ue_eyes.cli.create_difference_map")
@patch("ue_eyes.cli.create_comparison")
@patch("ue_eyes.cli.match_frames")
def test_compare_command(
    mock_match: MagicMock,
    mock_comp: MagicMock,
    mock_diff: MagicMock,
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """compare generates comparison and diff images for each matched pair."""
    ref_dir = tmp_path / "ref"
    cap_dir = tmp_path / "cap"
    out_dir = tmp_path / "out"
    ref_dir.mkdir()
    cap_dir.mkdir()

    mock_match.return_value = [
        (str(ref_dir / "frame_001.png"), str(cap_dir / "frame_001.png")),
    ]

    result = runner.invoke(main, [
        "compare",
        "--reference", str(ref_dir),
        "--capture", str(cap_dir),
        "--output", str(out_dir),
    ])
    assert result.exit_code == 0
    assert "Generated 1 comparison(s)" in result.output
    mock_comp.assert_called_once()
    mock_diff.assert_called_once()


# ------------------------------------------------------------------
# score
# ------------------------------------------------------------------


def test_score_requires_options(runner: CliRunner) -> None:
    """score without --reference fails."""
    result = runner.invoke(main, ["score"])
    assert result.exit_code != 0


def test_score_requires_capture(runner: CliRunner, tmp_path: Path) -> None:
    """score without --capture fails."""
    result = runner.invoke(main, ["score", "--reference", str(tmp_path)])
    assert result.exit_code != 0


@patch("ue_eyes.cli.compute_scores")
@patch("ue_eyes.cli.match_frames")
@patch("ue_eyes.cli.load_scorer")
def test_score_default_metrics(
    mock_load: MagicMock,
    mock_match: MagicMock,
    mock_compute: MagicMock,
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """Default metric is 'ssim'."""
    ref_dir = tmp_path / "ref"
    cap_dir = tmp_path / "cap"
    ref_dir.mkdir()
    cap_dir.mkdir()

    mock_load.return_value = MagicMock()
    mock_match.return_value = [
        (str(ref_dir / "frame_001.png"), str(cap_dir / "frame_001.png")),
    ]
    mock_compute.return_value = {
        "scores": {"ssim": 0.95},
        "composite": 0.95,
    }

    result = runner.invoke(main, [
        "score",
        "--reference", str(ref_dir),
        "--capture", str(cap_dir),
    ])
    assert result.exit_code == 0

    # Verify load_scorer was called with "ssim" (the default)
    mock_load.assert_called_with("ssim")

    # Verify compute_scores received metric_list with just "ssim"
    call_args = mock_compute.call_args
    assert call_args[0][2] == ["ssim"]


@patch("ue_eyes.cli.compute_scores")
@patch("ue_eyes.cli.match_frames")
@patch("ue_eyes.cli.load_scorer")
def test_score_custom_metrics(
    mock_load: MagicMock,
    mock_match: MagicMock,
    mock_compute: MagicMock,
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """--metrics 'ssim,pixel_mse' is parsed and passed correctly."""
    ref_dir = tmp_path / "ref"
    cap_dir = tmp_path / "cap"
    ref_dir.mkdir()
    cap_dir.mkdir()

    mock_load.return_value = MagicMock()
    mock_match.return_value = [
        (str(ref_dir / "frame_001.png"), str(cap_dir / "frame_001.png")),
    ]
    mock_compute.return_value = {
        "scores": {"ssim": 0.95, "pixel_mse": 0.88},
        "composite": 0.915,
    }

    result = runner.invoke(main, [
        "score",
        "--reference", str(ref_dir),
        "--capture", str(cap_dir),
        "--metrics", "ssim,pixel_mse",
    ])
    assert result.exit_code == 0

    # load_scorer should be called for each metric
    assert mock_load.call_count == 2

    # compute_scores should receive both metrics
    call_args = mock_compute.call_args
    assert call_args[0][2] == ["ssim", "pixel_mse"]
    assert "ssim" in result.output
    assert "pixel_mse" in result.output
