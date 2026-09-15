#!/bin/zsh
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/.venv/bin/activate"
cd "$ROOT/host"
exec python -m ai_quota "$@"
