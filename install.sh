#!/bin/bash
# Install ai2print via Clified (PyPI)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLIFIED_TOOLS="${CLIFIED_TOOLS:-$SCRIPT_DIR/tools.yaml}"

if [[ ! -f "$CLIFIED_TOOLS" && -f "$SCRIPT_DIR/tools.yaml.example" ]]; then
  cp "$SCRIPT_DIR/tools.yaml.example" "$CLIFIED_TOOLS"
fi

# shellcheck source=scripts/install-bootstrap.sh
source "$SCRIPT_DIR/scripts/install-bootstrap.sh"
clified_bootstrap ai2print "$@"
