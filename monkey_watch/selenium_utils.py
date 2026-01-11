"""Selenium helpers for monkey message watching."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple


def wait_for_debugger(address: str, timeout: float) -> Optional[str]:
    import urllib.error
    import urllib.request

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


def attach_driver(webdriver, debugger_address: str):
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", debugger_address)
    return webdriver.Chrome(options=options)


def select_discord_tab(driver, url: str) -> bool:
    try:
        handles = driver.window_handles
    except Exception:
        handles = []

    for handle in handles:
        try:
            driver.switch_to.window(handle)
            current = driver.current_url or ""
        except Exception:
            continue
        if "discord.com" in current:
            return True

    try:
        driver.get(url)
        return True
    except Exception:
        return False


def wait_for_injection(driver, inject_script: str, timeout: float) -> Tuple[bool, str]:
    deadline = time.monotonic() + timeout
    last_error = "unknown"
    while time.monotonic() < deadline:
        try:
            result = driver.execute_script(inject_script)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.5)
            continue
        if isinstance(result, dict):
            if result.get("ok"):
                return True, str(result.get("status", "attached"))
            error = str(result.get("error", last_error))
            diag = result.get("diag")
            if diag:
                error = f"{error} diag={json.dumps(diag, sort_keys=True)}"
            last_error = error
        else:
            last_error = str(result)
        time.sleep(0.5)
    return False, last_error


def debug_snapshot(driver, debug_script: str) -> Dict[str, Any]:
    try:
        result = driver.execute_script(debug_script)
    except Exception as exc:
        return {"error": str(exc)}
    if isinstance(result, dict):
        return result
    return {"value": str(result)}


def drain_messages(driver) -> List[Dict[str, Any]]:
    try:
        result = driver.execute_script(
            "return (window.__monkeyMessageQueue || []).splice(0);"
        )
    except Exception:
        return []
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []
