"""QRA Review Textual TUI — Prodigy-style human-in-the-loop assessment.

Embry-themed split-pane layout:
  Left 60%: QRA card with assessment details
  Right 40%: Embry chat panel with /slash command dispatch

Design compliance: P1 (semantic color), P2 (text+color), P5 (keyboard), P6 (no animation).
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Input, RichLog
from textual import on, work

from .tui_theme import EMBRY_TCSS
from .tui_widgets import StatsBar, QRACard, AssessmentDetail
from .tui_chat import EmbryChatHandler


class QRAReviewApp(App):
    """Textual TUI for reviewing WARN-grade QRA candidates."""

    CSS = EMBRY_TCSS + """
    #main-split {
        height: 1fr;
    }
    #qra-pane {
        width: 60%;
        padding: 1;
    }
    #chat-pane {
        width: 40%;
        border-left: solid #333333;
        padding: 1;
    }
    #chat-log {
        height: 1fr;
        background: #171717;
    }
    #chat-input {
        dock: bottom;
        background: #262626;
        color: #ffffff;
    }
    #stats-bar {
        dock: top;
        height: 1;
        background: #4a9eff;
        color: #ffffff;
        text-style: bold;
        padding: 0 2;
    }
    #hint-bar {
        dock: bottom;
        height: 1;
        background: #171717;
        color: #808080;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("a", "accept", "Accept", show=True),
        Binding("r", "reject", "Reject", show=True),
        Binding("e", "edit", "Edit", show=True),
        Binding("s", "skip", "Skip", show=True),
        Binding("slash", "chat", "Chat", show=True),
        Binding("f5", "regex", "Bulk", show=True),
        Binding("q", "quit_app", "Quit", show=True),
    ]

    def __init__(
        self,
        candidates: list[dict],
        bridge,
        reviewer: str = "human",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.candidates = candidates
        self.bridge = bridge
        self.reviewer = reviewer
        self.current_idx = 0
        self.stats = {"accepted": 0, "rejected": 0, "amended": 0, "skipped": 0}
        self.chat_handler = EmbryChatHandler()

    def compose(self) -> ComposeResult:
        yield Static(self._stats_text(), id="stats-bar")
        with Horizontal(id="main-split"):
            with Vertical(id="qra-pane"):
                yield QRACard(id="qra-card")
                yield AssessmentDetail(id="assess-detail")
            with Vertical(id="chat-pane"):
                yield RichLog(id="chat-log", highlight=True, markup=True)
                yield Input(placeholder="> Chat with Embry or /command...", id="chat-input")
        yield Static(
            "A=accept  R=reject  E=edit  S=skip  /=chat  F5=regex  Q=quit",
            id="hint-bar",
        )

    def on_mount(self) -> None:
        self._show_current()

    def _stats_text(self) -> str:
        total = len(self.candidates)
        idx = self.current_idx + 1
        a = self.stats["accepted"]
        r = self.stats["rejected"]
        e = self.stats["amended"]
        s = self.stats["skipped"]
        return f" QRA {idx}/{total}  |  \u2713{a}  \u2717{r}  \u270e{e}  \u2500{s}"

    def _refresh_stats(self) -> None:
        bar = self.query_one("#stats-bar", Static)
        bar.update(self._stats_text())

    def _show_current(self) -> None:
        if self.current_idx >= len(self.candidates):
            self._show_done()
            return
        doc = self.candidates[self.current_idx]
        self.query_one("#qra-card", QRACard).load(doc)
        self.query_one("#assess-detail", AssessmentDetail).load(doc)
        self._refresh_stats()
        # Add context to chat
        log = self.query_one("#chat-log", RichLog)
        log.clear()
        control = doc.get("control_id", "?")
        fw = doc.get("assessment_framework", "?")
        log.write(f"[dim]--- Candidate: {doc.get('_key', '?')} ({fw}: {control}) ---[/dim]")

    def _show_done(self) -> None:
        card = self.query_one("#qra-card", QRACard)
        card.update("[bold green]Review complete![/bold green]\n\n"
                     f"Accepted: {self.stats['accepted']}\n"
                     f"Rejected: {self.stats['rejected']}\n"
                     f"Amended: {self.stats['amended']}\n"
                     f"Skipped: {self.stats['skipped']}")
        self.query_one("#assess-detail", AssessmentDetail).update("")

    def _advance(self) -> None:
        self.current_idx += 1
        self._show_current()

    # --- Actions ---

    def action_accept(self) -> None:
        if self.current_idx >= len(self.candidates):
            return
        doc = self.candidates[self.current_idx]
        ok = self.bridge.accept(doc["_key"], self.reviewer)
        if ok:
            self.stats["accepted"] += 1
            log = self.query_one("#chat-log", RichLog)
            log.write(f"[green]\u2713 Accepted {doc['_key']}[/green]")
        self._advance()

    def action_reject(self) -> None:
        if self.current_idx >= len(self.candidates):
            return
        doc = self.candidates[self.current_idx]
        ok = self.bridge.reject(doc["_key"], self.reviewer)
        if ok:
            self.stats["rejected"] += 1
            log = self.query_one("#chat-log", RichLog)
            log.write(f"[red]\u2717 Rejected {doc['_key']}[/red]")
        self._advance()

    def action_edit(self) -> None:
        if self.current_idx >= len(self.candidates):
            return
        # Focus the chat input for editing
        inp = self.query_one("#chat-input", Input)
        doc = self.candidates[self.current_idx]
        inp.value = doc.get("answer", "")[:200]
        inp.focus()
        log = self.query_one("#chat-log", RichLog)
        log.write("[yellow]Edit mode: modify the answer above and press Enter to re-assess[/yellow]")
        inp.placeholder = "Edit answer, then Enter to re-assess..."

    def action_skip(self) -> None:
        if self.current_idx >= len(self.candidates):
            return
        self.stats["skipped"] += 1
        self._advance()

    def action_chat(self) -> None:
        inp = self.query_one("#chat-input", Input)
        inp.placeholder = "> Chat with Embry or /command..."
        inp.focus()

    def action_regex(self) -> None:
        inp = self.query_one("#chat-input", Input)
        inp.placeholder = "Bulk filter: reject framework:CWE grounding:<0.55"
        inp.value = "reject "
        inp.focus()

    def action_quit_app(self) -> None:
        self.exit()

    @on(Input.Submitted, "#chat-input")
    def on_chat_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        log = self.query_one("#chat-log", RichLog)

        # Check if this is an edit submission
        if event.input.placeholder.startswith("Edit answer"):
            self._handle_amend(text)
            event.input.placeholder = "> Chat with Embry or /command..."
            return

        # Check for bulk operations
        if text.startswith("reject ") or text.startswith("accept "):
            self._handle_bulk(text, log)
            return

        # Regular chat or /command
        log.write(f"[#4a9eff]> {text}[/#4a9eff]")
        self._run_chat(text)

    def _handle_amend(self, new_answer: str) -> None:
        if self.current_idx >= len(self.candidates):
            return
        doc = self.candidates[self.current_idx]
        log = self.query_one("#chat-log", RichLog)

        result = self.bridge.amend(doc["_key"], self.reviewer, new_answer)
        grade = result.get("grade", "FAIL")
        notes = result.get("notes", [])

        if grade == "PASS":
            # Auto-accept amended PASS
            self.bridge.accept(doc["_key"], self.reviewer)
            self.stats["amended"] += 1
            log.write(f"[green]\u270e Amended and accepted (PASS): {notes}[/green]")
            self._advance()
        elif grade == "WARN":
            log.write(f"[yellow]\u270e Amended but still WARN: {notes}[/yellow]")
            log.write("[dim]Try editing again or reject.[/dim]")
        else:
            log.write(f"[red]\u270e Amendment made it worse (FAIL): {notes}[/red]")

    def _handle_bulk(self, text: str, log: RichLog) -> None:
        """Parse bulk filter commands."""
        parts = text.split()
        action = parts[0]  # "reject" or "accept"

        # Parse filter fields
        allowed_fields = {"framework", "grounding", "control_id", "anchoring_ok", "space_terms_ok"}
        aql_parts = []
        for p in parts[1:]:
            if ":" not in p:
                continue
            field, val = p.split(":", 1)
            if field not in allowed_fields:
                log.write(f"[red]Unknown filter field: {field}. Allowed: {sorted(allowed_fields)}[/red]")
                return
            # Map to AQL
            if field == "framework":
                aql_parts.append(f'd.assessment_framework == "{val.upper()}"')
            elif field == "grounding":
                if val.startswith("<"):
                    aql_parts.append(f"d.assessment_grounding < {float(val[1:])}")
                elif val.startswith(">"):
                    aql_parts.append(f"d.assessment_grounding > {float(val[1:])}")
            elif field == "control_id":
                aql_parts.append(f'd.control_id == "{val}"')
            elif field in ("anchoring_ok", "space_terms_ok"):
                aql_parts.append(f"d.assessment_{field} == {'true' if val.lower() in ('true', 'ok', 'yes') else 'false'}")

        if not aql_parts:
            log.write("[red]No valid filters parsed.[/red]")
            return

        filter_aql = " AND ".join(aql_parts)
        log.write(f"[dim]Filter: {filter_aql}[/dim]")

        if action == "reject":
            count = self.bridge.bulk_reject(filter_aql, self.reviewer)
            self.stats["rejected"] += count
            log.write(f"[red]Bulk rejected {count} candidates[/red]")
        else:
            log.write("[yellow]Bulk accept not yet implemented — use individual accept.[/yellow]")

        self._refresh_stats()

    @work(thread=True)
    def _run_chat(self, text: str) -> None:
        """Run chat/command in background thread to avoid blocking TUI."""
        doc = self.candidates[self.current_idx] if self.current_idx < len(self.candidates) else {}
        response = self.chat_handler.handle(text, doc)
        self.call_from_thread(self._append_chat, response)

    def _append_chat(self, text: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.write(text)
