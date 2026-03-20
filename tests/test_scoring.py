"""Tests for ue_eyes.scoring — SSIM, pixel MSE, perceptual hash, rubrics, and utilities."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from ue_eyes.scoring import (
    RubricResult,
    compute_scores,
    create_comparison,
    create_comparison_grid,
    create_difference_map,
    format_rubric_prompt,
    load_rubric,
    load_scorer,
    match_frames,
    parse_rubric_scores,
    phash_score,
    pixel_mse_score,
    save_rubric,
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


# ===========================================================================
# Comparison visualization tests
# ===========================================================================


# ---------------------------------------------------------------------------
# 20. create_comparison — creates file
# ---------------------------------------------------------------------------


def test_create_comparison_creates_file(tmp_path: Path) -> None:
    """create_comparison writes an output PNG."""
    ref = tmp_path / "ref.png"
    render = tmp_path / "render.png"
    out = tmp_path / "out" / "comparison.png"
    _make_image(ref, width=80, height=60, color=(100, 100, 100))
    _make_image(render, width=80, height=60, color=(200, 200, 200))
    create_comparison(str(ref), str(render), str(out))
    assert out.exists()


# ---------------------------------------------------------------------------
# 21. create_comparison — wider than inputs
# ---------------------------------------------------------------------------


def test_create_comparison_wider_than_inputs(tmp_path: Path) -> None:
    """Output width should be larger than either input (ref + render + separator)."""
    ref = tmp_path / "ref.png"
    render = tmp_path / "render.png"
    out = tmp_path / "comparison.png"
    _make_image(ref, width=80, height=60, color=(100, 100, 100))
    _make_image(render, width=80, height=60, color=(200, 200, 200))
    create_comparison(str(ref), str(render), str(out))
    result = cv2.imread(str(out), cv2.IMREAD_COLOR)
    assert result is not None
    result_w = result.shape[1]
    assert result_w > 80


# ---------------------------------------------------------------------------
# 22. create_comparison — has label height
# ---------------------------------------------------------------------------


def test_create_comparison_has_label_height(tmp_path: Path) -> None:
    """Output height should exceed the reference height (label bar added)."""
    ref = tmp_path / "ref.png"
    render = tmp_path / "render.png"
    out = tmp_path / "comparison.png"
    ref_h = 60
    _make_image(ref, width=80, height=ref_h, color=(100, 100, 100))
    _make_image(render, width=80, height=ref_h, color=(200, 200, 200))
    create_comparison(str(ref), str(render), str(out))
    result = cv2.imread(str(out), cv2.IMREAD_COLOR)
    assert result is not None
    assert result.shape[0] > ref_h


# ---------------------------------------------------------------------------
# 23. create_difference_map — creates file
# ---------------------------------------------------------------------------


def test_create_difference_map_creates_file(tmp_path: Path) -> None:
    """create_difference_map writes an output PNG."""
    ref = tmp_path / "ref.png"
    render = tmp_path / "render.png"
    out = tmp_path / "diff.png"
    _make_image(ref, width=64, height=64, color=(100, 100, 100))
    _make_image(render, width=64, height=64, color=(200, 200, 200))
    create_difference_map(str(ref), str(render), str(out))
    assert out.exists()


# ---------------------------------------------------------------------------
# 24. create_difference_map — identical images produce low-variance heatmap
# ---------------------------------------------------------------------------


def test_create_difference_map_identical_is_uniform(tmp_path: Path) -> None:
    """Identical images should produce a uniform (low-variance) heatmap."""
    ref = tmp_path / "ref.png"
    out = tmp_path / "diff.png"
    _make_image(ref, width=64, height=64, color=(128, 128, 128))
    create_difference_map(str(ref), str(ref), str(out))
    result = cv2.imread(str(out), cv2.IMREAD_COLOR)
    assert result is not None
    # All diff pixels are 0 -> same JET mapping -> very low variance
    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    assert float(np.var(gray)) < 1.0


# ---------------------------------------------------------------------------
# 25. create_comparison_grid — creates file
# ---------------------------------------------------------------------------


def test_create_comparison_grid_creates_file(tmp_path: Path) -> None:
    """create_comparison_grid writes an output PNG."""
    ref_dir = tmp_path / "ref"
    render_dir = tmp_path / "render"
    ref_dir.mkdir()
    render_dir.mkdir()
    for i in range(3):
        _make_image(ref_dir / f"frame_{i:03d}.png", width=80, height=60)
        _make_image(render_dir / f"frame_{i:03d}.png", width=80, height=60)
    out = tmp_path / "grid.png"
    create_comparison_grid(str(ref_dir), str(render_dir), str(out))
    assert out.exists()


# ---------------------------------------------------------------------------
# 26. create_comparison_grid — respects max_frames
# ---------------------------------------------------------------------------


def test_create_comparison_grid_respects_max_frames(tmp_path: Path) -> None:
    """Grid should contain at most max_frames rows of pairs."""
    ref_dir = tmp_path / "ref"
    render_dir = tmp_path / "render"
    ref_dir.mkdir()
    render_dir.mkdir()
    for i in range(10):
        _make_image(ref_dir / f"frame_{i:03d}.png", width=80, height=60)
        _make_image(render_dir / f"frame_{i:03d}.png", width=80, height=60)
    out = tmp_path / "grid.png"
    max_frames = 3
    create_comparison_grid(str(ref_dir), str(render_dir), str(out), max_frames=max_frames)
    result = cv2.imread(str(out), cv2.IMREAD_COLOR)
    assert result is not None
    # Each row is GRID_ROW_HEIGHT (200) pixels + 1px separator between rows
    # max_frames rows => height = max_frames * 200 + (max_frames - 1) * 1
    from ue_eyes.scoring.compare import GRID_ROW_HEIGHT
    expected_height = max_frames * GRID_ROW_HEIGHT + (max_frames - 1) * 1
    assert result.shape[0] == expected_height


# ---------------------------------------------------------------------------
# 27. create_comparison_grid — no matches produces placeholder
# ---------------------------------------------------------------------------


def test_create_comparison_grid_no_matches(tmp_path: Path) -> None:
    """When no frames match, a placeholder image is created."""
    ref_dir = tmp_path / "ref"
    render_dir = tmp_path / "render"
    ref_dir.mkdir()
    render_dir.mkdir()
    _make_image(ref_dir / "frame_001.png")
    _make_image(render_dir / "frame_999.png")
    out = tmp_path / "grid.png"
    create_comparison_grid(str(ref_dir), str(render_dir), str(out))
    assert out.exists()
    result = cv2.imread(str(out), cv2.IMREAD_COLOR)
    assert result is not None
    # Placeholder is 100x400
    assert result.shape[0] == 100
    assert result.shape[1] == 400


# ===========================================================================
# Rubric tests
# ===========================================================================

SAMPLE_RUBRIC: dict = {
    "name": "Lighting Quality",
    "criteria": [
        {
            "name": "shadow_direction",
            "weight": 0.3,
            "description": "Shadows should fall consistently from the key light",
        },
        {
            "name": "ambient_balance",
            "weight": 0.3,
            "description": "Dark areas should have subtle fill, not pure black",
        },
        {
            "name": "highlight_rolloff",
            "weight": 0.4,
            "description": "Bright areas should have smooth gradients",
        },
    ],
    "goal_score": 8.0,
    "scale": "0-10",
}


# ---------------------------------------------------------------------------
# 28. RubricResult dataclass — construction + access
# ---------------------------------------------------------------------------


def test_rubric_result_dataclass() -> None:
    """RubricResult can be constructed and its fields accessed."""
    result = RubricResult(
        per_criterion={"shadow_direction": 7.5, "ambient_balance": 8.0},
        composite=7.75,
        reasoning={
            "shadow_direction": "Good shadows",
            "ambient_balance": "Nice balance",
        },
    )
    assert result.per_criterion["shadow_direction"] == 7.5
    assert result.composite == 7.75
    assert "Good shadows" in result.reasoning["shadow_direction"]


# ---------------------------------------------------------------------------
# 29. load_rubric — reads JSON, returns dict with correct keys
# ---------------------------------------------------------------------------


def test_load_rubric(tmp_path: Path) -> None:
    """load_rubric reads a JSON file and returns a dict with correct keys."""
    rubric_file = tmp_path / "rubric.json"
    rubric_file.write_text(json.dumps(SAMPLE_RUBRIC), encoding="utf-8")

    loaded = load_rubric(rubric_file)
    assert loaded["name"] == "Lighting Quality"
    assert len(loaded["criteria"]) == 3
    assert loaded["goal_score"] == 8.0
    assert loaded["scale"] == "0-10"


# ---------------------------------------------------------------------------
# 30. save_rubric — writes JSON, re-load matches
# ---------------------------------------------------------------------------


def test_save_rubric(tmp_path: Path) -> None:
    """save_rubric writes JSON that can be re-loaded identically."""
    rubric_file = tmp_path / "subdir" / "rubric.json"
    save_rubric(SAMPLE_RUBRIC, rubric_file)
    assert rubric_file.exists()

    loaded = load_rubric(rubric_file)
    assert loaded == SAMPLE_RUBRIC


# ---------------------------------------------------------------------------
# 31. format_rubric_prompt — includes all criteria names and descriptions
# ---------------------------------------------------------------------------


def test_format_rubric_prompt_includes_criteria() -> None:
    """Prompt contains every criterion name and description."""
    prompt = format_rubric_prompt(
        SAMPLE_RUBRIC,
        capture_paths=[Path("/captures/frame_001.png")],
    )
    for criterion in SAMPLE_RUBRIC["criteria"]:
        assert criterion["name"] in prompt
        assert criterion["description"] in prompt


# ---------------------------------------------------------------------------
# 32. format_rubric_prompt — includes image paths
# ---------------------------------------------------------------------------


def test_format_rubric_prompt_includes_images() -> None:
    """Prompt lists capture and reference paths."""
    captures = [Path("/captures/c1.png")]
    references = [Path("/refs/r1.png")]
    prompt = format_rubric_prompt(SAMPLE_RUBRIC, captures, references)
    assert "/captures/c1.png" in prompt
    assert "/refs/r1.png" in prompt
    assert "Capture:" in prompt
    assert "Reference:" in prompt


# ---------------------------------------------------------------------------
# 33. format_rubric_prompt — works without reference_paths
# ---------------------------------------------------------------------------


def test_format_rubric_prompt_no_references() -> None:
    """Prompt works when reference_paths is None."""
    prompt = format_rubric_prompt(
        SAMPLE_RUBRIC,
        capture_paths=[Path("/captures/c1.png")],
        reference_paths=None,
    )
    assert "/captures/c1.png" in prompt
    assert "Reference:" not in prompt


# ---------------------------------------------------------------------------
# 34. parse_rubric_scores — basic well-formed response
# ---------------------------------------------------------------------------


def test_parse_rubric_scores_basic() -> None:
    """Parses a well-formed response with all criteria scored."""
    response = (
        "shadow_direction: 7.5 \u2014 Mostly consistent\n"
        "ambient_balance: 8.0 \u2014 Good fill\n"
        "highlight_rolloff: 6.0 \u2014 Some clipping\n"
    )
    result = parse_rubric_scores(response, SAMPLE_RUBRIC)
    assert result.per_criterion["shadow_direction"] == 7.5
    assert result.per_criterion["ambient_balance"] == 8.0
    assert result.per_criterion["highlight_rolloff"] == 6.0


# ---------------------------------------------------------------------------
# 35. parse_rubric_scores — reasoning captured correctly
# ---------------------------------------------------------------------------


def test_parse_rubric_scores_with_reasoning() -> None:
    """Reasoning text is captured for each criterion."""
    response = (
        "shadow_direction: 7.5 \u2014 Shadows are mostly consistent but slightly off\n"
        "ambient_balance: 8.0 \u2014 Good fill light, no pure black areas\n"
        "highlight_rolloff: 6.0 \u2014 Some harsh clipping on the metallic surfaces\n"
    )
    result = parse_rubric_scores(response, SAMPLE_RUBRIC)
    assert "mostly consistent" in result.reasoning["shadow_direction"]
    assert "fill light" in result.reasoning["ambient_balance"]
    assert "clipping" in result.reasoning["highlight_rolloff"]


# ---------------------------------------------------------------------------
# 36. parse_rubric_scores — missing criteria
# ---------------------------------------------------------------------------


def test_parse_rubric_scores_missing_criteria() -> None:
    """Partial response only includes criteria that were scored."""
    response = "shadow_direction: 7.5 \u2014 Mostly consistent\n"
    result = parse_rubric_scores(response, SAMPLE_RUBRIC)
    assert "shadow_direction" in result.per_criterion
    assert "ambient_balance" not in result.per_criterion
    assert "highlight_rolloff" not in result.per_criterion
    assert len(result.per_criterion) == 1


# ---------------------------------------------------------------------------
# 37. parse_rubric_scores — extra lines ignored
# ---------------------------------------------------------------------------


def test_parse_rubric_scores_extra_lines_ignored() -> None:
    """Extra commentary lines don't break parsing."""
    response = (
        "Here is my evaluation:\n"
        "\n"
        "shadow_direction: 7.5 \u2014 Mostly consistent\n"
        "ambient_balance: 8.0 \u2014 Good fill\n"
        "highlight_rolloff: 6.0 \u2014 Some clipping\n"
        "\n"
        "Overall, the lighting is decent.\n"
    )
    result = parse_rubric_scores(response, SAMPLE_RUBRIC)
    assert len(result.per_criterion) == 3


