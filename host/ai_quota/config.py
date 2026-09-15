from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "interval_ms": 5000,
    "order": ["claude", "codex", "grok", "zai"],
    "brightness": 180,
    "paused": False,
    "poll_seconds": 30,
    "port": "",
    "zai_api_key": "",
}

VALID_IDS = ("claude", "codex", "grok", "zai")


def config_path() -> Path:
    override = os.environ.get("AI_QUOTA_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "ai-quota" / "config.json"


def status_path() -> Path:
    return config_path().with_name("last.json")


def load() -> dict[str, Any]:
    path = config_path()
    data = dict(DEFAULTS)
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    data["order"] = [x for x in data.get("order", DEFAULTS["order"]) if x in VALID_IDS]
    if not data["order"]:
        data["order"] = list(DEFAULTS["order"])
    data["interval_ms"] = int(data.get("interval_ms") or 5000)
    data["brightness"] = max(10, min(255, int(data.get("brightness") or 180)))
    data["paused"] = bool(data.get("paused"))
    data["poll_seconds"] = max(10, int(data.get("poll_seconds") or 30))
    data["port"] = str(data.get("port") or "")
    data["zai_api_key"] = str(data.get("zai_api_key") or "")
    return data


def save(data: dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def save_status(payload: dict[str, Any]) -> None:
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
