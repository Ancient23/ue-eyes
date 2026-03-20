"""Tests for ue_eyes.experiment.loop — coerce_param_value, run_iteration, get_loop_status."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from ue_eyes.config import UEEyesConfig
from ue_eyes.experiment.loop import coerce_param_value, get_loop_status, run_iteration
from ue_eyes.experiment.runner import ExperimentResult, EXPERIMENTS_DIR, RESULTS_TSV


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_params() -> dict:
    """Return a representative parameter dict for testing."""
    return {
        "version": 1,
        "parameters": {
            "light_intensity": {"value": 5000.0, "type": "float", "min": 0, "max": 50000},
            "sample_count": {"value": 4, "type": "int", "min": 1, "max": 64},
            "enable_ao": {"value": True, "type": "bool"},
            "post_process_preset": {
                "value": "cinematic",
                "type": "enum",
                "options": ["default", "cinematic", "filmic"],
            },
            "notes": {"value": "baseline", "type": "str"},
        },
    }


def _write_params(path: Path, data: dict) -> Path:
    """Write *data* as JSON to *path* and return the path."""
    path.write_text(json.dumps(data, indent=2))
    return path


def _make_config(**overrides: object) -> UEEyesConfig:
    return UEEyesConfig(**overrides)  # type: ignore[arg-type]


def _make_experiment_result(
    experiment_id: str = "exp_001",
    composite_score: float = 0.85,
    verdict: str = "baseline",
) -> ExperimentResult:
    return ExperimentResult(
        experiment_id=experiment_id,
        timestamp="2026-03-20T00:00:00+00:00",
        params_before=None,
        params_after=None,
        parameter_changed=None,
        hypothesis="test",
        scores={"ssim": composite_score},
        composite_score=composite_score,
        rubric_result=None,
        verdict=verdict,
        error=None,
        notes="",
        capture_dir=Path(f"experiments/{experiment_id}/captures"),
        comparison_dir=Path(f"experiments/{experiment_id}/comparisons"),
    )


# ===========================================================================
# Task 1: coerce_param_value
# ===========================================================================


def test_coerce_float() -> None:
    """'float' type converts raw_value via float()."""
    params = _sample_params()
    result = coerce_param_value(params, "light_intensity", "1234.5")
    assert result == 1234.5
    assert isinstance(result, float)


def test_coerce_int() -> None:
    """'int' type converts raw_value via int()."""
    params = _sample_params()
    result = coerce_param_value(params, "sample_count", "16")
    assert result == 16
    assert isinstance(result, int)


def test_coerce_bool_true() -> None:
    """'bool' type, 'true' (case-insensitive) → True."""
    params = _sample_params()
    assert coerce_param_value(params, "enable_ao", "true") is True
    assert coerce_param_value(params, "enable_ao", "True") is True
    assert coerce_param_value(params, "enable_ao", "TRUE") is True


def test_coerce_bool_false() -> None:
    """'bool' type, 'false' (case-insensitive) → False."""
    params = _sample_params()
    assert coerce_param_value(params, "enable_ao", "false") is False
    assert coerce_param_value(params, "enable_ao", "False") is False
    assert coerce_param_value(params, "enable_ao", "FALSE") is False


def test_coerce_enum() -> None:
    """'enum' type passes through as string."""
    params = _sample_params()
    result = coerce_param_value(params, "post_process_preset", "filmic")
    assert result == "filmic"
    assert isinstance(result, str)


def test_coerce_str() -> None:
    """'str' type passes through as string."""
    params = _sample_params()
    result = coerce_param_value(params, "notes", "my notes")
    assert result == "my notes"
    assert isinstance(result, str)


def test_coerce_invalid_float() -> None:
    """Non-numeric raw_value for float parameter raises ValueError."""
    params = _sample_params()
    with pytest.raises(ValueError):
        coerce_param_value(params, "light_intensity", "not_a_number")


def test_coerce_invalid_bool() -> None:
    """Non-true/false raw_value for bool parameter raises ValueError."""
    params = _sample_params()
    with pytest.raises(ValueError, match="[Bb]ool"):
        coerce_param_value(params, "enable_ao", "yes")


def test_coerce_unknown_param() -> None:
    """Unknown parameter name raises KeyError."""
    params = _sample_params()
    with pytest.raises(KeyError):
        coerce_param_value(params, "nonexistent", "42")


# ===========================================================================
# Task 2: IterationResult + run_iteration
# ===========================================================================


class TestRunIterationBaseline:
    """No prior results → verdict 'baseline'."""

    def test_run_iteration_baseline(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        params_path = tmp_path / "tune_params.json"
        _write_params(params_path, _sample_params())

        config = _make_config()
        exp_result = _make_experiment_result("exp_001", composite_score=0.85, verdict="baseline")

        with (
            patch("ue_eyes.experiment.loop.load_params", return_value=_sample_params()) as mock_load,
            patch("ue_eyes.experiment.loop.save_params") as mock_save,
            patch("ue_eyes.experiment.loop.ExperimentRunner") as mock_runner_cls,
            patch("ue_eyes.experiment.loop.get_best_score", return_value=None) as mock_best,
        ):
            mock_runner = mock_runner_cls.return_value
            mock_runner.run_experiment.return_value = exp_result

            from ue_eyes.experiment.loop import run_iteration

            result = run_iteration(
                config=config,
                parameter_name="light_intensity",
                new_value=8000.0,
                hypothesis="Higher intensity improves reflections",
                params_path=params_path,
            )

        assert result.verdict == "baseline"
        assert result.parameter_name == "light_intensity"
        assert result.new_value == 8000.0
        assert result.experiment.experiment_id == "exp_001"


class TestRunIterationKeep:
    """Score beats best → verdict 'keep'."""

    def test_run_iteration_keep(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        params_path = tmp_path / "tune_params.json"
        _write_params(params_path, _sample_params())

        config = _make_config()
        exp_result = _make_experiment_result("exp_002", composite_score=0.95, verdict="keep")

        best_row = {"composite_score": 0.80, "experiment": "exp_001"}

        with (
            patch("ue_eyes.experiment.loop.load_params", return_value=_sample_params()),
            patch("ue_eyes.experiment.loop.save_params") as mock_save,
            patch("ue_eyes.experiment.loop.ExperimentRunner") as mock_runner_cls,
            patch("ue_eyes.experiment.loop.get_best_score", return_value=best_row),
        ):
            mock_runner = mock_runner_cls.return_value
            mock_runner.run_experiment.return_value = exp_result

            from ue_eyes.experiment.loop import run_iteration

            result = run_iteration(
                config=config,
                parameter_name="light_intensity",
                new_value=8000.0,
                hypothesis="Higher intensity improves reflections",
                params_path=params_path,
            )

        assert result.verdict == "keep"
        assert result.best_previous_score == pytest.approx(0.80)
        # save_params called once (mutation), NOT called again (no revert)
        assert mock_save.call_count == 1


class TestRunIterationDiscard:
    """Score below best → verdict 'discard', save_params called twice."""

    def test_run_iteration_discard_reverts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        params_path = tmp_path / "tune_params.json"
        original_params = _sample_params()
        _write_params(params_path, original_params)

        config = _make_config()
        exp_result = _make_experiment_result("exp_003", composite_score=0.50, verdict="discard")

        best_row = {"composite_score": 0.90, "experiment": "exp_001"}

        with (
            patch("ue_eyes.experiment.loop.load_params", return_value=_sample_params()),
            patch("ue_eyes.experiment.loop.save_params") as mock_save,
            patch("ue_eyes.experiment.loop.ExperimentRunner") as mock_runner_cls,
            patch("ue_eyes.experiment.loop.get_best_score", return_value=best_row),
        ):
            mock_runner = mock_runner_cls.return_value
            mock_runner.run_experiment.return_value = exp_result

            from ue_eyes.experiment.loop import run_iteration

            result = run_iteration(
                config=config,
                parameter_name="light_intensity",
                new_value=8000.0,
                hypothesis="Higher intensity improves reflections",
                params_path=params_path,
            )

        assert result.verdict == "discard"
        # save_params called twice: mutation + revert
        assert mock_save.call_count == 2


# ===========================================================================
# Task 3: get_loop_status
# ===========================================================================


class TestGetLoopStatusEmpty:
    """Empty state — no experiments, no params file."""

    def test_empty_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)

        with patch("ue_eyes.experiment.loop.load_params", side_effect=FileNotFoundError):
            status = get_loop_status(params_path=tmp_path / "nonexistent.json")

        assert status["experiment_count"] == 0
        assert status["best_score"] is None
        assert status["best_experiment"] is None
        assert status["score_trend"] == []
        assert status["parameters"] == {}
        assert status["tested_parameters"] == []
        assert status["untested_parameters"] == []


class TestGetLoopStatusWithHistory:
    """State with prior experiments and params."""

    def test_with_history(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        params_path = tmp_path / "tune_params.json"
        params = _sample_params()
        _write_params(params_path, params)

        # Build a fake results.tsv
        results_rows = [
            {
                "experiment": "exp_001",
                "timestamp": "2026-03-20T00:00:00+00:00",
                "parameter": "light_intensity",
                "old_value": "5000",
                "new_value": "8000",
                "hypothesis": "test",
                "composite_score": 0.75,
                "metric_scores_json": {},
                "verdict": "baseline",
                "notes": "",
            },
            {
                "experiment": "exp_002",
                "timestamp": "2026-03-20T01:00:00+00:00",
                "parameter": "sample_count",
                "old_value": "4",
                "new_value": "8",
                "hypothesis": "test",
                "composite_score": 0.85,
                "metric_scores_json": {},
                "verdict": "keep",
                "notes": "",
            },
        ]

        best_row = {"composite_score": 0.85, "experiment": "exp_002"}
        trend = [0.75, 0.85]

        with (
            patch("ue_eyes.experiment.loop.load_params", return_value=params),
            patch("ue_eyes.experiment.loop.load_results", return_value=results_rows),
            patch("ue_eyes.experiment.loop.get_best_score", return_value=best_row),
            patch("ue_eyes.experiment.loop.get_score_trend", return_value=trend),
        ):
            status = get_loop_status(params_path=params_path)

        assert status["experiment_count"] == 2
        assert status["best_score"] == pytest.approx(0.85)
        assert status["best_experiment"] == "exp_002"
        assert status["score_trend"] == [pytest.approx(0.75), pytest.approx(0.85)]

        # parameters should be name -> {value, type}
        assert "light_intensity" in status["parameters"]
        assert status["parameters"]["light_intensity"]["type"] == "float"
        assert status["parameters"]["light_intensity"]["value"] == 5000.0

        # tested_parameters: params that appear in results history
        assert "light_intensity" in status["tested_parameters"]
        assert "sample_count" in status["tested_parameters"]

        # untested_parameters: params not yet tried
        for name in status["untested_parameters"]:
            assert name not in status["tested_parameters"]
