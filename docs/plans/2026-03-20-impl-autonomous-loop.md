# Autonomous Research Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-command experiment iterations via `ue-eyes iterate` and loop status via `ue-eyes loop-status`, powered by a thin orchestration layer in `ue_eyes/experiment/loop.py`.

**Architecture:** `loop.py` wraps `ExperimentRunner`, `params.py`, and `results.py` into `run_iteration()` — a single function that mutates a parameter, runs the experiment, decides keep/discard, and reverts on discard. The CLI exposes this as `ue-eyes iterate`. The enhanced `/ue-eyes:research-loop` skill drives the loop.

**Tech Stack:** Python, Click, existing ue_eyes.experiment modules

**Spec:** `docs/plans/2026-03-20-autonomous-research-loop.md`

**Execution order:** Can be implemented after Plans 1-2, in parallel with Plan 3. Both this plan and Plan 3 add imports and commands to `cli.py` — if implemented concurrently, resolve merge conflicts in `cli.py`.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `ue_eyes/experiment/loop.py` | `IterationResult`, `run_iteration()`, `get_loop_status()`, `coerce_param_value()` |
| `tests/test_loop.py` | Unit tests for loop orchestration |
| `ue_eyes/cli.py` | `iterate` and `loop-status` commands |
| `skills/research-loop/SKILL.md` | Rewritten to use `ue-eyes iterate` |

---

### Task 1: Type Coercion Utility

**Files:**
- Create: `ue_eyes/experiment/loop.py`
- Create: `tests/test_loop.py`

The CLI receives all values as strings. This function coerces them to the correct Python type based on the parameter definition in `tune_params.json`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for ue_eyes.experiment.loop."""

import pytest

from ue_eyes.experiment.loop import coerce_param_value


def test_coerce_float():
    params = {"parameters": {"x": {"type": "float", "value": 1.0}}}
    assert coerce_param_value(params, "x", "3.14") == 3.14


def test_coerce_int():
    params = {"parameters": {"x": {"type": "int", "value": 1}}}
    assert coerce_param_value(params, "x", "42") == 42


def test_coerce_bool_true():
    params = {"parameters": {"x": {"type": "bool", "value": False}}}
    assert coerce_param_value(params, "x", "true") is True


def test_coerce_bool_false():
    params = {"parameters": {"x": {"type": "bool", "value": True}}}
    assert coerce_param_value(params, "x", "False") is False


def test_coerce_enum():
    params = {"parameters": {"x": {"type": "enum", "value": "a", "options": ["a", "b"]}}}
    assert coerce_param_value(params, "x", "b") == "b"


def test_coerce_str():
    params = {"parameters": {"x": {"type": "str", "value": "old"}}}
    assert coerce_param_value(params, "x", "new") == "new"


def test_coerce_invalid_float():
    params = {"parameters": {"x": {"type": "float", "value": 1.0}}}
    with pytest.raises(ValueError, match="Cannot convert"):
        coerce_param_value(params, "x", "notanumber")


def test_coerce_invalid_bool():
    params = {"parameters": {"x": {"type": "bool", "value": True}}}
    with pytest.raises(ValueError, match="Cannot convert"):
        coerce_param_value(params, "x", "maybe")


def test_coerce_unknown_param():
    params = {"parameters": {}}
    with pytest.raises(KeyError):
        coerce_param_value(params, "missing", "val")
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_loop.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write implementation**

```python
"""Experiment loop orchestration for autonomous research.

Wraps :class:`~ue_eyes.experiment.runner.ExperimentRunner` into a single
``run_iteration()`` call that handles parameter mutation, experiment execution,
verdict computation, and automatic revert on discard.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ue_eyes.config import UEEyesConfig
from ue_eyes.experiment.params import (
    load_params,
    save_params,
    set_param_value,
    validate_param_change,
)
from ue_eyes.experiment.results import get_best_score, get_score_trend, load_results, log_result
from ue_eyes.experiment.runner import ExperimentResult, ExperimentRunner, EXPERIMENTS_DIR, RESULTS_TSV

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


