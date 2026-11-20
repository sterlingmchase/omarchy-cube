#!/usr/bin/env python3
"""Offline built-in preset, asset and portable-reference regression tests."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("control", ROOT / "shell/control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class BuiltinTests(unittest.TestCase):
    def test_catalog_is_offline_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(control, "CONFIG", Path(directory) / "untouched"), \
             patch.object(control, "ctl", side_effect=AssertionError("must not touch compositor")):
            catalog = control.builtin_presets()["builtins"]
            self.assertEqual([item["id"] for item in catalog], list(control.BUILTINS))
            for item in catalog:
                self.assertTrue(Path(item["preview"]).is_file())
                control.builtin_presets(item["id"])
            self.assertFalse(control.CONFIG.exists())

    def test_presets_only_stage_presentation(self):
        current = dict(control.DEFAULTS, enabled=False, trackpad_enabled=False, carry_windows=True,
                       horizontal_sensitivity=2, invert_horizontal=True, momentum=True,
                       workspace_name_1="My workspace")
        allowed = {"workspace_count", "duration_ms", "zoom", "show_labels", "highlight_selected",
                   "skydome_enabled", "skydome_mode", "skydome_path", "skydome_brightness"}
        for name in control.BUILTINS:
            staged = control.builtin_presets(name)["values"]
            self.assertEqual(set(staged), allowed)
            merged = dict(current, **staged)
            control.validate(merged)
            for key in set(current) - allowed:
                self.assertEqual(merged[key], current[key])
        self.assertEqual(control.builtin_presets("classic")["values"]["skydome_path"], "")

    def test_ids_cannot_escape_assets_directory(self):
        for bad in ("../orbital", "https://example.invalid/image", "", "CLASSIC", "missing"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                control.builtin_presets(bad)
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                control.resolve_preset({"skydome_path": "builtin:" + bad})
        with self.assertRaisesRegex(ValueError, "missing"):
            with patch.object(control, "SKY_ASSETS", Path("/nonexistent-cube-assets")):
                control.builtin_presets("orbital")

    def test_custom_copies_survive_widget_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            moved = Path(directory) / "another install/assets/skydomes"
            shutil.copytree(control.SKY_ASSETS, moved)
            with patch.object(control, "CONFIG", config):
                values = dict(control.DEFAULTS, **control.builtin_presets("orbital")["values"])
                control.presets("save", "My orbital", values)
                stored = json.loads((config / "cube-presets.json").read_text())
                self.assertEqual(stored["My orbital"]["skydome_path"], "builtin:orbital")
                with patch.object(control, "SKY_ASSETS", moved):
                    loaded = control.presets("load", "My orbital")["values"]
                    self.assertEqual(loaded["skydome_path"], str(moved / "orbital.jpg"))
                    self.assertNotIn("workspace_count", loaded)
                    control.validate(dict(control.DEFAULTS, **loaded))

    def test_trial_art_uses_native_resolution_and_backdrop_mapping(self):
        assets = control.SKY_ASSETS
        self.assertLess(sum(p.stat().st_size for p in assets.glob("*.jpg")), 10 * 1024 * 1024)
        for name in control.BUILTINS:
            with Image.open(assets / (name + "-preview.jpg")) as preview:
                self.assertEqual(preview.size, (480, 240))
            if name == "classic":
                continue
            with Image.open(assets / (name + ".jpg")) as image:
                self.assertEqual(image.size, (1774, 887))
                self.assertEqual(image.mode, "RGB")
            self.assertEqual(control.builtin_presets(name)["values"]["skydome_mode"], "photo")
        records = json.loads((assets / "sources.json").read_text())
        self.assertEqual({r["id"] for r in records}, set(control.BUILTINS) - {"classic"})
        self.assertTrue(all(not r["upscaled"] for r in records))

    def test_all_builtin_strings_are_present(self):
        english = json.loads((ROOT / "shell/i18n/en.json").read_text())
        for name in control.BUILTINS:
            self.assertIn("builtin_" + name, english)
            self.assertIn("builtinDescription_" + name, english)


if __name__ == "__main__":
    unittest.main()
