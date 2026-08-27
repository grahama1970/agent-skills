#!/usr/bin/env node
// Validate receipt bindings for unlazy-backed agent workflows.
// This is intentionally a narrow, deterministic validator. It does not run
// gates and it does not judge semantic correctness.

import { existsSync, lstatSync, readFileSync, realpathSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, isAbsolute, resolve, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = resolve(HERE, "..");

function usage() {
  console.error("Usage: receipt-check [--project-root DIR] [--json] RECEIPT.json");
}

function sha256File(path) {
  return "sha256:" + createHash("sha256").update(readFileSync(path)).digest("hex");
}

function sha256Text(value) {
  return "sha256:" + createHash("sha256").update(String(value)).digest("hex");
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new Error(path + ": invalid JSON: " + error.message);
  }
}

function inside(child, root) {
  const rel = relative(root, child);
  return rel === "" || (!!rel && !rel.startsWith("..") && !isAbsolute(rel));
}

function resolveProjectPath(projectRoot, value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(label + " must be a non-empty project-relative path");
  }
  if (value.includes("\0") || isAbsolute(value) || /^[A-Za-z]:[\\/]/.test(value)) {
    throw new Error(label + " must be project-relative: " + value);
  }
  const parts = value.replace(/\\/g, "/").split("/");
  if (parts.some((part) => part === "..")) {
    throw new Error(label + " cannot contain traversal: " + value);
  }
  const resolved = resolve(projectRoot, value);
  if (!inside(resolved, projectRoot)) throw new Error(label + " escapes project root: " + value);
  if (!existsSync(resolved)) throw new Error(label + " does not exist: " + value);
  const real = realpathSync(resolved);
  if (!inside(real, projectRoot)) throw new Error(label + " resolves outside project root: " + value);
  return resolved;
}

function validateSha(value, label) {
  if (typeof value !== "string" || !/^sha256:[0-9a-f]{64}$/i.test(value)) {
    throw new Error(label + " must be sha256:<64 hex>");
  }
}

function validatePathHashRef(projectRoot, ref, label) {
  if (!ref || typeof ref !== "object" || Array.isArray(ref)) {
    throw new Error(label + " must be an object");
  }
  const path = resolveProjectPath(projectRoot, ref.path, label + ".path");
  validateSha(ref.sha256, label + ".sha256");
  const actual = sha256File(path);
  if (actual.toLowerCase() !== ref.sha256.toLowerCase()) {
    throw new Error(label + " hash mismatch for " + ref.path + ": expected " + ref.sha256 + " got " + actual);
  }
  return path;
}

function validateAcceptanceRef(projectRoot, ref, errors, prefix = "acceptance_ref") {
  try {
    if (!ref || typeof ref !== "object" || Array.isArray(ref)) throw new Error(prefix + " must be an object");
    if (ref.schema !== "unlazy.acceptance_ref.v1") throw new Error(prefix + ".schema must be unlazy.acceptance_ref.v1");

    const goalPath = resolveProjectPath(projectRoot, ref.goal_path, prefix + ".goal_path");
    validateSha(ref.goal_sha256, prefix + ".goal_sha256");
    const goalHash = sha256File(goalPath);
    if (goalHash.toLowerCase() !== ref.goal_sha256.toLowerCase()) {
      throw new Error(prefix + " goal hash mismatch: expected " + ref.goal_sha256 + " got " + goalHash);
    }

    const ledgerPath = resolveProjectPath(projectRoot, ref.ledger_path, prefix + ".ledger_path");
    validateSha(ref.ledger_sha256, prefix + ".ledger_sha256");
    const ledgerHash = sha256File(ledgerPath);
    if (ledgerHash.toLowerCase() !== ref.ledger_sha256.toLowerCase()) {
      throw new Error(prefix + " ledger hash mismatch: expected " + ref.ledger_sha256 + " got " + ledgerHash);
    }

    if (ref.lock_path !== undefined || ref.lock_sha256 !== undefined) {
      const lockPath = resolveProjectPath(projectRoot, ref.lock_path, prefix + ".lock_path");
      validateSha(ref.lock_sha256, prefix + ".lock_sha256");
      const lockHash = sha256File(lockPath);
      if (lockHash.toLowerCase() !== ref.lock_sha256.toLowerCase()) {
        throw new Error(prefix + " lock hash mismatch: expected " + ref.lock_sha256 + " got " + lockHash);
      }
    }

    if (ref.required_gate_ids !== undefined) {
      if (!Array.isArray(ref.required_gate_ids) || ref.required_gate_ids.some((id) => typeof id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(id))) {
        throw new Error(prefix + ".required_gate_ids must be an array of gate IDs");
      }
    }
  } catch (error) {
    errors.push(error.message);
  }
}

