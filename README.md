# Accounts Helper

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

Remote debugging is enabled by default (base port 9222). Override with `DEBUG_PORT_BASE` if needed.

```bash
./scripts/launch_monkeys.sh
```

## Auto-fill login email fields

```bash
./.venv/bin/python login.py
```

## Post a message to a channel

`-n` and `-c` map to entries in `servers.json`.

```bash
./scripts/launch_monkeys.sh
./.venv/bin/python post_message.py -i "test" -n 1 -c general
```

To send concurrently:

```bash
./.venv/bin/python post_message.py -i "test" -n 1 -c general --parallel
```
