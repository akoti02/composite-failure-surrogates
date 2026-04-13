#!/usr/bin/env node
import { chromium } from "playwright";

async function main() {
  const browser = await chromium.connectOverCDP("http://localhost:9222");
  const page = browser.contexts()[0]?.pages()[0];
  if (!page) { console.error("No page found"); process.exit(1); }

  // Listen for console output
  page.on('console', msg => {
    if (msg.type() === 'warn' || msg.type() === 'error') {
      console.log(`  [${msg.type()}] ${msg.text()}`);
    }
  });

  const clickTab = async (text) => {
    const tab = page.locator('button', { hasText: text }).first();
    await tab.click({ timeout: 3000 }).catch(e =>
      console.log(`  WARN tab "${text}": ${e.message.split('\n')[0]}`)
    );
    await page.waitForTimeout(800);
  };

  // Go to Explorer > Monte Carlo
  await clickTab("Explorer");
  await page.waitForTimeout(500);
  await clickTab("Monte Carlo");
  await page.waitForTimeout(500);

  // Set samples to 10 for quick test
  const samplesInput = page.locator('input[type="number"]').last();
  await samplesInput.fill('10');
  await page.waitForTimeout(300);

  console.log("Running MC with 10 samples...");

  // Add a debug hook to intercept invoke calls
  await page.evaluate(() => {
    const origInvoke = window.__TAURI__?.core?.invoke || window.__TAURI_INTERNALS__?.invoke;
    window._mcDebug = { calls: 0, responses: [] };

    // We can't easily monkey-patch invoke since it's imported via ES modules
    // Instead, let's just track via console
    console.log("Debug hook installed");
  });

  // Click Run
  const runBtn = page.locator('button', { hasText: /^Run$/ }).first();
  await runBtn.click();

  // Wait for completion
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(1000);
    const btnText = await runBtn.textContent().catch(() => "?");
    if (btnText === "Run") {
      console.log(`MC completed after ${i+1}s`);
      break;
    }
  }

  // Check the histogram values
  const histogramData = await page.evaluate(() => {
    // Look for SVG rect elements in histogram
    const svgs = document.querySelectorAll('svg');
    const results = [];
    svgs.forEach((svg, si) => {
      const title = svg.querySelector('text')?.textContent || '';
      const rects = svg.querySelectorAll('rect');
      const texts = svg.querySelectorAll('text');
      results.push({
        svgIndex: si,
        title,
        rectCount: rects.length,
        textContents: Array.from(texts).map(t => t.textContent).slice(0, 10),
      });
    });
    return results;
  });
  console.log("\nSVG analysis:");
  histogramData.forEach(s => {
    console.log(`  SVG ${s.svgIndex}: "${s.title}" — ${s.rectCount} rects`);
    console.log(`    texts: ${s.textContents.join(', ')}`);
  });

  // Check the stats cards
  const statsCards = await page.evaluate(() => {
    const cards = document.querySelectorAll('[class*="grid"] [class*="rounded-lg"]');
    return Array.from(cards).map(c => c.textContent?.trim().slice(0, 100)).filter(t => t && t.length > 5);
  });
  console.log("\nStats cards:");
  statsCards.forEach(c => console.log(`  ${c}`));

  // Check tabular-nums values specifically
  const tabNums = await page.locator('.tabular-nums').allTextContents();
  console.log("\nTabular nums values:", tabNums.join(' | '));

  await browser.close();
  console.log("\n✓ Done");
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
