"""House costs: a shared house's running costs, split between the households that share it."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("house-cost")
except PackageNotFoundError:  # pragma: no cover - only when run from a tree that is not installed
    __version__ = "0.0.0"
