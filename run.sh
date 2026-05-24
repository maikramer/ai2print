#!/usr/bin/env bash
# Atalho de desenvolvimento — preferir ./install.sh ou o comando global ai2print
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export STL_REPAIR_ROOT="$ROOT"
export STL_REPAIR_PYTHON="${STL_REPAIR_PYTHON:-$ROOT/.venv/bin/python3}"

BIN="$ROOT/target/release/stl-repair-gui"
if [[ ! -x "$BIN" ]]; then
  echo "Binário não encontrado. Instale com: ./install.sh"
  exit 1
fi

exec "$BIN" "$@"
