"""Durable atomic writers shared by configuration, state, and artifacts."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(file_path: Path, content: str) -> None:
    """Write UTF-8 text atomically, anchoring the destination directory on POSIX."""
    if not isinstance(file_path, Path):
        raise ValueError(f"file_path must be a Path object, got {type(file_path)}")
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if os.name != "posix":
        descriptor, temporary = tempfile.mkstemp(
            dir=file_path.parent, prefix=f".{file_path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, file_path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        return

    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    directory_fd = os.open(file_path.parent, directory_flags)
    temporary_name = f".{file_path.name}.{secrets.token_hex(8)}.tmp"
    posix_descriptor: int | None = None
    try:
        posix_descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(posix_descriptor, "w", encoding="utf-8") as handle:
            posix_descriptor = None
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            file_path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except BaseException:
        if posix_descriptor is not None:
            os.close(posix_descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(directory_fd)


def atomic_write_json(
    file_path: Path,
    data: dict[str, Any],
    indent: int = 4,
    private: bool = False,
    private_parent: bool = False,
) -> None:
    """
    Atomically write JSON data to a file using temp-rename pattern.

    This function ensures that:
    - Either the entire write succeeds, or the original file is unchanged
    - No partial or corrupt files are left on disk
    - The operation is atomic on POSIX systems (using os.replace)
    - Works reliably across all supported platforms

    The implementation uses the standard temp-file-then-rename pattern:
    1. Create a temporary file in the same directory as the target
    2. Write all data to the temporary file
    3. Flush and fsync to ensure data is on disk
    4. Atomically rename temp file to target (replaces original)

    Args:
        file_path: Target file path where JSON will be written
        data: Dictionary to serialize as JSON
        indent: JSON indentation level for human readability (default: 4)
        private: Restrict the target file to its owner on POSIX.
        private_parent: Also manage and restrict the parent directory. Use only
            for application-owned directories, never caller-selected parents.

    Raises:
        OSError: If write operation fails (permissions, disk full, etc.)
        TypeError: If data cannot be serialized to JSON
        ValueError: If file_path is not a Path object

    Example:
        >>> config = {"headers": {"custom_headers": {}}, "logging": {"level": "INFO"}}
        >>> atomic_write_json(Path("/path/to/config.json"), config)
    """
    if not isinstance(file_path, Path):
        raise ValueError(f"file_path must be a Path object, got {type(file_path)}")

    # Ensure parent directory exists
    file_path.parent.mkdir(
        parents=True, exist_ok=True, mode=0o700 if private_parent else 0o777
    )
    if private_parent and os.name == "posix":
        os.chmod(file_path.parent, 0o700)

    # Create temp file in same directory (ensures same filesystem for atomic rename)
    fd, temp_path = tempfile.mkstemp(
        dir=file_path.parent, prefix=f".{file_path.stem}.", suffix=".tmp"
    )

    try:
        if private and os.name == "posix":
            os.fchmod(fd, 0o600)
        # Write JSON data to temp file
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            # Persist file contents before exposing the replacement name.
            os.fsync(f.fileno())

        # Atomic rename (POSIX guarantees atomicity, Windows best-effort on Python 3.3+)
        os.replace(temp_path, file_path)
        if private and os.name == "posix":
            os.chmod(file_path, 0o600)
        if os.name == "posix":
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            directory_fd = os.open(file_path.parent, directory_flags)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(temp_path)
        except OSError:
            # Ignore errors during cleanup (temp file may not exist)
            pass
        raise
