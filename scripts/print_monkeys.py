#!/usr/bin/env python3
"""Display monkey accounts from accounts.json."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


def format_kv(label: str, value: str, width: int) -> List[str]:
    if not value:
        value = "-"
    prefix = f"  {label:<8} "
    wrap_width = max(20, width - len(prefix))
    lines = []
    for i, chunk in enumerate(_wrap(value, wrap_width)):
        lines.append(f"{prefix if i == 0 else ' ' * len(prefix)}{chunk}")
    return lines


def _wrap(text: str, width: int) -> List[str]:
    if len(text) <= width:
        return [text]
    words = text.split()
    if not words:
        return [text]
    lines: List[str] = []
    current: List[str] = []
    current_len = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current_len + extra > width:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += extra
    if current:
        lines.append(" ".join(current))
    return lines


def render_cards(accounts: List[Dict[str, Any]]) -> str:
    width = shutil.get_terminal_size(fallback=(88, 24)).columns
    line = "=" * min(width, 88)

    output: List[str] = [f"Monkey Accounts ({len(accounts)})", line]

    for acct in accounts:
        acct_id = str(acct.get("id", "-"))
        discord_tag = str(acct.get("discord", {}).get("tag", ""))
        info = acct.get("info") if isinstance(acct.get("info"), dict) else {}
        nickname = str(info.get("nickname", ""))
        full_name = str(info.get("full_name", ""))
        profile_picture = str(info.get("profile_picture", ""))

        output.append(acct_id)
        output.extend(format_kv("discord", discord_tag, width))
        output.extend(format_kv("nickname", nickname, width))
        output.extend(format_kv("full_name", full_name, width))
        output.extend(format_kv("picture", profile_picture, width))
        output.append("-")

    if output:
        output.pop()  # remove last separator
    return "\n".join(output)


def _resolve_picture_path(
    picture: str, assets_dir: Path, repo_root: Path
) -> Tuple[Optional[Path], str]:
    if not picture:
        return None, "No image"

    if picture.startswith(("http://", "https://")):
        return None, "URL image (not fetched)"

    path = Path(picture)
    candidates: List[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(assets_dir / path)
        candidates.append(repo_root / path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate, ""

    return None, f"Missing file: {picture}"


def _load_profile_image(path: Path, max_size: int):
    try:
        import tkinter as tk
    except Exception:
        return None, "tkinter unavailable"

    try:
        from PIL import Image, ImageTk
    except Exception:
        Image = None
        ImageTk = None

    if Image is not None and ImageTk is not None:
        try:
            img = Image.open(path)
        except Exception as exc:
            return None, f"Failed to load image: {exc}"
        img.thumbnail((max_size, max_size))
        return ImageTk.PhotoImage(img), ""

    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return None, "JPEG requires Pillow"

    try:
        img = tk.PhotoImage(file=str(path))
    except tk.TclError:
        return None, f"Unsupported image: {path.suffix.lower() or 'unknown'}"

    width, height = img.width(), img.height()
    if width > max_size or height > max_size:
        factor = max(width / max_size, height / max_size)
        img = img.subsample(max(1, int(math.ceil(factor))))

    return img, ""


def render_gui(accounts: List[Dict[str, Any]]) -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:
        raise RuntimeError("tkinter is not installed") from exc

    root = tk.Tk()
    root.title("Monkey Accounts")
    root.minsize(560, 420)

    container = ttk.Frame(root, padding=12)
    container.pack(fill="both", expand=True)

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)

    scrollable = ttk.Frame(canvas)
    scroll_window = canvas.create_window((0, 0), window=scrollable, anchor="nw")

    def _on_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfigure(scroll_window, width=event.width)

    canvas.bind("<Configure>", _on_configure)

    scrollable.bind(
        "<Configure>", lambda _evt: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    image_refs: List[Any] = []

    repo_root = Path(__file__).resolve().parents[1]
    assets_dir = repo_root / "assets"

    for idx, acct in enumerate(accounts):
        acct_id = str(acct.get("id", "-"))
        discord_tag = str(acct.get("discord", {}).get("tag", "")) or "-"
        info = acct.get("info") if isinstance(acct.get("info"), dict) else {}
        nickname = str(info.get("nickname", "")) or "-"
        full_name = str(info.get("full_name", "")) or "-"
        profile_picture_raw = str(info.get("profile_picture", ""))
        profile_picture = profile_picture_raw or "-"

        resolved_path, resolve_note = _resolve_picture_path(
            profile_picture_raw, assets_dir, repo_root
        )
        if resolved_path is not None:
            try:
                profile_picture = str(resolved_path.relative_to(repo_root))
            except ValueError:
                profile_picture = str(resolved_path)

        card = ttk.Frame(scrollable, padding=10, relief="ridge")
        card.grid(row=idx, column=0, sticky="ew", pady=6)
        card.columnconfigure(1, weight=1)

        if resolved_path is not None:
            img, img_note = _load_profile_image(resolved_path, max_size=96)
        else:
            img, img_note = None, resolve_note
        if img is not None:
            image_refs.append(img)
            img_label = ttk.Label(card, image=img)
        else:
            img_label = ttk.Label(card, text=img_note or "No image", width=18, anchor="center")

        img_label.grid(row=0, column=0, rowspan=5, padx=(0, 12), sticky="n")

        title = ttk.Label(card, text=acct_id, font=("TkDefaultFont", 12, "bold"))
        title.grid(row=0, column=1, sticky="w")

        ttk.Label(card, text=f"Discord tag: {discord_tag}").grid(row=1, column=1, sticky="w")
        ttk.Label(card, text=f"Nickname: {nickname}").grid(row=2, column=1, sticky="w")
        ttk.Label(card, text=f"Full name: {full_name}").grid(row=3, column=1, sticky="w")
        ttk.Label(card, text=f"Picture: {profile_picture}", wraplength=520).grid(
            row=4, column=1, sticky="w"
        )

    root.mainloop()
    return 0


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    default_path = repo_root / "accounts.json"

    parser = argparse.ArgumentParser(description="Show monkey accounts.")
    parser.add_argument(
        "--accounts",
        type=Path,
        default=default_path,
        help=f"Path to accounts.json (copy from accounts_template.json; default: {default_path})",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Print to the terminal instead of opening a window.",
    )

    args = parser.parse_args()
    accounts = load_accounts(args.accounts)
    monkeys = [acct for acct in accounts if is_monkey(acct)]

    if not monkeys:
        print("No monkey accounts found.")
        return 0

    if args.text:
        print(render_cards(monkeys))
        return 0

    if os.environ.get("DISPLAY") is None and sys.platform.startswith("linux"):
        print("DISPLAY is not set; falling back to text output.", file=sys.stderr)
        print(render_cards(monkeys))
        return 0

    try:
        return render_gui(monkeys)
    except Exception as exc:
        print(f"GUI unavailable ({exc}); falling back to text output.", file=sys.stderr)
        print(render_cards(monkeys))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
