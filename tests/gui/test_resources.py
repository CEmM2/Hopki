"""Tests for the bundled-asset resolver used by the frozen build."""

from __future__ import annotations

import unittest
from pathlib import Path

from hopki.gui.resources import asset_path


class AssetPathTests(unittest.TestCase):
    def test_resolves_existing_package_asset(self) -> None:
        # theme_seuss.css ships in hopki/gui/ — resolves from the source checkout.
        p = asset_path("theme_seuss.css")
        self.assertTrue(p.exists())
        self.assertEqual(p.name, "theme_seuss.css")

    def test_missing_asset_falls_back_to_source_path(self) -> None:
        # Unknown asset: return the source-tree candidate (caller handles the missing file),
        # never raise.
        p = asset_path("does_not_exist_12345.png")
        self.assertEqual(p.name, "does_not_exist_12345.png")
        self.assertEqual(p.parent, Path(asset_path("theme_seuss.css")).parent)


if __name__ == "__main__":
    unittest.main()
