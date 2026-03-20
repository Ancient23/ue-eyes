"""Agent rubric system for qualitative scoring.

Provides rubric loading/saving, prompt formatting for agent-based evaluation,
and parsing of agent scoring responses into structured results.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RubricResult:
    """Structured result from agent-based rubric scoring."""

    per_criterion: dict[str, float]  # criterion name -> score (0-10)
    composite: float  # weighted composite
    reasoning: dict[str, str]  # criterion name -> agent's reasoning


# ---------------------------------------------------------------------------
# Rubric I/O
# ---------------------------------------------------------------------------


def load_rubric(path: Path) -> dict:
    """Load rubric definition from a JSON file.

    Returns the parsed dictionary with keys like ``name``, ``criteria``,
    ``goal_score``, and ``scale``.
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_rubric(rubric: dict, path: Path) -> None:
    """Save rubric definition to a JSON file.

    Creates parent directories if they don't exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rubric, f, indent=2)


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def format_rubric_prompt(
    rubric: dict,
    capture_paths: list[Path],
    reference_paths: list[Path] | None = None,
) -> str:
    """Build a structured prompt for the agent to score each criterion.

    The prompt includes the rubric name, each criterion with its weight and
    description, image paths, and response format instructions.
    """
    lines: list[str] = []

    rubric_name = rubric.get("name", "Unnamed Rubric")
    lines.append(f"## Scoring Rubric: {rubric_name}")
    lines.append("")
    lines.append("Score each criterion on a 0-10 scale.")
    lines.append("")

    for criterion in rubric.get("criteria", []):
        name = criterion["name"]
        weight = criterion["weight"]
        description = criterion["description"]
        lines.append(f"### {name} (weight: {weight})")
        lines.append(description)
        lines.append("")

    lines.append("## Images to evaluate")
    for p in capture_paths:
        lines.append(f"- Capture: {p.as_posix()}")
    if reference_paths:
        for p in reference_paths:
            lines.append(f"- Reference: {p.as_posix()}")
    lines.append("")

    lines.append("For each criterion, respond with:")
    lines.append("criterion_name: <score> \u2014 <reasoning>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

# Matches lines like:
#   shadow_direction: 7.5 — Shadows are mostly consistent
#   shadow_direction: 7.5 - Shadows are mostly consistent
#   shadow_direction: 7 — Shadows are mostly consistent
_SCORE_LINE_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(\d+(?:\.\d+)?)\s*[\u2014\-]\s*(.*?)\s*$"
)


def parse_rubric_scores(agent_response: str, rubric: dict) -> RubricResult:
    """Parse the agent's scoring response into a structured RubricResult.

    Handles:
    - Score as int or float
    - Reasoning after em dash or hyphen
    - Missing criteria (partial response)
    - Extra commentary lines (ignored)
    - Case-insensitive criterion name matching
    """
    # Build a lookup from lowercase criterion name to canonical name + weight
    criteria_lookup: dict[str, tuple[str, float]] = {}
    for criterion in rubric.get("criteria", []):
        canonical = criterion["name"]
        criteria_lookup[canonical.lower()] = (canonical, criterion["weight"])

    per_criterion: dict[str, float] = {}
    reasoning: dict[str, str] = {}

    for line in agent_response.splitlines():
        m = _SCORE_LINE_RE.match(line)
        if not m:
            continue
        raw_name = m.group(1)
        score = float(m.group(2))
        reason = m.group(3)

        # Case-insensitive lookup
        entry = criteria_lookup.get(raw_name.lower())
        if entry is None:
            continue
        canonical_name, _weight = entry
        per_criterion[canonical_name] = score
        reasoning[canonical_name] = reason

    # Compute weighted composite from matched criteria
    total_weight = 0.0
    weighted_sum = 0.0
    for criterion in rubric.get("criteria", []):
        canonical = criterion["name"]
        if canonical in per_criterion:
            w = criterion["weight"]
            weighted_sum += per_criterion[canonical] * w
            total_weight += w

    composite = weighted_sum / total_weight if total_weight > 0.0 else 0.0

    return RubricResult(
        per_criterion=per_criterion,
        composite=composite,
        reasoning=reasoning,
    )
