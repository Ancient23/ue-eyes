"""
UE-side render script -- runs INSIDE Unreal Engine 5.7 Python environment.

This file is executed via ``UERemoteExecution.execute_file()`` which injects
a ``_ue_eyes_params`` dict before this code runs.

Expected params:
    sequence_path (str)                 -- UE asset path to the Level Sequence
    map_path      (str)                 -- UE asset path to the map/level
    output_dir    (str)                 -- host filesystem path for PNG output
    resolution    (list[int, int])      -- [width, height]  (default [1920, 1080])
    frame_step    (int, optional)       -- step between frames (default 1)
    frames        (list[int], optional) -- specific frame numbers to keep
    frame_range   (list[int, int], optional) -- [start, end] inclusive frame range

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
DEFAULT_RESOLUTION = [1920, 1080]
DEFAULT_FRAME_STEP = 1
TICK_INTERVAL_SECONDS = 0.1
MANIFEST_FILENAME = "capture_manifest.json"
FILENAME_FORMAT = "{sequence_name}.{frame_number}"


# ---------------------------------------------------------------------------
# Main render logic
# ---------------------------------------------------------------------------

def _render_sequence(params):
    """Render a Level Sequence to PNG frames via Movie Render Graph.

    The function sets up a Movie Pipeline job, configures output settings and
    PNG format, starts a PIE executor, blocks until rendering completes, and
    writes a JSON manifest listing every output file.

    Args:
        params: Dict injected as ``_ue_eyes_params`` by the remote executor.

    Returns:
        A dict describing the render results (the manifest).
    """
    sequence_path = params["sequence_path"]
    map_path = params["map_path"]
    output_dir = params["output_dir"]
    resolution = params.get("resolution", DEFAULT_RESOLUTION)
    frame_step = params.get("frame_step", DEFAULT_FRAME_STEP)
    specific_frames = params.get("frames")
    frame_range = params.get("frame_range")

    width, height = resolution
    os.makedirs(output_dir, exist_ok=True)

    # Get the Movie Pipeline subsystem ----------------------------------
    subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    queue = subsystem.get_queue()

    # Clear any existing jobs -------------------------------------------
    while queue.get_jobs():
        queue.delete_job(queue.get_jobs()[0])

    # Allocate a new job ------------------------------------------------
    job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
    job.sequence = unreal.SoftObjectPath(sequence_path)
    job.map = unreal.SoftObjectPath(map_path)

    # Get or create the primary configuration ---------------------------
    config = job.get_configuration()

    # -- Output setting: resolution and directory -----------------------
    output_setting = config.find_or_add_setting_by_class(
        unreal.MoviePipelineOutputSetting
    )
    output_setting.output_resolution = unreal.IntPoint(width, height)
    output_setting.output_directory = unreal.DirectoryPath(output_dir)
    output_setting.file_name_format = FILENAME_FORMAT
    output_setting.override_existing_output = True

    # -- Output format: PNG ---------------------------------------------
    config.find_or_add_setting_by_class(
        unreal.MoviePipelineImageSequenceOutput_PNG
    )

    # -- Frame range / playback settings --------------------------------
    if frame_range is not None:
        playback_setting = config.find_or_add_setting_by_class(
            unreal.MoviePipelineOutputSetting
        )
        playback_setting.use_custom_playback_range = True
        playback_setting.custom_start_frame = frame_range[0]
        playback_setting.custom_end_frame = frame_range[1]

    if frame_step > 1:
        output_setting.output_frame_step = frame_step

    # -- Create a PIE executor and start rendering ----------------------
    executor = unreal.MoviePipelinePIEExecutor()

    completion_data = {"done": False, "success": False}

    def _on_complete(pipeline_executor, is_error):
        completion_data["done"] = True
        completion_data["success"] = not is_error
        unreal.log("[ue-eyes] Render complete, error=" + str(is_error))

    executor.on_executor_finished_delegate.add_callable(_on_complete)

    # Start rendering ---------------------------------------------------
    subsystem.render_queue_with_executor(executor)

    # Block until render completes (tick the engine) --------------------
    while not completion_data["done"]:
        unreal.EditorLevelLibrary.editor_tick(TICK_INTERVAL_SECONDS)

    # Scan for output PNGs ----------------------------------------------
    rendered_files = sorted(
        f for f in os.listdir(output_dir)
        if f.lower().endswith(".png")
    )

    # If specific frames requested, filter ------------------------------
    if specific_frames is not None:
        frame_set = set(specific_frames)
        kept = []
        for fname in rendered_files:
            base = os.path.splitext(fname)[0]
            parts = base.rsplit(".", 1)
            if len(parts) == 2:
                try:
                    fnum = int(parts[1])
                    if fnum in frame_set:
                        kept.append(fname)
                        continue
                except ValueError:
                    pass
            # File doesn't match the frame-number pattern -- keep it
            kept.append(fname)

        # Remove non-matching files from disk
        for fname in rendered_files:
            if fname not in kept:
                try:
                    os.remove(os.path.join(output_dir, fname))
                except OSError:
                    pass
        rendered_files = kept

    # Write manifest ----------------------------------------------------
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    manifest = {
        "type": "render",
        "sequence_path": sequence_path,
        "map_path": map_path,
        "resolution": [width, height],
        "frame_step": frame_step,
        "frames_requested": specific_frames,
        "frame_range": frame_range,
        "output_dir": output_dir,
        "files": [os.path.join(output_dir, f) for f in rendered_files],
        "frame_count": len(rendered_files),
        "timestamp": timestamp,
        "success": completion_data["success"],
    }
    manifest_path = os.path.join(output_dir, MANIFEST_FILENAME)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    unreal.log(f"[ue-eyes] Rendered {len(rendered_files)} frame(s) to {output_dir}")
    return manifest


# ------------------------------------------------------------------
# Entry point -- _ue_eyes_params is injected by remote_exec
# ------------------------------------------------------------------
_result = _render_sequence(_ue_eyes_params)  # noqa: F821
