"""Version metadata for the CLI-only pre-1.0 distribution.

Internal modules remain importable for implementation and testing, but they are
not a supported compatibility surface before 1.0.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("grab2md")
except PackageNotFoundError:  # Source tree imported without installation metadata.
    __version__ = "0+unknown"

__all__ = ["__version__"]
