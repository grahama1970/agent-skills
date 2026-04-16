"""Debug dashboard generator for code-runner.

Generates a self-contained HTML dashboard for diagnosing code-runner failures.
Inspired by Braintrust/LangSmith trace visualization patterns.

Features:
- Run-centric view: task spec, status, duration
- Trace tree: rounds as expandable nodes with tool calls
- Timeline: chronological view of all events
- Misuse detection: preflight errors/warnings
- Error classification: API errors with recovery hints
- Diff support: compare good vs bad runs (via localStorage)

Usage:
    from _debug_dashboard import TraceCollector, generate_dashboard

    collector = TraceCollector(task_id="abc123")
    collector.add_event("preflight", {"errors": [], "warnings": []})
    collector.add_round(1, messages=[...], tool_calls=[...])
    collector.set_result(success=True, dod_passed=True)

    html = generate_dashboard(collector)
    Path("/tmp/debug.html").write_text(html)
"""
from __future__ import annotations

import html
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TraceEvent:
    """A single event in the execution trace."""

    ts: float  # Unix timestamp
    event_type: str  # preflight, round, tool_call, tool_result, error, result
    data: dict[str, Any]


@dataclass
class TraceCollector:
    """Collects trace events during code-runner execution."""

    task_id: str
    task_spec: dict[str, Any] = field(default_factory=dict)
    events: list[TraceEvent] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None

    # Summary fields (set at end)
    success: bool | None = None
    dod_passed: bool | None = None
    files_written: list[str] = field(default_factory=list)
    error_message: str | None = None

    def set_task_spec(self, spec: dict[str, Any]) -> None:
        """Record the input task spec."""
        self.task_spec = spec

    def add_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Add a generic event to the trace."""
        self.events.append(TraceEvent(
            ts=time.time(),
            event_type=event_type,
            data=data,
        ))

    def add_preflight(self, errors: list[dict], warnings: list[dict]) -> None:
        """Record misuse detection results."""
        self.add_event("preflight", {
            "errors": errors,
            "warnings": warnings,
        })

    def add_round_start(self, round_num: int, prompt_tokens: int = 0) -> None:
        """Record start of a round."""
        self.add_event("round_start", {
            "round": round_num,
            "prompt_tokens": prompt_tokens,
        })

    def add_llm_response(
        self,
        round_num: int,
        content: str | None,
        tool_calls: list[dict],
        finish_reason: str,
        response_tokens: int = 0,
        duration_ms: int = 0,
    ) -> None:
        """Record LLM response."""
        self.add_event("llm_response", {
            "round": round_num,
            "content": content[:500] if content else None,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "response_tokens": response_tokens,
            "duration_ms": duration_ms,
        })

    def add_tool_call(
        self,
        round_num: int,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str,
    ) -> None:
        """Record a tool call."""
        self.add_event("tool_call", {
            "round": round_num,
            "tool_name": tool_name,
            "arguments": arguments,
            "tool_call_id": tool_call_id,
        })

    def add_tool_result(
        self,
        round_num: int,
        tool_call_id: str,
        result: dict[str, Any],
        duration_ms: int = 0,
    ) -> None:
        """Record a tool result."""
        self.add_event("tool_result", {
            "round": round_num,
            "tool_call_id": tool_call_id,
            "result": result,
            "duration_ms": duration_ms,
        })

    def add_api_error(
        self,
        round_num: int,
        status_code: int | None,
        reason: str,
        message: str,
        retryable: bool,
        should_compress: bool,
    ) -> None:
        """Record an API error with classification."""
        self.add_event("api_error", {
            "round": round_num,
            "status_code": status_code,
            "reason": reason,
            "message": message,
            "retryable": retryable,
            "should_compress": should_compress,
        })

    def add_fallback_parse(self, round_num: int, num_calls: int) -> None:
        """Record fallback tool call parsing."""
        self.add_event("fallback_parse", {
            "round": round_num,
            "num_calls": num_calls,
        })

    def set_result(
        self,
        success: bool,
        dod_passed: bool | None = None,
        files_written: list[str] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Set final execution result."""
        self.end_time = time.time()
        self.success = success
        self.dod_passed = dod_passed
        self.files_written = files_written or []
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        """Export trace as JSON-serializable dict."""
        return {
            "task_id": self.task_id,
            "task_spec": self.task_spec,
            "events": [
                {"ts": e.ts, "type": e.event_type, "data": e.data}
                for e in self.events
            ],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": int((self.end_time or time.time()) - self.start_time) * 1000,
            "success": self.success,
            "dod_passed": self.dod_passed,
            "files_written": self.files_written,
            "error_message": self.error_message,
        }


