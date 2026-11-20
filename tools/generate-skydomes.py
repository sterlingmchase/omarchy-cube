#!/usr/bin/env python3
"""Prepare user-supplied trial artwork without upscaling. Development-only Pillow dependency."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "shell/assets/skydomes"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads((ASSETS / "sources.json").read_text())
    # Check all originals before replacing any delivery files.
    for entry in records:
        path = args.source_dir / entry["source_filename"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit("Source checksum mismatch: " + path.name)
        with Image.open(path) as image:
            if image.size != (entry["width"], entry["height"]):
                raise SystemExit("Unexpected dimensions: " + path.name)
    for entry in records:
        with Image.open(args.source_dir / entry["source_filename"]) as source:
            image = source.convert("RGB")
        image.save(ASSETS / (entry["id"] + ".jpg"), quality=97, subsampling=0, optimize=True)
        image.resize((480, 240), Image.Resampling.LANCZOS).save(
            ASSETS / (entry["id"] + "-preview.jpg"), quality=92, optimize=True)
    print("Prepared three full-color, native-resolution trial images and thumbnails; no upscaling.")


if __name__ == "__main__":
    main()
