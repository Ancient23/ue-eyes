"""Autonomous research loop for ue-eyes — single-iteration control logic.

Provides :func:`coerce_param_value`, :func:`run_iteration`, and
:func:`get_loop_status` as the core API consumed by the CLI and the
research-loop skill.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ue_eyes.config import UEEyesConfig
from ue_eyes.experiment.params import (
    get_param_value,
    load_params,
    save_params,
    set_param_value,
)
from ue_eyes.experiment.results import get_best_score, get_score_trend, load_results
from ue_eyes.experiment.runner import EXPERIMENTS_DIR, RESULTS_TSV, ExperimentResult, ExperimentRunner

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

EXP_ID_PATTERN: str = "exp_{n:03d}"
_EXP_ID_RE = re.compile(r"^exp_(\d+)$")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class IterationResult:
    """Holds the outcome of a single experiment iteration."""

    experiment: ExperimentResult
    parameter_name: str
    old_value: Any
    new_value: Any
    best_previous_score: float
    verdict: str  # "baseline", "keep", "discard"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def coerce_param_value(params: dict, name: str, raw_value: str) -> Any:
    """Coerce a CLI string to the type declared in *params*.

    Parameters
    ----------
    params:
        Full parameter dict (as returned by :func:`load_params`).
    name:
        Parameter name to look up.
    raw_value:
        The string value provided on the command line.

    Returns
    -------
    Any
        The coerced value with the correct Python type.

    Raises
    ------
    KeyError
        If *name* is not present in *params*.
    ValueError
        If *raw_value* cannot be converted to the declared type.
    """
    parameters = params.get("parameters", {})
    if name not in parameters:
        raise KeyError(f"Unknown parameter: {name!r}")

    ptype: str = parameters[name].get("type", "str")

    if ptype == "float":
        try:
            return float(raw_value)
        except ValueError:
            raise ValueError(
                f"Cannot convert {raw_value!r} to float for parameter {name!r}"
            )

    if ptype == "int":
        try:
            return int(raw_value)
        except ValueError:
            raise ValueError(
                f"Cannot convert {raw_value!r} to int for parameter {name!r}"
            )

    if ptype == "bool":
        lower = raw_value.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        raise ValueError(
            f"Bool parameter {name!r} requires 'true' or 'false', got {raw_value!r}"
        )

    # "enum" and "str" — pass through as string
    return raw_value


def run_iteration(
    config: UEEyesConfig,
    parameter_name: str,
    new_value: Any,
    hypothesis: str,
    baseline_dir: str | None = None,
    params_path: Path | None = None,
) -> IterationResult:
    """Run a single experiment iteration.

    Steps
    -----
    1. Load and snapshot current params.
    2. Validate and mutate the parameter.
    3. Generate experiment ID (``exp_001``, ``exp_002``, …).
    4. Run :class:`ExperimentRunner`.run_experiment().
    5. Get best score from history, compute verdict.
    6. Revert params on discard.
    7. Return :class:`IterationResult`.

    Parameters
    ----------
    config:
        Loaded :class:`UEEyesConfig`.
    parameter_name:
        The single parameter to change.
    new_value:
        Already-coerced new value (use :func:`coerce_param_value` first).
    hypothesis:
        Short description of the prediction.
    baseline_dir:
        Optional path to reference captures for scoring.
    params_path:
        Path to the parameter JSON file.  Defaults to ``config.params_file``.

    Returns
    -------
    IterationResult
    """
    if params_path is None:
        params_path = Path(config.params_file)

    # 1. Load and snapshot
    params = load_params(params_path)
    params_snapshot = copy.deepcopy(params)
    old_value = get_param_value(params, parameter_name)

    # 2. Mutate and persist
    updated_params = set_param_value(params, parameter_name, new_value)
    save_params(updated_params, params_path)

    # 3. Generate experiment ID
    results_tsv = Path(EXPERIMENTS_DIR) / RESULTS_TSV
    prior_results = load_results(results_tsv)
    experiment_id = _next_experiment_id(prior_results)

    # 5a. Capture the best score BEFORE running (so we can compare afterwards)
    best_before = get_best_score(results_tsv)
    if best_before is None:
        best_previous_score = 0.0
    else:
        raw = best_before.get("composite_score", 0.0)
        best_previous_score = float(raw) if isinstance(raw, (int, float)) else 0.0

    # 4. Run experiment
    runner = ExperimentRunner(config)
    if baseline_dir is not None:
        runner.set_baseline(Path(baseline_dir))

    exp_result = runner.run_experiment(
        experiment_id=experiment_id,
        apply_fn=None,
        params=updated_params,
        hypothesis=hypothesis,
        parameter_changed=parameter_name,
    )

    # 5b. Compute verdict
    if best_before is None:
        verdict = "baseline"
    elif exp_result.composite_score > best_previous_score:
        verdict = "keep"
    else:
        verdict = "discard"

    # 6. Revert params if discard
    if verdict == "discard":
        save_params(params_snapshot, params_path)

    return IterationResult(
        experiment=exp_result,
        parameter_name=parameter_name,
        old_value=old_value,
        new_value=new_value,
        best_previous_score=best_previous_score,
        verdict=verdict,
    )


def get_loop_status(params_path: Path | None = None) -> dict:
    """Return a summary of the experiment loop state.

    Parameters
    ----------
    params_path:
        Path to the parameter JSON file.  ``None`` uses ``tune_params.json``
        in the current directory.

    Returns
    -------
    dict with keys:
        - ``experiment_count`` — number of experiments run
        - ``best_score`` — highest composite score seen (or ``None``)
        - ``best_experiment`` — experiment ID of best result (or ``None``)
        - ``score_trend`` — last 10 composite scores as a list
        - ``parameters`` — dict of ``{name: {value, type}}``
        - ``tested_parameters`` — parameter names that appear in results
        - ``untested_parameters`` — parameter names not yet tested
    """
    if params_path is None:
        params_path = Path("tune_params.json")

    results_tsv = Path(EXPERIMENTS_DIR) / RESULTS_TSV

    # Load parameters (gracefully handle missing file)
    try:
        params = load_params(params_path)
        param_defs = params.get("parameters", {})
    except (FileNotFoundError, ValueError):
        param_defs = {}

    # Summarise parameter definitions
    parameters: dict[str, dict] = {
        name: {"value": defn.get("value"), "type": defn.get("type", "str")}
        for name, defn in param_defs.items()
    }

    # Load results
    rows = load_results(results_tsv)
    experiment_count = len(rows)

    best_row = get_best_score(results_tsv)
    best_score: float | None = None
    best_experiment: str | None = None
    if best_row is not None:
        raw = best_row.get("composite_score")
        if isinstance(raw, (int, float)):
            best_score = float(raw)
        best_experiment = best_row.get("experiment") or None

    score_trend = get_score_trend(results_tsv)

    # Identify tested vs untested parameters
    tested_set: set[str] = set()
    for row in rows:
        param = row.get("parameter", "")
        if param:
            tested_set.add(param)

    tested_parameters = sorted(tested_set)
    untested_parameters = sorted(
        name for name in param_defs if name not in tested_set
    )

    return {
        "experiment_count": experiment_count,
        "best_score": best_score,
        "best_experiment": best_experiment,
        "score_trend": score_trend,
        "parameters": parameters,
        "tested_parameters": tested_parameters,
        "untested_parameters": untested_parameters,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _next_experiment_id(prior_results: list[dict]) -> str:
    """Return the next sequential experiment ID (``exp_001``, ``exp_002``, …)."""
    max_n = 0
    for row in prior_results:
        exp_id = row.get("experiment", "")
        m = _EXP_ID_RE.match(exp_id)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return EXP_ID_PATTERN.format(n=max_n + 1)
