"""TSV-based experiment results tracking for ue-eyes.

Stores one row per experiment run in a ``results.tsv`` file, providing
functions to initialise, append, load, and query results.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

RESULTS_HEADER: list[str] = [
    "experiment",
    "timestamp",
    "parameter",
    "old_value",
    "new_value",
    "hypothesis",
    "composite_score",
    "metric_scores_json",
    "verdict",
    "notes",
]

# Columns that should be converted to float when loading.
_NUMERIC_COLUMNS: set[str] = {"composite_score"}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_results(results_path: Path) -> None:
    """Create results.tsv with header if it does not exist. Idempotent."""
    results_path = Path(results_path)
    if results_path.exists():
        return
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(RESULTS_HEADER)


def log_result(results_path: Path, result: dict) -> None:
    """Append a result row. Initializes file first if needed.

    *result* should have keys matching :data:`RESULTS_HEADER`.
    The ``metric_scores_json`` value is auto-serialized to a JSON string if
    it is a dict (or list).
    """
    results_path = Path(results_path)
    init_results(results_path)

    # Auto-serialize metric_scores_json if it is not already a string.
    metric_scores = result.get("metric_scores_json", "")
    if isinstance(metric_scores, (dict, list)):
        metric_scores = json.dumps(metric_scores, separators=(",", ":"))

    row = [
        str(result.get(col, "")) if col != "metric_scores_json" else metric_scores
        for col in RESULTS_HEADER
    ]

    with results_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(row)


def load_results(results_path: Path) -> list[dict]:
    """Load all rows as list of dicts.

    Converts numeric fields to float and parses ``metric_scores_json`` back
    to a dict.  Returns an empty list if the file does not exist or contains
    only the header.
    """
    results_path = Path(results_path)
    if not results_path.exists():
        return []

    with results_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows: list[dict] = []
        for row in reader:
            # Convert numeric columns.
            for col in _NUMERIC_COLUMNS:
                val = row.get(col, "")
                if val:
                    try:
                        row[col] = float(val)
                    except ValueError:
                        pass

            # Parse metric_scores_json.
            msj = row.get("metric_scores_json", "")
            if msj:
                try:
                    row["metric_scores_json"] = json.loads(msj)
                except (json.JSONDecodeError, TypeError):
                    pass

            rows.append(row)
    return rows


def get_best_score(results_path: Path) -> dict | None:
    """Return the row with the highest ``composite_score``, or None."""
    rows = load_results(results_path)
    if not rows:
        return None

    best: dict | None = None
    best_score = -float("inf")
    for row in rows:
        score = row.get("composite_score")
        if isinstance(score, (int, float)) and score > best_score:
            best_score = score
            best = row
    return best


def get_score_trend(results_path: Path, last_n: int = 10) -> list[float]:
    """Return last *last_n* ``composite_score`` values for trend analysis.

    Scores that are missing or non-numeric are skipped.
    """
    rows = load_results(results_path)
    scores: list[float] = []
    for row in rows:
        s = row.get("composite_score")
        if isinstance(s, (int, float)):
            scores.append(float(s))
    return scores[-last_n:]
