#!/usr/bin/env python3
"""Offline checks: no compositor, user config or installed shell changes."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("control", Path(__file__).resolve().parents[1] / "shell/control.py")
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


class SettingsTests(unittest.TestCase):
    def test_workspace_names_and_trackpad(self):
        self.assertTrue(control.DEFAULTS["trackpad_enabled"])
        self.assertFalse(control.DEFAULTS["carry_windows"])
        name = 'Code <img src="https://invalid"> é🙂'
        values = dict(control.DEFAULTS, workspace_name_1=name, workspace_name_20="🙂" * 80)
        self.assertEqual(control.validate(values), values)
        self.assertNotIn("<img", control.encode(values))
        for invalid in ("x" * 81, "new\nline", "tab\t", "\0", "\x7f", "\u2028", "\ud800", 1):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                control.validate(dict(control.DEFAULTS, workspace_name_1=invalid))
        with self.assertRaises(ValueError):
            control.validate(dict(control.DEFAULTS, trackpad_enabled=1))

    def test_trackpad_finger_count(self):
        self.assertEqual(control.DEFAULTS["trackpad_fingers"], 3)
        for count in (3, 4):
            values = dict(control.DEFAULTS, trackpad_fingers=count)
            self.assertIn(f"trackpad_fingers = {count},", control.encode(control.validate(values)))
        for invalid in (2, 5, 3.5, "4", True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                control.validate(dict(control.DEFAULTS, trackpad_fingers=invalid))
        self.assertNotIn("trackpad_fingers", control.PRESET_KEYS)

    def test_preset_lifecycle_preserves_workspace_settings(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(control, "CONFIG", Path(directory)), \
             patch.object(control, "ctl", side_effect=AssertionError("Presets must not call the compositor")):
            name = '<img src="https://invalid"> é🙂'
            self.assertEqual(control.presets("list"), dict(presets=[]))
            pending = dict(control.DEFAULTS, duration_ms=350, workspace_count=4,
                           workspace_name_1="Code", enabled=False, trackpad_enabled=False,
                           carry_windows=True)
            self.assertEqual(control.presets("save", name, pending), dict(presets=[name]))
            loaded = control.presets("load", name)["values"]
            self.assertEqual(set(loaded), control.PRESET_KEYS)
            current = dict(control.DEFAULTS, workspace_name_1="Keep", workspace_count=12)
            merged = dict(current, **loaded)
            self.assertEqual(merged["duration_ms"], 350)
            self.assertNotIn("carry_windows", loaded)
            for key in set(control.DEFAULTS) - control.PRESET_KEYS:
                self.assertEqual(merged[key], current[key])
            control.validate(merged)
            control.presets("save", name, dict(pending, duration_ms=400))
            self.assertEqual(control.presets("load", name)["values"]["duration_ms"], 400)
            self.assertEqual(control.presets("delete", name), dict(presets=[]))
            with self.assertRaisesRegex(ValueError, "does not exist"):
                control.presets("load", name)

    def test_presets_reject_invalid_and_preserve_corrupt_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(control, "CONFIG", Path(directory)):
            path = Path(directory) / "cube-presets.json"
            for name in ("", "  ", "x" * 65, "new\nline", "\0", "\ud800"):
                with self.subTest(name=repr(name)), self.assertRaises(ValueError):
                    control.presets("save", name, control.DEFAULTS.copy())
            with self.assertRaises(ValueError):
                control.presets("save", "valid", dict(control.DEFAULTS, zoom=3))
            for corrupt in ('{', '[]', '{"bad":{}}', ' ' * (control.PRESET_BYTES + 1)):
                path.write_text(corrupt)
                for action in ("list", "load", "save", "delete"):
                    with self.subTest(action=action), self.assertRaisesRegex(ValueError, "preserved"):
                        control.presets(action, "valid", control.DEFAULTS.copy())
                    self.assertEqual(path.read_text(), corrupt)
            path.unlink()
            with patch.object(control, "PRESET_LIMIT", 1):
                control.presets("save", "first", control.DEFAULTS.copy())
                with self.assertRaisesRegex(ValueError, "At most"):
                    control.presets("save", "second", control.DEFAULTS.copy())
                control.presets("save", "first", dict(control.DEFAULTS, zoom=1))

    def test_image_picker_selection_cancel_and_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sky " $ moon.jpeg'
            path.touch()
            with patch.object(control.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, str(path) + "\n")) as run:
                self.assertEqual(control.pick_image(), str(path))
                self.assertIn("[jJ][pP][eE][gG]", run.call_args.args[0][3])
            with patch.object(control.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "")):
                self.assertIsNone(control.pick_image())
            with patch.object(control.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "/tmp/no.jpg\n")):
                with self.assertRaises(ValueError):
                    control.pick_image()
            with patch.object(control.subprocess, "run", return_value=subprocess.CompletedProcess([], 2, "")):
                with self.assertRaises(RuntimeError):
                    control.pick_image()

    def test_bounds_and_types(self):
        self.assertEqual(control.validate(control.DEFAULTS.copy()), control.DEFAULTS)
        for suffix in (".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JpEg"):
            with self.subTest(suffix=suffix):
                self.assertEqual(control.validate(dict(control.DEFAULTS, skydome_path="/tmp/image" + suffix))["skydome_path"], "/tmp/image" + suffix)
        for key, invalid in (("duration_ms", 119), ("workspace_count", 21),
                             ("horizontal_sensitivity", .24), ("vertical_sensitivity", 3.01),
                             ("horizontal_sensitivity", True), ("vertical_sensitivity", float("inf")),
                             ("momentum", 1), ("carry_windows", 1), ("show_labels", "true"), ("highlight_selected", None),
                             ("invert_horizontal", 0), ("invert_vertical", "false"),
                             ("skydome_mode", "remote"), ("skydome_mode", 1),
                             ("zoom", float("nan")), ("zoom", True),
                             ("enabled", 1), ("skydome_brightness", 0),
                             ("skydome_path", "relative.png"),
                             ("skydome_path", "/tmp/image.gif"),
                             ("skydome_path", "/tmp/\0.png"),
                             ("skydome_path", "/" + "x" * 4096 + ".png")):
            with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                control.validate(dict(control.DEFAULTS, **{key: invalid}))
        with self.assertRaises(ValueError):
            control.validate({})
        for mode in ("auto", "photo", "panorama"):
            control.validate(dict(control.DEFAULTS, skydome_mode=mode))

    def test_live_reads_new_native_defaults_and_mode(self):
        values = dict(control.DEFAULTS, carry_windows=True, skydome_mode="panorama")
        options = []
        for key, value in values.items():
            field = "str" if isinstance(value, str) else "bool" if key in control.BOOLS else "int" if key in control.INTS else "float"
            options.append(json.dumps(dict(option="plugin:cube:" + key, **{field: value})))
        with patch.object(control, "ctl", side_effect=["active=false sky_error=none", "\n".join(options)]):
            self.assertEqual(control.live(), values)

    @unittest.skipUnless(shutil.which("node"), "Node unavailable")
    def test_preview_only_uses_encoded_local_urls(self):
        qml = (Path(__file__).resolve().parents[1] / "shell/Cube.qml").read_text()
        function = qml[qml.index("  function imageUrl("):qml.index("\n  function change(")]
        script = function + r'''
const assert = require("node:assert/strict");
const path = '/tmp/<img src="https://invalid"> #?%é.png';
const url = new URL(imageUrl(path));
assert.equal(url.protocol, "file:");
assert.equal(url.host, "");
assert.equal(url.hash, "");
assert.equal(url.search, "");
assert.equal(decodeURIComponent(url.pathname), path);
assert.equal(new URL(imageUrl("//host/sky.jpg")).host, "");
for (const path of ["https://invalid/sky.png", "relative.png", "file:///tmp/sky.png", "", null])
  assert.equal(imageUrl(path), "");
'''
        subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)

    def test_navigation_only_accepts_known_actions(self):
        with patch.object(control, "ctl", return_value="ok") as ctl, patch.object(control, "live", return_value=control.DEFAULTS.copy()):
            self.assertEqual(control.navigate("overview"), control.DEFAULTS)
            self.assertIn('rotate("overview")', ctl.call_args.args[1])
            with self.assertRaises(ValueError): control.navigate('overview"); os.execute("bad")')
            self.assertEqual(ctl.call_count, 1)

    def test_curvature_bounds_and_legacy_presets(self):
        for value in (-1, -.5, 0, .5, 1):
            control.validate(dict(control.DEFAULTS, face_curvature=value))
        for value in (-1.01, 1.01, True, float('nan'), float('inf'), '0'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                control.validate(dict(control.DEFAULTS, face_curvature=value))
        with tempfile.TemporaryDirectory() as directory, patch.object(control, 'CONFIG', Path(directory)):
            old = {k: control.DEFAULTS[k] for k in control.PRESET_KEYS - {'face_curvature'}}
            path = Path(directory) / 'cube-presets.json'
            path.write_text(json.dumps({'Legacy': old}))
            loaded = control.presets('load', 'Legacy')['values']
            self.assertNotIn('face_curvature', loaded)
            self.assertEqual(dict(control.DEFAULTS, face_curvature=.5, **loaded)['face_curvature'], .5)
            control.presets('save', 'Curved', dict(control.DEFAULTS, face_curvature=-.75))
            self.assertEqual(control.presets('load', 'Curved')['values']['face_curvature'], -.75)

    def test_skydome_status_errors(self):
        values = dict(control.DEFAULTS, skydome_path="/tmp/sky.png")
        self.assertEqual(control.sky_problem(values, "active=false sky_loaded=true sky_error=none"), "")
        self.assertIn("bad PNG", control.sky_problem(values, "active=false sky_loaded=false sky_error=bad PNG"))
        self.assertEqual(control.sky_problem(dict(values, skydome_enabled=False), "active=false sky_loaded=false sky_error=bad PNG"), "")

    def test_lua_string_bytes_do_not_become_code(self):
        path = '/tmp/é"\\\n<img src="https://invalid">123.png'
        control.validate(dict(control.DEFAULTS, skydome_path=path))
        encoded = control.lua_value(path)
        self.assertRegex(encoded, r'^"(?:\\[0-9]{3})+"$')
        decoded = bytes(int(encoded[i:i + 3]) for i in range(2, len(encoded) - 1, 4))
        self.assertEqual(decoded.decode("utf-8"), path)
        self.assertNotIn("<img", encoded)

    @unittest.skipUnless(shutil.which("lua"), "Lua unavailable")
    def test_lua_runtime_roundtrip(self):
        path = '/tmp/é"\\\n123.png'
        encoded = control.encode(dict(control.DEFAULTS, skydome_path=path))
        result = subprocess.run(["lua", "-"], input=("local settings = (function()\n" + encoded +
            "end)(); io.write(settings.skydome_path)"), text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout, path)

    def test_failed_apply_restores_previous_or_removes_new_file(self):
        for previous in (None, control.encode(control.DEFAULTS)):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as directory:
                config = Path(directory)
                target = config / "cube-gui.lua"
                (config / "cube.lua").write_text("-- Omarchy Cube GUI bridge v2\n")
                if previous is not None:
                    target.write_text(previous)
                responses = iter(("", "ok", "injected config error", "ok", ""))
                with patch.object(control, "CONFIG", config), patch.object(control, "TARGET", target), \
                     patch.object(control, "live", return_value=control.DEFAULTS.copy()), \
                     patch.object(control, "ctl", side_effect=lambda *args: next(responses)), \
                     self.assertRaisesRegex(RuntimeError, "injected config error"):
                    control.apply(dict(control.DEFAULTS, duration_ms=300))
                self.assertEqual(target.read_text() if target.exists() else None, previous)

    def test_skydome_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            target = config / "cube-gui.lua"
            (config / "cube.lua").write_text("-- Omarchy Cube GUI bridge v2\n")
            with patch.object(control, "CONFIG", config), patch.object(control, "TARGET", target), \
                 patch.object(control, "live", side_effect=[control.DEFAULTS.copy(),
                     RuntimeError("Skydome image error: bad PNG"), control.DEFAULTS.copy()]), \
                 patch.object(control, "ctl", return_value=""), \
                 self.assertRaisesRegex(RuntimeError, "bad PNG"):
                control.apply(dict(control.DEFAULTS, skydome_path="/tmp/sky.png"))
            self.assertFalse(target.exists())

    def test_readback_mismatch_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            target = config / "cube-gui.lua"
            (config / "cube.lua").write_text("-- Omarchy Cube GUI bridge v2\n")
            with patch.object(control, "CONFIG", config), patch.object(control, "TARGET", target), \
                 patch.object(control, "live", return_value=control.DEFAULTS.copy()), \
                 patch.object(control, "ctl", side_effect=lambda *args: ""), \
                 self.assertRaisesRegex(RuntimeError, "overrides"):
                control.apply(dict(control.DEFAULTS, duration_ms=300))
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
