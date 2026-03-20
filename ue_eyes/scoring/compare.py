"""Side-by-side comparison image generator.

Creates visual comparison images (side-by-side, grid, difference heatmap)
for evaluating rendered frames against reference frames.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ue_eyes.scoring.metrics import match_frames

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

LABEL_HEIGHT: int = 40  # pixels for label bar
SEPARATOR_WIDTH: int = 2  # pixels for vertical separator
LABEL_FONT_SCALE: float = 0.9
LABEL_THICKNESS: int = 2
LABEL_COLOR: tuple[int, int, int] = (255, 255, 255)
SEPARATOR_COLOR: tuple[int, int, int] = (200, 200, 200)
GRID_ROW_HEIGHT: int = 200
MAX_GRID_FRAMES: int = 12


# ---------------------------------------------------------------------------
# Single-pair comparison
# ---------------------------------------------------------------------------


def create_comparison(
    ref_path: str,
    render_path: str,
    output_path: str,
    label_ref: str = "Reference",
    label_render: str = "Render",
) -> None:
    """Create a side-by-side comparison image with labels.

    The render image is resized to match the reference height (maintaining
    aspect ratio).  A vertical separator line is drawn between the two
    halves and text labels are placed at the top.
    """
    ref = cv2.imread(str(ref_path), cv2.IMREAD_COLOR)
    render = cv2.imread(str(render_path), cv2.IMREAD_COLOR)
    if ref is None:
        raise FileNotFoundError(f"Cannot read reference image: {ref_path}")
    if render is None:
        raise FileNotFoundError(f"Cannot read render image: {render_path}")

    ref_h, ref_w = ref.shape[:2]
    render_h, render_w = render.shape[:2]

    # Resize render to match reference height, maintaining aspect ratio
    if render_h != ref_h:
        scale = ref_h / render_h
        new_w = int(render_w * scale)
        render = cv2.resize(render, (new_w, ref_h), interpolation=cv2.INTER_AREA)

    # Leave room for a label bar at the top
    canvas_h = ref_h + LABEL_HEIGHT
    canvas_w = ref.shape[1] + render.shape[1] + SEPARATOR_WIDTH

    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)

    # Place images below label bar
    canvas[LABEL_HEIGHT: LABEL_HEIGHT + ref_h, : ref.shape[1]] = ref
    sep_x = ref.shape[1]
    canvas[LABEL_HEIGHT: LABEL_HEIGHT + ref_h, sep_x + SEPARATOR_WIDTH:] = render

    # Draw vertical separator
    cv2.line(canvas, (sep_x, 0), (sep_x, canvas_h), SEPARATOR_COLOR, SEPARATOR_WIDTH)

    # Draw labels
    font = cv2.FONT_HERSHEY_SIMPLEX

    # Center label text above each image
    ref_text_size = cv2.getTextSize(label_ref, font, LABEL_FONT_SCALE, LABEL_THICKNESS)[0]
    ref_text_x = (ref.shape[1] - ref_text_size[0]) // 2
    cv2.putText(canvas, label_ref, (max(ref_text_x, 5), 28),
                font, LABEL_FONT_SCALE, LABEL_COLOR, LABEL_THICKNESS, cv2.LINE_AA)

    render_text_size = cv2.getTextSize(label_render, font, LABEL_FONT_SCALE, LABEL_THICKNESS)[0]
    render_text_x = sep_x + SEPARATOR_WIDTH + (render.shape[1] - render_text_size[0]) // 2
    cv2.putText(canvas, label_render, (max(render_text_x, sep_x + 5), 28),
                font, LABEL_FONT_SCALE, LABEL_COLOR, LABEL_THICKNESS, cv2.LINE_AA)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), canvas)


# ---------------------------------------------------------------------------
# Grid comparison
# ---------------------------------------------------------------------------


def create_comparison_grid(
    ref_dir: str,
    render_dir: str,
    output_path: str,
    max_frames: int = MAX_GRID_FRAMES,
) -> None:
    """Create a grid of comparison images (ref|render pairs stacked vertically).

    Matches frames by extracted numeric index, then creates a row per pair
    (reference on left, render on right) and stacks all rows.
    """
    pairs = match_frames(ref_dir, render_dir)
    if not pairs:
        # Create a small placeholder image indicating no matches
        placeholder = np.zeros((100, 400, 3), dtype=np.uint8)
        cv2.putText(placeholder, "No matching frames found", (20, 55),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), placeholder)
        return

    pairs = pairs[:max_frames]

    # Build rows at a uniform width
    rows: list[np.ndarray] = []

    for ref_path, render_path in pairs:
        ref = cv2.imread(str(ref_path), cv2.IMREAD_COLOR)
        render = cv2.imread(str(render_path), cv2.IMREAD_COLOR)
        if ref is None or render is None:
            continue

        # Resize both to GRID_ROW_HEIGHT, keeping aspect ratio
        ref = _resize_to_height(ref, GRID_ROW_HEIGHT)
        render = _resize_to_height(render, GRID_ROW_HEIGHT)

        # Concatenate horizontally with a separator
        sep = np.full((GRID_ROW_HEIGHT, SEPARATOR_WIDTH, 3), SEPARATOR_COLOR[0], dtype=np.uint8)
        row = np.concatenate([ref, sep, render], axis=1)
        rows.append(row)

    if not rows:
        return

    # Pad all rows to the same width
    max_w = max(r.shape[1] for r in rows)
    padded: list[np.ndarray] = []
    for row in rows:
        if row.shape[1] < max_w:
            pad = np.zeros((row.shape[0], max_w - row.shape[1], 3), dtype=np.uint8)
            row = np.concatenate([row, pad], axis=1)
        padded.append(row)

    # Add 1px horizontal separator between rows
    result_parts: list[np.ndarray] = []
    for i, row in enumerate(padded):
        if i > 0:
            hsep = np.full((1, max_w, 3), 100, dtype=np.uint8)
            result_parts.append(hsep)
        result_parts.append(row)

    grid = np.concatenate(result_parts, axis=0)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), grid)


# ---------------------------------------------------------------------------
# Difference heatmap
# ---------------------------------------------------------------------------


def create_difference_map(
    ref_path: str,
    render_path: str,
    output_path: str,
) -> None:
    """Create a heatmap showing pixel differences between two frames.

    Converts both images to grayscale, computes absolute difference,
    and applies the JET colourmap so areas of high difference appear hot.
    """
    ref = cv2.imread(str(ref_path), cv2.IMREAD_COLOR)
    render = cv2.imread(str(render_path), cv2.IMREAD_COLOR)
    if ref is None:
        raise FileNotFoundError(f"Cannot read reference image: {ref_path}")
    if render is None:
        raise FileNotFoundError(f"Cannot read render image: {render_path}")

    ref_h, ref_w = ref.shape[:2]
    render_h, render_w = render.shape[:2]

    # Resize render to match reference dimensions
    if (render_h, render_w) != (ref_h, ref_w):
        render = cv2.resize(render, (ref_w, ref_h), interpolation=cv2.INTER_AREA)

    gray_ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    gray_render = cv2.cvtColor(render, cv2.COLOR_BGR2GRAY)

    diff = cv2.absdiff(gray_ref, gray_render)
    heatmap = cv2.applyColorMap(diff, cv2.COLORMAP_JET)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), heatmap)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resize_to_height(img: np.ndarray, target_h: int) -> np.ndarray:
    """Resize image to a target height, maintaining aspect ratio."""
    h, w = img.shape[:2]
    if h == target_h:
        return img
    scale = target_h / h
    new_w = max(int(w * scale), 1)
    return cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_AREA)
