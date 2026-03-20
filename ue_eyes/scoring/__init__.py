"""Scoring sub-package — image comparison metrics, frame matching, and rubrics."""

from ue_eyes.scoring.compare import (
    create_comparison,
    create_comparison_grid,
    create_difference_map,
)
from ue_eyes.scoring.metrics import (
    compute_scores,
    load_scorer,
    match_frames,
    phash_score,
    pixel_mse_score,
    ssim_score,
)
from ue_eyes.scoring.rubric import (
    RubricResult,
    format_rubric_prompt,
    load_rubric,
    parse_rubric_scores,
    save_rubric,
)

__all__ = [
    "RubricResult",
    "compute_scores",
    "create_comparison",
    "create_comparison_grid",
    "create_difference_map",
    "format_rubric_prompt",
    "load_rubric",
    "load_scorer",
    "match_frames",
    "parse_rubric_scores",
    "phash_score",
    "pixel_mse_score",
    "save_rubric",
    "ssim_score",
]
