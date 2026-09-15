from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

TZ_PLUS_8 = timezone(timedelta(hours=8))
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WINDOW_RANK = {"5h": 0, "weekly": 1, "7d": 1, "wk": 1, "mo": 2}


def normalize_label(label: Any) -> str:
    raw = str(label or "").strip().lower()
    if raw in ("5h", "5hr", "5hour", "5-hour"):
        return "5h"
    if raw in ("7d", "wk", "week", "weekly"):
        return "weekly"
    if raw in ("mo", "month", "monthly"):
        return "mo"
    return str(label or "")


def sort_windows(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        windows,
        key=lambda w: WINDOW_RANK.get(normalize_label(w.get("label")), 9),
    )


def format_reset_local(resets_in_s: Any) -> str:
    try:
        seconds = int(resets_in_s)
    except (TypeError, ValueError):
        return ""
    if seconds < 0:
        return ""
    now = datetime.now(TZ_PLUS_8)
    when = now + timedelta(seconds=seconds)
    clock = when.strftime("%H:%M")
    if when.date() == now.date():
        return clock
    return f"{when.day} {MONTHS[when.month - 1]} {clock}"


def quota_frame(providers: list[dict[str, Any]]) -> str:
    slim = []
    for p in providers:
        slim.append(
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "status": p.get("status"),
                "windows": [
                    {
                        "label": normalize_label(w.get("label")),
                        "used_pct": w.get("used_pct"),
                        "resets_in_s": w.get("resets_in_s"),
                        "resets_at": format_reset_local(w.get("resets_in_s")),
                    }
                    for w in sort_windows(list(p.get("windows") or []))
                ],
            }
        )
    return json.dumps({"type": "quota", "ts": int(time.time()), "providers": slim}, separators=(",", ":"))


def config_frame(cfg: dict[str, Any]) -> str:
    return json.dumps(
        {
            "type": "config",
            "interval_ms": int(cfg["interval_ms"]),
            "order": list(cfg["order"]),
            "brightness": int(cfg["brightness"]),
            "paused": bool(cfg["paused"]),
        },
        separators=(",", ":"),
    )


def parse_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
