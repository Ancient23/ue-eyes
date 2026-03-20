"""
UE-side scene info -- runs INSIDE Unreal Engine 5.7 Python environment.

This file is executed via ``UERemoteExecution.execute_file()`` which injects
a ``_ue_eyes_params`` dict before this code runs.

Injected params via _ue_eyes_params:
    action (str)                        -- action to perform (see below)
    class_name (str, optional)          -- for find_actors: UE class name
    tag (str, optional)                 -- for find_actors: actor tag filter
    actor_name (str, optional)          -- for get_bones, get_actor_transform,
                                           get_bone_transform, get_property
    bone_name (str, optional)           -- for get_bone_transform
    property_name (str, optional)       -- for get_property

Supported actions:
    discover_cameras    -- find all CameraActor instances, return names + transforms
    find_actors         -- filter actors by class_name and/or tag
    get_bones           -- list bone names from a SkeletalMeshComponent
    get_actor_transform -- get an actor's world location + rotation
    get_bone_transform  -- get a bone's world transform on a skeletal mesh actor
    get_property        -- read an actor property via get_editor_property()

All results are returned as JSON via ``unreal.log(json.dumps(...))``.

DO NOT import this file on the host -- ``import unreal`` is only available
inside the UE editor Python environment.
"""

import json

import unreal  # type: ignore  # noqa: F401  -- UE-only module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vector_to_list(vec):
    """Convert an ``unreal.Vector`` to ``[x, y, z]``."""
    return [vec.x, vec.y, vec.z]


def _rotator_to_list(rot):
    """Convert an ``unreal.Rotator`` to ``[pitch, yaw, roll]``."""
    return [rot.pitch, rot.yaw, rot.roll]


def _find_actor_by_label(label):
    """Find an actor in the current level by its display label.

    Args:
        label: The actor label to search for.

    Returns:
        The first matching actor, or ``None``.
    """
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    for actor in actors:
        if actor.get_actor_label() == label:
            return actor
    return None


def _get_skeletal_mesh_component(actor):
    """Return the first ``SkeletalMeshComponent`` on *actor*, or ``None``."""
    return actor.get_component_by_class(unreal.SkeletalMeshComponent)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _discover_cameras(params):
    """Find all CameraActor instances in the level.

    Returns:
        A dict with ``cameras`` -- a list of dicts containing each camera's
        ``name``, ``location``, and ``rotation``.
    """
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    cameras = []
    for actor in actors:
        if actor.get_class().get_name() == "CameraActor":
            loc = actor.get_actor_location()
            rot = actor.get_actor_rotation()
            cameras.append({
                "name": actor.get_actor_label(),
                "location": _vector_to_list(loc),
                "rotation": _rotator_to_list(rot),
            })

    return {
        "action": "discover_cameras",
        "count": len(cameras),
        "cameras": cameras,
    }


def _find_actors(params):
    """Find actors filtered by class name and/or tag.

    Args:
        params: Must include at least one of ``class_name`` or ``tag``.

    Returns:
        A dict with ``actors`` -- a list of matching actor names and classes.
    """
    class_name = params.get("class_name")
    tag = params.get("tag")

    all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
    results = []

    for actor in all_actors:
        actor_class = actor.get_class().get_name()

        # Filter by class name if specified
        if class_name and actor_class != class_name:
            continue

        # Filter by tag if specified
        if tag:
            actor_tags = actor.tags
            tag_found = False
            for actor_tag in actor_tags:
                if str(actor_tag) == tag:
                    tag_found = True
                    break
            if not tag_found:
                continue

        loc = actor.get_actor_location()
        rot = actor.get_actor_rotation()
        results.append({
            "name": actor.get_actor_label(),
            "class": actor_class,
            "location": _vector_to_list(loc),
            "rotation": _rotator_to_list(rot),
        })

    return {
        "action": "find_actors",
        "class_name": class_name,
        "tag": tag,
        "count": len(results),
        "actors": results,
    }


def _get_bones(params):
    """List all bone names from a SkeletalMeshComponent on the named actor.

    Args:
        params: Must include ``actor_name``.

    Returns:
        A dict with ``bones`` -- a list of bone name strings.
    """
    actor_name = params["actor_name"]
    actor = _find_actor_by_label(actor_name)
    if actor is None:
        return {"error": f"Actor '{actor_name}' not found"}

    skel_comp = _get_skeletal_mesh_component(actor)
    if skel_comp is None:
        return {"error": f"Actor '{actor_name}' has no SkeletalMeshComponent"}

    bone_names = []
    num_bones = skel_comp.get_num_bones()
    for i in range(num_bones):
        bone_names.append(skel_comp.get_bone_name(i))

    return {
        "action": "get_bones",
        "actor_name": actor_name,
        "count": len(bone_names),
        "bones": [str(name) for name in bone_names],
    }


