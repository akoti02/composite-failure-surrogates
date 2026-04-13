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

  // Go to Laminate > Failure
  await clickTab("Laminate");
  await page.waitForTimeout(500);
  await clickTab("Failure");
  await page.waitForTimeout(500);

  // Get the full page HTML of the failure section
  const failureHTML = await page.evaluate(() => {
    // Find the active tab content
    const allDivs = document.querySelectorAll('[class*="flex"][class*="col"][class*="gap"]');
    let failContent = '';
    allDivs.forEach(d => {
      const text = d.textContent || '';
      if (text.includes('First Ply') || text.includes('Hashin') || text.includes('Progressive') || text.includes('Failure')) {
        failContent += d.outerHTML.slice(0, 500) + '\n---\n';
      }
    });
    return failContent || 'No failure content found';
  });
  console.log("Failure section HTML snippets:");
  console.log(failureHTML.slice(0, 1000));

  // Also get the full visible text of the right panel
  const rightPanel = await page.evaluate(() => {
    // The laminate content should be in the right side or main content area
    const main = document.querySelector('main');
    if (!main) return 'no main';
    // Get all text nodes
    const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
    const texts = [];
    let node;
    while (node = walker.nextNode()) {
      const t = node.textContent?.trim();
      if (t && t.length > 0) texts.push(t);
    }
    return texts.join(' | ');
  });
  console.log("\nAll text in main:");
  console.log(rightPanel.slice(0, 800));

  // Check if failure tab is actually selected
  const activeTab = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const failBtn = buttons.find(b => b.textContent?.trim() === 'Failure');
    if (!failBtn) return 'Failure button not found';
    return `Failure button found, classes: ${failBtn.className}`;
  });
  console.log("\nFailure tab state:", activeTab);

  // Check console errors
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  await page.waitForTimeout(1000);

  // Check for any error content
  const errorEls = await page.locator('text=/error|Error|exception/i').allTextContents().catch(() => []);
  console.log("Error elements:", errorEls.slice(0, 5).join(' | '));

  await browser.close();
  console.log("\n✓ Done");
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
