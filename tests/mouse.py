#!/usr/bin/env python3
"""Mouse regression suite; --display must name the isolated tests/nested.lua instance.

Run: python3 tests/mouse.py --display wayland-N
Build only (no compositor interaction): python3 tests/mouse.py --build-only
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
# Official swaywm/wlr-protocols unstable/wlr-virtual-pointer-unstable-v1.xml;
# descriptions removed, protocol declarations and copyright preserved.
PROTOCOL = '<protocol name="wlr_virtual_pointer_unstable_v1"><copyright>\n    Copyright © 2019 Josef Gajdusek\n\n    Permission is hereby granted, free of charge, to any person obtaining a\n    copy of this software and associated documentation files (the "Software"),\n    to deal in the Software without restriction, including without limitation\n    the rights to use, copy, modify, merge, publish, distribute, sublicense,\n    and/or sell copies of the Software, and to permit persons to whom the\n    Software is furnished to do so, subject to the following conditions:\n\n    The above copyright notice and this permission notice (including the next\n    paragraph) shall be included in all copies or substantial portions of the\n    Software.\n\n    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL\n    THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING\n    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER\n    DEALINGS IN THE SOFTWARE.\n  </copyright><interface name="zwlr_virtual_pointer_v1" version="2"><enum name="error"><entry name="invalid_axis" value="0" /><entry name="invalid_axis_source" value="1" /></enum><request name="motion"><arg name="time" type="uint" /><arg name="dx" type="fixed" /><arg name="dy" type="fixed" /></request><request name="motion_absolute"><arg name="time" type="uint" /><arg name="x" type="uint" /><arg name="y" type="uint" /><arg name="x_extent" type="uint" /><arg name="y_extent" type="uint" /></request><request name="button"><arg name="time" type="uint" /><arg name="button" type="uint" /><arg name="state" type="uint" enum="wl_pointer.button_state" /></request><request name="axis"><arg name="time" type="uint" /><arg name="axis" type="uint" enum="wl_pointer.axis" /><arg name="value" type="fixed" /></request><request name="frame" /><request name="axis_source"><arg name="axis_source" type="uint" enum="wl_pointer.axis_source" /></request><request name="axis_stop"><arg name="time" type="uint" /><arg name="axis" type="uint" enum="wl_pointer.axis" /></request><request name="axis_discrete"><arg name="time" type="uint" /><arg name="axis" type="uint" enum="wl_pointer.axis" /><arg name="value" type="fixed" /><arg name="discrete" type="int" /></request><request name="destroy" type="destructor" since="1" /></interface><interface name="zwlr_virtual_pointer_manager_v1" version="2"><request name="create_virtual_pointer"><arg name="seat" type="object" interface="wl_seat" allow-null="true" /><arg name="id" type="new_id" interface="zwlr_virtual_pointer_v1" /></request><request name="destroy" type="destructor" since="1" /><request name="create_virtual_pointer_with_output" since="2"><arg name="seat" type="object" interface="wl_seat" allow-null="true" /><arg name="output" type="object" interface="wl_output" allow-null="true" /><arg name="id" type="new_id" interface="zwlr_virtual_pointer_v1" /></request></interface></protocol>'


def build():
    target = ROOT / "build"
    target.mkdir(exist_ok=True)
    xml = target / "pointer.xml"
    xml.write_text(PROTOCOL)
    for kind, name in (("client-header", "pointer-protocol.h"), ("private-code", "pointer-protocol.c")):
        subprocess.run(["wayland-scanner", kind, str(xml), str(target / name)], check=True)
    flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "wayland-client"], text=True))
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(target),
                    str(ROOT / "tests/pointer.c"), str(target / "pointer-protocol.c"),
                    "-o", str(target / "pointer"), *flags], check=True)
    return target / "pointer"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    options = parser.parse_args()
    pointer = build()
    if options.build_only:
        print("PASS: built bounded virtual pointer driver")
        return
    if not options.display:
        parser.error("--display is required; refusing to use the personal desktop")
    instances = json.loads(subprocess.check_output(["hyprctl", "instances", "-j"]))
    matches = [i for i in instances if i["wl_socket"] == options.display]
    assert len(matches) == 1, "Explicit test display does not identify one compositor"
    instance = matches[0]

    def guard():
        args = Path(f"/proc/{instance['pid']}/cmdline").read_bytes().split(b"\0")
        assert str(ROOT / "tests/nested.lua").encode() in args, "Refusing non-fixture compositor"

    def ctl(*args):
        guard()
        result = subprocess.run(["hyprctl", "-i", instance["instance"], *args], capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.strip()

    def ok(*args):
        result = ctl(*args)
        assert result == "ok", result

    def rotate(direction):
        ok("eval", f"local ok, err = hl.plugin.cube.rotate({json.dumps(direction)}); assert(ok, err)")

    def status():
        return dict(re.findall(r"(\w+)=([^ ]+)", ctl("omarchy-cube:status")))

    def workspace():
        return json.loads(ctl("activeworkspace", "-j"))["id"]

    def mouse(*actions, settle=.35):
        guard()
        actions = list(actions)
        for i, value in enumerate(actions):
            if value == "move":
                actions[i+1:i+5] = [actions[i+1] + monitor["x"] - origin_x, actions[i+2] + monitor["y"] - origin_y, bounds_width, bounds_height]
        subprocess.run([str(pointer), options.display, *map(str, actions)], check=True, timeout=15)
        time.sleep(settle)

    def overview():
        rotate("overview")
        time.sleep(.3)
        current = status()
        assert current["overview"] == "true", current
        return int(current["selected"])

    if options.headless:
        assert not any(m["name"] == "CUBE-test" for m in json.loads(ctl("monitors", "-j")))
        ok("eval", 'hl.dispatch(hl.dsp.focus({workspace=99}))')
        ctl("output", "create", "headless", "CUBE-test")
        for ws in range(1, 5):
            ok("eval", f'hl.dispatch(hl.dsp.focus({{workspace={ws}}})); hl.dispatch(hl.dsp.workspace.move({{workspace="{ws}",monitor="CUBE-test"}}))')
        ok("eval", 'hl.dispatch(hl.dsp.focus({monitor="CUBE-test"}))')
    monitors = json.loads(ctl("monitors", "-j"))
    assert options.headless or len(monitors) == 1, "Use a fresh single-output fixture or --headless"
    monitor = next(m for m in monitors if m["name"] == "CUBE-test") if options.headless else monitors[0]
    assert monitor["transform"] == 0, monitor
    origin_x = min(m["x"] for m in monitors)
    origin_y = min(m["y"] for m in monitors)
    bounds_width = max(m["x"] + round(m["width"] / m["scale"]) for m in monitors) - origin_x
    bounds_height = max(m["y"] + round(m["height"] / m["scale"]) for m in monitors) - origin_y
    width = round(monitor["width"] / monitor["scale"])
    height = round(monitor["height"] / monitor["scale"])
    center = ("move", width // 2, height // 2, width, height)
    so = str(ROOT / "build/omarchy-cube.so")
    child = None
    reports = ROOT / "build/mouse-reports.bin"
    try:
        if "Omarchy Cube" in ctl("plugin", "list"):
            ok("plugin", "unload", so)
        ok("plugin", "load", so)
        ok("eval", "hl.config({animations={enabled=true},plugin={cube={workspace_count=4,duration_ms=240}}}); hl.dispatch(hl.dsp.focus({workspace=1}))")
        reports.write_bytes(b"")
        # Foot reports any leaked mouse presses to this bounded child, not a shell.
        code = ("import os,tty; tty.setraw(0); os.write(1,b'\\x1b[?1000h\\x1b[?1006h'); "
                f"f=open({str(reports)!r},'ab',buffering=0); "
                "exec('while True: f.write(os.read(0,1024))')")
        env = os.environ | {"WAYLAND_DISPLAY": options.display, "HYPRLAND_INSTANCE_SIGNATURE": instance["instance"]}
        child = subprocess.Popen(["foot", "--title", "Cube mouse sink", "python3", "-c", code], env=env)
        for _ in range(30):
            if any(c["title"] == "Cube mouse sink" for c in json.loads(ctl("clients", "-j"))):
                break
            time.sleep(.1)
        else:
            raise AssertionError("Mouse sink window did not open")
        time.sleep(.3)
        start = workspace()
        ok("eval", 'hl.config({plugin={cube={horizontal_sensitivity=2,vertical_sensitivity=0.5,invert_horizontal=true,invert_vertical=true}}})')
        overview()
        mouse(*center, "down", "wait", 20, "move", round(width*.4), round(height*.4), width, height, settle=0)
        tuned = status()
        assert -.65 < float(tuned["angle"]) < -.5 and -.13 < float(tuned["pitch"]) < -.07, tuned
        mouse("up")
        rotate("cancel")
        ok("eval", 'hl.config({plugin={cube={horizontal_sensitivity=1,vertical_sensitivity=1,invert_horizontal=false,invert_vertical=false}}})')
        for momentum, offset in ((False, 1), (True, 2)):
            ok("eval", 'hl.config({plugin={cube={momentum=' + str(momentum).lower() + '}}})')
            overview()
            mouse(*center, "down", "wait", 20,
                  "move", round(width*.42), height//2, width, height, "wait", 20,
                  "move", round(width*.34), height//2, width, height, "wait", 20,
                  "move", round(width*.26), height//2, width, height, "up")
            assert int(status()["selected"]) == (start - 1 + offset) % 4 + 1, status()
            rotate("cancel")
        ok("eval", 'hl.config({plugin={cube={momentum=false}}})')
        rotate("drag")
        initial_zoom = float(status()["zoom"])
        time.sleep(.07)
        middle_zoom = float(status()["zoom"])
        rotate("right")
        assert float(status()["zoom"]) >= middle_zoom, "Rotation restarted the entry zoom"
        time.sleep(.25)
        final_zoom = float(status()["zoom"])
        assert 0 <= initial_zoom < middle_zoom < final_zoom, (initial_zoom, middle_zoom, final_zoom)
        rotate("cancel")
        for end_y, label in ((0, "top"), (height - 1, "bottom")):
            overview()
            mouse(*center, "down", "move", width // 2, end_y, width, height, "up")
            tilted = status()
            pitch = float(tilted["pitch"])
            assert .7 < abs(pitch) <= math.pi / 4 + .0001, tilted
            assert workspace() == start and int(tilted["selected"]) == start, tilted
            subprocess.run(["grim", "-o", monitor["name"], str(ROOT / f"build/tilt-{label}.png")], env=env, check=True, timeout=10)
            distance = 3 + float(tilted["zoom"])
            ndc_y = -2 * math.sin(pitch) / (distance - math.cos(pitch))
            mouse("move", width // 2, round(height * (1 + ndc_y) / 2), width, height, "down", "up")
            assert status()["overview"] == "false" and workspace() == start, "Tilted face click missed"
        # Start dragging through a mouse binding, before overview owns input.
        ok("eval", 'hl.bind("mouse:272", function() hl.plugin.cube.rotate("drag") end)')
        mouse(*center, "down", "wait", 30, "move", width // 8, height // 8, width, height, "wait", 220, "up", settle=0)
        released = status()
        assert released["active"] == "true" and released["overview"] == "false", released
        time.sleep(.07)
        landing = status()
        assert 0 < float(landing["zoom"]) < float(released["zoom"]), (released, landing)
        assert 0 < abs(float(landing["pitch"])) < abs(float(released["pitch"])), (released, landing)
        assert abs(float(landing["angle"]) - float(landing["target"])) < abs(float(released["angle"]) - float(released["target"])), (released, landing)
        time.sleep(.25)
        assert status()["active"] == "false", "Landing animation did not finish"
        assert float(status()["pitch"]) == 0, "Landing did not level the cube"
        assert status()["overview"] == "false" and workspace() == start % 4 + 1, (status(), workspace())
        assert reports.read_bytes() == b"", "Activation drag leaked"
        start = workspace()
        mouse(*center, "down", "wait", 30, "up")
        assert status()["overview"] == "false" and workspace() == start, "Click without dragging changed workspace"
        mouse(*center, "down", "wait", 30, "move", width // 8, height // 2, width, height,
              "rightdown", "rightup", "up")
        assert status()["overview"] == "false" and workspace() == start, "Cancelled activation drag committed"
        ok("eval", 'hl.unbind("mouse:272")')
        overview()
        rotate("cancel")
        assert status()["overview"] == "false" and workspace() == start
        overview()
        mouse(*center, "down", "wait", 30, "up", settle=0)
        assert status()["active"] == "true" and status()["overview"] == "false", "Face click snapped instead of animating"
        time.sleep(.3)
        assert status()["overview"] == "false" and workspace() == start
        selected = overview()
        mouse(*center, "scroll", 1)
        assert status()["overview"] == "true" and int(status()["selected"]) != selected, status()
        rotate("cancel")
        selected = overview()
        mouse(*center, "down", "wait", 30, "move", width // 8, height // 2, width, height, "wait", 30, "up")
        assert status()["overview"] == "true", status()
        assert int(status()["selected"]) != selected, status()
        assert workspace() == start, "Drag committed before acceptance"
        rotate("cancel")
        overview()
        rotate("right")
        time.sleep(.35)
        selected = int(status()["selected"])
        mouse(*center, "down", "wait", 30, "up")
        assert status()["overview"] == "false" and workspace() == selected, (status(), workspace(), selected)
        start = workspace()
        overview()
        rotate("right")
        mouse(*center, "rightdown", "wait", 30, "rightup")
        assert status()["overview"] == "false" and workspace() == start
        assert reports.read_bytes() == b"", "Underlying client received mouse events"
        # Keyboard alternatives must be consumed by the overview as well.
        overview()
        guard()
        subprocess.run(["wtype", "-k", "Escape"], env=env, check=True, timeout=10)
        time.sleep(.1)
        assert status()["overview"] == "false" and workspace() == start
        overview()
        guard()
        subprocess.run(["wtype", "-k", "Right"], env=env, check=True, timeout=10)
        time.sleep(.2)
        selected = int(status()["selected"])
        assert status()["overview"] == "true" and selected == start % 4 + 1, 'Right key did not rotate the overview'
        guard()
        subprocess.run(["wtype", "-k", "Return"], env=env, check=True, timeout=10)
        time.sleep(.1)
        assert status()["overview"] == "false" and workspace() == selected
        start = workspace()
        assert reports.read_bytes() == b"", "Underlying client received keyboard events"
        overview()
        time.sleep(.3)
        before = int(status()["draws"])
        time.sleep(.5)
        # Client damage/cursor updates may redraw a static cube; a frame loop would draw ~30 times.
        assert int(status()["draws"]) - before <= 3, "Stationary overview redraws continuously"
        rotate("cancel")
        # One Lua call keeps all repeats inside one animation duration.
        ok("eval", 'for _=1,3 do local ok, err=hl.plugin.cube.rotate("right"); assert(ok,err) end')
        time.sleep(.4)
        assert workspace() == (start - 1 + 3) % 4 + 1, workspace()
        assert status()["active"] == "false", status()
        start = workspace()
        ok("eval", 'local ok,err=hl.plugin.cube.rotate("right"); assert(ok,err); ok,err=hl.plugin.cube.rotate("left"); assert(ok,err)')
        time.sleep(.4)
        assert workspace() == start and status()["active"] == "false", (workspace(), status())
        rotate("right")
        time.sleep(.08)
        before = float(status()["angle"])
        rotate("right")
        after = float(status()["angle"])
        assert abs(after-before) < .35, (before, after)
        time.sleep(.4)
        start = workspace()
        overview()
        ok("plugin", "unload", so)
        assert workspace() == start
        assert "Omarchy Cube" not in ctl("plugin", "list")
        print("PASS: overview cancel, scroll, drag, face click, right-click cancel, input isolation, rapid repeats/reversal, unload")
    finally:
        if child is not None:
            child.terminate()
            child.wait(timeout=5)
        if "Omarchy Cube" in ctl("plugin", "list"):
            ok("plugin", "unload", so)
        if options.headless:
            ctl("output", "remove", "CUBE-test")


if __name__ == "__main__":
    main()
