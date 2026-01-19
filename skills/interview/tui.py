#!/usr/bin/env python3
"""
Textual TUI for Interview Skill.

Rich terminal interface with keyboard navigation.
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    RadioSet,
    RadioButton,
    Input,
    Label,
    Checkbox,
    Rule,
)
from textual.binding import Binding
from textual import on
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .interview import Session


class QuestionCard(Container):
    """A single question with recommendation and response options."""

    DEFAULT_CSS = """
    QuestionCard {
        background: $surface;
        border: solid $primary;
        margin: 1;
        padding: 1;
        height: auto;
    }

    QuestionCard .question-text {
        margin-bottom: 1;
    }

    QuestionCard .recommendation {
        background: $primary-darken-2;
        padding: 0 1;
        margin-bottom: 1;
    }

    QuestionCard .recommendation.keep {
        background: $success-darken-2;
    }

    QuestionCard .recommendation.drop {
        background: $error-darken-2;
    }

    QuestionCard .options {
        margin-top: 1;
    }

    QuestionCard Input {
        margin-top: 1;
    }
    """

    def __init__(self, question: dict, **kwargs):
        super().__init__(**kwargs)
        self.question = question
        self.qid = question["id"]
        self.qtype = question.get("type", "yes_no_refine")
        self.recommendation = question.get("recommendation")
        self.reason = question.get("reason", "")
        self.options = question.get("options", [])

    def compose(self) -> ComposeResult:
        q = self.question

        # Question text
        yield Static(q["text"], classes="question-text")

        # Agent recommendation (if present)
        if self.recommendation:
            rec_class = "keep" if self.recommendation.lower() in ("keep", "yes") else "drop"
            rec_text = f"Agent Recommendation: {self.recommendation.upper()}"
            if self.reason:
                rec_text += f"\n  {self.reason}"
            yield Static(rec_text, classes=f"recommendation {rec_class}")

        # Response options based on type
        if self.qtype in ("yes_no", "yes_no_refine"):
            with RadioSet(id=f"radio_{self.qid}", classes="options"):
                if self.recommendation:
                    yield RadioButton("Accept recommendation", id=f"{self.qid}_accept", value=True)
                yield RadioButton("Yes / Keep", id=f"{self.qid}_yes")
                yield RadioButton("No / Drop", id=f"{self.qid}_no")

            if self.qtype == "yes_no_refine":
                yield Input(placeholder="Refinement notes (optional)", id=f"refine_{self.qid}")

        elif self.qtype == "select":
            with RadioSet(id=f"radio_{self.qid}", classes="options"):
                if self.recommendation:
                    yield RadioButton(f"Accept: {self.recommendation}", id=f"{self.qid}_accept", value=True)
                for opt in self.options:
                    yield RadioButton(opt, id=f"{self.qid}_{opt}")

        elif self.qtype == "multi":
            with Vertical(classes="options"):
                for opt in self.options:
                    checked = self.recommendation and opt in self.recommendation
                    yield Checkbox(opt, id=f"{self.qid}_{opt}", value=checked)

        elif self.qtype == "text":
            default = self.recommendation or ""
            yield Input(placeholder="Your response", id=f"text_{self.qid}", value=default)

        elif self.qtype == "confirm":
            with RadioSet(id=f"radio_{self.qid}", classes="options"):
                yield RadioButton("Confirm", id=f"{self.qid}_confirm")
                yield RadioButton("Cancel", id=f"{self.qid}_cancel")

    def get_response(self) -> dict | None:
        """Extract response from this card."""
        if self.qtype in ("yes_no", "yes_no_refine", "select", "confirm"):
            radio_set = self.query_one(f"#radio_{self.qid}", RadioSet)
            if radio_set.pressed_button is None:
                return None

            btn_id = radio_set.pressed_button.id

            if "_accept" in btn_id:
                decision = "accept"
                value = self.recommendation
            elif "_yes" in btn_id or "_confirm" in btn_id:
                decision = "override"
                value = "keep" if "_yes" in btn_id else "confirm"
            elif "_no" in btn_id or "_cancel" in btn_id:
                decision = "override"
                value = "drop" if "_no" in btn_id else "cancel"
            else:
                # Custom option from select
                decision = "override"
                value = btn_id.replace(f"{self.qid}_", "")

            response = {"decision": decision, "value": value}

            # Add refinement note if present
            if self.qtype == "yes_no_refine":
                try:
                    refine_input = self.query_one(f"#refine_{self.qid}", Input)
                    if refine_input.value.strip():
                        response["note"] = refine_input.value.strip()
                except Exception:
                    pass

            return response

        elif self.qtype == "multi":
            selected = []
            for checkbox in self.query(Checkbox):
                if checkbox.value:
                    opt = checkbox.id.replace(f"{self.qid}_", "")
                    selected.append(opt)

            # Determine if this matches recommendation
            rec_set = set(self.recommendation) if self.recommendation else set()
            decision = "accept" if set(selected) == rec_set else "override"

            return {"decision": decision, "value": selected}

        elif self.qtype == "text":
            text_input = self.query_one(f"#text_{self.qid}", Input)
            value = text_input.value.strip()
            decision = "accept" if value == self.recommendation else "override"
            return {"decision": decision, "value": value}

        return None


class InterviewApp(App):
    """Textual app for interview."""

    CSS = """
    Screen {
        background: $background;
    }

    #main-container {
        padding: 1;
    }

    #title-bar {
        background: $primary;
        padding: 1;
        margin-bottom: 1;
        text-align: center;
    }

    #context-bar {
        background: $surface;
        padding: 1;
        margin-bottom: 1;
    }

    #questions-container {
        height: 1fr;
    }

    #button-bar {
        dock: bottom;
        height: 3;
        padding: 1;
        background: $surface;
    }

    #button-bar Button {
        margin-right: 2;
    }

    #submit-btn {
        background: $success;
    }

    #skip-btn {
        background: $warning;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "submit", "Submit"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("tab", "focus_next", "Next"),
        Binding("shift+tab", "focus_previous", "Previous"),
    ]

    def __init__(self, session: "Session", **kwargs):
        super().__init__(**kwargs)
        self.session = session
        self.responses: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="main-container"):
            yield Static(self.session.title, id="title-bar")

            if self.session.context:
                yield Static(self.session.context, id="context-bar")

            with ScrollableContainer(id="questions-container"):
                for i, q in enumerate(self.session.questions, 1):
                    yield Static(f"Question {i} of {len(self.session.questions)}", classes="question-counter")
                    yield QuestionCard(q.to_dict(), id=f"card_{q.id}")
                    yield Rule()

            with Horizontal(id="button-bar"):
                yield Button("Submit (Ctrl+S)", id="submit-btn", variant="success")
                yield Button("Skip Remaining", id="skip-btn", variant="warning")

        yield Footer()

    def action_submit(self):
        """Collect all responses and exit."""
        self._collect_responses()
        self.exit(self.responses)

    def action_quit(self):
        """Save progress and exit."""
        self._collect_responses()
        self.exit(self.responses)

    @on(Button.Pressed, "#submit-btn")
    def on_submit(self):
        self.action_submit()

    @on(Button.Pressed, "#skip-btn")
    def on_skip(self):
        """Mark remaining as skipped."""
        self._collect_responses()
        for q in self.session.questions:
            if q.id not in self.responses:
                self.responses[q.id] = {"decision": "skip", "value": None}
        self.exit(self.responses)

    def _collect_responses(self):
        """Collect responses from all question cards."""
        for q in self.session.questions:
            try:
                card = self.query_one(f"#card_{q.id}", QuestionCard)
                resp = card.get_response()
                if resp:
                    self.responses[q.id] = resp
            except Exception:
                pass


def run_tui_interview(session: "Session", timeout: int) -> dict[str, dict]:
    """
    Run TUI interview and return responses.

    Args:
        session: Interview session
        timeout: Timeout in seconds (not enforced in TUI, user controls)

    Returns:
        Dict mapping question IDs to response dicts
    """
    app = InterviewApp(session)
    result = app.run()
    return result or {}
