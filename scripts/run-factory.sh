#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"
SIGNAL="${1:-examples/sample-signal.json}"
python -m factory_cli.main run --signal "$SIGNAL"
