from app.services.disease_predictor import get_model_status, get_species_mismatch, predict


def test_status_reports_not_ready_when_files_missing(tmp_path):
    status = get_model_status(tmp_path)
    assert status["files_present"] is False
    assert status["ready"] is False


def test_predict_returns_none_when_not_ready(tmp_path):
    assert predict(tmp_path / "nonexistent.jpg", tmp_path) is None


def test_status_reports_invalid_labels(tmp_path):
    (tmp_path / "plant_disease_model.keras").write_bytes(b"not a real model")
    (tmp_path / "labels.json").write_text("not valid json {{{")
    status = get_model_status(tmp_path)
    assert status["labels_valid"] is False
    assert status["ready"] is False


def test_species_mismatch_flags_known_different_species(tmp_path):
    (tmp_path / "labels.json").write_text(
        '["Apple___Apple_scab", "Tomato___Septoria_leaf_spot"]',
        encoding="utf-8",
    )

    assert get_species_mismatch("Apple", "Tomato___Septoria_leaf_spot", tmp_path) == "Tomato"
    assert get_species_mismatch("Apple", "Apple___Apple_scab", tmp_path) is None


def test_species_mismatch_ignores_missing_or_unknown_species(tmp_path):
    (tmp_path / "labels.json").write_text(
        '["Apple___Apple_scab", "Tomato___Septoria_leaf_spot"]',
        encoding="utf-8",
    )

    assert get_species_mismatch(None, "Tomato___Septoria_leaf_spot", tmp_path) is None
    assert get_species_mismatch("", "Tomato___Septoria_leaf_spot", tmp_path) is None
    assert get_species_mismatch("Unknown plant", "Tomato___Septoria_leaf_spot", tmp_path) is None
