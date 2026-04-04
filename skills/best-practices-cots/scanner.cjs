/**
 * COTS Defense UX Compliance Scanner — 100% Deterministic
 *
 * Every rule is a programmatic check via CDP. No VLM. No LLM. No subjectivity.
 * Either the UI complies or it doesn't. Numbers against thresholds.
 *
 * Standards: WCAG 2.1 AA, Section 508, MIL-STD-1472H, NIST 800-53
 */
const http = require("http");
const WebSocket = require("ws");
const fs = require("fs");
const path = require("path");

const CDP_PORT = process.env.CDP_PORT || 9222;
const CAPTURES_DIR = path.resolve(__dirname, "../../../packages/ux-lab/captures/cots");

// ── Thresholds ──────────────────────────────────────────────────────────
const MIN_FONT_PX = 12;          // MIL-STD-1472H: minimum readable text
const MIN_TOUCH_PX = 44;         // WCAG 2.1 / Apple HIG: minimum touch target
const MIN_CONTRAST = 4.5;        // WCAG 2.1 AA: normal text contrast ratio
const KNOWN_ACRONYMS = ['SPARTA', 'QRA', 'CMMC', 'NIST', 'WCAG', 'BM25', 'CWE', 'ATT&CK'];

// ── CDP connection ──────────────────────────────────────────────────────
async function connectCDP() {
  const targets = await new Promise((resolve, reject) => {
    http.get(`http://127.0.0.1:${CDP_PORT}/json`, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => resolve(JSON.parse(data)));
    }).on("error", reject);
  });
  const target = targets.find((t) => t.type === "page");
  if (!target) throw new Error("No CDP page target");
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let msgId = 1;
  const send = (method, params = {}) =>
    new Promise((resolve) => {
      const id = msgId++;
      ws.on("message", function handler(raw) {
        const msg = JSON.parse(raw);
        if (msg.id === id) { ws.removeListener("message", handler); resolve(msg.result); }
      });
      ws.send(JSON.stringify({ id, method, params }));
    });
  await new Promise((r) => ws.on("open", r));
  return { ws, send };
}

// ── Deterministic checks ────────────────────────────────────────────────

// C01: Font sizes — every text node inside [data-qid] must be >= MIN_FONT_PX
async function checkC01(send) {
  const { result } = await send("Runtime.evaluate", {
    expression: `(()=>{
      const v=[];
      document.querySelectorAll('[data-qid] *').forEach(el=>{
        if(el.children.length>0)return;
        const t=el.textContent?.trim();
        if(!t||t.length===0)return;
        const s=parseFloat(getComputedStyle(el).fontSize);
        if(s<${MIN_FONT_PX}){
          const p=el.closest('[data-qid]');
          v.push({qid:p?.getAttribute('data-qid')||'?',size:s,text:t.slice(0,40)});
        }
      });
      return v.slice(0,30);
    })()`,
    returnByValue: true,
  });
  const violations = result?.value || [];
  return { id: "C01", name: `All text >= ${MIN_FONT_PX}px`, standard: "MIL-STD-1472H", threshold: MIN_FONT_PX, unit: "px", status: violations.length === 0 ? "PASS" : "FAIL", count: violations.length, violations };
}

// C02: Touch targets — every interactive element must be >= MIN_TOUCH_PX x MIN_TOUCH_PX
async function checkC02(send) {
  const { result } = await send("Runtime.evaluate", {
    expression: `(()=>{
      const v=[];
      document.querySelectorAll('button,[role=button],a[href],input,textarea,select,[tabindex]').forEach(el=>{
        const r=el.getBoundingClientRect();
        if(r.width<=0||r.height<=0)return;
        if(r.width<${MIN_TOUCH_PX}||r.height<${MIN_TOUCH_PX}){
          const qid=el.getAttribute('data-qid')||el.tagName.toLowerCase();
          v.push({qid,w:Math.round(r.width),h:Math.round(r.height),text:el.textContent?.trim().slice(0,30)||''});
        }
      });
      return v.slice(0,30);
    })()`,
    returnByValue: true,
  });
  const violations = result?.value || [];
  return { id: "C02", name: `Touch targets >= ${MIN_TOUCH_PX}x${MIN_TOUCH_PX}px`, standard: "WCAG 2.1", threshold: MIN_TOUCH_PX, unit: "px", status: violations.length === 0 ? "PASS" : "FAIL", count: violations.length, violations };
}

