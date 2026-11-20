#!/usr/bin/env python3
"""Only exercise the nested compositor launched with this project's test config."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import struct
import zlib
from PIL import Image

root = Path(__file__).resolve().parents[1]
instances = json.loads(subprocess.check_output(['hyprctl', 'instances', '-j']))
instance = next(i for i in instances if str(root / 'tests/nested.lua').encode() in Path(f"/proc/{i['pid']}/cmdline").read_bytes().split(b'\0'))
def ctl(*args):
    if args[0] == 'dispatch':
        code = (f'hl.dispatch(hl.dsp.focus({{workspace={args[2]}}}))' if args[1] == 'workspace'
                else f'local ok, err = hl.plugin.cube.rotate({json.dumps(args[2])}); assert(ok, err)')
        args = ('eval', code)
    result = subprocess.run(['hyprctl', '-i', instance['instance'], *args], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()
def ok(*args):
    result = ctl(*args)
    assert result == 'ok', result

env = os.environ | {'WAYLAND_DISPLAY': instance['wl_socket'], 'HYPRLAND_INSTANCE_SIGNATURE': instance['instance']}
parser = argparse.ArgumentParser()
parser.add_argument('--highres', action='store_true')
parser.add_argument('--no-capture', action='store_true')
options = parser.parse_args()
if options.highres:
    ok('dispatch', 'workspace', '99')
    ctl('output', 'create', 'headless', 'CUBE-test')
    ok('eval', 'hl.monitor({output="CUBE-test",mode="3840x2160@60",position="1280x0",scale=1}); hl.dispatch(hl.dsp.focus({monitor="CUBE-test"}))')
    # Numbered workspace 1 can initially belong to the nested Wayland output.
    for ws in (1, 2, 3, 4):
        ok('eval', f'hl.dispatch(hl.dsp.focus({{workspace={ws}}}))')
        ok('eval', f'hl.dispatch(hl.dsp.workspace.move({{workspace="{ws}",monitor="CUBE-test"}}))')
    # On a headless backend, a default output can steal focus between timed
    # assertions. Keep just the owned 4K output; retain a Wayland nested window.
    for output in json.loads(ctl('monitors', '-j')):
        if output['name'].startswith('HEADLESS') and output['name'] != 'CUBE-test':
            ctl('output', 'remove', output['name'])
    ok('eval', 'hl.dispatch(hl.dsp.focus({monitor="CUBE-test"}))')
children = []
so = str(root / 'build/omarchy-cube.so')
try:
    if 'Omarchy Cube' in ctl('plugin', 'list'): ok('plugin', 'unload', so)
    ok('plugin', 'load', so)
    ok('eval', 'hl.config({animations={enabled=true},plugin={cube={workspace_count=4}}})')
    assert not ctl('configerrors'), ctl('configerrors')
    for ws in (1, 2):
        ok('dispatch', 'workspace', str(ws))
        children.append(subprocess.Popen(['foot', '--title', f'Cube workspace {ws}', 'sh', '-c', f'printf "\\033[4{ws}m\\033[2JWorkspace {ws}\\n"; sleep 120'], env=env))
        time.sleep(.3)
    ok('dispatch', 'workspace', '1')
    time.sleep(.3)
    # Omarchy changes follow_mouse when crossing tiled/floating workspace boundaries.
    ok('eval', 'hl.config({plugin={cube={duration_ms=600}}})')
    for direction, follow_mouse, target in [('right', 0, 2), ('left', 1, 1)]:
        ok('eval', f'local ok,err=hl.plugin.cube.rotate("{direction}"); assert(ok,err); hl.config({{input={{follow_mouse={follow_mouse}}}}})')
        assert 'active=true' in ctl('omarchy-cube:status'), 'Unrelated config refresh cancelled the turn'
        assert json.loads(ctl('activeworkspace', '-j'))['id'] == target
        time.sleep(.65)
        assert 'active=false' in ctl('omarchy-cube:status')
    ok('dispatch', 'omarchy-cube', 'overview')
    ok('eval', 'hl.config({input={follow_mouse=0}})')
    assert 'overview=true' in ctl('omarchy-cube:status'), 'Focus setting closed overview'
    ok('eval', 'hl.config({plugin={cube={enabled=false}}})')
    assert 'active=false' in ctl('omarchy-cube:status'), 'Disabling cube did not cancel it'
    ok('eval', 'hl.config({input={follow_mouse=0},plugin={cube={enabled=true,duration_ms=280}}})')
    if options.highres:
        output = next(m for m in json.loads(ctl('monitors', '-j')) if m['focused'])
        assert output['name'] == 'CUBE-test' and output['width'] == 3840 and output['height'] == 2160, output
    before = ctl('omarchy-cube:status')
    ok('dispatch', 'omarchy-cube', 'right')
    time.sleep(.09)
    if not options.no_capture:
        subprocess.run(['grim', '-o', next(m['name'] for m in json.loads(ctl('monitors', '-j')) if m['focused']), str(root / 'build/cube.png')], env=env, check=True, timeout=10)
    time.sleep(.4)
    after = ctl('omarchy-cube:status')
    assert 'active=false' in after, after
    assert after != before, (before, after)
    assert json.loads(ctl('activeworkspace', '-j'))['id'] == 2
    for direction in ('left', 'left', 'right'):
        ok('dispatch', 'omarchy-cube', direction)
        time.sleep(.4)
    assert json.loads(ctl('activeworkspace', '-j'))['id'] == 1
    assert 'ok' == ctl('eval', 'local ok, err = hl.plugin.cube.rotate("invalid"); assert(not ok and #err > 0)')
    ok('dispatch', 'omarchy-cube', 'right')
    ok('dispatch', 'omarchy-cube', 'cancel')
    assert 'active=false' in ctl('omarchy-cube:status')
    # A bounded, generated PNG tests the actual decoder/upload without external files.
    def png_chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    png = b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('!IIBBBBB', 4096, 2048, 8, 2, 0, 0, 0))
    row = b'\0' + bytes(channel for x in range(4096) for channel in (x // 16, 100, 255 - x // 16))
    png += png_chunk(b'IDAT', zlib.compress(row * 2048)) + png_chunk(b'IEND', b'')
    image = root / 'build/test-sky.png'
    image.write_bytes(png)
    ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(image)) + '}}})')
    assert 'sky_loaded=true' in ctl('omarchy-cube:status'), ctl('omarchy-cube:status')
    jpeg = root / 'build/test-sky.jpg'
    for mode, progressive in [('RGB', False), ('RGB', True), ('L', False)]:
        Image.new(mode, (512, 256), 100).save(jpeg, progressive=progressive)
        ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(jpeg)) + '}}})')
        assert 'sky_loaded=true' in ctl('omarchy-cube:status'), ctl('omarchy-cube:status')
    jpeg.write_bytes(jpeg.read_bytes()[:40])
    ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(jpeg)) + '}}})')
    assert 'sky_loaded=false' in ctl('omarchy-cube:status') and 'sky_error=none' not in ctl('omarchy-cube:status')
    for dimensions in [(6000, 4000), (9000, 1)]:
        Image.new('RGB', dimensions).save(jpeg)
        ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(jpeg)) + '}}})')
        assert 'sky_loaded=true' in ctl('omarchy-cube:status'), ctl('omarchy-cube:status')
        if dimensions == (6000, 4000):
            assert 'sky_width=4500 sky_height=3000' in ctl('omarchy-cube:status'), ctl('omarchy-cube:status')
    Image.new('RGB', (16385, 1)).save(jpeg)
    ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(jpeg)) + '}}})')
    assert 'sky_loaded=false' in ctl('omarchy-cube:status') and '16384' in ctl('omarchy-cube:status')
    if not options.no_capture:
        # A normal photo must show its outer corners, not a magnified spherical center crop.
        output = next(m for m in json.loads(ctl('monitors', '-j')) if m['focused'])
        photo_width, photo_height = 300, round(300 * output['height'] / output['width'])
        photo = Image.new('RGB', (photo_width, photo_height), (60, 60, 60))
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
        w, h = photo.size
        for color, box in zip(colors, [(0, 0, w//5, h//4), (4*w//5, 0, w, h//4),
                                       (0, 3*h//4, w//5, h), (4*w//5, 3*h//4, w, h)]):
            photo.paste(color, box)
        photo_path = root / 'build/photo-mapping.png'
        photo.save(photo_path)
        ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(photo_path)) + ',skydome_brightness=1,zoom=1.5}}})')
        ok('dispatch', 'omarchy-cube', 'overview')
        time.sleep(.4)
        output = next(m for m in json.loads(ctl('monitors', '-j')) if m['focused'])
        capture = root / 'build/photo-mapping-render.png'
        subprocess.run(['grim', '-o', output['name'], str(capture)], env=env, check=True, timeout=10)
        with Image.open(capture).convert('RGB') as rendered:
            for expected, (x, y) in zip(colors, [(0.05, 0.05), (0.95, 0.05), (0.05, 0.95), (0.95, 0.95)]):
                actual = rendered.getpixel((int(x * rendered.width), int(y * rendered.height)))
                assert all(abs(a-b) < 10 for a, b in zip(actual, expected)), (actual, expected)
        # Legacy mode values remain accepted, but all now use the aspect-correct backdrop.
        for mode in ('panorama', 'photo', 'auto'):
            ok('dispatch', 'omarchy-cube', 'cancel')
            ok('eval', 'hl.config({plugin={cube={skydome_mode="' + mode + '"}}})')
            ok('dispatch', 'omarchy-cube', 'overview')
            time.sleep(.4)
            subprocess.run(['grim', '-o', output['name'], str(capture)], env=env, check=True, timeout=10)
            with Image.open(capture).convert('RGB') as rendered:
                corner = rendered.getpixel((int(.05 * rendered.width), int(.05 * rendered.height)))
                red_corner = corner[0] > 240 and corner[1] < 10 and corner[2] < 10
                assert red_corner, (mode, corner)
        # Both texture decoders and all mappings must keep north/top above south/bottom.
        # A vertically uniform image cannot catch the panorama latitude inversion.
        orientation = Image.new('RGB', (512, 256), (240, 100, 20))
        orientation.paste((20, 160, 240), (0, 0, 512, 128))
        for extension in ('png', 'jpg'):
            fixture = root / ('build/sky-orientation.' + extension)
            orientation.save(fixture)
            for mapping in ('auto', 'panorama', 'photo'):
                ok('dispatch', 'omarchy-cube', 'cancel')
                ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(fixture)) +
                   ',skydome_mode="' + mapping + '",skydome_brightness=1,zoom=1.5}}})')
                ok('dispatch', 'omarchy-cube', 'overview')
                time.sleep(.4)
                subprocess.run(['grim', '-o', output['name'], str(capture)], env=env, check=True, timeout=10)
                with Image.open(capture).convert('RGB') as rendered:
                    for x in (.03, .97):
                        for y, expected in ((.08, (20, 160, 240)), (.92, (240, 100, 20))):
                            actual = rendered.getpixel((int(x * rendered.width), int(y * rendered.height)))
                            assert all(abs(a-b) < 12 for a, b in zip(actual, expected)), (extension, mapping, x, y, actual, expected)
        ok('dispatch', 'omarchy-cube', 'cancel')
        ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(photo_path)) + ',skydome_mode="auto"}}})')
        # Compare each adornment independently on an empty face, with stable snapshots.
        ok('dispatch', 'omarchy-cube', 'cancel')
        ok('dispatch', 'workspace', '4')
        shots = []
        for labels, outline in ((False, False), (True, False), (False, True)):
            ok('eval', 'hl.config({plugin={cube={show_labels=' + str(labels).lower() + ',highlight_selected=' + str(outline).lower() + '}}})')
            ok('dispatch', 'omarchy-cube', 'overview')
            time.sleep(.4)
            path = root / f'build/details-{int(labels)}-{int(outline)}.png'
            subprocess.run(['grim', '-o', output['name'], str(path)], env=env, check=True, timeout=10)
            with Image.open(path).convert('RGB') as shot:
                shots.append(shot.copy())
            ok('dispatch', 'omarchy-cube', 'cancel')
        from PIL import ImageChops
        for shot in shots[1:]:
            diff = ImageChops.difference(shots[0], shot)
            assert sum(n for n, rgb in diff.getcolors(diff.width * diff.height) if max(rgb) > 20) > 300, 'Adornment did not render'
        glow_diff = ImageChops.difference(shots[0], shots[2])
        run = longest = 0
        for y in range(glow_diff.height):
            run = run + 1 if max(glow_diff.getpixel((glow_diff.width // 2, y))) > 3 else 0
            longest = max(longest, run)
        assert longest >= 8, ('Selected edge has no soft halo beyond the crisp line', longest)
        assert max(glow_diff.getpixel((glow_diff.width // 2, glow_diff.height // 2))) <= 2, 'Glow obscures workspace center'
        ok('dispatch', 'workspace', '1')
        ok('eval', 'hl.config({plugin={cube={show_labels=true,highlight_selected=true,zoom=0.7,skydome_brightness=0.65}}})')
    image.write_bytes(b'not a PNG image')
    ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(image)) + '}}})')
    assert 'sky_loaded=false' in ctl('omarchy-cube:status') and 'sky_error=none' not in ctl('omarchy-cube:status')
    image.write_bytes(png)
    ok('eval', 'hl.config({plugin={cube={skydome_path=' + json.dumps(str(image)) + ',workspace_count=10}}})')
    assert 'sky_loaded=true' in ctl('omarchy-cube:status')
    ok('dispatch', 'workspace', '10')
    ok('dispatch', 'omarchy-cube', 'right')
    time.sleep(.35)
    assert json.loads(ctl('activeworkspace', '-j'))['id'] == 1
    ok('dispatch', 'omarchy-cube', 'left')
    time.sleep(.35)
    assert json.loads(ctl('activeworkspace', '-j'))['id'] == 10
    if not options.no_capture:
        ok('dispatch', 'omarchy-cube', 'right')
        time.sleep(.1)
        subprocess.run(['grim', '-o', next(m['name'] for m in json.loads(ctl('monitors', '-j')) if m['focused']), str(root / 'build/prism.png')], env=env, check=True, timeout=10)
        time.sleep(.35)
    # Benchmark the final default ten-face prism with a loaded skydome.
    settings = subprocess.run(['python3', str(root / 'shell/control.py'), 'read'], env=env, text=True, capture_output=True, check=True, timeout=15)
    assert json.loads(settings.stdout)['values']['workspace_count'] == 10
    samples = []
    for n in range(32):
        ok('dispatch', 'omarchy-cube', 'right')
        time.sleep(.32)
        sample = ctl('omarchy-cube:status')
        assert 'active=false' in sample, sample
        samples.append(sample)
    idle = ctl('omarchy-cube:status')
    time.sleep(.5)
    assert ctl('omarchy-cube:status') == idle, 'Cube draws while idle'
    ok('eval', 'hl.config({animations={enabled=false}})')
    ok('dispatch', 'omarchy-cube', 'left')
    assert ctl('omarchy-cube:status') == idle, 'Reduced motion rendered cube'
    ok('eval', 'hl.config({animations={enabled=true},plugin={cube={workspace_count=10}}})')
    for n in range(8):
        ok('dispatch', 'omarchy-cube', 'right')
        ok('plugin', 'unload', so)
        ok('plugin', 'load', so)
    ok('plugin', 'unload', so)
    if not options.no_capture:
        children.append(subprocess.Popen(['qs', '-p', str(root / 'tests/dock.qml')], env=env))
        time.sleep(.8)
        ok('plugin', 'load', so)
        ok('eval', 'hl.config({plugin={cube={workspace_count=4}}})')
        def dock_pixels():
            output = next(m for m in json.loads(ctl('monitors', '-j')) if m['focused'])
            path = root / 'build/dock-capture.png'
            subprocess.run(['grim', '-o', output['name'], str(path)], env=env, check=True, timeout=10)
            with Image.open(path).convert('RGB') as capture:
                return sum(n for n, rgb in capture.getcolors(capture.width * capture.height)
                           if (rgb[0] > 180 and rgb[1] < 20 and rgb[2] > 180)
                           or (rgb[0] < 20 and rgb[1] > 180 and rgb[2] > 180))
        assert any(c['workspace']['id'] == 1 for c in json.loads(ctl('clients', '-j'))), 'Populated fixture exited'
        assert not any(c['workspace']['id'] == 4 for c in json.loads(ctl('clients', '-j'))), 'Empty fixture has windows'
        for workspace in (1, 4):
            ok('dispatch', 'workspace', str(workspace))
            time.sleep(.35)
            assert dock_pixels() > 5000, 'Test dock is not visible before cube'
            ok('dispatch', 'omarchy-cube', 'overview')
            time.sleep(.35)
            assert dock_pixels() == 0, 'Dock was baked into cube snapshots'
            ok('dispatch', 'omarchy-cube', 'right')
            time.sleep(.2)
            assert dock_pixels() == 0, 'Dock appeared on newly captured face'
            ok('dispatch', 'omarchy-cube', 'cancel')
            time.sleep(.2)
            assert dock_pixels() > 5000, 'Dock did not return after cube'
        ok('plugin', 'unload', so)
    (root / ('build/performance-4k.txt' if options.highres else 'build/performance.txt')).write_text('\n'.join(samples) + '\n')
    print('PASS: rendering, switching/wrap, cancellation, invalid input, reduced motion, idle, stress, unload during animation; ' + samples[-1])
finally:
    if options.highres: ctl('output', 'remove', 'CUBE-test')
    for child in children:
        child.terminate()
        child.wait(timeout=5)
