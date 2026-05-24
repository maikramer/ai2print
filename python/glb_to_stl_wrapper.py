#!/usr/bin/env python3
"""Wrapper: GLB/GLTF → STL print-ready via Blender."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_blender() -> str:
    if path := os.environ.get("STL_REPAIR_BLENDER"):
        return path
    for candidate in ("blender", "/snap/bin/blender", "/usr/bin/blender"):
        if shutil.which(candidate):
            return candidate
    raise FileNotFoundError("Blender não encontrado.")


def main() -> int:
    parser = argparse.ArgumentParser(description="GLB → STL via Blender")
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--merge", type=float, default=0.0001)
    args = parser.parse_args()

    script = Path(__file__).resolve().parent / "glb_to_stl.py"
    blender = find_blender()
    cmd = [
        blender,
        "--background",
        "--python",
        str(script),
        "--",
        "--input",
        str(args.input.expanduser().resolve()),
        "--output",
        str(args.output.expanduser().resolve()),
        "--merge",
        str(args.merge),
    ]
    print(f"Blender: {blender}", flush=True)
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
