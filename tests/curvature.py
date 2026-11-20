#!/usr/bin/env python3
"""Curvature render/click checks. Refuses any compositor except tests/nested.lua."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--display', required=True)
    args = parser.parse_args()
    instances = json.loads(subprocess.check_output(['hyprctl', 'instances', '-j']))
    matches = [i for i in instances if i['wl_socket'] == args.display]
    assert len(matches) == 1
    instance = matches[0]

    def guard():
        assert str(ROOT / 'tests/nested.lua').encode() in Path(f"/proc/{instance['pid']}/cmdline").read_bytes().split(b'\0')

    def ctl(*command):
        guard()
        return subprocess.check_output(['hyprctl', '-i', instance['instance'], *command], text=True, timeout=15).strip()

    def ok(*command):
        result = ctl(*command)
        assert result == 'ok', result

    def rotate(action):
        ok('eval', f'local ok,err=hl.plugin.cube.rotate({json.dumps(action)}); assert(ok,err)')

    env = os.environ | {'WAYLAND_DISPLAY': args.display, 'HYPRLAND_INSTANCE_SIGNATURE': instance['instance']}
    spec = importlib.util.spec_from_file_location('mouse_fixture', ROOT / 'tests/mouse.py')
    mouse = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mouse)
    pointer = mouse.build()
    so = str(ROOT / 'build/omarchy-cube.so')
    guard()
    if 'Omarchy Cube' in ctl('plugin', 'list'):
        ok('plugin', 'unload', so)
    ctl('output', 'create', 'headless', 'CUBE-curve')
    # This fixture owns its outputs. Avoid focus-following races between overlapping
    # default headless outputs and the test output at the same logical origin.
    for monitor in json.loads(ctl('monitors', '-j')):
        if monitor['name'] != 'CUBE-curve':
            ctl('output', 'remove', monitor['name'])
    ok('eval', 'hl.monitor({output="CUBE-curve",mode="1600x1000@60",position="0x0",scale=1}); hl.dispatch(hl.dsp.focus({monitor="CUBE-curve"})); hl.dispatch(hl.dsp.focus({workspace=1}))')
    ok('eval', 'hl.dispatch(hl.dsp.workspace.move({workspace="1",monitor="CUBE-curve"})); hl.dispatch(hl.dsp.focus({workspace=1}))')
    ok('plugin', 'load', so)
    try:
        ok('eval', 'hl.config({animations={enabled=true},plugin={cube={show_labels=false,highlight_selected=true,zoom=1,skydome_path=""}}})')
        for count in (4, 10, 20):
            shots = []
            for curvature in (0, -1, 1):
                ok('eval', 'hl.config({plugin={cube={workspace_count=%d,face_curvature=%d}}})' % (count, curvature))
                rotate('overview')
                time.sleep(.4)
                path = ROOT / f'build/curvature-{count}-{curvature}.png'
                subprocess.run(['grim', '-o', 'CUBE-curve', str(path)], env=env, check=True, timeout=10)
                with Image.open(path) as image:
                    shots.append(image.convert('RGB'))
                rotate('cancel')
            for image in shots[1:]:
                diff = ImageChops.difference(shots[0], image)
                changed = sum(n for n, color in diff.getcolors(diff.width*diff.height) if max(color) > 12)
                assert changed > max(100, 2000/count), ('Curvature not visible', count, changed)
        # Verify selection in the narrow band where bent and flat silhouettes differ.
        # Uses the exact center of a strip vertex, so no mesh approximation is needed.
        monitors = json.loads(ctl('monitors', '-j'))
        output = next(m for m in monitors if m['name'] == 'CUBE-curve')
        origin_x, origin_y = min(m['x'] for m in monitors), min(m['y'] for m in monitors)
        extent_x = max(m['x'] + round(m['width']/m['scale']) for m in monitors) - origin_x
        extent_y = max(m['y'] + round(m['height']/m['scale']) for m in monitors) - origin_y
        for curvature in (-1, 1):
            ok('eval', 'hl.config({plugin={cube={workspace_count=4,face_curvature=%d,zoom=1}}})' % curvature)
            rotate('overview')
            time.sleep(.4)
            flat_top, curved_top = 2/3, 2/(3-.24*curvature)
            top = (flat_top + curved_top)/2
            width, height = round(output['width']/output['scale']), round(output['height']/output['scale'])
            x = output['x'] - origin_x + width//2
            y = output['y'] - origin_y + round((1-top)*height/2)
            guard()
            subprocess.run([str(pointer), args.display, 'move', str(x), str(y), str(extent_x), str(extent_y),
                            'down', 'wait', '20', 'up'], check=True, timeout=10)
            time.sleep(.4)
            status = ctl('omarchy-cube:status')
            assert ('overview=true' in status) == (curvature < 0), ('Bent face click mismatch', curvature, status)
            rotate('cancel')
        ok('eval', 'hl.config({plugin={cube={face_curvature=0}}})')
        assert not ctl('configerrors')
        print('PASS: concave/flat/convex rendering at 4/10/20 faces; curved silhouette click inclusion/exclusion; flat restore')
    finally:
        ok('plugin', 'unload', so)
        ctl('output', 'remove', 'CUBE-curve')


if __name__ == '__main__':
    main()
