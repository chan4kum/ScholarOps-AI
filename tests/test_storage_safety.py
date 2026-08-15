from pathlib import Path

import pytest

from opportunity_intel.config import Settings
from opportunity_intel.documents.storage import stored_file_path


def test_stored_file_path_rejects_traversal(tmp_path: Path) -> None:
    settings = Settings(uploads_dir=tmp_path / "uploads")
    settings.uploads_dir.mkdir()
    ok = stored_file_path(settings, "abc123.pdf")
    assert ok.parent == settings.uploads_dir.resolve()
    with pytest.raises(ValueError):
        stored_file_path(settings, "../secret.txt")
    with pytest.raises(ValueError):
        stored_file_path(settings, "")
