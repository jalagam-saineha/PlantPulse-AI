"""
Real OpenCV-based leaf analysis pipeline.

Segments the leaf from the background using HSV thresholding, classifies
foliage pixels into green / yellow / brown-damage / dark-spot categories,
and renders two output images: a segmentation view ("processed") and a
color-coded health map ("overlay"). All percentages are computed from the
actual pixel counts of the uploaded image — nothing here is fabricated.
"""
import uuid
from pathlib import Path

import cv2
import numpy as np

PROCESS_MAX_DIM = 900

# BGR colors used to render the health map, matching the on-screen legend.
_COLOR_GREEN = (87, 167, 71)     # healthy foliage
_COLOR_YELLOW = (39, 199, 236)   # yellowing
_COLOR_BROWN = (46, 73, 142)     # visible damage
_COLOR_SPOT = (150, 66, 138)     # dark spots


def _resize_max(img: np.ndarray, max_dim: int = PROCESS_MAX_DIM) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min(1.0, max_dim / float(max(h, w)))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def analyze_leaf_array(img: np.ndarray) -> dict:
    """
    Same pipeline as analyze_leaf_image() but operates on an in-memory BGR
    array and returns only the measurements (no image files written).
    Used by both single-image Leaf Analysis and per-frame Growth Studio
    processing so the two features share one measurement algorithm.
    """
    img = _resize_max(img)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    green_mask = (h >= 32) & (h <= 85) & (s >= 40) & (v >= 40)
    yellow_mask = (h >= 18) & (h < 32) & (s >= 40) & (v >= 40)
    brown_mask = (h >= 5) & (h < 18) & (s >= 30) & (v >= 25) & (v < 200)
    dark_spot_mask = v < 55

    leaf_mask_raw = ((green_mask | yellow_mask | brown_mask | dark_spot_mask) * 255).astype(np.uint8)
    kernel = np.ones((5, 5), np.uint8)
    leaf_mask_clean = cv2.morphologyEx(leaf_mask_raw, cv2.MORPH_OPEN, kernel)
    leaf_mask_clean = cv2.morphologyEx(leaf_mask_clean, cv2.MORPH_CLOSE, kernel)
    leaf_bool = leaf_mask_clean > 0

    leaf_area_px = int(np.count_nonzero(leaf_bool))
    if leaf_area_px == 0:
        return {
            "leaf_area_px": 0, "leaf_coverage": 0.0, "yellowing": 0.0,
            "damage": 0.0, "dark_spots": 0.0, "affected_area": 0.0,
        }

    spot_bool = dark_spot_mask & leaf_bool
    brown_bool = brown_mask & leaf_bool & ~spot_bool
    yellow_bool = yellow_mask & leaf_bool & ~spot_bool & ~brown_bool
    green_bool = green_mask & leaf_bool & ~spot_bool & ~brown_bool & ~yellow_bool

    def pct(mask_bool: np.ndarray) -> float:
        return round(100.0 * np.count_nonzero(mask_bool) / leaf_area_px, 2)

    green_pct = pct(green_bool)
    yellow_pct = pct(yellow_bool)
    brown_pct = pct(brown_bool)
    spot_pct = pct(spot_bool)
    affected_pct = round(min(100.0, yellow_pct + brown_pct + spot_pct), 2)

    return {
        "leaf_area_px": leaf_area_px,
        "leaf_coverage": green_pct,
        "yellowing": yellow_pct,
        "damage": brown_pct,
        "dark_spots": spot_pct,
        "affected_area": affected_pct,
    }


def analyze_leaf_image(source_path: Path, processed_dir: Path) -> tuple[dict, str, str]:
    """
    Runs the full pipeline on the image at source_path.
    Returns (metrics_dict, processed_filename, overlay_filename).
    Raises ValueError with a user-facing message on bad/unreadable images
    or when no foliage can be detected.
    """
    img = cv2.imread(str(source_path))
    if img is None:
        raise ValueError(
            "Could not read the uploaded image. It may be corrupted or in an unsupported format."
        )

    img = _resize_max(img)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    green_mask = (h >= 32) & (h <= 85) & (s >= 40) & (v >= 40)
    yellow_mask = (h >= 18) & (h < 32) & (s >= 40) & (v >= 40)
    brown_mask = (h >= 5) & (h < 18) & (s >= 30) & (v >= 25) & (v < 200)
    dark_spot_mask = v < 55

    leaf_mask_raw = ((green_mask | yellow_mask | brown_mask | dark_spot_mask) * 255).astype(np.uint8)
    kernel = np.ones((5, 5), np.uint8)
    leaf_mask_clean = cv2.morphologyEx(leaf_mask_raw, cv2.MORPH_OPEN, kernel)
    leaf_mask_clean = cv2.morphologyEx(leaf_mask_clean, cv2.MORPH_CLOSE, kernel)
    leaf_bool = leaf_mask_clean > 0

    leaf_area_px = int(np.count_nonzero(leaf_bool))
    if leaf_area_px == 0:
        raise ValueError(
            "No foliage could be detected in this image. Try a clearer, closer photo of the leaf "
            "against a plain background."
        )

    # Categories are made mutually exclusive (priority: spot > brown > yellow > green)
    # so percentages add up cleanly against the measured leaf area.
    spot_bool = dark_spot_mask & leaf_bool
    brown_bool = brown_mask & leaf_bool & ~spot_bool
    yellow_bool = yellow_mask & leaf_bool & ~spot_bool & ~brown_bool
    green_bool = green_mask & leaf_bool & ~spot_bool & ~brown_bool & ~yellow_bool

    def pct(mask_bool: np.ndarray) -> float:
        return round(100.0 * np.count_nonzero(mask_bool) / leaf_area_px, 2)

    green_pct = pct(green_bool)
    yellow_pct = pct(yellow_bool)
    brown_pct = pct(brown_bool)
    spot_pct = pct(spot_bool)
    affected_pct = round(min(100.0, yellow_pct + brown_pct + spot_pct), 2)

    metrics = {
        "leaf_area_px": leaf_area_px,
        "leaf_coverage": green_pct,
        "yellowing": yellow_pct,
        "damage": brown_pct,
        "dark_spots": spot_pct,
        "affected_area": affected_pct,
    }

    # --- "Processed" image: segmentation view (background dimmed) ---
    processed = img.copy()
    bg_bool = ~leaf_bool
    processed[bg_bool] = (processed[bg_bool] * 0.25).astype(np.uint8)

    # --- "Overlay" image: color-coded visual health map ---
    overlay_color = np.zeros_like(img)
    overlay_color[green_bool] = _COLOR_GREEN
    overlay_color[yellow_bool] = _COLOR_YELLOW
    overlay_color[brown_bool] = _COLOR_BROWN
    overlay_color[spot_bool] = _COLOR_SPOT
    blended_full = cv2.addWeighted(img, 0.35, overlay_color, 0.65, 0)
    overlay = img.copy()
    overlay[leaf_bool] = blended_full[leaf_bool]
    overlay[bg_bool] = (overlay[bg_bool] * 0.35).astype(np.uint8)

    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_name = f"{uuid.uuid4().hex}_processed.jpg"
    overlay_name = f"{uuid.uuid4().hex}_overlay.jpg"
    cv2.imwrite(str(processed_dir / processed_name), processed, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    cv2.imwrite(str(processed_dir / overlay_name), overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 90])

    return metrics, processed_name, overlay_name
