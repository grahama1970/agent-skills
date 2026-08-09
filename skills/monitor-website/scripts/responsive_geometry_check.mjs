#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const args = process.argv.slice(2);
const getArg = (name, fallback = null) => {
  const idx = args.indexOf(name);
  if (idx === -1) return fallback;
  return args[idx + 1] ?? fallback;
};
const hasArg = (name) => args.includes(name);

const baseUrl = getArg('--base-url', process.env.SITE_URL || 'http://127.0.0.1:43220');
const outDir = getArg('--out', null);
const asJson = hasArg('--json');

const viewports = [
  ['phone-390', 390, 844],
  ['phone-430', 430, 932],
  ['tablet-768', 768, 1024],
  ['desktop-1366', 1366, 768],
  ['desktop-1440', 1440, 900],
];

const routes = [
  ['home', '/'],
  ['explore', '/explore.html'],
  ['how-proof-works', '/how-proof-works.html'],
  ['ledger', '/ledger.html'],
  ['capabilities', '/capabilities.html'],
  ['resume', '/resume.html'],
];

const routeUrl = (route) => new URL(route, baseUrl).toString();

const browser = await chromium.launch({ headless: true });
const results = [];
const failures = [];

if (outDir) {
  fs.mkdirSync(outDir, { recursive: true });
}

for (const [routeName, route] of routes) {
  for (const [viewportName, width, height] of viewports) {
    const page = await browser.newPage({ viewport: { width, height } });
    const url = routeUrl(route);
    let record;
    try {
      const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(500);
      record = await page.evaluate(() => {
        const isWithinHorizontalScrollSurface = (el) => {
          let parent = el.parentElement;
          while (parent && parent !== document.body) {
            const style = getComputedStyle(parent);
            const hasHorizontalScroll =
              (style.overflowX === 'auto' || style.overflowX === 'scroll') &&
              parent.scrollWidth > parent.clientWidth + 1;
            if (hasHorizontalScroll) return true;
            parent = parent.parentElement;
          }
          return false;
        };
        const root = document.documentElement;
        const body = document.body;
        const interactive = [...document.querySelectorAll('a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])')];
        const offscreenActions = interactive
          .map((el) => {
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return {
              tag: el.tagName.toLowerCase(),
              qid: el.getAttribute('data-qid') || '',
              text: (el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().slice(0, 80),
              hidden: style.visibility === 'hidden' || style.display === 'none',
              left: rect.left,
              right: rect.right,
              top: rect.top,
              bottom: rect.bottom,
              width: rect.width,
              height: rect.height,
            };
          })
          .filter((item) => !item.hidden && item.width > 0 && item.height > 0)
          .filter((item) => item.right < -1 || item.left > window.innerWidth + 1);

        const wideElements = [...document.querySelectorAll('body *')]
          .map((el) => {
            const rect = el.getBoundingClientRect();
            return {
              tag: el.tagName.toLowerCase(),
              className: typeof el.className === 'string' ? el.className : '',
              id: el.id || '',
              qid: el.getAttribute('data-qid') || '',
              left: Number(rect.left.toFixed(2)),
              right: Number(rect.right.toFixed(2)),
              width: Number(rect.width.toFixed(2)),
            };
          })
          .filter((item) => item.right > window.innerWidth + 1 || item.left < -1)
          .slice(0, 20);

        return {
          innerWidth: window.innerWidth,
          scrollWidth: root.scrollWidth,
          bodyScrollWidth: body.scrollWidth,
          overflowPx: Math.max(0, root.scrollWidth - window.innerWidth),
          bodyOverflowPx: Math.max(0, body.scrollWidth - window.innerWidth),
          offscreenActions: offscreenActions.filter((item) => {
            const el = item.qid
              ? document.querySelector(`[data-qid="${CSS.escape(item.qid)}"]`)
              : null;
            return !(el && isWithinHorizontalScrollSurface(el));
          }),
          wideElements,
        };
      });
      record.route = route;
      record.routeName = routeName;
      record.viewport = viewportName;
      record.width = width;
      record.height = height;
      record.status = response?.status() ?? null;
      record.ok =
        record.status >= 200 &&
        record.status < 400 &&
        record.scrollWidth <= width &&
        record.bodyScrollWidth <= width &&
        record.offscreenActions.length === 0;
      if (!record.ok && outDir) {
        const screenshot = path.join(outDir, `${routeName}-${viewportName}.png`);
        await page.screenshot({ path: screenshot, fullPage: true });
        record.screenshot = screenshot;
      }
    } catch (error) {
      record = {
        route,
        routeName,
        viewport: viewportName,
        width,
        height,
        status: null,
        ok: false,
        error: String(error?.message || error),
      };
    } finally {
      await page.close();
    }
    results.push(record);
    if (!record.ok) failures.push(record);
  }
}

await browser.close();

const receipt = {
  schema: 'monitor_website.responsive_geometry_check.v1',
  baseUrl,
  status: failures.length ? 'FAIL' : 'PASS',
  counts: {
    routes: routes.length,
    viewports: viewports.length,
    checks: results.length,
    failures: failures.length,
  },
  failures,
  results,
};

if (outDir) {
  fs.writeFileSync(path.join(outDir, 'results.json'), `${JSON.stringify(receipt, null, 2)}\n`);
}

if (asJson) {
  console.log(JSON.stringify(receipt, null, 2));
} else {
  console.log(`responsive-geometry-check: ${receipt.status}`);
  console.log(`${receipt.counts.checks} checks, ${receipt.counts.failures} failures`);
}

process.exit(failures.length ? 1 : 0);
