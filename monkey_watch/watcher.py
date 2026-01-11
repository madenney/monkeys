"""Watcher threads for monkey accounts."""

from __future__ import annotations

import json
import threading
import time
from queue import Empty, Queue
from typing import Any, Dict

from .commands import Command
from .config import WatchConfig
from .events import ChannelSwitchEvent, Event, SystemEvent, payload_to_event
from .selenium_utils import (
    attach_driver,
    debug_snapshot,
    drain_messages,
    select_discord_tab,
    wait_for_debugger,
    wait_for_injection,
)


def watch_account(
    acct: Dict[str, Any],
    idx: int,
    *,
    webdriver,
    WebDriverException,
    config: WatchConfig,
    channel_names: Dict[str, str],
    inject_script: str,
    debug_script: str,
    command_queue: "Queue[Command]",
    event_queue: "Queue[Event]",
    stop_event: threading.Event,
    print_lock: threading.Lock,
    account_id: str,
) -> None:
    acct_id = account_id
    port = config.debug_base + idx * config.debug_step
    address = f"127.0.0.1:{port}"

    with print_lock:
        print(f"{acct_id}: connecting to {address}", flush=True)

    attach_error = wait_for_debugger(address, config.attach_timeout)
    if attach_error:
        with print_lock:
            print(
                f"{acct_id}: debugger not reachable at {address} ({attach_error}). "
                "Launch with DEBUG_PORT_BASE set to enable remote debugging.",
                flush=True,
            )
        return

    try:
        driver = attach_driver(webdriver, address)
    except WebDriverException as exc:
        with print_lock:
            print(f"{acct_id}: failed to connect to {address} ({exc})", flush=True)
        return

    try:
        if not select_discord_tab(driver, config.url):
            with print_lock:
                print(f"{acct_id}: failed to open a Discord tab", flush=True)
            return

        if config.default_channel.is_set():
            target_url = (
                f"https://discord.com/channels/"
                f"{config.default_channel.guild_id}/{config.default_channel.channel_id}"
            )
            try:
                current_url = driver.current_url or ""
            except Exception:
                current_url = ""
            if target_url not in current_url:
                try:
                    driver.get(target_url)
                except Exception:
                    pass

        try:
            driver.execute_script(
                "window.__monkeyMessageVerbose = arguments[0];"
                "window.__monkeyDispatcherScanEnabled = arguments[0];",
                bool(config.debug),
            )
        except Exception:
            pass

        ok, status = wait_for_injection(driver, inject_script, config.inject_timeout)
        if not ok:
            with print_lock:
                print(f"{acct_id}: failed to attach listener ({status})", flush=True)
            return

        if config.debug:
            with print_lock:
                print(f"{acct_id}: listening for messages ({status})", flush=True)

        if config.default_channel.is_set():
            event_queue.put(
                ChannelSwitchEvent(
                    account_id=acct_id,
                    channel_id=config.default_channel.channel_id,
                    channel_name=config.default_channel.label,
                )
            )

        last_debug = 0.0
        if config.debug:
            info = debug_snapshot(driver, debug_script)
            with print_lock:
                print(f"{acct_id}: debug {json.dumps(info, sort_keys=True)}", flush=True)
            last_debug = time.monotonic()

        while not stop_event.is_set():
            while True:
                try:
                    command = command_queue.get_nowait()
                except Empty:
                    break
                _handle_command(
                    command,
                    driver,
                    acct_id,
                    event_queue,
                    config,
                    inject_script,
                )
            messages = drain_messages(driver)
            for payload in messages:
                event_queue.put(payload_to_event(acct_id, payload, channel_names))
            if config.debug and config.debug_interval > 0:
                now = time.monotonic()
                if now - last_debug >= config.debug_interval:
                    info = debug_snapshot(driver, debug_script)
                    with print_lock:
                        print(
                            f"{acct_id}: debug {json.dumps(info, sort_keys=True)}",
                            flush=True,
                        )
                    last_debug = now
            time.sleep(config.poll_interval)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _handle_command(
    command: Command,
    driver,
    acct_id: str,
    event_queue: "Queue[Event]",
    config: WatchConfig,
    inject_script: str,
) -> None:
    if command.action == "goto":
        if not command.guild_id or not command.channel_id:
            event_queue.put(
                SystemEvent(
                    account_id=acct_id,
                    content=f"[cmd] {acct_id}: missing channel id for goto",
                    important=True,
                )
            )
            return
        url = f"https://discord.com/channels/{command.guild_id}/{command.channel_id}"
        try:
            driver.get(url)
            _apply_debug_flags(driver, config)
            ok, status = _apply_injection(driver, inject_script, config.inject_timeout)
            if not ok:
                event_queue.put(
                    SystemEvent(
                        account_id=acct_id,
                        content=f"[cmd] {acct_id}: goto inject failed ({status})",
                        important=True,
                    )
                )
                return
            verified, current_path = _verify_channel(
                driver,
                command.guild_id,
                command.channel_id,
                timeout=config.attach_timeout,
                interval=max(0.1, config.poll_interval),
            )
            if verified:
                event_queue.put(
                    ChannelSwitchEvent(
                        account_id=acct_id,
                        channel_id=command.channel_id,
                        channel_name=command.channel_name,
                    )
                )
            else:
                suffix = f" (current path: {current_path})" if current_path else ""
                event_queue.put(
                    SystemEvent(
                        account_id=acct_id,
                        content=(
                            f"[cmd] {acct_id}: goto not confirmed for "
                            f"{command.guild_id}/{command.channel_id}{suffix}"
                        ),
                        important=True,
                    )
                )
        except Exception as exc:
            event_queue.put(
                SystemEvent(
                    account_id=acct_id,
                    content=f"[cmd] {acct_id}: goto failed ({exc})",
                    important=True,
                )
            )
        return

    if command.action == "say":
        message = command.text
        if not message:
            return
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            box, error = _wait_for_textbox(driver, By, timeout=config.attach_timeout)
            if not box:
                event_queue.put(
                    SystemEvent(
                        account_id=acct_id,
                        content=f"[cmd] {acct_id}: say failed ({error})",
                        important=True,
                    )
                )
                return
            box.click()
            box.send_keys(message)
            box.send_keys(Keys.ENTER)
        except Exception as exc:
            event_queue.put(
                SystemEvent(
                    account_id=acct_id,
                    content=f"[cmd] {acct_id}: say failed ({exc})",
                    important=True,
                )
            )
        return

    event_queue.put(
        SystemEvent(
            account_id=acct_id,
            content=f"[cmd] {acct_id}: unknown command {command.action}",
            important=True,
        )
    )


