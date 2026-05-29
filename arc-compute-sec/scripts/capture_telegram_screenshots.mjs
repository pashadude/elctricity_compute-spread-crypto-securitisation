import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..');
const OUT_DIR = process.env.TELEGRAM_SCREENSHOT_DIR
  ? path.resolve(process.env.TELEGRAM_SCREENSHOT_DIR)
  : path.join(PROJECT_ROOT, 'logs', 'telegram_screenshots');
const BASE_URL = (
  process.env.TELEGRAM_SCREENSHOT_BASE_URL
  || process.env.PUBLIC_BASE_URL
  || 'http://127.0.0.1:8080'
).replace(/\/+$/, '');
const SETTLE_MS = Number(process.env.TELEGRAM_SCREENSHOT_SETTLE_MS || 3000);

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function gotoMini(page, screen) {
  const suffix = screen ? `?screen=${encodeURIComponent(screen)}` : '';
  const title = screen ? screenTitle(screen) : 'Botozen Power';
  let lastError;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      await page.goto(`${BASE_URL}/tg${suffix}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForLoadState('domcontentloaded');
      await page.getByText(title).first().waitFor({ timeout: 20000 });
      await sleep(SETTLE_MS);
      return;
    } catch (err) {
      lastError = err;
      await sleep(1000);
    }
  }
  throw lastError;
}

function screenTitle(screen) {
  const titles = {
    dashboard: 'Mock Contract',
    portfolio: 'My Portfolio',
    scouting: 'Agent Scouting',
    updates: "What's New",
  };
  return titles[screen] || 'Botozen Power';
}

async function scrollToText(page, text) {
  const target = page.getByText(text).first();
  try {
    await target.waitFor({ timeout: 10000 });
    await target.scrollIntoViewIfNeeded();
    await sleep(400);
    return true;
  } catch (_err) {
    return false;
  }
}

async function capture(page, filename) {
  const output = path.join(OUT_DIR, filename);
  await page.screenshot({ path: output, fullPage: false });
  return output;
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true });
  const outputs = [];

  await gotoMini(page, '');
  outputs.push(await capture(page, 'miniapp-home.png'));

  await gotoMini(page, 'portfolio');
  outputs.push(await capture(page, 'miniapp-portfolio.png'));

  await gotoMini(page, 'updates');
  outputs.push(await capture(page, 'miniapp-updates.png'));

  await gotoMini(page, 'dashboard');
  outputs.push(await capture(page, 'miniapp-contract.png'));

  await gotoMini(page, 'dashboard');
  await scrollToText(page, 'Index catalog');
  outputs.push(await capture(page, 'indexes-spreads.png'));

  await gotoMini(page, 'dashboard');
  await scrollToText(page, 'Profitability ledger');
  outputs.push(await capture(page, 'profitability.png'));

  await gotoMini(page, 'scouting');
  await scrollToText(page, 'Venue evidence');
  outputs.push(await capture(page, 'venue-copy.png'));

  await browser.close();
  console.log(JSON.stringify({ ok: true, base_url: BASE_URL, output_dir: OUT_DIR, files: outputs }, null, 2));
}

main().catch(err => {
  console.error(err?.stack || err);
  process.exit(1);
});
