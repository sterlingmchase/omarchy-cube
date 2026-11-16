#!/usr/bin/env python3
"""Offline installer checks with a disposable home and mocked desktop commands."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallGuiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        home, config, commands = root / "home", root / "config", root / "bin"
        commands.mkdir()
        self.module = config / "hypr/cube.lua"
        self.module.parent.mkdir(parents=True)
        self.original = "-- Existing user settings: é\n"
        self.module.write_text(self.original)
        library = home / ".local/lib/hypr/omarchy-cube.so"
        library.parent.mkdir(parents=True)
        library.touch()
        self.log = root / "calls"
        self.destination = config / "omarchy/plugins/local.cube"
        self.env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(config),
                        PATH=str(commands) + os.pathsep + os.environ["PATH"],
                        CUBE_TEST_LOG=str(self.log), CUBE_TEST_RELOADED=str(root / "reloaded"),
                        CUBE_TEST_FAIL="0")
        mocks = {
            "omarchy": '[[ "$*" == "plugin validate "* ]]',
            "omarchy-shell": '[[ "$*" == "shell ping" ]]',
            "hyprctl": '''case "$*" in
  omarchy-cube:status) echo 'active=false' ;;
  reload) touch "$CUBE_TEST_RELOADED" ;;
  configerrors)
    if [[ "$CUBE_TEST_FAIL" == 1 && -f "$CUBE_TEST_RELOADED" ]]; then
      echo 'mock configuration error'
    fi ;;
  *) exit 1 ;;
esac''',
        }
        for name, body in mocks.items():
            command = commands / name
            command.write_text('#!/usr/bin/env bash\nset -eu\nprintf "%s %s\\n" "${0##*/}" "$*" >> "$CUBE_TEST_LOG"\n' + body + "\n")
            command.chmod(0o755)

    def install(self):
        return subprocess.run(["bash", str(ROOT / "tools/install-gui"), "--bridge-only"],
                              env=self.env, capture_output=True, text=True, timeout=10)

    def assert_no_widget_install(self):
        self.assertFalse(self.destination.exists())
        calls = self.log.read_text().splitlines()
        self.assertNotIn("omarchy-shell shell rescanPlugins", calls)
        self.assertTrue(all(not call.startswith("omarchy plugin enable") for call in calls))

    def test_bridge_only_is_idempotent(self):
        for _ in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.module.read_text(), self.original + (ROOT / "shell/SettingsBridge.lua").read_text())
            self.assert_no_widget_install()

    def test_reload_validation_failure_restores_module(self):
        self.env["CUBE_TEST_FAIL"] = "1"
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Restored cube.lua", result.stderr)
        self.assertEqual(self.module.read_text(), self.original)
        self.assertEqual(self.log.read_text().splitlines().count("hyprctl reload"), 2)
        self.assert_no_widget_install()


if __name__ == "__main__":
    unittest.main()
