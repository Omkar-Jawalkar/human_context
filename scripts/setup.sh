#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON=python3.12
  else
    PYTHON=python3
  fi
fi

if [ ! -d ".venv" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 .venv
  else
    "$PYTHON" -m venv .venv
  fi
fi

VENV_PYTHON=".venv/bin/python"

if command -v uv >/dev/null 2>&1; then
  uv sync --extra dev
else
  "$VENV_PYTHON" -m pip install -U pip
  "$VENV_PYTHON" -m pip install -e ".[dev]"
fi

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "Setup complete (Python: $($PYTHON --version)). Activate with: source .venv/bin/activate"
