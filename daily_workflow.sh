#!/usr/bin/env bash
set -euo pipefail

DATE="$(date +%F)"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEBUG_PORT=9222
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi
PLUGIN_EXTENSION_ID="${PLUGIN_EXTENSION_ID:-eckpehelplpholpddkpmihfigodplkdp}"
PLUGIN_URL="${PLUGIN_URL:-chrome-extension://$PLUGIN_EXTENSION_ID/batch.html}"
PLUGIN_OPTIONS_URL="${PLUGIN_OPTIONS_URL:-chrome-extension://$PLUGIN_EXTENSION_ID/options.html}"
SCRAPE_TIMEOUT_MINUTES=240
PLUGIN_COMPLETION_TIMEOUT_MINUTES=240
SKIP_SCRAPE=0
SKIP_PLUGIN=0
NO_START_PLUGIN_TASK=0
NO_EXPORT_PLUGIN_RESULT=0
REQUIRE_INPUT_TODAY=0
CSV_PATH=""
PLUGIN_OUTPUT_DIR=""
PLUGIN_START_SELECTORS=()
PYTHON_BIN="${PYTHON:-python3}"
export PYTHONUNBUFFERED=1

usage() {
  cat <<'USAGE'
Usage: ./daily_workflow.sh [options]

Options:
  --date YYYY-MM-DD
  --project-root PATH
  --debug-port PORT
  --plugin-url URL
  --plugin-options-url URL
  --scrape-timeout-minutes MINUTES
  --plugin-completion-timeout-minutes MINUTES
  --skip-scrape
  --skip-plugin
  --no-start-plugin-task
  --no-export-plugin-result
  --require-input-today
  --csv-path PATH
  --plugin-output-dir PATH
  --plugin-start-selector SELECTOR   May be repeated.
  -h, --help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date) DATE="$2"; shift 2 ;;
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    --debug-port) DEBUG_PORT="$2"; shift 2 ;;
    --plugin-url) PLUGIN_URL="$2"; shift 2 ;;
    --plugin-options-url) PLUGIN_OPTIONS_URL="$2"; shift 2 ;;
    --scrape-timeout-minutes) SCRAPE_TIMEOUT_MINUTES="$2"; shift 2 ;;
    --plugin-completion-timeout-minutes) PLUGIN_COMPLETION_TIMEOUT_MINUTES="$2"; shift 2 ;;
    --skip-scrape) SKIP_SCRAPE=1; shift ;;
    --skip-plugin) SKIP_PLUGIN=1; shift ;;
    --no-start-plugin-task) NO_START_PLUGIN_TASK=1; shift ;;
    --no-export-plugin-result) NO_EXPORT_PLUGIN_RESULT=1; shift ;;
    --require-input-today) REQUIRE_INPUT_TODAY=1; shift ;;
    --csv-path) CSV_PATH="$2"; shift 2 ;;
    --plugin-output-dir) PLUGIN_OUTPUT_DIR="$2"; shift 2 ;;
    --plugin-start-selector) PLUGIN_START_SELECTORS+=("$2"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"
cd "$PROJECT_ROOT"

mkdir -p logs
LOG_FILE="$PROJECT_ROOT/logs/daily_workflow_$DATE.log"
exec > >(tee -a "$LOG_FILE") 2>&1

write_step() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

wait_debug_port() {
  local port="$1"
  local timeout_seconds="${2:-60}"
  local deadline=$((SECONDS + timeout_seconds))
  while (( SECONDS < deadline )); do
    if curl -fsS "http://127.0.0.1:$port/json/version" 2>/dev/null | grep -q "webSocketDebuggerUrl"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

run_checked() {
  local timeout_minutes="$1"
  shift
  write_step "Running: $*"

  if (( timeout_minutes <= 0 )); then
    "$@"
    return
  fi

  "$@" &
  local pid=$!
  local deadline=$((SECONDS + timeout_minutes * 60))
  while kill -0 "$pid" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      kill "$pid" 2>/dev/null || true
      sleep 2
      kill -9 "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      echo "Process timed out after $timeout_minutes minutes: $*" >&2
      return 124
    fi
    sleep 2
  done
  wait "$pid"
}

file_signature() {
  local file="$1"
  if stat -f "%N:%z:%m" "$file" >/dev/null 2>&1; then
    stat -f "%N:%z:%m" "$file"
  else
    stat -c "%n:%s:%Y" "$file"
  fi
}

wait_stable_files() {
  local directory="$1"
  local pattern="$2"
  local timeout_seconds="${3:-300}"
  local stable_seconds="${4:-10}"
  local deadline=$((SECONDS + timeout_seconds))
  local last_signature=""
  local stable_since=0
  local signature files partial_count

  while (( SECONDS < deadline )); do
    partial_count=$(find "$directory" -maxdepth 1 -name "*.crdownload" -type f 2>/dev/null | wc -l | tr -d ' ')
    files=()
    while IFS= read -r file; do
      files+=("$file")
    done < <(find "$directory" -maxdepth 1 -name "$pattern" -type f 2>/dev/null | sort)

    if (( ${#files[@]} > 0 && partial_count == 0 )); then
      signature=""
      for file in "${files[@]}"; do
        signature+="$(file_signature "$file")|"
      done

      if [[ "$signature" == "$last_signature" ]]; then
        if (( stable_since == 0 )); then
          stable_since=$SECONDS
        fi
        if (( SECONDS - stable_since >= stable_seconds )); then
          printf '%s\n' "${files[@]}"
          return 0
        fi
      else
        last_signature="$signature"
        stable_since=0
      fi
    fi
    sleep 2
  done

  echo "Timed out waiting for stable files: $directory/$pattern" >&2
  return 1
}

input_file="$PROJECT_ROOT/data/input.xlsx"
if [[ ! -f "$input_file" ]]; then
  echo "Missing input file: $input_file" >&2
  exit 1
fi

write_step "Workflow started for $DATE"
write_step "Input file: $input_file"
if (( REQUIRE_INPUT_TODAY )); then
  if input_day=$(stat -f "%Sm" -t "%F" "$input_file" 2>/dev/null); then
    :
  else
    input_day=$(stat -c "%y" "$input_file" | cut -d' ' -f1)
  fi
  if [[ "$input_day" != "$(date +%F)" ]]; then
    echo "input.xlsx was not updated today. Use without --require-input-today to allow stale input." >&2
    exit 1
  fi
fi

export DEBUG_PORT="$DEBUG_PORT"
write_step "Starting Chrome debug session"
run_checked 0 "$PROJECT_ROOT/start_chrome_debug.sh"

if ! wait_debug_port "$DEBUG_PORT" 90; then
  echo "Chrome debug port $DEBUG_PORT did not become ready." >&2
  exit 1
fi
write_step "Chrome debug port $DEBUG_PORT is ready"

if (( ! SKIP_SCRAPE )); then
  run_checked "$SCRAPE_TIMEOUT_MINUTES" "$PYTHON_BIN" main.py --mode full --date "$DATE"
  write_step "Waiting for exported CSV downloads to settle"
  downloaded=()
  while IFS= read -r file; do
    downloaded+=("$file")
  done < <(wait_stable_files "$PROJECT_ROOT/data/downloads" "backlinks_export_$DATE*.csv" 600 10)
  write_step "Detected ${#downloaded[@]} stable exported CSV files"
else
  write_step "Skipping scrape step"
fi

write_step "Running final merge for $DATE"
run_checked 0 "$PYTHON_BIN" merge_only.py --date "$DATE"

if [[ -z "$CSV_PATH" ]]; then
  CSV_PATH="$PROJECT_ROOT/data/backlinks_merged_$DATE.csv"
elif [[ "$CSV_PATH" != /* ]]; then
  CSV_PATH="$PROJECT_ROOT/$CSV_PATH"
fi

if [[ ! -f "$CSV_PATH" ]]; then
  echo "Merged CSV was not created: $CSV_PATH" >&2
  exit 1
fi
write_step "Merged CSV ready: $CSV_PATH"

if [[ -z "$PLUGIN_OUTPUT_DIR" ]]; then
  PLUGIN_OUTPUT_DIR="$PROJECT_ROOT/data/output"
elif [[ "$PLUGIN_OUTPUT_DIR" != /* ]]; then
  PLUGIN_OUTPUT_DIR="$PROJECT_ROOT/$PLUGIN_OUTPUT_DIR"
fi
mkdir -p "$PLUGIN_OUTPUT_DIR"

if (( ! SKIP_PLUGIN )); then
  if ! wait_debug_port "$DEBUG_PORT" 30; then
    write_step "Chrome debug port is not ready after merge; starting Chrome again"
    run_checked 0 "$PROJECT_ROOT/start_chrome_debug.sh"
    if ! wait_debug_port "$DEBUG_PORT" 90; then
      echo "Chrome debug port $DEBUG_PORT did not become ready before plugin upload." >&2
      exit 1
    fi
  fi

  plugin_args=(
    extension_batch_upload.py
    --csv "$CSV_PATH"
    --url "$PLUGIN_URL"
    --options-url "$PLUGIN_OPTIONS_URL"
    --port "$DEBUG_PORT"
    --output-dir "$PLUGIN_OUTPUT_DIR"
    --completion-timeout-minutes "$PLUGIN_COMPLETION_TIMEOUT_MINUTES"
  )

  set +u
  for selector in "${PLUGIN_START_SELECTORS[@]}"; do
    [[ -n "$selector" ]] && plugin_args+=(--start-selector "$selector")
  done
  set -u

  (( NO_START_PLUGIN_TASK )) && plugin_args+=(--no-start)
  (( NO_EXPORT_PLUGIN_RESULT )) && plugin_args+=(--no-export)

  run_checked 0 "$PYTHON_BIN" "${plugin_args[@]}"
else
  write_step "Skipping plugin step"
fi

write_step "Workflow completed successfully"
