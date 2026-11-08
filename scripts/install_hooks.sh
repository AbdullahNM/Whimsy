#!/usr/bin/env bash
# ==============================================================================
# Whimsy — install the private-data guard hooks into this clone
# ==============================================================================
# Points core.hooksPath at the versioned .githooks/ directory so the pre-commit
# and pre-push guards are active. Run once per clone.
# ==============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

chmod +x .githooks/pre-commit .githooks/pre-push
git config core.hooksPath .githooks

echo "Hooks installed for $(basename "$ROOT_DIR"):"
echo "  pre-commit -> blocks staging personal campaigns into the public repo"
echo "  pre-push   -> blocks pushing commits that contain them"
echo
echo "Verify with:  git config --get core.hooksPath   # -> .githooks"
