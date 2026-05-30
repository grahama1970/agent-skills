#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execSync } = require("child_process");

const HOST_NAME = "surf.browser.host";

const BROWSERS = {
  chrome: {
    name: "Google Chrome",
    darwin: "Library/Application Support/Google/Chrome/NativeMessagingHosts",
    linux: ".config/google-chrome/NativeMessagingHosts",
    win32: "Google\\Chrome",
  },
  chromium: {
    name: "Chromium",
    darwin: "Library/Application Support/Chromium/NativeMessagingHosts",
    linux: ".config/chromium/NativeMessagingHosts",
    win32: "Chromium",
  },
  brave: {
    name: "Brave",
    darwin: "Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts",
    linux: ".config/BraveSoftware/Brave-Browser/NativeMessagingHosts",
    win32: "BraveSoftware\\Brave-Browser",
  },
  edge: {
    name: "Microsoft Edge",
    darwin: "Library/Application Support/Microsoft Edge/NativeMessagingHosts",
    linux: ".config/microsoft-edge/NativeMessagingHosts",
    win32: "Microsoft\\Edge",
  },
  arc: {
    name: "Arc",
    darwin: "Library/Application Support/Arc/User Data/NativeMessagingHosts",
    linux: null,
    win32: null,
  },
};

function getWrapperDir() {
  const platform = process.platform;
  const home = os.homedir();
  switch (platform) {
    case "darwin":
      return path.join(home, "Library/Application Support/surf-cli");
    case "linux":
      return path.join(home, ".local/share/surf-cli");
    case "win32":
      return path.join(process.env.LOCALAPPDATA || path.join(home, "AppData/Local"), "surf-cli");
    default:
      return null;
  }
}

function removeManifest(browser) {
  const platform = process.platform;
  const browserConfig = BROWSERS[browser];

  if (!browserConfig || !browserConfig[platform]) {
    return null;
  }

  if (platform === "win32") {
    return removeWindowsRegistry(browser);
  }

  const manifestPath = path.join(
    os.homedir(),
    browserConfig[platform],
    `${HOST_NAME}.json`
  );

  try {
    fs.unlinkSync(manifestPath);
    return manifestPath;
  } catch {
    return null;
  }
}

function removeWindowsRegistry(browser) {
  const browserConfig = BROWSERS[browser];
  const regPath = `HKCU\\Software\\${browserConfig.win32}\\NativeMessagingHosts\\${HOST_NAME}`;

  try {
    execSync(`reg delete "${regPath}" /f`, { stdio: "pipe" });
    return regPath;
  } catch {
    return null;
  }
}

function removeWrapperDir() {
  const wrapperDir = getWrapperDir();
  if (!wrapperDir) return null;

  try {
    fs.rmSync(wrapperDir, { recursive: true, force: true });
    return wrapperDir;
  } catch {
    return null;
  }
}

function parseArgs() {
  const args = process.argv.slice(2);
  const result = { browsers: ["chrome"], all: false };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--browser" || arg === "-b") {
      const browserArg = args[++i];
      if (browserArg === "all") {
        result.browsers = Object.keys(BROWSERS);
        result.all = true;
      } else {
        result.browsers = browserArg.split(",").map((b) => b.trim().toLowerCase());
      }
    } else if (arg === "--all" || arg === "-a") {
      result.browsers = Object.keys(BROWSERS);
      result.all = true;
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    }
  }
  return result;
}

function printHelp() {
  console.log(`
Surf CLI Native Host Uninstaller

Usage: uninstall-native-host.cjs [options]

Options:
  -b, --browser   Browser(s) to uninstall from (default: chrome)
                  Values: chrome, chromium, brave, edge, arc, all
  -a, --all       Uninstall from all browsers and remove wrapper

Examples:
  node uninstall-native-host.cjs
  node uninstall-native-host.cjs --browser brave
  node uninstall-native-host.cjs --all
`);
}

function main() {
  const { browsers, all } = parseArgs();

  console.log(`Platform: ${process.platform}`);
  console.log("");

  const removed = [];
  const notFound = [];

  for (const browser of browsers) {
    if (!BROWSERS[browser]) {
      console.error(`Unknown browser: ${browser}`);
      continue;
    }

    const result = removeManifest(browser);
    if (result) {
      removed.push({ browser: BROWSERS[browser].name, path: result });
    } else {
      notFound.push(BROWSERS[browser].name);
    }
  }

  if (removed.length > 0) {
    console.log("Removed manifests:");
    for (const { browser, path: p } of removed) {
      console.log(`  ${browser}: ${p}`);
    }
  }

  if (notFound.length > 0) {
    console.log(`\nNot found: ${notFound.join(", ")}`);
  }

  if (all) {
    const wrapperDir = removeWrapperDir();
    if (wrapperDir) {
      console.log(`\nRemoved wrapper directory: ${wrapperDir}`);
    }
  }

  console.log("\nDone!");
}

main();
