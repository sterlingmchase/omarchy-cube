# Launch preset collection

Four built-ins, available offline. Choosing one stages its changes; only Apply
writes settings or calls the compositor. Built-ins cannot be overwritten or deleted.
Users can save a customized copy under My presets.

| ID | Name | Scene | Workspaces | Duration | Zoom | Brightness |
| --- | --- | --- | --- | --- | --- | --- |
| classic | Classic Cube | Native generated sky | 4 | 240 ms | 0.70 | 0.65 |
| orbital | Orbital | Illustrated ringed planet and sculpted clouds | 6 | 300 ms | 0.85 | 0.75 |
| deep-space | Deep Space | Illustrated violet nebula cathedral | 8 | 340 ms | 1.00 | 0.60 |
| golden-hour | Golden Hour | Illustrated sunset canyon | 4 | 320 ms | 0.75 | 0.75 |

All use labels and selected-face highlighting. Built-ins may change workspace
count (shown on each card), animation, zoom, labels, highlighting and skydome.
They never change workspace names, enabled state, gestures, mouse sensitivity,
inversion, momentum, or window-carry preferences. Custom presets retain their
existing behavior: workspace count and input-related settings excluded by the
existing format stay unchanged.

The three trial scenes are user-supplied ChatGPT illustrations at their downloaded
native resolution of 1774×887, with separate 480×240 previews. They use a bounded parallax
backdrop, not spherical panorama mapping. They replace the prior sourced
4K assets and must not retain NASA/Poly Haven labels or licenses. No upscaling is
performed. The gradient Classic preview is original. Source hashes, limitations
and the provenance and distribution notes are documented in
`shell/assets/skydomes/README.md`. `tools/generate-skydomes.py` prepares delivery
JPEGs from the verified original PNG downloads.

No network request or image download occurs during install, preview, or use.
Bundled image references in saved custom presets use stable built-in IDs, resolved
to the installed widget directory when loaded. Existing absolute user-image paths
remain supported. The runtime Lua settings file still uses a local absolute path.
