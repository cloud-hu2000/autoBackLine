#!/bin/bash
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
bash run_merge.sh
echo
read -n 1 -s -r -p "Press any key to close this window..."
