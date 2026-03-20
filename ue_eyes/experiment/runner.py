"""Experiment runner — the 6-step pipeline for ue-eyes experiments.

Orchestrates APPLY, CAPTURE, COMPARE, SCORE, DECIDE, and LOG steps
into a single ``run_experiment()`` call.  Each step delegates to the
appropriate sub-module so the runner itself stays thin.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ue_eyes.capture import snap_frame
from ue_eyes.config import UEEyesConfig
from ue_eyes.experiment.results import get_best_score, log_result
from ue_eyes.scoring.compare import create_comparison, create_difference_map
from ue_eyes.scoring.metrics import compute_scores, match_frames
from ue_eyes.scoring.rubric import RubricResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

EXPERIMENTS_DIR: str = "experiments"
CAPTURES_SUBDIR: str = "captures"
COMPARISONS_SUBDIR: str = "comparisons"
RESULT_FILENAME: str = "result.json"
RESULTS_TSV: str = "results.tsv"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ExperimentResult:
    """Holds every piece of data produced by a single experiment run."""

    experiment_id: str
    timestamp: str  # ISO 8601
    params_before: dict | None
    params_after: dict | None
    parameter_changed: str | None
    hypothesis: str
    scores: dict[str, float]  # metric name -> score (0.0-1.0)
    composite_score: float
    rubric_result: RubricResult | None
    verdict: str  # "baseline", "keep", "discard", "failed"
    error: str | None
    notes: str
    capture_dir: Path
    comparison_dir: Path


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class ExperimentRunner:
    """Executes the 6-step experiment pipeline."""

    def __init__(self, config: UEEyesConfig) -> None:
        self.config = config
        self._baseline_dir: Path | None = None

    # -- baseline ----------------------------------------------------------

    def set_baseline(self, reference_dir: Path) -> None:
        """Store the reference capture directory used for comparisons."""
        self._baseline_dir = Path(reference_dir)

    # -- main pipeline -----------------------------------------------------

    def run_experiment(
        self,
        experiment_id: str,
        apply_fn: Callable | None = None,
        params: dict | None = None,
        hypothesis: str = "",
        parameter_changed: str | None = None,
    ) -> ExperimentResult:
        """Run the 6-step experiment pipeline and return the result."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Prepare output directories
        experiment_dir = Path(EXPERIMENTS_DIR) / experiment_id
        capture_dir = experiment_dir / CAPTURES_SUBDIR
        comparison_dir = experiment_dir / COMPARISONS_SUBDIR
        capture_dir.mkdir(parents=True, exist_ok=True)
        comparison_dir.mkdir(parents=True, exist_ok=True)

        results_tsv = Path(EXPERIMENTS_DIR) / RESULTS_TSV

        # ---- 1. APPLY ----
        try:
            self._apply(apply_fn, params)
        except Exception as exc:
            return self._fail(
                experiment_id=experiment_id,
                timestamp=timestamp,
                params=params,
                hypothesis=hypothesis,
                parameter_changed=parameter_changed,
                capture_dir=capture_dir,
                comparison_dir=comparison_dir,
                results_tsv=results_tsv,
                error=f"Apply failed: {exc}",
            )

        # ---- 2. CAPTURE ----
        try:
            width, height = self.config.default_resolution
            snap_frame(
                output_dir=str(capture_dir),
                width=width,
                height=height,
            )
        except Exception as exc:
            return self._fail(
                experiment_id=experiment_id,
                timestamp=timestamp,
                params=params,
                hypothesis=hypothesis,
                parameter_changed=parameter_changed,
                capture_dir=capture_dir,
                comparison_dir=comparison_dir,
                results_tsv=results_tsv,
                error=f"Capture failed: {exc}",
            )

        # ---- 3. COMPARE ----
        if self._baseline_dir is not None:
            pairs = match_frames(str(self._baseline_dir), str(capture_dir))
            for ref_path, cap_path in pairs:
                stem = Path(cap_path).stem
                create_comparison(
                    ref_path=ref_path,
                    render_path=cap_path,
                    output_path=str(comparison_dir / f"{stem}_comparison.png"),
                )
                create_difference_map(
                    ref_path=ref_path,
                    render_path=cap_path,
                    output_path=str(comparison_dir / f"{stem}_diff.png"),
                )

        # ---- 4. SCORE ----
        scores: dict[str, float] = {}
        composite_score: float = 0.0
        if self._baseline_dir is not None:
            pairs = match_frames(str(self._baseline_dir), str(capture_dir))
            if pairs:
                ref_path, cap_path = pairs[0]
                result = compute_scores(
                    reference=Path(ref_path),
                    capture=Path(cap_path),
                    metrics=self.config.metrics,
                    weights=self.config.composite_weights,
                )
                scores = result["scores"]
                composite_score = result["composite"]

        # ---- 5. DECIDE ----
        best = get_best_score(results_tsv)
        if best is None:
            verdict = "baseline"
        else:
            best_composite = best.get("composite_score", 0.0)
            if not isinstance(best_composite, (int, float)):
                best_composite = 0.0
            if composite_score > best_composite:
                verdict = "keep"
            else:
                verdict = "discard"

        # ---- 6. LOG ----
        experiment_result = ExperimentResult(
            experiment_id=experiment_id,
            timestamp=timestamp,
            params_before=None,
            params_after=params,
            parameter_changed=parameter_changed,
            hypothesis=hypothesis,
            scores=scores,
            composite_score=composite_score,
            rubric_result=None,
            verdict=verdict,
            error=None,
            notes="",
            capture_dir=capture_dir,
            comparison_dir=comparison_dir,
        )

        self._log(results_tsv, experiment_result)
        self._write_result_json(experiment_dir, experiment_result)

        return experiment_result

    # -- internal helpers --------------------------------------------------

    @staticmethod
    def _apply(apply_fn: Callable | None, params: dict | None) -> None:
        """Step 1: APPLY changes based on provided arguments."""
        if apply_fn is None:
            # Agent mode — no-op
            return
        if params is not None:
            # Hybrid mode
            apply_fn(params)
        else:
            # Script mode
            apply_fn()

    def _fail(
        self,
        *,
        experiment_id: str,
        timestamp: str,
        params: dict | None,
        hypothesis: str,
        parameter_changed: str | None,
        capture_dir: Path,
        comparison_dir: Path,
        results_tsv: Path,
        error: str,
    ) -> ExperimentResult:
        """Build a failed ExperimentResult, log it, and return it."""
        result = ExperimentResult(
            experiment_id=experiment_id,
            timestamp=timestamp,
            params_before=None,
            params_after=params,
            parameter_changed=parameter_changed,
            hypothesis=hypothesis,
            scores={},
            composite_score=0.0,
            rubric_result=None,
            verdict="failed",
            error=error,
            notes="",
            capture_dir=capture_dir,
            comparison_dir=comparison_dir,
        )
        experiment_dir = capture_dir.parent
        self._log(results_tsv, result)
        self._write_result_json(experiment_dir, result)
        return result

    @staticmethod
    def _log(results_tsv: Path, result: ExperimentResult) -> None:
        """Step 6: LOG — append to results.tsv."""
        row = {
            "experiment": result.experiment_id,
            "timestamp": result.timestamp,
            "parameter": result.parameter_changed or "",
            "old_value": "",
            "new_value": "",
            "hypothesis": result.hypothesis,
            "composite_score": result.composite_score,
            "metric_scores_json": result.scores,
            "verdict": result.verdict,
            "notes": result.notes,
        }
        log_result(results_tsv, row)

    @staticmethod
    def _write_result_json(experiment_dir: Path, result: ExperimentResult) -> None:
        """Write result.json into the experiment directory."""
        experiment_dir.mkdir(parents=True, exist_ok=True)
        out_path = experiment_dir / RESULT_FILENAME

        # Build a JSON-safe dict
        data = asdict(result)
        # Convert Path objects to strings
        data["capture_dir"] = str(result.capture_dir)
        data["comparison_dir"] = str(result.comparison_dir)
        # RubricResult is already a dict from asdict, but may be None
        out_path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
