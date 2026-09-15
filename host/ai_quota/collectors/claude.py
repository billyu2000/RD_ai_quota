from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NAME = "Claude"
CACHE_STALE_S = 30 * 60


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, Any]:
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except HTTPError as exc:
        return exc.code, exc.reason
    except (URLError, TimeoutError, OSError) as exc:
        return 0, str(exc)


def _resets_in(iso_time: str | None) -> int:
    if not iso_time:
        return -1
    try:
        reset = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        return max(0, int((reset - datetime.now(timezone.utc)).total_seconds()))
    except ValueError:
        return -1


def _windows_from_usage(data: dict[str, Any]) -> list[dict[str, Any]]:
    windows = []
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        used = block.get("utilization")
        if not isinstance(used, (int, float)):
            continue
        windows.append(
            {
                "label": label,
                "used_pct": float(used),
                "resets_in_s": _resets_in(block.get("resets_at")),
            }
        )
    return windows


def _oauth_token() -> str | None:
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return None
        creds = json.loads(proc.stdout.strip())
        if isinstance(creds, dict) and "claudeAiOauth" in creds:
            token = creds["claudeAiOauth"].get("accessToken")
            return token if isinstance(token, str) else None
        token = creds.get("accessToken") if isinstance(creds, dict) else None
        return token if isinstance(token, str) else None
    except Exception:
        return None


def _cached(max_age: float | None = CACHE_STALE_S) -> dict[str, Any] | None:
    path = Path.home() / ".claude.json"
    try:
        root = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    cached = root.get("cachedUsageUtilization") if isinstance(root, dict) else None
    if not isinstance(cached, dict):
        return None
    fetched = cached.get("fetchedAtMs")
    if not isinstance(fetched, (int, float)) or fetched <= 0:
        return None
    age = time.time() - fetched / 1000.0
    if max_age is not None and age > max_age:
        return None
    util = cached.get("utilization")
    if not isinstance(util, dict):
        return None
    windows = _windows_from_usage(util)
    if not windows:
        return None
    return {"id": "claude", "name": NAME, "status": "ok", "windows": windows, "source": "cache"}


def collect() -> dict[str, Any]:
    fresh = _cached(120)
    if fresh:
        return fresh

    token = _oauth_token()
    if token:
        status, data = _http_get(
            "https://api.anthropic.com/api/oauth/usage",
            {
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "Content-Type": "application/json",
            },
        )
        if status == 200 and isinstance(data, dict):
            windows = _windows_from_usage(data)
            if windows:
                return {"id": "claude", "name": NAME, "status": "ok", "windows": windows}
        cached = _cached(None)
        if cached:
            return cached
        return {
            "id": "claude",
            "name": NAME,
            "status": "error",
            "windows": [],
            "error": f"HTTP {status}",
        }

    cached = _cached(None)
    if cached:
        return cached
    return {"id": "claude", "name": NAME, "status": "no_creds", "windows": []}
