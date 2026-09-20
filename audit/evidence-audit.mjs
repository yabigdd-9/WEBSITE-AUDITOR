#!/usr/bin/env node
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";

const execFileAsync = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const VERSION = "evidence-v1.0.0";

function usage() {
  console.error("Usage: node evidence-audit.mjs <http(s)://url> [output-dir]");
  process.exit(2);
}

function safeTarget(raw) {
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("target must be a valid URL");
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("target protocol must be http or https");
  }
  return parsed;
}

async function sha256(path) {
  const data = await readFile(path);
  return createHash("sha256").update(data).digest("hex");
}

function categoryScore(lighthouse, key) {
  const value = lighthouse?.categories?.[key]?.score;
  return typeof value === "number" ? Math.round(value * 100) : null;
}

async function runLighthouse(target, outputPath) {
  const lighthouseCli = resolve(HERE, "node_modules/lighthouse/cli/index.js");
  const chromePath = chromium.executablePath();
  await execFileAsync(
    process.execPath,
    [
      lighthouseCli,
      target,
      "--output=json",
      "--output-path=" + outputPath,
      "--quiet",
      "--only-categories=performance,accessibility,best-practices,seo",
      "--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage"
    ],
    {
      env: { ...process.env, CHROME_PATH: chromePath },
      timeout: 120000,
      maxBuffer: 4 * 1024 * 1024
    }
  );
  return JSON.parse(await readFile(outputPath, "utf8"));
}

async function main() {
  const rawTarget = process.argv[2];
  if (!rawTarget) usage();

  const target = safeTarget(rawTarget);
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const outputDir = resolve(
    process.argv[3] || resolve(process.cwd(), "evidence", target.hostname, stamp)
  );
  await mkdir(outputDir, { recursive: true });

  const consoleEvents = [];
  const redirects = [];
  const desktopPath = resolve(outputDir, "desktop-full.webp");
  const mobilePath = resolve(outputDir, "mobile-full.webp");
  const accessibilityPath = resolve(outputDir, "accessibility.json");
  const lighthousePath = resolve(outputDir, "lighthouse.json");
  const consolePath = resolve(outputDir, "console-errors.json");
  const provenancePath = resolve(outputDir, "provenance.json");
  const auditPath = resolve(outputDir, "audit.json");

  const browser = await chromium.launch({ headless: true });
  let browserVersion;
  let responseStatus = null;
  let finalUrl = target.toString();
  let axeResults;

  try {
    browserVersion = browser.version();

    const desktop = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      deviceScaleFactor: 1
    });
    const page = await desktop.newPage();

    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) {
        consoleEvents.push({
          type: message.type(),
          text: message.text(),
          location: message.location()
        });
      }
    });

    page.on("response", (response) => {
      if (response.request().isNavigationRequest()) {
        redirects.push({
          url: response.url(),
          status: response.status()
        });
      }
    });

    const response = await page.goto(target.toString(), {
      waitUntil: "domcontentloaded",
      timeout: 30000
    });
    await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});

    responseStatus = response?.status() ?? null;
    finalUrl = page.url();

    await page.screenshot({
      path: desktopPath,
      type: "webp",
      quality: 82,
      fullPage: true,
      animations: "disabled"
    });

    axeResults = await new AxeBuilder({ page }).analyze();
    await writeFile(accessibilityPath, JSON.stringify(axeResults, null, 2));
    await desktop.close();

    const mobile = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      deviceScaleFactor: 1
    });
    const mobilePage = await mobile.newPage();
    await mobilePage.goto(target.toString(), {
      waitUntil: "domcontentloaded",
      timeout: 30000
    });
    await mobilePage.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
    await mobilePage.screenshot({
      path: mobilePath,
      type: "webp",
      quality: 82,
      fullPage: true,
      animations: "disabled"
    });
    await mobile.close();
  } finally {
    await browser.close();
  }

  await writeFile(consolePath, JSON.stringify(consoleEvents, null, 2));

  const lighthouse = await runLighthouse(target.toString(), lighthousePath);

  const provenance = {
    schema_version: 1,
    auditor_version: VERSION,
    captured_at: new Date().toISOString(),
    requested_url: target.toString(),
    final_url: finalUrl,
    response_status: responseStatus,
    redirect_chain: redirects,
    browser: {
      engine: "chromium",
      version: browserVersion
    },
    viewports: {
      desktop: { width: 1440, height: 1000 },
      mobile: { width: 390, height: 844 }
    },
    artifacts: {
      desktop_full: {
        file: "desktop-full.webp",
        sha256: await sha256(desktopPath)
      },
      mobile_full: {
        file: "mobile-full.webp",
        sha256: await sha256(mobilePath)
      },
      accessibility: {
        file: "accessibility.json",
        sha256: await sha256(accessibilityPath)
      },
      lighthouse: {
        file: "lighthouse.json",
        sha256: await sha256(lighthousePath)
      },
      console: {
        file: "console-errors.json",
        sha256: await sha256(consolePath)
      }
    }
  };
  await writeFile(provenancePath, JSON.stringify(provenance, null, 2));

  const audit = {
    schema_version: 1,
    target: {
      requested_url: target.toString(),
      final_url: finalUrl,
      status: responseStatus
    },
    evidence: {
      provenance_file: "provenance.json",
      console_error_count: consoleEvents.filter((event) => event.type === "error").length,
      accessibility_violation_count: axeResults?.violations?.length ?? 0,
      accessibility_critical_or_serious: (axeResults?.violations || []).filter(
        (item) => item.impact === "critical" || item.impact === "serious"
      ).length
    },
    lighthouse: {
      performance: categoryScore(lighthouse, "performance"),
      accessibility: categoryScore(lighthouse, "accessibility"),
      best_practices: categoryScore(lighthouse, "best-practices"),
      seo: categoryScore(lighthouse, "seo")
    },
    generated_at: new Date().toISOString()
  };
  await writeFile(auditPath, JSON.stringify(audit, null, 2));

  process.stdout.write(JSON.stringify({ ok: true, output_dir: outputDir, audit }, null, 2) + "\n");
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exit(1);
});
