from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .claude import collect as collect_claude
from .codex import collect as collect_codex
from .grok import collect as collect_grok
from .zai import collect as collect_zai

COLLECTORS: dict[str, Callable[..., dict[str, Any]]] = {
    "claude": collect_claude,
    "codex": collect_codex,
    "grok": collect_grok,
    "zai": collect_zai,
}


def collect_all(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    order = list(cfg.get("order") or COLLECTORS.keys())
    results: dict[str, dict[str, Any]] = {}

    def run(pid: str) -> tuple[str, dict[str, Any]]:
        fn = COLLECTORS[pid]
        try:
            if pid == "zai":
                return pid, fn(cfg.get("zai_api_key") or "")
            return pid, fn()
        except Exception as exc:
            return pid, {
                "id": pid,
                "name": pid.title(),
                "status": "error",
                "windows": [],
                "error": str(exc)[:160],
            }

    with ThreadPoolExecutor(max_workers=4) as pool:
        for pid, data in pool.map(run, [p for p in order if p in COLLECTORS]):
            results[pid] = data
    return [results[pid] for pid in order if pid in results]
