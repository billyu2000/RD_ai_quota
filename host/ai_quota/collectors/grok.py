from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

NAME = "Grok"
LOG_PATH = Path.home() / ".grok" / "logs" / "unified.jsonl"
BILLING_MSG = "billing: fetched credits config"
MAX_TAIL_BYTES = 4 * 1024 * 1024
CHUNK = 64 * 1024


def _tail_lines(path: Path) -> Iterator[bytes]:
    with path.open("rb") as log_file:
        log_file.seek(0, os.SEEK_END)
        position = log_file.tell()
        remaining = b""
        scanned = 0
        while position > 0 and scanned < MAX_TAIL_BYTES:
            chunk_size = min(CHUNK, position, MAX_TAIL_BYTES - scanned)
            position -= chunk_size
            log_file.seek(position)
            chunk = log_file.read(chunk_size)
            scanned += len(chunk)
            parts = (chunk + remaining).split(b"\n")
            remaining = parts[0]
            for line in reversed(parts[1:]):
                if line:
                    yield line
        if remaining:
            yield remaining


def collect() -> dict[str, Any]:
    if not LOG_PATH.exists():
        return {"id": "grok", "name": NAME, "status": "no_creds", "windows": []}
    try:
        for line in _tail_lines(LOG_PATH):
            try:
                payload = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(payload, dict) or payload.get("msg") != BILLING_MSG:
                continue
            ctx = payload.get("ctx") if isinstance(payload.get("ctx"), dict) else {}
            config = ctx.get("config") if isinstance(ctx.get("config"), dict) else {}
            used = config.get("creditUsagePercent")
            period = config.get("currentPeriod") if isinstance(config.get("currentPeriod"), dict) else {}
            end = period.get("end")
            if not isinstance(used, (int, float)) or not isinstance(end, str):
                continue
            try:
                reset = datetime.fromisoformat(end[:-1] + "+00:00" if end.endswith("Z") else end)
                if reset.tzinfo is None:
                    continue
                remaining = int((reset.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds())
            except ValueError:
                remaining = -1
            return {
                "id": "grok",
                "name": NAME,
                "status": "ok",
                "windows": [
                    {"label": "wk", "used_pct": float(used), "resets_in_s": max(0, remaining)}
                ],
            }
    except OSError:
        return {"id": "grok", "name": NAME, "status": "error", "windows": []}
    return {"id": "grok", "name": NAME, "status": "no_creds", "windows": []}
