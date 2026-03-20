"""Tests for ue_eyes.scoring — SSIM, pixel MSE, perceptual hash, and utilities."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from ue_eyes.scoring import (
    compute_scores,
    load_scorer,
    match_frames,
    phash_score,
    pixel_mse_score,
    ssim_score,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_image(
    path: Path,
    width: int = 64,
    height: int = 64,
    color: tuple[int, int, int] = (128, 128, 128),
) -> None:
    """Write a solid-colour BGR image to *path*."""
    img = np.full((height, width, 3), color, dtype=np.uint8)
    cv2.imwrite(str(path), img)


# ---------------------------------------------------------------------------
# 1. SSIM — identical images
# ---------------------------------------------------------------------------


def test_ssim_identical_images(tmp_path: Path) -> None:
    """SSIM of an image with itself should be 1.0."""
    ref = tmp_path / "ref.png"
    _make_image(ref)
    assert ssim_score(ref, ref) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 2. SSIM — different images
# ---------------------------------------------------------------------------


def test_ssim_different_images(tmp_path: Path) -> None:
    """SSIM of two different images should be < 1.0."""
    ref = tmp_path / "ref.png"
    cap = tmp_path / "cap.png"
    _make_image(ref, color=(100, 100, 100))
    _make_image(cap, color=(200, 200, 200))
    assert ssim_score(ref, cap) < 1.0


# ---------------------------------------------------------------------------
# 3. SSIM — completely different (black vs white)
# ---------------------------------------------------------------------------


def test_ssim_completely_different(tmp_path: Path) -> None:
    """Black vs white should yield a low SSIM score."""
    ref = tmp_path / "black.png"
    cap = tmp_path / "white.png"
    _make_image(ref, color=(0, 0, 0))
    _make_image(cap, color=(255, 255, 255))
    score = ssim_score(ref, cap)
    assert score < 0.1


# ---------------------------------------------------------------------------
# 4. SSIM — size mismatch
# ---------------------------------------------------------------------------


def test_ssim_handles_size_mismatch(tmp_path: Path) -> None:
    """SSIM gracefully handles images of different dimensions."""
    ref = tmp_path / "small.png"
    cap = tmp_path / "big.png"
    _make_image(ref, width=32, height=32, color=(128, 128, 128))
    _make_image(cap, width=64, height=64, color=(128, 128, 128))
    score = ssim_score(ref, cap)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# 5. Pixel MSE — identical
# ---------------------------------------------------------------------------


def test_pixel_mse_identical(tmp_path: Path) -> None:
    """Identical images yield MSE score of 1.0."""
    ref = tmp_path / "ref.png"
    _make_image(ref)
    assert pixel_mse_score(ref, ref) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 6. Pixel MSE — max difference
# ---------------------------------------------------------------------------


def test_pixel_mse_max_difference(tmp_path: Path) -> None:
    """Black vs white yields a score close to 0.0."""
    ref = tmp_path / "black.png"
    cap = tmp_path / "white.png"
    _make_image(ref, color=(0, 0, 0))
    _make_image(cap, color=(255, 255, 255))
    score = pixel_mse_score(ref, cap)
    assert score == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 7. Pixel MSE — partial difference
# ---------------------------------------------------------------------------


def test_pixel_mse_partial_difference(tmp_path: Path) -> None:
    """Moderately different images yield a score between 0 and 1."""
    ref = tmp_path / "a.png"
    cap = tmp_path / "b.png"
    _make_image(ref, color=(50, 50, 50))
    _make_image(cap, color=(200, 200, 200))
    score = pixel_mse_score(ref, cap)
    assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# 8. Perceptual hash — identical
# ---------------------------------------------------------------------------


def test_phash_identical(tmp_path: Path) -> None:
    """Identical images yield phash score of 1.0."""
    ref = tmp_path / "ref.png"
    _make_image(ref)
    assert phash_score(ref, ref) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 9. Perceptual hash — different
# ---------------------------------------------------------------------------


def test_phash_different(tmp_path: Path) -> None:
    """Clearly different images yield phash score < 1.0."""
    ref = tmp_path / "a.png"
    cap = tmp_path / "b.png"
    # Use patterned images so the average-hash bits actually differ.
    # A gradient vs its inverse will have opposite hash bits.
    img_a = np.zeros((64, 64, 3), dtype=np.uint8)
    img_a[:32, :, :] = 255  # top half white, bottom half black
    cv2.imwrite(str(ref), img_a)
    img_b = np.zeros((64, 64, 3), dtype=np.uint8)
    img_b[32:, :, :] = 255  # bottom half white, top half black
    cv2.imwrite(str(cap), img_b)
    score = phash_score(ref, cap)
    assert score < 1.0


# ---------------------------------------------------------------------------
# 10. Perceptual hash — similar images
# ---------------------------------------------------------------------------


def test_phash_similar_images(tmp_path: Path) -> None:
    """Slightly different images should still score high."""
    ref = tmp_path / "a.png"
    cap = tmp_path / "b.png"
    _make_image(ref, color=(120, 120, 120))
    _make_image(cap, color=(130, 130, 130))
    score = phash_score(ref, cap)
    assert score > 0.8


# ---------------------------------------------------------------------------
# 11. load_scorer — built-in
# ---------------------------------------------------------------------------


def test_load_scorer_builtin() -> None:
    """load_scorer('ssim') returns the ssim_score function."""
    assert load_scorer("ssim") is ssim_score


# ---------------------------------------------------------------------------
# 12. load_scorer — custom module:function
# ---------------------------------------------------------------------------


def test_load_scorer_custom() -> None:
    """load_scorer('module:func') imports and returns the function."""
    scorer = load_scorer("ue_eyes.scoring.metrics:ssim_score")
    assert scorer is ssim_score


# ---------------------------------------------------------------------------
# 13. load_scorer — invalid module
# ---------------------------------------------------------------------------


def test_load_scorer_invalid() -> None:
    """Bad module path raises ImportError."""
    with pytest.raises((ImportError, ModuleNotFoundError)):
        load_scorer("nonexistent.module:func")


# ---------------------------------------------------------------------------
# 14. compute_scores — single metric
# ---------------------------------------------------------------------------


def test_compute_scores_single_metric(tmp_path: Path) -> None:
    """Compute scores with a single metric returns correct composite."""
    ref = tmp_path / "ref.png"
    _make_image(ref)
    result = compute_scores(ref, ref, metrics=["ssim"], weights={"ssim": 1.0})
    assert "scores" in result
    assert "composite" in result
    assert result["scores"]["ssim"] == pytest.approx(1.0, abs=1e-6)
    assert result["composite"] == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 15. compute_scores — weighted composite
# ---------------------------------------------------------------------------


def test_compute_scores_weighted(tmp_path: Path) -> None:
    """Weights correctly affect composite score."""
    ref = tmp_path / "ref.png"
    cap = tmp_path / "cap.png"
    _make_image(ref, color=(0, 0, 0))
    _make_image(cap, color=(255, 255, 255))

    result = compute_scores(
        ref,
        cap,
        metrics=["pixel_mse", "phash"],
        weights={"pixel_mse": 0.5, "phash": 0.5},
    )

    # Both metrics should be low for black-vs-white.  Composite = weighted avg.
    expected_composite = (
        result["scores"]["pixel_mse"] * 0.5
        + result["scores"]["phash"] * 0.5
    )
    assert result["composite"] == pytest.approx(expected_composite, abs=1e-6)


# ---------------------------------------------------------------------------
# 16. match_frames — basic matching by number
# ---------------------------------------------------------------------------


def test_match_frames_by_number(tmp_path: Path) -> None:
    """frame_001.png in both dirs matches by frame number."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    _make_image(dir_a / "frame_001.png")
    _make_image(dir_b / "frame_001.png")

    pairs = match_frames(str(dir_a), str(dir_b))
    assert len(pairs) == 1
    assert Path(pairs[0][0]).name == "frame_001.png"
    assert Path(pairs[0][1]).name == "frame_001.png"


