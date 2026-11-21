#!/usr/bin/env python3
"""Native swipe bus regression tests on an explicit tests/nested.lua compositor.

Run: python3 tests/gestures.py --display wayland-N [--screenshot]
Build only: python3 tests/gestures.py --build-only
This emits compositor events; physical libinput/device delivery needs hardware.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def build():
    target = ROOT / "build/gesture-driver.so"
    target.parent.mkdir(exist_ok=True)
    flags = shlex.split(subprocess.check_output(
        ["pkg-config", "--cflags", "hyprland", "pixman-1", "libdrm", "libturbojpeg", "pangocairo"], text=True))
    subprocess.run(["c++", "-std=c++23", "-shared", "-fPIC", "-fno-gnu-unique", "-Wall", "-Wextra",
                    "-Wno-unused-parameter", "-Wno-missing-field-initializers", *flags,
                    str(ROOT / "tests/gesture-driver.cpp"), "-o", str(target)], check=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--screenshot", action="store_true")
    options = parser.parse_args()
    driver = build()
    if options.build_only:
        print("PASS: built test-only swipe bus driver")
        return
    if not options.display:
        parser.error("--display is required; refusing to use the personal desktop")
    instances = json.loads(subprocess.check_output(["hyprctl", "instances", "-j"]))
    matches = [i for i in instances if i["wl_socket"] == options.display]
    assert len(matches) == 1, "Explicit display must identify one compositor"
    instance = matches[0]

    def guard():
        args = Path(f"/proc/{instance['pid']}/cmdline").read_bytes().split(b"\0")
        assert str(ROOT / "tests/nested.lua").encode() in args, "Refusing non-fixture compositor"

    def ctl(*args):
        guard()
        result = subprocess.run(["hyprctl", "-i", instance["instance"], *args],
                                text=True, capture_output=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.strip()

    def ok(*args):
        result = ctl(*args)
        assert result == "ok", result

    def lua(code):
        ok("eval", code)

    def rotate(action):
        lua(f"local ok,err=hl.plugin.cube.rotate({json.dumps(action)}); assert(ok,err)")

    def emit(call, consumed=True):
        lua(f"assert(hl.plugin.cube_test_gesture.{call} == {str(consumed).lower()}, 'gesture consumption')")

    def status():
        return dict(re.findall(r"(\w+)=([^ ]+)", ctl("omarchy-cube:status")))

    def workspace():
        return json.loads(ctl("activeworkspace", "-j"))["id"]

    def config(values):
        fields = ",".join(key + "=" + (str(value).lower() if isinstance(value, bool) else
                                      json.dumps(value, ensure_ascii=False)) for key, value in values.items())
        lua("hl.config({plugin={cube={" + fields + "}}})")

    cube = ROOT / "build/omarchy-cube.so"
    loaded = []
    try:
        existing = ctl("plugin", "list")
        assert "Omarchy Cube" not in existing and "Cube Gesture Test Driver" not in existing, \
            "Use a fresh fixture; refusing to unload someone else's plugins"
        for plugin in (cube, driver):
            ok("plugin", "load", str(plugin))
            loaded.append(plugin)
        config(dict(workspace_count=4, duration_ms=240, momentum=False,
                    horizontal_sensitivity=1, vertical_sensitivity=1,
                    invert_horizontal=False, invert_vertical=False))
        lua("hl.dispatch(hl.dsp.focus({workspace=1}))")
        time.sleep(.15)
        start = workspace()
        config(dict(trackpad_enabled=False))
        for fingers in (4, 3):
            emit(f"begin({fingers})", False)
            emit("update(-300,0)", False)
            emit("finish(false)", False)
            assert status()["active"] == "false" and workspace() == start
        config(dict(trackpad_enabled=True))
        emit("begin(4)", False)
        emit("update(-300,0)", False)
        emit("finish(false)", False)
        assert status()["active"] == "false" and workspace() == start

        emit("begin(3)")
        assert status()["overview"] == "true"
        time.sleep(.3)
        emit("update(-300,1000)")
        moving = status()
        assert math.isclose(float(moving["angle"]), 1, abs_tol=.001), moving
        assert math.isclose(float(moving["pitch"]), -math.pi / 4, abs_tol=.001), moving
        assert int(moving["selected"]) == start % 4 + 1 and workspace() == start, moving
        emit("finish(false)")
        landing = status()
        assert landing["active"] == "true" and landing["overview"] == "false", landing
        time.sleep(.07)
        middle = status()
        assert 0 < float(middle["zoom"]) < float(landing["zoom"]), (landing, middle)
        assert abs(float(middle["pitch"])) < abs(float(landing["pitch"])), (landing, middle)
        time.sleep(.25)
        assert status()["active"] == "false" and workspace() == start % 4 + 1
        start = workspace()

        config(dict(trackpad_fingers=4))
        emit("begin(3)", False)
        emit("update(-300,0)", False)
        emit("finish(false)", False)
        assert status()["active"] == "false" and workspace() == start
        emit("begin(4)")
        assert status()["overview"] == "true"
        emit("finish(true)")
        assert status()["active"] == "false" and workspace() == start
        config(dict(trackpad_fingers=3))

        config(dict(horizontal_sensitivity=2, vertical_sensitivity=.5,
                    invert_horizontal=True, invert_vertical=True))
        emit("begin(3)")
        time.sleep(.3)
        emit("update(-150,100)")
        tuned = status()
        assert math.isclose(float(tuned["angle"]), -1, abs_tol=.001), tuned
        assert math.isclose(float(tuned["pitch"]), .1, abs_tol=.001), tuned
        emit("finish(true)")
        assert status()["active"] == "false" and workspace() == start, "Cancelled swipe committed"
        config(dict(horizontal_sensitivity=1, vertical_sensitivity=1,
                    invert_horizontal=False, invert_vertical=False))
        name = "Gesture named face é🙂"
        config({f"workspace_name_{start % 4 + 1}": name})
        rotate("overview")
        time.sleep(.3)
        emit("begin(3)")
        emit("update(-270,-1000)")
        assert math.isclose(float(status()["pitch"]), math.pi / 4, abs_tol=.001)
        emit("finish(false)")
        time.sleep(.3)
        preview = status()
        assert preview["overview"] == "true" and workspace() == start, preview
        assert int(preview["selected"]) == start % 4 + 1 and float(preview["target"]) == 1, preview
        readback = json.loads(ctl("getoption", "plugin:cube:workspace_name_" + preview["selected"], "-j"))
        assert readback["str"] == name, readback
        if options.screenshot:
            rotate("cancel")
            rotate("overview")
            rotate("right")
            time.sleep(.3)
            monitor = json.loads(ctl("monitors", "-j"))[0]["name"]
            guard()
            subprocess.run(["grim", "-o", monitor, str(ROOT / "build/gesture-named-face.png")],
                           env=os.environ | {"WAYLAND_DISPLAY": options.display,
                                             "HYPRLAND_INSTANCE_SIGNATURE": instance["instance"]}, check=True, timeout=10)
        rotate("cancel")

        for action in ("cancel", "Escape"):
            emit("begin(3)")
            emit("update(-300,0)")
            if action == "cancel":
                rotate("cancel")
            else:
                guard()
                subprocess.run(["wtype", "-k", "Escape"],
                               env=os.environ | {"WAYLAND_DISPLAY": options.display,
                                                 "HYPRLAND_INSTANCE_SIGNATURE": instance["instance"]}, check=True, timeout=10)
            assert status()["active"] == "false"
            emit("update(-900,500)")
            emit("finish(false)")
            assert status()["active"] == "false" and workspace() == start, "Interrupted swipe committed"
            emit("update(-300,0)", False)
            emit("finish(false)", False)
        # A new sequence must work after cancellation drained the old one.
        emit("begin(3)")
        emit("update(-180,0)")
        emit("finish(false)")
        time.sleep(.3)
        assert workspace() == start % 4 + 1 and status()["active"] == "false"
        print("PASS: swipe ownership, selection/landing, tuning, tilt clamps, cancellation, names, overview preservation")
    finally:
        for plugin in reversed(loaded):
            ok("plugin", "unload", str(plugin))


if __name__ == "__main__":
    main()
