# Experimental face-curvature prototype

## Scope

`face_curvature` ranges from −1 (concave) through 0 (flat, default) to +1 (convex).
This is a horizontal bow, not a sphere or a true spherical workspace layout.
Twenty-four strips / forty-eight triangles per curved face reuse the existing
workspace snapshot. The shared static vertex buffer is 1,184 bytes including the
original quad. Zero retains the original flat draw path. The bend eases out when
landing. Strength scales down for high face counts to avoid crossing neighbors.

Hit testing intersects the exact rendered strip planes, including per-strip
camera-facing rejection, and returns matching texture coordinates for window
selection/carry. The GL front-face convention is set explicitly and restored.
Curved silhouettes disable the flat-only backdrop occlusion shortcut and use an
interior pass; this opt-in mode does more rendering work than flat. No new idle
animation, image layer, per-strip workspace capture or timer is introduced.

## Evidence

- Native build against the pinned Hyprland 0.56.2 commit passed.
- ASan/UBSan geometry/file tests passed, including 5,625 curved-surface projection/
  hit-test round trips across 4/5/8/12/20 faces, both curvature signs, rotations,
  UV positions and tilt through ±45°; bounds/nonfinite checks also passed.
- 36 Python settings/presets/installer/setup tests passed. New tests cover curvature
  limits, old custom presets missing curvature, saving new curved presets, and
  upgrading the previous v2 data-only Lua parser without losing user code.
- Full screenshot-enabled 4K flat-default integration passed: rendering, labels,
  glow, backdrop orientation, switching, reduced motion, idle, stress and unload.
- Dedicated guarded native curvature suite passed in a disposable headless
  compositor: concave/flat/convex screenshots at 4/10/20 faces, clicking inside an
  expanded convex silhouette, rejecting clicks in a removed concave strip, and
  returning to flat. Curved screenshots were inspected directly.
- The render fixture was tightened to own one headless output: overlapping outputs
  initially caused wrong-monitor/blank captures. A strict static-overview counter
  probe also proved sensitive to compositor damage and was not retained as a
  curvature performance claim. Existing closed/idle integration remains passing.
- Omarchy manifest validation and whitespace checks passed.

There is no claimed physical-display FPS benchmark or native window-carry gesture
suite with nonzero curvature. Geometry UV round trips cover the coordinate mapping;
physical feel, readability and advanced carry behavior still deserve user testing.

## Compatibility

Old `cube-gui.lua` data files may omit curvature. The upgraded safe Lua parser
accepts the new numeric key while retaining the same format/marker. The installer
recognizes the exact prior v2 parser and upgrades it with backup/rollback. Old
custom presets lacking curvature retain the current setting on load; new saves
include it. Built-in appearance presets do not force a curvature setting.
