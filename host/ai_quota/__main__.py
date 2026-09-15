from __future__ import annotations

import argparse
import json
import sys

from . import __version__, config as cfgmod
from .collectors import collect_all
from .serial_link import find_port


def cmd_run(_: argparse.Namespace) -> int:
    from .daemon import run_forever

    run_forever()
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    cfg = cfgmod.load()
    if args.interval is not None:
        cfg["interval_ms"] = max(1, int(args.interval)) * 1000
    if args.order:
        order = [x.strip() for x in args.order.split(",") if x.strip()]
        unknown = [x for x in order if x not in cfgmod.VALID_IDS]
        if unknown:
            print(f"unknown providers: {', '.join(unknown)}", file=sys.stderr)
            return 2
        cfg["order"] = order
    if args.brightness is not None:
        cfg["brightness"] = max(10, min(255, int(args.brightness)))
    if args.paused:
        cfg["paused"] = True
    if args.resume:
        cfg["paused"] = False
    if args.zai_key:
        cfg["zai_api_key"] = args.zai_key
    if args.port:
        cfg["port"] = args.port
    path = cfgmod.save(cfg)
    print(f"saved {path}")
    print(json.dumps({k: cfg[k] for k in ("interval_ms", "order", "brightness", "paused")}, indent=2))
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    cfg = cfgmod.load()
    port = find_port(cfg.get("port") or "")
    print(f"port: {port or 'not found'}")
    print(f"config: {cfgmod.config_path()}")
    print(
        json.dumps(
            {
                "interval_ms": cfg["interval_ms"],
                "order": cfg["order"],
                "brightness": cfg["brightness"],
                "paused": cfg["paused"],
                "has_zai_key": bool(cfg.get("zai_api_key")),
            },
            indent=2,
        )
    )
    last = cfgmod.status_path()
    if last.exists():
        print("--- last push ---")
        print(last.read_text())
    return 0


def cmd_collect(_: argparse.Namespace) -> int:
    cfg = cfgmod.load()
    print(json.dumps(collect_all(cfg), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ai-quota", description="ESP32-S3 AI quota display")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="collect quotas and push to the display")
    p_run.set_defaults(func=cmd_run)

    p_set = sub.add_parser("set", help="save display settings on this Mac")
    p_set.add_argument("--interval", type=int, help="seconds per screen")
    p_set.add_argument("--order", help="comma list, e.g. claude,codex,grok,zai")
    p_set.add_argument("--brightness", type=int, help="10-255")
    p_set.add_argument("--paused", action="store_true")
    p_set.add_argument("--resume", action="store_true")
    p_set.add_argument("--zai-key", dest="zai_key", help="Z.AI API key")
    p_set.add_argument("--port", help="override serial port")
    p_set.set_defaults(func=cmd_set)

    p_status = sub.add_parser("status", help="show port, config, last payload")
    p_status.set_defaults(func=cmd_status)

    p_collect = sub.add_parser("collect", help="print live quotas without the device")
    p_collect.set_defaults(func=cmd_collect)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
