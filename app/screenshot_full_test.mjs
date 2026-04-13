#!/usr/bin/env node
import { chromium } from "playwright";
import { mkdirSync } from "fs";

const BASE = "http://localhost:4174";
const DIR = "screenshots/verify";
mkdirSync(DIR, { recursive: true });

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

  await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(2000);
  await page.evaluate(() => {
    const splash = document.querySelector('.fixed.inset-0.z-50');
    if (splash) splash.remove();
  });
  await page.waitForTimeout(500);

  let step = 0;
  const snap = async (name) => {
    step++;
    await page.screenshot({ path: `${DIR}/${String(step).padStart(2, "0")}_${name}.png` });
    console.log(`${step}. ${name}`);
  };

  const clickText = async (text) => {
    await page.locator('button', { hasText: text }).first().click({ timeout: 3000 }).catch(e =>
      console.log(`  WARN: couldn't click "${text}": ${e.message.split('\n')[0]}`)
    );
    await page.waitForTimeout(600);
  };

  // ═══ ANALYSIS ═══
  console.log("\n=== ANALYSIS TAB ===");
  await snap("analysis_default");

  // Scroll to see full left panel
  await page.evaluate(() => {
    const panel = document.querySelector('.overflow-y-auto');
    if (panel) panel.scrollTop = 300;
  });
  await page.waitForTimeout(300);
  await snap("analysis_scrolled_inputs");

  // Click + button on Pressure X a few times to increase it
  const plusBtns = page.locator('button:has-text("+")');
  const plusCount = await plusBtns.count();
  console.log(`  Found ${plusCount} + buttons`);

  // Use preset instead (reliable)
  await page.locator('select').first().selectOption({ label: "Biaxial Loading" });
  await page.waitForTimeout(500);
  await page.evaluate(() => window.scrollTo(0, 0));
  await snap("analysis_biaxial_preset");

  await page.locator('select').first().selectOption({ label: "Severe Multi-Defect" });
  await page.waitForTimeout(500);
  await snap("analysis_severe_preset");

  // Scroll to see all 5 defect tabs
  await page.evaluate(() => {
    const panel = document.querySelector('.overflow-y-auto');
    if (panel) panel.scrollTop = 200;
  });
  await page.waitForTimeout(300);
  await snap("analysis_severe_defects");

  await page.locator('select').first().selectOption({ label: "Edge Crack (Critical)" });
  await page.waitForTimeout(500);
  await snap("analysis_edge_crack");

  await page.locator('select').first().selectOption({ label: "Light Surface Damage" });
  await page.waitForTimeout(500);
  await snap("analysis_light_damage");

  // Reset to default
  await page.locator('select').first().selectOption({ label: "Single Central Crack" });
  await page.waitForTimeout(500);
  await snap("analysis_single_crack");

  // ═══ STRESS FIELD ═══
  console.log("\n=== STRESS FIELD TAB ===");
  await clickText("Stress Field");
  await snap("stress_empty");

  await clickText("Compute");
  await page.waitForTimeout(3000);
  await snap("stress_vonmises");

  // Change fields - find the field select (has von Mises option)
  const allSelects = await page.locator('select').all();
  let fieldSel = null, cmapSel = null, matSel = null;
  for (const s of allSelects) {
    const opts = await s.locator('option').allTextContents();
    const j = opts.join(',');
    if (j.includes('von Mises') && j.includes('Tsai-Wu')) fieldSel = s;
    else if (j.includes('turbo') && j.includes('viridis')) cmapSel = s;
    else if (j.includes('T300/5208') && !j.includes('Presets')) matSel = s;
  }

  if (fieldSel) {
    await fieldSel.selectOption("sigX");
    await page.waitForTimeout(300);
    await snap("stress_sigX");

    await fieldSel.selectOption("tauXY");
    await page.waitForTimeout(300);
    await snap("stress_tauXY");

    await fieldSel.selectOption("tsaiWu");
    await page.waitForTimeout(300);
    await snap("stress_tsaiWu");

    await fieldSel.selectOption("vonMises");
  } else {
    console.log("  WARN: field select not found");
  }

  if (cmapSel) {
    await cmapSel.selectOption("viridis");
    await page.waitForTimeout(300);
    await snap("stress_viridis");

    await cmapSel.selectOption("coolwarm");
    await page.waitForTimeout(300);
    await snap("stress_coolwarm");

    await cmapSel.selectOption("turbo");
  }

  if (matSel) {
    const matOpts = await matSel.locator('option').allTextContents();
    console.log(`  Materials: ${matOpts.join(', ')}`);
  }

  // ═══ LAMINATE ═══
  console.log("\n=== LAMINATE TAB ===");
  await clickText("Laminate");
  await snap("lam_stiffness");

  await clickText("Ply Stress");
  await snap("lam_ply_stress");

  await clickText("Failure");
  await snap("lam_failure");

  // Progressive failure
  const checkbox = page.locator('input[type="checkbox"]').first();
  if (await checkbox.isVisible({ timeout: 1000 }).catch(() => false)) {
    await checkbox.check();
    await page.waitForTimeout(800);
    await snap("lam_progressive");
    await checkbox.uncheck();
  }

  // Different laminate codes
  const codeInput = page.locator('input[placeholder="[0/±45/90]s"]').first();
  if (await codeInput.isVisible({ timeout: 1000 }).catch(() => false)) {
    await clickText("Stiffness");

    await codeInput.fill("[0/90]4s");
    await page.waitForTimeout(400);
    await snap("lam_crossply_0_90");

    await codeInput.fill("[±45]2s");
    await page.waitForTimeout(400);
    await snap("lam_pm45");

    await codeInput.fill("[0]8");
    await page.waitForTimeout(400);
    await snap("lam_unidirectional");

    await codeInput.fill("[0/90/±45]s");
    await page.waitForTimeout(400);
    await snap("lam_quasi_iso_alt");

    // Invalid code
    await codeInput.fill("garbage");
    await page.waitForTimeout(400);
    await snap("lam_invalid_code");

    // Restore
    await codeInput.fill("[0/±45/90]s");
    await page.waitForTimeout(300);
  }

  // Use laminate preset
  const lamPresetSel = page.locator('select').filter({ has: page.locator('option', { hasText: 'Select preset...' }) }).first();
  if (await lamPresetSel.isVisible({ timeout: 500 }).catch(() => false)) {
    const presets = await lamPresetSel.locator('option').allTextContents();
    console.log(`  Laminate presets: ${presets.slice(1).join(', ')}`);
  }

  // ═══ EXPLORER ═══
  console.log("\n=== EXPLORER TAB ===");
  await clickText("Explorer");
  await snap("explorer_1d");

  // Check what parameter options are available
  const expSelects = await page.locator('select').all();
  for (const s of expSelects) {
    const opts = await s.locator('option').allTextContents();
    if (opts.some(o => o.includes('Pressure'))) {
      console.log(`  Param options: ${opts.join(', ')}`);
      break;
    }
  }

  await clickText("2D Sweep");
  await snap("explorer_2d");

  await clickText("Monte Carlo");
  await snap("explorer_mc");

  await clickText("Sensitivity");
  await snap("explorer_sens");

  // ═══ PROJECT ═══
  console.log("\n=== PROJECT TAB ===");
  await clickText("Project");
  await snap("project_snapshots");

  await clickText("Compare");
  await snap("project_compare");

  await clickText("History");
  await snap("project_history");

  // Check buttons
  const expBtn = page.locator('button', { hasText: 'Export' });
  const impBtn = page.locator('button', { hasText: 'Import' });
  console.log(`  Export visible: ${await expBtn.first().isVisible({ timeout: 500 }).catch(() => false)}`);
  console.log(`  Import visible: ${await impBtn.first().isVisible({ timeout: 500 }).catch(() => false)}`);

  await browser.close();
  console.log(`\n✓ Done — ${step} screenshots in ${DIR}/`);
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
