"""Evaluate the trained PlantVillage classifier on its held-out test split."""
import argparse
import csv
import json
import os
from pathlib import Path

os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")

from ai_training_utils import (  # noqa: E402
    discover_plantvillage_images,
    make_dataset,
    report_dataset_verification,
    split_records,
)

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_DIR = Path(
    os.environ.get(
        "PLANTVILLAGE_DIR",
        r"D:\PlantVillage\PlantVillage-Dataset-master\raw\color",
    )
)
MODEL_PATH = PROJECT_DIR / "models" / "plant_disease_model.keras"
LABELS_PATH = PROJECT_DIR / "models" / "labels.json"
RESULTS_DIR = PROJECT_DIR / "training_results"


def _arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR,
        help="Same extracted PlantVillage directory used for training.",
    )
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


def _write_confusion_matrix(matrix, labels, output_path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from sklearn.metrics import ConfusionMatrixDisplay

    figure, axis = plt.subplots(figsize=(max(9, len(labels) * 0.8), max(8, len(labels) * 0.7)))
    display = ConfusionMatrixDisplay(confusion_matrix=np.asarray(matrix), display_labels=labels)
    display.plot(ax=axis, xticks_rotation=90, cmap="Blues", colorbar=False, values_format="d")
    axis.set_title("PlantVillage test-set confusion matrix")
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def main():
    args = _arguments()
    if args.batch_size < 1:
        raise ValueError("Batch size must be positive.")
    if not args.model.is_file():
        raise FileNotFoundError(f"Trained model not found: {args.model}. Run train_model.py first.")
    if not args.labels.is_file():
        raise FileNotFoundError(f"Ordered labels file not found: {args.labels}. Run train_model.py first.")

    import numpy as np
    import tensorflow as tf
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

    tf.keras.utils.set_random_seed(args.seed)
    tf.config.experimental.enable_op_determinism()

    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if not isinstance(labels, list) or not labels or not all(isinstance(label, str) for label in labels):
        raise ValueError(f"Labels file must contain a non-empty JSON array of strings: {args.labels}")

    dataset_labels, records, corrupted_paths = discover_plantvillage_images(args.dataset_dir)
    report_dataset_verification(args.dataset_dir, dataset_labels, records, corrupted_paths)
    if corrupted_paths:
        raise ValueError(
            f"Evaluation aborted: {len(corrupted_paths)} unreadable image(s) were found."
        )
    if dataset_labels != labels:
        raise ValueError(
            "PlantVillage classes do not match the ordered labels saved with this model. "
            "Use the same dataset class folders as training."
        )
    _, _, test_records = split_records(labels, records, seed=args.seed)
    if not test_records:
        raise ValueError("The deterministic test split is empty.")
    test_data = make_dataset(
        tf, test_records, len(labels), args.batch_size, shuffle=False, seed=args.seed
    )

    model = tf.keras.models.load_model(args.model)
    if model.output_shape[-1] != len(labels):
        raise ValueError(
            f"Model has {model.output_shape[-1]} outputs but labels.json has {len(labels)} classes."
        )
    test_loss, test_accuracy = model.evaluate(test_data, verbose=1)
    probabilities = model.predict(test_data, verbose=1)
    y_true = np.asarray([label_index for _, label_index in test_records], dtype=np.int64)
    y_pred = np.argmax(probabilities, axis=1)
    class_ids = list(range(len(labels)))
    matrix = confusion_matrix(y_true, y_pred, labels=class_ids)
    report = classification_report(
        y_true,
        y_pred,
        labels=class_ids,
        target_names=labels,
        output_dict=True,
        zero_division=0,
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_confusion_matrix(matrix, labels, RESULTS_DIR / "confusion_matrix.png")
    (RESULTS_DIR / "classification_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    with (RESULTS_DIR / "per_class_metrics.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(("class", "precision", "recall", "f1_score", "support"))
        for label in labels:
            row = report[label]
            writer.writerow((label, row["precision"], row["recall"], row["f1-score"], row["support"]))

    results = {
        "dataset_dir": str(Path(args.dataset_dir).resolve()),
        "model_path": str(args.model.resolve()),
        "labels_path": str(args.labels.resolve()),
        "seed": args.seed,
        "test_sample_count": len(test_records),
        "test_loss": float(test_loss),
        "test_accuracy": float(test_accuracy),
        "accuracy_from_predictions": float(accuracy_score(y_true, y_pred)),
        "class_names": labels,
        "confusion_matrix": matrix.tolist(),
        "per_class": {
            label: {
                "precision": float(report[label]["precision"]),
                "recall": float(report[label]["recall"]),
                "f1_score": float(report[label]["f1-score"]),
                "support": int(report[label]["support"]),
            }
            for label in labels
        },
        "macro_average": report["macro avg"],
        "weighted_average": report["weighted avg"],
    }
    (RESULTS_DIR / "evaluation_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Test accuracy: {test_accuracy:.4f}")
    print(f"Test loss: {test_loss:.4f}")
    print(f"Saved evaluation outputs: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
