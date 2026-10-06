"""File storage for generated media.

Single-host deployment: a directory on a Docker volume shared by the API and the worker.
Keys are relative POSIX paths such as ``jobs/<job_id>/video.mp4``.
"""

from pathlib import Path


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path_for(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"storage key escapes root: {key!r}")
        return path

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def is_writable(self) -> bool:
        probe = self.root / ".write-probe"
        try:
            self.ensure_root()
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            return False
        return True
