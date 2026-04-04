#!/usr/bin/env node
/**
 * review-ui: Generate a review page from a manifest.json using iframes to
 * render the Stitch HTML/CSS at full fidelity (no blurry screenshots).
 *
 * Usage:
 *   node review_ui.mjs --manifest <path/to/manifest.json> [--output <dir>] [--title <name>]
 *
 * The manifest entries should have htmlPath fields (from explore --with-html).
 * Falls back to screenId-based HTML lookup in the same directory.
 * Notes persist in localStorage keyed by the manifest path.
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { resolve, dirname, basename, join } from "path";

const args = process.argv.slice(2);

function getArg(name) {
  const idx = args.indexOf(`--${name}`);
  return idx >= 0 && idx + 1 < args.length ? args[idx + 1] : null;
}

const manifestPath = getArg("manifest");
const outputDir = getArg("output") || dirname(manifestPath || ".");
const title = getArg("title") || "Mockup Review";

if (!manifestPath || !existsSync(resolve(manifestPath))) {
  console.error("Usage: review-ui --manifest <manifest.json> [--output <dir>] [--title <name>]");
  process.exit(1);
}

const manifestDir = dirname(resolve(manifestPath));
const manifest = JSON.parse(readFileSync(resolve(manifestPath), "utf-8"));
const views = manifest.filter(v => !v.error);

// Resolve HTML path for each view: htmlPath field > screenId.html > view.html
const viewData = views.map(v => {
  let htmlFile = null;
  // Try htmlPath from manifest
  if (v.htmlPath && existsSync(v.htmlPath)) {
    htmlFile = basename(v.htmlPath);
  }
  // Try screenId.html in manifest dir
  if (!htmlFile && v.screenId) {
    const candidate = join(manifestDir, `${v.screenId}.html`);
    if (existsSync(candidate)) htmlFile = `${v.screenId}.html`;
  }
  // Try view.html in manifest dir
  if (!htmlFile) {
    const candidate = join(manifestDir, `${v.view}.html`);
    if (existsSync(candidate)) htmlFile = `${v.view}.html`;
  }
  return {
    name: v.view,
    screenId: v.screenId || "",
    htmlFile, // relative to manifest dir (for iframe src)
  };
});

const missing = viewData.filter(v => !v.htmlFile);
if (missing.length > 0) {
  console.error(`Warning: no HTML found for: ${missing.map(m => m.name).join(", ")}`);
  console.error(`  Pull HTML with: ./run.sh pull --project <id> --screen <screenId> --output ${manifestDir}`);
}

const storageKey = resolve(manifestPath);

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${title} — Review</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0b1220; color: #e2e8f0; font-family: 'Inter', -apple-system, sans-serif; }

  .tab-bar {
    display: flex; gap: 2px; padding: 8px 16px 0; background: #0f1729;
    border-bottom: 1px solid #1e293b; position: sticky; top: 0; z-index: 100;
  }
  .tab {
    padding: 8px 16px; cursor: pointer; border-radius: 6px 6px 0 0;
    background: #1a2332; color: #94a3b8; font-size: 13px; font-weight: 500;
    transition: all 0.15s; position: relative; user-select: none;
  }
  .tab:hover { background: #1e293b; color: #cbd5e1; }
  .tab.active { background: #7c3aed; color: #fff; }
  .tab .badge {
    position: absolute; top: 2px; right: 4px; background: #ff4444; color: #fff;
    font-size: 9px; border-radius: 8px; min-width: 14px; height: 14px;
    display: flex; align-items: center; justify-content: center; padding: 0 3px;
  }

  .header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; background: #0f1729; border-bottom: 1px solid #1e293b;
  }
  .header h1 { font-size: 16px; font-weight: 600; }
  .header-actions { display: flex; gap: 8px; }
  .btn {
    padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer;
    font-size: 12px; font-weight: 500; transition: all 0.15s;
  }
  .btn-primary { background: #7c3aed; color: #fff; }
  .btn-primary:hover { background: #6d28d9; }
  .btn-secondary { background: #1e293b; color: #cbd5e1; }
  .btn-secondary:hover { background: #334155; }

  .view-panel { display: none; padding: 16px; }
  .view-panel.active { display: flex; gap: 16px; }

  .iframe-area {
    flex: 1; position: relative; overflow: hidden;
    height: calc(100vh - 110px); border-radius: 8px; border: 1px solid #1e293b;
  }
  .iframe-area iframe {
    width: 100%; height: 100%; border: none; background: #fff;
  }
  .iframe-area .no-html {
    display: flex; align-items: center; justify-content: center;
    height: 100%; color: #64748b; font-size: 14px;
  }

  /* Transparent overlay for capturing right-clicks on iframe */
  .click-overlay {
    position: absolute; inset: 0; z-index: 5; cursor: crosshair;
  }
  .click-overlay.passthrough { pointer-events: none; }

  .note-marker {
    position: absolute; width: 24px; height: 24px; border-radius: 50%;
    background: #ff4444; color: #fff; font-size: 11px; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; transform: translate(-50%, -50%);
    box-shadow: 0 2px 8px rgba(255,68,68,0.5); z-index: 10;
    transition: transform 0.1s; pointer-events: auto;
  }
  .note-marker:hover { transform: translate(-50%, -50%) scale(1.2); }

  .notes-sidebar {
    width: 320px; min-width: 320px; max-height: calc(100vh - 110px);
    overflow-y: auto; display: flex; flex-direction: column; gap: 8px;
  }
  .notes-sidebar h3 {
    font-size: 13px; color: #94a3b8; text-transform: uppercase;
    letter-spacing: 0.05em; padding-bottom: 4px;
    border-bottom: 1px solid #1e293b;
  }
  .note-card {
    background: #1a2332; border-radius: 6px; padding: 10px;
    border-left: 3px solid #7c3aed; font-size: 13px;
  }
  .note-card .note-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 6px;
  }
  .note-card .note-num { color: #7c3aed; font-weight: 600; }
  .note-card .note-delete {
    color: #94a3b8; cursor: pointer; font-size: 16px; line-height: 1;
  }
  .note-card .note-delete:hover { color: #ff4444; }
  .note-card .note-text { color: #cbd5e1; line-height: 1.4; }
  .note-card .note-pos { color: #64748b; font-size: 11px; margin-top: 4px; }

  .no-notes {
    color: #64748b; font-style: italic; text-align: center; padding: 24px 0;
    font-size: 13px;
  }

  .ctx-menu {
    display: none; position: fixed; z-index: 200;
    background: #1e293b; border: 1px solid #334155; border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5); min-width: 200px; padding: 4px 0;
  }
  .ctx-menu.show { display: block; }
  .ctx-item {
    padding: 8px 14px; cursor: pointer; font-size: 13px; color: #e2e8f0;
    transition: background 0.1s;
  }
  .ctx-item:hover { background: #334155; }

  .note-dialog {
    display: none; position: fixed; z-index: 300;
    background: #1a2332; border: 1px solid #7c3aed; border-radius: 8px;
    box-shadow: 0 8px 32px rgba(124,58,237,0.3); padding: 12px; width: 320px;
  }
  .note-dialog.show { display: block; }
  .note-dialog textarea {
    width: 100%; height: 80px; background: #0f1729; border: 1px solid #334155;
    border-radius: 4px; color: #e2e8f0; padding: 8px; font-size: 13px;
    font-family: inherit; resize: vertical;
  }
  .note-dialog textarea:focus { outline: none; border-color: #7c3aed; }
  .note-dialog .dialog-actions {
    display: flex; justify-content: flex-end; gap: 6px; margin-top: 8px;
  }

  .export-panel {
    display: none; position: fixed; top: 50%; left: 50%;
    transform: translate(-50%, -50%); z-index: 400;
    background: #1a2332; border: 1px solid #334155; border-radius: 12px;
    box-shadow: 0 16px 48px rgba(0,0,0,0.6); padding: 24px; width: 600px;
    max-height: 80vh; overflow-y: auto;
  }
  .export-panel.show { display: block; }
  .export-panel h2 { font-size: 16px; margin-bottom: 12px; }
  .export-panel pre {
    background: #0f1729; padding: 12px; border-radius: 6px;
    font-size: 12px; overflow-x: auto; max-height: 400px; overflow-y: auto;
    color: #94a3b8; white-space: pre-wrap;
  }
  .overlay {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 350;
  }
  .overlay.show { display: block; }

  .status-bar {
    position: fixed; bottom: 0; left: 0; right: 0; padding: 6px 16px;
    background: #0f1729; border-top: 1px solid #1e293b; font-size: 11px;
    color: #64748b; display: flex; justify-content: space-between;
  }

  /* Toggle button for overlay mode */
  .mode-toggle {
    display: flex; align-items: center; gap: 6px; font-size: 12px; color: #94a3b8;
  }
  .mode-toggle input { accent-color: #7c3aed; }
</style>
</head>
<body>

<div class="header">
  <h1>${title}</h1>
  <div class="header-actions">
    <label class="mode-toggle">
      <input type="checkbox" id="interactToggle" onchange="toggleInteract(this.checked)">
      Interact with mockup
    </label>
    <button class="btn btn-secondary" onclick="clearAllNotes()">Clear All Notes</button>
    <button class="btn btn-secondary" onclick="showExport('json')">Export JSON</button>
    <button class="btn btn-primary" onclick="showExport('feedback')">Compile Feedback</button>
  </div>
</div>

<div class="tab-bar" id="tabBar"></div>
<div id="panels"></div>

<div class="ctx-menu" id="ctxMenu">
  <div class="ctx-item" onclick="openNoteDialog()">Add Note</div>
  <div class="ctx-item" onclick="copyCoords()">Copy Position</div>
</div>

<div class="note-dialog" id="noteDialog">
  <textarea id="noteInput" placeholder="Describe the issue or feedback..."></textarea>
  <div class="dialog-actions">
    <button class="btn btn-secondary" onclick="closeNoteDialog()">Cancel</button>
    <button class="btn btn-primary" onclick="saveNote()">Save Note</button>
  </div>
</div>

<div class="overlay" id="overlay" onclick="closeExport()"></div>
<div class="export-panel" id="exportPanel">
  <h2 id="exportTitle">Export</h2>
  <pre id="exportContent"></pre>
  <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
    <button class="btn btn-primary" onclick="copyExport()">Copy to Clipboard</button>
    <button class="btn btn-secondary" onclick="closeExport()">Close</button>
  </div>
</div>

<div class="status-bar">
  <span>Right-click on mockup to add notes &middot; Toggle "Interact" to click inside mockup</span>
  <span id="noteCount">0 notes</span>
</div>

<script>
const VIEWS = ${JSON.stringify(viewData)};
const STORAGE_KEY = ${JSON.stringify(storageKey)};
let notes = {};
let activeView = VIEWS[0]?.name || "";
let ctxPos = { x: 0, y: 0, relX: 0, relY: 0 };

try {
  const saved = localStorage.getItem("mockup-notes:" + STORAGE_KEY);
  if (saved) notes = JSON.parse(saved);
} catch {}

function saveNotes() {
  localStorage.setItem("mockup-notes:" + STORAGE_KEY, JSON.stringify(notes));
  updateNoteCounts();
}

function updateNoteCounts() {
  let total = 0;
  for (const view of VIEWS) {
    const count = (notes[view.name] || []).length;
    total += count;
    const badge = document.getElementById("badge-" + view.name);
    if (badge) {
      badge.textContent = count;
      badge.style.display = count > 0 ? "flex" : "none";
    }
  }
  document.getElementById("noteCount").textContent = total + " note" + (total !== 1 ? "s" : "");
}

const tabBar = document.getElementById("tabBar");
const panels = document.getElementById("panels");

VIEWS.forEach((view, i) => {
  const tab = document.createElement("div");
  tab.className = "tab" + (i === 0 ? " active" : "");
  tab.id = "tab-" + view.name;
  tab.textContent = view.name.replace(/-/g, " ");
  tab.onclick = () => switchTab(view.name);
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.id = "badge-" + view.name;
  badge.style.display = "none";
  tab.appendChild(badge);
  tabBar.appendChild(tab);

  var panel = document.createElement("div");
  panel.className = "view-panel" + (i === 0 ? " active" : "");
  panel.id = "panel-" + view.name;

  var iframeArea = document.createElement("div");
  iframeArea.className = "iframe-area";
  iframeArea.id = "imgarea-" + view.name;

  var overlay = document.createElement("div");
  overlay.className = "click-overlay";
  overlay.id = "overlay-" + view.name;
  (function(vn) {
    overlay.oncontextmenu = function(e) { onRightClick(e, vn); };
  })(view.name);
  iframeArea.appendChild(overlay);

  if (view.htmlFile) {
    var iframe = document.createElement("iframe");
    iframe.src = view.htmlFile;
    iframeArea.appendChild(iframe);
  } else {
    var noHtml = document.createElement("div");
    noHtml.className = "no-html";
    noHtml.textContent = "No HTML file. Pull with: ./run.sh pull --project <id> --screen " + view.screenId;
    iframeArea.appendChild(noHtml);
  }

  var sidebar = document.createElement("div");
  sidebar.className = "notes-sidebar";
  sidebar.id = "sidebar-" + view.name;
  var sidebarTitle = document.createElement("h3");
  sidebarTitle.textContent = "Notes — " + view.name.replace(/-/g, " ");
  sidebar.appendChild(sidebarTitle);
  var notelist = document.createElement("div");
  notelist.id = "notelist-" + view.name;
  sidebar.appendChild(notelist);

  panel.appendChild(iframeArea);
  panel.appendChild(sidebar);
  panels.appendChild(panel);
});

function switchTab(name) {
  activeView = name;
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".view-panel").forEach(p => p.classList.remove("active"));
  document.getElementById("tab-" + name)?.classList.add("active");
  document.getElementById("panel-" + name)?.classList.add("active");
  renderNotes(name);
}

function toggleInteract(on) {
  document.querySelectorAll(".click-overlay").forEach(o => {
    o.classList.toggle("passthrough", on);
  });
}

function onRightClick(e, viewName) {
  e.preventDefault();
  activeView = viewName;
  const area = document.getElementById("imgarea-" + viewName);
  const rect = area.getBoundingClientRect();
  ctxPos = {
    x: e.clientX, y: e.clientY,
    relX: ((e.clientX - rect.left) / rect.width * 100).toFixed(1),
    relY: ((e.clientY - rect.top) / rect.height * 100).toFixed(1),
  };
  const menu = document.getElementById("ctxMenu");
  menu.style.left = e.clientX + "px";
  menu.style.top = e.clientY + "px";
  menu.classList.add("show");
}

document.addEventListener("click", () => {
  document.getElementById("ctxMenu").classList.remove("show");
});

function openNoteDialog() {
  document.getElementById("ctxMenu").classList.remove("show");
  const dlg = document.getElementById("noteDialog");
  dlg.style.left = Math.min(ctxPos.x, window.innerWidth - 340) + "px";
  dlg.style.top = Math.min(ctxPos.y, window.innerHeight - 140) + "px";
  dlg.classList.add("show");
  const input = document.getElementById("noteInput");
  input.value = "";
  input.focus();
}

function closeNoteDialog() {
  document.getElementById("noteDialog").classList.remove("show");
}

function saveNote() {
  const text = document.getElementById("noteInput").value.trim();
  if (!text) return;
  if (!notes[activeView]) notes[activeView] = [];
  notes[activeView].push({
    id: Date.now(), text,
    x: parseFloat(ctxPos.relX),
    y: parseFloat(ctxPos.relY),
  });
  saveNotes();
  renderNotes(activeView);
  closeNoteDialog();
}

document.getElementById("noteInput").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); saveNote(); }
});

function deleteNote(viewName, noteId) {
  if (!notes[viewName]) return;
  notes[viewName] = notes[viewName].filter(n => n.id !== noteId);
  saveNotes();
  renderNotes(viewName);
}

function renderNotes(viewName) {
  const list = document.getElementById("notelist-" + viewName);
  const area = document.getElementById("imgarea-" + viewName);
  if (!list || !area) return;
  area.querySelectorAll(".note-marker").forEach(m => m.remove());

  const viewNotes = notes[viewName] || [];
  if (viewNotes.length === 0) {
    list.innerHTML = '<div class="no-notes">No notes yet. Right-click on the mockup to add one.</div>';
    return;
  }

  list.innerHTML = "";
  viewNotes.forEach(function(n, i) {
    var card = document.createElement("div");
    card.className = "note-card";
    card.dataset.view = viewName;
    card.dataset.noteId = n.id;
    card.onmouseenter = function() { highlightMarker(viewName, n.id); };
    card.onmouseleave = function() { unhighlightMarker(viewName, n.id); };

    var hdr = document.createElement("div");
    hdr.className = "note-header";
    var num = document.createElement("span");
    num.className = "note-num";
    num.textContent = "#" + (i + 1);
    var del = document.createElement("span");
    del.className = "note-delete";
    del.innerHTML = "&times;";
    del.onclick = function() { deleteNote(viewName, n.id); };
    hdr.appendChild(num);
    hdr.appendChild(del);

    var txt = document.createElement("div");
    txt.className = "note-text";
    txt.textContent = n.text;
    var pos = document.createElement("div");
    pos.className = "note-pos";
    pos.textContent = n.x + "%, " + n.y + "%";

    card.appendChild(hdr);
    card.appendChild(txt);
    card.appendChild(pos);
    list.appendChild(card);

    var marker = document.createElement("div");
    marker.className = "note-marker";
    marker.id = "marker-" + viewName + "-" + n.id;
    marker.textContent = i + 1;
    marker.style.left = n.x + "%";
    marker.style.top = n.y + "%";
    marker.onclick = function() { card.scrollIntoView({ behavior: "smooth", block: "center" }); };
    area.appendChild(marker);
  });
}

function highlightMarker(viewName, noteId) {
  const m = document.getElementById("marker-" + viewName + "-" + noteId);
  if (m) m.style.background = "#7c3aed";
}
function unhighlightMarker(viewName, noteId) {
  const m = document.getElementById("marker-" + viewName + "-" + noteId);
  if (m) m.style.background = "#ff4444";
}

function copyCoords() {
  navigator.clipboard.writeText(ctxPos.relX + "%, " + ctxPos.relY + "%");
  document.getElementById("ctxMenu").classList.remove("show");
}

function escapeHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function showExport(mode) {
  const panel = document.getElementById("exportPanel");
  const titleEl = document.getElementById("exportTitle");
  const content = document.getElementById("exportContent");

  if (mode === "json") {
    titleEl.textContent = "Notes JSON";
    content.textContent = JSON.stringify(notes, null, 2);
  } else {
    titleEl.textContent = "Compiled Feedback for Stitch";
    const lines = [];
    for (const view of VIEWS) {
      const viewNotes = notes[view.name] || [];
      if (viewNotes.length === 0) continue;
      lines.push("## " + view.name.replace(/-/g, " ").toUpperCase());
      viewNotes.forEach((n, i) => {
        lines.push((i+1) + ". " + n.text + " (at " + n.x + "%, " + n.y + "%)");
      });
      lines.push("");
    }
    content.textContent = lines.length === 0
      ? "No notes to compile. Right-click on mockups to add feedback."
      : lines.join("\\n");
  }
  document.getElementById("overlay").classList.add("show");
  panel.classList.add("show");
}

function closeExport() {
  document.getElementById("overlay").classList.remove("show");
  document.getElementById("exportPanel").classList.remove("show");
}

function copyExport() {
  const text = document.getElementById("exportContent").textContent;
  navigator.clipboard.writeText(text);
  const btn = event.target;
  btn.textContent = "Copied!";
  setTimeout(() => btn.textContent = "Copy to Clipboard", 1500);
}

function clearAllNotes() {
  if (!confirm("Clear all notes across all tabs?")) return;
  notes = {};
  saveNotes();
  renderNotes(activeView);
}

updateNoteCounts();
if (VIEWS.length > 0) renderNotes(VIEWS[0].name);
</script>
</body>
</html>`;

mkdirSync(resolve(outputDir), { recursive: true });
const outPath = join(resolve(outputDir), "review.html");
writeFileSync(outPath, html);
console.log(`Review page: ${outPath}`);
console.log(`Views: ${views.length} (${viewData.filter(v => v.htmlFile).length} with HTML)`);
console.log(`Open: xdg-open ${outPath}`);
