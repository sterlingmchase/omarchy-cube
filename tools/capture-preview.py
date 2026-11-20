#!/usr/bin/env python3
"""Capture real plugin rendering with generated demo windows in an owned headless compositor.

Development-only: Hyprland, Foot, Grim, Pillow and the mouse-test build dependencies.
Never captures or changes the personal desktop. Run from a built checkout.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    screenshots = ROOT / 'docs/screenshots'
    screenshots.mkdir(parents=True, exist_ok=True)
    children = []
    with (build / 'preview-nested.log').open('w') as log:
        compositor = subprocess.Popen(['Hyprland', '--config', str(ROOT / 'tests/nested.lua')],
                                     env=os.environ | {'AQ_BACKEND': 'headless'}, stdout=log, stderr=log)
        try:
            for _ in range(50):
                instances = json.loads(subprocess.check_output(['hyprctl', 'instances', '-j']))
                instance = next((i for i in instances if i['pid'] == compositor.pid), None)
                if instance:
                    break
                time.sleep(.1)
            assert instance, 'Preview compositor did not start'

            def ctl(*args):
                assert str(ROOT / 'tests/nested.lua').encode() in Path(f'/proc/{compositor.pid}/cmdline').read_bytes().split(b'\0')
                return subprocess.check_output(['hyprctl', '-i', instance['instance'], *args], text=True, timeout=15).strip()

            def ok(*args):
                result = ctl(*args)
                assert result == 'ok', result

            ctl('output', 'create', 'headless', 'CUBE-test')
            for monitor in json.loads(ctl('monitors', '-j')):
                if monitor['name'] != 'CUBE-test':
                    ctl('output', 'remove', monitor['name'])
            ok('eval', 'hl.monitor({output="CUBE-test",mode="3840x2160@60",position="0x0",scale=1}); hl.dispatch(hl.dsp.focus({monitor="CUBE-test"}))')
            for ws in range(1, 5):
                ok('eval', 'hl.dispatch(hl.dsp.focus({workspace=%d})); hl.dispatch(hl.dsp.workspace.move({workspace="%d",monitor="CUBE-test"}))' % (ws, ws))
            ok('plugin', 'load', str(build / 'omarchy-cube.so'))
            settings = ('hl.config({general={col={active_border={colors={"rgba(cba6f7ff)"},angle=0}}},'
                        'plugin={cube={workspace_count=4,zoom=1.05,show_labels=true,highlight_selected=true,'
                        'face_curvature=0,duration_ms=600,workspace_name_1="Code",workspace_name_2="Build",'
                        'workspace_name_3="Design",workspace_name_4="Terminal",skydome_path=' +
                        json.dumps(str(ROOT / 'shell/assets/skydomes/orbital.jpg')) + ',skydome_brightness=0.85}}})')
            ok('eval', settings)
            env = os.environ | {'WAYLAND_DISPLAY': instance['wl_socket'], 'HYPRLAND_INSTANCE_SIGNATURE': instance['instance']}
            blocks = [
                ('CODE', ['// A lightweight workspace cube', '', 'Background  >  bounded parallax', 'Selection   >  theme-colored glow', 'Geometry    >  optional curved faces', '', 'Flat by default. Yours to customize.']),
                ('BUILD', ['$ make -j2', 'Native plugin compiled', '', '$ make test', 'Geometry and file tests passed', '', '$ python3 tests/settings.py', 'Settings validated']),
                ('DESIGN', ['ORBITAL', '', 'Indigo cloud relief', 'Lavender light', 'Warm golden rings', '', 'Four built-in looks. Offline.']),
                ('TERMINAL', ['OMARCHY CUBE', '', 'Super + Ctrl + Alt + Up', '    Open workspace overview', '', 'Drag to rotate and tilt.', 'Click a face to land.']),
            ]
            for ws, (title, lines) in enumerate(blocks, 1):
                ok('eval', 'hl.dispatch(hl.dsp.focus({workspace=%d}))' % ws)
                text = '\033[2J\033[H\033[38;2;203;166;247m\n    ' + title + '\033[0m\n\n'
                text += ''.join('    ' + line + '\n\n' for line in lines)
                code = 'import sys,time;sys.stdout.write(' + repr(text) + ');sys.stdout.flush();time.sleep(180)'
                children.append(subprocess.Popen(['foot', '-c', '/dev/null', '-o', 'font=monospace:size=40',
                    '-o', 'colors.background=1e1e2e', '-o', 'colors.foreground=cdd6f4', '--title',
                    'Omarchy Cube demo — ' + title, 'python3', '-c', code], env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                time.sleep(.35)
            ok('eval', 'hl.dispatch(hl.dsp.focus({workspace=1}))')
            spec = importlib.util.spec_from_file_location('mouse_fixture', ROOT / 'tests/mouse.py')
            fixture = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fixture)
            pointer = fixture.build()
            ok('eval', 'local ok,err=hl.plugin.cube.rotate("overview"); assert(ok,err)')
            time.sleep(.4)
            monitor = next(m for m in json.loads(ctl('monitors', '-j')) if m['name'] == 'CUBE-test')
            width, height = monitor['width'], monitor['height']
            drag = subprocess.Popen([str(pointer), instance['wl_socket'], 'move', str(width//2), str(height//2), str(width), str(height),
                            'down', 'wait', '30', 'move', str(round(width*.60)), str(round(height*.54)), str(width), str(height), 'wait', '1000', 'up'])
            children.append(drag)
            time.sleep(.35)
            for name, curve in [('cube', None), ('curvature', .8)]:
                if curve is not None:
                    assert drag.wait(timeout=5) == 0, 'Demo drag failed'
                    ok('eval', 'local ok,err=hl.plugin.cube.rotate("cancel"); assert(ok,err); hl.config({plugin={cube={face_curvature=.8}}})')
                    ok('eval', 'local ok,err=hl.plugin.cube.rotate("overview"); assert(ok,err)')
                    time.sleep(.4)
                full = build / ('preview-' + name + '-full.png')
                subprocess.run(['grim', '-o', 'CUBE-test', str(full)], env=env, check=True, timeout=10)
                with Image.open(full) as image:
                    # Crop a narrow margin containing the nested-compositor startup
                    # warning; the plugin rendering is otherwise unmodified.
                    image = image.crop((48, 54, image.width-48, image.height))
                    image.resize((1920, 1080), Image.Resampling.LANCZOS).save(screenshots / (name + '.png'), optimize=True)
            assert not ctl('configerrors')
            print('Captured real 4K native rendering, delivered at 1920×1080; demo content only.')
        finally:
            for child in children:
                child.terminate()
            compositor.terminate()
            compositor.wait(timeout=10)


if __name__ == '__main__':
    main()
