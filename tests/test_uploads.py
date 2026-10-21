import io

import pytest
from werkzeug.datastructures import FileStorage

from app.utils.uploads import validate_and_save, UploadError


def _file(name, content=b"hello world"):
    return FileStorage(stream=io.BytesIO(content), filename=name)


def test_rejects_disallowed_extension(tmp_path):
    with pytest.raises(UploadError, match="Unsupported file type"):
        validate_and_save(_file("leaf.txt"), tmp_path, {"jpg", "png"}, 1024)


def test_rejects_empty_file(tmp_path):
    with pytest.raises(UploadError, match="empty"):
        validate_and_save(_file("leaf.jpg", b""), tmp_path, {"jpg"}, 1024)


def test_rejects_oversized_file(tmp_path):
    with pytest.raises(UploadError, match="maximum size"):
        validate_and_save(_file("leaf.jpg", b"x" * 2000), tmp_path, {"jpg"}, 1000)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(UploadError, match="No file"):
        validate_and_save(None, tmp_path, {"jpg"}, 1024)


def test_saves_valid_file_with_random_name(tmp_path):
    name = validate_and_save(_file("leaf.jpg", b"x" * 50), tmp_path, {"jpg"}, 1024)
    assert name.endswith(".jpg")
    assert (tmp_path / name).exists()
    assert name != "leaf.jpg"  # renamed to a safe random name
