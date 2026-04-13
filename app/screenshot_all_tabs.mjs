#!/usr/bin/env node
import { chromium } from "playwright";

const BASE = "http://localhost:4174";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

  await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(1500);

  // Force-remove the splash screen overlay
  await page.evaluate(() => {
    const splash = document.querySelector('.fixed.inset-0.z-50');
    if (splash) splash.remove();
  });
  await page.waitForTimeout(500);

  // Screenshot Analysis tab (default)
  await page.screenshot({ path: "screenshots/01_analysis.png" });
  console.log("1. Analysis tab");

  // Click each tab by matching the icon+label pattern
  const tabNames = [
    { label: "Stress Field", file: "02_stress_field" },
    { label: "Laminate", file: "03_laminate" },
    { label: "Explorer", file: "04_explorer" },
    { label: "Project", file: "05_project" },
  ];

  for (const tab of tabNames) {
    try {
      await page.locator(`button`, { hasText: tab.label }).first().click({ timeout: 3000 });
      await page.waitForTimeout(600);
      await page.screenshot({ path: `screenshots/${tab.file}.png` });
      console.log(`  ${tab.label} captured`);

      // Sub-tabs for Laminate
      if (tab.label === "Laminate") {
        for (const sub of ["Ply Stress", "Failure"]) {
          const btn = page.locator(`button`, { hasText: sub }).first();
          if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
            await btn.click({ timeout: 2000 });
            await page.waitForTimeout(400);
            await page.screenshot({ path: `screenshots/03_laminate_${sub.toLowerCase().replace(/\s+/g, '_')}.png` });
            console.log(`    ${sub} captured`);
          }
        }
        // Enable progressive failure
        const checkbox = page.locator('input[type="checkbox"]').first();
        if (await checkbox.isVisible({ timeout: 1000 }).catch(() => false)) {
          await checkbox.check();
          await page.waitForTimeout(500);
          await page.screenshot({ path: "screenshots/03_laminate_progressive.png" });
          console.log("    Progressive failure captured");
        }
      }

      // Sub-tabs for Explorer
      if (tab.label === "Explorer") {
        for (const mode of ["2D Sweep", "Monte Carlo", "Sensitivity"]) {
          const btn = page.locator(`button`, { hasText: mode }).first();
          if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
            await btn.click({ timeout: 2000 });
            await page.waitForTimeout(400);
            await page.screenshot({ path: `screenshots/04_explorer_${mode.toLowerCase().replace(/\s+/g, '_')}.png` });
            console.log(`    ${mode} captured`);
          }
        }
      }

      // Sub-tabs for Project
      if (tab.label === "Project") {
        for (const sub of ["Compare", "History"]) {
          const btn = page.locator(`button`, { hasText: sub }).first();
          if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
            await btn.click({ timeout: 2000 });
            await page.waitForTimeout(400);
            await page.screenshot({ path: `screenshots/05_project_${sub.toLowerCase()}.png` });
            console.log(`    ${sub} captured`);
          }
        }
      }

    } catch (err) {
      console.error(`  ERROR ${tab.label}: ${err.message.split('\n')[0]}`);
    }
  }

  // Go back to Analysis, try 5 defects
  try {
    await page.locator(`button`, { hasText: "Analysis" }).first().click({ timeout: 3000 });
    await page.waitForTimeout(500);

    // Try changing defect count slider
    const slider = page.locator('input[type="range"]').first();
    if (await slider.isVisible({ timeout: 1000 }).catch(() => false)) {
      await slider.evaluate((el) => {
        el.value = "5";
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
      await page.waitForTimeout(600);
      await page.screenshot({ path: "screenshots/01_analysis_5defects.png" });
      console.log("  Analysis 5 defects captured");
    }
  } catch (err) {
    console.error(`  ERROR Analysis 5 defects: ${err.message.split('\n')[0]}`);
  }

  await browser.close();
  console.log("\nDone.");
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
