"""Inspect the Hugging Face PlantVillage color dataset without training."""
from datasets import ClassLabel, load_dataset


def main():
    dataset = load_dataset(
        "mohanty/PlantVillage",
        "default",
        trust_remote_code=True,
    )

    print("Dataset splits available:")
    for split_name, split in dataset.items():
        print(f"  {split_name}: {len(split)} examples")

    if "train" not in dataset or "test" not in dataset:
        raise ValueError("Expected the dataset to provide predefined train and test splits.")

    train = dataset["train"]
    test = dataset["test"]
    required_columns = {"image", "label"}
    if not required_columns.issubset(train.column_names):
        raise ValueError(
            f"Expected image and label columns, found {train.column_names!r}. "
            "The dataset script did not load its image dataset."
        )
    label_feature = train.features["label"]
    if not isinstance(label_feature, ClassLabel):
        raise TypeError(f"Expected a ClassLabel 'label' feature, found {label_feature!r}.")

    class_names = label_feature.names
    if len(class_names) != 38:
        raise ValueError(f"Expected 38 PlantVillage classes, found {len(class_names)}.")

    sample = train[0]["image"]
    if not hasattr(sample, "convert") or not hasattr(sample, "size"):
        raise TypeError(f"Expected a decoded PIL image sample, found {type(sample).__name__}.")
    rgb_sample = sample.convert("RGB")

    print(f"Training examples: {len(train)}")
    print(f"Test examples: {len(test)}")
    print(f"Number of classes: {len(class_names)}")
    print("All class names (dataset label order):")
    for index, class_name in enumerate(class_names):
        print(f"  {index}: {class_name}")
    print("Sample image:")
    print(f"  Python type: {type(sample).__name__}")
    print(f"  Original mode: {sample.mode}")
    print(f"  Original dimensions: {sample.width}x{sample.height}")
    print(f"  RGB mode after conversion: {rgb_sample.mode}")
    print(f"  RGB dimensions: {rgb_sample.width}x{rgb_sample.height}")


if __name__ == "__main__":
    main()
