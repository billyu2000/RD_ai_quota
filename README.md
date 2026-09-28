# AI Quota Display

LilyGO T-Display-S3 desk display for Claude, Codex, Grok, and Z.AI quota.
The Mac reads local credentials, then pushes numbers over USB. The screen
rotates `Claude → Codex → Grok → Z.AI`.

Flashing this firmware replaces NerdMiner v2.

## One-time setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r host/requirements.txt platformio
```

## Flash the board

```bash
source .venv/bin/activate
cd firmware
pio run -t upload
```

If upload fails: hold **BOOT**, tap **RST**, release **BOOT**, then retry.

## Mac menu bar app

Double-click `macos/AI Quota.app`, or:

```bash
./run.sh app
```

A status item appears on the right of the menu bar (`C35 X0 G68 Z1`). Click it for per-provider 5h / weekly numbers, USB status, pause, and rotation interval.

To open at login: System Settings → General → Login Items → add **AI Quota**.

The terminal daemon still works:

```bash
./run.sh run
```

Use only one of `app` or `run` at a time so they do not share the USB port.

Settings (picked up live, no reboot):

```bash
./run.sh set --interval 8
./run.sh set --order claude,codex,grok,zai
./run.sh set --brightness 180
./run.sh set --zai-key YOUR_ZAI_KEY
./run.sh status
```

Config file: `~/.config/ai-quota/config.json`

## Buttons

- GPIO0 / BOOT: next provider
- GPIO14: pause / resume rotation

## Notes

- Claude, Codex, and Grok use credentials already on this Mac.
- Z.AI needs `ZAI_API_KEY` or `python -m ai_quota set --zai-key ...`
- Tokens stay on the Mac. The board only receives percentages and reset times.
