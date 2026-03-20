"""Scoring metrics for comparing reference and captured frames.

Provides SSIM, pixel MSE, perceptual hash, pluggable custom scorers, and
frame-matching utilities.  All ``score`` functions follow the same interface:
return 0.0-1.0 where 1.0 means a perfect match.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

SSIM_C1: float = (0.01 * 255) ** 2
SSIM_C2: float = (0.03 * 255) ** 2
SSIM_KERNEL_SIZE: int = 11
SSIM_SIGMA: float = 1.5

MAX_PIXEL_VALUE: int = 255

PHASH_SIZE: int = 8
PHASH_BITS: int = 64

IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}

_FRAME_NUM_RE = re.compile(r"(\d+)")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_gray(path: Path) -> np.ndarray:
    """Load an image from *path* as single-channel grayscale uint8."""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return _to_gray(img)


def _to_gray(img: np.ndarray) -> np.ndarray:
    """Convert an image to single-channel grayscale if it isn't already."""
    if img.ndim == 2:
        return img
    if img.ndim == 3 and img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.ndim == 3 and img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    if img.ndim == 3 and img.shape[2] == 1:
        return img[:, :, 0]
    return img


def _resize_to_match(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Resize two grayscale images so their dimensions agree.

    The larger dimension wins on each axis; both images are resized to
    ``(max_h, max_w)`` using area interpolation.
    """
    if a.shape == b.shape:
        return a, b
    h = max(a.shape[0], b.shape[0])
    w = max(a.shape[1], b.shape[1])
    a = cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA)
    b = cv2.resize(b, (w, h), interpolation=cv2.INTER_AREA)
    return a, b


# ---------------------------------------------------------------------------
# SSIM
# ---------------------------------------------------------------------------


def ssim_score(reference: Path, capture: Path) -> float:
    """Structural similarity index.  Return 0.0-1.0 (1.0 = identical).

    Uses an 11x11 Gaussian window (sigma=1.5) with the standard SSIM
    constants C1 and C2.  Both images are converted to grayscale and resized
    to matching dimensions before comparison.
    """
    a = _load_gray(reference)
    b = _load_gray(capture)
    a, b = _resize_to_match(a, b)

    a = a.astype(np.float64)
    b = b.astype(np.float64)

    kernel = cv2.getGaussianKernel(SSIM_KERNEL_SIZE, SSIM_SIGMA)
    window = kernel @ kernel.T

    mu_a = cv2.filter2D(a, -1, window)
    mu_b = cv2.filter2D(b, -1, window)

    mu_a_sq = mu_a ** 2
    mu_b_sq = mu_b ** 2
    mu_ab = mu_a * mu_b

    sigma_a_sq = cv2.filter2D(a ** 2, -1, window) - mu_a_sq
    sigma_b_sq = cv2.filter2D(b ** 2, -1, window) - mu_b_sq
    sigma_ab = cv2.filter2D(a * b, -1, window) - mu_ab

    numerator = (2 * mu_ab + SSIM_C1) * (2 * sigma_ab + SSIM_C2)
    denominator = (mu_a_sq + mu_b_sq + SSIM_C1) * (sigma_a_sq + sigma_b_sq + SSIM_C2)

    ssim_map = numerator / denominator
    value = float(np.mean(ssim_map))
    return float(np.clip(value, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Pixel MSE
# ---------------------------------------------------------------------------


def pixel_mse_score(reference: Path, capture: Path) -> float:
    """1.0 minus normalised mean-squared error.

    Returns 1.0 for identical images, 0.0 for maximum difference (black vs
    white).  Both images are converted to grayscale and resized to match.
    """
    a = _load_gray(reference)
    b = _load_gray(capture)
    a, b = _resize_to_match(a, b)

    a = a.astype(np.float64)
    b = b.astype(np.float64)

    mse = float(np.mean((a - b) ** 2)) / (MAX_PIXEL_VALUE ** 2)
    return 1.0 - mse


# ---------------------------------------------------------------------------
# Perceptual hash (average hash)
# ---------------------------------------------------------------------------


def phash_score(reference: Path, capture: Path) -> float:
    """1.0 minus normalised Hamming distance of average perceptual hashes.

    Each image is resized to 8x8 grayscale, a 64-bit hash is built from
    pixels above the mean, and the normalised Hamming distance gives the
    dissimilarity.
    """
    a = _load_gray(reference)
    b = _load_gray(capture)

    def _ahash(img: np.ndarray) -> np.ndarray:
        small = cv2.resize(img, (PHASH_SIZE, PHASH_SIZE), interpolation=cv2.INTER_AREA)
        mean_val = float(np.mean(small))
        return (small > mean_val).flatten().astype(np.uint8)

    hash_a = _ahash(a)
    hash_b = _ahash(b)

    hamming = int(np.sum(hash_a != hash_b))
    return 1.0 - hamming / PHASH_BITS


# ---------------------------------------------------------------------------
# Scorer registry and loading
# ---------------------------------------------------------------------------

BUILTIN_SCORERS: dict[str, Callable] = {
    "ssim": ssim_score,
    "pixel_mse": pixel_mse_score,
    "phash": phash_score,
}


def load_scorer(name: str) -> Callable:
    """Load a scorer by name.

    Built-in names (``"ssim"``, ``"pixel_mse"``, ``"phash"``) resolve to the
    functions in this module.  Anything containing ``":"`` is treated as
    ``"module.path:function_name"`` and imported dynamically.
    """
    if name in BUILTIN_SCORERS:
        return BUILTIN_SCORERS[name]

    module_path, func_name = name.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)


def compute_scores(
    reference: Path,
    capture: Path,
    metrics: list[str],
    weights: dict[str, float],
) -> dict:
    """Compute all requested metrics and a weighted composite score.

    Returns ``{"scores": {name: value, ...}, "composite": float}``.
    Metrics not present in *weights* default to weight 0.0.
    """
    scores: dict[str, float] = {}
    for name in metrics:
        scorer = load_scorer(name)
        scores[name] = scorer(reference, capture)

    total_weight = sum(weights.get(m, 0.0) for m in metrics)
    if total_weight == 0.0:
        composite = 0.0
    else:
        composite = sum(scores[m] * weights.get(m, 0.0) for m in metrics) / total_weight

    return {"scores": scores, "composite": composite}


# ---------------------------------------------------------------------------
# Frame matching
# ---------------------------------------------------------------------------


def _extract_frame_number(filename: str) -> int | None:
    """Extract the numeric portion from a frame filename.

    Handles ``frame_0001.png``, ``frame_001.png``, ``0001.png``, etc.
    Returns ``None`` if no number is found.
    """
    m = _FRAME_NUM_RE.findall(filename)
    if not m:
        return None
    # Use the last numeric group (handles prefixes like "frame_0001")
    return int(m[-1])


def match_frames(dir_a: str, dir_b: str) -> list[tuple[str, str]]:
    """Match frames between two directories by extracted frame number.

    Handles varied naming conventions (``frame_0001.png``, ``0001.png``,
    etc.) by comparing the integer frame number.  Non-image files are
    ignored.

    Returns a sorted list of ``(path_a, path_b)`` pairs.
    """
    path_a = Path(dir_a)
    path_b = Path(dir_b)

    if not path_a.is_dir() or not path_b.is_dir():
        return []

    def _build_index(directory: Path) -> dict[int, Path]:
        index: dict[int, Path] = {}
        for f in sorted(directory.iterdir()):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                num = _extract_frame_number(f.stem)
                if num is not None:
                    index[num] = f
        return index

    idx_a = _build_index(path_a)
    idx_b = _build_index(path_b)

    common = sorted(set(idx_a.keys()) & set(idx_b.keys()))
    return [(str(idx_a[n]), str(idx_b[n])) for n in common]
