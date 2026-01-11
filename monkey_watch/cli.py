"""CLI entrypoint for monkey message watching."""

from __future__ import annotations

import argparse
import os
import queue
import threading
import time
from pathlib import Path
from typing import Dict, List

from .commands import (
    ChannelIndex,
    Command,
    build_channel_index,
    build_help,
    format_servers,
    parse_command_line,
    resolve_goto_argument,
)
from .config import (
    DEFAULT_ATTACH_TIMEOUT,
    DEFAULT_ADMIN_USER,
    DEFAULT_DEBUG_BASE,
    DEFAULT_DEBUG_INTERVAL,
    DEFAULT_GLOBAL_DEDUPE_LIMIT,
    DEFAULT_INJECT_TIMEOUT,
    DEFAULT_MAX_QUEUE_SIZE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_CONTROL_PORT,
    DEFAULT_SERVER_NAME,
    DEFAULT_CHANNEL_NAME,
    DEFAULT_SNAPSHOT_LIMIT,
    DEFAULT_STARTUP_DELAY,
    DEFAULT_URL,
    WatchConfig,
    load_dotenv,
    load_accounts,
    load_channel_names,
    load_servers,
    parse_env_int,
    parse_env_str,
    resolve_default_channel,
)
from .events import (
    ChannelSwitchEvent,
    Event,
    GlobalDedupe,
    MessageEvent,
    SystemEvent,
    format_event,
)
from .inject import load_debug_script, load_inject_script
from .watcher import watch_account
from .control import CommandDispatcher, start_control_server, start_stdin_listener


def is_monkey(acct: Dict[str, object]) -> bool:
    acct_id = str(acct.get("id", ""))
    return acct_id.startswith("monkey-") or acct_id == "monkey"


def pick_monkeys(accounts: List[Dict[str, object]], limit: int | None) -> List[Dict[str, object]]:
    monkeys = [acct for acct in accounts if is_monkey(acct)]
    if limit is None:
        return monkeys
    if limit < 0:
        return []
    return monkeys[:limit]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch Discord messages from monkey accounts using remote debugging."
    )
    parser.add_argument(
        "--accounts",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "accounts.json",
        help="Path to accounts.json (copy from accounts_template.json).",
    )
    parser.add_argument(
        "--servers",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "servers.json",
        help="Path to servers.json (supports ${VARS} from .env).",
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
        default=DEFAULT_URL,
        help=f"Discord URL to open if no tab is active (default: {DEFAULT_URL}).",
    )
    parser.add_argument(
        "--attach-timeout",
        type=float,
        default=DEFAULT_ATTACH_TIMEOUT,
        help="Seconds to wait for the debugger port.",
    )
    parser.add_argument(
        "--inject-timeout",
        type=float,
        default=DEFAULT_INJECT_TIMEOUT,
        help="Seconds to wait for the Discord app to load before injecting.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Seconds between message queue polls.",
    )
    parser.add_argument(
        "--startup-delay",
        type=float,
        default=DEFAULT_STARTUP_DELAY,
        help="Seconds to wait before attaching (after launching windows).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print periodic debug info from the Discord tab.",
    )
    parser.add_argument(
        "--debug-interval",
        type=float,
        default=DEFAULT_DEBUG_INTERVAL,
        help="Seconds between debug snapshots (debug mode only).",
    )
    return parser.parse_args()


def handle_event(
    event: Event,
    *,
    debug: bool,
    dedupe: GlobalDedupe,
    admin_user_ids: List[str],
    dispatch_command,
    last_channel_by_account: Dict[str, str],
    print_lock: threading.Lock,
) -> None:
    if isinstance(event, SystemEvent):
        if not (debug or event.important):
            return
        with print_lock:
            print(format_event(event), flush=True)
        return

    if isinstance(event, ChannelSwitchEvent):
        channel_label = event.channel_name or event.channel_id
        if channel_label:
            last_channel_by_account[event.account_id] = event.channel_id or channel_label
            with print_lock:
                print(format_event(event), flush=True)
        return

    if isinstance(event, MessageEvent):
        is_new = dedupe.allow(event.message_id)
        if is_new and event.author_id and event.author_id in admin_user_ids:
            raw = (event.content or "").strip()
            prefix = "monkeys"
            if raw.casefold().startswith(prefix):
                remainder = raw[len(prefix):].lstrip()
                if remainder.startswith(":"):
                    remainder = remainder[1:].lstrip()
                if remainder:
                    response = dispatch_command(remainder, f"discord:{event.author_id}")
                    if response not in ("", "ok"):
                        with print_lock:
                            print(response, flush=True)

        channel_key = event.channel_id or event.channel_name
        if channel_key and last_channel_by_account.get(event.account_id) != channel_key:
            last_channel_by_account[event.account_id] = channel_key
            channel_label = event.channel_name or event.channel_id
            if channel_label:
                switch_event = ChannelSwitchEvent(
                    account_id=event.account_id,
                    channel_id=event.channel_id,
                    channel_name=event.channel_name,
                )
                with print_lock:
                    print(format_event(switch_event), flush=True)

        if not is_new:
            return
        with print_lock:
            print(format_event(event), flush=True)


