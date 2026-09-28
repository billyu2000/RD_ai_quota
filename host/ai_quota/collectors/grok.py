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


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _exhausted(payload: dict[str, Any]) -> bool:
    ctx = payload.get("ctx")
    if not isinstance(ctx, dict):
        return False
    if ctx.get("status_code") == 402:
        return True
    err = ctx.get("error")
    return isinstance(err, str) and "402" in err and "exhausted" in err.lower()


def collect() -> dict[str, Any]:
    if not LOG_PATH.exists():
        return {"id": "grok", "name": NAME, "status": "no_creds", "windows": []}
    try:
        used: float | None = None
        end: str | None = None
        exhausted = False
        for line in _tail_lines(LOG_PATH):
            try:
                payload = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("msg") == BILLING_MSG:
                config = _as_dict(_as_dict(payload.get("ctx")).get("config"))
                period = _as_dict(config.get("currentPeriod"))
                if end is None and isinstance(period.get("end"), str):
                    end = period["end"]
                pct = config.get("creditUsagePercent")
                if isinstance(pct, (int, float)):
                    used = 100.0 if exhausted else float(pct)
                    if end is not None:
                        break
            elif not exhausted and used is None and _exhausted(payload):
                exhausted = True
    except OSError:
        return {"id": "grok", "name": NAME, "status": "error", "windows": []}
    if used is None:
        if not exhausted:
            return {"id": "grok", "name": NAME, "status": "no_creds", "windows": []}
        used = 100.0
    remaining = -1
    if end is not None:
        try:
            reset = datetime.fromisoformat(end[:-1] + "+00:00" if end.endswith("Z") else end)
            if reset.tzinfo is not None:
                remaining = max(0, int((reset.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()))
        except ValueError:
            pass
    return {
        "id": "grok",
        "name": NAME,
        "status": "ok",
        "windows": [{"label": "wk", "used_pct": used, "resets_in_s": remaining}],
    }
