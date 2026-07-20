#!/usr/bin/env node
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");
const distDir = resolve(packageRoot, "dist");
const candidates = [
  resolve(packageRoot, "node_modules/esbuild"),
  resolve(packageRoot, "../monitor/battle/node_modules/esbuild"),
];

const esbuildRoot = candidates.find((candidate) => existsSync(resolve(candidate, "package.json")));
if (!esbuildRoot) {
  console.error("No esbuild package found for Battle spectator static build.");
  console.error(`Checked: ${candidates.join(", ")}`);
  process.exit(1);
}

const require = createRequire(resolve(esbuildRoot, "package.json"));
const esbuild = require("esbuild");

mkdirSync(resolve(distDir, "assets"), { recursive: true });

const rawTextPlugin = {
  name: "raw-text",
  setup(build) {
    build.onResolve({ filter: /\?raw$/ }, (args) => ({
      path: resolve(args.resolveDir, args.path.replace(/\?raw$/, "")),
      namespace: "raw-text",
    }));
    build.onLoad({ filter: /.*/, namespace: "raw-text" }, async (args) => {
      const { readFile } = await import("node:fs/promises");
      return {
        contents: await readFile(args.path, "utf8"),
        loader: "text",
      };
    });
  },
};

await esbuild.build({
  entryPoints: [resolve(packageRoot, "src/main.tsx")],
  bundle: true,
  format: "esm",
  sourcemap: false,
  minify: false,
  splitting: false,
  target: ["es2022"],
  outfile: resolve(distDir, "assets/main.js"),
  loader: {
    ".png": "file",
    ".ogg": "file",
    ".mid": "file",
    ".json": "json",
  },
  assetNames: "assets/[name]-[hash]",
  publicPath: "/",
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  plugins: [rawTextPlugin],
  logLevel: "info",
});

writeFileSync(
  resolve(distDir, "index.html"),
  `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Battle Spectator</title>
    <link rel="stylesheet" href="/assets/main.css" />
  </head>
  <body>
    <div id="root"></div>
    <script>
      window.__battleBootErrors = [];
      window.addEventListener("error", (event) => {
        window.__battleBootErrors.push({
          type: "error",
          message: event.message,
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
        });
      });
      window.addEventListener("unhandledrejection", (event) => {
        window.__battleBootErrors.push({
          type: "unhandledrejection",
          reason: String(event.reason && (event.reason.stack || event.reason.message || event.reason)),
        });
      });
    </script>
    <script type="module" src="/assets/main.js"></script>
  </body>
</html>
`,
);
