"""Configuration helpers for monkey message watching."""

from __future__ import annotations

import json
import os
import re

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_DEBUG_BASE = 9222
DEFAULT_ATTACH_TIMEOUT = 6.0
DEFAULT_INJECT_TIMEOUT = 30.0
DEFAULT_POLL_INTERVAL = 0.6
DEFAULT_STARTUP_DELAY = 2.0
DEFAULT_DEBUG_INTERVAL = 5.0
DEFAULT_SNAPSHOT_LIMIT = 10
DEFAULT_URL = "https://discord.com/app"
DEFAULT_MAX_QUEUE_SIZE = 500
DEFAULT_GLOBAL_DEDUPE_LIMIT = 5000
DEFAULT_SERVER_NAME = "Home Tree"
DEFAULT_CHANNEL_NAME = "test-jungle"
DEFAULT_CONTROL_PORT = 7331
DEFAULT_ADMIN_USER = ""

_ENV_PATTERN = re.compile(r"\$(?:\{([A-Z0-9_]+)\}|([A-Z0-9_]+))")


@dataclass(frozen=True)
class DefaultChannel:
    guild_id: str
    channel_id: str
    label: str

    def is_set(self) -> bool:
        return bool(self.guild_id and self.channel_id)


@dataclass(frozen=True)
class WatchConfig:
    accounts_path: Path
    servers_path: Path
    count: Optional[int]
    debug_base: int
    debug_step: int
    url: str
    attach_timeout: float
    inject_timeout: float
    poll_interval: float
    startup_delay: float
    debug: bool
    debug_interval: float
    snapshot_limit: int
    max_queue_size: int
    global_dedupe_limit: int
    default_channel: DefaultChannel
    control_port: int
    admin_user_ids: Tuple[str, ...]


def parse_env_int(value: Optional[str], *, name: str) -> Optional[int]:
    if value is None or value == "":
        return None
    if not value.isdigit():
        raise ValueError(f"{name} must be an integer")
    return int(value)


def parse_env_str(value: Optional[str]) -> str:
    if value is None:
        return ""
    return value.strip()


def load_dotenv(path: Optional[Path] = None, *, override: bool = False) -> None:
    env_path = path or Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    try:
        raw = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ("'", '"')
        ):
            value = value[1:-1]
        if not override and key in os.environ:
            continue
        os.environ[key] = value


def _expand_env_value(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1) or match.group(2)
        return os.environ.get(key, "")

    return _ENV_PATTERN.sub(replace, value)


def expand_env_values(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_env_value(value)
    if isinstance(value, list):
        return [expand_env_values(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env_values(item) for key, item in value.items()}
    return value


def load_accounts(path: Path) -> List[Dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"accounts file not found: {path}") from None
    except OSError as exc:
        raise OSError(f"failed to read accounts file: {path} ({exc})") from exc

    try:
        data = raw and json.loads(raw)
    except Exception as exc:  # pragma: no cover - caught by caller
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc

    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        raise ValueError(f"missing or invalid 'accounts' list in {path}")
    return accounts


def load_servers(path: Path) -> List[Dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        return []

    try:
        data = raw and json.loads(raw)
    except Exception:
        return []

    if not isinstance(data, list):
        return []
    data = expand_env_values(data)
    return [item for item in data if isinstance(item, dict)]


def load_channel_names(servers: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    channel_names: Dict[str, str] = {}
    for server in servers:
        channels = server.get("channels")
        if not isinstance(channels, list):
            continue
        for channel in channels:
            channel_id = str(channel.get("id", "")).strip()
            channel_name = str(channel.get("name", "")).strip()
            if channel_id and channel_name:
                channel_names[channel_id] = channel_name
    return channel_names


def normalize_name(value: str) -> str:
    return value.strip().casefold()


def resolve_default_channel(
    servers: List[Dict[str, Any]],
    channel_names: Dict[str, str],
    *,
    default_guild_id: str,
    default_channel_id: str,
    default_server_name: str,
    default_channel_name: str,
) -> DefaultChannel:
    guild_id = default_guild_id.strip()
    channel_id = default_channel_id.strip()
    server_name = default_server_name.strip()
    channel_name = default_channel_name.strip()

    if guild_id and channel_id:
        label = channel_names.get(channel_id, "") or channel_name or channel_id
        return DefaultChannel(guild_id=guild_id, channel_id=channel_id, label=label)

    server = None
    if guild_id:
        for entry in servers:
            if str(entry.get("server_id", "")).strip() == guild_id:
                server = entry
                break
            if str(entry.get("id", "")).strip() == guild_id:
                server = entry
                break
    elif server_name:
        target = normalize_name(server_name)
        for entry in servers:
            if normalize_name(str(entry.get("name", ""))) == target:
                server = entry
                break

    if server:
        if not guild_id:
            guild_id = str(server.get("server_id", "") or server.get("id", "")).strip()
        if not channel_id and channel_name:
            target_channel = normalize_name(channel_name)
            channels = server.get("channels")
            if isinstance(channels, list):
                for channel in channels:
                    if normalize_name(str(channel.get("name", ""))) == target_channel:
                        channel_id = str(channel.get("id", "")).strip()
                        break

    if guild_id and channel_id:
        label = channel_names.get(channel_id, "") or channel_name or channel_id
        return DefaultChannel(guild_id=guild_id, channel_id=channel_id, label=label)

    return DefaultChannel(guild_id="", channel_id="", label="")
