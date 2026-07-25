"""Durable atomic writers shared by configuration, state, and artifacts."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any


def _atomic_write_bytes(
    file_path: Path,
    payload: bytes,
    *,
    private_parent: bool = False,
    owner_only: bool = True,
) -> None:
    """Atomically publish ``payload`` at ``file_path``.

    On POSIX the destination directory is opened once and every subsequent step
    -- temporary-file creation, the rename, and both fsyncs -- is anchored to
    that descriptor with ``O_NOFOLLOW``. This structurally eliminates the TOCTOU
    escape in which a concurrent attacker swaps the parent directory for a
    symlink between temp creation and the final rename: because the rename
    targets ``dir_fd`` rather than a re-resolved path, a swapped symlink is
    never followed.

    Args:
        file_path: Target path. Must be a :class:`~pathlib.Path`.
        payload: Exact bytes to write.
        private_parent: Create (if missing) and clamp the parent directory to
            owner-only (``0o700``). This is safe for both application-owned and
            caller-selected parents because it only tightens permissions, never
            loosens them.
        owner_only: When true (the default), publish the file ``0o600`` so it is
            readable only by its owner regardless of the process umask.

    Raises:
        OSError: If any filesystem operation fails (permissions, disk full, ...).
        ValueError: If ``file_path`` is not a :class:`~pathlib.Path`.
    """
    if not isinstance(file_path, Path):
        raise ValueError(f"file_path must be a Path object, got {type(file_path)}")

    file_path.parent.mkdir(
        parents=True, exist_ok=True, mode=0o700 if private_parent else 0o777
    )
    if private_parent and os.name == "posix":
        os.chmod(file_path.parent, 0o700)

    if os.name != "posix":
        descriptor, temporary = tempfile.mkstemp(
            dir=file_path.parent, prefix=f".{file_path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
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
    create_mode = 0o600 if owner_only else 0o666
    posix_descriptor: int | None = None
    try:
        posix_descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            create_mode,
            dir_fd=directory_fd,
        )
        with os.fdopen(posix_descriptor, "wb") as handle:
            posix_descriptor = None
            handle.write(payload)
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


def atomic_write_text(file_path: Path, content: str) -> None:
    """Write UTF-8 text atomically, anchoring the destination directory on POSIX."""
    _atomic_write_bytes(file_path, content.encode("utf-8"))


def atomic_write_json(
    file_path: Path,
    data: dict[str, Any],
    indent: int = 4,
    private: bool = True,
    private_parent: bool = False,
) -> None:
    """
    Atomically write JSON data to a file using the shared anchored writer.

    This function guarantees that:
    - Either the entire write succeeds, or the original file is unchanged
    - No partial or corrupt files are left on disk
    - The rename is atomic on POSIX (via ``os.replace``)
    - On POSIX the destination directory is opened once and every step is
      anchored to that descriptor with ``O_NOFOLLOW``, so a concurrent
      symlink swap of the parent cannot redirect the write (TOCTOU-resistant)
    - The published file is owner-only (``0o600``) on POSIX when ``private``

    Args:
        file_path: Target file path where JSON will be written.
        data: Dictionary to serialize as JSON.
        indent: JSON indentation level for human readability (default: 4).
        private: Publish the file owner-only (``0o600``) on POSIX. Defaults to
            ``True`` (secure by default): every caller must opt *out* of
            owner-only permissions rather than remember to opt in, so a
            sensitive JSON payload (config, crawl state) cannot be written
            world-readable by omission. Pass ``private=False`` for a
            deliberately shared file.
        private_parent: Also create and clamp the parent directory to
            owner-only (``0o700``). Safe for both application-owned and
            caller-selected parents, since it only tightens permissions.

    Raises:
        OSError: If the write operation fails (permissions, disk full, etc.).
        TypeError: If data cannot be serialized to JSON.
        ValueError: If file_path is not a Path object.

    Example:
        >>> config = {"headers": {"custom_headers": {}}, "logging": {"level": "INFO"}}
        >>> atomic_write_json(Path("/path/to/config.json"), config)
    """
    if not isinstance(file_path, Path):
        raise ValueError(f"file_path must be a Path object, got {type(file_path)}")

    payload = json.dumps(data, indent=indent, ensure_ascii=False).encode("utf-8")
    _atomic_write_bytes(
        file_path, payload, private_parent=private_parent, owner_only=private
    )
