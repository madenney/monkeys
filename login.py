#!/usr/bin/env python3
"""Populate Discord login email fields for monkey accounts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from monkey_watch.config import load_dotenv
DEFAULT_DEBUG_BASE = 9222


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


def find_email_input(driver, selectors: List[Tuple[str, str]], timeout: float):
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


def fill_email(driver, email: str, url: str, selectors: List[Tuple[str, str]], timeout: float) -> str:
    try:
        driver.get(url)
    except Exception:
        return "navigation_failed"

    field = find_email_input(driver, selectors, timeout)
    if field is None:
        return "no_login_form"

    try:
        current = field.get_attribute("value") or ""
        if current.strip() != email:
            field.clear()
            field.send_keys(email)
    except Exception:
        return "fill_failed"

    return "filled"


def attach_driver(webdriver, debugger_address: str):
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", debugger_address)
    return webdriver.Chrome(options=options)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate Discord login email fields for monkey accounts."
    )
    parser.add_argument(
        "--accounts",
        type=Path,
        default=Path(__file__).resolve().parent / "accounts.json",
        help="Path to accounts.json (copy from accounts_template.json).",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        help="Only handle the first COUNT monkey accounts.",
    )
    parser.add_argument(
        "--debug-base",
        type=int,
        help="Remote debugging base port (matches DEBUG_PORT_BASE). Defaults to 9222.",
    )
    parser.add_argument(
        "--debug-step",
        type=int,
        help="Remote debugging port step (matches DEBUG_PORT_STEP).",
    )
    parser.add_argument(
        "--url",
        default="https://discord.com/login",
        help="Login URL to open before filling email.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Seconds to wait for the email field.",
    )

    args = parser.parse_args()
    load_dotenv()

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
    print(f"Found {len(monkeys)} monkey account(s).")

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
    print(f"Using debug base {debug_base} with step {debug_step}.")
    print(f"Login URL: {args.url} (timeout {args.timeout:.1f}s).")

    selectors = [
        (By.NAME, "email"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[autocomplete='email']"),
        (By.CSS_SELECTOR, "input[placeholder*='Email']"),
        (By.CSS_SELECTOR, "input[aria-label*='Email']"),
    ]

    failures = 0

    for idx, acct in enumerate(monkeys):
        acct_id = str(acct.get("id", "-"))
        email = str(acct.get("gmail", {}).get("email", ""))
        if not email:
            print(f"{acct_id}: missing gmail.email")
            failures += 1
            continue

        port = debug_base + idx * debug_step
        address = f"127.0.0.1:{port}"

        print(f"{acct_id}: connecting to {address}")
        try:
            driver = attach_driver(webdriver, address)
        except WebDriverException as exc:
            print(f"{acct_id}: failed to connect to {address} ({exc})")
            failures += 1
            continue

        print(f"{acct_id}: opening {args.url} and waiting for login form")
        try:
            result = fill_email(driver, email, args.url, selectors, args.timeout)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        if result == "filled":
            print(f"{acct_id}: email filled")
        elif result == "no_login_form":
            print(f"{acct_id}: no login form detected (maybe already logged in)")
        elif result == "navigation_failed":
            print(f"{acct_id}: failed to open login page")
            failures += 1
        else:
            print(f"{acct_id}: failed to fill email")
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
