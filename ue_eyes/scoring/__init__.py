"""Scoring sub-package — image comparison metrics and frame matching."""

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

__all__ = [
    "compute_scores",
    "create_comparison",
    "create_comparison_grid",
    "create_difference_map",
    "load_scorer",
    "match_frames",
    "phash_score",
    "pixel_mse_score",
    "ssim_score",
]
