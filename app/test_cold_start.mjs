#!/usr/bin/env node
import { chromium } from "playwright";

async function main() {
  const browser = await chromium.connectOverCDP("http://localhost:9222");
  const page = browser.contexts()[0]?.pages()[0];
  if (!page) { console.error("No page found"); process.exit(1); }

  console.log("Connected. Monitoring status over 30s...");

  // Poll the status text every 2 seconds
  for (let i = 0; i < 15; i++) {
    const info = await page.evaluate(() => {
      const truncates = document.querySelectorAll('.truncate');
      const texts = Array.from(truncates).map(el => el.textContent?.trim());

      // Also check for any dots
      const dots = document.querySelectorAll('[class*="dot"]');
      const dotInfo = Array.from(dots).map(d => ({
        classes: d.className,
        style: d.getAttribute('style') || ''
      }));

      return { statusTexts: texts, dots: dotInfo };
    });

    console.log(`[${i*2}s] Status: ${info.statusTexts.join(' | ')}`);
    if (info.dots.length > 0) {
      console.log(`       Dots: ${info.dots.map(d => d.style.slice(0, 50)).join('; ')}`);
    }

    await page.waitForTimeout(2000);
  }

  // Final check: can we call load_models directly?
  console.log("\n=== Direct load_models call ===");
  const loadResp = await page.evaluate(async () => {
    const invoke = window.__TAURI__?.core?.invoke || window.__TAURI_INTERNALS__?.invoke;
    if (!invoke) return "No invoke available";
    try {
      const resp = await invoke("load_models");
      return JSON.stringify(resp);
    } catch (e) {
      return `Error: ${e}`;
    }
  });
  console.log("load_models response:", loadResp);

  await browser.close();
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
