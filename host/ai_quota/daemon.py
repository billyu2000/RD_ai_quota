from __future__ import annotations

import time

from serial import SerialException

from . import config as cfgmod
from .collectors import collect_all
from .protocol import config_frame, parse_line, quota_frame
from .serial_link import find_port, open_port, read_lines, wait_for_port, write_line

SERIAL_ERRORS = (SerialException, OSError, TimeoutError)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _drop(ser):
    if ser is None:
        return None
    try:
        ser.close()
    except Exception:
        pass
    return None


def run_forever() -> None:
    last_poll = 0.0
    last_cfg_mtime = 0.0
    ser = None
    port = ""

    _log("ai-quota: waiting for T-Display-S3 over USB")
    while True:
        cfg = cfgmod.load()
        try:
            mtime = cfgmod.config_path().stat().st_mtime if cfgmod.config_path().exists() else 0
        except OSError:
            mtime = 0

        if ser is None or not ser.is_open:
            try:
                port = wait_for_port(cfg.get("port") or "", timeout=0)
                ser = open_port(port)
                time.sleep(1.0)
                write_line(ser, config_frame(cfg))
                last_poll = 0
                _log(f"ai-quota: connected {port}")
            except Exception as exc:
                _log(f"ai-quota: connect failed ({exc})")
                ser = _drop(ser)
                time.sleep(2)
                continue

        now = time.time()
        try:
            if now - last_poll >= cfg["poll_seconds"]:
                providers = collect_all(cfg)
                payload = {
                    "ts": int(now),
                    "port": port,
                    "config": {
                        "interval_ms": cfg["interval_ms"],
                        "order": cfg["order"],
                        "brightness": cfg["brightness"],
                        "paused": cfg["paused"],
                    },
                    "providers": providers,
                }
                cfgmod.save_status(payload)
                write_line(ser, quota_frame(providers))
                write_line(ser, config_frame(cfg))
                summary = ", ".join(
                    f"{p['id']}:{p['status']}"
                    + (
                        f" {p['windows'][0]['used_pct']:.0f}%"
                        if p.get("windows")
                        else ""
                    )
                    for p in providers
                )
                _log(f"ai-quota: pushed {summary}")
                last_poll = now
                last_cfg_mtime = mtime
            elif mtime and mtime != last_cfg_mtime:
                write_line(ser, config_frame(cfg))
                _log("ai-quota: config updated")
                last_cfg_mtime = mtime

            for line in read_lines(ser):
                msg = parse_line(line)
                if not msg:
                    continue
                kind = msg.get("type")
                if kind == "hello":
                    _log(f"ai-quota: device hello fw={msg.get('fw')}")
                    if now - last_poll > 2:
                        last_poll = 0
                elif kind == "ack":
                    _log(f"ai-quota: ack {msg.get('what')}")
                elif kind == "err":
                    _log(f"ai-quota: device parse error {msg.get('msg')}")
                elif kind == "event":
                    _log(f"ai-quota: button {msg.get('btn')}")

            current = find_port(cfg.get("port") or "")
            if current and current != port:
                _log(f"ai-quota: port moved {port} -> {current}")
                ser = _drop(ser)
                continue
        except SERIAL_ERRORS as exc:
            _log(f"ai-quota: serial lost ({exc})")
            ser = _drop(ser)
            time.sleep(1)
            continue

        time.sleep(0.2)