def _get_actor_transform(params):
    """Get the world transform of a named actor.

    Args:
        params: Must include ``actor_name``.

    Returns:
        A dict with ``location`` and ``rotation``.
    """
    actor_name = params["actor_name"]
    actor = _find_actor_by_label(actor_name)
    if actor is None:
        return {"error": f"Actor '{actor_name}' not found"}

    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()

    return {
        "action": "get_actor_transform",
        "actor_name": actor_name,
        "location": _vector_to_list(loc),
        "rotation": _rotator_to_list(rot),
        "scale": _vector_to_list(scale),
    }


def _get_bone_transform(params):
    """Get the world transform of a specific bone on a skeletal mesh actor.

    Args:
        params: Must include ``actor_name`` and ``bone_name``.

    Returns:
        A dict with the bone's world ``location`` and ``rotation``.
    """
    actor_name = params["actor_name"]
    bone_name = params["bone_name"]

    actor = _find_actor_by_label(actor_name)
    if actor is None:
        return {"error": f"Actor '{actor_name}' not found"}

    skel_comp = _get_skeletal_mesh_component(actor)
    if skel_comp is None:
        return {"error": f"Actor '{actor_name}' has no SkeletalMeshComponent"}

    # Verify bone exists
    bone_index = skel_comp.get_bone_index(bone_name)
    if bone_index < 0:
        return {"error": f"Bone '{bone_name}' not found on '{actor_name}'"}

    bone_transform = skel_comp.get_bone_transform(bone_name, unreal.BoneSpaceName.WORLD_SPACE)
    bone_loc = bone_transform.translation
    bone_rot = bone_transform.rotation.rotator()

    return {
        "action": "get_bone_transform",
        "actor_name": actor_name,
        "bone_name": bone_name,
        "location": _vector_to_list(bone_loc),
        "rotation": _rotator_to_list(bone_rot),
    }


def _get_property(params):
    """Read an actor property via ``get_editor_property()``.

    Args:
        params: Must include ``actor_name`` and ``property_name``.

    Returns:
        A dict with the property ``value`` (converted to a JSON-safe type).
    """
    actor_name = params["actor_name"]
    property_name = params["property_name"]

    actor = _find_actor_by_label(actor_name)
    if actor is None:
        return {"error": f"Actor '{actor_name}' not found"}

    try:
        value = actor.get_editor_property(property_name)
    except Exception as exc:
        return {"error": f"Cannot read property '{property_name}' on '{actor_name}': {exc}"}

    # Convert UE types to JSON-serializable values
    serialized_value = _serialize_value(value)

    return {
        "action": "get_property",
        "actor_name": actor_name,
        "property_name": property_name,
        "value": serialized_value,
    }


def _serialize_value(value):
    """Best-effort conversion of a UE property value to a JSON-safe type.

    Handles common UE types (Vector, Rotator, Color, bool, int, float, str,
    Name, Text) and falls back to ``str()`` for unknown types.
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value

    type_name = type(value).__name__

    if type_name == "Vector":
        return {"x": value.x, "y": value.y, "z": value.z}
    if type_name == "Rotator":
        return {"pitch": value.pitch, "yaw": value.yaw, "roll": value.roll}
    if type_name == "LinearColor":
        return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
    if type_name == "Color":
        return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
    if type_name == "Transform":
        return {
            "location": _vector_to_list(value.translation),
            "rotation": _rotator_to_list(value.rotation.rotator()),
            "scale": _vector_to_list(value.scale3d),
        }
    if type_name in ("Name", "Text"):
        return str(value)

    # Arrays / lists
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]

    # Fallback
    return str(value)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ACTION_MAP = {
    "discover_cameras": _discover_cameras,
    "find_actors": _find_actors,
    "get_bones": _get_bones,
    "get_actor_transform": _get_actor_transform,
    "get_bone_transform": _get_bone_transform,
    "get_property": _get_property,
}


def _scene_info(params):
    """Dispatch to the appropriate scene info action.

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
        valid_actions = list(_ACTION_MAP.keys())
        error_msg = f"Unknown action '{action}'. Valid: {valid_actions}"
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
_result = _scene_info(_ue_eyes_params)  # noqa: F821
