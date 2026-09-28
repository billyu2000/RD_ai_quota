from __future__ import annotations

import time

from serial import SerialException

from . import config as cfgmod
from .collectors import collect_all
from .netserver import NetServer
from .protocol import config_frame, parse_line, quota_frame
from .serial_link import find_port, open_port, read_lines, write_line

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


def _enabled(cfg, providers):
    disabled = set(cfg.get("disabled") or [])
    return [p for p in providers if p.get("id") not in disabled]


def run_forever(on_update=None, should_stop=None, log=None) -> None:
    last_poll = 0.0
    last_cfg_mtime = 0.0
    ser = None
    port = ""
    providers: list = []
    emit = log or _log
    stop = should_stop or (lambda: False)

    net = None

    def push(frame_line: str) -> None:
        """Send a frame to every connected transport (USB + WiFi clients)."""
        nonlocal ser, port
        if net is not None:
            net.broadcast(frame_line)
        if ser is not None:
            try:
                write_line(ser, frame_line)
            except SERIAL_ERRORS as exc:
                emit(f"ai-quota: serial lost ({exc})")
                ser = _drop(ser)
                port = ""
                if on_update:
                    on_update(connected=False, port="", providers=providers)

    def handle_device_line(line: str) -> None:
        msg = parse_line(line)
        if not msg:
            return
        kind = msg.get("type")
        if kind == "hello":
            emit(f"ai-quota: device hello fw={msg.get('fw')}")
            if providers:
                push(quota_frame(_enabled(cfgmod.load(), providers)))
                push(config_frame(cfgmod.load()))
        elif kind == "ack":
            emit(f"ai-quota: ack {msg.get('what')}")
        elif kind == "pong":
            pass
        elif kind == "err":
            emit(f"ai-quota: device parse error {msg.get('msg')}")
        elif kind == "event":
            emit(f"ai-quota: button {msg.get('btn')}")

    cfg0 = cfgmod.load()
    if cfg0.get("listen_port"):
        net = NetServer(int(cfg0["listen_port"]), on_line=handle_device_line, log=emit)

        def _on_wifi_connect(addr):
            cfg = cfgmod.load()
            if providers:
                net.broadcast(quota_frame(_enabled(cfg, providers)))
                net.broadcast(config_frame(cfg))

        net.on_connect = _on_wifi_connect
        net.start()

    emit("ai-quota: running")
    while not stop():
        cfg = cfgmod.load()
        try:
            mtime = cfgmod.config_path().stat().st_mtime if cfgmod.config_path().exists() else 0
        except OSError:
            mtime = 0

        now = time.time()
        if now - last_poll >= cfg["poll_seconds"] or last_poll == 0:
            providers = collect_all(cfg)
            payload = {
                "ts": int(now),
                "port": port,
                "listen_port": cfg.get("listen_port") or 0,
                "wifi_clients": net.client_count() if net else 0,
                "config": {
                    "interval_ms": cfg["interval_ms"],
                    "order": cfg["order"],
                    "brightness": cfg["brightness"],
                    "paused": cfg["paused"],
                    "disabled": cfg.get("disabled") or [],
                },
                "providers": providers,
            }
            cfgmod.save_status(payload)
            summary = ", ".join(
                f"{p['id']}:{p['status']}"
                + (f" {p['windows'][0]['used_pct']:.0f}%" if p.get("windows") else "")
                for p in providers
            )
            emit(f"ai-quota: {summary}")
            last_poll = now
            wifi = net.client_count() if net else 0
            if on_update:
                on_update(connected=bool(ser and ser.is_open), port=port, providers=providers, wifi_clients=wifi)
            push(quota_frame(_enabled(cfg, providers)))
            push(config_frame(cfg))

        if ser is None or not ser.is_open:
            found = find_port(cfg.get("port") or "")
            if found:
                try:
                    ser = open_port(found)
                    port = found
                    time.sleep(0.8)
                    push(config_frame(cfg))
                    if providers:
                        push(quota_frame(_enabled(cfg, providers)))
                    emit(f"ai-quota: connected {port}")
                    if on_update:
                        on_update(connected=True, port=port, providers=providers)
                    last_cfg_mtime = mtime
                except Exception as exc:
                    emit(f"ai-quota: connect failed ({exc})")
                    ser = _drop(ser)
                    port = ""
        else:
            try:
                if mtime and mtime != last_cfg_mtime:
                    push(config_frame(cfg))
                    if providers:
                        push(quota_frame(_enabled(cfg, providers)))
                    emit("ai-quota: config updated")
                    last_cfg_mtime = mtime
                for line in read_lines(ser):
                    handle_device_line(line)
                current = find_port(cfg.get("port") or "")
                if current and current != port:
                    emit(f"ai-quota: port moved {port} -> {current}")
                    ser = _drop(ser)
                    port = ""
            except SERIAL_ERRORS as exc:
                emit(f"ai-quota: serial lost ({exc})")
                ser = _drop(ser)
                port = ""
                if on_update:
                    on_update(connected=False, port="", providers=providers)

        time.sleep(0.2)
