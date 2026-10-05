from pathlib import Path

import pytest

from vidgen.storage import LocalStorage


def test_path_for_stays_inside_root(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    assert storage.path_for("jobs/1/video.mp4") == tmp_path.resolve() / "jobs/1/video.mp4"
    with pytest.raises(ValueError):
        storage.path_for("../escape.txt")


def test_is_writable(tmp_path: Path) -> None:
    assert LocalStorage(tmp_path / "new").is_writable()
