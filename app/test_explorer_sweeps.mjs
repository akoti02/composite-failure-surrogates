#!/usr/bin/env node
import { chromium } from "playwright";

async function main() {
  const browser = await chromium.connectOverCDP("http://localhost:9222");
  const page = browser.contexts()[0]?.pages()[0];
  if (!page) { console.error("No page found"); process.exit(1); }

  const clickTab = async (text) => {
    const tab = page.locator('button', { hasText: text }).first();
    await tab.click({ timeout: 3000 }).catch(e =>
      console.log(`  WARN: tab "${text}": ${e.message.split('\n')[0]}`)
    );
    await page.waitForTimeout(800);
  };

  // Go to Explorer
  await clickTab("Explorer");
  await page.waitForTimeout(500);

  // ═══ 2D SWEEP ═══
  console.log("=== 2D SWEEP ===");
  await clickTab("2D Sweep");
  await page.waitForTimeout(300);

  const run2d = page.locator('button', { hasText: /^Run$/ }).first();
  if (await run2d.isVisible({ timeout: 1000 }).catch(() => false)) {
    console.log("Running 2D sweep...");
    await run2d.click();

    // Wait up to 60s
    for (let i = 0; i < 60; i++) {
      await page.waitForTimeout(1000);
      const disabled = await run2d.isDisabled().catch(() => false);
      if (!disabled && i > 2) {
        console.log(`2D sweep completed after ${i+1}s`);
        break;
      }
      if (i % 10 === 9) console.log(`  ...still running (${i+1}s)`);
    }

    // Check output
    const svgs = await page.locator('svg').count();
    const canvases = await page.locator('canvas').count();
    console.log(`Charts — SVGs: ${svgs}, Canvases: ${canvases}`);

    const chartText = await page.locator('svg text').allTextContents().catch(() => []);
    console.log("Chart labels:", chartText.slice(0, 10).join(', '));
  }

  // ═══ MONTE CARLO ═══
  console.log("\n=== MONTE CARLO ===");
  await clickTab("Monte Carlo");
  await page.waitForTimeout(300);

  const runMC = page.locator('button', { hasText: /^Run$/ }).first();
  if (await runMC.isVisible({ timeout: 1000 }).catch(() => false)) {
    console.log("Running Monte Carlo...");
    await runMC.click();

    for (let i = 0; i < 60; i++) {
      await page.waitForTimeout(1000);
      const disabled = await runMC.isDisabled().catch(() => false);
      if (!disabled && i > 2) {
        console.log(`MC completed after ${i+1}s`);
        break;
      }
      if (i % 10 === 9) console.log(`  ...still running (${i+1}s)`);
    }

    const svgs = await page.locator('svg').count();
    console.log(`MC Charts — SVGs: ${svgs}`);
    const chartText = await page.locator('svg text').allTextContents().catch(() => []);
    console.log("MC labels:", chartText.slice(0, 10).join(', '));
  }

  // ═══ SENSITIVITY ═══
  console.log("\n=== SENSITIVITY ===");
  await clickTab("Sensitivity");
  await page.waitForTimeout(300);

  const runSens = page.locator('button', { hasText: /^Run$/ }).first();
  if (await runSens.isVisible({ timeout: 1000 }).catch(() => false)) {
    console.log("Running Sensitivity...");
    await runSens.click();

    for (let i = 0; i < 90; i++) {
      await page.waitForTimeout(1000);
      const disabled = await runSens.isDisabled().catch(() => false);
      if (!disabled && i > 2) {
        console.log(`Sensitivity completed after ${i+1}s`);
        break;
      }
      if (i % 10 === 9) console.log(`  ...still running (${i+1}s)`);
    }

    const svgs = await page.locator('svg').count();
    console.log(`Sens Charts — SVGs: ${svgs}`);
    const chartText = await page.locator('svg text').allTextContents().catch(() => []);
    console.log("Sens labels:", chartText.slice(0, 15).join(', '));
  }

  await browser.close();
  console.log("\n✓ Explorer sweeps complete");
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
