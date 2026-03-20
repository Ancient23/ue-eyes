"""Tests for ue_eyes.experiment — parameter loading, diffing, validation, and results tracking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ue_eyes.experiment import (
    RESULTS_HEADER,
    diff_params,
    get_best_score,
    get_param_value,
    get_score_trend,
    init_results,
    load_params,
    load_results,
    log_result,
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


# ===========================================================================
# Results tracking tests
# ===========================================================================

def _sample_result(**overrides: object) -> dict:
    """Return a representative result dict for testing."""
    base: dict = {
        "experiment": "exp_001",
        "timestamp": "2026-03-19T12:00:00+00:00",
        "parameter": "light_intensity",
        "old_value": "5000",
        "new_value": "8000",
        "hypothesis": "Brighter light improves eye reflections",
        "composite_score": 0.85,
        "metric_scores_json": {"ssim": 0.82, "pixel_mse": 0.91},
        "verdict": "improved",
        "notes": "Clear improvement in specular highlights",
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------
# 20. test_init_results_creates_file
# ------------------------------------------------------------------

def test_init_results_creates_file(tmp_path: Path) -> None:
    """New file is created with the correct header."""
    tsv = tmp_path / "results.tsv"
    init_results(tsv)
    assert tsv.exists()
    text = tsv.read_text(encoding="utf-8")
    header_line = text.strip().split("\n")[0]
    assert header_line == "\t".join(RESULTS_HEADER)


# ------------------------------------------------------------------
# 21. test_init_results_idempotent
# ------------------------------------------------------------------

def test_init_results_idempotent(tmp_path: Path) -> None:
    """Calling init_results twice does not overwrite the file."""
    tsv = tmp_path / "results.tsv"
    init_results(tsv)
    # Append a dummy line so we can check it survives the second call.
    with tsv.open("a", encoding="utf-8") as f:
        f.write("extra_line\n")
    init_results(tsv)
    text = tsv.read_text(encoding="utf-8")
    assert "extra_line" in text


# ------------------------------------------------------------------
# 22. test_log_result_appends_row
# ------------------------------------------------------------------

def test_log_result_appends_row(tmp_path: Path) -> None:
    """One data row after the header."""
    tsv = tmp_path / "results.tsv"
    init_results(tsv)
    log_result(tsv, _sample_result())
    lines = tsv.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2  # header + 1 row


# ------------------------------------------------------------------
# 23. test_log_result_auto_initializes
# ------------------------------------------------------------------

def test_log_result_auto_initializes(tmp_path: Path) -> None:
    """File is created automatically when log_result is called on a missing file."""
    tsv = tmp_path / "sub" / "results.tsv"
    assert not tsv.exists()
    log_result(tsv, _sample_result())
    assert tsv.exists()
    lines = tsv.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2  # header + 1 row


# ------------------------------------------------------------------
# 24. test_log_result_serializes_metric_scores
# ------------------------------------------------------------------

def test_log_result_serializes_metric_scores(tmp_path: Path) -> None:
    """metric_scores_json dict is written as a JSON string in the TSV."""
    tsv = tmp_path / "results.tsv"
    log_result(tsv, _sample_result())
    text = tsv.read_text(encoding="utf-8")
    data_line = text.strip().split("\n")[1]
    # The JSON-serialized dict should appear as a substring.
    assert '"ssim"' in data_line
    assert '"pixel_mse"' in data_line


# ------------------------------------------------------------------
# 25. test_load_results_empty
# ------------------------------------------------------------------

def test_load_results_empty(tmp_path: Path) -> None:
    """Nonexistent file returns an empty list."""
    tsv = tmp_path / "missing.tsv"
    assert load_results(tsv) == []


# ------------------------------------------------------------------
# 26. test_load_results_parses_rows
# ------------------------------------------------------------------

def test_load_results_parses_rows(tmp_path: Path) -> None:
    """Returns list of dicts with correct keys."""
    tsv = tmp_path / "results.tsv"
    log_result(tsv, _sample_result())
    rows = load_results(tsv)
    assert len(rows) == 1
    row = rows[0]
    for key in RESULTS_HEADER:
        assert key in row


# ------------------------------------------------------------------
# 27. test_load_results_converts_numeric
# ------------------------------------------------------------------

def test_load_results_converts_numeric(tmp_path: Path) -> None:
    """composite_score is loaded as a float."""
    tsv = tmp_path / "results.tsv"
    log_result(tsv, _sample_result(composite_score=0.92))
    rows = load_results(tsv)
    assert isinstance(rows[0]["composite_score"], float)
    assert rows[0]["composite_score"] == pytest.approx(0.92)


# ------------------------------------------------------------------
# 28. test_load_results_parses_metric_scores_json
# ------------------------------------------------------------------

def test_load_results_parses_metric_scores_json(tmp_path: Path) -> None:
    """metric_scores_json JSON string is parsed back to a dict."""
    tsv = tmp_path / "results.tsv"
    metrics = {"ssim": 0.82, "pixel_mse": 0.91}
    log_result(tsv, _sample_result(metric_scores_json=metrics))
    rows = load_results(tsv)
    loaded_metrics = rows[0]["metric_scores_json"]
    assert isinstance(loaded_metrics, dict)
    assert loaded_metrics["ssim"] == pytest.approx(0.82)
    assert loaded_metrics["pixel_mse"] == pytest.approx(0.91)


# ------------------------------------------------------------------
# 29. test_get_best_score
# ------------------------------------------------------------------

def test_get_best_score(tmp_path: Path) -> None:
    """Returns the row with the highest composite_score."""
    tsv = tmp_path / "results.tsv"
    log_result(tsv, _sample_result(experiment="a", composite_score=0.70))
    log_result(tsv, _sample_result(experiment="b", composite_score=0.95))
    log_result(tsv, _sample_result(experiment="c", composite_score=0.80))
    best = get_best_score(tsv)
    assert best is not None
    assert best["experiment"] == "b"
    assert best["composite_score"] == pytest.approx(0.95)


# ------------------------------------------------------------------
# 30. test_get_best_score_empty
# ------------------------------------------------------------------

def test_get_best_score_empty(tmp_path: Path) -> None:
    """Returns None when the file does not exist."""
    tsv = tmp_path / "empty.tsv"
    assert get_best_score(tsv) is None


# ------------------------------------------------------------------
# 31. test_get_score_trend
# ------------------------------------------------------------------

def test_get_score_trend(tmp_path: Path) -> None:
    """Returns the last N composite_score values."""
    tsv = tmp_path / "results.tsv"
    scores = [0.60, 0.65, 0.70, 0.75, 0.80]
    for i, s in enumerate(scores):
        log_result(tsv, _sample_result(experiment=f"exp_{i}", composite_score=s))
    trend = get_score_trend(tsv, last_n=3)
    assert len(trend) == 3
    assert trend == [pytest.approx(0.70), pytest.approx(0.75), pytest.approx(0.80)]


# ------------------------------------------------------------------
# 32. test_get_score_trend_fewer_than_n
# ------------------------------------------------------------------

def test_get_score_trend_fewer_than_n(tmp_path: Path) -> None:
    """Returns all available scores when fewer than last_n exist."""
    tsv = tmp_path / "results.tsv"
    log_result(tsv, _sample_result(composite_score=0.55))
    log_result(tsv, _sample_result(composite_score=0.60))
    trend = get_score_trend(tsv, last_n=10)
    assert len(trend) == 2
    assert trend == [pytest.approx(0.55), pytest.approx(0.60)]
