"""Race-resistant loading for caller-supplied private JSON files."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

MAX_PRIVATE_JSON_BYTES = 256 * 1024


def load_private_json(
    path: Path,
    *,
    description: str = "Authentication input",
    max_bytes: int = MAX_PRIVATE_JSON_BYTES,
) -> Any:
    """Load bounded owner-private UTF-8 JSON without following symlinks."""
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise ValueError(f"{description} must be a regular file: {candidate}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
        with os.fdopen(descriptor, "rb") as private_file:
            metadata = os.fstat(private_file.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"{description} must be a regular file: {candidate}")
            if metadata.st_size > max_bytes:
                raise ValueError(
                    f"{description} exceeds {max_bytes} bytes: {candidate}"
                )
            if os.name == "posix" and metadata.st_mode & 0o077:
                raise ValueError(
                    f"{description} must be owner-only (chmod 600): {candidate}"
                )
            contents = private_file.read(max_bytes + 1)
        if len(contents) > max_bytes:
            raise ValueError(f"{description} exceeds {max_bytes} bytes: {candidate}")
        return json.loads(contents.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"{description} is not valid UTF-8 JSON: {candidate}"
        ) from error
