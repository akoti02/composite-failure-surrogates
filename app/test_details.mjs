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

  // ═══ LAMINATE DEEP CHECK ═══
  console.log("=== LAMINATE STIFFNESS DEEP CHECK ===");
  await clickTab("Laminate");
  await page.waitForTimeout(500);
  await clickTab("Stiffness");
  await page.waitForTimeout(500);

  // Get all content in the main area
  const mainContent = await page.locator('main, [class*="flex-1"], [class*="overflow"]').last().textContent().catch(() => "");
  console.log("Stiffness content (first 500 chars):");
  console.log(mainContent.slice(0, 500));

  // Look for matrix labels
  const matrixLabels = await page.locator('text=/[ABD]|A₁₁|stiffness|matrix/i').allTextContents().catch(() => []);
  console.log("\nMatrix labels:", matrixLabels.slice(0, 10).join(' | '));

  // Check for any numbers that look like stiffness values
  const allNums = await page.locator('[class*="mono"], [class*="tabular"], td').allTextContents().catch(() => []);
  console.log("Mono/tabular values:", allNums.slice(0, 15).join(' | '));

  // ═══ LAMINATE PLY STRESS ═══
  console.log("\n=== PLY STRESS DEEP CHECK ===");
  await clickTab("Ply Stress");
  await page.waitForTimeout(500);

  const plyContent = await page.locator('main, [class*="flex-1"], [class*="overflow"]').last().textContent().catch(() => "");
  console.log("Ply stress content (first 500 chars):");
  console.log(plyContent.slice(0, 500));

  // ═══ LAMINATE FAILURE ═══
  console.log("\n=== FAILURE DEEP CHECK ===");
  await clickTab("Failure");
  await page.waitForTimeout(500);

  const failContent = await page.locator('main, [class*="flex-1"], [class*="overflow"]').last().textContent().catch(() => "");
  console.log("Failure content (first 500 chars):");
  console.log(failContent.slice(0, 500));

  // ═══ EXPLORER 2D/MC/SENS CHECK ═══
  console.log("\n=== EXPLORER SUB-TABS CHECK ===");
  await clickTab("Explorer");
  await page.waitForTimeout(500);

  // 2D Sweep
  await clickTab("2D Sweep");
  await page.waitForTimeout(300);
  const sweep2d = await page.evaluate(() => {
    const main = document.querySelector('main') || document.body;
    return main.innerText;
  });
  console.log("2D Sweep full text (first 300):", sweep2d.slice(0, 300));

  // Check for Run button in 2D
  const run2d = page.locator('button', { hasText: /^Run$/ }).first();
  console.log("2D Run visible:", await run2d.isVisible({ timeout: 500 }).catch(() => false));

  // Monte Carlo
  await clickTab("Monte Carlo");
  await page.waitForTimeout(300);
  const mc = await page.evaluate(() => document.querySelector('main')?.innerText || document.body.innerText);
  console.log("\nMC full text (first 300):", mc.slice(0, 300));
  const runMC = page.locator('button', { hasText: /^Run$/ }).first();
  console.log("MC Run visible:", await runMC.isVisible({ timeout: 500 }).catch(() => false));

  // Sensitivity
  await clickTab("Sensitivity");
  await page.waitForTimeout(300);
  const sens = await page.evaluate(() => document.querySelector('main')?.innerText || document.body.innerText);
  console.log("\nSens full text (first 300):", sens.slice(0, 300));
  const runSens = page.locator('button', { hasText: /^Run$/ }).first();
  console.log("Sens Run visible:", await runSens.isVisible({ timeout: 500 }).catch(() => false));

  // ═══ PROJECT HISTORY CHECK ═══
  console.log("\n=== PROJECT DEEP CHECK ===");
  await clickTab("Project");
  await page.waitForTimeout(500);

  const projText = await page.evaluate(() => document.querySelector('main')?.innerText || document.body.innerText);
  console.log("Project full text (first 600):");
  console.log(projText.slice(0, 600));

  await browser.close();
  console.log("\n✓ Detail check complete");
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