def _apply_debug_flags(driver, config: WatchConfig) -> None:
    try:
        driver.execute_script(
            "window.__monkeyMessageVerbose = arguments[0];"
            "window.__monkeyDispatcherScanEnabled = arguments[0];",
            bool(config.debug),
        )
    except Exception:
        pass


def _apply_injection(driver, inject_script: str, timeout: float) -> tuple[bool, str]:
    return wait_for_injection(driver, inject_script, timeout)


def _get_path(driver) -> str:
    try:
        path = driver.execute_script("return location.pathname || ''")
        if isinstance(path, str):
            return path
    except Exception:
        pass
    try:
        url = driver.current_url or ""
    except Exception:
        return ""
    if "://" in url:
        _, rest = url.split("://", 1)
        if "/" in rest:
            return "/" + rest.split("/", 1)[1]
    return ""


def _get_channel_key(driver) -> str:
    try:
        value = driver.execute_script(
            "return (window.__monkeyMessageWatcher && "
            "window.__monkeyMessageWatcher.channelKey) || '';"
        )
    except Exception:
        return ""
    if isinstance(value, str):
        return value
    return ""


def _verify_channel(
    driver,
    guild_id: str,
    channel_id: str,
    *,
    timeout: float,
    interval: float,
) -> tuple[bool, str]:
    target_prefix = f"/channels/{guild_id}/{channel_id}"
    target_key = f"{guild_id}:{channel_id}"
    deadline = time.monotonic() + max(0.5, timeout)
    stable_hits = 0
    last_path = ""
    while time.monotonic() < deadline:
        path = _get_path(driver)
        if path:
            last_path = path
        channel_key = _get_channel_key(driver)
        if (path and path.startswith(target_prefix)) or (
            channel_key and channel_key == target_key
        ):
            stable_hits += 1
            if stable_hits >= 2:
                return True, last_path
        else:
            stable_hits = 0
        time.sleep(max(0.05, interval))
    return False, last_path


def _wait_for_textbox(driver, By, *, timeout: float, interval: float = 0.2):
    deadline = time.monotonic() + max(0.5, timeout)
    last_error = ""
    selector = "div[role='textbox'][contenteditable='true']"
    while time.monotonic() < deadline:
        try:
            boxes = driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(interval)
            continue
        for box in boxes:
            try:
                if box.is_displayed():
                    return box, ""
            except Exception:
                continue
        time.sleep(interval)
    return None, last_error or "no visible textbox found"
