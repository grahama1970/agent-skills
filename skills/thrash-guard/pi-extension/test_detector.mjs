// Deterministic proof of the thrash detector against real patterns from the
// 2026 cockpit-click session. Run: node test_detector.mjs
import { ThrashDetector, isDiagnosticCall, normalizeSignature } from "./detector.mjs";
import assert from "node:assert";

// 1. Repetition thrash: surf click/js retried with different coords/selectors,
//    all returning OK (isError=false) but changing nothing — the exact pattern
//    that isError-only detection would MISS.
{
  const d = new ThrashDetector({ window: 6, threshold: 3 });
  const calls = [
    { t: "bash", i: { command: "skills/surf/run.sh click [data-qid=cockpit:diagram:node:publish-report] --tab-id 837439619" } },
    { t: "bash", i: { command: "skills/surf/run.sh click [data-qid=cockpit:diagram:node-list] [data-qid=cockpit:diagram:node:publish-report] --tab-id 837439620" } },
    { t: "bash", i: { command: "skills/surf/run.sh click button[data-qs-action=COCKPIT_DIAGRAM_STEP_3] --tab-id 837439621" } },
  ];
  let blocked = null;
  for (const c of calls) {
    d.recordResult(false); // surf returned OK each time
    blocked = d.inspectCall(c.t, c.i);
  }
  assert.ok(blocked?.block, "repetition thrash should block the 3rd near-duplicate surf call");
  assert.match(blocked.reason, /triage-error/, "reason must point at triage-error");
}

// 2. Error thrash: 3 real tool errors in the window engages the lock.
{
  const d = new ThrashDetector({ window: 6, threshold: 3 });
  d.recordResult(true);
  d.recordResult(true);
  d.recordResult(true);
  const v = d.inspectCall("edit", { path: "/x/y.py" });
  assert.ok(v?.block, "3 errors should block the next mutating call");
}

// 3. A diagnostic call (triage-error classify) CLEARS the lock.
{
  const d = new ThrashDetector({ window: 6, threshold: 3 });
  d.recordResult(true); d.recordResult(true); d.recordResult(true);
  assert.ok(d.inspectCall("bash", { command: "echo x" })?.block, "locked");
  const cleared = d.inspectCall("bash", {
    command: 'skills/triage-error/run.sh classify --text "reads work but clicks do nothing" --layer surf',
  });
  assert.ok(cleared?.cleared, "triage-error classify clears the lock");
  assert.equal(d.inspectCall("edit", { path: "/x/y.py" }), null, "mutating allowed after diagnosis");
}

// 4. web_search also clears; reads are never blocked.
{
  const d = new ThrashDetector({ window: 6, threshold: 3 });
  d.recordResult(true); d.recordResult(true); d.recordResult(true);
  assert.equal(d.inspectCall("read", { path: "/a" }), null, "reads never blocked");
  assert.ok(d.inspectCall("bash", { command: "echo y" })?.block, "still locked for mutating");
  assert.ok(d.inspectCall("web_search", { query: "vite preview POST" })?.cleared, "web_search clears");
}

// 5. isDiagnosticCall / normalizeSignature sanity.
assert.ok(isDiagnosticCall("web_search", {}));
assert.ok(isDiagnosticCall("bash", { command: "x/triage-error/run.sh triage --text z" }));
assert.ok(!isDiagnosticCall("bash", { command: "git commit" }));
assert.equal(
  normalizeSignature("bash", { command: "surf click  X --tab-id 999" }),
  normalizeSignature("bash", { command: "surf click X --tab-id 111" }),
  "digits/whitespace normalized so retries collapse to one signature",
);

console.log("THRASH_GUARD_DETECTOR_OK");