# ---------------------------------------------------------------------------
# 17. match_frames — varied naming
# ---------------------------------------------------------------------------


def test_match_frames_varied_naming(tmp_path: Path) -> None:
    """frame_0001.png matches 0001.png (same frame number)."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    _make_image(dir_a / "frame_0001.png")
    _make_image(dir_b / "0001.png")

    pairs = match_frames(str(dir_a), str(dir_b))
    assert len(pairs) == 1


# ---------------------------------------------------------------------------
# 18. match_frames — no matches
# ---------------------------------------------------------------------------


def test_match_frames_no_matches(tmp_path: Path) -> None:
    """Directories with no overlapping frame numbers return empty list."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    _make_image(dir_a / "frame_001.png")
    _make_image(dir_b / "frame_999.png")

    pairs = match_frames(str(dir_a), str(dir_b))
    assert pairs == []


# ---------------------------------------------------------------------------
# 19. match_frames — non-image files ignored
# ---------------------------------------------------------------------------


def test_match_frames_non_image_ignored(tmp_path: Path) -> None:
    """.txt files are not treated as frames."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "frame_001.txt").write_text("not an image")
    (dir_b / "frame_001.txt").write_text("not an image")

    pairs = match_frames(str(dir_a), str(dir_b))
    assert pairs == []
