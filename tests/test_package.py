from __future__ import annotations

from importlib.metadata import version

import dark_factory


def test_version_matches_installed_metadata() -> None:
    assert dark_factory.__version__ == version("dark-factory")
