#!/usr/bin/env python3
"""Post monkey sounds to a Discord channel using random monkey accounts."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import post_message as pm

DEFAULT_SOUNDS_PATH = Path(__file__).resolve().parent / "monkey_sounds.json"


def load_sounds(path: Path) -> List[str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"monkey sounds file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except OSError as exc:
        print(f"failed to read monkey sounds file: {path} ({exc})", file=sys.stderr)
        sys.exit(2)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    sounds: List[str] = []
    if isinstance(data, list):
        sounds = [str(item).strip() for item in data if str(item).strip()]
    elif isinstance(data, dict) and isinstance(data.get("sounds"), list):
        sounds = [str(item).strip() for item in data["sounds"] if str(item).strip()]
    else:
        print(
            f"expected a JSON array of sounds in {path}",
            file=sys.stderr,
        )
        sys.exit(2)

    if not sounds:
        print(f"no sounds found in {path}", file=sys.stderr)
        sys.exit(2)

    return sounds


def pick_random_index(available: List[int], last_idx: Optional[int]) -> Optional[int]:
    if not available:
        return None
    if len(available) == 1:
        return available[0]
    if last_idx is None:
        return random.choice(available)
    options = [idx for idx in available if idx != last_idx]
    return random.choice(options) if options else last_idx


def attach_drivers(
    monkeys: List[Dict[str, Any]],
    *,
    debug_base: int,
    debug_step: int,
    attach_timeout: float,
    webdriver,
    WebDriverException,
) -> Tuple[Dict[int, Any], List[int]]:
    drivers: Dict[int, Any] = {}
    available: List[int] = []

    for idx, acct in enumerate(monkeys):
        acct_id = str(acct.get("id", "-"))
        port = debug_base + idx * debug_step
        address = f"127.0.0.1:{port}"

        attach_error = pm.wait_for_debugger(address, attach_timeout)
        if attach_error:
            print(
                f"{acct_id}: debugger not reachable at {address} ({attach_error})",
                file=sys.stderr,
            )
            continue
        try:
            drivers[idx] = pm.attach_driver(webdriver, address)
        except WebDriverException as exc:
            print(f"{acct_id}: failed to connect to {address} ({exc})", file=sys.stderr)
            continue
        available.append(idx)

    return drivers, available


def close_drivers(drivers: Dict[int, Any]) -> None:
    for driver in drivers.values():
        try:
            driver.quit()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post monkey sounds to a Discord channel using random monkey accounts."
    )
    parser.add_argument(
        "--accounts",
        type=Path,
        default=Path(__file__).resolve().parent / "accounts.json",
        help="Path to accounts.json",
    )
    parser.add_argument(
        "--servers",
        type=Path,
        default=Path(__file__).resolve().parent / "servers.json",
        help="Path to servers.json",
    )
    parser.add_argument(
        "--sounds",
        type=Path,
        default=DEFAULT_SOUNDS_PATH,
        help="Path to monkey_sounds.json",
    )
    parser.add_argument(
        "-n",
        "--server-id",
        default="1",
        help="Server id from servers.json (default: 1).",
    )
    parser.add_argument(
        "-c",
        "--channel",
        required=True,
        help="Channel name to send the message to.",
    )
    parser.add_argument(
        "--count",
        type=int,
        help="Only handle the first COUNT monkey accounts.",
    )
    parser.add_argument(
        "--debug-base",
        type=int,
        help=f"Remote debugging base port (matches DEBUG_PORT_BASE). Defaults to {pm.DEFAULT_DEBUG_BASE}.",
    )
    parser.add_argument(
        "--debug-step",
        type=int,
        help="Remote debugging port step (matches DEBUG_PORT_STEP).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=pm.DEFAULT_TIMEOUT,
        help="Seconds to wait for the message box.",
    )
    parser.add_argument(
        "--attach-timeout",
        type=float,
        default=pm.DEFAULT_ATTACH_TIMEOUT,
        help="Seconds to wait for the debugger port before giving up.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to sleep between messages.",
    )

    args = parser.parse_args()

    servers = pm.load_servers(args.servers)
    server = pm.find_server_by_id(servers, args.server_id)
    if not server:
        choices = ", ".join(
            f"{srv.get('id')} ({srv.get('name', 'unknown')})" for srv in servers
        )
        print(
            f"Server id {args.server_id!r} not found in {args.servers}. "
            f"Known servers: {choices}",
            file=sys.stderr,
        )
        return 2

    channel = pm.find_channel_by_name(server, args.channel)
    if not channel:
        channels = server.get("channels")
        available = ""
        if isinstance(channels, list):
            available = ", ".join(str(ch.get("name", "")) for ch in channels if ch.get("name"))
        print(
            f"Channel {args.channel!r} not found for server {server.get('name', 'unknown')}. "
            f"Known channels: {available}",
            file=sys.stderr,
        )
        return 2

    channel_url = pm.build_channel_url(server, channel)
    if not channel_url:
        print(
            "Server/channel is missing ids needed to build a Discord URL.",
            file=sys.stderr,
        )
        return 2

    accounts = pm.load_accounts(args.accounts)
    monkeys = pm.pick_monkeys(accounts, args.count)
    if not monkeys:
        print("No monkey accounts found.")
        return 0

    sounds = load_sounds(args.sounds)

    try:
        env_base = pm.parse_env_int("DEBUG_PORT_BASE")
        env_step = pm.parse_env_int("DEBUG_PORT_STEP")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    debug_base = args.debug_base if args.debug_base is not None else env_base
    debug_step = args.debug_step if args.debug_step is not None else (env_step or 1)

    if debug_base is None:
        debug_base = pm.DEFAULT_DEBUG_BASE

    if debug_step < 1:
        print("debug step must be >= 1", file=sys.stderr)
        return 2

    try:
        from selenium import webdriver
    except ImportError:
        print("selenium is required. Install it with 'pip install selenium'.", file=sys.stderr)
        return 2

    try:
        from selenium.common.exceptions import WebDriverException
        from selenium.webdriver.common.by import By
    except ImportError:
        print("selenium is required. Install it with 'pip install selenium'.", file=sys.stderr)
        return 2

    selectors = [
        (By.CSS_SELECTOR, "div[role='textbox'][data-slate-editor='true']"),
        (By.CSS_SELECTOR, "div[role='textbox'][aria-label*='Message']"),
        (By.CSS_SELECTOR, "div[role='textbox'][aria-label*='Send']"),
        (By.CSS_SELECTOR, "div[role='textbox'][contenteditable='true']"),
    ]

    print(f"Found {len(monkeys)} monkey account(s).")
    print(f"Using debug base {debug_base} with step {debug_step}.")
    print(f"Server: {server.get('name', 'unknown')} ({server.get('id', 'n/a')})")
    print(f"Channel: {channel.get('name', 'unknown')}")
    print(f"Channel URL: {channel_url}")
    print(f"Sounds: {len(sounds)}")

    drivers, available = attach_drivers(
        monkeys,
        debug_base=debug_base,
        debug_step=debug_step,
        attach_timeout=args.attach_timeout,
        webdriver=webdriver,
        WebDriverException=WebDriverException,
    )
    if not available:
        print("No monkey debuggers available.", file=sys.stderr)
        return 2

    last_idx: Optional[int] = None
    failures = 0

    try:
        for sound in sounds:
            idx = pick_random_index(available, last_idx)
            if idx is None:
                print("No available monkey accounts to send messages.", file=sys.stderr)
                failures += 1
                break
            acct_id = str(monkeys[idx].get("id", "-"))
            driver = drivers[idx]
            print(f"{acct_id}: sending {sound!r}")

            result = pm.post_message(driver, channel_url, sound, selectors, args.timeout)
            if result == "sent":
                pass
            elif result == "no_message_box":
                print(f"{acct_id}: message box not found (channel not ready or not logged in)")
                failures += 1
            elif result == "no_permission":
                print(f"{acct_id}: cannot send in this channel (permissions)")
                failures += 1
            elif result == "navigation_failed":
                print(f"{acct_id}: failed to open channel")
                failures += 1
            else:
                print(f"{acct_id}: failed to send message")
                failures += 1

            last_idx = idx
            if args.delay > 0:
                time.sleep(args.delay)
    finally:
        close_drivers(drivers)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
