from __future__ import annotations

import time
from typing import Optional

import serial
from serial.tools import list_ports


def find_port(preferred: str = "") -> Optional[str]:
    if preferred:
        return preferred
    try:
        ports = list(list_ports.comports())
    except OSError:
        return None
    for info in ports:
        hwid = (info.hwid or "").upper()
        mfr = (info.manufacturer or "").lower()
        desc = (info.description or "").lower()
        if "303A" in hwid or "espressif" in mfr or "usb jtag" in desc:
            return info.device
    for info in ports:
        if "usbmodem" in info.device:
            return info.device
    return None


def open_port(port: str, baud: int = 115200) -> serial.Serial:
    return serial.Serial(port, baudrate=baud, timeout=0.2)


def write_line(ser: serial.Serial, line: str) -> None:
    data = (line + "\n").encode("utf-8")
    for i in range(0, len(data), 64):
        ser.write(data[i : i + 64])
        ser.flush()
        time.sleep(0.008)


def read_lines(ser: serial.Serial) -> list[str]:
    if not ser or not ser.is_open:
        raise OSError("serial port closed")
    lines: list[str] = []
    waiting = ser.in_waiting
    while waiting:
        raw = ser.readline()
        if not raw:
            break
        try:
            lines.append(raw.decode("utf-8", "replace").rstrip("\r\n"))
        except Exception:
            continue
        waiting = ser.in_waiting
    return lines


def wait_for_port(preferred: str = "", timeout: float = 0) -> str:
    deadline = time.time() + timeout if timeout else None
    while True:
        port = find_port(preferred)
        if port:
            return port
        if deadline is not None and time.time() >= deadline:
            raise TimeoutError("ESP32-S3 serial port not found")
        time.sleep(1)
