#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

TARGET_DATE="${1:-$(date +%F)}"
"${PYTHON:-python3}" merge_only.py --date "$TARGET_DATE"
