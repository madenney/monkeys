#!/usr/bin/env python3
"""Post a message in a Discord channel from monkey accounts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from monkey_watch.config import expand_env_values, load_dotenv
DEFAULT_DEBUG_BASE = 9222
DEFAULT_MESSAGE = "test"
DEFAULT_TIMEOUT = 12.0
DEFAULT_ATTACH_TIMEOUT = 6.0


def load_servers(path: Path) -> List[Dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"servers file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except OSError as exc:
        print(f"failed to read servers file: {path} ({exc})", file=sys.stderr)
        sys.exit(2)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(data, list):
        print(f"servers file must contain a JSON array: {path}", file=sys.stderr)
        sys.exit(2)

    data = expand_env_values(data)
    return data


def load_accounts(path: Path) -> List[Dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"accounts file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except OSError as exc:
        print(f"failed to read accounts file: {path} ({exc})", file=sys.stderr)
        sys.exit(2)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        print(f"missing or invalid 'accounts' list in {path}", file=sys.stderr)
        sys.exit(2)

    return accounts


def is_monkey(acct: Dict[str, Any]) -> bool:
    acct_id = str(acct.get("id", ""))
    return acct_id.startswith("monkey-") or acct_id == "monkey"


def pick_monkeys(accounts: Iterable[Dict[str, Any]], limit: Optional[int]) -> List[Dict[str, Any]]:
    monkeys = [acct for acct in accounts if is_monkey(acct)]
    if limit is None:
        return monkeys
    if limit < 0:
        return []
    return monkeys[:limit]


def parse_env_int(name: str) -> Optional[int]:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    if not value.isdigit():
        raise ValueError(f"{name} must be an integer")
    return int(value)


def normalize_channel_name(name: str) -> str:
    return name.strip().lstrip("#").lower()


def find_server_by_id(servers: Iterable[Dict[str, Any]], server_id: str) -> Optional[Dict[str, Any]]:
    needle = str(server_id)
    for server in servers:
        if str(server.get("id", "")) == needle:
            return server
    return None


def find_channel_by_name(server: Dict[str, Any], channel_name: str) -> Optional[Dict[str, Any]]:
    channels = server.get("channels")
    if not isinstance(channels, list):
        return None
    needle = normalize_channel_name(channel_name)
    for channel in channels:
        name = str(channel.get("name", ""))
        if normalize_channel_name(name) == needle:
            return channel
    return None


def build_channel_url(server: Dict[str, Any], channel: Dict[str, Any]) -> Optional[str]:
    server_id = str(server.get("server_id", "")).strip()
    channel_id = str(channel.get("id", "")).strip()
    if not server_id or not channel_id:
        return None
    return f"https://discord.com/channels/{server_id}/{channel_id}"


def wait_for_debugger(address: str, timeout: float) -> Optional[str]:
    url = f"http://{address}/json/version"
    deadline = time.monotonic() + timeout
    last_error: Optional[str] = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return None
                last_error = f"unexpected status {response.status}"
        except (urllib.error.URLError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.3)
    return last_error or "no response"


def find_message_box(driver, selectors: List[Tuple[str, str]], timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for by, selector in selectors:
            try:
                elements = driver.find_elements(by, selector)
            except Exception:
                elements = []
            for element in elements:
                try:
                    if element.is_displayed():
                        return element
                except Exception:
                    continue
        time.sleep(0.2)
    return None


def post_message(
    driver,
    url: str,
    message: str,
    selectors: List[Tuple[str, str]],
    timeout: float,
    *,
    navigate: bool = True,
):
    if navigate:
        try:
            driver.get(url)
        except Exception:
            return "navigation_failed"

    box = find_message_box(driver, selectors, timeout)
    if box is None:
        return "no_message_box"

    aria_label = (box.get_attribute("aria-label") or "").lower()
    if "permission" in aria_label or "cannot send" in aria_label or "can't send" in aria_label:
        return "no_permission"

    try:
        box.click()
        box.send_keys(message)
        box.send_keys("\n")
    except Exception:
        return "send_failed"

    return "sent"


def attach_driver(webdriver, debugger_address: str):
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", debugger_address)
    return webdriver.Chrome(options=options)


def process_account(
    acct: Dict[str, Any],
    idx: int,
    *,
    webdriver,
    WebDriverException,
    debug_base: int,
    debug_step: int,
    channel_url: str,
    message: str,
    selectors: List[Tuple[str, str]],
    timeout: float,
    attach_timeout: float,
    delay: float,
):
    acct_id = str(acct.get("id", "-"))
    port = debug_base + idx * debug_step
    address = f"127.0.0.1:{port}"

    print(f"{acct_id}: connecting to {address}")
    attach_error = wait_for_debugger(address, attach_timeout)
    if attach_error:
        print(
            f"{acct_id}: debugger not reachable at {address} ({attach_error}). "
            "Launch with DEBUG_PORT_BASE set to enable remote debugging.",
            file=sys.stderr,
        )
        return True
    try:
        driver = attach_driver(webdriver, address)
    except WebDriverException as exc:
        print(f"{acct_id}: failed to connect to {address} ({exc})")
        return True

    print(f"{acct_id}: posting message")
    try:
        result = post_message(driver, channel_url, message, selectors, timeout)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    if result == "sent":
        print(f"{acct_id}: message sent")
        failed = False
    elif result == "no_message_box":
        print(f"{acct_id}: message box not found (channel not ready or not logged in)")
        failed = True
    elif result == "no_permission":
        print(f"{acct_id}: cannot send in this channel (permissions)")
        failed = True
    elif result == "navigation_failed":
        print(f"{acct_id}: failed to open channel")
        failed = True
    else:
        print(f"{acct_id}: failed to send message")
        failed = True

    if delay > 0:
        time.sleep(delay)

    return failed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post a Discord message from monkey accounts using remote debugging."
    )
    parser.add_argument(
        "--accounts",
        type=Path,
        default=Path(__file__).resolve().parent / "accounts.json",
        help="Path to accounts.json (copy from accounts_template.json).",
    )
    parser.add_argument(
        "--servers",
        type=Path,
        default=Path(__file__).resolve().parent / "servers.json",
        help="Path to servers.json (supports ${VARS} from .env).",
    )
    parser.add_argument(
        "-i",
        "--message",
        default=DEFAULT_MESSAGE,
        help=f"Message to send (default: {DEFAULT_MESSAGE!r}).",
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
        help=f"Remote debugging base port (matches DEBUG_PORT_BASE). Defaults to {DEFAULT_DEBUG_BASE}.",
    )
    parser.add_argument(
        "--debug-step",
        type=int,
        help="Remote debugging port step (matches DEBUG_PORT_STEP).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Seconds to wait for the message box.",
    )
    parser.add_argument(
        "--attach-timeout",
        type=float,
        default=DEFAULT_ATTACH_TIMEOUT,
        help="Seconds to wait for the debugger port before giving up.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to sleep between accounts (sequential mode only).",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Send messages in parallel across accounts.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        help="Maximum concurrent workers in parallel mode (default: all accounts).",
    )

    args = parser.parse_args()
    load_dotenv()

    servers = load_servers(args.servers)
    server = find_server_by_id(servers, args.server_id)
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

    channel = find_channel_by_name(server, args.channel)
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

    channel_url = build_channel_url(server, channel)
    if not channel_url:
        print(
            "Server/channel is missing ids needed to build a Discord URL.",
            file=sys.stderr,
        )
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

    accounts = load_accounts(args.accounts)
    monkeys = pick_monkeys(accounts, args.count)

    if not monkeys:
        print("No monkey accounts found.")
        return 0

    try:
        env_base = parse_env_int("DEBUG_PORT_BASE")
        env_step = parse_env_int("DEBUG_PORT_STEP")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    debug_base = args.debug_base if args.debug_base is not None else env_base
    debug_step = args.debug_step if args.debug_step is not None else (env_step or 1)

    if debug_base is None:
        debug_base = DEFAULT_DEBUG_BASE

    if debug_step < 1:
        print("debug step must be >= 1", file=sys.stderr)
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
    print(f"Message: {args.message!r}")

    failures = 0

    if args.parallel:
        max_workers = args.max_workers or len(monkeys)
        if max_workers < 1:
            print("--max-workers must be >= 1", file=sys.stderr)
            return 2
        if max_workers > len(monkeys):
            max_workers = len(monkeys)
        print(f"Parallel mode: {max_workers} worker(s).")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    process_account,
                    acct,
                    idx,
                    webdriver=webdriver,
                    WebDriverException=WebDriverException,
                    debug_base=debug_base,
                    debug_step=debug_step,
                    channel_url=channel_url,
                    message=args.message,
                    selectors=selectors,
                    timeout=args.timeout,
                    attach_timeout=args.attach_timeout,
                    delay=0,
                )
                for idx, acct in enumerate(monkeys)
            ]
            for future in as_completed(futures):
                if future.result():
                    failures += 1
    else:
        print(f"Delay between accounts: {args.delay:.1f}s.")
        for idx, acct in enumerate(monkeys):
            if process_account(
                acct,
                idx,
                webdriver=webdriver,
                WebDriverException=WebDriverException,
                debug_base=debug_base,
                debug_step=debug_step,
                channel_url=channel_url,
                message=args.message,
                selectors=selectors,
                timeout=args.timeout,
                attach_timeout=args.attach_timeout,
                delay=args.delay,
            ):
                failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
