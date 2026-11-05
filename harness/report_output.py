"""Reserve a writable report sink before paid work, then publish it atomically."""

from __future__ import annotations

import errno
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def prepared_report(target: Path | None) -> Iterator[Path | None]:
    """Yield a temporary sibling, leaving any previous report intact until replace().

    The caller resolves symlinks before entering, preserving file-target semantics.
    A successful preflight cannot guarantee disk space or permissions later in a run.
    """
    if target is None:
        yield None
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = None
    if target.exists():
        mode = target.stat().st_mode
        if not stat.S_ISREG(mode):
            if stat.S_ISDIR(mode):
                raise IsADirectoryError(errno.EISDIR, "report output is a directory", str(target))
            raise OSError(errno.EINVAL, "report output must be a regular file", str(target))
        # Check existing-file write access without truncating it or changing bytes.
        descriptor = os.open(target, os.O_WRONLY)
        os.close(descriptor)
    descriptor, name = tempfile.mkstemp(prefix=".extract-report-", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write("\n")
            stream.flush()
        if mode is not None:
            temporary.chmod(stat.S_IMODE(mode))
        yield temporary
    finally:
        temporary.unlink(missing_ok=True)
