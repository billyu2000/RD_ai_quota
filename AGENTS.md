# AGENTS.md

Two-component system: a LilyGO T-Display-S3 (ESP32-S3) desk display for AI quota, driven over USB by a macOS Python host.

- `host/ai_quota/` — Python package. Always run as `python -m ai_quota` from `host/` (or via `./run.sh`, which activates `.venv`, `cd`s to `host/`, and defaults to the `app` subcommand).
- `firmware/` — PlatformIO project (env `t-display-s3`). TFT_eSPI is configured entirely via `build_flags` in `firmware/platformio.ini`; there is no `User_Setup.h` — do not create one.
- `macos/AI Quota.app` — shell shim that execs the repo's `.venv` python. Not self-contained: it breaks if the repo or `.venv` moves. Logs to `~/.config/ai-quota/app.log`.

## Commands

```bash
# one-time setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r host/requirements.txt platformio

./run.sh app        # menu bar app (default when no args)
./run.sh run        # terminal daemon
./run.sh collect    # print live quotas as JSON, no device needed
./run.sh status     # port, config, last pushed payload
./run.sh set --interval 8 --order claude,codex,grok,zai --brightness 180 --zai-key KEY
./run.sh set --disable grok,zai   # turn platforms off (no tracking, hidden from device; --enable to turn on)
./run.sh set --listen-port 8788   # TCP port served on the LAN for wifi displays (0 disables)

# firmware: build/flash (from firmware/)
pio run -t upload
pio device monitor  # 115200, esp32_exception_decoder enabled
# if upload fails: hold BOOT, tap RST, release BOOT, retry

# regenerate firmware/src/icons.h from images/ (requires Pillow, NOT in requirements.txt)
python firmware/tools/gen_icons.py
```

No tests, linters, or CI exist in this repo.

## Architecture

- Serial protocol: newline-delimited JSON at 115200 over USB CDC. Frames `quota`/`config`/`ping` go host→board; `ack`/`hello`/`pong`/`event`/`err` go board→host. The protocol is implemented twice and must be kept in sync: `host/ai_quota/protocol.py` and `firmware/src/protocol.cpp` (window labels, ranks, clamps like `interval_ms` 1000–60000, `brightness` 10–255 are enforced on both sides, plus `daemon.py`/`config.py`).
- WiFi transport: the daemon also serves the same JSON protocol over TCP on `listen_port` (default 8788, 0 disables). The board connects over WiFi as an additional client (`firmware/src/net.cpp`); USB and WiFi run in parallel, frames are pushed to all transports. On the board: hold BOOT 3s → captive portal (AP `AI-Quota-Setup`, http://192.168.4.1) to set WiFi + host `ip:port`; "Use USB only" clears it. WiFi/host settings persist in NVS (`aiquota` namespace).
- `firmware/src/icons.h` is generated — never hand-edit; regenerate from `images/` via `firmware/tools/gen_icons.py`.
- Config lives at `~/.config/ai-quota/config.json` (override with `AI_QUOTA_CONFIG` env var), reloaded live by mtime. Defaults live in `host/ai_quota/config.py:DEFAULTS`; root `config.example.json` mirrors them — update both when adding a setting.
- Collectors each read different local credentials (macOS-only assumptions):
  - Claude: Keychain item `Claude Code-credentials` (via `security find-generic-password`) + `~/.claude.json` `cachedUsageUtilization` fallback cache.
  - Codex: `~/.codex/auth.json` (ChatGPT backend API).
  - Grok: tails `~/.grok/logs/unified.jsonl`.
  - Z.AI: `zai_api_key` in config, else env `ZAI_API_KEY`/`ZAI_KEY`/`ZHIPU_API_KEY`/`ZHIPUAI_API_KEY`.
- Board buttons: GPIO0/BOOT = next provider, GPIO14 = pause/resume rotation.

## Gotchas

- Run only one of `app` or `run` at a time — they contend for the USB serial port.
- Host targets macOS specifically (Keychain, rumps, pyobjc); don't assume Linux portability.
- Board firmware replaces NerdMiner v2 on this device.
- Tokens/credentials never leave the Mac; the board receives only percentages and reset times. Keep it that way.
