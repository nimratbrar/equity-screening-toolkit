#!/usr/bin/env bash
# Build the Python environment with uv (Python 3.12, versions pinned by uv.lock).
# The environment lives in ~/.venvs/equity-screening-toolkit, outside any synced folder.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install it from https://docs.astral.sh/uv/ (for example: brew install uv)"
  exit 1
fi

export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/equity-screening-toolkit"
uv sync

echo
echo "Setup done. Run the pipeline with:"
echo "  UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run pipeline.py --config pipelines/quality_growth.json"
