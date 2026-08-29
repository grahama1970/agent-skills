#!/usr/bin/env node
// Deterministic eval-guard checker. Judges an assistant's final message plus
// optional evidence files; the model never judges itself. Output is a strict
// triage-style verdict: {ok, violations:[{code, cause, next_command}]}.
//
//   node checker.mjs --message-file <txt> [--report <agentic-evals-report.json>]
//                    [--skill-dir <path>] [--catalog <failure_codes.json>]
//                    [--max-report-age-hours N]
//
// Violation codes (stable, catalog-style):
//   completion_claim_without_eval_receipt
//   eval_receipt_not_ready | eval_receipt_wrong_skill | eval_receipt_stale
//   eval_receipt_unit_only
//   failure_without_triage_code | triage_code_not_in_catalog
//   proof_laundering_git
import { readFileSync, statSync, existsSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { createHash } from "node:crypto";

const COMPLETION_CLAIMS = [
  /\b(feature|fix|change|skill|pipeline|extension|bridge|command) (now )?works\b/i,
  /\bworks as expected\b/i,
  /\b(fully|successfully) (implemented|working|verified|tested)\b/i,
  /\b(is|are) (complete|done|finished|ready|production.ready)\b/i,
  /\ball (tests|checks|cases) pass(ing|ed)?\b/i,
  /\bverified\b/i,
];
const FAILURE_MARKERS = [
  /\bfail(ed|ure|s)?\b/i,
  /\berror(s)?:\b/i,
  /\bexit(ed)? (code )?[1-9]\b/i,
  /\bblocked\b/i,
  /\btraceback\b/i,
  /\btimed? ?out\b/i,
];
const GIT_LAUNDERING = [
  /\b(committed|pushed|merged)\b/i,
  /\bbranch (is )?updated\b/i,
  /\b[0-9a-f]{10,40}\b/,
];
const UNIT_RUNNER = /\b(npm test|pytest|node --test|vitest|cargo test|go test|unittest)\b/;
// Evidence that a command drives a production surface, not just a test runner.
const PROD_MARKER = /(run\.sh|[a-z0-9-]+-cli(\.mjs)?|curl |https?:\/\/|\.\/[a-z0-9_-]+\.(mjs|py|sh)|evals\/)/;
const TRIAGE_LINE = /^\s*Triage:\s*([a-z0-9_]+)\s*$/m;
const CLAIM_EXEMPT = /\b(unverified|not verified|unproven|needs verification|claim withheld)\b/i;

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith("--")) {
      const key = argv[i].slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith("--")) { args[key] = next; i++; }
      else args[key] = true;
    }
  }
  return args;
}

