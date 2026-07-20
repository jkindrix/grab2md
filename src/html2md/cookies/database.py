"""Owner-private lifecycle for copied browser cookie databases."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def copy_cookie_database(
    source_path: str | Path,
) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """Copy a locked browser database into unpredictable owner-only storage."""
    temp_directory = tempfile.TemporaryDirectory(prefix="html2md-cookies-")
    if os.name == "posix":
        os.chmod(temp_directory.name, 0o700)
    destination = Path(temp_directory.name) / "cookies.sqlite"
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with open(source_path, "rb") as source, os.fdopen(fd, "wb") as target:
            shutil.copyfileobj(source, target)
        if os.name == "posix":
            os.chmod(destination, 0o600)
        return temp_directory, destination
    except BaseException:
        temp_directory.cleanup()
        raise


@contextmanager
def copied_cookie_connection(
    source_path: str | Path,
) -> Iterator[sqlite3.Connection]:
    """Open a disposable cookie-database copy and release every resource."""
    temp_directory, copied_path = copy_cookie_database(source_path)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(copied_path))
        yield connection
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            temp_directory.cleanup()
