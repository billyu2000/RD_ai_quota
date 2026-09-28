#!/bin/zsh
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/.venv/bin/activate"
cd "$ROOT/host"
if [ $# -eq 0 ]; then
  exec python -m ai_quota app
fi
exec python -m ai_quota "$@"
