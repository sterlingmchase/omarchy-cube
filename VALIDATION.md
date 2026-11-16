# Mouse controls and responsive turns — 0.2.0

Tested 2026-11-16 in an isolated compositor:

- Real virtual-pointer drag, scroll, face-click selection and right-click cancel.
- Escape/Enter/arrow-key alternatives through Wtype.
- A raw-input terminal beneath the overview received no leaked clicks or keys.
- Three rapid next calls and immediate reversal finish on the expected workspace.
- Mid-turn retarget preserves the rendered position; stationary overview requests
  no continuous redraws; unload during overview is safe.
- Eight settings-helper tests and ASan/UBSan geometry/hit-testing checks pass.
- Updated QML panel loads with installed Omarchy components in the nested session.
- 4K regression with a 4096×2048 skydome: 602 measured intervals, average
  16.720 ms, max 27.664 ms, one interval above 25 ms. Draw CPU average 65.611 µs.
  These are virtual-output measurements, not GPU completion times.

Pointer tests: `python3 tests/mouse.py --display wayland-N` against the exact
`tests/nested.lua` fixture only. No input injection is performed on a personal session.

The 0.2.0 face cache captures newly visible faces on demand and drops hidden faces,
so repeated turns and dragging remain bounded rather than caching every workspace.

---

# Previous 0.1.0 validation

Tested 2026-11-15 on Omarchy 4.5.0, Hyprland 0.56.2
`efb50993780079460b0cbed1363e2166a2de1d9f`, Intel integrated graphics, in an isolated
nested compositor. The personal desktop was not modified or used to load the plugin.

## Final 4K run

Command: `python3 tests/integration.py --highres --no-capture`.
The test asserts that the focused output is the virtual 3840×2160 output. It loads
a generated 4096×2048 PNG panorama and exercises the default ten-workspace prism.

| Metric | Observed |
| --- | --- |
| Measured frame intervals | 603 |
| Average interval | 16.722 ms |
| Longest interval | 17.005 ms |
| Intervals over 1.5 refresh periods (25 ms at 60 Hz) | 0 |
| Average draw submission CPU time | 63.237 µs |
| Maximum draw submission CPU time | 173.074 µs |
| Last turn's snapshot submission CPU time | 0.334 ms |
| Captured workspace faces per default ten-sided turn | 4 |

These measure compositor-side frame timing and CPU submission, not GPU completion
or physical-display latency. They do not guarantee the same performance on other
hardware, with expensive windows/effects, or under system load. A prior run taking
a screenshot during animation recorded a 71 ms gap; screenshot readback is excluded
from the benchmark above. The host also throttled the nested Wayland window in
one visual run (about 31 ms average intervals); the stable 4K figures above are
from the independent virtual output, not a claim about that nested window. The plugin itself never performs screenshot readback.

## Passed

- Native plugin build against installed matching headers.
- ASan/UBSan math self-checks: wraparound, timing, monotonic easing and conservative
  visible-face coverage for workspace counts 4–20 in both directions.
- Isolated rendering, four-workspace wrapping, ten-workspace 10→1→10 wrapping,
  cancellation and invalid operation handling.
- Generated panorama decode/upload, replacing the same image, malformed image
  fallback, and recovery to a valid image.
- Live graphical-helper reads against native plugin options.
- 32 repeated turns, no extra cube draws while idle, global reduced-motion bypass.
  A one-shot end deadline releases snapshots even when an output is throttled.
- Eight unloads during animation followed by reload; queued-pass lifetime regression.
- Seven settings-helper tests covering validation, UTF-8/Lua escaping, native image
  error reporting and apply rollback.
- Omarchy manifest validation and installer shell syntax.
- Actual settings QML loaded in a separate nested compositor using installed
  Omarchy Commons/Ui and a stub helper. All seven settings populated. No QML runtime
  warnings/errors; one unrelated host portal warning. This checks presentation,
  not a complete real-image Apply interaction through the panel.

An early isolated unload test found a crash caused by a queued render pass outliving
the plugin. Cleanup now removes those objects before unload; the regression tests
above exercise the fixed path. No crash occurred in the final test runs.

## Not verified

- Real personal-desktop activation or installer execution.
- A full graphical Apply interaction against live user configuration (rollback is
  tested with mocks, native option reads and image loading are tested separately).
- Physical multi-monitor/mixed-DPI, HDR, VRR, output mirroring, lockscreen integration,
  or coexistence with other rendering-hook plugins.
