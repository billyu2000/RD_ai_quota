from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NAME = "Z.AI"


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


def _key(explicit: str = "") -> str:
    if explicit:
        return explicit
    for var in ("ZAI_API_KEY", "ZAI_KEY", "ZHIPU_API_KEY", "ZHIPUAI_API_KEY"):
        value = os.environ.get(var)
        if value:
            return value
    return ""


def _resets_in_ms(ts: Any) -> int:
    try:
        reset = datetime.fromtimestamp(int(ts) / 1000.0)
        return max(0, int((reset - datetime.now()).total_seconds()))
    except (TypeError, ValueError, OSError):
        return -1


def collect(explicit_key: str = "") -> dict[str, Any]:
    key = _key(explicit_key)
    if not key:
        return {"id": "zai", "name": NAME, "status": "no_creds", "windows": []}

    status, data = _http_get(
        "https://api.z.ai/api/monitor/usage/quota/limit",
        {"Authorization": key, "Content-Type": "application/json"},
    )
    if status != 200 or not isinstance(data, dict) or not data.get("success"):
        detail = ""
        if isinstance(data, dict):
            msg = data.get("msg") or data.get("message")
            detail = f": {msg or data.get('code') or 'unsuccessful response'}"
        elif isinstance(data, str) and data.strip():
            detail = f": {data.strip()[:120]}"
        return {
            "id": "zai",
            "name": NAME,
            "status": "error",
            "windows": [],
            "error": f"HTTP {status}{detail}",
        }

    windows: list[dict[str, Any]] = []
    limits = (data.get("data") or {}).get("limits") if isinstance(data.get("data"), dict) else []
    if isinstance(limits, list):
        for limit in limits:
            if not isinstance(limit, dict):
                continue
            kind = limit.get("type")
            pct = float(limit.get("percentage") or 0)
            reset = _resets_in_ms(limit.get("nextResetTime"))
            if kind == "TOKENS_LIMIT":
                windows.append({"label": "5h", "used_pct": pct, "resets_in_s": reset})
            elif kind == "TIME_LIMIT":
                total = float(limit.get("usage") or 0)
                used = float(limit.get("currentValue") or 0)
                used_pct = (used / total * 100.0) if total else pct
                windows.append({"label": "mo", "used_pct": used_pct, "resets_in_s": reset})

    return {"id": "zai", "name": NAME, "status": "ok", "windows": windows}
