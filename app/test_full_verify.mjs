#!/usr/bin/env node
import { chromium } from "playwright";

async function main() {
  const browser = await chromium.connectOverCDP("http://localhost:9222");
  const page = browser.contexts()[0]?.pages()[0];
  if (!page) { console.error("No page found"); process.exit(1); }

  console.log("Connected. URL:", page.url());

  const clickTab = async (text) => {
    const tab = page.locator('button', { hasText: text }).first();
    await tab.click({ timeout: 3000 }).catch(e =>
      console.log(`  WARN: tab "${text}": ${e.message.split('\n')[0]}`)
    );
    await page.waitForTimeout(800);
  };

  // ═══ 1. ANALYSIS TAB ═══
  console.log("\n=== ANALYSIS ===");
  await clickTab("Analysis");
  await page.waitForTimeout(500);

  // Header status
  const statusText = await page.locator('.truncate').first().textContent().catch(() => "?");
  console.log("Status:", statusText);

  // Check preset selector
  const presetSel = page.locator('select').first();
  if (await presetSel.isVisible({ timeout: 1000 }).catch(() => false)) {
    const opts = await presetSel.locator('option').allTextContents();
    console.log("Presets:", opts.join(', '));
  }

  // Check inputs are visible
  const inputs = await page.locator('input[type="number"]').count();
  console.log("Number inputs visible:", inputs);

  // Check if canvas is visible
  const canvas = page.locator('svg, canvas').first();
  console.log("Canvas/SVG visible:", await canvas.isVisible({ timeout: 1000 }).catch(() => false));

  // Run prediction
  const runBtn = page.locator('button', { hasText: /Run|Enter/ }).first();
  const runVisible = await runBtn.isVisible({ timeout: 1000 }).catch(() => false);
  const runDisabled = runVisible ? await runBtn.isDisabled().catch(() => true) : true;
  console.log("Run btn:", runVisible ? (runDisabled ? "visible but disabled" : "READY") : "not visible");

  if (runVisible && !runDisabled) {
    await runBtn.click();
    await page.waitForTimeout(5000);
    const status2 = await page.locator('.truncate').first().textContent().catch(() => "?");
    console.log("After Run:", status2);

    // Check verdict
    const verdict = await page.locator('text=/FAILURE|SAFE|PREDICTED/').first().textContent().catch(() => "none");
    console.log("Verdict:", verdict);

    // Check result values
    const resultTexts = await page.locator('[class*="font-mono"], [class*="tabular"]').allTextContents().catch(() => []);
    console.log("Result values:", resultTexts.slice(0, 10).join(' | '));
  }

  // ═══ 2. STRESS FIELD ═══
  console.log("\n=== STRESS FIELD ===");
  await clickTab("Stress Field");
  await page.waitForTimeout(500);

  // Check canvas
  const sfCanvas = page.locator('canvas').first();
  console.log("Stress canvas visible:", await sfCanvas.isVisible({ timeout: 1000 }).catch(() => false));

  // Check material dropdown
  const matSel = page.locator('select').first();
  if (await matSel.isVisible({ timeout: 1000 }).catch(() => false)) {
    const matOpts = await matSel.locator('option').allTextContents();
    console.log("Materials:", matOpts.join(', '));
  }

  // Check compute button
  const computeBtn = page.locator('button', { hasText: 'Compute' }).first();
  if (await computeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await computeBtn.click();
    await page.waitForTimeout(3000);
    console.log("Compute clicked, checking results...");

    // Check if stress values appeared
    const stressInfo = await page.locator('text=/max|σ|stress|MPa/i').first().textContent().catch(() => "no stress info");
    console.log("Stress info:", stressInfo);
  }

  // ═══ 3. LAMINATE ═══
  console.log("\n=== LAMINATE ===");
  await clickTab("Laminate");
  await page.waitForTimeout(500);

  // Check sub-tabs
  const subTabs = await page.locator('button').allTextContents();
  const lamSubTabs = subTabs.filter(t => /Stiffness|Ply Stress|Failure|Compliance|Engineering/i.test(t));
  console.log("Sub-tabs found:", lamSubTabs.join(', '));

  // Check laminate code input
  const lamInput = page.locator('input[placeholder*="Laminate"], input[value*="["]').first();
  const lamCode = await lamInput.inputValue().catch(() => "not found");
  console.log("Laminate code:", lamCode);

  // Stiffness tab - check ABD matrix
  await clickTab("Stiffness");
  await page.waitForTimeout(300);
  const abdCells = await page.locator('table td, [class*="grid"] [class*="font-mono"]').count();
  console.log("ABD matrix cells:", abdCells);

  // Ply Stress tab
  await clickTab("Ply Stress");
  await page.waitForTimeout(300);
  const plyRows = await page.locator('table tr, [class*="ply"]').count();
  console.log("Ply stress rows:", plyRows);

  // Failure tab
  await clickTab("Failure");
  await page.waitForTimeout(300);
  const failureText = await page.locator('text=/Tsai|Hashin|failure|FI|margin/i').first().textContent().catch(() => "none");
  console.log("Failure info:", failureText);

  // ═══ 4. EXPLORER ═══
  console.log("\n=== EXPLORER ===");
  await clickTab("Explorer");
  await page.waitForTimeout(500);

  // Check mode tabs
  const expButtons = await page.locator('button').allTextContents();
  const expModes = expButtons.filter(t => /1D|2D|Monte|Sensitivity/i.test(t));
  console.log("Explorer modes:", expModes.join(', '));

  // Check Run button
  const expRunBtn = page.locator('button', { hasText: /^Run$/ }).first();
  const expRunVisible = await expRunBtn.isVisible({ timeout: 1000 }).catch(() => false);
  console.log("Explorer Run visible:", expRunVisible);

  if (expRunVisible) {
    const expRunDisabled = await expRunBtn.isDisabled().catch(() => true);
    console.log("Explorer Run disabled:", expRunDisabled);

    if (!expRunDisabled) {
      console.log("Running 1D sweep...");
      await expRunBtn.click();

      // Wait for sweep — poll for completion
      for (let i = 0; i < 30; i++) {
        await page.waitForTimeout(1000);
        const btnText = await expRunBtn.textContent().catch(() => "?");
        if (btnText === "Run") {
          console.log(`Sweep completed after ${i+1}s`);
          break;
        }
        if (i % 5 === 4) console.log(`  ...still running (${i+1}s)`);
      }

      // Check for chart output
      const svgChart = page.locator('svg').first();
      const chartVisible = await svgChart.isVisible({ timeout: 2000 }).catch(() => false);
      console.log("Chart SVG visible:", chartVisible);

      // Check for data points
      const circles = await page.locator('svg circle').count();
      const paths = await page.locator('svg path').count();
      const lines = await page.locator('svg line').count();
      console.log(`Chart elements — circles:${circles} paths:${paths} lines:${lines}`);

      // Check axis labels
      const axisText = await page.locator('svg text').allTextContents().catch(() => []);
      console.log("Axis labels:", axisText.slice(0, 10).join(', '));
    }
  }

  // Check 2D sweep tab
  await clickTab("2D Sweep");
  await page.waitForTimeout(300);
  const sweep2dContent = await page.locator('[class*="explorer"], [class*="sweep"]').first().textContent().catch(() => "");
  console.log("2D sweep section length:", sweep2dContent.length);

  // Check Monte Carlo tab
  await clickTab("Monte Carlo");
  await page.waitForTimeout(300);
  const mcContent = await page.locator('[class*="explorer"], [class*="monte"]').first().textContent().catch(() => "");
  console.log("MC section length:", mcContent.length);

  // Check Sensitivity tab
  await clickTab("Sensitivity");
  await page.waitForTimeout(300);
  const sensContent = await page.locator('[class*="explorer"], [class*="sens"]').first().textContent().catch(() => "");
  console.log("Sens section length:", sensContent.length);

  // ═══ 5. PROJECT ═══
  console.log("\n=== PROJECT ===");
  await clickTab("Project");
  await page.waitForTimeout(500);

  // Check snapshots
  const snapshots = await page.locator('text=/Test Snapshot|snapshot/i').count();
  console.log("Snapshots found:", snapshots);

  // Check history entries
  const historyEntries = await page.locator('[class*="history"], text=/History/i').first().textContent().catch(() => "no history section");
  console.log("History:", historyEntries?.slice(0, 100));

  // Check export button
  const exportBtn = page.locator('button', { hasText: /Export|Download/i }).first();
  console.log("Export btn visible:", await exportBtn.isVisible({ timeout: 1000 }).catch(() => false));

  await browser.close();
  console.log("\n✓ Full verification complete");
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
