/**
 * ops-stitch: Programmatic interface to Google Stitch design tool.
 * Uses @google/stitch-sdk (MCP-based) to create projects, generate screens,
 * edit designs, and download HTML/screenshots.
 */

import { stitch } from "@google/stitch-sdk";
import { writeFileSync, mkdirSync, readFileSync, existsSync } from "fs";
import { join, resolve } from "path";

const args = process.argv.slice(2);
const command = args[0];

function usage() {
  console.log(`Usage: tsx stitch.ts <command> [options]

Commands:
  list-projects                     List all Stitch projects
  get-project <id>                  Get screens from a project
  generate <prompt> [--project <id>] [--output <dir>]
                                    Generate a new screen from prompt
  edit <screen-id> <prompt> [--project <id>] [--output <dir>]
                                    Edit an existing screen
  variants <screen-id> <prompt> [--project <id>] [--count <n>] [--output <dir>]
                                    Generate variants of a screen
  download <project-id> [--output <dir>]
                                    Download all screens (HTML + PNG) from a project
  bundle <prompt> [--project <id>] [--design-md <path>] [--url <url>] [--output <dir>]
                                    Generate design + bundle context for integration

Environment:
  STITCH_API_KEY                    Required. Set in .env
`);
}

function getArg(flag: string): string | undefined {
  const idx = args.indexOf(flag);
  return idx !== -1 && idx + 1 < args.length ? args[idx + 1] : undefined;
}

