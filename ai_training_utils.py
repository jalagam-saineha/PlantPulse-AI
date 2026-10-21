"""Shared PlantVillage discovery, validation, and deterministic split helpers."""
import random
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
TOMATO_PREFIX = "Tomato___"
IMAGE_SIZE = (224, 224)
EXPECTED_CLASS_COUNT = 38


def _discover_images(
    dataset_dir: Path,
    class_prefix: str | None,
    expected_class_count: int | None,
    validate_images: bool,
) -> tuple[list[str], list[tuple[str, int]], list[str]]:
    dataset_dir = Path(dataset_dir)
    if not dataset_dir.is_dir():
        raise FileNotFoundError(
            f"PlantVillage directory does not exist: {dataset_dir}. "
            "Pass an extracted dataset directory containing class folders."
        )

    class_dirs = sorted(
        (
            path for path in dataset_dir.iterdir()
            if path.is_dir() and (class_prefix is None or path.name.startswith(class_prefix))
        ),
        key=lambda path: path.name,
    )
    if not class_dirs:
        description = f"{class_prefix}* class folders" if class_prefix else "class folders"
        raise ValueError(f"No {description} found directly under {dataset_dir}.")
    if expected_class_count is not None and len(class_dirs) != expected_class_count:
        raise ValueError(
            f"Expected exactly {expected_class_count} class folders under {dataset_dir}, "
            f"found {len(class_dirs)}: {[path.name for path in class_dirs]}"
        )

    labels = [path.name for path in class_dirs]
    records: list[tuple[str, int]] = []
    corrupted_paths: list[str] = []
    for label_index, class_dir in enumerate(class_dirs):
        image_paths = sorted(
            (
                path for path in class_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            ),
            key=lambda path: path.as_posix(),
        )
        if not image_paths:
            raise ValueError(f"No supported images found in class folder {class_dir}.")
        for path in image_paths:
            resolved_path = str(path.resolve())
            records.append((resolved_path, label_index))
            if validate_images and not _is_readable_image(path):
                corrupted_paths.append(resolved_path)
    return labels, records, corrupted_paths


def _is_readable_image(image_path: Path) -> bool:
    """Check both image structure and pixel decoding before training uses a file."""
    from PIL import Image

    try:
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            image.load()
    except (OSError, SyntaxError, ValueError):
        return False
    return True


def discover_plantvillage_images(
    dataset_dir: Path,
) -> tuple[list[str], list[tuple[str, int]], list[str]]:
    """Return sorted classes, image records, and paths that fail image decoding."""
    return _discover_images(
        dataset_dir,
        class_prefix=None,
        expected_class_count=EXPECTED_CLASS_COUNT,
        validate_images=True,
    )


def discover_tomato_images(dataset_dir: Path) -> tuple[list[str], list[tuple[str, int]]]:
    """Return sorted tomato classes and records (legacy helper retained for callers)."""
    labels, records, _ = _discover_images(
        dataset_dir,
        class_prefix=TOMATO_PREFIX,
        expected_class_count=None,
        validate_images=False,
    )
    return labels, records


def report_dataset_verification(
    dataset_dir: Path,
    labels: list[str],
    records: list[tuple[str, int]],
    corrupted_paths: list[str],
) -> None:
    """Print class/image counts and the paths of any unreadable image files."""
    counts = [0] * len(labels)
    for _, label_index in records:
        counts[label_index] += 1

    print(f"Dataset path: {Path(dataset_dir).resolve()}")
    print(f"Number of classes: {len(labels)}")
    print("Class names:")
    for label, image_count in zip(labels, counts):
        print(f"  {label}: {image_count} images")
    print(f"Total image count: {len(records)}")
    print(f"Corrupted image count: {len(corrupted_paths)}")
    for image_path in corrupted_paths:
        print(f"  Unreadable: {image_path}")


def split_records(
    labels: list[str],
    records: list[tuple[str, int]],
    seed: int = 42,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> tuple[list[tuple[str, int]], list[tuple[str, int]], list[tuple[str, int]]]:
    """Create a deterministic, stratified split; remainder is assigned to test."""
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("Train and validation fractions must be between 0 and 1.")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Train and validation fractions must sum to less than 1.")

    grouped = [[] for _ in labels]
    for record in records:
        path, label_index = record
        if label_index < 0 or label_index >= len(labels):
            raise ValueError(f"Image {path} has an invalid class index {label_index}.")
        grouped[label_index].append(record)

    train_records, validation_records, test_records = [], [], []
    rng = random.Random(seed)
    for label, class_records in zip(labels, grouped):
        if len(class_records) < 3:
            raise ValueError(
                f"Class {label!r} has {len(class_records)} image(s); "
                "at least 3 are required for train/validation/test splits."
            )
        class_records = sorted(class_records, key=lambda record: record[0])
        rng.shuffle(class_records)
        train_count = max(1, int(len(class_records) * train_fraction))
        validation_count = max(1, int(len(class_records) * validation_fraction))
        if train_count + validation_count >= len(class_records):
            train_count = len(class_records) - 2
            validation_count = 1
        train_records.extend(class_records[:train_count])
        validation_records.extend(class_records[train_count:train_count + validation_count])
        test_records.extend(class_records[train_count + validation_count:])

    return train_records, validation_records, test_records


def make_dataset(tf, records, class_count: int, batch_size: int, shuffle: bool, seed: int):
    """Decode RGB images as float32 [0, 1], matching disease_predictor.predict()."""
    paths = [record[0] for record in records]
    labels = [record[1] for record in records]
    dataset = tf.data.Dataset.from_tensor_slices((paths, labels))
    if shuffle:
        dataset = dataset.shuffle(
            buffer_size=len(records), seed=seed, reshuffle_each_iteration=True
        )

    def load_image(path, label):
        def pillow_rgb_resize(path_value):
            import numpy as np
            from PIL import Image

            image_path = path_value.decode("utf-8")
            with Image.open(image_path) as image:
                return np.asarray(
                    image.convert("RGB").resize(IMAGE_SIZE),
                    dtype=np.uint8,
                )

        image = tf.numpy_function(pillow_rgb_resize, [path], Tout=tf.uint8)
        image.set_shape((*IMAGE_SIZE, 3))
        image = tf.cast(image, tf.float32) / 255.0
        return image, tf.one_hot(label, class_count)

    dataset = dataset.map(load_image, num_parallel_calls=tf.data.AUTOTUNE, deterministic=True)
    options = tf.data.Options()
    options.deterministic = True
    return dataset.batch(batch_size).prefetch(tf.data.AUTOTUNE).with_options(options)