- High-refresh 120/144/240 Hz hardware or arbitrary workloads.
- LeakSanitizer: sandbox ptrace prevents it from running. ASan/UBSan math tests pass
  with `ASAN_OPTIONS=detect_leaks=0`; the compositor itself was not sanitizer-built.

## 0.2.0 activation

Installed and activated 2026-11-16. Live overview open/cancel and immediate
right→left reversal passed; the original workspace/console overlay were restored.
One initial live check was interrupted by concurrent interaction; the traced check
then passed. User settings (390 ms, zoom 0.2) were preserved. Configuration errors
were empty, and the installed library matched the tested build. Backup:
`<local-install-backup>`.

Activation shortcut update: rebuilt successfully; tests/mouse.py passed in isolated nested.lua compositor, including mouse-binding activation drag, no input leakage, release without committing, and existing mouse/keyboard/repeat regressions. Installed Super+Ctrl+Alt+Up and Super+Ctrl+Alt+mouse:272 after conflict check; live configerrors empty and both bindings registered. Physical modifier-drag gesture not exercised by automation.

Smooth overview entry: independent 220 ms zoom clock, immediate drag rotation, hit testing uses rendered zoom, animation-disabled entry remains instant. Build and eight settings tests passed. Fresh isolated mouse suite passed including increasing entry zoom and no zoom restart on rotation, plus stationary draw count. Earlier runs observed an idle redraw and a reused-session activation failure; the fresh-session suite passed. Installed using backed-up update procedure; configerrors empty. Physical feel not assessed.

Initial shortcut drag release selection: build and isolated mouse suite passed. Tests cover release selecting the front workspace, no-motion click preserving workspace, right-click cancellation before left release, and normal overview drag remaining open. Installed with backup and clean configerrors. Physical gesture feel not checked.

Animated initial-drag release: 220 ms interpolation from current angle/zoom to the selected front face and zero zoom. Existing animation timer handles completion; keyboard rotation can retarget. Build and complete mouse suite passed, including intermediate decreasing zoom/angle error and eventual inactive state. Idle test allows up to three compositor draws over 500 ms rather than requiring zero external redraws. First run had no rendered frames at activation; second passed landing but hit old strict idle assertion; final suite passed. Installed with backup, configerrors empty; physical feel not assessed.

Skydome Browse button: nine helper tests passed, plugin validation passed, isolated Quickshell harness confirmed selection/cancellation reopen the panel and preserve unsaved values. Uses installed Zenity GNOME PNG chooser, not the Nautilus file-manager CLI. Installed widget files with backup and restarted shell. Actual human selection in the GNOME picker was not automated.

JPEG support: libjpeg-turbo header inspection and bounded decode to Cairo RGB24 before texture upload. Existing 32 MiB input, 8192 per-side and 16 MP limits preserved. Native isolated integration passed RGB baseline/progressive and grayscale JPEG uploads, truncated JPEG rejection, oversized JPEG rejection, PNG recovery and rendering/switching/reduced-motion/idle/unload regressions. Nine helper tests and plugin validation passed. Installed with backup and shell restart; user Downloads images were not selected or tested. Integration fixture generation uses Pillow.

Large JPEG fix: reproduced photo-a.jpg failure from 24 MP exceeding 16 MP bound. Added TurboJPEG decode scaling (power-of-two reduction), source safety cap 16384/64 MP, texture cap remains 8192/16 MP. Full integration passed including 6000x4000 and 9000x1 loading and 16385x1 rejection. Both actual Downloads images photo-a.jpg and photo-b.jpg loaded successfully in isolated renderer. Installed with backup and refreshed shell. Earlier rejected Apply left live skydome path empty; user must select image again unless their choice is supplied.

Sharper JPEG scaling: choose highest supported TurboJPEG fractional factor within existing texture limit instead of power-of-two reduction. 6000x4000 now decodes at 4500x3000 (previously 3000x2000), preserving 2.25x pixels. Integration asserts actual texture dimensions; full integration and nine settings tests passed. Lossless JPEGs requiring unsupported scaling rejected before allocation. Live selected photo-a.jpg verified at 4500x3000 after backed-up install. No visual sharpness comparison or physical GPU benchmark performed.

