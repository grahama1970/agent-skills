#!/usr/bin/env python3
"""
Agent-Inbox TUI.

Interactive terminal interface for managing the agent inbox.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Static,
    TextArea,
    Markdown,
)

try:
    from . import inbox
except ImportError:
    import inbox

class InboxTUI(App):
    """Agent-Inbox TUI Application."""

    CSS = """
    Screen {
        background: $surface;
    }
    
    DataTable {
        height: 1fr;
        border: solid $accent;
    }
    
    #detail_container {
        height: 1fr;
        border: solid $secondary;
        display: none;
    }
    
    .visible {
        display: block;
    }
    
    #thread_content {
        height: 1fr;
        overflow-y: scroll;
        margin: 1;
    }
    
    #reply_input {
        dock: bottom;
        margin: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "back_to_list", "Back to List"),
    ]

    current_msg_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        # Main List View
        with Container(id="main_view"):
            yield DataTable(cursor_type="row")
            
        # Detail View (Initially Hidden)
        with Container(id="detail_container"):
            yield Static("Message Details", id="detail_header")
            # Using Markdown for thread view
            yield Markdown(id="thread_content")
            yield Input(placeholder="Type reply to send...", id="reply_input")
            
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("ID", width=12)
        table.add_column("Status", width=10)
        table.add_column("From", width=15)
        table.add_column("To", width=15)
        table.add_column("Type", width=8)
        table.add_column("Priority", width=8)
        table.add_column("Subject")
        self.load_messages()

    def action_refresh(self) -> None:
        self.load_messages()
        if self.current_msg_id and self.query_one("#detail_container").display:
             self.show_details(self.current_msg_id)

    def action_back_to_list(self) -> None:
        self.query_one("#detail_container").styles.display = "none"
        self.query_one("#main_view").styles.display = "block"
        self.current_msg_id = None
        self.query_one(DataTable).focus()

    def load_messages(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        
        # Load pending details
        # inbox.list_messages returns list of dicts
        # Sort by created_at desc
        
        try:
            pending = inbox.list_messages(status="pending")
            done = inbox.list_messages(status="done")
            all_msgs = pending + done
            all_msgs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            for msg in all_msgs:
                msg_id = msg.get("id", "unknown")
                subject = msg.get("message", "").split("\n")[0][:60]
                status = msg.get("status", "pending")
                
                table.add_row(
                    msg_id,
                    status,
                    msg.get("from", "?"),
                    msg.get("to", "?"),
                    msg.get("type", "info"),
                    msg.get("priority", "normal"),
                    subject,
                    key=str(msg_id)
                )
        except Exception as e:
            self.notify(f"Error loading messages: {e}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value:
            self.show_details(event.row_key.value)

    def show_details(self, msg_id: str) -> None:
        try:
            msg = inbox.read_message(msg_id)
            if not msg:
                return
                
            # Switch views
            self.query_one("#main_view").styles.display = "none"
            self.query_one("#detail_container").styles.display = "block"
            self.current_msg_id = msg_id
            
            # Load Thread
            thread_id = msg.get("thread_id") or msg_id
            # inbox.list_thread returns sorted list
            thread = inbox.list_thread(thread_id)
            if not thread:
                thread = [msg] # Fallback
            
            md_content = f"# Thread: {thread_id}\n\n"
            for m in thread:
                sender = m.get("from", "unknown")
                timestamp = m.get("created_at", "")
                status = m.get("status", "")
                content = m.get("message", "")
                
                md_content += f"### **{sender}** ({timestamp}) [{status}]\n"
                md_content += f"{content}\n\n"
                md_content += "---\n"
                
            self.query_one("#thread_content").update(md_content)
            self.query_one("#reply_input").focus()
            
        except Exception as e:
            self.notify(f"Error showing details: {e}", severity="error")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "reply_input":
            text = event.value.strip()
            if text and self.current_msg_id:
                # Send reply
                try:
                    # Determine target
                    msg = inbox.read_message(self.current_msg_id)
                    to_project = msg.get("from") # Reply back to sender
                    current_project = inbox._detect_project() or "unknown"
                    
                    if to_project == current_project:
                         # If I am sender, reply to recipient
                         to_project = msg.get("to")
                    
                    inbox.send(
                        to_project=to_project,
                        message=text,
                        reply_to=self.current_msg_id,
                        from_project=current_project
                    )
                    
                    event.input.value = ""
                    self.notify("Reply sent!")
                    self.show_details(self.current_msg_id) # Refresh
                except Exception as e:
                    self.notify(f"Error sending reply: {e}", severity="error")

if __name__ == "__main__":
    app = InboxTUI()
    app.run()
