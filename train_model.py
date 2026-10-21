"""Train the optional PlantVillage disease classifier."""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")

from ai_training_utils import (  # noqa: E402
    IMAGE_SIZE,
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
        help="Extracted PlantVillage color directory containing 38 class folders "
        "(default: PLANTVILLAGE_DIR or the local PlantVillage path).",
    )
    parser.add_argument(
        "--verify-dataset", action="store_true",
        help="Verify class folders and image readability, then exit without training.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    return parser.parse_args()


def _build_model(tf, class_count: int, learning_rate: float):
    keras = tf.keras
    augmentation = keras.Sequential(
        [
            keras.layers.RandomFlip("horizontal"),
            keras.layers.RandomRotation(0.08),
            keras.layers.RandomZoom(0.10),
            keras.layers.RandomContrast(0.10),
        ],
        name="training_augmentation",
    )
    backbone = keras.applications.MobileNetV2(
        input_shape=(*IMAGE_SIZE, 3),
        include_top=False,
        weights="imagenet",
        pooling="avg",
    )
    backbone.trainable = False

    inputs = keras.Input(shape=(*IMAGE_SIZE, 3), name="rgb_image_0_to_1")
    augmented = augmentation(inputs)
    mobilenet_input = keras.layers.Rescaling(
        scale=2.0, offset=-1.0, name="mobilenetv2_input_scaling"
    )(augmented)
    features = backbone(mobilenet_input, training=False)
    outputs = keras.layers.Dense(class_count, activation="softmax", name="class_probabilities")(features)
    model = keras.Model(inputs, outputs, name="plantpulse_tomato_mobilenetv2")
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def _compute_class_weights(
    records: list[tuple[str, int]],
    class_count: int,
) -> dict[int, float]:
    """Compute balanced class weights from the training records only."""
    if class_count < 1:
        raise ValueError("Class count must be positive.")

    counts = [0] * class_count
    for image_path, class_index in records:
        if class_index < 0 or class_index >= class_count:
            raise ValueError(f"Image {image_path} has an invalid class index {class_index}.")
        counts[class_index] += 1

    if not records or any(count == 0 for count in counts):
        raise ValueError("Every class must have training images to compute class weights.")

    sample_count = len(records)
    return {
        class_index: sample_count / (class_count * count)
        for class_index, count in enumerate(counts)
    }


def _write_plots(history, output_dir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    epochs = range(1, len(history.history["accuracy"]) + 1)
    for metric, title, filename in (
        ("accuracy", "Training and validation accuracy", "accuracy.png"),
        ("loss", "Training and validation loss", "loss.png"),
    ):
        figure, axis = plt.subplots(figsize=(8, 5))
        axis.plot(epochs, history.history[metric], label="Training")
        axis.plot(epochs, history.history[f"val_{metric}"], label="Validation")
        axis.set(title=title, xlabel="Epoch", ylabel=metric.capitalize())
        axis.legend()
        axis.grid(True, alpha=0.3)
        figure.tight_layout()
        figure.savefig(output_dir / filename, dpi=150)
        plt.close(figure)


def main():
    args = _arguments()
    if args.epochs < 1 or args.batch_size < 1 or args.learning_rate <= 0:
        raise ValueError("Epochs, batch size, and learning rate must be positive.")

    labels, records, corrupted_paths = discover_plantvillage_images(args.dataset_dir)
    report_dataset_verification(args.dataset_dir, labels, records, corrupted_paths)
    if args.verify_dataset:
        return
    if corrupted_paths:
        raise ValueError(
            f"Training aborted: {len(corrupted_paths)} unreadable image(s) were found."
        )

    import tensorflow as tf

    tf.keras.utils.set_random_seed(args.seed)
    tf.config.experimental.enable_op_determinism()

    train_records, validation_records, test_records = split_records(
        labels, records, seed=args.seed
    )
    class_weights = _compute_class_weights(train_records, len(labels))
    train_data = make_dataset(
        tf, train_records, len(labels), args.batch_size, shuffle=True, seed=args.seed
    )
    validation_data = make_dataset(
        tf, validation_records, len(labels), args.batch_size, shuffle=False, seed=args.seed
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path = RESULTS_DIR / "best_model.keras"
    model = _build_model(tf, len(labels), args.learning_rate)
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=5, restore_best_weights=True, verbose=1
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(checkpoint_path),
            monitor="val_loss",
            save_best_only=True,
            verbose=1,
        ),
    ]
    history = model.fit(
        train_data,
        validation_data=validation_data,
        epochs=args.epochs,
        callbacks=callbacks,
        class_weight=class_weights,
    )

    model.save(MODEL_PATH)
    LABELS_PATH.write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")
    _write_plots(history, RESULTS_DIR)
    (RESULTS_DIR / "training_summary.json").write_text(
        json.dumps(
            {
                "seed": args.seed,
                "dataset_dir": str(Path(args.dataset_dir).resolve()),
                "class_names": labels,
                "image_size": list(IMAGE_SIZE),
                "input_contract": "RGB float32 in [0, 1]; model rescales to [-1, 1] for MobileNetV2",
                "split_counts": {
                    "train": len(train_records),
                    "validation": len(validation_records),
                    "test": len(test_records),
                },
                "epochs_completed": len(history.history["accuracy"]),
                "best_validation_loss": min(history.history["val_loss"]),
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"Saved model: {MODEL_PATH}")
    print(f"Saved ordered labels: {LABELS_PATH}")
    print(f"Saved training plots and summary: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
