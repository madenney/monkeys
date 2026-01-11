# Monkeys

## What this is

Monkeys launches multiple Discord profiles and watches messages via Chrome remote
debugging. It can also accept simple commands (goto/say) from stdin, a local
socket, or a Discord admin account.

## Requirements

- Python 3 with `selenium`
- Chrome/Chromium installed (for remote debugging)

## Python virtual environment

Use a local venv for scripts like `login.py`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install selenium
```

To use the venv later:

```bash
source .venv/bin/activate
```

## Launching monkey instances

Remote debugging is enabled by default (base port 9222). Launches are headless
by default; pass `-d` to show windows. Override with `DEBUG_PORT_BASE` if needed.

```bash
./scripts/launch_monkeys.sh
./scripts/launch_monkeys.sh -d
```

## Configuration files

- Copy `accounts_template.json` to `accounts.json` and fill in your monkey accounts.
- Copy `.env.example` to `.env` and set your Discord IDs (admin + servers/channels).
- `servers.json` references `${VARS}` from `.env`, so you can keep IDs out of git.

## Control commands

Commands work from stdin, the control socket, or Discord (prefix with `monkeys`).

Examples:

- `servers`
- `goto 1:1`
- `@monkey-2 say hello`
- `go home`

## Auto-fill login email fields

```bash
./.venv/bin/python login.py
```

## Post a message to a channel

`-n` and `-c` map to entries in `servers.json` (IDs come from `.env`).

```bash
./scripts/launch_monkeys.sh
./.venv/bin/python post_message.py -i "test" -n 1 -c general
```

To send concurrently:

```bash
./.venv/bin/python post_message.py -i "test" -n 1 -c general --parallel
```