def main() -> int:
    args = parse_args()
    load_dotenv()

    try:
        from selenium import webdriver
    except ImportError:
        print("selenium is required. Install it with 'pip install selenium'.")
        return 2

    try:
        from selenium.common.exceptions import WebDriverException
    except ImportError:
        print("selenium is required. Install it with 'pip install selenium'.")
        return 2

    try:
        accounts = load_accounts(args.accounts)
    except Exception as exc:
        print(str(exc))
        return 2

    monkeys = pick_monkeys(accounts, args.count)
    if not monkeys:
        print("No monkey accounts found.")
        return 0
    print(f"Found {len(monkeys)} monkey account(s).")

    servers = load_servers(args.servers)
    channel_names = load_channel_names(servers)

    try:
        env_base = parse_env_int(os.environ.get("DEBUG_PORT_BASE"), name="DEBUG_PORT_BASE")
        env_step = parse_env_int(os.environ.get("DEBUG_PORT_STEP"), name="DEBUG_PORT_STEP")
    except ValueError as exc:
        print(str(exc))
        return 2

    debug_base = args.debug_base if args.debug_base is not None else env_base
    debug_step = args.debug_step if args.debug_step is not None else (env_step or 1)
    if debug_base is None:
        debug_base = DEFAULT_DEBUG_BASE
    if debug_step < 1:
        print("debug step must be >= 1")
        return 2
    if args.debug_interval <= 0:
        print("debug interval must be > 0")
        return 2

    default_guild_id = parse_env_str(os.environ.get("MONKEY_DEFAULT_GUILD_ID"))
    default_channel_id = parse_env_str(os.environ.get("MONKEY_DEFAULT_CHANNEL_ID"))
    default_server_name = parse_env_str(os.environ.get("MONKEY_DEFAULT_SERVER_NAME"))
    default_channel_name = parse_env_str(os.environ.get("MONKEY_DEFAULT_CHANNEL_NAME"))
    if not (default_guild_id or default_channel_id or default_server_name or default_channel_name):
        default_server_name = DEFAULT_SERVER_NAME
        default_channel_name = DEFAULT_CHANNEL_NAME

    default_channel = resolve_default_channel(
        servers,
        channel_names,
        default_guild_id=default_guild_id,
        default_channel_id=default_channel_id,
        default_server_name=default_server_name,
        default_channel_name=default_channel_name,
    )
    if default_channel.is_set():
        print(
            f"Default channel: {default_channel.label} "
            f"({default_channel.guild_id}/{default_channel.channel_id})"
        )

    admin_user_raw = parse_env_str(
        os.environ.get("admin_user") or os.environ.get("ADMIN_USER")
    )
    if not admin_user_raw:
        admin_user_raw = DEFAULT_ADMIN_USER
    admin_user_ids = [item for item in admin_user_raw.replace(",", " ").split() if item]

    try:
        control_port = parse_env_int(
            os.environ.get("MONKEY_CONTROL_PORT"), name="MONKEY_CONTROL_PORT"
        )
    except ValueError as exc:
        print(str(exc))
        return 2
    if control_port is None:
        control_port = DEFAULT_CONTROL_PORT

    config = WatchConfig(
        accounts_path=args.accounts,
        servers_path=args.servers,
        count=args.count,
        debug_base=debug_base,
        debug_step=debug_step,
        url=args.url,
        attach_timeout=args.attach_timeout,
        inject_timeout=args.inject_timeout,
        poll_interval=args.poll_interval,
        startup_delay=args.startup_delay,
        debug=args.debug,
        debug_interval=args.debug_interval,
        snapshot_limit=DEFAULT_SNAPSHOT_LIMIT,
        max_queue_size=DEFAULT_MAX_QUEUE_SIZE,
        global_dedupe_limit=DEFAULT_GLOBAL_DEDUPE_LIMIT,
        default_channel=default_channel,
        control_port=control_port,
        admin_user_ids=tuple(admin_user_ids),
    )

    if config.debug:
        print(f"Using debug base {config.debug_base} with step {config.debug_step}.")
        print(f"Discord URL: {config.url}")
    if config.startup_delay > 0:
        print(f"Waiting {config.startup_delay:.1f}s before attaching...")
        time.sleep(config.startup_delay)

    inject_script = load_inject_script(config.snapshot_limit, config.max_queue_size)
    debug_script = load_debug_script()

    stop_event = threading.Event()
    print_lock = threading.Lock()
    event_queue: "queue.Queue[Event]" = queue.Queue()
    threads: List[threading.Thread] = []

    monkey_ids: List[str] = []
    for idx, acct in enumerate(monkeys):
        acct_id = str(acct.get("id", "")).strip() or f"monkey-{idx + 1}"
        monkey_ids.append(acct_id)
    command_queues: Dict[str, "queue.Queue[Command]"] = {
        monkey_id: queue.Queue() for monkey_id in monkey_ids
    }
    channel_index = build_channel_index(servers)

    def dispatch_command_line(line: str, source: str) -> str:
        command, error = parse_command_line(line, monkey_ids)
        if error:
            return error
        if command is None:
            return ""
        if command.action == "help":
            return build_help()
        if command.action == "servers":
            return format_servers(channel_index)

        targets = []
        if command.target is None:
            targets = monkey_ids
        elif command.target in command_queues:
            targets = [command.target]
        else:
            return f"unknown monkey: {command.target}"

        if command.action == "goto":
            ref, error = resolve_goto_argument(command.text, channel_index)
            if error:
                return error
            if not ref:
                return "unable to resolve channel"
            resolved = Command(
                target=command.target,
                action="goto",
                text=command.text,
                guild_id=ref.guild_id,
                channel_id=ref.channel_id,
                channel_name=ref.channel_name,
                source=source,
            )
            for target in targets:
                command_queues[target].put(resolved)
            return "ok"

        if command.action == "home":
            if not config.default_channel.is_set():
                return "default channel not configured"
            resolved = Command(
                target=command.target,
                action="goto",
                text="home",
                guild_id=config.default_channel.guild_id,
                channel_id=config.default_channel.channel_id,
                channel_name=config.default_channel.label,
                source=source,
            )
            for target in targets:
                command_queues[target].put(resolved)
            return "ok"

        if command.action == "say":
            resolved = Command(
                target=command.target,
                action="say",
                text=command.text,
                source=source,
            )
            for target in targets:
                command_queues[target].put(resolved)
            return "ok"

        return f"unhandled command: {command.action}"

    dispatcher = CommandDispatcher(dispatch_command_line, print_lock)
    start_stdin_listener(dispatcher, stop_event)
    try:
        start_control_server(dispatcher, "127.0.0.1", config.control_port, stop_event)
    except OSError as exc:
        if config.debug:
            print(f"control server failed to start: {exc}")

    for idx, acct in enumerate(monkeys):
        acct_id = str(acct.get("id", "")).strip() or f"monkey-{idx + 1}"
        if acct_id not in command_queues:
            command_queues[acct_id] = queue.Queue()
        thread = threading.Thread(
            target=watch_account,
            args=(acct, idx),
            kwargs={
                "webdriver": webdriver,
                "WebDriverException": WebDriverException,
                "config": config,
                "channel_names": channel_names,
                "inject_script": inject_script,
                "debug_script": debug_script,
                "command_queue": command_queues[acct_id],
                "event_queue": event_queue,
                "stop_event": stop_event,
                "print_lock": print_lock,
                "account_id": acct_id,
            },
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    dedupe = GlobalDedupe(config.global_dedupe_limit)
    last_channel_by_account: Dict[str, str] = {}

    try:
        while True:
            alive = any(thread.is_alive() for thread in threads)
            try:
                event = event_queue.get(timeout=0.5)
            except queue.Empty:
                if not alive:
                    break
                continue
            handle_event(
                event,
                debug=config.debug,
                dedupe=dedupe,
                admin_user_ids=admin_user_ids,
                dispatch_command=dispatch_command_line,
                last_channel_by_account=last_channel_by_account,
                print_lock=print_lock,
            )
    except KeyboardInterrupt:
        with print_lock:
            print("Stopping message watchers...", flush=True)
        stop_event.set()
    finally:
        for thread in threads:
            thread.join(timeout=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
