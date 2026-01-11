"""Event models and formatting."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Set, Union


@dataclass(frozen=True)
class MessageEvent:
    account_id: str
    message_id: str
    channel_id: str
    channel_name: str
    guild_id: str
    author_name: str
    author_id: str
    content: str
    timestamp: str
    source: str
    system: bool = False
    raw: Optional[Dict[str, Any]] = None

    @property
    def kind(self) -> str:
        return "message"


@dataclass(frozen=True)
class SystemEvent:
    account_id: str
    content: str
    important: bool = False

    @property
    def kind(self) -> str:
        return "system"


@dataclass(frozen=True)
class ChannelSwitchEvent:
    account_id: str
    channel_id: str
    channel_name: str

    @property
    def kind(self) -> str:
        return "channel-switch"


Event = Union[MessageEvent, SystemEvent, ChannelSwitchEvent]


class GlobalDedupe:
    def __init__(self, limit: int) -> None:
        self._limit = max(0, limit)
        self._ids: Set[str] = set()
        self._order: Deque[str] = deque()

    def allow(self, message_id: str) -> bool:
        if not message_id:
            return True
        if message_id in self._ids:
            return False
        self._ids.add(message_id)
        self._order.append(message_id)
        if self._limit > 0:
            while len(self._order) > self._limit:
                oldest = self._order.popleft()
                self._ids.discard(oldest)
        return True


def resolve_channel_label(
    payload: Dict[str, Any],
    channel_names: Dict[str, str],
    *,
    fallback_id: bool = False,
) -> str:
    channel_name = str(payload.get("channel_name", "") or "")
    channel_id = str(payload.get("channel_id", "") or "")
    if not channel_name and channel_id:
        channel_name = channel_names.get(channel_id, "")
    if channel_name:
        return channel_name
    if fallback_id and channel_id:
        return channel_id
    return "unknown-channel"


def payload_to_event(
    account_id: str,
    payload: Dict[str, Any],
    channel_names: Dict[str, str],
) -> Event:
    if payload.get("system"):
        return SystemEvent(account_id=account_id, content=str(payload.get("content", "") or ""))
    content = str(payload.get("content", "") or "")
    author_name = str(payload.get("author", "") or "")
    author_id = str(payload.get("author_id", "") or "")
    channel_id = str(payload.get("channel_id", "") or "")
    channel_name = resolve_channel_label(payload, channel_names)
    return MessageEvent(
        account_id=account_id,
        message_id=str(payload.get("id", "") or ""),
        channel_id=channel_id,
        channel_name=channel_name,
        guild_id=str(payload.get("guild_id", "") or ""),
        author_name=author_name,
        author_id=author_id,
        content=content,
        timestamp=str(payload.get("timestamp", "") or ""),
        source=str(payload.get("source", "") or ""),
        system=False,
        raw=payload,
    )


def format_message(event: MessageEvent) -> str:
    content = event.content or "<no text>"
    content = content.replace("\n", "\\n")
    channel_label = event.channel_name or event.channel_id or "unknown-channel"
    author_label = event.author_name or event.author_id or "unknown-user"
    return f"{channel_label} {author_label}: {content}"


def format_channel_switch(event: ChannelSwitchEvent) -> str:
    channel_label = event.channel_name or event.channel_id or "unknown-channel"
    return f"{event.account_id} watching: {channel_label}"


def format_system(event: SystemEvent) -> str:
    return event.content


def format_event(event: Event) -> str:
    if isinstance(event, MessageEvent):
        return format_message(event)
    if isinstance(event, ChannelSwitchEvent):
        return format_channel_switch(event)
    return format_system(event)