Photo mapping: image aspect outside 1.9–2.1 uses aspect-correct cover framing with 4% overscan and bounded sinusoidal pan; near-2:1 retains sphere. Full integration passed, including screenshot pixel assertions for colored outer corners and upright orientation of a 3:2 fixture. Original photo-a.jpg visually inspected and contains soft/streaked stars. Additional actual-photo nested screenshots were blank or timed out (no rendered frames); no successful actual-photo visual comparison claimed. Installed with backup and clean reload.

Vertical tilt + dock capture fix: added ±45° pitch, pitch-aware exterior visibility and hit testing, shaded open-end interior walls without extra workspace captures, and smooth pitch leveling during release landing. ASan/UBSan geometry tests passed for counts4–20 and ±.65 pitch; mouse suite passed both tilt limits, projected face clicks, diagonal release leveling, cancellation and input isolation in fresh compositor. Top/bottom screenshots visually inspected. Native renderLayer hook excludes only omarchy-dock and omarchy-dock-apps while capturing, restored by RAII; no layer alpha mutation. Integration screenshot tests passed dock absence during overview/new face capture and restoration on occupied+empty workspaces, plus image and render regressions. One reused-compositor mouse run cancelled unexpectedly; clean-session combined run passed. Nine settings tests and plugin validation passed; installed with backup, clean configerrors. Physical dock interaction not automated.

Workspace 1/2 refresh cancellation fix: live state confirms workspace1 uses default dwindle and workspace2 floating; Omarchy workspace modes update input.follow_mouse on active-workspace boundary. Reproduced a running 600 ms turn cancelling immediately when hl.config changes that input setting. refreshSky now preserves animation on unchanged sky/settings, still cancels for disable/count/image changes and full config reload. Integration asserts 1→2 and 2→1 remain active across follow_mouse updates, overview survives, disable cancels. Full integration (including dock occupied/empty and screenshots), nine settings tests and validation passed. Photo fixture adapted to resized nested output. Installed with backup; configerrors empty. Physical shortcuts were not injected into the personal desktop.

Six-feature improvements (2026-11-16): cached workspace number/name labels with bounded plain-text Pango rendering; selected-face outline from active theme border; independent sensitivity/inversion; Auto/Photo/Panorama mapping and local image preview; click/Enter landing shared with drag-release landing; optional momentum capped at one extra face and disabled by default. Build, ASan/UBSan geometry checks, 11 helper tests and shell plugin validation passed. Guarded nested mouse suite passed sensitivity/inversion, momentum on/off, animated click acceptance and existing drag/tilt/input-isolation/repeat checks. Expanded integration passed screenshot comparisons for label/outline toggles, mapping overrides, photo orientation, image decoding, dock capture, workspace1/2 config refresh, wrap, idle, reduced motion, stress and unload. Label and settings screenshots inspected; GUI harness showed all three sections, Image.Ready for actual photo-a.jpg, and no QML errors (host portal warning only). Labels cache with visible faces; no new continuous idle rendering. Nested frame timings include host scheduling/readback overhead and are not a physical smoothness benchmark.

Installed tested binary and widget with backup `<local-install-backup>`; active image decoded at4500x3000. Physical gesture feel, high-refresh hardware and mixed-DPI/multimonitor behavior were not assessed in this pass.

Workspace names/presets/trackpad/performance pass (2026-11-16): native workspace_name_1..20 overrides label text only; empty values retain existing labels. New four-finger swipe listeners consume only owned sequences and preserve existing three-finger gestures. Escape/cancel drains the owned sequence without committing. Swipe release uses existing landing/momentum logic; swipes inside an open overview stay in preview. Test-only bus emitter is not installed. Native gesture tests passed tuning/inversion, pitch clamps, landing, cancellation, ownership, existing-overview behavior and Unicode label screenshot. Physical libinput delivery/feel is not simulated by that driver.

Fourteen helper tests passed, including names validation and preset CRUD/corrupt-file preservation. GUI harness used actual preset storage in /tmp with mocked live Apply; verified save/load/delete, pending-until-Apply behavior, preserved organization, and literal Unicode/markup-shaped names. Captured names/presets views; no QML errors. Presets use bounded locked atomic JSON storage. Source plugin validation and ASan/UBSan geometry tests passed.

Performance baseline on actual eDP-1 2880x1800@59.99Hz: eight turns, 71 frame intervals, average25.578ms, 38 intervals above25ms, average CPU submission58.555us. A four-turn background-disabled comparison averaged18.160ms over51 intervals with5 late intervals, CPU49.393us. These session measurements are not controlled GPU benchmarks; background workload and capture costs vary. Photo shader now computes spherical atan/acos only in Panorama mode; image resolution is unchanged. Landing resets the timing origin so idle overview time is excluded. Raw results live in build/performance-baseline.json and build/performance-no-sky.json.