def generate_dashboard(collector: TraceCollector) -> str:
    """Generate self-contained HTML debug dashboard."""
    trace_json = json.dumps(collector.to_dict(), indent=2, default=str)
    # XSS prevention: escape </script> in embedded JSON to prevent tag injection
    trace_json = trace_json.replace("</", "<\\/")
    duration_s = (collector.end_time or time.time()) - collector.start_time

    # Count events by type
    preflight_events = [e for e in collector.events if e.event_type == "preflight"]
    round_events = [e for e in collector.events if e.event_type == "round_start"]
    tool_events = [e for e in collector.events if e.event_type == "tool_call"]
    error_events = [e for e in collector.events if e.event_type == "api_error"]

    status_class = "success" if collector.success else "failure"
    status_text = "PASSED" if collector.success else "FAILED"

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code-Runner Debug: {html.escape(collector.task_id)}</title>
    <style>
        :root {{
            --bg: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --border: #30363d;
            --text: #c9d1d9;
            --text-muted: #8b949e;
            --success: #3fb950;
            --failure: #f85149;
            --warning: #d29922;
            --info: #58a6ff;
            --accent: #7c3aed;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            padding: 20px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .header h1 {{ font-size: 1.5rem; }}
        .status {{
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 0.9rem;
        }}
        .status.success {{ background: var(--success); color: #000; }}
        .status.failure {{ background: var(--failure); color: #fff; }}
        .meta {{ color: var(--text-muted); font-size: 0.85rem; }}
        .meta span {{ margin-right: 20px; }}
        .grid {{
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 20px;
        }}
        .sidebar {{
            display: flex;
            flex-direction: column;
            gap: 15px;
        }}
        .card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
        }}
        .card-header {{
            padding: 12px 16px;
            background: var(--bg-tertiary);
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .card-header:hover {{ background: var(--border); }}
        .card-header .toggle {{ color: var(--text-muted); }}
        .card-body {{
            padding: 12px 16px;
            font-size: 0.85rem;
        }}
        .card-body.collapsed {{ display: none; }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .badge-success {{ background: var(--success); color: #000; }}
        .badge-failure {{ background: var(--failure); color: #fff; }}
        .badge-warning {{ background: var(--warning); color: #000; }}
        .badge-info {{ background: var(--info); color: #000; }}
        .timeline {{
            position: relative;
            padding-left: 30px;
        }}
        .timeline::before {{
            content: '';
            position: absolute;
            left: 10px;
            top: 0;
            bottom: 0;
            width: 2px;
            background: var(--border);
        }}
        .timeline-item {{
            position: relative;
            padding: 12px 16px;
            margin-bottom: 10px;
            background: var(--bg-tertiary);
            border-radius: 6px;
            border-left: 3px solid var(--info);
        }}
        .timeline-item.error {{ border-left-color: var(--failure); }}
        .timeline-item.success {{ border-left-color: var(--success); }}
        .timeline-item.warning {{ border-left-color: var(--warning); }}
        .timeline-item::before {{
            content: '';
            position: absolute;
            left: -24px;
            top: 18px;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--info);
            border: 2px solid var(--bg);
        }}
        .timeline-item.error::before {{ background: var(--failure); }}
        .timeline-item.success::before {{ background: var(--success); }}
        .timeline-item.warning::before {{ background: var(--warning); }}
        .timeline-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}
        .timeline-title {{ font-weight: 600; font-size: 0.9rem; }}
        .timeline-time {{ color: var(--text-muted); font-size: 0.75rem; }}
        .timeline-content {{ font-size: 0.85rem; }}
        pre {{
            background: var(--bg);
            padding: 12px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 0.8rem;
            margin-top: 8px;
        }}
        .tool-call {{
            display: flex;
            gap: 8px;
            align-items: flex-start;
            padding: 8px;
            background: var(--bg);
            border-radius: 4px;
            margin-top: 8px;
        }}
        .tool-name {{
            font-weight: 600;
            color: var(--accent);
            white-space: nowrap;
        }}
        .tool-args {{
            flex: 1;
            font-size: 0.8rem;
            color: var(--text-muted);
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .misuse-item {{
            padding: 8px 12px;
            margin: 4px 0;
            border-radius: 4px;
            font-size: 0.85rem;
        }}
        .misuse-error {{
            background: rgba(248, 81, 73, 0.1);
            border-left: 3px solid var(--failure);
        }}
        .misuse-warning {{
            background: rgba(210, 153, 34, 0.1);
            border-left: 3px solid var(--warning);
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }}
        .stat {{
            text-align: center;
            padding: 12px;
            background: var(--bg);
            border-radius: 4px;
        }}
        .stat-value {{
            font-size: 1.5rem;
            font-weight: bold;
            color: var(--info);
        }}
        .stat-label {{
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }}
        .file-list {{
            list-style: none;
        }}
        .file-list li {{
            padding: 6px 0;
            border-bottom: 1px solid var(--border);
            font-family: monospace;
            font-size: 0.85rem;
        }}
        .file-list li:last-child {{ border-bottom: none; }}
        .tabs {{
            display: flex;
            border-bottom: 1px solid var(--border);
            margin-bottom: 15px;
        }}
        .tab {{
            padding: 10px 20px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            color: var(--text-muted);
        }}
        .tab:hover {{ color: var(--text); }}
        .tab.active {{
            color: var(--info);
            border-bottom-color: var(--info);
        }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .json-viewer {{
            max-height: 400px;
            overflow-y: auto;
        }}
        .expand-btn {{
            color: var(--info);
            cursor: pointer;
            font-size: 0.8rem;
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Code-Runner Debug Dashboard</h1>
            <div class="meta">
                <span>Task: <strong>{html.escape(collector.task_id)}</strong></span>
                <span>Backend: <strong>{html.escape(collector.task_spec.get('backend', 'unknown'))}</strong></span>
                <span>Duration: <strong>{duration_s:.1f}s</strong></span>
                <span>Rounds: <strong>{len(round_events)}</strong></span>
                <span>Tool Calls: <strong>{len(tool_events)}</strong></span>
            </div>
        </div>
        <div class="status {status_class}">{status_text}</div>
    </div>

    <div class="grid">
        <div class="sidebar">
            <!-- Stats Card -->
            <div class="card">
                <div class="card-header" onclick="toggleCard(this)">
                    <span>Summary</span>
                    <span class="toggle">-</span>
                </div>
                <div class="card-body">
                    <div class="stats">
                        <div class="stat">
                            <div class="stat-value">{len(round_events)}</div>
                            <div class="stat-label">Rounds</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">{len(tool_events)}</div>
                            <div class="stat-label">Tool Calls</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">{len(error_events)}</div>
                            <div class="stat-label">Errors</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">{len(collector.files_written)}</div>
                            <div class="stat-label">Files</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Misuse Detection Card -->
            <div class="card">
                <div class="card-header" onclick="toggleCard(this)">
                    <span>Misuse Detection</span>
                    <span class="toggle">-</span>
                </div>
                <div class="card-body" id="misuse-card">
                    <!-- Populated by JS -->
                </div>
            </div>

            <!-- Files Written Card -->
            <div class="card">
                <div class="card-header" onclick="toggleCard(this)">
                    <span>Files Written</span>
                    <span class="toggle">-</span>
                </div>
                <div class="card-body">
                    <ul class="file-list" id="files-list">
                        <!-- Populated by JS -->
                    </ul>
                </div>
            </div>

            <!-- Task Spec Card -->
            <div class="card">
                <div class="card-header" onclick="toggleCard(this)">
                    <span>Task Spec</span>
                    <span class="toggle">+</span>
                </div>
                <div class="card-body collapsed">
                    <pre id="task-spec-json"></pre>
                </div>
            </div>

            <!-- Raw Trace Card -->
            <div class="card">
                <div class="card-header" onclick="toggleCard(this)">
                    <span>Raw Trace JSON</span>
                    <span class="toggle">+</span>
                </div>
                <div class="card-body collapsed json-viewer">
                    <pre id="raw-trace-json"></pre>
                </div>
            </div>
        </div>

        <div class="main">
            <div class="card">
                <div class="tabs">
                    <div class="tab active" onclick="switchTab('timeline')">Timeline</div>
                    <div class="tab" onclick="switchTab('rounds')">By Round</div>
                </div>

                <div id="timeline-tab" class="tab-content active">
                    <div class="card-body">
                        <div class="timeline" id="timeline">
                            <!-- Populated by JS -->
                        </div>
                    </div>
                </div>

                <div id="rounds-tab" class="tab-content">
                    <div class="card-body" id="rounds-view">
                        <!-- Populated by JS -->
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const TRACE = {trace_json};

        function toggleCard(header) {{
            const body = header.nextElementSibling;
            const toggle = header.querySelector('.toggle');
            body.classList.toggle('collapsed');
            toggle.textContent = body.classList.contains('collapsed') ? '+' : '-';
        }}

        function switchTab(tab) {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelector(`.tab[onclick*="${{tab}}"]`).classList.add('active');
            document.getElementById(tab + '-tab').classList.add('active');
        }}

        function escapeHtml(str) {{
            if (typeof str !== 'string') return String(str);
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }}

        function formatTime(ts) {{
            const d = new Date(ts * 1000);
            return d.toLocaleTimeString();
        }}

        function truncate(str, len=100) {{
            if (!str) return '';
            str = String(str);
            return str.length > len ? str.slice(0, len) + '...' : str;
        }}

        function renderMisuse() {{
            const container = document.getElementById('misuse-card');
            const preflightEvents = TRACE.events.filter(e => e.type === 'preflight');

            if (preflightEvents.length === 0) {{
                container.innerHTML = '<div style="color: var(--text-muted)">No misuse detection data</div>';
                return;
            }}

            let html = '';
            for (const evt of preflightEvents) {{
                const {{ errors, warnings }} = evt.data;
                if (errors && errors.length > 0) {{
                    for (const err of errors) {{
                        html += `<div class="misuse-item misuse-error">
                            <strong>[ERROR] ${{escapeHtml(err.field || err.error_type)}}</strong><br>
                            ${{escapeHtml(err.message)}}
                            ${{err.correct_value ? '<br><em>Correct: ' + escapeHtml(err.correct_value) + '</em>' : ''}}
                        </div>`;
                    }}
                }}
                if (warnings && warnings.length > 0) {{
                    for (const warn of warnings) {{
                        html += `<div class="misuse-item misuse-warning">
                            <strong>[WARN] ${{escapeHtml(warn.field)}}</strong><br>
                            ${{escapeHtml(warn.message)}}
                        </div>`;
                    }}
                }}
            }}

            if (!html) {{
                html = '<div style="color: var(--success)">No issues detected</div>';
            }}
            container.innerHTML = html;
        }}

        function renderFiles() {{
            const container = document.getElementById('files-list');
            if (!TRACE.files_written || TRACE.files_written.length === 0) {{
                container.innerHTML = '<li style="color: var(--text-muted)">No files written</li>';
                return;
            }}
            container.innerHTML = TRACE.files_written.map(f => `<li>${{escapeHtml(f)}}</li>`).join('');
        }}

        function renderTimeline() {{
            const container = document.getElementById('timeline');
            let html = '';

            for (const evt of TRACE.events) {{
                const time = formatTime(evt.ts);
                let itemClass = '';
                let title = '';
                let content = '';

                switch (evt.type) {{
                    case 'preflight':
                        const hasErrors = evt.data.errors && evt.data.errors.length > 0;
                        itemClass = hasErrors ? 'error' : 'success';
                        title = 'Preflight Check';
                        content = hasErrors
                            ? `${{evt.data.errors.length}} error(s), ${{(evt.data.warnings || []).length}} warning(s)`
                            : 'Passed';
                        break;

                    case 'round_start':
                        itemClass = '';
                        title = `Round ${{evt.data.round}} Started`;
                        content = evt.data.prompt_tokens ? `~${{evt.data.prompt_tokens}} prompt tokens` : '';
                        break;

                    case 'llm_response':
                        itemClass = 'success';
                        title = `Round ${{evt.data.round}} Response`;
                        const tcCount = (evt.data.tool_calls || []).length;
                        content = `${{tcCount}} tool call(s), finish: ${{evt.data.finish_reason}}`;
                        if (evt.data.duration_ms) content += ` (${{evt.data.duration_ms}}ms)`;
                        break;

                    case 'tool_call':
                        itemClass = '';
                        title = `Tool: ${{evt.data.tool_name}}`;
                        content = `<div class="tool-call">
                            <span class="tool-name">${{escapeHtml(evt.data.tool_name)}}</span>
                            <span class="tool-args">${{escapeHtml(truncate(JSON.stringify(evt.data.arguments), 150))}}</span>
                        </div>`;
                        break;

                    case 'tool_result':
                        const ok = evt.data.result?.ok;
                        itemClass = ok ? 'success' : 'error';
                        title = `Tool Result`;
                        const resultPreview = evt.data.result?.error_message || evt.data.result?.path || 'OK';
                        content = escapeHtml(truncate(resultPreview, 100));
                        if (evt.data.duration_ms) content += ` (${{evt.data.duration_ms}}ms)`;
                        break;

                    case 'api_error':
                        itemClass = 'error';
                        title = `API Error: ${{evt.data.reason}}`;
                        content = `Status: ${{evt.data.status_code || 'N/A'}}, Retryable: ${{evt.data.retryable}}<br>
                            ${{escapeHtml(truncate(evt.data.message, 200))}}`;
                        break;

                    case 'fallback_parse':
                        itemClass = 'warning';
                        title = 'Fallback Parser';
                        content = `Extracted ${{evt.data.num_calls}} tool call(s) from raw content`;
                        break;

                    default:
                        title = evt.type;
                        content = `<pre>${{escapeHtml(JSON.stringify(evt.data, null, 2))}}</pre>`;
                }}

                html += `<div class="timeline-item ${{itemClass}}">
                    <div class="timeline-header">
                        <span class="timeline-title">${{title}}</span>
                        <span class="timeline-time">${{time}}</span>
                    </div>
                    <div class="timeline-content">${{content}}</div>
                </div>`;
            }}

            container.innerHTML = html || '<div style="color: var(--text-muted)">No events recorded</div>';
        }}

        function renderRoundsView() {{
            const container = document.getElementById('rounds-view');
            const rounds = {{}};

            // Group events by round
            for (const evt of TRACE.events) {{
                const round = evt.data.round;
                if (round !== undefined) {{
                    if (!rounds[round]) rounds[round] = [];
                    rounds[round].push(evt);
                }}
            }}

            let html = '';
            for (const [roundNum, events] of Object.entries(rounds).sort((a, b) => a[0] - b[0])) {{
                const toolCalls = events.filter(e => e.type === 'tool_call');
                const response = events.find(e => e.type === 'llm_response');
                const errors = events.filter(e => e.type === 'api_error');

                html += `<div class="card" style="margin-bottom: 15px;">
                    <div class="card-header" onclick="toggleCard(this)">
                        <span>Round ${{roundNum}}</span>
                        <span>
                            <span class="badge badge-info">${{toolCalls.length}} tools</span>
                            ${{errors.length > 0 ? '<span class="badge badge-failure">' + errors.length + ' errors</span>' : ''}}
                        </span>
                    </div>
                    <div class="card-body">`;

                // Tool calls
                for (const tc of toolCalls) {{
                    const result = events.find(e => e.type === 'tool_result' && e.data.tool_call_id === tc.data.tool_call_id);
                    const ok = result?.data?.result?.ok;
                    html += `<div class="tool-call" style="border-left: 3px solid var(${{ok ? '--success' : '--failure'}});">
                        <span class="tool-name">${{escapeHtml(tc.data.tool_name)}}</span>
                        <span class="tool-args">${{escapeHtml(truncate(JSON.stringify(tc.data.arguments), 150))}}</span>
                    </div>`;
                }}

                // Errors
                for (const err of errors) {{
                    html += `<div class="misuse-item misuse-error" style="margin-top: 10px;">
                        <strong>${{escapeHtml(err.data.reason)}}</strong>: ${{escapeHtml(err.data.message)}}
                    </div>`;
                }}

                html += `</div></div>`;
            }}

            container.innerHTML = html || '<div style="color: var(--text-muted)">No rounds recorded</div>';
        }}

        // Initialize
        document.getElementById('task-spec-json').textContent = JSON.stringify(TRACE.task_spec, null, 2);
        document.getElementById('raw-trace-json').textContent = JSON.stringify(TRACE, null, 2);
        renderMisuse();
        renderFiles();
        renderTimeline();
        renderRoundsView();

        // Save to localStorage for comparison
        const traceKey = 'code-runner-trace-' + TRACE.task_id;
        localStorage.setItem(traceKey, JSON.stringify(TRACE));
        console.log('Trace saved to localStorage:', traceKey);
    </script>
</body>
</html>
'''
