#!/usr/bin/env python3
"""On-demand settings bridge. Never imported by the compositor or run on a timer."""
import fcntl
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unicodedata

DEFAULTS = dict(enabled=True, trackpad_enabled=True, carry_windows=False, duration_ms=280, zoom=.7, workspace_count=10,
                show_labels=True, highlight_selected=True,
                horizontal_sensitivity=1.0, vertical_sensitivity=1.0,
                invert_horizontal=False, invert_vertical=False, momentum=False,
                skydome_enabled=True, skydome_path="", skydome_brightness=.65,
                skydome_mode="auto")
NAMES = {"workspace_name_" + str(i) for i in range(1, 21)}
DEFAULTS.update(("workspace_name_" + str(i), "") for i in range(1, 21))
PRESET_KEYS = set(DEFAULTS) - NAMES - {"enabled", "trackpad_enabled", "carry_windows", "workspace_count"}
PRESET_LIMIT = 32
PRESET_BYTES = 262144
RANGES = dict(duration_ms=(120, 600), zoom=(0, 1.5), workspace_count=(4, 20),
              horizontal_sensitivity=(.25, 3), vertical_sensitivity=(.25, 3),
              skydome_brightness=(.1, 1))
BOOLS = {"enabled", "trackpad_enabled", "carry_windows", "skydome_enabled", "show_labels", "highlight_selected",
         "invert_horizontal", "invert_vertical", "momentum"}
INTS = {"duration_ms", "workspace_count"}
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "hypr"
TARGET = CONFIG / "cube-gui.lua"
MARKER = "-- Omarchy Cube GUI settings v1\n"


def ctl(*args):
    result = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "hyprctl failed")
    return result.stdout.strip()


def validate(values):
    if not isinstance(values, dict) or set(values) != set(DEFAULTS):
        raise ValueError("Expected the complete Omarchy Cube settings object")
    for key, value in values.items():
        if key in BOOLS:
            if type(value) is not bool:
                raise ValueError(key + " must be a boolean")
        elif key in NAMES:
            validate_name(value, 80, empty=True)
        elif key == "skydome_mode":
            if value not in ("auto", "photo", "panorama"):
                raise ValueError("Skydome mode must be auto, photo or panorama")
        elif key == "skydome_path":
            if (not isinstance(value, str) or len(value.encode("utf-8")) > 4096
                    or "\0" in value or (value and (not Path(value).is_absolute()
                                                      or Path(value).suffix.lower() not in (".png", ".jpg", ".jpeg")))):
                raise ValueError("Skydome must be an absolute PNG or JPEG path or empty")
        elif key in INTS:
            if type(value) is not int or not RANGES[key][0] <= value <= RANGES[key][1]:
                raise ValueError("Out of range: " + key)
        elif (type(value) not in (int, float) or not math.isfinite(value)
              or not RANGES[key][0] <= value <= RANGES[key][1]):
            raise ValueError("Out of range: " + key)
    return values


def validate_name(name, limit=64, empty=False):
    if (not isinstance(name, str) or len(name) > limit or (not empty and not name.strip())
            or any(unicodedata.category(char) in ("Cc", "Cs") or char in "\u2028\u2029" for char in name)):
        raise ValueError("Name must be at most %d characters without control characters" % limit)
    return name


