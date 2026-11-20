# Changelog

## 0.3.0

- Guided, explicitly confirmed first-run native setup with compatibility checks,
  local build, dependency prompts, configuration backups and activation rollback.
  Existing native installations are not silently replaced. The exact Hyprland
  0.56.2 commit requirement remains unchanged.
- Wider tabbed settings: Cube, Controls, Background and Presets, with persistent
  Apply/status controls and pending edits preserved across tabs.
- Four built-in appearance presets, bundled generated illustrations, separate
  previews, and portable built-in image references in saved custom presets.
- Lightweight aspect-correct background parallax opposing rotation and tilt,
  respecting reduced motion. True spherical mapping has been retired: legacy
  `auto`, `photo` and `panorama` keys still parse, but now use the image backdrop.
- Selected-face theme-colored sharp edge and soft inward glow in the existing
  shader, without a blur pass or idle pulse.
- Experimental concave/convex horizontal face curvature with matching mesh hit
  testing and a flat default. Bends ease out while landing and scale down on
  high-face-count prisms. This is not a sphere mode.
- Backward-compatible saved-settings/custom-preset handling and safe migration of
  the prior v2 data-only Lua settings bridge.
- Real, privacy-safe action screenshots and a root marketplace preview.
- Sanitizer geometry/file tests, 36 Python tests, guarded native curvature/click
  checks and isolated 4K rendering regression validation.

Code is BSD-3-Clause. Supplied generated artwork has separate provenance notices;
no NASA, Poly Haven or CC0 license is claimed for replacement imagery. Marketplace
verification/publication applies only after maintainer review of the exact commit.
