#!/usr/bin/env node
import { chromium } from "playwright";
import { mkdirSync } from "fs";

const DIR = "screenshots/tauri";
mkdirSync(DIR, { recursive: true });

async function main() {
  // Connect to WebView2 via CDP
  const browser = await chromium.connectOverCDP("http://localhost:9222");
  const contexts = browser.contexts();
  const page = contexts[0]?.pages()[0];
  if (!page) { console.error("No page found"); process.exit(1); }

  console.log("Connected to Tauri WebView2");
  console.log("URL:", page.url());

  // Wait for models to load (sidecar needs time)
  console.log("Waiting for models to load...");
  await page.waitForTimeout(5000);

  let step = 0;
  const snap = async (name) => {
    step++;
    await page.screenshot({ path: `${DIR}/${String(step).padStart(2, "0")}_${name}.png` });
    console.log(`${step}. ${name}`);
  };

  const clickTab = async (text) => {
    // Tab buttons in the tab bar
    const tab = page.locator('button', { hasText: text }).first();
    await tab.click({ timeout: 3000 }).catch(e =>
      console.log(`  WARN: tab "${text}": ${e.message.split('\n')[0]}`)
    );
    await page.waitForTimeout(800);
  };

  // Check header status
  const headerText = await page.locator('header, [class*="h-12"], [class*="shrink-0"]').first().textContent().catch(() => "");
  console.log("Header:", headerText?.slice(0, 100));

  // ═══ ANALYSIS ═══
  console.log("\n=== ANALYSIS TAB ===");
  await snap("analysis_init");

  // Check model status
  const statusEl = await page.locator('.truncate').first().textContent().catch(() => "unknown");
  console.log("Status:", statusEl);

  // Click Run button
  const runBtn = page.locator('button', { hasText: /Run|Enter/ }).first();
  const runVisible = await runBtn.isVisible({ timeout: 1000 }).catch(() => false);
  console.log("Run button visible:", runVisible);

  if (runVisible) {
    const runDisabled = await runBtn.isDisabled().catch(() => true);
    console.log("Run button disabled:", runDisabled);
    if (!runDisabled) {
      await runBtn.click();
      console.log("Clicked Run, waiting for prediction...");
      await page.waitForTimeout(8000);
      await snap("analysis_predicted");
    } else {
      console.log("Run button disabled - models may not be ready");
      // Wait longer
      await page.waitForTimeout(30000);
      const status2 = await page.locator('.truncate').first().textContent().catch(() => "unknown");
      console.log("Status after wait:", status2);
      await snap("analysis_after_wait");

      // Try again
      const runDisabled2 = await runBtn.isDisabled().catch(() => true);
      if (!runDisabled2) {
        await runBtn.click();
        console.log("Clicked Run (2nd attempt)...");
        await page.waitForTimeout(8000);
        await snap("analysis_predicted");
      }
    }
  }

  // Try preset
  const presetSel = page.locator('select').first();
  if (await presetSel.isVisible({ timeout: 1000 }).catch(() => false)) {
    const opts = await presetSel.locator('option').allTextContents();
    console.log("Presets:", opts.join(', '));
  }

  // ═══ STRESS FIELD ═══
  console.log("\n=== STRESS FIELD TAB ===");
  await clickTab("Stress Field");
  await snap("stress_field");

  // Click Compute
  const computeBtn = page.locator('button', { hasText: 'Compute' }).first();
  if (await computeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await computeBtn.click();
    await page.waitForTimeout(3000);
    await snap("stress_computed");
  }

  // ═══ LAMINATE ═══
  console.log("\n=== LAMINATE TAB ===");
  await clickTab("Laminate");
  await snap("laminate_stiffness");

  await clickTab("Ply Stress");
  await snap("laminate_ply_stress");

  await clickTab("Failure");
  await snap("laminate_failure");

  // ═══ EXPLORER ═══
  console.log("\n=== EXPLORER TAB ===");
  await clickTab("Explorer");
  await snap("explorer_1d");

  // Check if Run button is available (needs models)
  const expRunBtn = page.locator('button', { hasText: /Run|Models/ }).first();
  const expRunText = await expRunBtn.textContent().catch(() => "");
  console.log("Explorer Run button:", expRunText);

  if (expRunText === "Run") {
    await expRunBtn.click();
    console.log("Running 1D sweep...");
    // Wait for sweep to complete
    await page.waitForTimeout(15000);
    await snap("explorer_1d_results");
  }

  // 2D Sweep
  await clickTab("2D Sweep");
  await snap("explorer_2d");

  // Monte Carlo
  await clickTab("Monte Carlo");
  await snap("explorer_mc");

  // Sensitivity
  await clickTab("Sensitivity");
  await snap("explorer_sens");

  // ═══ PROJECT ═══
  console.log("\n=== PROJECT TAB ===");
  await clickTab("Project");
  await snap("project");

  // Save a snapshot
  const snapInput = page.locator('input[placeholder*="Snapshot"]').first();
  if (await snapInput.isVisible({ timeout: 1000 }).catch(() => false)) {
    await snapInput.fill("Test Snapshot");
    const saveBtn = page.locator('button', { hasText: 'Save' }).first();
    await saveBtn.click();
    await page.waitForTimeout(500);
    await snap("project_saved");
  }

  await browser.close();
  console.log(`\n✓ Done — ${step} screenshots in ${DIR}/`);
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
