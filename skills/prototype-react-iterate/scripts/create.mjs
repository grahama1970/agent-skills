#!/usr/bin/env node
/**
 * Create React/Tailwind/ShadCN prototypes from a text prompt.
 * Stub — full implementation TBD.
 */
const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("Usage: create.mjs <prompt> [--variants N] [--out DIR]");
  process.exit(1);
}
console.log(`[create] Prompt: ${args[0]}`);
console.log("[create] Stub: full implementation pending");