const GLOBAL_COMPLETION_SCHEMAS = new Set([
  "project_watchdog.goal_completion.v1",
]);

function scanForbiddenCompletionClaims(value, errors, path = "$", schema = null) {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) {
    value.forEach((item, index) => scanForbiddenCompletionClaims(item, errors, path + "[" + index + "]", schema));
    return;
  }
  for (const [key, field] of Object.entries(value)) {
    const next = path + "." + key;
    if (/^(global_goal_state|immutable_goal_state|goal_state)$/i.test(key) && typeof field === "string") {
      if (/^(ACHIEVED|ACHIEVED_WITH_RECEIPT|DONE_WITH_RECEIPT|COMPLETE|COMPLETED)$/i.test(field) &&
          !GLOBAL_COMPLETION_SCHEMAS.has(schema)) {
        errors.push(next + " claims global completion but schema " + (schema || "(missing)") + " is not an authorized completion schema");
      }
    }
    scanForbiddenCompletionClaims(field, errors, next, schema);
  }
}

function scanHashRefs(projectRoot, value, errors, path = "$") {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) {
    value.forEach((item, index) => scanHashRefs(projectRoot, item, errors, path + "[" + index + "]"));
    return;
  }
  if (typeof value.path === "string" && typeof value.sha256 === "string") {
    try { validatePathHashRef(projectRoot, value, path); }
    catch (error) { errors.push(error.message); }
  }
  for (const [key, field] of Object.entries(value)) {
    if (key === "acceptance_ref") continue;
    scanHashRefs(projectRoot, field, errors, path + "." + key);
  }
}

function main(argv) {
  let projectRoot = process.cwd();
  let json = false;
  const files = [];
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--project-root") {
      projectRoot = argv[++index];
      if (!projectRoot) throw new Error("--project-root needs a directory");
    } else if (arg === "--json") {
      json = true;
    } else if (arg === "--help" || arg === "-h") {
      usage();
      process.exit(0);
    } else if (arg.startsWith("--")) {
      throw new Error("unknown option " + arg);
    } else {
      files.push(arg);
    }
  }
  if (files.length !== 1) throw new Error("expected exactly one receipt file");

  projectRoot = realpathSync(resolve(projectRoot));
  const receiptPath = resolve(process.cwd(), files[0]);
  if (!inside(receiptPath, projectRoot)) throw new Error("receipt path escapes project root: " + files[0]);
  const receiptReal = realpathSync(receiptPath);
  if (!inside(receiptReal, projectRoot)) throw new Error("receipt realpath escapes project root: " + files[0]);
  if (!statSync(receiptPath).isFile() || lstatSync(receiptPath).isSymbolicLink()) {
    throw new Error("receipt must be a regular non-symlink file");
  }

  const receipt = readJson(receiptPath);
  const errors = [];
  const schema = receipt && receipt.schema;
  if (typeof schema !== "string" || !schema) errors.push("receipt.schema must be non-empty");
  validateAcceptanceRef(projectRoot, receipt.acceptance_ref, errors);
  scanForbiddenCompletionClaims(receipt, errors, "$", schema);
  scanHashRefs(projectRoot, receipt, errors);

  const report = {
    schema: "unlazy.receipt_check.v1",
    status: errors.length ? "FAIL" : "PASS",
    ok: errors.length === 0,
    live: false,
    mocked: false,
    project_root: projectRoot,
    receipt_path: receiptPath,
    receipt_sha256: sha256File(receiptPath),
    receipt_schema: schema || null,
    errors,
    seam_validation: {
      kind: "unlazy.receipt_check.v1",
      status: errors.length ? "FAIL" : "PASS",
    },
    proof_scope: {
      proves: [
        "receipt is readable JSON",
        "receipt and referenced artifacts resolve inside the project root",
        "acceptance_ref goal, ledger, and optional lock hashes match current files",
        "non-watchdog receipts do not claim global immutable-goal completion",
      ],
      does_not_prove: [
        "gate commands were executed",
        "receipt producer is trustworthy",
        "semantic correctness of the referenced workflow",
        "downstream Herdr, Tau, ticket, or project-watchdog integration is installed",
      ],
    },
  };
  if (json) console.log(JSON.stringify(report, null, 2));
  else if (report.ok) console.log("RECEIPT_CHECK_OK " + receiptPath);
  else console.error("RECEIPT_CHECK_FAILED " + errors.join("; "));
  return report.ok ? 0 : 1;
}

try {
  process.exit(main(process.argv.slice(2)));
} catch (error) {
  console.error("receipt-check: " + error.message);
  usage();
  process.exit(2);
}
