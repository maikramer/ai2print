#!/usr/bin/env python3
"""Redireciona para o instalador Clified (PyPI)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    os.environ.setdefault("CLIFIED_TOOLS", str(repo / "tools.yaml"))
    from clified.installer.bootstrap import run

    return run(["ai2print", *sys.argv[1:]], cwd=str(repo))


if __name__ == "__main__":
    sys.exit(main())