def coerce_param_value(params: dict, name: str, raw_value: str) -> Any:
    """Coerce a CLI string *raw_value* to the type declared in *params*.

    Raises :class:`KeyError` for unknown params, :class:`ValueError` for
    invalid conversions.
    """
    parameters = params.get("parameters", {})
    if name not in parameters:
        raise KeyError(f"Unknown parameter: {name!r}")

    ptype = parameters[name].get("type", "str")

    if ptype == "float":
        try:
            return float(raw_value)
        except ValueError:
            raise ValueError(f"Cannot convert {raw_value!r} to float for parameter {name!r}")

    if ptype == "int":
        try:
            return int(raw_value)
        except ValueError:
            raise ValueError(f"Cannot convert {raw_value!r} to int for parameter {name!r}")

    if ptype == "bool":
        if raw_value.lower() == "true":
            return True
        if raw_value.lower() == "false":
            return False
        raise ValueError(f"Cannot convert {raw_value!r} to bool for parameter {name!r} (use 'true' or 'false')")

    # enum and str pass through as strings
    return raw_value
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_loop.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/experiment/loop.py tests/test_loop.py
git commit -m "feat(loop): add CLI type coercion for parameter values"
```

---

### Task 2: IterationResult and run_iteration()

**Files:**
- Modify: `ue_eyes/experiment/loop.py`
- Modify: `tests/test_loop.py`

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock, patch
from pathlib import Path

from ue_eyes.experiment.loop import IterationResult, run_iteration
from ue_eyes.experiment.runner import ExperimentResult


def _make_config():
    """Create a minimal UEEyesConfig for testing."""
    from ue_eyes.config import UEEyesConfig
    return UEEyesConfig()


def _make_params():
    return {
        "version": 1,
        "parameters": {
            "brightness": {"type": "float", "value": 5000.0, "min": 0, "max": 50000},
        },
    }


def _mock_experiment_result(composite_score=0.85):
    return ExperimentResult(
        experiment_id="exp_001",
        timestamp="2026-01-01T00:00:00",
        params_before=None,
        params_after=None,
        parameter_changed="brightness",
        hypothesis="test",
        scores={"ssim": composite_score},
        composite_score=composite_score,
        rubric_result=None,
        verdict="baseline",
        error=None,
        notes="",
        capture_dir=Path("experiments/exp_001/captures"),
        comparison_dir=Path("experiments/exp_001/comparisons"),
    )


@patch("ue_eyes.experiment.loop.ExperimentRunner")
@patch("ue_eyes.experiment.loop.load_params")
@patch("ue_eyes.experiment.loop.save_params")
@patch("ue_eyes.experiment.loop.get_best_score", return_value=None)
@patch("ue_eyes.experiment.loop.load_results", return_value=[])
@patch("ue_eyes.experiment.loop.log_result")
def test_run_iteration_baseline(mock_log, mock_load_results, mock_best, mock_save, mock_load, MockRunner, tmp_path):
    mock_load.return_value = _make_params()
    mock_runner = MockRunner.return_value
    mock_runner.run_experiment.return_value = _mock_experiment_result(0.85)

    config = _make_config()
    result = run_iteration(config, "brightness", 7500.0, "Increase brightness", params_path=tmp_path / "params.json")

    assert isinstance(result, IterationResult)
    assert result.verdict == "baseline"
    assert result.parameter_name == "brightness"
    assert result.old_value == 5000.0
    assert result.new_value == 7500.0


@patch("ue_eyes.experiment.loop.ExperimentRunner")
@patch("ue_eyes.experiment.loop.load_params")
@patch("ue_eyes.experiment.loop.save_params")
@patch("ue_eyes.experiment.loop.get_best_score", return_value={"composite_score": 0.80})
@patch("ue_eyes.experiment.loop.load_results", return_value=[{"composite_score": 0.80}])
@patch("ue_eyes.experiment.loop.log_result")
def test_run_iteration_keep(mock_log, mock_load_results, mock_best, mock_save, mock_load, MockRunner, tmp_path):
    mock_load.return_value = _make_params()
    mock_runner = MockRunner.return_value
    mock_runner.run_experiment.return_value = _mock_experiment_result(0.90)

    config = _make_config()
    result = run_iteration(config, "brightness", 7500.0, "Increase brightness", params_path=tmp_path / "params.json")

    assert result.verdict == "keep"
    assert result.experiment.composite_score == 0.90


@patch("ue_eyes.experiment.loop.ExperimentRunner")
@patch("ue_eyes.experiment.loop.load_params")
@patch("ue_eyes.experiment.loop.save_params")
@patch("ue_eyes.experiment.loop.get_best_score", return_value={"composite_score": 0.90})
@patch("ue_eyes.experiment.loop.load_results", return_value=[{"composite_score": 0.90}])
@patch("ue_eyes.experiment.loop.log_result")
def test_run_iteration_discard_reverts(mock_log, mock_load_results, mock_best, mock_save, mock_load, MockRunner, tmp_path):
    original_params = _make_params()
    mock_load.return_value = original_params
    mock_runner = MockRunner.return_value
    mock_runner.run_experiment.return_value = _mock_experiment_result(0.80)

    config = _make_config()
    result = run_iteration(config, "brightness", 100.0, "Try lower", params_path=tmp_path / "params.json")

    assert result.verdict == "discard"
    # save_params called twice: once for mutation, once for revert
    assert mock_save.call_count == 2
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_loop.py::test_run_iteration_baseline -v`

