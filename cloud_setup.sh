#!/usr/bin/env bash
# Paste this into the Claude Code cloud environment's "Setup script" box (or run it in a cloud session).
# Installs the same pinned versions as the Mac (pyproject.toml + uv.lock) into the repo's .venv.
# No credentials here: set WRDS_USERNAME and WRDS_PASSWORD in the environment's Environment variables.
set -euo pipefail
command -v uv >/dev/null 2>&1 || python3 -m pip install --quiet uv
uv sync --frozen
uv run python -c "import wrds, pandas, openpyxl; print('WRDS skill dependencies installed')"
