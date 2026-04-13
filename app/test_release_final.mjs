#!/usr/bin/env node
import { chromium } from "playwright";

async function main() {
  const browser = await chromium.connectOverCDP("http://localhost:9222");
  const page = browser.contexts()[0]?.pages()[0];
  if (!page) { console.error("No page found"); process.exit(1); }

  console.log("Connected to RELEASE build. URL:", page.url());

  const clickTab = async (text) => {
    // Use exact-ish matching to avoid clicking wrong buttons
    const tabs = await page.locator('button').all();
    for (const tab of tabs) {
      const t = await tab.textContent().catch(() => "");
      if (t.trim() === text || t.includes(text)) {
        await tab.click({ timeout: 3000 }).catch(() => {});
        await page.waitForTimeout(600);
        return;
      }
    }
    console.log(`  WARN: tab "${text}" not found`);
  };

  // Wait for models to load (release sidecar takes longer to start)
  console.log("Waiting for sidecar + model loading...");
  let modelStatus = "";
  for (let i = 0; i < 40; i++) {
    await page.waitForTimeout(1000);
    modelStatus = await page.locator('.truncate').first().textContent().catch(() => "");
    if (modelStatus.includes("16 models") || modelStatus.includes("Ready")) {
      console.log(`[${i+1}s] ${modelStatus}`);
      break;
    }
    if (i % 5 === 4) console.log(`[${i+1}s] ${modelStatus}`);
  }

  if (!modelStatus.includes("16")) {
    console.log("PROBLEM: Models not loaded. Status:", modelStatus);
    // Try calling load_models directly
    const loadResp = await page.evaluate(async () => {
      const invoke = window.__TAURI__?.core?.invoke || window.__TAURI_INTERNALS__?.invoke;
      if (!invoke) return "No invoke";
      try {
        const r = await invoke("load_models");
        return JSON.stringify(r);
      } catch (e) { return `Error: ${e}`; }
    });
    console.log("Direct load_models:", loadResp);
    await page.waitForTimeout(2000);
    modelStatus = await page.locator('.truncate').first().textContent().catch(() => "");
    console.log("Status after direct load:", modelStatus);
  }

  const PASS = "✓";
  const FAIL = "✗";
  const results = [];
  const check = (name, ok, detail = "") => {
    results.push({ name, ok, detail });
    console.log(`  ${ok ? PASS : FAIL} ${name}${detail ? ` — ${detail}` : ""}`);
  };

  // ═══════════════════════════════════════════════
  // 1. ANALYSIS TAB
  // ═══════════════════════════════════════════════
  console.log("\n══ ANALYSIS TAB ══");
  await clickTab("Analysis");
  await page.waitForTimeout(500);

  // Status check
  const status = await page.locator('.truncate').first().textContent().catch(() => "");
  check("Models loaded", status.includes("16 models"), status);

  // Preset selector
  const presetOpts = await page.locator('select option').allTextContents().catch(() => []);
  check("Presets available", presetOpts.length >= 5, presetOpts.join(", "));

  // Input fields
  const numInputs = await page.locator('input[type="number"]').count();
  check("Input fields present", numInputs >= 6, `${numInputs} fields`);

  // Canvas/SVG (plate visualization)
  const svgVisible = await page.locator('svg').first().isVisible({ timeout: 1000 }).catch(() => false);
  check("Plate canvas visible", svgVisible);

  // Run prediction
  const runBtn = page.locator('button', { hasText: /Run.*Enter/ }).first();
  const runEnabled = await runBtn.isEnabled({ timeout: 1000 }).catch(() => false);
  check("Run button enabled", runEnabled);

  if (runEnabled) {
    await runBtn.click();
    await page.waitForTimeout(5000);
    const afterRun = await page.locator('.truncate').first().textContent().catch(() => "");
    check("Prediction completes", afterRun.includes("complete") || afterRun.includes("Analysis"), afterRun);

    // Verdict
    const verdictEl = await page.locator('text=/FAILURE|SAFE/').first().textContent().catch(() => "none");
    check("Verdict displayed", verdictEl !== "none", verdictEl);

    // Result values (check tabular-nums for actual numbers)
    const tabNums = await page.locator('.tabular-nums').allTextContents();
    const nonZero = tabNums.filter(t => t.trim() && t.trim() !== "0" && t.trim() !== "0.00");
    check("Non-zero result values", nonZero.length > 0, `${nonZero.length} values`);
  }

  // Test preset switching
  console.log("\n  -- Preset test --");
  const presetSelect = page.locator('select').first();
  await presetSelect.selectOption({ index: 1 }); // First preset
  await page.waitForTimeout(500);
  await runBtn.click();
  await page.waitForTimeout(5000);
  const preset1Status = await page.locator('.truncate').first().textContent().catch(() => "");
  check("Preset 1 prediction", preset1Status.includes("complete") || preset1Status.includes("Analysis"), preset1Status);

  await presetSelect.selectOption({ index: 3 }); // Third preset
  await page.waitForTimeout(500);
  await runBtn.click();
  await page.waitForTimeout(5000);
  const preset3Status = await page.locator('.truncate').first().textContent().catch(() => "");
  check("Preset 3 prediction", preset3Status.includes("complete") || preset3Status.includes("Analysis"), preset3Status);

  // Reset
  const resetBtn = page.locator('button svg').first(); // Reset icon button
  // Skip reset test, just move on

  // ═══════════════════════════════════════════════
  // 2. STRESS FIELD TAB
  // ═══════════════════════════════════════════════
  console.log("\n══ STRESS FIELD TAB ══");
  await clickTab("Stress Field");
  await page.waitForTimeout(500);

  const sfCanvas = page.locator('canvas').first();
  const sfVisible = await sfCanvas.isVisible({ timeout: 2000 }).catch(() => false);
  check("Stress canvas visible", sfVisible);

  // Material dropdown (stress field has its own)
  const sfSelects = await page.locator('select').all();
  let materialOpts = [];
  for (const sel of sfSelects) {
    const opts = await sel.locator('option').allTextContents();
    if (opts.some(o => o.includes("T300") || o.includes("analytical"))) {
      materialOpts = opts;
      break;
    }
  }
  check("Material dropdown", materialOpts.length > 0, materialOpts.join(", "));

  // Compute button
  const computeBtn = page.locator('button', { hasText: 'Compute' }).first();
  const computeVisible = await computeBtn.isVisible({ timeout: 1000 }).catch(() => false);
  check("Compute button visible", computeVisible);

  if (computeVisible) {
    await computeBtn.click();
    await page.waitForTimeout(3000);
    // Check canvas changed (has content)
    const canvasData = await page.evaluate(() => {
      const c = document.querySelector('canvas');
      if (!c) return null;
      const ctx = c.getContext('2d');
      const data = ctx.getImageData(c.width/2, c.height/2, 1, 1).data;
      return Array.from(data);
    });
    check("Stress computed (canvas has content)", canvasData && (canvasData[0] > 0 || canvasData[1] > 0 || canvasData[2] > 0),
      canvasData ? `center pixel: rgba(${canvasData.join(",")})` : "no canvas");
  }

  // Input fields for stress field
  const sfInputs = await page.locator('input[type="number"], input[type="range"]').count();
  check("Stress field inputs", sfInputs >= 3, `${sfInputs} inputs`);

  // ═══════════════════════════════════════════════
  // 3. LAMINATE TAB
  // ═══════════════════════════════════════════════
  console.log("\n══ LAMINATE TAB ══");
  await clickTab("Laminate");
  await page.waitForTimeout(500);

  // Laminate code input
  const lamInput = page.locator('input[placeholder*="Laminate"], input[value*="["]').first();
  const lamCode = await lamInput.inputValue().catch(() => "");
  check("Laminate code input", lamCode.includes("["), lamCode);

  // Sub-tab: Stiffness
  await clickTab("Stiffness");
  await page.waitForTimeout(300);
  const stiffContent = await page.evaluate(() => {
    const monos = document.querySelectorAll('.tabular-nums, [class*="font-mono"]');
    return Array.from(monos).map(m => m.textContent?.trim()).filter(t => t && t.length > 0).slice(0, 20);
  });
  check("ABD matrix values", stiffContent.length > 0, `${stiffContent.length} values: ${stiffContent.slice(0, 5).join(", ")}`);

  // Sub-tab: Ply Stress
  await clickTab("Ply Stress");
  await page.waitForTimeout(300);
  const plyRows = await page.evaluate(() => {
    const rows = document.querySelectorAll('tr');
    return rows.length;
  });
  check("Ply stress table rows", plyRows > 1, `${plyRows} rows`);

  // Ply values non-zero
  const plyValues = await page.evaluate(() => {
    const tds = document.querySelectorAll('td');
    return Array.from(tds).map(t => t.textContent?.trim()).filter(t => t && !isNaN(parseFloat(t)) && parseFloat(t) !== 0).length;
  });
  check("Non-zero ply stress values", plyValues > 0, `${plyValues} non-zero`);

  // Sub-tab: Failure
  await clickTab("Failure");
  await page.waitForTimeout(300);
  const failureCards = await page.evaluate(() => {
    const els = document.querySelectorAll('[class*="grid"] [class*="rounded-lg"]');
    return Array.from(els).map(e => e.textContent?.trim().slice(0, 60)).filter(t => t && t.length > 5);
  });
  check("Failure analysis cards", failureCards.length >= 3, failureCards.map(c => c.slice(0, 30)).join(" | "));

  // Test different laminate codes
  console.log("\n  -- Laminate code tests --");
  const testCodes = [
    { code: "[0/90]4s", desc: "repeat count", expectPlies: 16 },
    { code: "[±45]2s", desc: "plus-minus with repeat", expectPlies: 8 },
    { code: "[0]8", desc: "single angle repeat", expectPlies: 8 },
    { code: "[0/±45/90]s", desc: "standard quasi-iso", expectPlies: 8 },
  ];

  await clickTab("Ply Stress"); // Switch to ply stress to count plies
  await page.waitForTimeout(300);

  for (const tc of testCodes) {
    await lamInput.fill(tc.code);
    await page.waitForTimeout(500);
    const rows = await page.evaluate(() => document.querySelectorAll('tr').length) - 1; // minus header
    check(`Laminate "${tc.code}"`, rows === tc.expectPlies, `${rows} plies (expected ${tc.expectPlies})`);
  }

  // Restore default
  await lamInput.fill("[0/±45/90]s");
  await page.waitForTimeout(300);

  // ═══════════════════════════════════════════════
  // 4. EXPLORER TAB
  // ═══════════════════════════════════════════════
  console.log("\n══ EXPLORER TAB ══");
  await clickTab("Explorer");
  await page.waitForTimeout(500);

  // Mode buttons
  const modeLabels = ["1D Sweep", "2D Sweep", "Monte Carlo", "Sensitivity"];
  for (const m of modeLabels) {
    const btn = page.locator('button', { hasText: m }).first();
    const vis = await btn.isVisible({ timeout: 500 }).catch(() => false);
    check(`Mode "${m}" button`, vis);
  }

  // Explorer Run button
  const expRun = page.locator('button', { hasText: /^Run$/ }).first();
  const expRunEnabled = await expRun.isEnabled({ timeout: 1000 }).catch(() => false);
  check("Explorer Run enabled", expRunEnabled);

  // 1D Sweep test
  console.log("\n  -- 1D Sweep --");
  await clickTab("1D Sweep");
  await page.waitForTimeout(300);
  if (expRunEnabled) {
    await expRun.click();
    for (let i = 0; i < 30; i++) {
      await page.waitForTimeout(1000);
      const t = await expRun.textContent().catch(() => "?");
      if (t === "Run") break;
    }
    const chartLabels = await page.locator('svg text').allTextContents().catch(() => []);
    const hasChart = chartLabels.some(l => l.includes("von Mises") || l.includes("Pressure") || l.includes("vs"));
    check("1D sweep chart rendered", hasChart, chartLabels.slice(0, 5).join(", "));

    // Check for non-trivial data (polyline points)
    const paths = await page.locator('svg polyline').count();
    check("1D sweep data lines", paths > 0, `${paths} polylines`);
  }

  // 2D Sweep test
  console.log("\n  -- 2D Sweep --");
  await clickTab("2D Sweep");
  await page.waitForTimeout(300);
  const run2d = page.locator('button', { hasText: /^Run$/ }).first();
  await run2d.click();
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(1000);
    const t = await run2d.textContent().catch(() => "?");
    if (t === "Run") { console.log(`    completed ${i+1}s`); break; }
    if (i % 10 === 9) console.log(`    ...running ${i+1}s`);
  }
  const heatRects = await page.locator('svg rect').count();
  check("2D sweep heatmap", heatRects > 20, `${heatRects} rects`);

  // Monte Carlo test
  console.log("\n  -- Monte Carlo --");
  await clickTab("Monte Carlo");
  await page.waitForTimeout(300);

  // Set samples to 20 for speed
  const samplesInput = page.locator('input[type="number"]').last();
  await samplesInput.fill('20');
  await page.waitForTimeout(200);

  const runMC = page.locator('button', { hasText: /^Run$/ }).first();
  await runMC.click();
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(1000);
    const t = await runMC.textContent().catch(() => "?");
    if (t === "Run") { console.log(`    completed ${i+1}s`); break; }
  }

  // Check histogram
  const histBars = await page.evaluate(() => {
    const svgs = document.querySelectorAll('svg');
    let maxRects = 0;
    svgs.forEach(svg => {
      const title = svg.querySelector('text')?.textContent || '';
      if (title.includes('Distribution')) {
        maxRects = svg.querySelectorAll('rect').length;
      }
    });
    return maxRects;
  });
  check("MC histogram rendered", histBars > 5, `${histBars} bars`);

  // Check stats are non-zero
  const mcStats = await page.locator('.tabular-nums').allTextContents();
  const nonZeroStats = mcStats.filter(t => {
    const v = parseFloat(t.replace(/[–,]/g, ''));
    return !isNaN(v) && v !== 0;
  });
  check("MC stats non-zero", nonZeroStats.length > 3, `${nonZeroStats.length} non-zero values`);

  // Sensitivity test
  console.log("\n  -- Sensitivity --");
  await clickTab("Sensitivity");
  await page.waitForTimeout(300);
  const runSens = page.locator('button', { hasText: /^Run$/ }).first();
  await runSens.click();
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(1000);
    const t = await runSens.textContent().catch(() => "?");
    if (t === "Run") { console.log(`    completed ${i+1}s`); break; }
    if (i % 10 === 9) console.log(`    ...running ${i+1}s`);
  }
  const sensBars = await page.locator('svg rect').count();
  const sensLabels = await page.locator('svg text').allTextContents().catch(() => []);
  check("Sensitivity bars rendered", sensBars > 3, `${sensBars} bars`);
  check("Sensitivity param labels", sensLabels.some(l => l.includes("Pressure") || l.includes("Thickness")),
    sensLabels.filter(l => l.length > 3).slice(0, 5).join(", "));

  // ═══════════════════════════════════════════════
  // 5. PROJECT TAB
  // ═══════════════════════════════════════════════
  console.log("\n══ PROJECT TAB ══");
  await clickTab("Project");
  await page.waitForTimeout(500);

  // Export button
  const exportBtn = page.locator('button', { hasText: /Export.*rp3/i }).first();
  check("Export button", await exportBtn.isVisible({ timeout: 1000 }).catch(() => false));

  // Import button
  const importBtn = page.locator('button', { hasText: /Import/i }).first();
  check("Import button", await importBtn.isVisible({ timeout: 1000 }).catch(() => false));

  // Save snapshot
  const saveBtn = page.locator('button', { hasText: /Save/i }).first();
  check("Save button", await saveBtn.isVisible({ timeout: 1000 }).catch(() => false));

  // Save a test snapshot
  if (await saveBtn.isVisible({ timeout: 500 }).catch(() => false)) {
    await saveBtn.click();
    await page.waitForTimeout(500);

    // Check snapshot appears
    const snapshots = await page.evaluate(() => {
      const els = document.querySelectorAll('[class*="rounded"]');
      return Array.from(els).filter(e => {
        const t = e.textContent || '';
        return t.includes('defect') || t.includes('Px=') || t.includes('MPa');
      }).length;
    });
    check("Snapshot saved", snapshots > 0, `${snapshots} snapshot entries`);
  }

  // History section
  const historyText = await page.evaluate(() => {
    const body = document.body.innerText;
    return body.includes('History') ? 'History section found' : 'No history section';
  });
  check("History section exists", historyText.includes("found"), historyText);

  // ═══════════════════════════════════════════════
  // SUMMARY
  // ═══════════════════════════════════════════════
  console.log("\n══════════════════════════════════════");
  console.log("FINAL RESULTS");
  console.log("══════════════════════════════════════");
  const passed = results.filter(r => r.ok).length;
  const failed = results.filter(r => !r.ok).length;
  console.log(`${passed} passed, ${failed} failed out of ${results.length} checks`);
  if (failed > 0) {
    console.log("\nFailed checks:");
    results.filter(r => !r.ok).forEach(r => console.log(`  ${FAIL} ${r.name}: ${r.detail}`));
  }

  await browser.close();
  console.log(`\nDone.`);
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
