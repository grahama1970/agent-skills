from __future__ import annotations

import curses
from typing import Any, Callable, Dict, Optional

from .types import ClarifyQuestion


def prompt_single_question(
    question: ClarifyQuestion,
    *,
    handler: Optional[Callable[[ClarifyQuestion], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Render a single-question TUI using curses (or an injected handler)."""
    if handler is not None:
        return handler(question)
    if question.options:
        selected = _option_menu(question.prompt, [opt.label for opt in question.options])
        return {"selected_option": question.options[selected].id}
    text = _text_input(question.prompt)
    return {"text": text}


def _option_menu(prompt: str, options: list[str]) -> int:
    def _inner(stdscr):
        curses.curs_set(0)
        stdscr.clear()
        idx = 0
        while True:
            stdscr.erase()
            stdscr.addstr(0, 0, prompt)
            for i, label in enumerate(options):
                prefix = "➤ " if i == idx else "  "
                stdscr.addstr(i + 2, 0, f"{prefix}{label}")
            key = stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                idx = (idx - 1) % len(options)
            elif key in (curses.KEY_DOWN, ord("j")):
                idx = (idx + 1) % len(options)
            elif key in (curses.KEY_ENTER, ord("\n")):
                return idx

    try:
        return curses.wrapper(_inner)
    except curses.error:
        # Fallback to simple input if the terminal doesn't support curses.
        while True:
            print(prompt)
            for i, label in enumerate(options):
                print(f"{i + 1}. {label}")
            raw = input("Select option #: ").strip()
            if raw.isdigit():
                choice = int(raw) - 1
                if 0 <= choice < len(options):
                    return choice


def _text_input(prompt: str) -> str:
    def _inner(stdscr):
        curses.curs_set(1)
        curses.echo()
        stdscr.clear()
        stdscr.addstr(0, 0, prompt)
        stdscr.addstr(2, 0, "> ")
        stdscr.refresh()
        text = stdscr.getstr(2, 2).decode("utf-8")
        return text.strip()

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return input(f"{prompt}\n> ").strip()
