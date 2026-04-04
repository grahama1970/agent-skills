#!/usr/bin/env node
/**
 * mockup-lab CLI — wraps @google/stitch-sdk for iterative mockup generation.
 *
 * Retry, backoff, and rate-limit handling are built into the forked SDK
 * (grahama1970/stitch-sdk). This CLI only adds cooldown (proactive spacing)
 * and screen-lookup helpers.
 *
 * Commands: generate, variants, iterate, pull, list, converge, theme, explore
 */
import { stitch } from "@google/stitch-sdk";
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { join, resolve } from "path";

const args = process.argv.slice(2);
const cmd = args[0];

function getArg(name) {
  const idx = args.indexOf(`--${name}`);
  return idx >= 0 && idx + 1 < args.length ? args[idx + 1] : null;
}

/** Parse --device flag. Defaults to DESKTOP. */
function getDevice() {
  const raw = (getArg("device") || "desktop").toUpperCase();
  const valid = ["MOBILE", "DESKTOP", "TABLET", "AGNOSTIC"];
  if (!valid.includes(raw)) {
    console.error(`Invalid --device: ${raw}. Must be one of: ${valid.join(", ")}`);
    process.exit(1);
  }
  return raw;
}

/** Proactive cooldown between Stitch API calls to avoid hitting rate limits */
const COOLDOWN_MS = parseInt(process.env.STITCH_COOLDOWN_MS || "3000", 10);
let lastCallTime = 0;

async function cooldown() {
  const elapsed = Date.now() - lastCallTime;
  if (elapsed < COOLDOWN_MS) {
    const wait = COOLDOWN_MS - elapsed;
    console.error(`[cooldown] waiting ${(wait / 1000).toFixed(1)}s`);
    await new Promise(r => setTimeout(r, wait));
  }
  lastCallTime = Date.now();
}

async function downloadUrl(url, outPath) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Download failed: ${resp.status}`);
  const buf = Buffer.from(await resp.arrayBuffer());
  writeFileSync(outPath, buf);
  return outPath;
}

/**
 * Find a screen by ID. The SDK's project.getScreen() handles settle-delay
 * retries internally, but this helper provides a fallback via screens() list
 * when the screenId format doesn't match what getScreen expects.
 */
async function findScreen(project, screenId) {
  // Try direct lookup first (SDK handles retry on NOT_FOUND for fresh projects)
  try {
    return await project.getScreen(screenId);
  } catch {
    // Fallback: search the screens list
    const screens = await project.screens();
    return screens.find(s => s.id === screenId || s.screenId === screenId) || null;
  }
}

// ── generate: spec file → new project + screen ──
async function generate() {
  const specPath = getArg("spec");
  if (!specPath) { console.error("Usage: generate --spec <file> [--device desktop|mobile|tablet]"); process.exit(1); }
  const device = getDevice();

  const spec = readFileSync(resolve(specPath), "utf-8");
  const title = spec.match(/^#\s+(.+)/m)?.[1] || "Mockup Lab Project";

  console.log(`Creating Stitch project: ${title} (${device})`);
  await cooldown();
  const project = await stitch.createProject(title);
  console.log(`Project ID: ${project.id}`);

  console.log("Generating screen from spec...");
  await cooldown();
  const screen = await project.generate(spec, device);
  const htmlUrl = await screen.getHtml();
  const imageUrl = await screen.getImage();

  console.log(JSON.stringify({
    projectId: project.id,
    screenId: screen.id,
    htmlUrl,
    imageUrl,
    stitchUrl: `https://stitch.withgoogle.com/projects/${project.id}`,
  }, null, 2));
}

// ── variants: generate N variations of a screen ──
async function variants() {
  const projectId = getArg("project");
  const screenId = getArg("screen");
  const prompt = getArg("prompt") || "Try different layouts and color approaches";
  const count = parseInt(getArg("count") || "3", 10);

  if (!projectId || !screenId) {
    console.error("Usage: variants --project <id> --screen <id> [--prompt <text>] [--count 3]");
    process.exit(1);
  }

  const project = stitch.project(projectId);
  const screen = await findScreen(project, screenId);
  if (!screen) { console.error(`Screen ${screenId} not found`); process.exit(1); }

  const device = getDevice();
  console.log(`Generating ${count} variants (${device})...`);
  await cooldown();
  const results = await screen.variants(prompt, {
    variantCount: count,
    creativeRange: "EXPLORE",
    aspects: ["LAYOUT", "COLOR_SCHEME"],
  }, device);

  const output = [];
  for (const v of results) {
    output.push({
      screenId: v.id,
      htmlUrl: await v.getHtml(),
      imageUrl: await v.getImage(),
    });
  }
  console.log(JSON.stringify(output, null, 2));
}

