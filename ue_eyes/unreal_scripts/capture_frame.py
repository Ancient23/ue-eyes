"""
UE-side capture script -- runs INSIDE Unreal Engine 5.7 Python environment.

This file is executed via ``UERemoteExecution.execute_file()`` which injects
a ``_ue_eyes_params`` dict before this code runs.

Expected params:
    output_dir  (str)            -- host filesystem path for PNG output
    width       (int)            -- capture width in pixels  (default 1920)
    height      (int)            -- capture height in pixels (default 1080)
    camera_name (str, optional)  -- label of a CameraActor to use; if omitted
                                    the current viewport camera is used

DO NOT import this file on the host -- ``import unreal`` is only available
inside the UE editor Python environment.
"""

import json
import os
from datetime import datetime

import unreal  # type: ignore  # noqa: F401  -- UE-only module

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
PIXEL_FORMAT = unreal.EPixelFormat.PF_B8G8R8A8
TARGET_GAMMA = 2.2
MANIFEST_FILENAME = "capture_manifest.json"
SNAP_PREFIX = "ue_eyes_snap"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_editor_world():
    """Return the current editor world."""
    return unreal.EditorLevelLibrary.get_editor_world()


def _find_camera_actor(world, camera_name):
    """Find a CameraActor by its actor label.

    Args:
        world: The editor world (unused but kept for API symmetry).
        camera_name: Display label of the CameraActor to find.

    Returns:
        The matching actor, or ``None`` if not found.
    """
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    for actor in actors:
        if actor.get_actor_label() == camera_name:
            return actor
    return None


def _get_viewport_transform():
    """Return ``(location, rotation)`` of the active viewport camera."""
    loc, rot = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
    return loc, rot


# ---------------------------------------------------------------------------
# Main capture logic
# ---------------------------------------------------------------------------

def _capture_frame(params):
    """Capture a single frame from the editor and write it as a PNG.

    The function spawns a transient ``SceneCapture2D`` actor, renders into an
    off-screen render target, exports the result via
    ``KismetRenderingLibrary``, writes a JSON manifest alongside the image,
    and cleans up the transient actor.

    Args:
        params: Dict injected as ``_ue_eyes_params`` by the remote executor.

    Returns:
        A dict describing the capture (the manifest).
    """
    output_dir = params["output_dir"]
    width = params.get("width", DEFAULT_WIDTH)
    height = params.get("height", DEFAULT_HEIGHT)
    camera_name = params.get("camera_name")

    os.makedirs(output_dir, exist_ok=True)

    world = _get_editor_world()

    # Determine camera transform ----------------------------------------
    if camera_name:
        cam_actor = _find_camera_actor(world, camera_name)
        if cam_actor is None:
            error_msg = f"Camera actor '{camera_name}' not found in level"
            unreal.log_error(f"[ue-eyes] {error_msg}")
            return {"error": error_msg}
        location = cam_actor.get_actor_location()
        rotation = cam_actor.get_actor_rotation()
    else:
        location, rotation = _get_viewport_transform()

    # Spawn a transient SceneCapture2D actor ----------------------------
    capture_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SceneCapture2D,
        location,
        rotation,
    )
    capture_component = capture_actor.get_capture_component2d()

    # Create and configure the render target ----------------------------
    render_target = unreal.RenderTarget2D()
    render_target.init_custom_format(width, height, PIXEL_FORMAT, False)
    render_target.target_gamma = TARGET_GAMMA

    capture_component.texture_target = render_target
    capture_component.capture_source = unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR

    # Trigger the capture -----------------------------------------------
    capture_component.capture_scene()

    # Export to PNG -----------------------------------------------------
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{SNAP_PREFIX}_{timestamp}.png"
    filepath = os.path.join(output_dir, filename)

    unreal.KismetRenderingLibrary.export_render_target(
        world,
        render_target,
        output_dir,
        filename,
    )

    # Write manifest data -----------------------------------------------
    manifest = {
        "type": "snap",
        "camera": camera_name or "viewport",
        "resolution": [width, height],
        "file": filepath,
        "timestamp": timestamp,
    }
    manifest_path = os.path.join(output_dir, MANIFEST_FILENAME)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Clean up the transient actor --------------------------------------
    capture_actor.destroy_actor()

    unreal.log(f"[ue-eyes] Captured frame: {filepath}")
    return manifest


# ------------------------------------------------------------------
# Entry point -- _ue_eyes_params is injected by remote_exec
# ------------------------------------------------------------------
_result = _capture_frame(_ue_eyes_params)  # noqa: F821
