#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$ROOT/daily_workflow.sh" "$@"

echo
echo "Workflow completed. Check logs/daily_workflow_*.log for details."
