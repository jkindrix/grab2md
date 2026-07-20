"""Shared traversal primitives for dotted configuration paths."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

ConfigTree = MutableMapping[str, Any]


class ConfigPathError(ValueError):
    """Raised when a dotted path cannot be traversed safely."""


def split_config_path(raw_path: str) -> tuple[str, ...]:
    """Return validated components for a dotted configuration path."""
    components = tuple(raw_path.split("."))
    if not raw_path or any(not component for component in components):
        raise ConfigPathError("configuration paths cannot contain empty components")
    return components


def _parent_at_path(
    config: ConfigTree, path: tuple[str, ...], *, create: bool
) -> ConfigTree:
    current = config
    for index, component in enumerate(path[:-1]):
        if component not in current:
            if not create:
                raise ConfigPathError(
                    f"Path '{'.'.join(path)}' not found in configuration"
                )
            current[component] = {}
        child = current[component]
        if not isinstance(child, MutableMapping):
            prefix = ".".join(path[: index + 1])
            raise ConfigPathError(f"'{prefix}' is not a dictionary")
        current = child
    return current


def get_at_path(config: ConfigTree, path: tuple[str, ...]) -> Any:
    """Return a value from a validated dotted path."""
    parent = _parent_at_path(config, path, create=False)
    if path[-1] not in parent:
        raise ConfigPathError(f"Path '{'.'.join(path)}' not found in configuration")
    return parent[path[-1]]


def set_at_path(config: ConfigTree, path: tuple[str, ...], value: Any) -> None:
    """Set a value, creating missing mapping parents when safe."""
    _parent_at_path(config, path, create=True)[path[-1]] = value


def delete_at_path(config: ConfigTree, path: tuple[str, ...]) -> Any:
    """Delete and return the value at a validated dotted path."""
    parent = _parent_at_path(config, path, create=False)
    if path[-1] not in parent:
        raise ConfigPathError(f"Path '{'.'.join(path)}' not found in configuration")
    return parent.pop(path[-1])
