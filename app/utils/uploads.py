"""
Shared file-upload helpers: extension/size validation and safe saving.
Used by Plant image upload (Phase 2), Leaf Analysis (Phase 3), and
Growth Studio video upload (Phase 5).
"""
import os
import uuid
from pathlib import Path

from werkzeug.utils import secure_filename


class UploadError(ValueError):
    pass


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_and_save(file_storage, dest_dir: Path, allowed_extensions: set, max_bytes: int) -> str:
    """
    Validates a Flask-uploaded file (extension + size) and saves it under
    dest_dir with a random, collision-proof, path-traversal-safe filename.
    Returns the filename (not the full path) that was written.
    """
    if not file_storage or not file_storage.filename:
        raise UploadError("No file was selected.")

    original_name = secure_filename(file_storage.filename)
    ext = _ext(original_name)
    if ext not in allowed_extensions:
        raise UploadError(
            f"Unsupported file type '.{ext}'. Allowed: {', '.join(sorted(allowed_extensions))}."
        )

    # Determine actual size without loading the whole file into memory.
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size <= 0:
        raise UploadError("The uploaded file is empty.")
    if size > max_bytes:
        raise UploadError(f"File exceeds the maximum size of {max_bytes // (1024 * 1024)} MB.")

    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    dest_path = dest_dir / safe_name

    # Guard against any path-traversal shenanigans even though uuid4 can't
    # produce one; resolve() + is_relative_to keeps this defensive.
    resolved = dest_path.resolve()
    if not str(resolved).startswith(str(dest_dir.resolve())):
        raise UploadError("Invalid upload destination.")

    file_storage.save(str(dest_path))
    return safe_name