def presets(action, name=None, values=None):
    if action not in ("list", "save", "load", "delete"):
        raise ValueError("Unknown preset action")
    if action != "list":
        validate_name(name)
    if action == "save":
        validate(values)
    CONFIG.mkdir(parents=True, exist_ok=True)
    path = CONFIG / "cube-presets.json"
    with (CONFIG / ".cube-presets.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        saved = {}
        if path.exists():
            with path.open("rb") as stream:
                raw = stream.read(PRESET_BYTES + 1)
            if len(raw) > PRESET_BYTES:
                raise ValueError("Preset file is too large; existing file was preserved")
            try:
                saved = json.loads(raw)
                if not isinstance(saved, dict) or len(saved) > PRESET_LIMIT:
                    raise ValueError("Invalid preset collection")
                for label, settings in saved.items():
                    validate_name(label)
                    if not isinstance(settings, dict) or set(settings) != PRESET_KEYS:
                        raise ValueError("Invalid preset settings")
                    validate(dict(DEFAULTS, **settings))
            except (ValueError, TypeError) as error:
                raise ValueError("Invalid preset file; existing file was preserved: " + str(error)) from error
        if action == "load":
            if name not in saved:
                raise ValueError("Preset does not exist")
            return dict(presets=sorted(saved), values=saved[name])
        if action == "save":
            if name not in saved and len(saved) >= PRESET_LIMIT:
                raise ValueError("At most %d presets can be saved" % PRESET_LIMIT)
            saved[name] = {key: values[key] for key in DEFAULTS if key in PRESET_KEYS}
        elif action == "delete":
            if name not in saved:
                raise ValueError("Preset does not exist")
            del saved[name]
        if action in ("save", "delete"):
            content = json.dumps(saved, ensure_ascii=False, indent=2) + "\n"
            if len(content.encode("utf-8")) > PRESET_BYTES:
                raise ValueError("Preset file would be too large")
            atomic(path, content)
        return dict(presets=sorted(saved))


def lua_value(value):
    if isinstance(value, str):
        # Three-digit byte escapes are valid in Lua, including UTF-8 and path punctuation.
        return '"' + "".join("\\%03d" % byte for byte in value.encode("utf-8")) + '"'
    return json.dumps(value)


def encode(values):
    return MARKER + "return {\n" + "".join(
        f"  {key} = {lua_value(value)},\n" for key, value in values.items()) + "}\n"


def sky_problem(values, status):
    if values["skydome_enabled"] and values["skydome_path"]:
        if " sky_loaded=true " not in status or not status.endswith("sky_error=none"):
            error = status.partition(" sky_error=")[2] or "Image was not loaded"
            return "Skydome image error: " + error[:1024]
    return ""


def live(check_sky=False):
    status = ctl("omarchy-cube:status")
    if not status.startswith("active="):
        raise RuntimeError("Native Omarchy Cube is not loaded. Run make install and load examples/cube.lua first.")
    # hyprctl batch emits consecutive JSON documents, not a JSON array.
    raw = ctl("--batch", "-j", "; ".join("getoption plugin:cube:" + key for key in DEFAULTS))
    decoder = json.JSONDecoder()
    options = {}
    while raw.strip():
        option, end = decoder.raw_decode(raw.lstrip())
        raw = raw.lstrip()[end:]
        key = option["option"].removeprefix("plugin:cube:")
        if key not in DEFAULTS or key in options:
            raise RuntimeError("Unexpected or duplicate Omarchy Cube option in batch response")
        options[key] = option
    if set(options) != set(DEFAULTS):
        raise RuntimeError("Incomplete Omarchy Cube settings response")
    values = {}
    for key, default in DEFAULTS.items():
        option = options[key]
        field = ("str" if isinstance(default, str) else "bool" if key in BOOLS
                 else "int" if key in INTS else "float")
        value = option[field]
        if key in BOOLS and value not in (0, 1, False, True):
            raise RuntimeError("Invalid boolean option: " + key)
        values[key] = bool(value) if type(default) is bool else value
    values = validate(values)
    problem = sky_problem(values, status)
    if check_sky and problem:
        raise RuntimeError(problem)
    return values


def atomic(path, content):
    fd, name = tempfile.mkstemp(prefix=".cube-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def apply(values):
    values = validate(values)
    before = live()  # Refuse to change config if the native plugin is unavailable.
    errors = ctl("configerrors")
    if errors:
        raise RuntimeError("Fix existing Hyprland configuration errors before applying: " + errors)
    module = CONFIG / "cube.lua"
    if not module.exists() or "-- Omarchy Cube GUI bridge v2" not in module.read_text():
        raise RuntimeError("GUI configuration bridge missing. Run tools/install-gui first.")
    CONFIG.mkdir(parents=True, exist_ok=True)
    with (CONFIG / ".cube-gui.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = TARGET.read_text() if TARGET.exists() else None
        if previous is not None and not previous.startswith(MARKER):
            raise RuntimeError("Refusing to replace an unrecognized cube-gui.lua")
        if previous is not None:
            atomic(CONFIG / "cube-gui.lua.bak", previous)
        try:
            atomic(TARGET, encode(values))
            ctl("reload")
            errors = ctl("configerrors")
            if errors:
                raise RuntimeError(errors)
            actual = live(check_sky=True)
            if any(not (math.isclose(actual[k], v, abs_tol=1e-5) if type(v) in (int, float)
                        else actual[k] == v) for k, v in values.items()):
                raise RuntimeError("Another config overrides Omarchy Cube. Place hypr.cube last in hyprland.lua.")
        except Exception as original:
            if previous is None:
                TARGET.unlink(missing_ok=True)
            else:
                atomic(TARGET, previous)
            ctl("reload")
            rollback_errors = ctl("configerrors")
            if rollback_errors:
                raise RuntimeError("Settings restored, but Hyprland reports: " + rollback_errors)
            restored = live()
            if restored != before:
                raise RuntimeError("Configuration restored, but live settings differ; check Hyprland") from original
            raise
    return actual


def navigate(action):
    if action not in ("left", "right", "overview"):
        raise ValueError("Unknown cube control")
    ctl("eval", 'local ok, err = hl.plugin.cube.rotate("' + action + '"); assert(ok, err)')
    return live()


def pick_image():
    result = subprocess.run(["zenity", "--file-selection", "--title=Choose skydome image",
                             "--file-filter=PNG and JPEG images | *.[pP][nN][gG] *.[jJ][pP][gG] *.[jJ][pP][eE][gG]"],
                            capture_output=True, text=True, timeout=600)
    if result.returncode == 1:
        return None
    if result.returncode:
        raise RuntimeError("Could not open the image picker")
    path = result.stdout.removesuffix("\n")
    validate(dict(DEFAULTS, skydome_path=path))
    if not path or not Path(path).is_file():
        raise ValueError("Choose an existing PNG or JPEG image")
    return path


def main():
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "presets":
            action = sys.argv[2]
            expected = {"list": 3, "load": 4, "delete": 4, "save": 5}
            if len(sys.argv) != expected.get(action):
                raise ValueError("Usage: control.py presets list|load NAME|delete NAME|save NAME '<settings JSON>'")
            if action == "save" and len(sys.argv[4]) > 32768:
                raise ValueError("Settings payload too large")
            result = presets(action, sys.argv[3] if len(sys.argv) > 3 else None,
                             json.loads(sys.argv[4]) if action == "save" else None)
            print(json.dumps(dict(ok=True, **result)))
            return
        if len(sys.argv) == 2 and sys.argv[1] == "pick":
            print(json.dumps(dict(ok=True, path=pick_image())))
            return
        warning = ""
        if len(sys.argv) == 2 and sys.argv[1] == "read":
            values = live()
            warning = sky_problem(values, ctl("omarchy-cube:status"))
        elif len(sys.argv) == 3 and sys.argv[1] == "apply":
            if len(sys.argv[2]) > 32768:
                raise ValueError("Settings payload too large")
            values = apply(json.loads(sys.argv[2]))
        elif len(sys.argv) == 3 and sys.argv[1] == "navigate":
            values = navigate(sys.argv[2])
        else:
            raise ValueError("Usage: control.py read | navigate left|right|overview | apply '<settings JSON>'")
        print(json.dumps(dict(ok=True, values=values, warning=warning)))
    except Exception as error:
        print(json.dumps(dict(ok=False, error=str(error))))
        sys.exit(1)


if __name__ == "__main__":
    main()
