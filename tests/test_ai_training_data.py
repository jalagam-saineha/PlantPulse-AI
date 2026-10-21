from ai_training_utils import discover_tomato_images, split_records


def test_tomato_discovery_ignores_other_plant_classes(tmp_path):
    tomato = tmp_path / "Tomato___healthy"
    potato = tmp_path / "Potato___healthy"
    tomato.mkdir()
    potato.mkdir()
    (tomato / "leaf.JPG").write_bytes(b"image")
    (potato / "leaf.jpg").write_bytes(b"image")

    labels, records = discover_tomato_images(tmp_path)

    assert labels == ["Tomato___healthy"]
    assert len(records) == 1
    assert records[0][0].endswith("leaf.JPG")


def test_split_is_deterministic_stratified_and_disjoint():
    labels = ["Tomato___early_blight", "Tomato___healthy"]
    records = [
        (f"{label}/{index}.jpg", label_index)
        for label_index, label in enumerate(labels)
        for index in range(20)
    ]

    first = split_records(labels, records, seed=17)
    second = split_records(labels, records, seed=17)

    assert first == second
    train, validation, test = first
    assert [len(group) for group in first] == [28, 6, 6]
    assert not ({path for path, _ in train} & {path for path, _ in validation})
    assert not ({path for path, _ in train} & {path for path, _ in test})
    assert not ({path for path, _ in validation} & {path for path, _ in test})
    for label_index in range(len(labels)):
        assert all(any(record[1] == label_index for record in group) for group in first)