- [ ] **Step 3: Write implementation**

Add to `ue_eyes/experiment/loop.py`:

```python
# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class IterationResult:
    """Wraps an ExperimentResult with iteration-level metadata."""

    experiment: ExperimentResult
    parameter_name: str
    old_value: Any
    new_value: Any
    best_previous_score: float
    verdict: str  # "baseline", "keep", "discard"


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def run_iteration(
    config: UEEyesConfig,
    parameter_name: str,
    new_value: Any,
    hypothesis: str,
    baseline_dir: str | None = None,
    params_path: Path | None = None,
) -> IterationResult:
    """Run a single experiment iteration.

    1. Load and snapshot current params
    2. Validate and mutate the parameter
    3. Run the experiment (capture, compare, score)
    4. Decide: keep or discard
    5. Revert on discard
    6. Log result
    7. Return IterationResult
    """
    if params_path is None:
        params_path = Path(config.params_file)

    results_tsv = Path(EXPERIMENTS_DIR) / RESULTS_TSV

    # 1. Load and snapshot
    params = load_params(params_path)
    snapshot = copy.deepcopy(params)
    old_value = params["parameters"][parameter_name]["value"]

    # 2. Validate and mutate
    validate_param_change(params, parameter_name, new_value)
    params = set_param_value(params, parameter_name, new_value)
    save_params(params, params_path)

    # 3. Generate experiment ID
    existing = load_results(results_tsv)
    experiment_id = f"exp_{len(existing) + 1:03d}"

    # 4. Run experiment
    runner = ExperimentRunner(config)
    if baseline_dir is not None:
        runner.set_baseline(Path(baseline_dir))

    experiment_result = runner.run_experiment(
        experiment_id=experiment_id,
        apply_fn=None,  # Agent mode — params already mutated
        params=params,
        hypothesis=hypothesis,
        parameter_changed=parameter_name,
    )

    # 5. Decide
    best = get_best_score(results_tsv)
    if best is None:
        verdict = "baseline"
        best_score = 0.0
    else:
        best_score = best.get("composite_score", 0.0)
        if not isinstance(best_score, (int, float)):
            best_score = 0.0
        if experiment_result.composite_score > best_score:
            verdict = "keep"
        else:
            verdict = "discard"

    # 6. Revert on discard
    if verdict == "discard":
        save_params(snapshot, params_path)

    # 7. Note on logging: ExperimentRunner.run_experiment() already logs
    # to results.tsv with its own verdict. Since the runner calls
    # get_best_score() on the same TSV, its verdict should match ours
    # in single-threaded use. The IterationResult.verdict is what
    # the CLI reports to the agent. If they ever diverge (shouldn't
    # happen in practice), the TSV has the runner's verdict and the
    # CLI output has the loop's verdict.

    return IterationResult(
        experiment=experiment_result,
        parameter_name=parameter_name,
        old_value=old_value,
        new_value=new_value,
        best_previous_score=best_score,
        verdict=verdict,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_loop.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/experiment/loop.py tests/test_loop.py
git commit -m "feat(loop): add IterationResult and run_iteration orchestration"
```