async function downloadFile(url: string, dest: string) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed: ${res.status} ${url}`);
  const buf = Buffer.from(await res.arrayBuffer());
  writeFileSync(dest, buf);
}

async function listProjects() {
  const projects = await stitch.projects();
  for (const p of projects) {
    const screens = await p.screens();
    console.log(`${p.projectId}  ${screens.length} screens`);
  }
}

async function getProject(id: string) {
  const project = stitch.project(id);
  const screens = await project.screens();
  console.log(`Project ${id}: ${screens.length} screens`);
  for (const s of screens) {
    console.log(`  ${s.id}`);
  }
}

async function generate(prompt: string) {
  const projectId = getArg("--project");
  const outputDir = getArg("--output") || ".";
  mkdirSync(outputDir, { recursive: true });

  let project;
  if (projectId) {
    project = stitch.project(projectId);
  } else {
    project = await stitch.createProject("ops-stitch-gen");
    console.log(`Created project: ${project.projectId}`);
  }

  console.log(`Generating: "${prompt.slice(0, 80)}..."`);
  const screen = await project.generate(prompt);
  console.log(`Screen: ${screen.id}`);

  // Download HTML and screenshot
  const htmlUrl = await screen.getHtml();
  const imageUrl = await screen.getImage();

  if (htmlUrl) {
    const htmlPath = join(outputDir, `${screen.id}.html`);
    await downloadFile(htmlUrl, htmlPath);
    console.log(`HTML: ${htmlPath}`);
  }

  if (imageUrl) {
    const imgPath = join(outputDir, `${screen.id}.png`);
    await downloadFile(imageUrl, imgPath);
    console.log(`PNG: ${imgPath}`);
  }

  // Write manifest
  const manifest = {
    projectId: project.projectId,
    screenId: screen.id,
    prompt,
    timestamp: new Date().toISOString(),
    files: { html: `${screen.id}.html`, png: `${screen.id}.png` },
  };
  writeFileSync(join(outputDir, "manifest.json"), JSON.stringify(manifest, null, 2));
  console.log(`Manifest: ${join(outputDir, "manifest.json")}`);
}

async function editScreen(screenId: string, prompt: string) {
  const projectId = getArg("--project");
  const outputDir = getArg("--output") || ".";
  mkdirSync(outputDir, { recursive: true });

  if (!projectId) {
    console.error("--project required for edit");
    process.exit(1);
  }

  const project = stitch.project(projectId);
  const screens = await project.screens();
  const screen = screens.find((s: any) => s.id === screenId);
  if (!screen) {
    console.error(`Screen ${screenId} not found in project ${projectId}`);
    process.exit(1);
  }

  console.log(`Editing screen ${screenId}: "${prompt.slice(0, 80)}..."`);
  const edited = await screen.edit(prompt);
  console.log(`Edited screen: ${edited.id}`);

  const htmlUrl = await edited.getHtml();
  const imageUrl = await edited.getImage();

  if (htmlUrl) {
    const htmlPath = join(outputDir, `${edited.id}.html`);
    await downloadFile(htmlUrl, htmlPath);
    console.log(`HTML: ${htmlPath}`);
  }
  if (imageUrl) {
    const imgPath = join(outputDir, `${edited.id}.png`);
    await downloadFile(imgPath, imgPath);
    console.log(`PNG: ${imgPath}`);
  }
}

async function generateVariants(screenId: string, prompt: string) {
  const projectId = getArg("--project");
  const outputDir = getArg("--output") || ".";
  const count = parseInt(getArg("--count") || "3");
  mkdirSync(outputDir, { recursive: true });

  if (!projectId) {
    console.error("--project required for variants");
    process.exit(1);
  }

  const project = stitch.project(projectId);
  const screens = await project.screens();
  const screen = screens.find((s: any) => s.id === screenId);
  if (!screen) {
    console.error(`Screen ${screenId} not found`);
    process.exit(1);
  }

  console.log(`Generating ${count} variants: "${prompt.slice(0, 80)}..."`);
  const variants = await screen.variants(prompt, { variantCount: count });

  for (const v of variants) {
    const htmlUrl = await v.getHtml();
    const imageUrl = await v.getImage();
    if (htmlUrl) {
      const htmlPath = join(outputDir, `${v.id}.html`);
      await downloadFile(htmlUrl, htmlPath);
      console.log(`Variant HTML: ${htmlPath}`);
    }
    if (imageUrl) {
      const imgPath = join(outputDir, `${v.id}.png`);
      await downloadFile(imageUrl, imgPath);
      console.log(`Variant PNG: ${imgPath}`);
    }
  }
}

async function downloadProject(projectId: string) {
  const outputDir = getArg("--output") || `./${projectId}`;
  mkdirSync(outputDir, { recursive: true });

  const project = stitch.project(projectId);
  const screens = await project.screens();
  console.log(`Downloading ${screens.length} screens from ${projectId}`);

  for (const s of screens) {
    const htmlUrl = await s.getHtml();
    const imageUrl = await s.getImage();
    if (htmlUrl) {
      await downloadFile(htmlUrl, join(outputDir, `${s.id}.html`));
    }
    if (imageUrl) {
      await downloadFile(imageUrl, join(outputDir, `${s.id}.png`));
    }
    console.log(`  ${s.id} ✓`);
  }
  console.log(`Downloaded to ${outputDir}`);
}

async function bundle(prompt: string) {
  const projectId = getArg("--project");
  const designMdPath = getArg("--design-md");
  const outputDir = getArg("--output") || "./context-bundle";
  mkdirSync(outputDir, { recursive: true });

  // 1. Generate via Stitch
  let project;
  if (projectId) {
    project = stitch.project(projectId);
  } else {
    project = await stitch.createProject("ops-stitch-bundle");
    console.log(`Created project: ${project.projectId}`);
  }

  // Prepend DESIGN.md context to prompt if available
  let fullPrompt = prompt;
  if (designMdPath && existsSync(designMdPath)) {
    const designCtx = readFileSync(designMdPath, "utf-8");
    // Extract key tokens (colors, fonts, rules) — keep under Stitch limits
    const lines = designCtx.split("\n").filter(l =>
      l.includes("#") || l.includes("|") || l.includes("```") || l.includes("- ")
    ).slice(0, 30);
    fullPrompt = `Design system context:\n${lines.join("\n")}\n\nDesign request: ${prompt}`;
  }

  console.log(`Generating: "${prompt.slice(0, 80)}..."`);
  const screen = await project.generate(fullPrompt);

  // Download outputs
  const htmlUrl = await screen.getHtml();
  const imageUrl = await screen.getImage();

  if (htmlUrl) {
    await downloadFile(htmlUrl, join(outputDir, `${screen.id}.html`));
    console.log(`HTML: ${screen.id}.html`);
  }
  if (imageUrl) {
    await downloadFile(imageUrl, join(outputDir, `${screen.id}.png`));
    console.log(`PNG: ${screen.id}.png`);
  }

  // Copy DESIGN.md
  if (designMdPath && existsSync(designMdPath)) {
    writeFileSync(join(outputDir, "DESIGN.md"), readFileSync(designMdPath));
  }

  // Write manifest
  const manifest = {
    projectId: project.projectId,
    screenId: screen.id,
    prompt,
    designMd: designMdPath || null,
    timestamp: new Date().toISOString(),
  };
  writeFileSync(join(outputDir, "manifest.json"), JSON.stringify(manifest, null, 2));
  console.log(`\nBundle ready: ${outputDir}`);
}

// --- Main dispatch ---
async function main() {
  if (!command) { usage(); process.exit(1); }

  switch (command) {
    case "list-projects":
      await listProjects();
      break;
    case "get-project":
      await getProject(args[1]);
      break;
    case "generate":
      await generate(args[1]);
      break;
    case "edit":
      await editScreen(args[1], args[2]);
      break;
    case "variants":
      await generateVariants(args[1], args[2]);
      break;
    case "download":
      await downloadProject(args[1]);
      break;
    case "bundle":
      await bundle(args[1]);
      break;
    default:
      console.error(`Unknown command: ${command}`);
      usage();
      process.exit(1);
  }

  await stitch.close();
}

main().catch((err) => {
  console.error("Error:", err.message || err);
  process.exit(1);
});
