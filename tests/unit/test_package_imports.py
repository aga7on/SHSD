from __future__ import annotations

import importlib
import pkgutil

import shsd


def test_every_shipped_module_imports() -> None:
    """Every module that ships in the package must be importable without model weights.

    The primary `shsd` package is imported by the CLI, the API and most test
    modules. When a module is missing from the repository (for example because
    a broad `.gitignore` pattern such as `models/` excluded `src/shsd/models/`),
    the failure surfaces only at import time and every dependent module fails to
    collect. This regression guard walks the package tree and imports all of it.
    """
    modules = sorted(
        module.name for module in pkgutil.walk_packages(shsd.__path__, f"{shsd.__name__}.")
    )

    assert "shsd.models.artifacts" in modules, (
        "src/shsd/models/ is missing from the repository; check .gitignore for a "
        "pattern that excludes it from version control"
    )
    for name in modules:
        importlib.import_module(name)