---

### Task 3: Loop Status

**Files:**
- Modify: `ue_eyes/experiment/loop.py`
- Modify: `tests/test_loop.py`

- [ ] **Step 1: Write the failing tests**

```python
@patch("ue_eyes.experiment.loop.load_params")
@patch("ue_eyes.experiment.loop.load_results")
@patch("ue_eyes.experiment.loop.get_best_score")
@patch("ue_eyes.experiment.loop.get_score_trend")
def test_get_loop_status_empty(mock_trend, mock_best, mock_results, mock_params):
    mock_params.return_value = _make_params()
    mock_results.return_value = []
    mock_best.return_value = None
    mock_trend.return_value = []

    from ue_eyes.experiment.loop import get_loop_status
    status = get_loop_status(Path("params.json"))
    assert status["experiment_count"] == 0
    assert status["best_score"] is None
    assert "brightness" in status["parameters"]


@patch("ue_eyes.experiment.loop.load_params")
@patch("ue_eyes.experiment.loop.load_results")
@patch("ue_eyes.experiment.loop.get_best_score")
@patch("ue_eyes.experiment.loop.get_score_trend")
def test_get_loop_status_with_history(mock_trend, mock_best, mock_results, mock_params):
    mock_params.return_value = _make_params()
    mock_results.return_value = [
        {"parameter": "brightness", "composite_score": 0.85},
    ]
    mock_best.return_value = {"experiment": "exp_001", "composite_score": 0.85}
    mock_trend.return_value = [0.85]

    from ue_eyes.experiment.loop import get_loop_status
    status = get_loop_status(Path("params.json"))
    assert status["experiment_count"] == 1
    assert status["best_score"] == 0.85
```

- [ ] **Step 2: Run to verify fail**

- [ ] **Step 3: Write implementation**

Add to `ue_eyes/experiment/loop.py`:

```python
def get_loop_status(params_path: Path | None = None) -> dict:
    """Return a summary of the experiment loop state for the agent."""
    if params_path is None:
        params_path = Path("tune_params.json")

    results_tsv = Path(EXPERIMENTS_DIR) / RESULTS_TSV

    params = load_params(params_path)
    results = load_results(results_tsv)
    best = get_best_score(results_tsv)
    trend = get_score_trend(results_tsv)

    # Extract parameter names and current values
    parameters = {}
    for name, defn in params.get("parameters", {}).items():
        parameters[name] = {
            "value": defn.get("value"),
            "type": defn.get("type"),
        }

    # Find parameters that have been tested
    tested = {r.get("parameter") for r in results if r.get("parameter")}

    return {
        "experiment_count": len(results),
        "best_score": best.get("composite_score") if best else None,
        "best_experiment": best.get("experiment") if best else None,
        "score_trend": trend,
        "parameters": parameters,
        "tested_parameters": sorted(tested),
        "untested_parameters": sorted(set(parameters.keys()) - tested),
    }
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_loop.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/experiment/loop.py tests/test_loop.py
git commit -m "feat(loop): add get_loop_status for experiment state summary"
```

---

### Task 4: CLI Commands (`iterate` and `loop-status`)

**Files:**
- Modify: `ue_eyes/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_iterate_command_exists(runner):
    result = runner.invoke(main, ["iterate", "--help"])
    assert result.exit_code == 0
    assert "--param" in result.output
    assert "--value" in result.output
    assert "--hypothesis" in result.output


def test_loop_status_command_exists(runner):
    result = runner.invoke(main, ["loop-status", "--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_cli.py::test_iterate_command_exists -v`

- [ ] **Step 3: Write the iterate command**

Add imports to `cli.py`:

```python
from ue_eyes.config import load_config
from ue_eyes.experiment.loop import coerce_param_value, run_iteration, get_loop_status
from ue_eyes.experiment.params import load_params
```