Full integration passed on virtual4K output, including screenshot comparisons, dock regression and stress: average frame interval16.881ms, five late intervals out of770. First hidden nested-window capture timed out; capture now targets the focused test output explicitly, and full4K rerun passed. Installed with backup `<local-install-backup>`, restarted shell, native settings readback includes all36 settings and configerrors is empty. Existing five workspaces,250ms,zoom0.95 and selected photo-b image preserved.

Post-install physical-display sample:71 intervals, average24.689ms,34 late intervals, CPU submission70.748us; raw build/performance-updated.json. Average per-turn capture cost dropped from7.472ms in the first sample to2.952ms, but cache warmth/background load differ, so no causal speedup claim. Physical rendering still misses the16.67ms budget; this pass does not establish steady60fps. No image-quality reduction was applied. Physical four-finger hardware feel remains for user verification.

Final interaction round (2026-11-16): carry_windows is optional/default false and excluded from appearance presets. Shift-left drag in overview acquires the top snapshot window by projected UV and stored geometry, retains weak references, and only moves on button release after revalidating mapped/source/monitor state. Escape/right-click cancel; Enter does not prematurely accept a carried window. Pinned/grouped grabs and foreign-monitor drops are rejected. Normal unmodified rotation remains unchanged. Carry feedback forces a destination outline and bounded plain-text title even when ordinary labels/highlights are off. Toggle GUI harness passed default-off, staging, reread, Apply and persisted-read checks with no QML errors; actual user configuration was not used for harness writes.

Geometry tests now cover inverse-projected UV and conservative opaque-face coverage across4–20 faces and tilted views. Skydome rendering skips only a rectangle inside an actually captured opaque face, shrinking it by two pixels; GL scissor state is restored. Pixel comparisons of old/new renderers were exactly equal at neutral, positive-tilt and negative-tilt poses after output/entry settlement. Initial neutral comparison captured unsettled geometry; increased settlement and repeated strict comparison passed. No image-resolution/filtering changes. Fourteen helper tests and sanitizer geometry tests passed.

Performance investigation: physical old/new/old scheduler comparisons averaged23.65/20.25/22.98ms, so newer scheduling was restored to its original false setting. Continuous reversals still missed frame deadlines; GPU clocks rose200–1200MHz. Isolated4K CPU submission tests were near16.73ms while completion-synchronized GPU probes varied with system load. Temporary glFinish probes were only loaded in isolated compositor, never installed. A clipped-sky GPU probe averaged14.13ms versus the immediate unclipped control17.81ms; earlier control had9.38ms, so these are not a stable percentage-speedup claim. Final physical measurements must be interpreted with those limits.

Final input checks: corrected the multi-output virtual-pointer harness to subtract the desktop bounding-box origin (the fixture had no monitor at x=0). The full carry suite then passed default-off, ordinary drag, Escape/right-click cancellation, tiled/floating release-only single-window movement and closed-source abort. Destination/title screenshot was checked with normal labels/highlighting disabled. The full headless mouse suite passed, including sensitivity, tilt, animated release, input isolation, rapid repeat/reversal and a strengthened Right-then-Enter assertion. Keyboard handling now resolves symbols from the originating keyboard's keymap through the pinned native input hook; raw evdev numbers were incorrect for virtual/remapped layouts. Enter during a carry remains ignored. Fourteen helper checks and ASan/UBSan geometry checks passed (sanitizers require host execution because sandbox ptrace prevents LeakSanitizer).

Final post-keymap integration passed at4K: rendering, switching/wrap, cancellation, invalid input, reduced motion, idle and repeated unloads including during animation; average16.740ms, one late interval out of674. This last run omitted captures; the earlier full capture suite and pixel equivalence checks passed. Isolated compositor was stopped after tests. Installed and shell restarted with backup `<local-install-backup>`. Installed binary hash matches tested build, configerrors empty, all37 settings read successfully with carry_windows=false. Existing user preferences preserved. Physical pre-install sample24.429ms,27/60 late intervals; after-install benchmark refused because desktop was busy, with no input sent. No steady physical60fps or causal speedup claim. Physical drag feel and pinned/grouped/cross-monitor rejection paths were not interactively exercised.
