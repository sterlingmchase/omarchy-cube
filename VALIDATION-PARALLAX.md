# Parallax backdrop and selected-face glow validation

- Built against the pinned Hyprland 0.56.2 commit.
- ASan/UBSan geometry and file-reader tests passed.
- Backdrop math tests cover bounded opposing horizontal/vertical motion, reduced
  motion, nonfinite inputs, portrait/ultrawide aspect ratios, and UV bounds at
  maximum tilt (no exposed image edges).
- All 34 Python preset/settings/installer/setup tests passed.
- Omarchy manifest validation and git whitespace checks passed.
- Full screenshot-enabled integration passed in a fresh, isolated headless 4K
  compositor. Includes PNG/JPEG orientation, legacy mapping-value compatibility,
  selected-face glow visible beyond the crisp line, unchanged workspace center,
  labels/dock rendering, switching, reduced motion, idle, stress and unload checks.
- An integration rerun in a reused virtual-output session failed a workspace/
  monitor precondition. Restarting only that disposable compositor and rerunning
  passed. The personal compositor was not used for integration testing.
- Final nested sample: average frame interval 16.851 ms, three late intervals out
  of 837. These include host scheduling and are not a physical-display FPS claim.
- Glow is a soft inward edge band in the existing face shader, not an external
  blurred halo. No extra framebuffer, capture, or draw pass is introduced.
- Backdrop uses one cached image, aspect-correct cover with 10% overscan, bounded
  rotation/tilt offsets, and no additional render timer. No 8K dependency.