Add commands:

```python
@main.command()
@click.option("--param", required=True, help="Parameter name from tune_params.json.")
@click.option("--value", required=True, help="New value to test (auto-coerced to param type).")
@click.option("--hypothesis", required=True, help="Why this change should improve the score.")
@click.option("--baseline", default=None, type=click.Path(exists=True),
              help="Override baseline directory.")
@click.option("--params-file", default=None, type=click.Path(exists=True),
              help="Path to tune_params.json (default: from config).")
def iterate(param: str, value: str, hypothesis: str, baseline: str | None, params_file: str | None) -> None:
    """Run a single experiment iteration: mutate param, capture, score, decide."""
    config = load_config()
    params_path = Path(params_file) if params_file else Path(config.params_file)

    # Load params to coerce value type
    try:
        params = load_params(params_path)
    except FileNotFoundError:
        click.secho(f"Parameter file not found: {params_path}", fg="red", err=True)
        sys.exit(1)

    try:
        typed_value = coerce_param_value(params, param, value)
    except (KeyError, ValueError) as exc:
        click.secho(str(exc), fg="red", err=True)
        sys.exit(1)

    try:
        result = run_iteration(
            config=config,
            parameter_name=param,
            new_value=typed_value,
            hypothesis=hypothesis,
            baseline_dir=baseline,
            params_path=params_path,
        )
    except (UEConnectionError, UEExecutionError) as exc:
        _handle_ue_error(exc)
        return
    except (KeyError, ValueError) as exc:
        click.secho(f"Parameter error: {exc}", fg="red", err=True)
        sys.exit(1)

    # Output JSON for agent consumption
    output = {
        "experiment_id": result.experiment.experiment_id,
        "parameter": result.parameter_name,
        "old_value": result.old_value,
        "new_value": result.new_value,
        "hypothesis": hypothesis,
        "composite_score": result.experiment.composite_score,
        "best_previous_score": result.best_previous_score,
        "verdict": result.verdict,
        "scores": result.experiment.scores,
        "capture_dir": str(result.experiment.capture_dir),
        "comparison_dir": str(result.experiment.comparison_dir),
    }

    verdict_color = {"keep": "green", "discard": "red", "baseline": "cyan"}.get(result.verdict, "white")
    click.secho(f"Verdict: {result.verdict} (score={result.experiment.composite_score:.4f})", fg=verdict_color, err=True)
    _dump_json(output)


@main.command("loop-status")
@click.option("--params-file", default=None, type=click.Path(exists=True),
              help="Path to tune_params.json.")
def loop_status(params_file: str | None) -> None:
    """Show experiment loop status: scores, tested parameters, trends."""
    params_path = Path(params_file) if params_file else None
    try:
        status = get_loop_status(params_path)
    except FileNotFoundError as exc:
        click.secho(f"Not found: {exc}", fg="red", err=True)
        sys.exit(1)

    _dump_json(status)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All passed

- [ ] **Step 5: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: All passed

- [ ] **Step 6: Commit**

```bash
git add ue_eyes/cli.py tests/test_cli.py
git commit -m "feat: add iterate and loop-status CLI commands"
```

---

### Task 5: Update Research Loop Skill

**Files:**
- Modify: `skills/research-loop/SKILL.md`

- [ ] **Step 1: Read the current skill**

Read `skills/research-loop/SKILL.md` to understand the current structure.

- [ ] **Step 2: Rewrite the core loop section**

Replace the manual steps (edit tune_params.json, run ue-eyes snap, run ue-eyes score, etc.) with the streamlined flow:

**ANALYZE:** `ue-eyes loop-status` + read comparison images from best experiment
**HYPOTHESIZE:** Pick ONE parameter and value, form hypothesis
**RUN:** `ue-eyes iterate --param X --value Y --hypothesis "..."`
**EVALUATE:** Read JSON output + visually inspect comparison images
**LOOP:** Return to ANALYZE

Keep the escalation strategies section unchanged.

- [ ] **Step 3: Commit**

```bash
git add skills/research-loop/SKILL.md
git commit -m "feat: update research-loop skill to use ue-eyes iterate"
```
