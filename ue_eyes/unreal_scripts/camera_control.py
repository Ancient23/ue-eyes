"""
UE-side camera control -- runs INSIDE Unreal Engine 5.7 Python environment.

This file is executed via ``UERemoteExecution.execute_file()`` which injects
a ``_ue_eyes_params`` dict before this code runs.

Injected params via _ue_eyes_params:
    action (str)                        -- "spawn", "move", "destroy", "apply_tracking"
    name (str)                          -- camera actor label
    location (list[float], optional)    -- [x, y, z]
    rotation (list[float], optional)    -- [pitch, yaw, roll]
    tracking_mode (str, optional)       -- "fixed", "look_at", "follow"
    target_actor (str, optional)        -- actor label to track
    target_bone (str, optional)         -- bone name on target skeletal mesh
    offset (list[float], optional)      -- [x, y, z] offset from target

DO NOT import this file on the host -- ``import unreal`` is only available
inside the UE editor Python environment.
"""

import json
import math

import unreal  # type: ignore  # noqa: F401  -- UE-only module

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_LOCATION = [0.0, 0.0, 200.0]
DEFAULT_ROTATION = [0.0, 0.0, 0.0]
DEFAULT_OFFSET = [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_actor(label):
    """Find an actor in the current level by its display label.

    Args:
        label: The actor label string to search for.

    Returns:
        The first matching actor, or ``None`` if no actor has that label.
    """
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    for actor in actors:
        if actor.get_actor_label() == label:
            return actor
    return None


def _make_vector(values):
    """Create an ``unreal.Vector`` from a 3-element list of floats."""
    return unreal.Vector(values[0], values[1], values[2])


def _make_rotator(values):
    """Create an ``unreal.Rotator`` from ``[pitch, yaw, roll]``."""
    return unreal.Rotator(values[0], values[1], values[2])


def _vector_to_list(vec):
    """Convert an ``unreal.Vector`` to a plain Python list."""
    return [vec.x, vec.y, vec.z]


def _rotator_to_list(rot):
    """Convert an ``unreal.Rotator`` to ``[pitch, yaw, roll]``."""
    return [rot.pitch, rot.yaw, rot.roll]


def _get_target_position(params):
    """Resolve the world position of a tracking target.

    If ``target_bone`` is specified and the target actor has a
    ``SkeletalMeshComponent``, the bone's world-space position is returned.
    Otherwise, the actor's root location is used.

    Args:
        params: The injected params dict.

    Returns:
        An ``unreal.Vector`` with the target world position.

    Raises:
        RuntimeError: If the target actor is not found.
    """
    target_name = params["target_actor"]
    target = _find_actor(target_name)
    if target is None:
        raise RuntimeError(f"Target actor '{target_name}' not found")

    bone_name = params.get("target_bone")
    if bone_name:
        skel_comp = target.get_component_by_class(unreal.SkeletalMeshComponent)
        if skel_comp is not None:
            return skel_comp.get_bone_location(bone_name, unreal.BoneSpaceName.WORLD_SPACE)

    return target.get_actor_location()


def _compute_look_at_rotation(from_location, to_location):
    """Compute a rotator that points from *from_location* toward *to_location*.

    Args:
        from_location: Camera world position (``unreal.Vector``).
        to_location: Target world position (``unreal.Vector``).

    Returns:
        An ``unreal.Rotator`` facing the target.
    """
    dx = to_location.x - from_location.x
    dy = to_location.y - from_location.y
    dz = to_location.z - from_location.z

    dist_xy = math.sqrt(dx * dx + dy * dy)
    pitch = math.degrees(math.atan2(dz, dist_xy))
    yaw = math.degrees(math.atan2(dy, dx))

    return unreal.Rotator(pitch, yaw, 0.0)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _spawn_camera(params):
    """Spawn a new ``CameraActor`` at the given location/rotation.

    Returns:
        A dict with the new camera's label and transform.
    """
    name = params["name"]
    location = _make_vector(params.get("location", DEFAULT_LOCATION))
    rotation = _make_rotator(params.get("rotation", DEFAULT_ROTATION))

    camera = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.CameraActor,
        location,
        rotation,
    )
    camera.set_actor_label(name)

    unreal.log(f"[ue-eyes] Spawned camera '{name}'")
    return {
        "action": "spawn",
        "name": name,
        "location": _vector_to_list(location),
        "rotation": _rotator_to_list(rotation),
    }


