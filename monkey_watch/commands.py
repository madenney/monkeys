"""Command parsing and dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class ChannelRef:
    guild_id: str
    channel_id: str
    channel_name: str
    server_name: str
    server_index: int = 0
    channel_index: int = 0

    def label(self) -> str:
        return self.channel_name or self.channel_id


@dataclass(frozen=True)
class ServerRef:
    server_index: int
    guild_id: str
    server_name: str
    channels: List[ChannelRef]


@dataclass(frozen=True)
class ChannelIndex:
    by_id: Dict[str, ChannelRef]
    by_name: Dict[str, List[ChannelRef]]
    servers: List[ServerRef]


@dataclass(frozen=True)
class Command:
    target: Optional[str]
    action: str
    text: str
    guild_id: str = ""
    channel_id: str = ""
    channel_name: str = ""
    source: str = ""


def build_channel_index(servers: Iterable[Dict[str, object]]) -> ChannelIndex:
    by_id: Dict[str, ChannelRef] = {}
    by_name: Dict[str, List[ChannelRef]] = {}
    server_refs: List[ServerRef] = []
    for server_idx, server in enumerate(servers, start=1):
        channels = server.get("channels")
        server_name = str(server.get("name", "") or "")
        guild_id = str(server.get("server_id", "") or server.get("id", "") or "")
        channel_refs: List[ChannelRef] = []
        if isinstance(channels, list):
            for channel_idx, channel in enumerate(channels, start=1):
                channel_id = str(channel.get("id", "") or "")
                channel_name = str(channel.get("name", "") or "")
                if not channel_id:
                    continue
                ref = ChannelRef(
                    guild_id=guild_id.strip(),
                    channel_id=channel_id.strip(),
                    channel_name=channel_name.strip(),
                    server_name=server_name.strip(),
                    server_index=server_idx,
                    channel_index=channel_idx,
                )
                channel_refs.append(ref)
                by_id[ref.channel_id] = ref
                if ref.channel_name:
                    key = ref.channel_name.casefold()
                    by_name.setdefault(key, []).append(ref)
        server_refs.append(
            ServerRef(
                server_index=server_idx,
                guild_id=guild_id.strip(),
                server_name=server_name.strip(),
                channels=channel_refs,
            )
        )
    return ChannelIndex(by_id=by_id, by_name=by_name, servers=server_refs)


def _normalize_name(value: str) -> str:
    return value.strip().casefold()


def parse_command_line(
    line: str,
    monkey_ids: Iterable[str],
) -> Tuple[Optional[Command], Optional[str]]:
    cleaned = line.strip()
    if not cleaned:
        return None, None
    tokens = cleaned.split()
    if not tokens:
        return None, None

    target = None
    first = tokens[0]
    if first.startswith("@"):
        candidate = first[1:].strip().rstrip(":,")
        if candidate in ("all", "*"):
            target = None
        else:
            target = candidate
        tokens = tokens[1:]

    if not tokens:
        return None, "missing command (try: goto <channel> or say <text>)"

    action = tokens[0].lower()
    rest = " ".join(tokens[1:]).strip()

    if action == "go":
        if rest.lower() == "home":
            return Command(target=target, action="home", text=""), None
        return None, "unknown command: go"

    if action in ("help", "?"):
        return Command(target=target, action="help", text=""), None

    if action in ("servers", "server", "list"):
        return Command(target=target, action="servers", text=""), None

    if action == "home":
        return Command(target=target, action="home", text=""), None

    if action not in ("goto", "say"):
        return None, f"unknown command: {action}"

    if action == "goto" and not rest:
        return None, "goto requires a channel name or id"
    if action == "say" and not rest:
        return None, "say requires message text"

    return Command(target=target, action=action, text=rest), None


def resolve_goto_argument(
    argument: str,
    channel_index: ChannelIndex,
) -> Tuple[Optional[ChannelRef], Optional[str]]:
    cleaned = argument.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        cleaned = cleaned[1:-1].strip()
    if not cleaned:
        return None, "missing channel"

    if ":" in cleaned:
        left, right = (part.strip() for part in cleaned.split(":", 1))
        if not left or not right:
            return None, "expected server:channel or server_index:channel_index"
        if left.isdigit():
            server_idx = int(left)
            if server_idx < 1 or server_idx > len(channel_index.servers):
                return None, f"unknown server index: {left}"
            server_ref = channel_index.servers[server_idx - 1]
            if right.isdigit():
                channel_idx = int(right)
                if channel_idx < 1 or channel_idx > len(server_ref.channels):
                    return None, f"unknown channel index: {left}:{right}"
                return server_ref.channels[channel_idx - 1], None
            target = _normalize_name(right)
            matches = [
                ref
                for ref in server_ref.channels
                if _normalize_name(ref.channel_name) == target
            ]
            if not matches:
                return None, f"unknown channel name: {right} (server {left})"
            if len(matches) == 1:
                return matches[0], None
            labels = [f"{left}:{ref.channel_index}" for ref in matches]
            return None, f"ambiguous channel name: {right} ({', '.join(labels)})"

        target_server = _normalize_name(left)
        server_matches = [
            ref
            for ref in channel_index.servers
            if _normalize_name(ref.server_name) == target_server
        ]
        if not server_matches:
            return None, f"unknown server name: {left}"
        if len(server_matches) > 1:
            labels = [f"{ref.server_index}:{ref.server_name}" for ref in server_matches]
            return None, f"ambiguous server name: {left} ({', '.join(labels)})"
        server_ref = server_matches[0]
        if right.isdigit():
            channel_idx = int(right)
            if channel_idx < 1 or channel_idx > len(server_ref.channels):
                return None, f"unknown channel index: {server_ref.server_index}:{right}"
            return server_ref.channels[channel_idx - 1], None
        target = _normalize_name(right)
        matches = [
            ref
            for ref in server_ref.channels
            if _normalize_name(ref.channel_name) == target
        ]
        if not matches:
            return None, f"unknown channel name: {right} (server {server_ref.server_name})"
        if len(matches) == 1:
            return matches[0], None
        labels = [f"{server_ref.server_index}:{ref.channel_index}" for ref in matches]
        return None, f"ambiguous channel name: {right} ({', '.join(labels)})"

    if "/" in cleaned:
        parts = [part for part in cleaned.split("/") if part]
        if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
            guild_id, channel_id = parts[0], parts[1]
            ref = channel_index.by_id.get(channel_id)
            if ref:
                return ChannelRef(
                    guild_id=guild_id,
                    channel_id=channel_id,
                    channel_name=ref.channel_name,
                    server_name=ref.server_name,
                    server_index=ref.server_index,
                    channel_index=ref.channel_index,
                ), None
            return ChannelRef(
                guild_id=guild_id,
                channel_id=channel_id,
                channel_name="",
                server_name="",
                server_index=0,
                channel_index=0,
            ), None
        return None, "expected channel as guild_id/channel_id"

    if cleaned.isdigit():
        ref = channel_index.by_id.get(cleaned)
        if ref:
            return ref, None
        return None, f"unknown channel id: {cleaned}"

    key = _normalize_name(cleaned)
    matches = channel_index.by_name.get(key, [])
    if not matches:
        return None, f"unknown channel name: {cleaned}"
    if len(matches) == 1:
        return matches[0], None

    labels = [f"{ref.server_index}:{ref.channel_index}" for ref in matches]
    return None, f"ambiguous channel name: {cleaned} ({', '.join(labels)})"


def build_help() -> str:
    return (
        "commands: [@monkey-id] goto <channel|server:channel|server_index:channel_index> "
        "| [@monkey-id] say <text> | go home | servers"
    )


def format_servers(channel_index: ChannelIndex) -> str:
    if not channel_index.servers:
        return "no servers loaded (servers.json missing or empty)"
    lines: List[str] = ["servers:"]
    for server in channel_index.servers:
        server_label = server.server_name or "unknown-server"
        server_line = f"{server.server_index}) {server_label}"
        if server.guild_id:
            server_line += f" (id={server.guild_id})"
        lines.append(server_line)
        if not server.channels:
            lines.append("  (no channels)")
            continue
        for channel in server.channels:
            channel_label = channel.channel_name or channel.channel_id or "unknown-channel"
            channel_line = f"  {channel.channel_index}) {channel_label}"
            if channel.channel_id:
                channel_line += f" (id={channel.channel_id})"
            lines.append(channel_line)
    lines.append("goto <server_index>:<channel_index> to jump quickly.")
    return "\n".join(lines)