// C03: Color contrast — sample foreground/background on key elements
async function checkC03(send) {
  const { result } = await send("Runtime.evaluate", {
    expression: `(()=>{
      function luminance(r,g,b){
        const a=[r,g,b].map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);});
        return 0.2126*a[0]+0.7152*a[1]+0.0722*a[2];
      }
      function contrast(fg,bg){
        const l1=Math.max(fg,bg),l2=Math.min(fg,bg);
        return(l1+0.05)/(l2+0.05);
      }
      function parseColor(c){
        const m=c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
        return m?[+m[1],+m[2],+m[3]]:null;
      }
      const v=[];
      document.querySelectorAll('[data-qid] *').forEach(el=>{
        if(el.children.length>0)return;
        const t=el.textContent?.trim();
        if(!t||t.length===0)return;
        const s=getComputedStyle(el);
        const fg=parseColor(s.color);
        // Walk up DOM to find actual rendered background (skip transparent/near-transparent)
        let bgEl=el;
        let bg=null;
        for(let depth=0;depth<20&&bgEl&&!bg;depth++){
          const bgc=getComputedStyle(bgEl).backgroundColor;
          // Parse rgba — skip if alpha < 0.5 (transparent/semi-transparent)
          const m4=bgc.match(/rgba\\((\\d+),\\s*(\\d+),\\s*(\\d+),\\s*([\\d.]+)/);
          if(m4&&parseFloat(m4[4])>=0.5){ bg=[+m4[1],+m4[2],+m4[3]]; break; }
          // Parse rgb (no alpha = fully opaque)
          const m3=bgc.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
          if(m3&&!(+m3[1]===0&&+m3[2]===0&&+m3[3]===0)){ bg=[+m3[1],+m3[2],+m3[3]]; break; }
          bgEl=bgEl.parentElement;
        }
        if(!bg) bg=[20,20,20]; // fallback: dark page background
        if(!fg||!bg)return;
        const ratio=contrast(luminance(...fg),luminance(...bg));
        if(ratio<${MIN_CONTRAST}){
          const p=el.closest('[data-qid]');
          v.push({qid:p?.getAttribute('data-qid')||'?',ratio:Math.round(ratio*10)/10,fg:s.color,bg:s.backgroundColor,text:t.slice(0,30)});
        }
      });
      return v.slice(0,20);
    })()`,
    returnByValue: true,
  });
  const violations = result?.value || [];
  return { id: "C03", name: `Color contrast >= ${MIN_CONTRAST}:1`, standard: "WCAG 2.1 AA", threshold: MIN_CONTRAST, unit: ":1", status: violations.length === 0 ? "PASS" : "FAIL", count: violations.length, violations };
}

// C04: Color not sole carrier — every status indicator must have text/icon + color
async function checkC04(send) {
  const { result } = await send("Runtime.evaluate", {
    expression: `(()=>{
      const v=[];
      document.querySelectorAll('[data-qid] span, [data-qid] div').forEach(el=>{
        const s=getComputedStyle(el);
        const hasColor=s.color!=='rgb(226, 232, 240)'&&s.color!=='rgb(100, 116, 139)';
        const hasText=el.textContent?.trim().length>0;
        const hasBg=s.backgroundColor!=='rgba(0, 0, 0, 0)';
        // Only flag if element uses color but has no text content (pure color indicator)
        if(hasColor&&!hasText&&(el.clientWidth<20||el.clientHeight<20)){
          const p=el.closest('[data-qid]');
          v.push({qid:p?.getAttribute('data-qid')||'?',color:s.color,size:el.clientWidth+'x'+el.clientHeight});
        }
      });
      return v.slice(0,10);
    })()`,
    returnByValue: true,
  });
  const violations = result?.value || [];
  return { id: "C04", name: "Color not sole information carrier", standard: "WCAG 2.1", status: violations.length === 0 ? "PASS" : "WARN", count: violations.length, violations };
}

