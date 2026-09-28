from __future__ import annotations

import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSNoBorder,
    NSScrollView,
    NSStatusBar,
    NSTextField,
    NSVariableStatusItemLength,
    NSView,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
import objc
from Foundation import NSObject, NSTimer, NSMakeRect

from . import config as cfgmod
from .daemon import run_forever
from .protocol import format_reset_local, normalize_label, sort_windows

SHORT = {"claude": "C", "codex": "X", "grok": "G", "zai": "Z"}
NAMES = {"claude": "Claude", "codex": "Codex", "grok": "Grok", "zai": "Z.AI"}
ORDER = ("claude", "codex", "grok", "zai")
LOG = Path.home() / ".config" / "ai-quota" / "app.log"


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}\n"
    try:
        with LOG.open("a") as handle:
            handle.write(line)
    except OSError:
        pass
    print(msg, flush=True)


def _reset_at(window: dict[str, Any]) -> str:
    return window.get("resets_at") or format_reset_local(window.get("resets_in_s"))


def _pct_pair(provider: dict[str, Any] | None) -> str:
    if not provider:
        return "—"
    windows = sort_windows(list(provider.get("windows") or []))
    if provider.get("status") != "ok" or not windows:
        return provider.get("status") or "—"
    first = f"{windows[0]['used_pct']:.0f}%"
    if len(windows) > 1:
        return f"{first}  ({windows[1]['used_pct']:.0f}%)"
    return first


def _reset_tag(provider: dict[str, Any] | None) -> str:
    if not provider or provider.get("status") != "ok":
        return ""
    windows = sort_windows(list(provider.get("windows") or []))
    if not windows:
        return ""
    reset_at = _reset_at(windows[0])
    if not reset_at:
        return ""
    return f"   ↻{normalize_label(windows[0].get('label'))} {reset_at}"


def _detail_lines(provider: dict[str, Any] | None) -> list[str]:
    if not provider:
        return ["", ""]
    windows = sort_windows(list(provider.get("windows") or []))
    lines = []
    for window in windows[:2]:
        part = f"{normalize_label(window.get('label'))} {window.get('used_pct', 0):.0f}%"
        reset_at = _reset_at(window)
        if reset_at:
            part += f"  ↻ {reset_at}"
        lines.append(part)
    while len(lines) < 2:
        lines.append("")
    return lines


def _title(providers: list[dict[str, Any]], connected: bool) -> str:
    if not providers:
        return " AI Quota"
    bits = []
    for provider in providers:
        letter = SHORT.get(provider.get("id"), "?")
        windows = sort_windows(list(provider.get("windows") or []))
        if provider.get("status") != "ok" or not windows:
            bits.append(f"{letter}–")
        else:
            bits.append(f"{letter}{windows[0]['used_pct']:.0f}")
    text = "  ".join(bits)
    if not connected:
        text += "  USB"
    return " " + text


def _label(rect, text, size=13, bold=False, color=None):
    field = NSTextField.alloc().initWithFrame_(rect)
    field.setStringValue_(text)
    field.setBezeled_(False)
    field.setBordered_(False)
    field.setDrawsBackground_(False)
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    if color is not None:
        field.setTextColor_(color)
    return field


class _FlippedView(NSView):
    def isFlipped(self) -> bool:
        return True


