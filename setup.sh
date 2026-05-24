#!/usr/bin/env bash
# Legado — use ./install.sh (Clified / PyPI)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/install.sh" "$@"