# ---------------------------------------------------------------------------
# 38. parse_rubric_scores — composite calculation
# ---------------------------------------------------------------------------


def test_parse_rubric_scores_composite_calculation() -> None:
    """Weighted composite is correctly computed from per-criterion scores."""
    response = (
        "shadow_direction: 7.5 \u2014 Mostly consistent\n"
        "ambient_balance: 8.0 \u2014 Good fill\n"
        "highlight_rolloff: 6.0 \u2014 Some clipping\n"
    )
    result = parse_rubric_scores(response, SAMPLE_RUBRIC)
    # weights: shadow=0.3, ambient=0.3, highlight=0.4
    expected = (7.5 * 0.3 + 8.0 * 0.3 + 6.0 * 0.4) / (0.3 + 0.3 + 0.4)
    assert result.composite == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# 39. parse_rubric_scores — case insensitive
# ---------------------------------------------------------------------------


def test_parse_rubric_scores_case_insensitive() -> None:
    """'Shadow_Direction' matches 'shadow_direction' criterion."""
    response = "Shadow_Direction: 7.5 \u2014 Mostly consistent\n"
    result = parse_rubric_scores(response, SAMPLE_RUBRIC)
    assert "shadow_direction" in result.per_criterion
    assert result.per_criterion["shadow_direction"] == 7.5


# ---------------------------------------------------------------------------
# 40. parse_rubric_scores — hyphen separator
# ---------------------------------------------------------------------------


def test_parse_rubric_scores_hyphen_separator() -> None:
    """Uses '-' (hyphen) instead of em dash as separator."""
    response = (
        "shadow_direction: 7.5 - Mostly consistent\n"
        "ambient_balance: 8.0 - Good fill\n"
        "highlight_rolloff: 6 - Some clipping\n"
    )
    result = parse_rubric_scores(response, SAMPLE_RUBRIC)
    assert len(result.per_criterion) == 3
    assert result.per_criterion["highlight_rolloff"] == 6.0
    assert "Mostly consistent" in result.reasoning["shadow_direction"]
