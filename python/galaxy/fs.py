"""Writing files so a reader, or a crash, never sees half of one: the data
is written beside the target and renamed over it, so the file is either the
old one or the new one, whole."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Union

# For a file that did not exist yet. Reading the umask means setting it, which
# is not thread-safe, and an editor may write from a thread pool.
NEW_FILE_MODE = 0o644


def write_atomic(path: Union[str, Path], data: Union[str, bytes]) -> None:
    """Write *data* (text as UTF-8) to *path* through a temporary file in the
    same directory, flushed to disk before the rename. An existing file keeps
    its permissions; the parent directory is created if missing."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    mode = target.stat().st_mode & 0o777 if target.exists() else NEW_FILE_MODE
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
