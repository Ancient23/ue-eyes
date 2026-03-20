"""Parameter space loading, diffing, and validation for ue-eyes experiments.

Parameters are stored as JSON files with a version field and a ``parameters``
dict.  Each parameter entry declares its type and optional constraints (min/max
for numerics, options for enums).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

PARAMS_VERSION: int = 1

_VALID_TYPES: set[str] = {"float", "int", "bool", "enum", "str"}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_params(path: Path) -> dict:
    """Load a parameter file.  Validates that the *version* field exists."""
    with open(path) as fh:
        data: dict = json.load(fh)
    if "version" not in data:
        raise ValueError(f"Parameter file {path} is missing required 'version' field")
    return data


def save_params(params: dict, path: Path) -> None:
    """Save a parameter dict as formatted JSON."""
    with open(path, "w") as fh:
        json.dump(params, fh, indent=2)
        fh.write("\n")


def diff_params(before: dict, after: dict) -> dict:
    """Return changed parameters as ``{name: {"old": val, "new": val}}``.

    Recursively compares values inside the ``"parameters"`` dict.
    """
    before_params = before.get("parameters", {})
    after_params = after.get("parameters", {})
    all_keys = set(before_params.keys()) | set(after_params.keys())
    changes: dict[str, dict[str, Any]] = {}
    for key in sorted(all_keys):
        old_entry = before_params.get(key, {})
        new_entry = after_params.get(key, {})
        old_val = old_entry.get("value")
        new_val = new_entry.get("value")
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}
    return changes


def validate_param_change(params: dict, name: str, value: Any) -> None:
    """Validate setting *name* to *value* against the parameter definition.

    Raises :class:`ValueError` for type mismatches, out-of-range values, or
    invalid enum options.
    """
    parameters = params.get("parameters", {})
    if name not in parameters:
        raise KeyError(f"Unknown parameter: {name!r}")
    defn = parameters[name]
    ptype = defn.get("type", "str")

    if ptype == "float":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(
                f"Parameter {name!r} expects a numeric value, got {type(value).__name__}"
            )
        _check_range(name, float(value), defn)

    elif ptype == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"Parameter {name!r} expects an integer, got {type(value).__name__}"
            )
        _check_range(name, value, defn)

    elif ptype == "bool":
        if not isinstance(value, bool):
            raise ValueError(
                f"Parameter {name!r} expects a bool, got {type(value).__name__}"
            )

    elif ptype == "enum":
        options = defn.get("options", [])
        if value not in options:
            raise ValueError(
                f"Parameter {name!r} value {value!r} not in options: {options}"
            )

    elif ptype == "str":
        if not isinstance(value, str):
            raise ValueError(
                f"Parameter {name!r} expects a string, got {type(value).__name__}"
            )


def get_param_value(params: dict, name: str) -> Any:
    """Return the current value of parameter *name*."""
    parameters = params.get("parameters", {})
    if name not in parameters:
        raise KeyError(f"Unknown parameter: {name!r}")
    return parameters[name]["value"]


def set_param_value(params: dict, name: str, value: Any) -> dict:
    """Set parameter *name* to *value* (validates first).

    Returns a deep copy of *params* with the updated value — the original dict
    is not mutated.
    """
    validate_param_change(params, name, value)
    result = copy.deepcopy(params)
    result["parameters"][name]["value"] = value
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_range(name: str, value: float | int, defn: dict) -> None:
    """Raise :class:`ValueError` if *value* is outside [min, max]."""
    lo = defn.get("min")
    hi = defn.get("max")
    if lo is not None and value < lo:
        raise ValueError(
            f"Parameter {name!r} value {value} is below minimum {lo}"
        )
    if hi is not None and value > hi:
        raise ValueError(
            f"Parameter {name!r} value {value} is above maximum {hi}"
        )