function newestMtimeMs(dir) {
  let newest = 0;
  const walk = (d) => {
    for (const entry of readdirSync(d, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      const p = join(d, entry.name);
      if (entry.isDirectory()) walk(p);
      else {
        const m = statSync(p).mtimeMs;
        if (m > newest) newest = m;
      }
    }
  };
  walk(dir);
  return newest;
}

export function check({ message, report, reportMtimeMs, fixture, skillFixtureSha, skillDirNewestMtimeMs, catalogCodes, maxReportAgeHours = 24 }) {
  const violations = [];
  const push = (code, cause, next_command) => violations.push({ code, cause, next_command });

  const claims = COMPLETION_CLAIMS.some((r) => r.test(message)) && !CLAIM_EXEMPT.test(message);
  const failing = FAILURE_MARKERS.some((r) => r.test(message));

  if (claims) {
    if (!report) {
      push(
        "completion_claim_without_eval_receipt",
        "message claims the feature works/complete but no agentic-evals report was provided",
        "run /agentic-evals on the owning skill, save the report JSON, and re-report with the receipt (or downgrade the claim to unverified)",
      );
      if (GIT_LAUNDERING.some((r) => r.test(message))) {
        push(
          "proof_laundering_git",
          "git activity (committed/pushed/SHA) is presented alongside a works-claim with no eval receipt",
          "git metadata is retention, not proof; attach the agentic-evals receipt for the claim",
        );
      }
    } else {
      if (report.schema !== "agentic_evals.report.v2") {
        push("completion_claim_without_eval_receipt", `report schema is ${report.schema}, not agentic_evals.report.v2`, "re-run /agentic-evals and save its JSON output");
      }
      if (report.readiness !== "READY") {
        push("eval_receipt_not_ready", `report readiness is ${report.readiness}`, "fix the failing cases and re-run /agentic-evals until READY, or report the failure with a Triage: code");
      }
      if (skillFixtureSha && report.fixture_sha256 && report.fixture_sha256 !== skillFixtureSha) {
        push("eval_receipt_wrong_skill", `report fixture_sha256 ${report.fixture_sha256} does not match the skill's current fixtures/agentic_eval.json (${skillFixtureSha})`, "run /agentic-evals against the owning skill's current fixture");
      }
      if (skillDirNewestMtimeMs && reportMtimeMs && reportMtimeMs < skillDirNewestMtimeMs) {
        push("eval_receipt_stale", "the skill changed after the eval report was generated", "re-run /agentic-evals so the receipt covers the current code");
      }
      if (reportMtimeMs && Date.now() - reportMtimeMs > maxReportAgeHours * 3600 * 1000) {
        push("eval_receipt_stale", `report is older than ${maxReportAgeHours}h`, "re-run /agentic-evals for a fresh receipt");
      }
      if (fixture) {
        // A case counts as real-world when marked real_world AND its command
        // touches a production surface — a command may run unit tests AND the
        // production path; only pure test-runner commands are disqualified.
        const realWorld = (fixture.cases ?? []).some((c) => {
          const cmd = (c.command ?? []).join(" ");
          return c.real_world === true && (PROD_MARKER.test(cmd) || !UNIT_RUNNER.test(cmd));
        });
        if (!realWorld) {
          push(
            "eval_receipt_unit_only",
            "the eval fixture has no real_world case beyond unit-test runners; unit tests cannot prove a feature works",
            "add a real_world case that drives the production entrypoint (run.sh, CLI, live endpoint, artifact read-back) and re-run /agentic-evals",
          );
        }
      }
    }
  }

  if (failing && !claims) {
    const m = message.match(TRIAGE_LINE);
    if (!m) {
      push(
        "failure_without_triage_code",
        "failure is reported in ambiguous prose with no `Triage: <code>` line",
        "run triage-error: skills/triage-error/run.sh classify --text \"<exact error>\" and include `Triage: <code>` in the report",
      );
    } else if (catalogCodes && catalogCodes.length > 0) {
      const code = m[1];
      const known = catalogCodes.includes(code) || code.includes("_unclassified_");
      if (!known) {
        push(
          "triage_code_not_in_catalog",
          `Triage code ${code} is not in failure_codes.json and is not a minted *_unclassified_* code`,
          "use skills/triage-error/run.sh classify to get a canonical code, or triage to mint one",
        );
      }
    }
  }

  return { ok: violations.length === 0, violations };
}

const isMain = process.argv[1] && resolve(process.argv[1]) === resolve(new URL(import.meta.url).pathname);
if (isMain) {
  const args = parseArgs(process.argv.slice(2));
  if (!args["message-file"]) {
    process.stderr.write("usage: checker.mjs --message-file <txt> [--report <json>] [--skill-dir <path>] [--catalog <failure_codes.json>]\n");
    process.exit(2);
  }
  const message = readFileSync(args["message-file"], "utf-8");
  let report = null;
  let reportMtimeMs = null;
  let fixture = null;
  if (args.report && existsSync(args.report)) {
    report = JSON.parse(readFileSync(args.report, "utf-8"));
    reportMtimeMs = statSync(args.report).mtimeMs;
    const src = report.source && args["skill-dir"] ? join(args["skill-dir"], String(report.source).replace(/^\.\.\//, "")) : report.source;
    for (const candidate of [src, report.source, args["skill-dir"] ? join(args["skill-dir"], "fixtures/agentic_eval.json") : null]) {
      if (candidate && existsSync(candidate)) {
        fixture = JSON.parse(readFileSync(candidate, "utf-8"));
        break;
      }
    }
  }
  const skillDir = args["skill-dir"] ? resolve(args["skill-dir"]) : null;
  const catalogPath = args.catalog
    || join(new URL(".", import.meta.url).pathname, "..", "triage-error", "failure_codes.json");
  let catalogCodes = null;
  if (existsSync(catalogPath)) {
    const catalog = JSON.parse(readFileSync(catalogPath, "utf-8"));
    const entries = Array.isArray(catalog) ? catalog : catalog.codes ?? Object.values(catalog);
    catalogCodes = entries.map((e) => e.code ?? e).filter((c) => typeof c === "string");
  }
  let skillFixtureSha = null;
  if (skillDir) {
    const fixturePath = join(skillDir, "fixtures/agentic_eval.json");
    if (existsSync(fixturePath)) {
      skillFixtureSha = "sha256:" + createHash("sha256").update(readFileSync(fixturePath)).digest("hex");
      if (!fixture) fixture = JSON.parse(readFileSync(fixturePath, "utf-8"));
    }
  }
  const verdict = check({
    message,
    report,
    reportMtimeMs,
    fixture,
    skillFixtureSha,
    skillDirNewestMtimeMs: skillDir && existsSync(skillDir) ? newestMtimeMs(skillDir) : null,
    catalogCodes,
    maxReportAgeHours: args["max-report-age-hours"] ? Number(args["max-report-age-hours"]) : 24,
  });
  process.stdout.write(JSON.stringify(verdict, null, 2) + "\n");
  process.exit(verdict.ok ? 0 : 1);
}
