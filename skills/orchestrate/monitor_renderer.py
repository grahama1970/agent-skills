"""Live HTML monitor renderer for /orchestrate sessions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_monitor_html(
    session_dir: Path,
    status: dict[str, Any],
    plan: dict[str, Any],
    deps: dict[str, list[str]],
) -> None:
    """Write a live polling monitor for the session.

    The monitor is intentionally file-backed: /orchestrate already writes
    status.json after every scheduler transition, and the browser polls that
    file directly every two seconds. This keeps the pipeline transparent
    without requiring a long-running web server inside /orchestrate.
    """
    (session_dir / "monitor.css").write_text(_monitor_css())
    (session_dir / "monitor.js").write_text(_monitor_js())
    (session_dir / "monitor.html").write_text(_monitor_html(status, plan, deps))


def _monitor_html(status: dict[str, Any], plan: dict[str, Any],
                  deps: dict[str, list[str]]) -> str:
    embedded = json.dumps({"status": status, "plan": plan, "deps": deps})
    return f"""\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Orchestrate Monitor</title>
  <link rel="stylesheet" href="monitor.css">
</head>
<body>
  <main>
    <section class="hero">
      <div class="panel">
        <div class="eyebrow">Live Orchestrate Pipeline</div>
        <h1 id="run-title">Loading plan…</h1>
        <p id="run-goal" class="subtitle"></p>
        <div class="progress" aria-label="Overall progress">
          <span id="progress-bar"></span>
        </div>
        <p id="run-meta" class="meta-line"></p>
      </div>
      <aside class="panel stats" aria-label="Run summary">
        <div class="stat"><strong id="stat-completed">0</strong><span>Completed</span></div>
        <div class="stat"><strong id="stat-running">0</strong><span>Running</span></div>
        <div class="stat"><strong id="stat-failed">0</strong><span>Failed</span></div>
        <div class="stat"><strong id="stat-queued">0</strong><span>Queued</span></div>
      </aside>
    </section>

    <section class="panel transparency">
      <h2>Execution Transparency</h2>
      <div class="transparency-grid">
        <div><strong>/plan</strong><span>Full YAML-derived plan payload is visible below.</span></div>
        <div><strong>/review-plan</strong><span>Preflight/review output is surfaced as status and artifacts.</span></div>
        <div><strong>/orchestrate</strong><span>DAG lanes, dependencies, gates, and task states are live.</span></div>
        <div><strong>/code-runner</strong><span>Rounds, hunk, result, stderr, and review artifacts are linked.</span></div>
      </div>
    </section>

    <section class="panel">
      <h2>Pipeline Chain</h2>
      <div id="pipeline-chain" class="pipeline-chain"></div>
    </section>

    <section id="lanes"></section>

    <section class="raw-grid">
      <div class="panel"><h2>Plan Payload</h2><pre id="plan-json"></pre></div>
      <div class="panel"><h2>Status Payload</h2><pre id="status-json"></pre></div>
    </section>
  </main>
  <script id="initial-data" type="application/json">{embedded}</script>
  <script src="monitor.js"></script>
</body>
</html>
"""


def _monitor_css() -> str:
    return """\
