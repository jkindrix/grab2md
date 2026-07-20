"""Import-boundary tripwires for the lowest-level utility package."""

from __future__ import annotations

import ast
from pathlib import Path


def test_utils_do_not_import_higher_level_packages() -> None:
    utils_dir = Path(__file__).parents[1] / "utils"
    forbidden = {
        "grab2md.cli",
        "grab2md.config",
        "grab2md.cookies",
        "grab2md.markdown",
        "grab2md.network",
    }
    violations: list[str] = []

    for source_path in sorted(utils_dir.glob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), source_path.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            else:
                continue
            for module in imported:
                if any(
                    module == root or module.startswith(f"{root}.")
                    for root in forbidden
                ):
                    violations.append(f"{source_path.name}:{node.lineno}: {module}")

    assert not violations, "Utility-layer import inversion:\n" + "\n".join(violations)
