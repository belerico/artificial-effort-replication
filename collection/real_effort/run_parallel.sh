#!/usr/bin/env bash
# Run benchmarks in parallel — one worker process per model.
# Wrapper around run_benchmarks.py with a shared experiment name and auto-resume.
#
# Usage:
#   ./run_parallel.sh [folder] [wrapper options] [run_benchmarks.py options...]
#
# Wrapper options:
#   --tier EFFORT / --reasoning-effort EFFORT
#   --incentive true|false|explicit_none
#   --models MODEL [MODEL ...]
#
# If <folder> is omitted, it is auto-generated from the effective reasoning tier
# and incentive mode. Effective defaults come from the same YAML config that
# run_benchmarks.py loads, unless overridden here.
#
# Notes:
#   - The folder argument is the shared experiment name.
#   - This wrapper manages --experiment-name / --resume / --report-dir itself.
#   - Put the optional folder before multi-value options like --models / --games.
#   - Reports go in reports/<experiment-name>/, matching run_benchmarks.py defaults.

set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1

usage() {
    cat <<'EOF'
Usage:
  ./run_parallel.sh [folder] [wrapper options] [run_benchmarks.py options...]

Wrapper options:
  --tier EFFORT, --reasoning-effort EFFORT
      Override reasoning effort for all launched processes.
      Choices: none, minimal, low, medium, high, xhigh

  --incentive MODE
      Override incentive mode for all launched processes.
      Choices: true, false, explicit_none

  --models MODEL [MODEL ...]
      Override the model list. Accepts either multiple args or one quoted string.

Pass-through options currently supported from run_benchmarks.py:
  --config PATH
  --games GAME [GAME ...]
  --temperature FLOAT
  --max-tokens INT
  --reasoning-max-tokens INT
  --persona standard|human|control
  --top-p FLOAT
  --run-delay FLOAT
  --max-retries INT
  --repetitions INT
  --no-reload
  --text-only

Managed internally by this wrapper and therefore rejected:
  --experiment-name
  --resume
  --report-dir

Examples:
  ./run_parallel.sh
  ./run_parallel.sh high-incentive --tier high
  ./run_parallel.sh --config alt.yaml --games add_numbers task_sequences
  ./run_parallel.sh quick-test --models google/gemini-3-flash-preview openai/gpt-5-mini
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

require_value() {
    local flag="$1"
    [[ $# -ge 2 ]] || die "Missing value for ${flag}"
}

FOLDER=""
CONFIG_PATH=""
TIER=""
INCENTIVE=""
TEXT_ONLY=false
MODELS_OVERRIDE_RAW=()
GAMES_OVERRIDE_RAW=()
PASSTHROUGH_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --tier|--reasoning-effort)
            require_value "$1" "$@"
            TIER="$2"
            shift 2
            ;;
        --tier=*|--reasoning-effort=*)
            TIER="${1#*=}"
            shift
            ;;
        --incentive)
            require_value "$1" "$@"
            INCENTIVE="$2"
            shift 2
            ;;
        --incentive=*)
            INCENTIVE="${1#*=}"
            shift
            ;;
        --models)
            shift
            [[ $# -gt 0 ]] || die "--models requires at least one model"
            while [[ $# -gt 0 && "$1" != --* ]]; do
                MODELS_OVERRIDE_RAW+=("$1")
                shift
            done
            [[ ${#MODELS_OVERRIDE_RAW[@]} -gt 0 ]] || die "--models requires at least one model"
            ;;
        --models=*)
            MODELS_OVERRIDE_RAW+=("${1#*=}")
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                MODELS_OVERRIDE_RAW+=("$1")
                shift
            done
            ;;
        --games)
            shift
            [[ $# -gt 0 ]] || die "--games requires at least one game"
            while [[ $# -gt 0 && "$1" != --* ]]; do
                GAMES_OVERRIDE_RAW+=("$1")
                shift
            done
            [[ ${#GAMES_OVERRIDE_RAW[@]} -gt 0 ]] || die "--games requires at least one game"
            ;;
        --games=*)
            GAMES_OVERRIDE_RAW+=("${1#*=}")
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                GAMES_OVERRIDE_RAW+=("$1")
                shift
            done
            ;;
        --config|--temperature|--max-tokens|--reasoning-max-tokens|--persona|--top-p|--run-delay|--max-retries|--repetitions)
            require_value "$1" "$@"
            PASSTHROUGH_ARGS+=("$1" "$2")
            if [[ "$1" == "--config" ]]; then
                CONFIG_PATH="$2"
            fi
            shift 2
            ;;
        --config=*|--temperature=*|--max-tokens=*|--reasoning-max-tokens=*|--persona=*|--top-p=*|--run-delay=*|--max-retries=*|--repetitions=*)
            PASSTHROUGH_ARGS+=("${1%%=*}" "${1#*=}")
            if [[ "${1%%=*}" == "--config" ]]; then
                CONFIG_PATH="${1#*=}"
            fi
            shift
            ;;
        --no-reload)
            PASSTHROUGH_ARGS+=("$1")
            shift
            ;;
        --text-only)
            TEXT_ONLY=true
            PASSTHROUGH_ARGS+=("$1")
            shift
            ;;
        --resume|--experiment-name|--report-dir|--resume=*|--experiment-name=*|--report-dir=*)
            die "$1 is managed by run_parallel.sh; use the folder argument and built-in auto-resume instead"
            ;;
        --*)
            die "Unknown option '$1'. Use --help to see supported arguments."
            ;;
        *)
            if [[ -z "$FOLDER" ]]; then
                FOLDER="$1"
            else
                PASSTHROUGH_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

MODELS_OVERRIDE=()
if [[ ${#MODELS_OVERRIDE_RAW[@]} -gt 0 ]]; then
    IFS=' ' read -r -a MODELS_OVERRIDE <<< "${MODELS_OVERRIDE_RAW[*]}"
fi

if [[ ${#GAMES_OVERRIDE_RAW[@]} -gt 0 ]]; then
    GAMES_OVERRIDE=()
    IFS=' ' read -r -a GAMES_OVERRIDE <<< "${GAMES_OVERRIDE_RAW[*]}"
    PASSTHROUGH_ARGS+=(--games "${GAMES_OVERRIDE[@]}")
fi

CONFIG_OUTPUT=$(
    BENCHMARK_CONFIG_PATH="${CONFIG_PATH:-config/benchmark_config_llm.yaml}" uv run python -c '
import os
from config import load_benchmark_config
from run_benchmarks import DEFAULT_MODEL

cfg = load_benchmark_config(os.environ.get("BENCHMARK_CONFIG_PATH") or None)
game_defaults = cfg.get("game_defaults") or {}
incentive = game_defaults.get("incentive", False)
if incentive is True:
    incentive = "true"
elif incentive is False or incentive is None:
    incentive = "false"
else:
    incentive = str(incentive)

for model in (cfg.get("models") or [DEFAULT_MODEL]):
    print("MODEL\t" + model)
print("REASONING_EFFORT\t" + str(cfg.get("reasoning_effort") or ""))
print("INCENTIVE\t" + incentive)
'
) || die "Failed to load benchmark defaults from run_benchmarks.py/config"

CONFIG_MODELS=()
CONFIG_REASONING_EFFORT=""
CONFIG_INCENTIVE="false"
while IFS=$'\t' read -r kind value; do
    case "$kind" in
        MODEL)
            CONFIG_MODELS+=("$value")
            ;;
        REASONING_EFFORT)
            CONFIG_REASONING_EFFORT="$value"
            ;;
        INCENTIVE)
            CONFIG_INCENTIVE="$value"
            ;;
    esac
done <<< "$CONFIG_OUTPUT"

if [[ ${#MODELS_OVERRIDE[@]} -gt 0 ]]; then
    MODELS=("${MODELS_OVERRIDE[@]}")
else
    MODELS=("${CONFIG_MODELS[@]}")
fi

[[ ${#MODELS[@]} -gt 0 ]] || die "No models resolved from overrides or config"

TIER_ARGS=()
if [[ -n "$TIER" ]]; then
    case "$TIER" in
        none|minimal|low|medium|high|xhigh)
            TIER_ARGS=(--reasoning-effort "$TIER")
            ;;
        *)
            die "Unknown tier '${TIER}'. Use: none, minimal, low, medium, high, xhigh"
            ;;
    esac
fi

INCENTIVE_ARGS=()
if [[ -n "$INCENTIVE" ]]; then
    case "$INCENTIVE" in
        true|false|explicit_none)
            INCENTIVE_ARGS=(--incentive "$INCENTIVE")
            ;;
        *)
            die "Unknown incentive '${INCENTIVE}'. Use: true, false, explicit_none"
            ;;
    esac
fi

EFFECTIVE_TIER="${TIER:-$CONFIG_REASONING_EFFORT}"
EFFECTIVE_INCENTIVE="${INCENTIVE:-$CONFIG_INCENTIVE}"

case "${EFFECTIVE_INCENTIVE}" in
    true)
        INCENTIVE_LABEL="incentive"
        ;;
    false)
        INCENTIVE_LABEL="no-incentive"
        ;;
    explicit_none)
        INCENTIVE_LABEL="explicit-no-incentive"
        ;;
    *)
        die "Unknown effective incentive '${EFFECTIVE_INCENTIVE}' from overrides/config"
        ;;
esac

if [[ -z "$FOLDER" ]]; then
    FOLDER="${EFFECTIVE_TIER:-default}-${INCENTIVE_LABEL}"
    if [[ "$TEXT_ONLY" == "true" ]]; then
        FOLDER="${FOLDER}-text"
    fi
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    echo "ERROR: OPENROUTER_API_KEY is not set" >&2
    echo "  export OPENROUTER_API_KEY='your-key'" >&2
    exit 1
fi

echo "Starting parallel benchmarks: ${#MODELS[@]} models"
echo "Experiment: $FOLDER"
echo "Config: ${CONFIG_PATH:-config/benchmark_config_llm.yaml}"
echo "Reasoning: ${EFFECTIVE_TIER:-config-default}${TIER_ARGS:+ (override)}"
echo "Incentive: ${EFFECTIVE_INCENTIVE}${INCENTIVE_ARGS:+ (override)}"
echo "Models: ${MODELS[*]}"
echo "Extra args: ${PASSTHROUGH_ARGS[*]:-none}"
echo "---"

EXP_DIR="reports/${FOLDER}"
mkdir -p "$EXP_DIR"

experiment_exists() {
    local name="$1"
    local found

    [[ -f reports/results_orig.db ]] || return 1

    found=$(
        EXPERIMENT_NAME="$name" python3 -c '
import os
import sqlite3

conn = sqlite3.connect("reports/results_orig.db")
row = conn.execute(
    "SELECT 1 FROM experiments WHERE name = ? LIMIT 1",
    (os.environ["EXPERIMENT_NAME"],),
).fetchone()
print(1 if row else 0)
'
    ) || return 1

    [[ "$found" == "1" ]]
}

COMMON_ARGS=()
if ((${#TIER_ARGS[@]})); then
    COMMON_ARGS+=("${TIER_ARGS[@]}")
fi
if ((${#INCENTIVE_ARGS[@]})); then
    COMMON_ARGS+=("${INCENTIVE_ARGS[@]}")
fi
if ((${#PASSTHROUGH_ARGS[@]})); then
    COMMON_ARGS+=("${PASSTHROUGH_ARGS[@]}")
fi

SETUP_FLAG=(--experiment-name "$FOLDER")
if experiment_exists "$FOLDER"; then
    SETUP_FLAG=(--resume "$FOLDER")
    echo "Preparing existing experiment: $FOLDER"
else
    echo "Creating experiment: $FOLDER"
fi

SETUP_CMD=(uv run python run_benchmarks.py "${SETUP_FLAG[@]}" --models "${MODELS[@]}")
if ((${#COMMON_ARGS[@]})); then
    SETUP_CMD+=("${COMMON_ARGS[@]}")
fi
SETUP_CMD+=(--prepare-only)
"${SETUP_CMD[@]}"

echo "---"
echo "Launching workers:"

PIDS=()

for model in "${MODELS[@]}"; do
    short="${model##*/}"
    log_file="${EXP_DIR}/${short}.log"

    echo "  $short -> experiment=$FOLDER (log: $log_file)"

    WORKER_CMD=(uv run python run_benchmarks.py --resume "$FOLDER" --models "$model")
    if ((${#COMMON_ARGS[@]})); then
        WORKER_CMD+=("${COMMON_ARGS[@]}")
    fi

    "${WORKER_CMD[@]}" > "$log_file" 2>&1 &

    PIDS+=($!)
done

echo "---"
echo "All ${#MODELS[@]} processes launched. PIDs: ${PIDS[*]}"
echo "Waiting for completion..."

FAILED=0
for i in "${!PIDS[@]}"; do
    pid=${PIDS[$i]}
    model=${MODELS[$i]}
    short="${model##*/}"

    if wait "$pid"; then
        echo "  DONE: $short (pid $pid)"
    else
        status=$?
        echo "  FAIL: $short (pid $pid, exit $status)"
        FAILED=$((FAILED + 1))
    fi
done

echo "---"
echo "Completed: $((${#MODELS[@]} - FAILED))/${#MODELS[@]} succeeded"
if [[ $FAILED -gt 0 ]]; then
    echo "Check logs in $EXP_DIR for failures"
    exit 1
fi