def _icon_path() -> str:
    candidates = [
        Path(__file__).with_name("status_icon.png"),
        Path(__file__).resolve().parents[2] / "macos" / "AI Quota.app" / "Contents" / "Resources" / "status_icon.png",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


class AppDelegate(NSObject):
    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self._lock = threading.Lock()
        self._providers: list[dict[str, Any]] = []
        self._connected = False
        self._port = ""
        self._wifi = 0
        self._stop = threading.Event()
        self.status_item = None
        self.window = None
        self.rows = {}
        self.usb_field = None
        self.pause_button = None
        return self

    def applicationDidFinishLaunching_(self, _notification):
        try:
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
            self._setup_status_item()
            self._setup_window()
            threading.Thread(target=self._run_bridge, daemon=True).start()
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0, self, "tick:", None, True
            )
            NSApp.activateIgnoringOtherApps_(True)
            self.window.makeKeyAndOrderFront_(None)
            _log("app launched")
        except Exception:
            _log(traceback.format_exc())

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, has_windows):
        if self.window:
            self.window.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)
        return True

    def applicationShouldTerminateAfterLastWindowClosed_(self, _app):
        return False

    def _run_bridge(self):
        try:
            run_forever(on_update=self._on_update, should_stop=self._stop.is_set, log=_log)
        except Exception:
            _log(traceback.format_exc())

    def _on_update(self, connected=None, port=None, providers=None, error=None, wifi_clients=None, **_):
        with self._lock:
            if connected is not None:
                self._connected = bool(connected)
            if port is not None:
                self._port = port or ""
            if providers is not None:
                self._providers = list(providers)
            if wifi_clients is not None:
                self._wifi = int(wifi_clients)

    def _setup_status_item(self):
        bar = NSStatusBar.systemStatusBar()
        item = bar.statusItemWithLength_(NSVariableStatusItemLength)
        item.setVisible_(True)
        try:
            item.setAutosaveName_("AIQuotaStatusItem")
        except Exception:
            pass
        button = item.button()
        icon = _icon_path()
        if button is not None:
            if icon:
                image = NSImage.alloc().initWithContentsOfFile_(icon)
                if image:
                    image.setTemplate_(True)
                    image.setSize_((18.0, 18.0))
                    button.setImage_(image)
            button.setTitle_(" AI Quota")
            button.setToolTip_("AI Quota — click for menu")
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        show = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Show AI Quota", "showWindow:", "")
        show.setTarget_(self)
        menu.addItem_(show)
        menu.addItem_(NSMenuItem.separatorItem())
        self.menu_rows = {}
        for key in ORDER:
            row = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(NAMES[key], None, "")
            row.setEnabled_(False)
            menu.addItem_(row)
            self.menu_rows[key] = row
        menu.addItem_(NSMenuItem.separatorItem())
        self.menu_toggles = {}
        device_menu = NSMenu.alloc().init()
        for idx, key in enumerate(ORDER):
            toggle = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(NAMES[key], "togglePlatform:", "")
            toggle.setTarget_(self)
            toggle.setTag_(idx)
            device_menu.addItem_(toggle)
            self.menu_toggles[key] = toggle
        device_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Platforms", None, "")
        device_root.setSubmenu_(device_menu)
        menu.addItem_(device_root)
        menu.addItem_(NSMenuItem.separatorItem())
        self.menu_usb = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Display: waiting", None, "")
        self.menu_usb.setEnabled_(False)
        menu.addItem_(self.menu_usb)
        pause = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Pause rotation", "togglePause:", "")
        pause.setTarget_(self)
        menu.addItem_(pause)
        self.menu_pause = pause
        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit AI Quota", "quitApp:", "q")
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)
        item.setMenu_(menu)
        self.status_item = item

    def _setup_window(self):
        mask = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(240, 240, 460, 420),
            mask,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("AI Quota")
        window.setReleasedWhenClosed_(False)
        window.center()
        root = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 460, 420))
        title = _label(NSMakeRect(24, 388, 280, 28), "AI Quota", 22, True)
        self.usb_field = _label(NSMakeRect(24, 364, 410, 20), "Waiting for ESP32-S3…", 12)
        self.usb_field.setTextColor_(NSColor.secondaryLabelColor())
        root.addSubview_(title)
        root.addSubview_(self.usb_field)

        content_h = 8 + len(ORDER) * 80
        doc = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, 460, content_h))
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 60, 460, 296))
        scroll.setDocumentView_(doc)
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(NSNoBorder)
        scroll.setDrawsBackground_(False)
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        root.addSubview_(scroll)

        self.rows = {}
        for idx, key in enumerate(ORDER):
            y = 8 + idx * 80
            name = _label(NSMakeRect(24, y + 6, 140, 22), NAMES[key], 16, True)
            pct = _label(NSMakeRect(170, y + 4, 180, 24), "—", 20, True)
            detail = _label(NSMakeRect(24, y + 30, 410, 16), "", 12)
            detail2 = _label(NSMakeRect(24, y + 48, 410, 16), "", 12)
            detail.setTextColor_(NSColor.secondaryLabelColor())
            detail2.setTextColor_(NSColor.secondaryLabelColor())
            show = NSButton.alloc().initWithFrame_(NSMakeRect(362, y + 10, 84, 30))
            show.setButtonType_(4)  # NSSwitchButton
            show.setTitle_("Enabled")
            show.setTarget_(self)
            show.setAction_("togglePlatform:")
            show.setTag_(idx)
            doc.addSubview_(name)
            doc.addSubview_(pct)
            doc.addSubview_(detail)
            doc.addSubview_(detail2)
            doc.addSubview_(show)
            self.rows[key] = {"name": name, "pct": pct, "detail": detail, "detail2": detail2, "show": show}

        self.pause_button = NSButton.alloc().initWithFrame_(NSMakeRect(24, 16, 160, 32))
        self.pause_button.setTitle_("Pause rotation")
        self.pause_button.setBezelStyle_(1)
        self.pause_button.setTarget_(self)
        self.pause_button.setAction_("togglePause:")
        hint = _label(NSMakeRect(200, 20, 230, 24), "Menu bar icon is on the right →", 11)
        hint.setTextColor_(NSColor.secondaryLabelColor())
        root.addSubview_(self.pause_button)
        root.addSubview_(hint)
        window.setContentView_(root)
        self.window = window

    def tick_(self, _timer):
        try:
            self._refresh()
        except Exception:
            _log(traceback.format_exc())

    def _refresh(self):
        with self._lock:
            providers = list(self._providers)
            connected = self._connected
            port = self._port
        title = _title(providers, connected)
        button = self.status_item.button() if self.status_item else None
        if button is not None:
            button.setTitle_(title)
        cfg = cfgmod.load()
        disabled = set(cfg.get("disabled") or [])
        by_id = {p.get("id"): p for p in providers}
        for key in ORDER:
            provider = by_id.get(key)
            pair = "off" if key in disabled else _pct_pair(provider)
            if key in self.menu_rows:
                self.menu_rows[key].setTitle_(f"{NAMES[key]}    {pair}{_reset_tag(provider)}")
            if key in self.rows:
                self.rows[key]["pct"].setStringValue_(pair)
                lines = ["disabled — not tracked", ""] if key in disabled else _detail_lines(provider)
                self.rows[key]["detail"].setStringValue_(lines[0])
                self.rows[key]["detail2"].setStringValue_(lines[1])
        if connected:
            usb = f"Display connected  {port}"
        else:
            usb = "Display waiting for USB"
        if self._wifi:
            usb += f"  ·  wifi {self._wifi}"
        if self.menu_usb:
            self.menu_usb.setTitle_(usb)
        if self.usb_field:
            self.usb_field.setStringValue_(usb)
        cfg = cfgmod.load()
        paused = bool(cfg.get("paused"))
        if self.menu_pause:
            self.menu_pause.setState_(1 if paused else 0)
        if self.pause_button:
            self.pause_button.setTitle_("Resume rotation" if paused else "Pause rotation")
        disabled = set(cfg.get("disabled") or [])
        for key in ORDER:
            on = key not in disabled
            if key in self.menu_toggles:
                self.menu_toggles[key].setState_(1 if on else 0)
            if key in self.rows and self.rows[key].get("show"):
                self.rows[key]["show"].setState_(1 if on else 0)

    def showWindow_(self, _sender):
        if self.window:
            self.window.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)

    def togglePause_(self, _sender):
        cfg = cfgmod.load()
        cfg["paused"] = not bool(cfg.get("paused"))
        cfgmod.save(cfg)
        self._refresh()

    def togglePlatform_(self, sender):
        key = ORDER[int(sender.tag())]
        cfg = cfgmod.load()
        disabled = [x for x in (cfg.get("disabled") or []) if x in cfgmod.VALID_IDS]
        if key in disabled:
            disabled.remove(key)
        else:
            disabled.append(key)
        cfg["disabled"] = disabled
        cfgmod.save(cfg)
        self._refresh()

    def quitApp_(self, _sender):
        self._stop.set()
        NSApp.terminate_(None)


def run_app() -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        _log("starting Cocoa app")
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        delegate = AppDelegate.alloc().init()
        app.setDelegate_(delegate)
        app.activateIgnoringOtherApps_(True)
        app.run()
    except Exception:
        _log(traceback.format_exc())
        raise
