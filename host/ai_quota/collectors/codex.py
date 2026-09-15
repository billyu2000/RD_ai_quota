from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NAME = "Codex"


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


def _auth() -> dict[str, str]:
    path = Path.home() / ".codex" / "auth.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    tokens = data.get("tokens") if isinstance(data, dict) else None
    if isinstance(tokens, dict):
        if isinstance(tokens.get("access_token"), str):
            out["access_token"] = tokens["access_token"]
        if isinstance(tokens.get("account_id"), str):
            out["account_id"] = tokens["account_id"]
    return out


def collect() -> dict[str, Any]:
    creds = _auth()
    token = creds.get("access_token")
    account = creds.get("account_id")
    if not token or not account:
        return {"id": "codex", "name": NAME, "status": "no_creds", "windows": []}

    status, data = _http_get(
        "https://chatgpt.com/backend-api/wham/usage",
        {
            "Authorization": f"Bearer {token}",
            "chatgpt-account-id": account,
            "User-Agent": "codex-cli",
            "Content-Type": "application/json",
        },
    )
    if status != 200 or not isinstance(data, dict):
        return {
            "id": "codex",
            "name": NAME,
            "status": "error",
            "windows": [],
            "error": f"HTTP {status}",
        }

    windows: list[dict[str, Any]] = []
    rate = data.get("rate_limit") if isinstance(data.get("rate_limit"), dict) else {}
    for raw in (rate.get("primary_window"), rate.get("secondary_window")):
        if not isinstance(raw, dict):
            continue
        win_secs = int(raw.get("limit_window_seconds") or 0)
        used = float(raw.get("used_percent") or 0)
        reset_secs = int(raw.get("reset_after_seconds") or 0)
        label = f"{win_secs // 3600}h" if win_secs and win_secs <= 86400 else "7d"
        if win_secs and win_secs <= 86400:
            label = f"{max(1, win_secs // 3600)}h"
        else:
            label = "7d"
        windows.append({"label": label, "used_pct": used, "resets_in_s": max(0, reset_secs)})

    return {"id": "codex", "name": NAME, "status": "ok", "windows": windows}
