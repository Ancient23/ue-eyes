"""
Click-based CLI for the ue-eyes toolkit.

Entry point: ``ue-eyes`` (configured via pyproject.toml).

Commands
--------
- ``ue-eyes ping``       -- check whether UE is reachable
- ``ue-eyes snap``       -- capture a single frame from UE
- ``ue-eyes render``     -- render frames from a Level Sequence
- ``ue-eyes cameras``    -- discover and list all cameras
- ``ue-eyes compare``    -- generate side-by-side comparison images
- ``ue-eyes score``      -- compute similarity scores between frames
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ue_eyes import __version__
from ue_eyes.project_setup import (
    find_uproject,
    add_plugins_to_uproject,
    configure_remote_exec,
    get_symlink_command,
    verify_symlink,
)
from ue_eyes.remote_exec import (
    UEConnectionError,
    UEExecutionError,
    UERemoteExecution,
    DEFAULT_MULTICAST_GROUP,
    DEFAULT_MULTICAST_PORT,
)
from ue_eyes.capture import snap_frame, render_sequence, DEFAULT_WIDTH, DEFAULT_HEIGHT
from ue_eyes.cameras import discover_cameras
from ue_eyes.scoring.metrics import match_frames, compute_scores, load_scorer
from ue_eyes.scoring.compare import create_comparison, create_difference_map


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _dump_json(data: dict) -> None:
    """Pretty-print a dict as JSON to stdout."""
    click.echo(json.dumps(data, indent=2, default=str))


def _parse_resolution(value: str) -> tuple[int, int]:
    """Parse a ``WIDTHxHEIGHT`` string into (width, height)."""
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise click.BadParameter(f"Resolution must be WIDTHxHEIGHT, got: {value}")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        raise click.BadParameter(f"Non-integer resolution: {value}")


def _handle_ue_error(exc: Exception) -> None:
    """Print a helpful error message for UE connection/execution errors."""
    click.secho(f"Error: {exc}", fg="red", err=True)
    if isinstance(exc, UEConnectionError):
        click.secho(
            "Is the UE editor running with the Python Editor Script Plugin enabled?",
            fg="yellow",
            err=True,
        )
    sys.exit(1)


# ------------------------------------------------------------------
# CLI group
# ------------------------------------------------------------------


@click.group()
@click.version_option(version=__version__, prog_name="ue-eyes")
def main() -> None:
    """ue-eyes: Give AI agents visual access to Unreal Engine 5.7 projects."""


# ------------------------------------------------------------------
# ping
# ------------------------------------------------------------------


@main.command()
@click.option("--host", default=DEFAULT_MULTICAST_GROUP,
              help="UDP multicast group address.")
@click.option("--port", default=DEFAULT_MULTICAST_PORT, type=int,
              help="UDP multicast port.")
def ping(host: str, port: int) -> None:
    """Check if Unreal Engine is running and reachable."""
    ue = UERemoteExecution(multicast_group=host, multicast_port=port)
    reachable = ue.ping()
    if reachable:
        click.secho("UE is reachable", fg="green")
    else:
        click.secho("UE is NOT reachable", fg="red")
        sys.exit(1)


# ------------------------------------------------------------------
# snap
# ------------------------------------------------------------------


@main.command()
@click.option("--output", "-o", required=True, type=click.Path(),
              help="Output directory for captured frame.")
@click.option("--camera", "-c", default=None,
              help="Named camera actor. Uses viewport if omitted.")
@click.option("--width", default=DEFAULT_WIDTH, type=int,
              help="Capture width in pixels.")
@click.option("--height", default=DEFAULT_HEIGHT, type=int,
              help="Capture height in pixels.")
def snap(output: str, camera: str | None, width: int, height: int) -> None:
    """Capture a single frame from the UE viewport."""
    try:
        manifest = snap_frame(
            output_dir=output,
            camera=camera,
            width=width,
            height=height,
        )
    except (UEConnectionError, UEExecutionError) as exc:
        _handle_ue_error(exc)
        return  # unreachable, _handle_ue_error calls sys.exit

    click.secho(f"Captured {manifest['frame_count']} frame(s)", fg="green")
    _dump_json(manifest)


# ------------------------------------------------------------------
# render
# ------------------------------------------------------------------


@main.command()
@click.option("--output", "-o", required=True, type=click.Path(),
              help="Output directory for rendered frames.")
@click.option("--sequence", "-s", required=True,
              help="UE asset path to the Level Sequence.")
@click.option("--map", "-m", "map_path", required=True,
              help="UE asset path to the map/level.")
@click.option("--frames", default=None,
              help="Comma-separated frame numbers (e.g. 0,29,59).")
@click.option("--range", "frame_range", default=None,
              help="Frame range as START-END (e.g. 0-100).")
@click.option("--step", default=1, type=int,
              help="Frame step for range rendering.")
@click.option("--width", default=DEFAULT_WIDTH, type=int,
              help="Render width in pixels.")
@click.option("--height", default=DEFAULT_HEIGHT, type=int,
              help="Render height in pixels.")
def render(
    output: str,
    sequence: str,
    map_path: str,
    frames: str | None,
    frame_range: str | None,
    step: int,
    width: int,
    height: int,
) -> None:
    """Render frames from a Level Sequence via Movie Render Graph."""
    frame_list: list[int] | None = None
    if frames is not None:
        try:
            frame_list = [int(f.strip()) for f in frames.split(",")]
        except ValueError:
            raise click.BadParameter(f"Invalid frame list: {frames}")

    range_tuple: tuple[int, int] | None = None
    if frame_range is not None:
        parts = frame_range.split("-")
        if len(parts) != 2:
            raise click.BadParameter(f"Range must be START-END, got: {frame_range}")
        try:
            range_tuple = (int(parts[0]), int(parts[1]))
        except ValueError:
            raise click.BadParameter(f"Non-integer range: {frame_range}")

    try:
        manifest = render_sequence(
            output_dir=output,
            sequence_path=sequence,
            map_path=map_path,
            frames=frame_list,
            frame_range=range_tuple,
            frame_step=step,
            width=width,
            height=height,
        )
    except (UEConnectionError, UEExecutionError) as exc:
        _handle_ue_error(exc)
        return

    click.secho(f"Rendered {manifest['frame_count']} frame(s) to {output}", fg="green")
    _dump_json(manifest)


# ------------------------------------------------------------------
# cameras
# ------------------------------------------------------------------


@main.command()
def cameras() -> None:
    """Discover and list all cameras in the UE scene."""
    try:
        with UERemoteExecution() as ue:
            cam_list = discover_cameras(ue)
    except (UEConnectionError, UEExecutionError) as exc:
        _handle_ue_error(exc)
        return

    if not cam_list:
        click.secho("No cameras found in the scene.", fg="yellow")
        return

    click.secho(f"Found {len(cam_list)} camera(s):", fg="green")
    for cam in cam_list:
        click.echo(f"  {cam.name}: location={cam.location}, rotation={cam.rotation}")


# ------------------------------------------------------------------
# compare
# ------------------------------------------------------------------


@main.command()
@click.option("--reference", required=True, type=click.Path(exists=True),
              help="Directory containing reference frames.")
@click.option("--capture", required=True, type=click.Path(exists=True),
              help="Directory containing captured frames.")
@click.option("--output", "-o", required=True, type=click.Path(),
              help="Output directory for comparison images.")
def compare(reference: str, capture: str, output: str) -> None:
    """Generate side-by-side comparison and difference images."""
    pairs = match_frames(reference, capture)
    if not pairs:
        click.secho("No matching frames found between directories.", fg="yellow")
        sys.exit(1)

    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    for ref_path, cap_path in pairs:
        stem = Path(ref_path).stem
        comparison_path = str(out_dir / f"{stem}_compare.png")
        diff_path = str(out_dir / f"{stem}_diff.png")

        create_comparison(ref_path, cap_path, comparison_path)
        create_difference_map(ref_path, cap_path, diff_path)

    click.secho(f"Generated {len(pairs)} comparison(s) in {output}", fg="green")


# ------------------------------------------------------------------
# score
# ------------------------------------------------------------------


@main.command()
@click.option("--reference", required=True, type=click.Path(exists=True),
              help="Directory containing reference frames.")
@click.option("--capture", required=True, type=click.Path(exists=True),
              help="Directory containing captured frames.")
@click.option("--metrics", default="ssim",
              help="Comma-separated metric names (e.g. ssim,pixel_mse,phash).")
def score(reference: str, capture: str, metrics: str) -> None:
    """Compute similarity scores between reference and captured frames."""
    metric_list = [m.strip() for m in metrics.split(",")]

    # Validate metric names up front
    for name in metric_list:
        try:
            load_scorer(name)
        except (ImportError, AttributeError, ValueError) as exc:
            click.secho(f"Unknown metric '{name}': {exc}", fg="red", err=True)
            sys.exit(1)

    pairs = match_frames(reference, capture)
    if not pairs:
        click.secho("No matching frames found between directories.", fg="yellow")
        sys.exit(1)

    # Equal weights for all requested metrics
    weights = {m: 1.0 for m in metric_list}

    all_results: list[dict] = []
    for ref_path, cap_path in pairs:
        result = compute_scores(Path(ref_path), Path(cap_path), metric_list, weights)
        result["reference"] = ref_path
        result["capture"] = cap_path
        all_results.append(result)

        stem = Path(ref_path).stem
        scores_str = ", ".join(f"{k}={v:.4f}" for k, v in result["scores"].items())
        click.echo(f"  {stem}: {scores_str} (composite={result['composite']:.4f})")

    # Compute aggregate scores across all pairs
    if all_results:
        aggregate: dict[str, float] = {}
        for name in metric_list:
            values = [r["scores"][name] for r in all_results]
            aggregate[name] = sum(values) / len(values)

        composites = [r["composite"] for r in all_results]
        aggregate_composite = sum(composites) / len(composites)

        click.echo("")
        agg_str = ", ".join(f"{k}={v:.4f}" for k, v in aggregate.items())
        click.secho(
            f"Average ({len(all_results)} pairs): {agg_str} "
            f"(composite={aggregate_composite:.4f})",
            fg="green",
        )

    _dump_json(all_results)


# ------------------------------------------------------------------
# setup
# ------------------------------------------------------------------

_REQUIRED_PLUGINS = ["PythonScriptPlugin", "UEEyes"]


@main.command()
@click.argument("project_path", default=".", type=click.Path())
def setup(project_path: str) -> None:
    """Configure a UE project to work with ue-eyes.

    PROJECT_PATH is the root directory of the UE project (default: current dir).

    Runs an interactive 6-step flow:
      1. Detect the .uproject file
      2. Show symlink guidance for the UEEyes plugin
      3. Edit .uproject to enable required plugins
      4. Edit DefaultEditor.ini to enable remote execution
      5. Prompt to rebuild the project
      6. Verify the connection to UE
    """
    project = Path(project_path).resolve()

    # ------------------------------------------------------------------
    # Step 1: Detect .uproject
    # ------------------------------------------------------------------
    click.secho("Step 1/6: Detecting .uproject file...", fg="cyan")
    uproject = find_uproject(project)
    if uproject is None:
        click.secho(
            f"Error: No .uproject file found in {project}", fg="red", err=True
        )
        click.secho(
            "Make sure PROJECT_PATH points to the root of a UE project.", fg="yellow"
        )
        raise SystemExit(1)
    click.secho(f"  Found: {uproject.name}", fg="green")

    # ------------------------------------------------------------------
    # Step 2: Symlink guidance
    # ------------------------------------------------------------------
    click.secho("Step 2/6: UEEyes plugin symlink...", fg="cyan")
    symlink_cmd = get_symlink_command(project)
    click.echo(
        "  The UEEyes plugin must be accessible inside your project's Plugins/ folder.\n"
        "  Run the following command (as Administrator on Windows):\n"
    )
    click.secho(f"    {symlink_cmd}", fg="yellow")
    click.echo("")
    if not click.confirm("  Have you created the symlink?", default=False):
        click.secho(
            "  Skipping symlink step. You can run setup again after creating the symlink.",
            fg="yellow",
        )

    # ------------------------------------------------------------------
    # Step 3: Edit .uproject
    # ------------------------------------------------------------------
    click.secho("Step 3/6: Enabling plugins in .uproject...", fg="cyan")
    added = add_plugins_to_uproject(uproject, _REQUIRED_PLUGINS)
    if added:
        click.secho(f"  Added plugins: {', '.join(added)}", fg="green")
    else:
        click.secho("  All required plugins already present.", fg="green")

    # ------------------------------------------------------------------
    # Step 4: Edit DefaultEditor.ini
    # ------------------------------------------------------------------
    click.secho("Step 4/6: Configuring remote execution in DefaultEditor.ini...", fg="cyan")
    config_dir = project / "Config"
    config_dir.mkdir(parents=True, exist_ok=True)
    changed = configure_remote_exec(config_dir)
    if changed:
        click.secho("  Remote execution enabled in DefaultEditor.ini.", fg="green")
    else:
        click.secho("  Remote execution already configured.", fg="green")

    # ------------------------------------------------------------------
    # Step 5: Rebuild prompt
    # ------------------------------------------------------------------
    click.secho("Step 5/6: Rebuild the project...", fg="cyan")
    click.echo(
        "  Close the UE editor, then regenerate project files and recompile:\n"
        "  - Right-click the .uproject → 'Generate Visual Studio project files'\n"
        "  - Build the project in your IDE or via UnrealBuildTool\n"
    )
    click.confirm("  Press Enter when ready (or Ctrl-C to stop)", default=True)

    # ------------------------------------------------------------------
    # Step 6: Verify connection
    # ------------------------------------------------------------------
    click.secho("Step 6/6: Verifying UE connection...", fg="cyan")
    symlink_ok = verify_symlink(project)
    if symlink_ok:
        click.secho("  UEEyes plugin directory found.", fg="green")
    else:
        click.secho(
            "  Warning: UEEyes plugin not found at Plugins/UEEyes. "
            "Check the symlink and rebuild.",
            fg="yellow",
        )

    ue = None
    try:
        ue = UERemoteExecution()
        reachable = ue.ping()
    except Exception:
        reachable = False

    if reachable:
        click.secho("  UE is reachable — setup complete!", fg="green")
    else:
        click.secho(
            "  UE is not reachable yet. Open the UE editor with the plugin enabled,\n"
            "  then run: ue-eyes ping",
            fg="yellow",
        )


if __name__ == "__main__":
    main()
