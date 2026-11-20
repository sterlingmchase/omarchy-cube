# Screenshots

These are actual plugin/UI captures, not concept renders.

- `cube.png` / root `preview.png`: native cube during a held drag, showing multiple
  workspace faces, selected-face edge glow and the image backdrop.
- `curvature.png`: opt-in convex geometry in the native plugin, with glow following
  the bent face edge. Flat remains the default.
- `presets.png`: tightly cropped capture of the real tabbed settings panel. No
  unrelated windows, private names, chats or desktop content are included.

Native screenshots use an owned headless Hyprland compositor, public demo terminal
content, and a maintainer-supplied generated background. They were captured at
3840×2160, cropped by a narrow margin to omit a nested-compositor startup warning,
and downsampled to 1920×1080. This is not an FPS benchmark or a claim that the
background art itself is native 4K. Artwork provenance is documented in
`../../shell/assets/skydomes/README.md`.

To reproduce the native scenes from a built checkout:

```sh
python3 tools/capture-preview.py
cp docs/screenshots/cube.png preview.png
```

The script starts and stops only its own compositor, checks its command line,
uses explicitly targeted IPC, creates fake demo terminal content, and never
captures the personal desktop. It requires Foot, Grim, Pillow and the mouse-test
Wayland build dependencies. The panel capture is separate and cropped manually.