:root {
  color-scheme: dark;
  --bg: #091018;
  --panel: #111b27;
  --panel-2: #162333;
  --text: #e8eef6;
  --muted: #97a6b8;
  --line: #28384a;
  --good: #56d68a;
  --bad: #ff6b6b;
  --run: #70a8ff;
  --wait: #c5a45a;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: radial-gradient(circle at top left, #142235, var(--bg) 42%);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
main { width: min(1180px, calc(100vw - 32px)); margin: 0 auto; padding: 32px 0 56px; }
.hero { display: grid; gap: 20px; grid-template-columns: 1.3fr .7fr; align-items: stretch; }
.panel, .task-card, .lane {
  background: color-mix(in srgb, var(--panel) 92%, transparent);
  border: 1px solid var(--line);
  border-radius: 18px;
  box-shadow: 0 18px 42px rgba(0,0,0,.24);
}
.panel { padding: 22px; }
h1, h2, h3, p { margin-top: 0; }
h1 { font-size: clamp(28px, 4vw, 48px); line-height: 1.02; margin-bottom: 12px; }
h2 { color: #dce8f7; margin: 0 0 16px; }
h3 { margin-bottom: 14px; }
.eyebrow { color: var(--run); font-size: 12px; letter-spacing: .14em; text-transform: uppercase; margin-bottom: 10px; }
.subtitle { color: var(--muted); font-size: 16px; line-height: 1.55; max-width: 74ch; }
.stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.stat { background: var(--panel-2); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }
.stat strong { display: block; font-size: 34px; }
.stat span { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
.progress { height: 14px; border-radius: 999px; background: #0e1722; border: 1px solid var(--line); overflow: hidden; margin: 22px 0 8px; }
.progress span { display: block; height: 100%; width: 0; background: linear-gradient(90deg, var(--run), var(--good)); transition: width .25s ease; }
.meta-line { color: var(--muted); font-size: 13px; }
.transparency { margin-top: 22px; }
.transparency-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.transparency-grid div { background: var(--panel-2); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }
.transparency-grid strong, .transparency-grid span { display: block; }
.transparency-grid span { color: var(--muted); margin-top: 6px; line-height: 1.4; }
.pipeline-chain { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.pipeline-step { background: var(--panel-2); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }
.pipeline-step strong { display: block; font-size: 15px; margin-bottom: 6px; }
.pipeline-step span { color: var(--muted); line-height: 1.4; }
.lane { padding: 18px; margin-top: 22px; }
.task-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
.task-card { padding: 18px; background: var(--panel-2); }
.task-card__top { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
.task-id { color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.status { border-radius: 999px; padding: 5px 10px; font-size: 12px; font-weight: 700; text-transform: uppercase; border: 1px solid var(--line); }
.status--completed { color: #062313; background: var(--good); }
.status--failed { color: #350909; background: var(--bad); }
.status--running { color: #081b3b; background: var(--run); }
.status--queued, .status--blocked { color: #2e2306; background: var(--wait); }
.task-meta { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 0 0 14px; }
dt { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
dd { margin: 3px 0 0; overflow-wrap: anywhere; }
.gate, .dod, details { color: #c8d5e4; line-height: 1.45; }
.review { color: #c8d5e4; border-top: 1px solid var(--line); padding-top: 12px; }
.artifact-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.artifact-list a { color: #dce8f7; text-decoration: none; border: 1px solid var(--line); border-radius: 999px; padding: 5px 9px; background: #0e1722; font-size: 12px; }
.artifact-list a:hover { border-color: var(--run); color: white; }
summary { cursor: pointer; color: #dce8f7; font-weight: 700; }
.error:empty { display: none; }
.error { color: var(--bad); border-left: 3px solid var(--bad); padding-left: 10px; }
.raw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 22px; }
pre { white-space: pre-wrap; overflow: auto; max-height: 420px; margin: 0; color: #c5d2e2; font-size: 12px; }
@media (max-width: 920px) { .hero, .raw-grid { grid-template-columns: 1fr; } .transparency-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 620px) { .stats, .task-meta, .transparency-grid { grid-template-columns: 1fr; } }
"""


def _monitor_js() -> str:
    return """\
const initial = JSON.parse(document.getElementById("initial-data").textContent);
let currentPlan = initial.plan || {};
let currentDeps = initial.deps || {};

const text = (value) => String(value ?? "");
const byId = (id) => document.getElementById(id);
const list = (value) => Array.isArray(value) ? value : value ? [value] : [];
const escapeHtml = (value) => text(value)
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function duration(task) {
  if (typeof task.started_at === "number" && typeof task.finished_at === "number") {
    return formatDuration(Math.max(0, task.finished_at - task.started_at));
  }
  if (typeof task.started_at === "number" && task.status === "running") {
    return `${formatDuration(Math.max(0, Date.now() / 1000 - task.started_at))} running`;
  }
  return "not started";
}

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function laneSort(a, b) {
  const left = Number.parseFloat(a);
  const right = Number.parseFloat(b);
  if (Number.isFinite(left) && Number.isFinite(right)) return left - right;
  return a.localeCompare(b);
}

function render(status, plan) {
  currentPlan = plan || currentPlan || {};
  const tasks = list(status.tasks);
  const planTasks = Object.fromEntries(list(currentPlan.tasks).map((task) => [text(task.id), task]));
  const lanes = Object.fromEntries(list(currentPlan.lanes).map((lane) => [text(lane.id), text(lane.label || `Lane ${lane.id}`)]));
  const counts = {completed: 0, failed: 0, running: 0, queued: 0, blocked: 0, cancelled: 0};
  for (const task of tasks) counts[task.status || "queued"] = (counts[task.status || "queued"] || 0) + 1;

  const total = tasks.length || 0;
  const completed = counts.completed || 0;
  const queued = (counts.queued || 0) + (counts.blocked || 0);
  const progress = total ? Math.round((completed / total) * 100) : 0;
  const metadata = currentPlan.metadata || {};

  document.title = `${metadata.title || "Orchestrate"} · Monitor`;
  byId("run-title").textContent = metadata.title || "Orchestrate Run";
  byId("run-goal").textContent = metadata.goal || "";
  byId("progress-bar").style.width = `${progress}%`;
  byId("run-meta").textContent = `${status.session_dir || ""} · ${completed}/${total} tasks complete · last update ${new Date().toLocaleTimeString()}`;
  byId("stat-completed").textContent = completed;
  byId("stat-running").textContent = counts.running || 0;
  byId("stat-failed").textContent = counts.failed || 0;
  byId("stat-queued").textContent = queued;
  renderPipeline(status, currentPlan, counts, total);

  const grouped = {};
  for (const task of tasks) {
    const lane = text(task.lane || "default");
    grouped[lane] ||= [];
    grouped[lane].push(task);
  }

  byId("lanes").innerHTML = Object.keys(grouped).sort(laneSort).map((laneId) => {
    const cards = grouped[laneId].sort((a, b) => text(a.id).localeCompare(text(b.id))).map((task) => {
      const planTask = planTasks[text(task.id)] || {};
      const dod = planTask.definition_of_done || {};
      const implementation = list(planTask.implementation).slice(0, 8);
      const depends = currentDeps[text(task.id)] || task.depends_on || [];
      const statusName = task.status || "queued";
      const reviewStatus = task.review_status || "not run";
      const artifacts = task.artifacts || {};
      const artifactLinks = Object.entries(artifacts).map(([name, href]) =>
        `<a href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(name)}</a>`
      ).join("");
      return `<article class="task-card">
        <div class="task-card__top"><span class="task-id">#${escapeHtml(task.id)}</span><span class="status status--${escapeHtml(statusName)}">${escapeHtml(statusName)}</span></div>
        <h3>${escapeHtml(task.title)}</h3>
        <dl class="task-meta">
          <div><dt>Runner</dt><dd>${escapeHtml(task.runner)}</dd></div>
          <div><dt>Backend</dt><dd>${escapeHtml(task.backend || "local")}</dd></div>
          <div><dt>Depends</dt><dd>${escapeHtml(depends.length ? depends.join(", ") : "none")}</dd></div>
          <div><dt>Duration</dt><dd>${escapeHtml(duration(task))}</dd></div>
        </dl>
        <p class="gate"><strong>Gate:</strong> ${escapeHtml(planTask.gate || "not specified")}</p>
        <p class="dod"><strong>DoD:</strong> ${escapeHtml(dod.command || "not specified")}</p>
        <p class="review"><strong>Review:</strong> ${escapeHtml(reviewStatus)} ${escapeHtml(task.review_output || "")}</p>
        <div class="artifact-list">${artifactLinks}</div>
        <details><summary>Implementation plan</summary><ul>${implementation.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></details>
        <p class="error">${escapeHtml(task.error || "")}</p>
      </article>`;
    }).join("");
    return `<section class="lane"><h2>${escapeHtml(lanes[laneId] || `Lane ${laneId}`)}</h2><div class="task-list">${cards}</div></section>`;
  }).join("");

  byId("plan-json").textContent = JSON.stringify(currentPlan, null, 2);
  byId("status-json").textContent = JSON.stringify(status, null, 2);
}

function renderPipeline(status, plan, counts, total) {
  const hasPlan = Boolean(plan && Array.isArray(plan.tasks));
  const tasks = list(status.tasks);
  const codeRunnerTasks = tasks.filter((task) => task.runner === "code-runner").length;
  const artifacts = tasks.reduce((count, task) => count + Object.keys(task.artifacts || {}).length, 0);
  const failed = counts.failed || 0;
  const reviewLink = status.review_plan_output ? ` <a href="${escapeHtml(status.review_plan_output)}" target="_blank" rel="noreferrer">open review-plan output</a>` : "";
  byId("pipeline-chain").innerHTML = [
    ["1. /plan", hasPlan ? `${plan.tasks.length} planned task(s), full payload visible.` : "Plan payload not loaded."],
    ["2. /review-plan", `Preflight runs before execution; warnings/failures are persisted.${reviewLink}`],
    ["3. /orchestrate", `${counts.completed || 0}/${total} complete, ${failed} failed, live scheduler state.`],
    ["4. /code-runner", `${codeRunnerTasks} code-runner task(s), ${artifacts} linked artifact(s).`],
  ].map(([title, detail]) => `<div class="pipeline-step"><strong>${escapeHtml(title)}</strong><span>${detail}</span></div>`).join("");
}

async function refresh() {
  try {
    const stamp = Date.now();
    const [statusResponse, planResponse] = await Promise.all([
      fetch(`status.json?ts=${stamp}`, {cache: "no-store"}),
      fetch(`plan.json?ts=${stamp}`, {cache: "no-store"}),
    ]);
    const status = await statusResponse.json();
    const plan = await planResponse.json();
    render(status, plan);
  } catch (error) {
    render(initial.status || {}, currentPlan || {});
    byId("run-meta").textContent += ` · live polling unavailable: ${error.message}`;
  }
}

render(initial.status || {}, currentPlan || {});
refresh();
setInterval(refresh, 2000);
"""
