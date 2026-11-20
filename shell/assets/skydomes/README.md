# Trial generated skydome artwork

The three images were supplied by the user as original RGB PNG downloads from
ChatGPT. They replace the earlier NASA/Poly Haven trial assets; those earlier
credits and licenses do not apply to the replacement images.

| Preset | Source download |
| --- | --- |
| Orbital | Sculpted Rings Over a Tranquil Nebula (2).png |
| Deep Space | Carved Nebula Cathedral Panorama (2).png |
| Golden Hour | Carved Cloud Canyon at Sunset (2).png |

Sources are **1774×887**, RGB. Delivery JPEGs preserve those dimensions, use quality
97 and full chroma resolution, and have no upscaling or sharpening. The PNG originals
remain in the user's Downloads folder. Previews are separate 480×240 JPEGs.
`sources.json` records source filenames, original SHA-256 digests and dimensions.

These are illustrated landscapes, not verified seamless spherical environments.
Built-in presets now use an **aspect-correct image backdrop with bounded parallax**.
The renderer no longer wraps these illustrations around a sphere. Rotation and
tilt shift the image gently inside an overscanned crop; reduced motion disables
the shift. Legacy mapping settings remain accepted for compatibility.

This is generated illustration, not a claim of native 4K or 8K detail. The maintainer
provided the images and explicitly requested their inclusion and publication with
the plugin. Assess the actual result on high-resolution displays.

## Provenance and distribution

Generated using ChatGPT with user-provided prompts and the user's desktop
wallpaper as a broad visual reference. Exact model/native generation settings
were not exposed by the download and are not asserted here. Source download
names and checksums are known; provider metadata and rights in the reference
wallpaper have not been independently established.

**Do not label these assets NASA imagery, Poly Haven assets or CC0.** The code's
BSD-3-Clause license does not automatically license generated image output.
Inclusion is authorized by the maintainer's publication request, not by a claimed
NASA/Poly Haven license. Applicable provider terms and any underlying third-party
rights still apply; no independent third-party-rights clearance or blanket CC0
dedication is asserted. These notices accompany the assets and their screenshots.

Classic's small gradient preview is original generated artwork; the runtime
Classic preset still uses the native sky and no bundled background image.

## Reproduce delivery assets

Development-only Pillow is required. No network access is performed:

```sh
python3 tools/generate-skydomes.py --source-dir "$HOME/Downloads"
```

The tool verifies all three input hashes and dimensions before writing JPEGs.
No runtime image-generation service or additional dependency is required.
