import cv2
import numpy as np
import pytest

from app.services.image_processor import analyze_leaf_array, analyze_leaf_image
from app.services.health_score import compute_health_score


def _synthetic_leaf(yellow=False, brown=False, spot=False):
    img = np.full((400, 400, 3), (230, 230, 230), dtype=np.uint8)
    cv2.ellipse(img, (200, 200), (150, 110), 0, 0, 360, (40, 150, 40), -1)  # green leaf (BGR)
    if yellow:
        cv2.ellipse(img, (140, 150), (35, 25), 20, 0, 360, (30, 200, 220), -1)
    if brown:
        cv2.ellipse(img, (260, 230), (30, 20), -10, 0, 360, (40, 70, 110), -1)
    if spot:
        cv2.circle(img, (220, 150), 12, (20, 20, 20), -1)
    return img


def test_healthy_leaf_scores_high():
    metrics = analyze_leaf_array(_synthetic_leaf())
    assert metrics["leaf_area_px"] > 0
    assert metrics["leaf_coverage"] > 90
    assert metrics["yellowing"] < 2
    assert metrics["damage"] < 2

    score = compute_health_score(metrics)
    assert score["overall"] >= 85


def test_damaged_leaf_scores_lower_and_measurements_reflect_it():
    metrics = analyze_leaf_array(_synthetic_leaf(yellow=True, brown=True, spot=True))
    assert metrics["yellowing"] > 2
    assert metrics["damage"] > 1
    assert metrics["dark_spots"] > 0

    score = compute_health_score(metrics)
    healthy_score = compute_health_score(analyze_leaf_array(_synthetic_leaf()))
    assert score["overall"] < healthy_score["overall"]


def test_blank_image_raises_no_foliage_error(tmp_path):
    blank = np.full((200, 200, 3), (240, 240, 240), dtype=np.uint8)  # plain background, no leaf
    path = tmp_path / "blank.jpg"
    cv2.imwrite(str(path), blank)
    with pytest.raises(ValueError, match="No foliage"):
        analyze_leaf_image(path, tmp_path / "out")


def test_unreadable_file_raises_value_error(tmp_path):
    path = tmp_path / "not_an_image.jpg"
    path.write_bytes(b"this is not a jpeg")
    with pytest.raises(ValueError, match="Could not read"):
        analyze_leaf_image(path, tmp_path / "out")


def test_analyze_leaf_image_writes_processed_and_overlay_files(tmp_path):
    src = tmp_path / "leaf.jpg"
    cv2.imwrite(str(src), _synthetic_leaf(yellow=True))
    out_dir = tmp_path / "out"
    metrics, processed_name, overlay_name = analyze_leaf_image(src, out_dir)
    assert (out_dir / processed_name).exists()
    assert (out_dir / overlay_name).exists()
    assert metrics["leaf_coverage"] > 0


def test_health_score_components_are_weighted_and_bounded():
    score = compute_health_score({"leaf_coverage": 100, "yellowing": 0, "damage": 0, "dark_spots": 0})
    assert score["overall"] == 100.0
    score_zero = compute_health_score({"leaf_coverage": 0, "yellowing": 100, "damage": 100, "dark_spots": 100})
    assert 0 <= score_zero["overall"] < 10
