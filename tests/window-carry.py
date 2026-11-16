#!/usr/bin/env python3
"""Guarded window carry regression; only accepts the tests/nested.lua compositor.

Run: python3 tests/window-carry.py --display wayland-N
Build only: python3 tests/window-carry.py --build-only
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from mouse import ROOT, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--display')
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--screenshot', action='store_true')
    args = parser.parse_args()
    pointer = build()
    if args.build_only:
        print('PASS: built bounded virtual pointer driver')
        return
    if not args.display:
        parser.error('--display is required; refusing to use the personal desktop')
    matches = [i for i in json.loads(subprocess.check_output(['hyprctl', 'instances', '-j']))
               if i['wl_socket'] == args.display]
    assert len(matches) == 1, 'Explicit display must identify exactly one compositor'
    instance = matches[0]

    def guard():
        command = Path(f"/proc/{instance['pid']}/cmdline").read_bytes().split(b'\0')
        assert str(ROOT / 'tests/nested.lua').encode() in command, 'Refusing non-fixture compositor'

    def ctl(*words):
        guard()
        result = subprocess.run(['hyprctl', '-i', instance['instance'], *words], capture_output=True,
                                text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.strip()

    def ok(*words):
        result = ctl(*words)
        assert result == 'ok', result

    def config(settings):
        ok('eval', 'hl.config({plugin={cube={' + settings + '}}})')

    def rotate(direction):
        ok('eval', f'local ok,err=hl.plugin.cube.rotate({json.dumps(direction)}); assert(ok,err)')

    def status():
        return dict(re.findall(r'(\w+)=([^ ]+)', ctl('omarchy-cube:status')))

    def clients():
        return {c['title']: c for c in json.loads(ctl('clients', '-j'))}

    def locations():
        return {title: c['workspace']['id'] for title, c in clients().items() if title.startswith('Cube carry ')}

    def mouse(*actions, settle=.08):
        actions = list(actions)
        if actions and actions[0] == 'move':
            actions[1:5] = [monitor['x'] - origin_x + actions[1], monitor['y'] - origin_y + actions[2], bounds_width, bounds_height]
        guard()
        subprocess.run([str(pointer), args.display, *map(str, actions)], check=True, timeout=15)
        time.sleep(settle)

    def keyboard(*keys):
        guard()
        subprocess.run(['wtype', *keys], env=env, check=True, timeout=10)
        time.sleep(.08)

    def overview(title, shifted=True, feedback=False):
        rotate('overview')
        time.sleep(.35)
        assert status()['overview'] == 'true', status()
        c = clients()[title]
        # At zero rotation/pitch, invert the front-face projection to its window center.
        distance = 2 + float(status()['zoom'])
        x = round(width / 2 + (c['at'][0] + c['size'][0] / 2 - monitor['x'] - width / 2) * 2 / distance)
        y = round(height / 2 + (c['at'][1] + c['size'][1] / 2 - monitor['y'] - height / 2) * 2 / distance)
        mouse('move', x, y, width, height)
        held = None
        if shifted:
            guard()
            held = subprocess.Popen(['wtype', '-M', 'shift', '-s', '1000', '-m', 'shift'], env=env)
            inputs.append(held)
            time.sleep(.15)
        guard()
        gesture = subprocess.Popen([str(pointer), args.display,
            'move', str(monitor['x'] - origin_x + x), str(monitor['y'] - origin_y + y), str(bounds_width), str(bounds_height),
            'down', 'wait', '1000',
            'move', str(monitor['x'] - origin_x + round(x - width * .35 if x >= width * .35 else x + width * .35)), str(monitor['y'] - origin_y + y), str(bounds_width), str(bounds_height),
            *(['wait', '1000'] * (6 if feedback else 2)), 'up'])
        inputs.append(gesture)
        time.sleep(.1)
        return gesture, held

    def drag(point):
        deadline = time.monotonic() + 1.5
        while int(status()['selected']) == 1 and time.monotonic() < deadline:
            time.sleep(.04)
        assert int(status()['selected']) != 1, status()

    def release(point):
        gesture, held = point
        assert gesture.wait(timeout=10) == 0
        if held:
            assert held.wait(timeout=3) == 0
        time.sleep(.04)

    def reset():
        if status()['active'] == 'true':
            rotate('cancel')
        ok('eval', 'hl.dispatch(hl.dsp.focus({workspace=1}))')
        time.sleep(.45)

    assert not any(m['name'] == 'CUBE-test' for m in json.loads(ctl('monitors', '-j'))), 'Headless test output already exists'
    ok('eval', 'hl.dispatch(hl.dsp.focus({workspace=99}))')
    ctl('output', 'create', 'headless', 'CUBE-test')
    ok('eval', 'hl.monitor({output="CUBE-test",mode="3840x2160@60",position="1280x0",scale=1}); hl.dispatch(hl.dsp.focus({monitor="CUBE-test"}))')
    for workspace in (1, 2, 3, 4):
        ok('eval', f'hl.dispatch(hl.dsp.focus({{workspace={workspace}}})); hl.dispatch(hl.dsp.workspace.move({{workspace="{workspace}",monitor="CUBE-test"}}))')
    ok('eval', 'hl.dispatch(hl.dsp.focus({monitor="CUBE-test"}))')
    monitors = json.loads(ctl('monitors', '-j'))
    monitor = next(m for m in monitors if m['name'] == 'CUBE-test')
    assert monitor['transform'] == 0, monitor
    origin_x = min(m["x"] for m in monitors)
    origin_y = min(m["y"] for m in monitors)
    bounds_width = max(m['x'] + round(m['width'] / m['scale']) for m in monitors) - origin_x
    bounds_height = max(m['y'] + round(m['height'] / m['scale']) for m in monitors) - origin_y
    width, height = (round(monitor[k] / monitor['scale']) for k in ('width', 'height'))
    env = os.environ | {'WAYLAND_DISPLAY': args.display, 'HYPRLAND_INSTANCE_SIGNATURE': instance['instance']}
    so = str(ROOT / 'build/omarchy-cube.so')
    children = []
    inputs = []
    try:
        if 'Omarchy Cube' in ctl('plugin', 'list'):
            ok('plugin', 'unload', so)
        ok('plugin', 'load', so)
        config('workspace_count=4,duration_ms=220,momentum=false,carry_windows=false')
        assert status()['carrying'] == 'false', status()
        ok('eval', 'hl.dispatch(hl.dsp.focus({workspace=1}))')
        for name in ('chosen', 'bystander'):
            guard()
            children.append(subprocess.Popen(['foot', '--title', 'Cube carry ' + name, 'sleep', '300'], env=env))
        for _ in range(40):
            if len(locations()) == 2:
                break
            time.sleep(.1)
        assert len(locations()) == 2, clients()
        time.sleep(.4)
        title = 'Cube carry chosen'
        before = locations()
        point = overview(title)
        assert status()['carrying'] == 'false', 'Carry must default off'
        drag(point)
        release(point)
        assert locations() == before, 'Disabled carry moved a window'
        reset()
        config('carry_windows=true')
        point = overview(title, shifted=False)
        assert status()['carrying'] == 'false', 'Unmodified drag grabbed a window'
        drag(point)
        release(point)
        assert locations() == before
        reset()
        for cancel in ('Escape', 'right'):
            if args.screenshot and cancel == 'Escape':
                config('show_labels=false,highlight_selected=false')
            point = overview(title, feedback=args.screenshot and cancel == 'Escape')
            assert status()['carrying'] == 'true', ('Shift/window hit failed', status(), clients()[title])
            drag(point)
            assert locations() == before, 'Moved before release'
            if cancel == 'Escape':
                keyboard('-k', 'Return')
                assert status()['carrying'] == 'true' and locations() == before, ('Enter prematurely ended carry', status(), locations())
                if args.screenshot:
                    guard()
                    subprocess.run(['grim', '-o', 'CUBE-test', str(ROOT / 'build/carry-feedback.png')], env=env, check=True, timeout=10)
                keyboard('-k', 'Escape')
            else:
                mouse('rightdown', 'rightup')
            release(point)
            assert status()['active'] == 'false' and locations() == before, 'Cancellation moved a window'
            reset()
        for floating in (False, True):
            if floating:
                ok('eval', 'hl.dispatch(hl.dsp.window.float({window=' + json.dumps('address:' + clients()[title]['address']) + '}))')
                time.sleep(.25)
            point = overview(title)
            assert status()['carrying'] == 'true', status()
            drag(point)
            selected = int(status()['selected'])
            assert locations() == before, 'Moved before release'
            release(point)
            landed = status()
            assert landed['overview'] == 'false' and landed['carrying'] == 'false', landed
            assert locations() == {title: selected, 'Cube carry bystander': 1}, locations()
            time.sleep(.3)
            assert status()['active'] == 'false', status()
            ok('eval', 'hl.dispatch(hl.dsp.window.move({workspace=1,silent=true,window=' + json.dumps('address:' + clients()[title]['address']) + '}))')
            reset()
        # Retile the floater so it cannot obscure the source hit box below it.
        ok('eval', 'hl.dispatch(hl.dsp.window.float({window=' + json.dumps('address:' + clients()[title]['address']) + '}))')
        time.sleep(.4)
        assert clients()[title]['floating'] is False
        # A closed source must never move the surviving window or commit a workspace.
        title = 'Cube carry bystander'
        point = overview(title)
        assert status()['carrying'] == 'true', status()
        drag(point)
        children[1].terminate()
        children[1].wait(timeout=5)
        for _ in range(30):
            if title not in clients():
                break
            time.sleep(.1)
        assert title not in clients(), 'Source did not close'
        release(point)
        assert status()['active'] == 'false' and locations() == {'Cube carry chosen': 1}, (status(), locations())
        print('PASS: default-off, unmodified drag, Escape/right cancel, tiled/floating release-only single-window move, closed-source abort')
    finally:
        # Let bounded input clients release their keys/buttons before plugin cleanup.
        for child in inputs:
            child.wait(timeout=10)
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
        if 'Omarchy Cube' in ctl('plugin', 'list'):
            ok('plugin', 'unload', so)
        ctl('output', 'remove', 'CUBE-test')


if __name__ == '__main__':
    main()