// C07: Acronyms defined — check if known acronyms have expansion visible
async function checkC07(send) {
  const acronyms = KNOWN_ACRONYMS;
  const { result } = await send("Runtime.evaluate", {
    expression: `(()=>{
      const text=document.body.textContent||'';
      const missing=[];
      ${JSON.stringify(acronyms)}.forEach(a=>{
        if(text.includes(a)){
          // Check if expansion exists (e.g., "SPARTA = Space Attack..." or title attribute)
          const expanded=text.includes(a+' =') || text.includes(a+' —') || text.includes(a+' (');
          const hasTitle=!!document.querySelector('[title*="'+a+'"]');
          if(!expanded&&!hasTitle) missing.push(a);
        }
      });
      return missing;
    })()`,
    returnByValue: true,
  });
  const missing = result?.value || [];
  return { id: "C07", name: "Acronyms expanded or defined", standard: "MIL-STD-1472H", status: missing.length === 0 ? "PASS" : "FAIL", count: missing.length, violations: missing.map(a => ({ acronym: a, detail: "Used but not expanded or defined via title attribute" })) };
}

// C08: Metrics labeled — every number displayed must have adjacent label
async function checkC08(send) {
  const { result } = await send("Runtime.evaluate", {
    expression: `(()=>{
      const v=[];
      document.querySelectorAll('[data-qid] span, [data-qid] div').forEach(el=>{
        if(el.children.length>0)return;
        const t=el.textContent?.trim()||'';
        // Match bare numbers like "91%" or "1.2s" or "3200"
        if(/^\\d+(\\.\\d+)?(%|ms|s|px)?$/.test(t)){
          // Check if parent or sibling has a label
          const parent=el.parentElement;
          const siblings=parent?Array.from(parent.children).map(c=>c.textContent?.trim()||'').join(' '):'';
          const hasLabel=/conf|step|elapsed|duration|score|items|results|rows|confidence/i.test(siblings+' '+(el.getAttribute('title')||''));
          if(!hasLabel){
            const p=el.closest('[data-qid]');
            v.push({qid:p?.getAttribute('data-qid')||'?',value:t,context:siblings.slice(0,60)});
          }
        }
      });
      return v.slice(0,15);
    })()`,
    returnByValue: true,
  });
  const violations = result?.value || [];
  return { id: "C08", name: "Metrics labeled with units/definition", standard: "MIL-STD-1472H", status: violations.length === 0 ? "PASS" : "WARN", count: violations.length, violations };
}

// C12: Audit trail — check for user, session, timestamp elements
async function checkC12(send) {
  const { result } = await send("Runtime.evaluate", {
    expression: `(()=>{
      const text=document.body.textContent||'';
      const checks={
        user: /user:\\s*\\w+/.test(text),
        session: /session:\\s*\\S+/.test(text),
        timestamp: /\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}/.test(text),
        agent: /agent:\\s*\\w+/.test(text),
      };
      const missing=Object.entries(checks).filter(([,v])=>!v).map(([k])=>k);
      return {checks,missing};
    })()`,
    returnByValue: true,
  });
  const data = result?.value || { checks: {}, missing: ["user", "session", "timestamp", "agent"] };
  return { id: "C12", name: "Audit trail: user, session, timestamp, agent", standard: "NIST 800-53 AU-2", status: data.missing.length === 0 ? "PASS" : "FAIL", count: data.missing.length, violations: data.missing.map(f => ({ field: f, detail: `${f} not found in page content` })), checks: data.checks };
}

// C14: Tooltips — every interactive element must have title or aria-label
async function checkC14(send) {
  const { result } = await send("Runtime.evaluate", {
    expression: `(()=>{
      const v=[];
      document.querySelectorAll('button,[role=button],[data-qid] span[style*=cursor]').forEach(el=>{
        if(!el.getAttribute('title')&&!el.getAttribute('aria-label')){
          const qid=el.getAttribute('data-qid')||el.closest('[data-qid]')?.getAttribute('data-qid')||'?';
          v.push({qid,tag:el.tagName.toLowerCase(),text:el.textContent?.trim().slice(0,30)||''});
        }
      });
      return v.slice(0,20);
    })()`,
    returnByValue: true,
  });
  const violations = result?.value || [];
  return { id: "C14", name: "Tooltips on all interactive elements", standard: "MIL-STD-1472H", status: violations.length === 0 ? "PASS" : "FAIL", count: violations.length, violations };
}

