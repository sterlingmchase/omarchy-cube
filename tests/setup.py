#!/usr/bin/env python3
"""First-run setup tests: no real compositor, package install, or configuration edits."""
import importlib.machinery
import importlib.util
import json
import signal
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader("cube_setup", str(Path(__file__).resolve().parents[1] / "tools/setup"))
spec = importlib.util.spec_from_loader(loader.name, loader)
setup = importlib.util.module_from_spec(spec)
loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = self.home / ".config/hypr"
        self.config.mkdir(parents=True)
        self.main = self.config / "hyprland.lua"
        self.original = b"-- personal configuration\n"
        self.main.write_bytes(self.original)
        self.root = self.home / "source"
        for directory in ("examples", "shell", "build"):
            (self.root / directory).mkdir(parents=True)
        (self.root / "examples/cube.lua").write_text("-- default module\n")
        (self.root / "shell/SettingsBridge.lua").write_text("-- bridge\n")
        (self.root / "build/omarchy-cube.so").write_bytes(b"fixture, not a library")
        for p in (patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.home / ".config")}),
                  patch.object(Path, "home", return_value=self.home),
                  patch.object(setup, "ROOT", self.root),
                  patch.object(setup.sys, "argv", ["setup"]),
                  patch.object(setup.sys.stdin, "isatty", return_value=True),
                  patch("builtins.input", return_value="y"),
                  patch.object(setup.shutil, "which", return_value="/mock/bin"),
                  patch.object(setup.subprocess, "run")):
            p.start()
            self.addCleanup(p.stop)
        setup.subprocess.run.return_value.returncode = 0
        self.calls = []
        self.bad_status = False
        self.commit = setup.SUPPORTED_COMMIT
        def run(*args, capture=False):
            self.calls.append(args)
            if args[:2] == ("hyprctl", "version"):
                return json.dumps({"commit": self.commit})
            if args == ("hyprctl", "configerrors"):
                return ""
            if args == ("hyprctl", "omarchy-cube:status"):
                return "not loaded" if self.bad_status else "active=0"
            return "" if capture else None
        p = patch.object(setup, "run", side_effect=run)
        p.start()
        self.addCleanup(p.stop)

    def test_success(self):
        setup.main()
        self.assertIn(b'require("hypr.cube")', self.main.read_bytes())
        self.assertIn("-- bridge", (self.config / "cube.lua").read_text())
        self.assertEqual(next(self.config.glob("hyprland.lua.cube-backup-*")).read_bytes(), self.original)

    def test_incompatible_changes_nothing(self):
        self.commit = "unsupported"
        with self.assertRaisesRegex(RuntimeError, "not supported"):
            setup.main()
        self.assertEqual(self.main.read_bytes(), self.original)
        self.assertFalse((self.config / "cube.lua").exists())

    def test_existing_module_preserved(self):
        module = self.config / "cube.lua"
        module.write_text("personal settings")
        with self.assertRaisesRegex(RuntimeError, "existing native"):
            setup.main()
        self.assertEqual(module.read_text(), "personal settings")

    def test_cancel_no_build_or_changes(self):
        with patch("builtins.input", return_value="n"):
            setup.main()
        self.assertFalse(any(c[0] == "make" for c in self.calls))
        self.assertEqual(self.main.read_bytes(), self.original)

    def test_failed_activation_rolls_back(self):
        self.bad_status = True
        with self.assertRaisesRegex(RuntimeError, "healthy status"):
            setup.main()
        self.assertEqual(self.main.read_bytes(), self.original)
        self.assertFalse((self.config / "cube.lua").exists())
        self.assertFalse((self.home / ".local/lib/hypr/omarchy-cube.so").exists())

    def test_activation_signals_roll_back_and_restore_handlers(self):
        run = setup.run.side_effect
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig):
                previous = signal.getsignal(sig)

                def interrupt(*args, **kwargs):
                    if args == ('hyprctl', 'reload'):
                        signal.raise_signal(sig)
                    return run(*args, **kwargs)

                setup.run.side_effect = interrupt
                try:
                    with self.assertRaises(KeyboardInterrupt):
                        setup.main()
                finally:
                    setup.run.side_effect = run
                self.assertEqual(signal.getsignal(sig), previous)
                self.assertEqual(self.main.read_bytes(), self.original)
                self.assertFalse((self.config / 'cube.lua').exists())
                self.assertFalse((self.home / '.local/lib/hypr/omarchy-cube.so').exists())

    def test_unload_failure_keeps_library(self):
        self.bad_status = True
        setup.subprocess.run.return_value.returncode = 1
        with self.assertRaises(RuntimeError):
            setup.main()
        self.assertEqual(self.main.read_bytes(), self.original)
        self.assertTrue((self.home / ".local/lib/hypr/omarchy-cube.so").exists())

    def test_noninteractive_refused(self):
        with patch.object(setup.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "terminal"):
                setup.main()
        self.assertFalse(any(c[0] == "make" for c in self.calls))

    def test_check_is_read_only(self):
        with patch.object(setup.sys, "argv", ["setup", "--check"]):
            setup.main()
        self.assertEqual(self.main.read_bytes(), self.original)
        self.assertFalse(any(c[0] == "make" for c in self.calls))


if __name__ == "__main__":
    unittest.main()