// ── iterate: edit a screen with feedback ──
async function iterate() {
  const projectId = getArg("project");
  const screenId = getArg("screen");
  const feedback = getArg("feedback");

  if (!projectId || !screenId || !feedback) {
    console.error("Usage: iterate --project <id> --screen <id> --feedback <text>");
    process.exit(1);
  }

  const project = stitch.project(projectId);
  const screen = await findScreen(project, screenId);
  if (!screen) { console.error(`Screen ${screenId} not found`); process.exit(1); }

  const device = getDevice();
  console.log(`Iterating with feedback (${device})...`);
  await cooldown();
  const edited = await screen.edit(feedback, device);
  console.log(JSON.stringify({
    screenId: edited.id,
    htmlUrl: await edited.getHtml(),
    imageUrl: await edited.getImage(),
  }, null, 2));
}

// ── pull: download screen HTML + image locally ──
async function pull() {
  const projectId = getArg("project");
  const screenId = getArg("screen");
  const outputDir = getArg("output") || "./captures/stitch";

  if (!projectId || !screenId) {
    console.error("Usage: pull --project <id> --screen <id> [--output <dir>]");
    process.exit(1);
  }

  mkdirSync(resolve(outputDir), { recursive: true });

  const project = stitch.project(projectId);
  const screen = await findScreen(project, screenId);
  if (!screen) { console.error(`Screen ${screenId} not found`); process.exit(1); }

  const htmlUrl = await screen.getHtml();
  const imageUrl = await screen.getImage();

  const htmlPath = join(resolve(outputDir), `${screenId}.html`);
  const imgPath = join(resolve(outputDir), `${screenId}.png`);

  await downloadUrl(htmlUrl, htmlPath);
  console.log(`HTML: ${htmlPath}`);

  if (imageUrl) {
    await downloadUrl(imageUrl, imgPath);
    console.log(`Image: ${imgPath}`);
  }
}

// ── list: show projects or screens ──
async function list() {
  const projectId = getArg("project");

  if (projectId) {
    const project = stitch.project(projectId);
    const screens = await project.screens();
    for (const s of screens) {
      console.log(`  ${s.id}  ${s.title || s.name || "(untitled)"}`);
    }
  } else {
    const projects = await stitch.projects();
    for (const p of projects) {
      const screens = await p.screens();
      console.log(`${p.projectId}  ${p.title || "(untitled)"}  (${screens.length} screens)`);
    }
  }
}

