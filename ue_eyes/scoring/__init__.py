"""Scoring sub-package — image comparison metrics and frame matching."""

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
    "load_scorer",
    "match_frames",
    "phash_score",
    "pixel_mse_score",
    "ssim_score",
]
