"""Tests for ue_eyes.experiment — parameter loading, diffing, and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ue_eyes.experiment import (
    diff_params,
    get_param_value,
    load_params,
    save_params,
    set_param_value,
    validate_param_change,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_params() -> dict:
    """Return a representative parameter dict for testing."""
    return {
        "version": 1,
        "parameters": {
            "light_intensity": {"value": 5000, "type": "float", "min": 0, "max": 50000},
            "shadow_bias": {"value": 0.5, "type": "float", "min": 0, "max": 2.0},
            "enable_ao": {"value": True, "type": "bool"},
            "post_process_preset": {
                "value": "cinematic",
                "type": "enum",
                "options": ["default", "cinematic", "filmic"],
            },
        },
    }


def _write_params(path: Path, data: dict) -> Path:
    """Write *data* as JSON to *path* and return the path."""
    path.write_text(json.dumps(data, indent=2))
    return path


# ------------------------------------------------------------------
# 1. test_load_params
# ------------------------------------------------------------------

def test_load_params(tmp_path: Path) -> None:
    """Reads JSON, returns dict with version and parameters."""
    params = _sample_params()
    fpath = _write_params(tmp_path / "params.json", params)
    loaded = load_params(fpath)
    assert loaded["version"] == 1
    assert "light_intensity" in loaded["parameters"]
    assert loaded["parameters"]["light_intensity"]["value"] == 5000


# ------------------------------------------------------------------
# 2. test_load_params_missing_version
# ------------------------------------------------------------------

def test_load_params_missing_version(tmp_path: Path) -> None:
    """Raises ValueError when version field is missing."""
    data = {"parameters": {"x": {"value": 1, "type": "int"}}}
    fpath = _write_params(tmp_path / "bad.json", data)
    with pytest.raises(ValueError, match="missing required 'version' field"):
        load_params(fpath)


# ------------------------------------------------------------------
# 3. test_load_params_file_not_found
# ------------------------------------------------------------------

def test_load_params_file_not_found(tmp_path: Path) -> None:
    """Raises FileNotFoundError for a nonexistent path."""
    with pytest.raises(FileNotFoundError):
        load_params(tmp_path / "nonexistent.json")


# ------------------------------------------------------------------
# 4. test_save_params
# ------------------------------------------------------------------

def test_save_params(tmp_path: Path) -> None:
    """Writes JSON; re-read matches original."""
    params = _sample_params()
    fpath = tmp_path / "out.json"
    save_params(params, fpath)
    raw = json.loads(fpath.read_text())
    assert raw["version"] == params["version"]
    assert raw["parameters"] == params["parameters"]


# ------------------------------------------------------------------
# 5. test_save_load_roundtrip
# ------------------------------------------------------------------

def test_save_load_roundtrip(tmp_path: Path) -> None:
    """save then load gives identical dict."""
    params = _sample_params()
    fpath = tmp_path / "roundtrip.json"
    save_params(params, fpath)
    loaded = load_params(fpath)
    assert loaded == params


# ------------------------------------------------------------------
# 6. test_diff_params_no_changes
# ------------------------------------------------------------------

def test_diff_params_no_changes() -> None:
    """Returns empty dict when nothing changed."""
    params = _sample_params()
    assert diff_params(params, params) == {}


# ------------------------------------------------------------------
# 7. test_diff_params_value_changed
# ------------------------------------------------------------------

def test_diff_params_value_changed() -> None:
    """Detects a single changed parameter value."""
    before = _sample_params()
    after = _sample_params()
    after["parameters"]["shadow_bias"]["value"] = 1.0
    result = diff_params(before, after)
    assert "shadow_bias" in result
    assert result["shadow_bias"] == {"old": 0.5, "new": 1.0}


# ------------------------------------------------------------------
# 8. test_diff_params_multiple_changes
# ------------------------------------------------------------------

def test_diff_params_multiple_changes() -> None:
    """Detects all changed parameters."""
    before = _sample_params()
    after = _sample_params()
    after["parameters"]["light_intensity"]["value"] = 9999
    after["parameters"]["enable_ao"]["value"] = False
    result = diff_params(before, after)
    assert len(result) == 2
    assert "light_intensity" in result
    assert "enable_ao" in result
    assert result["light_intensity"] == {"old": 5000, "new": 9999}
    assert result["enable_ao"] == {"old": True, "new": False}


# ------------------------------------------------------------------
# 9. test_validate_float_in_range
# ------------------------------------------------------------------

def test_validate_float_in_range() -> None:
    """No error for a float value within [min, max]."""
    params = _sample_params()
    validate_param_change(params, "light_intensity", 10000)
    validate_param_change(params, "light_intensity", 10000.5)


# ------------------------------------------------------------------
# 10. test_validate_float_out_of_range
# ------------------------------------------------------------------

def test_validate_float_out_of_range() -> None:
    """Raises ValueError for a float value outside [min, max]."""
    params = _sample_params()
    with pytest.raises(ValueError, match="above maximum"):
        validate_param_change(params, "light_intensity", 99999)
    with pytest.raises(ValueError, match="below minimum"):
        validate_param_change(params, "shadow_bias", -0.1)


# ------------------------------------------------------------------
# 11. test_validate_float_type_mismatch
# ------------------------------------------------------------------

def test_validate_float_type_mismatch() -> None:
    """String value for a float parameter raises ValueError."""
    params = _sample_params()
    with pytest.raises(ValueError, match="expects a numeric value"):
        validate_param_change(params, "light_intensity", "bright")


# ------------------------------------------------------------------
# 12. test_validate_bool
# ------------------------------------------------------------------

def test_validate_bool() -> None:
    """True/False accepted for bool parameters."""
    params = _sample_params()
    validate_param_change(params, "enable_ao", True)
    validate_param_change(params, "enable_ao", False)


# ------------------------------------------------------------------
# 13. test_validate_bool_type_mismatch
# ------------------------------------------------------------------

def test_validate_bool_type_mismatch() -> None:
    """int raises ValueError for a bool parameter."""
    params = _sample_params()
    with pytest.raises(ValueError, match="expects a bool"):
        validate_param_change(params, "enable_ao", 1)


# ------------------------------------------------------------------
# 14. test_validate_enum_valid
# ------------------------------------------------------------------

def test_validate_enum_valid() -> None:
    """Value in options list is accepted."""
    params = _sample_params()
    validate_param_change(params, "post_process_preset", "cinematic")
    validate_param_change(params, "post_process_preset", "filmic")
    validate_param_change(params, "post_process_preset", "default")


# ------------------------------------------------------------------
# 15. test_validate_enum_invalid
# ------------------------------------------------------------------

def test_validate_enum_invalid() -> None:
    """Value not in options raises ValueError."""
    params = _sample_params()
    with pytest.raises(ValueError, match="not in options"):
        validate_param_change(params, "post_process_preset", "hdr")


# ------------------------------------------------------------------
# 16. test_get_param_value
# ------------------------------------------------------------------

def test_get_param_value() -> None:
    """Returns current value of a parameter."""
    params = _sample_params()
    assert get_param_value(params, "light_intensity") == 5000
    assert get_param_value(params, "enable_ao") is True
    assert get_param_value(params, "post_process_preset") == "cinematic"


# ------------------------------------------------------------------
# 17. test_get_param_value_missing
# ------------------------------------------------------------------

def test_get_param_value_missing() -> None:
    """Raises KeyError for an unknown parameter name."""
    params = _sample_params()
    with pytest.raises(KeyError, match="Unknown parameter"):
        get_param_value(params, "nonexistent")


# ------------------------------------------------------------------
# 18. test_set_param_value
# ------------------------------------------------------------------

def test_set_param_value() -> None:
    """Updates value and validates; original dict is not mutated."""
    params = _sample_params()
    updated = set_param_value(params, "shadow_bias", 1.5)
    # Updated dict has the new value.
    assert updated["parameters"]["shadow_bias"]["value"] == 1.5
    # Original dict is unchanged.
    assert params["parameters"]["shadow_bias"]["value"] == 0.5


# ------------------------------------------------------------------
# 19. test_set_param_value_invalid
# ------------------------------------------------------------------

def test_set_param_value_invalid() -> None:
    """Out-of-range value raises ValueError."""
    params = _sample_params()
    with pytest.raises(ValueError, match="above maximum"):
        set_param_value(params, "shadow_bias", 5.0)