// ── converge: generate initial screen (one-shot, loop is agent-driven) ──
async function converge() {
  const specPath = getArg("spec");
  if (!specPath) { console.error("Usage: converge --spec <file> [--device desktop|mobile|tablet]"); process.exit(1); }
  const device = getDevice();

  console.log(`=== Round 1: Generate from spec (${device}) ===`);
  const spec = readFileSync(resolve(specPath), "utf-8");
  const title = spec.match(/^#\s+(.+)/m)?.[1] || "Mockup Lab";

  await cooldown();
  const project = await stitch.createProject(title);

  await cooldown();
  const screen = await project.generate(spec, device);
  const imageUrl = await screen.getImage();
  const htmlUrl = await screen.getHtml();

  console.log(JSON.stringify({
    round: 1,
    projectId: project.id,
    screenId: screen.id,
    stitchUrl: `https://stitch.withgoogle.com/projects/${project.id}`,
    htmlUrl,
    imageUrl,
    status: "Generated. Review in Stitch, then run 'iterate' with feedback.",
  }, null, 2));
}

// ── theme: extract Tailwind config + design tokens from a project ──
async function theme() {
  const projectId = getArg("project");
  const output = getArg("output");

  if (!projectId) {
    console.error("Usage: theme --project <id> [--output <file>]");
    process.exit(1);
  }

  await cooldown();
  const result = await stitch.callTool("get_project", { projectId });
  const designTheme = result?.project?.designTheme || result?.designTheme;

  if (!designTheme) {
    console.error("No design theme found in project");
    process.exit(1);
  }

  const out = {
    tailwindConfig: designTheme.namedColors || {},
    fonts: {
      headline: designTheme.headlineFont,
      body: designTheme.font,
      label: designTheme.labelFont,
      mono: designTheme.bodyFont,
    },
    colorMode: designTheme.colorMode,
    customColor: designTheme.customColor,
    designMd: designTheme.designMd ? "(present, " + designTheme.designMd.length + " chars)" : "(none)",
  };

  const json = JSON.stringify(out, null, 2);
  if (output) {
    writeFileSync(resolve(output), json);
    console.log(`Theme written to ${output}`);
  } else {
    console.log(json);
  }
}

// ── explore: auto-generate screens for each view from --views file ──
async function explore() {
  const projectId = getArg("project");
  const screenId = getArg("screen");
  const viewsPath = getArg("views");
  const outputDir = getArg("output") || "./captures/stitch-explore";

  if (!projectId || !screenId || !viewsPath) {
    console.error("Usage: explore --project <id> --screen <id> --views <file.json> [--output <dir>]");
    console.error("");
    console.error("  --views: JSON file with array of { name, prompt } objects.");
    console.error("           Each entry becomes a Stitch screen (1 credit each).");
    console.error("");
    console.error("  Example views.json:");
    console.error('  [');
    console.error('    { "name": "dashboard", "prompt": "Show the main dashboard with..." },');
    console.error('    { "name": "settings", "prompt": "Show the settings page with..." }');
    console.error('  ]');
    process.exit(1);
  }

  mkdirSync(resolve(outputDir), { recursive: true });

  let views;
  try {
    views = JSON.parse(readFileSync(resolve(viewsPath), "utf-8"));
  } catch (err) {
    console.error(`Failed to read views file: ${err.message}`);
    process.exit(1);
  }

  if (!Array.isArray(views) || views.length === 0) {
    console.error("Views file must be a non-empty JSON array of { name, prompt } objects");
    process.exit(1);
  }
  for (const v of views) {
    if (!v.name || !v.prompt) {
      console.error(`Invalid view entry: each must have "name" and "prompt". Got: ${JSON.stringify(v)}`);
      process.exit(1);
    }
  }

  const device = getDevice();
  console.log(`Generating ${views.length} views (${device}, ${views.length} credits). ETA: ~${views.length * 4}s with cooldown.`);

  const project = stitch.project(projectId);
  const baseScreen = await findScreen(project, screenId);
  if (!baseScreen) { console.error(`Screen ${screenId} not found`); process.exit(1); }

  const results = [];
  for (const view of views) {
    console.log(`\n=== Generating: ${view.name} ===`);
    try {
      await cooldown();
      const edited = await baseScreen.edit(view.prompt, device);
      const imageUrl = await edited.getImage();
      const htmlUrl = await edited.getHtml();

      const imgPath = join(resolve(outputDir), `${view.name}.png`);
      const htmlPath = join(resolve(outputDir), `${view.name}.html`);
      await downloadUrl(imageUrl, imgPath);
      if (htmlUrl) await downloadUrl(htmlUrl, htmlPath);

      results.push({ view: view.name, screenId: edited.id, imagePath: imgPath, htmlPath: htmlUrl ? htmlPath : null });
      console.log(`  done: ${view.name} (${edited.id})`);
    } catch (err) {
      console.error(`  failed: ${view.name}: ${err.message}`);
      results.push({ view: view.name, error: err.message });
    }
  }

  const manifest = join(resolve(outputDir), "manifest.json");
  writeFileSync(manifest, JSON.stringify(results, null, 2));
  console.log(`\nManifest: ${manifest}`);
  console.log(`Generated ${results.filter(r => !r.error).length}/${views.length} views`);
}

// ── review: compare built component against Stitch design target via VLM ──
async function review() {
  const projectId = getArg("project");
  const screenId = getArg("screen");
  const screenshot = getArg("screenshot");
  const codeFiles = getArg("code");       // comma-separated paths to React source files
  const tokensFile = getArg("tokens");    // path to design-tokens.json or EmbryStyle.ts
  const outputDir = getArg("output") || "./captures/stitch-review";

  if (!projectId || !screenId || !screenshot) {
    console.error("Usage: review --project <id> --screen <design-target-id> --screenshot <path.png>");
    console.error("       [--code <file1.tsx,file2.tsx>] [--tokens <design-tokens.json>]");
    console.error("       [--output <dir>]");
    console.error("");
    console.error("  Compares built component against Stitch design target via Gemini VLM.");
    console.error("  With --code: sends React source so VLM can reference exact lines to fix.");
    console.error("  With --tokens: sends design tokens so VLM can verify color/font compliance.");
    process.exit(1);
  }

  const screenshotPath = resolve(screenshot);
  try { readFileSync(screenshotPath); } catch {
    console.error(`Screenshot not found: ${screenshotPath}`);
    process.exit(1);
  }

  mkdirSync(resolve(outputDir), { recursive: true });

  // Step 1: Pull the design target screenshot from Stitch
  console.log("Pulling design target from Stitch...");
  const project = stitch.project(projectId);
  const designTarget = await findScreen(project, screenId);
  if (!designTarget) { console.error(`Design target screen ${screenId} not found`); process.exit(1); }

  const designImageUrl = await designTarget.getImage();
  const designPath = join(resolve(outputDir), "design-target.png");
  await downloadUrl(designImageUrl, designPath);

  // Step 2: Gather code context
  let codeContext = "";
  if (codeFiles) {
    for (const f of codeFiles.split(",")) {
      const p = resolve(f.trim());
      try {
        const src = readFileSync(p, "utf-8");
        codeContext += `\n--- ${f.trim()} ---\n${src.slice(0, 8000)}\n`;
      } catch { console.error(`Warning: could not read ${p}`); }
    }
  }
  let tokensContext = "";
  if (tokensFile) {
    try {
      tokensContext = readFileSync(resolve(tokensFile), "utf-8").slice(0, 3000);
    } catch { console.error(`Warning: could not read ${tokensFile}`); }
  }

  // Step 3: Send images + code + tokens to scillm VLM
  console.log("Sending to Gemini VLM for visual diff...");
  const designB64 = readFileSync(designPath).toString("base64");
  const implB64 = readFileSync(screenshotPath).toString("base64");

  const systemPrompt = [
    "You are a UI design reviewer comparing a DESIGN TARGET against an IMPLEMENTATION.",
    "Return a JSON object with:",
    "- match_score: 0-100",
    "- differences: [{element, issue, fix, line_number?}] — reference exact code lines when --code is provided",
    "- missing_elements: string[]",
    "- extra_elements: string[]",
    "- color_issues: [{token, expected_hex, actual_hex, element}] — verify against design tokens when provided",
    "- iterate_prompt: paragraph to send to Stitch for correction",
    "",
    "Be specific: px values, hex colors, font names, line numbers in the source code.",
    codeContext ? "\n\nSOURCE CODE:\n" + codeContext : "",
    tokensContext ? "\n\nDESIGN TOKENS:\n" + tokensContext : "",
  ].join("\n");

  const vlmPayload = {
    model: "vlm",
    messages: [
      {
        role: "user",
        content: [
          { type: "text", text: systemPrompt },
          { type: "image_url", image_url: { url: "data:image/png;base64," + designB64 } },
          { type: "image_url", image_url: { url: "data:image/png;base64," + implB64 } },
        ],
      },
    ],
    response_format: { type: "json_object" },
  };

  const resp = await fetch("http://localhost:4001/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(vlmPayload),
  });

  if (!resp.ok) {
    console.error(`scillm VLM request failed: ${resp.status} ${resp.statusText}`);
    process.exit(1);
  }

  const vlmResult = await resp.json();
  const content = vlmResult.choices?.[0]?.message?.content;

  let reviewData;
  try {
    reviewData = JSON.parse(content);
  } catch {
    // VLM returned non-JSON — wrap it
    reviewData = { raw_review: content, match_score: null, iterate_prompt: content };
  }

  // Step 3: Write review results
  const reviewPath = join(resolve(outputDir), "review.json");
  writeFileSync(reviewPath, JSON.stringify(reviewData, null, 2));

  console.log(JSON.stringify({
    designTarget: designPath,
    implementation: screenshotPath,
    matchScore: reviewData.match_score,
    differenceCount: reviewData.differences?.length || 0,
    reviewFile: reviewPath,
    iteratePrompt: reviewData.iterate_prompt,
    nextStep: reviewData.match_score >= 90
      ? "Implementation matches design. Ready for production."
      : "Run: ./run.sh iterate --project " + projectId + " --screen " + screenId + " --feedback '<iterate_prompt from review.json>'",
  }, null, 2));
}

// ── dispatch ──
const commands = { generate, variants, iterate, pull, list, converge, theme, explore, review };
const fn = commands[cmd];
if (!fn) {
  console.error(`Unknown command: ${cmd}`);
  console.error(`Available: ${Object.keys(commands).join(", ")}`);
  process.exit(1);
}
fn().catch(err => { console.error("Error:", err.message); process.exit(1); });
