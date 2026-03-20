"""
Frame capture orchestration.

Connects to UE via :class:`~ue_eyes.remote_exec.UERemoteExecution` and
sends capture/render scripts for execution inside the editor.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .remote_exec import UERemoteExecution

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
MANIFEST_FILENAME = "capture_manifest.json"

# Paths to the scripts that run inside UE
_SCRIPTS_DIR = Path(__file__).resolve().parent / "unreal_scripts"
_SNAP_SCRIPT = _SCRIPTS_DIR / "capture_frame.py"
_RENDER_SCRIPT = _SCRIPTS_DIR / "render_sequence.py"

# Plugin detection query executed inside UE
_DETECT_PLUGIN_CODE = (
    "import unreal; actors = unreal.GameplayStatics.get_all_actors_of_class("
    "unreal.EditorLevelLibrary.get_editor_world(), unreal.Actor); "
    "found = any(a.get_class().get_name() == 'UEEyesCaptureService' for a in actors); "
    "unreal.log(str(found))"
)

# Plugin capture commands executed inside UE
_PLUGIN_SNAP_VIEWPORT_CODE = (
    "import unreal; "
    "service = next(a for a in unreal.GameplayStatics.get_all_actors_of_class("
    "unreal.EditorLevelLibrary.get_editor_world(), unreal.Actor) "
    "if a.get_class().get_name() == 'UEEyesCaptureService'); "
    "service.CaptureFromViewport()"
)


def _plugin_snap_camera_code(camera: str) -> str:
    """Return UE Python code to capture from a named camera via the plugin."""
    return (
        "import unreal; "
        "service = next(a for a in unreal.GameplayStatics.get_all_actors_of_class("
        "unreal.EditorLevelLibrary.get_editor_world(), unreal.Actor) "
        "if a.get_class().get_name() == 'UEEyesCaptureService'); "
        f"service.CaptureFromPreset('{camera}')"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_manifest(output_dir: Path, manifest: dict) -> Path:
    """Write *manifest* as ``capture_manifest.json`` in *output_dir*."""
    manifest_path = output_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    logger.info("Manifest written to %s", manifest_path)
    return manifest_path


def _detect_plugin(ue: UERemoteExecution) -> bool:
    """Check if UEEyes plugin is installed by querying for CaptureService actors."""
    try:
        result = ue.execute(_DETECT_PLUGIN_CODE)
        return "True" in result.get("output", "")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def snap_frame(
    output_dir: str,
    camera: str | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    ue: UERemoteExecution | None = None,
) -> dict:
    """Capture a single frame from PIE viewport or named CameraActor.

    The captured PNG and a ``capture_manifest.json`` are written into
    *output_dir*.  Returns the capture manifest dict.

    Parameters
    ----------
    output_dir:
        Host filesystem path where the PNG and manifest are written.
    camera:
        Actor label of a CameraActor.  ``None`` means use the viewport.
    width:
        Capture width in pixels.
    height:
        Capture height in pixels.
    ue:
        An existing :class:`UERemoteExecution` connection.  If ``None`` a
        new connection is created (and closed before returning).
    """
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    owns_connection = ue is None
    if owns_connection:
        ue = UERemoteExecution()
        ue.connect()

    try:
        # Check for plugin-based capture path
        if _detect_plugin(ue):
            if camera is not None:
                result = ue.execute(_plugin_snap_camera_code(camera))
            else:
                result = ue.execute(_PLUGIN_SNAP_VIEWPORT_CODE)
        else:
            # Fallback: transient SceneCapture2D via capture_frame.py
            params: dict = {
                "output_dir": str(out),
                "width": width,
                "height": height,
            }
            if camera is not None:
                params["camera_name"] = camera
            result = ue.execute_file(str(_SNAP_SCRIPT), **params)
    finally:
        if owns_connection:
            ue.close()

    # Build manifest
    pngs = sorted(out.glob("*.png"))
    manifest: dict = {
        "type": "snap",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "resolution": [width, height],
        "camera": camera,
        "output_dir": str(out),
        "frames": [str(p) for p in pngs],
        "frame_count": len(pngs),
        "ue_output": result.get("output", ""),
    }

    _write_manifest(out, manifest)
    return manifest


def render_sequence(
    output_dir: str,
    sequence_path: str,
    map_path: str,
    frames: list[int] | None = None,
    frame_range: tuple[int, int] | None = None,
    frame_step: int = 1,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    ue: UERemoteExecution | None = None,
) -> dict:
    """Render frames from a Level Sequence via Movie Render Graph.

    *sequence_path* and *map_path* are UE asset paths
    (e.g. ``/Game/Sequences/MyShotSequence``).

    Returns the manifest dict written to *output_dir*.

    Parameters
    ----------
    output_dir:
        Host filesystem path where PNGs and manifest are written.
    sequence_path:
        UE asset path to the Level Sequence.
    map_path:
        UE asset path to the map/level.
    frames:
        Specific frame numbers to keep (the rest are discarded).
    frame_range:
        ``(start, end)`` inclusive frame range to render.
    frame_step:
        Step between rendered frames (default 1 = every frame).
    width:
        Render width in pixels.
    height:
        Render height in pixels.
    ue:
        An existing :class:`UERemoteExecution` connection.  If ``None`` a
        new connection is created (and closed before returning).
    """
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    params: dict = {
        "output_dir": str(out),
        "sequence_path": sequence_path,
        "map_path": map_path,
        "resolution": [width, height],
        "frame_step": frame_step,
    }
    if frames is not None:
        params["frames"] = frames
    if frame_range is not None:
        params["frame_range"] = list(frame_range)

    owns_connection = ue is None
    if owns_connection:
        ue = UERemoteExecution()
        ue.connect()

    try:
        result = ue.execute_file(str(_RENDER_SCRIPT), **params)
    finally:
        if owns_connection:
            ue.close()

    pngs = sorted(out.glob("*.png"))
    manifest: dict = {
        "type": "render",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sequence_path": sequence_path,
        "map_path": map_path,
        "resolution": [width, height],
        "frames_requested": frames,
        "frame_range": list(frame_range) if frame_range else None,
        "frame_step": frame_step,
        "output_dir": str(out),
        "frames": [str(p) for p in pngs],
        "frame_count": len(pngs),
        "ue_output": result.get("output", ""),
    }

    _write_manifest(out, manifest)
    return manifest