// C05: Keyboard navigation — Tab through elements, count reachable
async function checkC05(send) {
  const { result } = await send("Runtime.evaluate", {
    expression: `(()=>{
      const interactive=document.querySelectorAll('button,a[href],input,textarea,select,[tabindex],[role=button]');
      const total=interactive.length;
      let reachable=0;
      interactive.forEach(el=>{
        const ti=el.getAttribute('tabindex');
        if(ti!=='-1'&&!el.disabled&&el.offsetParent!==null) reachable++;
      });
      return {total,reachable,unreachable:total-reachable};
    })()`,
    returnByValue: true,
  });
  const data = result?.value || { total: 0, reachable: 0, unreachable: 0 };
  return { id: "C05", name: "Keyboard navigable (no tabindex=-1 on visible interactive)", standard: "Section 508", status: data.unreachable === 0 ? "PASS" : "WARN", count: data.unreachable, detail: `${data.reachable}/${data.total} reachable via Tab` };
}

// ── Main scanner ────────────────────────────────────────────────────────

async function scan(url, options = {}) {
  fs.mkdirSync(CAPTURES_DIR, { recursive: true });
  const rulesFilter = options.rules ? options.rules.split(",") : null;
  const ignoreRules = options.ignore ? new Set(options.ignore.split(",")) : new Set();
  const scopePrefix = options.scope || null; // e.g., "reasoning-chain,chat:,topbar:,input:,sidebar:"

  console.log("");
  console.log("  ╔══════════════════════════════════════════════════════╗");
  console.log("  ║  COTS Compliance Scanner (Deterministic)            ║");
  console.log("  ╠══════════════════════════════════════════════════════╣");
  console.log(`  ║  URL: ${url.slice(0, 48).padEnd(48)} ║`);
  console.log(`  ║  Rules: ${(rulesFilter ? rulesFilter.join(", ") : "ALL").padEnd(46)} ║`);
  if (ignoreRules.size > 0) console.log(`  ║  Ignore: ${[...ignoreRules].join(", ").padEnd(44)} ║`);
  if (scopePrefix) console.log(`  ║  Scope: ${scopePrefix.slice(0, 45).padEnd(45)} ║`);
  console.log("  ╚══════════════════════════════════════════════════════╝");
  console.log("");

  const { ws, send } = await connectCDP();

  // Navigate + setup
  await send("Page.navigate", { url });
  await new Promise((r) => setTimeout(r, 3000));
  await send("Runtime.evaluate", { expression: 'document.querySelector("[data-testid=tab-final-site]")?.click()' });
  await new Promise((r) => setTimeout(r, 8000));

  // Expand reasoning chain for C07/C12 checks — retry until height > 100
  for (let attempt = 0; attempt < 5; attempt++) {
    await send("Runtime.evaluate", { expression: 'document.querySelector("[data-qid=reasoning-chain-summary]")?.click()' });
    await new Promise((r) => setTimeout(r, 1500));
    const { result: h } = await send("Runtime.evaluate", {
      expression: 'document.querySelector("[data-qid=reasoning-chain]")?.getBoundingClientRect()?.height || 0',
      returnByValue: true,
    });
    if (h?.value > 100) break;
    await new Promise((r) => setTimeout(r, 2000));
  }

  // Run all checks
  const checks = [checkC01, checkC02, checkC03, checkC04, checkC05, checkC07, checkC08, checkC12, checkC14];
  const results = {};

  for (const check of checks) {
    const result = await check(send);
    // Skip ignored rules
    if (ignoreRules.has(result.id)) {
      result.status = "SKIP";
      results[result.id] = result;
      console.log(`  \x1b[90m⊘\x1b[0m  ${result.id} ${result.name.padEnd(50)} SKIP (ignored)`);
      continue;
    }
    if (rulesFilter && !rulesFilter.includes(result.id)) continue;
    // Scope filtering — remove violations from elements outside scope
    if (scopePrefix && result.violations) {
      const prefixes = scopePrefix.split(",");
      result.violations = result.violations.filter((v) => {
        const qid = v.qid || v.field || "";
        if (qid === "?" || qid === "") return false; // exclude unscoped elements
        return prefixes.some((p) => qid.startsWith(p));
      });
      result.count = result.violations.length;
      result.status = result.count === 0 ? "PASS" : result.status;
    }
    results[result.id] = result;
    const icon = result.status === "PASS" ? "✓" : result.status === "WARN" ? "⚠" : "✗";
    const color = result.status === "PASS" ? "\x1b[32m" : result.status === "WARN" ? "\x1b[33m" : "\x1b[31m";
    console.log(`  ${color}${icon}\x1b[0m  ${result.id} ${result.name.padEnd(50)} ${result.status} (${result.count || 0})`);
    if (result.status !== "PASS" && result.status !== "SKIP" && result.violations) {
      result.violations.slice(0, 3).forEach((v) => {
        const detail = v.qid || v.acronym || v.field || JSON.stringify(v);
        console.log(`     → ${typeof detail === 'string' ? detail.slice(0, 70) : detail}`);
      });
    }
  }

  ws.close();

  // Summary
  const counts = { PASS: 0, WARN: 0, FAIL: 0, SKIP: 0 };
  for (const r of Object.values(results)) counts[r.status] = (counts[r.status] || 0) + 1;
  const total = Object.keys(results).length;
  const checked = total - (counts.SKIP || 0);

  console.log("");
  console.log("  ════════════════════════════════════════════════════════");
  console.log(`  PASS: ${counts.PASS}/${checked}  WARN: ${counts.WARN}/${checked}  FAIL: ${counts.FAIL}/${checked}${counts.SKIP ? `  SKIP: ${counts.SKIP}` : ""}`);
  console.log(`  Compliance: ${counts.FAIL === 0 ? "✅ COMPLIANT" : "❌ NON-COMPLIANT"} (${counts.FAIL} blocking violations)`);
  console.log("  ════════════════════════════════════════════════════════");
  console.log("");

  // Save report
  const report = { url, date: new Date().toISOString(), results, summary: counts, compliant: counts.FAIL === 0 };
  const reportPath = path.join(CAPTURES_DIR, "cots-report.json");
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`  Report: ${reportPath}`);

  // Generate plan if requested
  if (options.plan && counts.FAIL > 0) {
    const failures = Object.values(results).filter((r) => r.status === "FAIL");
    const planPath = path.join(CAPTURES_DIR, "cots-fixes.json");
    const tasks = failures.map((f, i) => ({
      id: String(i + 1),
      title: `Fix ${f.id}: ${f.name}`,
      violations: f.violations?.slice(0, 5),
      definition_of_done: `./run.sh scan ${url} --rules ${f.id} → PASS`,
    }));
    fs.writeFileSync(planPath, JSON.stringify({ fixes: tasks }, null, 2));
    console.log(`  Fix plan: ${planPath}`);
  }

  if (options.json) console.log(JSON.stringify(report, null, 2));
  return report;
}

// ── CLI ─────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const url = args[0];
if (!url) { console.error("Usage: scanner.cjs <url> [--plan] [--rules C01,C02] [--json]"); process.exit(1); }

const options = {};
for (let i = 1; i < args.length; i++) {
  if (args[i] === "--plan") options.plan = true;
  if (args[i] === "--rules") options.rules = args[++i];
  if (args[i] === "--ignore") options.ignore = args[++i];
  if (args[i] === "--json") options.json = true;
  if (args[i] === "--scope") options.scope = args[++i]; // filter violations to specific qid prefix
}

scan(url, options)
  .then((r) => process.exit(r.compliant ? 0 : 1))
  .catch((e) => { console.error(e.message); process.exit(2); });
