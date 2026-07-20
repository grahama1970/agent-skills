#!/usr/bin/env node
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");
const distRoot = resolve(packageRoot, "dist");
const publicRoot = resolve(packageRoot, "public");

const args = process.argv.slice(2);
const port = Number(valueAfter("--port") ?? "3002");
const host = valueAfter("--host") ?? "127.0.0.1";

function valueAfter(flag) {
  const index = args.indexOf(flag);
  if (index === -1) return null;
  return args[index + 1] ?? null;
}

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".mid", "audio/midi"],
  [".ogg", "audio/ogg"],
  [".png", "image/png"],
  [".tsx", "text/plain; charset=utf-8"],
]);

function inside(root, filePath) {
  return filePath === root || filePath.startsWith(`${root}${sep}`);
}

function resolveRequest(pathname) {
  const decoded = decodeURIComponent(pathname);
  if (decoded === "/__host.json") return { virtual: "host" };
  if (decoded === "/src/main.tsx") return { filePath: resolve(packageRoot, "src/main.tsx"), root: packageRoot };
  if (decoded.startsWith("/assets/")) return { filePath: resolve(distRoot, decoded.slice(1)), root: distRoot };
  if (
    decoded.startsWith("/battle-fixtures/") ||
    decoded.startsWith("/battle-audio/") ||
    decoded.startsWith("/battle-race-atlas")
  ) {
    return { filePath: resolve(publicRoot, decoded.slice(1)), root: publicRoot };
  }
  return { filePath: resolve(distRoot, "index.html"), root: distRoot };
}

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://${host}:${port}`);
  const target = resolveRequest(url.pathname);

  if (target.virtual === "host") {
    response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    response.end(
      JSON.stringify(
        {
          host: "agent-skills battle spectator",
          packageRoot,
          entry: "skills/battle/spectator/src/main.tsx",
        },
        null,
        2,
      ),
    );
    return;
  }

  if (!target.filePath || !target.root || !inside(target.root, target.filePath) || !existsSync(target.filePath)) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found\n");
    return;
  }

  const stat = statSync(target.filePath);
  if (!stat.isFile()) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found\n");
    return;
  }

  response.writeHead(200, {
    "content-length": stat.size,
    "content-type": contentTypes.get(extname(target.filePath)) ?? "application/octet-stream",
  });
  createReadStream(target.filePath).pipe(response);
});

server.listen(port, host, () => {
  console.log(`Battle spectator static host listening at http://${host}:${port}/`);
  console.log(`Serving ${packageRoot}`);
});
