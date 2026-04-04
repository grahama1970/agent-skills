#!/usr/bin/env node
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function sh(cmd, cwd) {
  console.log(`> ${cmd}`);
  execSync(cmd, { stdio: "inherit", cwd, env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" } });
}

function parseArgs(argv) {
  const args = { prompt: "", out: "outputs/run-001" };
  const rest = [...argv];
  args.prompt = rest.shift() ?? "";
  while (rest.length) {
    const a = rest.shift();
    if (a === "--out") args.out = rest.shift();
  }
  if (!args.prompt) throw new Error("Missing prompt string");
  return args;
}

function writeFile(p, content) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, content, "utf8");
}

function main() {
  const { prompt, out } = parseArgs(process.argv.slice(2));
  fs.mkdirSync(out, { recursive: true });

  const appDir = path.join(out, "app");

  if (fs.existsSync(appDir)) {
    console.log(`Output directory ${appDir} already exists. Skipping scaffold.`);
  } else {
    console.log("Scaffolding Next.js app...");
    // Create Next.js app non-interactively
    sh(
      `npx create-next-app@latest "${appDir}" --ts --eslint --tailwind --app --src-dir --import-alias "@/*" --no-turbo --use-pnpm`,
      out
    );

    // Initialize ShadCN
    console.log("Initializing ShadCN...");
    const componentsJson = {
      "$schema": "https://ui.shadcn.com/schema.json",
      "style": "default",
      "rsc": true,
      "tsx": true,
      "tailwind": {
        "config": "tailwind.config.ts",
        "css": "src/app/globals.css",
        "baseColor": "slate",
        "cssVariables": true,
        "prefix": ""
      },
      "aliases": {
        "components": "@/components",
        "utils": "@/lib/utils"
      }
    };
    writeFile(path.join(appDir, "components.json"), JSON.stringify(componentsJson, null, 2));
    
    // Install dependencies
    sh("pnpm add lucide-react class-variance-authority clsx tailwind-merge", appDir);
    
    // Install common ShadCN components
    const commonComponents = [
      "button", "card", "input", "badge", "tabs", "table", 
      "dropdown-menu", "dialog", "sheet", "toast", "form", 
      "avatar", "separator", "skeleton", "scroll-area"
    ];
    sh(`npx shadcn@latest add ${commonComponents.join(" ")} --yes`, appDir);
  }

  // Create the "Prompt Context" file so coders know what to build
  writeFile(
    path.join(out, "PROMPT.md"),
    `# Design Prompt\n\n${prompt}\n`
  );

  console.log(`\n✅ Created production-ready scaffold at: ${appDir}`);
  console.log(`\nNext steps:`);
  console.log(`1. Implement the design based on PROMPT.md`);
  console.log(`2. Run ./run.sh council to get feedback`);
}

main();