def _move_camera(params):
    """Move an existing camera to a new location and/or rotation.

    Returns:
        A dict with the updated transform.
    """
    name = params["name"]
    camera = _find_actor(name)
    if camera is None:
        error_msg = f"Camera '{name}' not found"
        unreal.log_error(f"[ue-eyes] {error_msg}")
        return {"error": error_msg}

    if "location" in params:
        camera.set_actor_location(_make_vector(params["location"]), False, False)
    if "rotation" in params:
        camera.set_actor_rotation(_make_rotator(params["rotation"]), False)

    final_loc = camera.get_actor_location()
    final_rot = camera.get_actor_rotation()

    unreal.log(f"[ue-eyes] Moved camera '{name}'")
    return {
        "action": "move",
        "name": name,
        "location": _vector_to_list(final_loc),
        "rotation": _rotator_to_list(final_rot),
    }


def _destroy_camera(params):
    """Destroy a camera actor by label.

    Returns:
        A dict confirming destruction.
    """
    name = params["name"]
    actor = _find_actor(name)
    if actor is None:
        error_msg = f"Actor '{name}' not found"
        unreal.log_error(f"[ue-eyes] {error_msg}")
        return {"error": error_msg}

    actor.destroy_actor()
    unreal.log(f"[ue-eyes] Destroyed actor '{name}'")
    return {
        "action": "destroy",
        "name": name,
    }


def _apply_tracking(params):
    """Apply a tracking mode to an existing camera.

    Supported modes:
        - ``fixed``    -- no-op, camera stays at its current transform.
        - ``look_at``  -- camera stays in place, rotation points at target.
        - ``follow``   -- camera moves to target position plus offset,
                          rotation points at target.

    Returns:
        A dict with the resulting camera transform.
    """
    name = params["name"]
    tracking_mode = params.get("tracking_mode", "fixed")

    camera = _find_actor(name)
    if camera is None:
        error_msg = f"Camera '{name}' not found"
        unreal.log_error(f"[ue-eyes] {error_msg}")
        return {"error": error_msg}

    if tracking_mode == "fixed":
        # Nothing to change
        pass

    elif tracking_mode == "look_at":
        target_pos = _get_target_position(params)
        cam_pos = camera.get_actor_location()
        look_rot = _compute_look_at_rotation(cam_pos, target_pos)
        camera.set_actor_rotation(look_rot, False)

    elif tracking_mode == "follow":
        offset = _make_vector(params.get("offset", DEFAULT_OFFSET))
        target_pos = _get_target_position(params)
        cam_pos = unreal.Vector(
            target_pos.x + offset.x,
            target_pos.y + offset.y,
            target_pos.z + offset.z,
        )
        camera.set_actor_location(cam_pos, False, False)
        look_rot = _compute_look_at_rotation(cam_pos, target_pos)
        camera.set_actor_rotation(look_rot, False)

    else:
        error_msg = f"Unknown tracking mode '{tracking_mode}'"
        unreal.log_error(f"[ue-eyes] {error_msg}")
        return {"error": error_msg}

    final_loc = camera.get_actor_location()
    final_rot = camera.get_actor_rotation()

    unreal.log(f"[ue-eyes] Applied tracking '{tracking_mode}' to '{name}'")
    return {
        "action": "apply_tracking",
        "name": name,
        "tracking_mode": tracking_mode,
        "location": _vector_to_list(final_loc),
        "rotation": _rotator_to_list(final_rot),
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ACTION_MAP = {
    "spawn": _spawn_camera,
    "move": _move_camera,
    "destroy": _destroy_camera,
    "apply_tracking": _apply_tracking,
}


def _camera_control(params):
    """Dispatch to the appropriate camera action.

    Args:
        params: Dict injected as ``_ue_eyes_params`` by the remote executor.
            Must contain an ``action`` key.

    Returns:
        A dict with action-specific result data, or an error dict.
    """
    action = params.get("action")
    if action is None:
        error_msg = "Missing required param 'action'"
        unreal.log_error(f"[ue-eyes] {error_msg}")
        return {"error": error_msg}

    handler = _ACTION_MAP.get(action)
    if handler is None:
        error_msg = f"Unknown action '{action}'. Valid: {list(_ACTION_MAP.keys())}"
        unreal.log_error(f"[ue-eyes] {error_msg}")
        return {"error": error_msg}

    try:
        result = handler(params)
    except Exception as exc:
        error_msg = f"Action '{action}' failed: {exc}"
        unreal.log_error(f"[ue-eyes] {error_msg}")
        return {"error": error_msg}

    unreal.log(json.dumps(result))
    return result


# ------------------------------------------------------------------
# Entry point -- _ue_eyes_params is injected by remote_exec
# ------------------------------------------------------------------
_result = _camera_control(_ue_eyes_params)  # noqa: F821
