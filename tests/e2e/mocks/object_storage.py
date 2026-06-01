"""Mock object storage for E2E tests."""
import os
import tempfile
import logging

logger = logging.getLogger(__name__)

_temp_dir: str | None = None
_stored_files: dict[str, str] = {}


def get_mock_storage_dir() -> str:
    global _temp_dir
    if not _temp_dir:
        _temp_dir = tempfile.mkdtemp(prefix="geo_e2e_storage_")
    return _temp_dir


def store_file(key: str, content: bytes) -> str:
    """Mock: write file to temp dir instead of cloud storage."""
    d = get_mock_storage_dir()
    path = os.path.join(d, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    _stored_files[key] = path
    return path


def get_file(key: str) -> bytes | None:
    path = _stored_files.get(key)
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None


def delete_file(key: str) -> bool:
    path = _stored_files.pop(key, None)
    if path and os.path.exists(path):
        os.remove(path)
        return True
    return False


def clear_storage():
    global _stored_files
    _stored_files.clear()
    if _temp_dir and os.path.exists(_temp_dir):
        import shutil
        shutil.rmtree(_temp_dir, ignore_errors=True)
