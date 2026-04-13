#!/usr/bin/env node
import { chromium } from "playwright";

async function main() {
  const browser = await chromium.connectOverCDP("http://localhost:9222");
  const page = browser.contexts()[0]?.pages()[0];
  if (!page) { console.error("No page found"); process.exit(1); }

  // Wait for models
  console.log("Waiting for models...");
  await page.waitForTimeout(8000);

  // Test 1: Direct predict call via __TAURI__
  console.log("=== Test 1: Direct predict call ===");
  const rawResp = await page.evaluate(async () => {
    const invoke = window.__TAURI__?.core?.invoke || window.__TAURI_INTERNALS__?.invoke;
    if (!invoke) return "ERROR: No invoke function found";

    const params = {
      n_defects: 3,
      pressure_x: 100,
      pressure_y: 0,
      ply_thickness: 0.125,
      layup_rotation: 0,
      defect1_x: 50, defect1_y: 25, defect1_half_length: 10, defect1_width: 1, defect1_angle: 0, defect1_roughness: 0.5,
      defect2_x: 30, defect2_y: 15, defect2_half_length: 5, defect2_width: 0.5, defect2_angle: 45, defect2_roughness: 0.3,
      defect3_x: 70, defect3_y: 35, defect3_half_length: 7, defect3_width: 0.7, defect3_angle: -30, defect3_roughness: 0.6,
      defect4_x: 0, defect4_y: 0, defect4_half_length: 0, defect4_width: 0, defect4_angle: 0, defect4_roughness: 0,
      defect5_x: 0, defect5_y: 0, defect5_half_length: 0, defect5_width: 0, defect5_angle: 0, defect5_roughness: 0,
    };
    try {
      const resp = await invoke("predict", { params });
      return JSON.stringify(resp, null, 2);
    } catch (e) {
      return `ERROR: ${e}`;
    }
  });
  console.log("Raw response:");
  console.log(rawResp);

  // Test 2: MC-style random sample
  console.log("\n=== Test 2: MC-style random ===");
  const mcResp = await page.evaluate(async () => {
    const invoke = window.__TAURI__?.core?.invoke || window.__TAURI_INTERNALS__?.invoke;
    if (!invoke) return "ERROR: No invoke";

    const params = {
      n_defects: 1,
      pressure_x: 237.5,
      pressure_y: -112.3,
      ply_thickness: 0.45,
      layup_rotation: 23.7,
      defect1_x: 50, defect1_y: 25, defect1_half_length: 28.3, defect1_width: 5.2, defect1_angle: -45, defect1_roughness: 0.73,
      defect2_x: 0, defect2_y: 0, defect2_half_length: 0, defect2_width: 0, defect2_angle: 0, defect2_roughness: 0,
      defect3_x: 0, defect3_y: 0, defect3_half_length: 0, defect3_width: 0, defect3_angle: 0, defect3_roughness: 0,
      defect4_x: 0, defect4_y: 0, defect4_half_length: 0, defect4_width: 0, defect4_angle: 0, defect4_roughness: 0,
      defect5_x: 0, defect5_y: 0, defect5_half_length: 0, defect5_width: 0, defect5_angle: 0, defect5_roughness: 0,
    };
    try {
      const resp = await invoke("predict", { params });
      return JSON.stringify(resp, null, 2);
    } catch (e) {
      return `ERROR: ${e}`;
    }
  });
  console.log(mcResp);

  // Test 3: Check what happens with ply_thickness at extreme values
  console.log("\n=== Test 3: Extreme ply_thickness ===");
  const extremeResp = await page.evaluate(async () => {
    const invoke = window.__TAURI__?.core?.invoke || window.__TAURI_INTERNALS__?.invoke;
    if (!invoke) return "ERROR: No invoke";

    const params = {
      n_defects: 1,
      pressure_x: 0.01,  // near zero pressure
      pressure_y: 0.01,
      ply_thickness: 0.05,
      layup_rotation: 0,
      defect1_x: 50, defect1_y: 25, defect1_half_length: 0.1, defect1_width: 0.01, defect1_angle: 0, defect1_roughness: 0,
      defect2_x: 0, defect2_y: 0, defect2_half_length: 0, defect2_width: 0, defect2_angle: 0, defect2_roughness: 0,
      defect3_x: 0, defect3_y: 0, defect3_half_length: 0, defect3_width: 0, defect3_angle: 0, defect3_roughness: 0,
      defect4_x: 0, defect4_y: 0, defect4_half_length: 0, defect4_width: 0, defect4_angle: 0, defect4_roughness: 0,
      defect5_x: 0, defect5_y: 0, defect5_half_length: 0, defect5_width: 0, defect5_angle: 0, defect5_roughness: 0,
    };
    try {
      const resp = await invoke("predict", { params });
      return JSON.stringify(resp, null, 2);
    } catch (e) {
      return `ERROR: ${e}`;
    }
  });
  console.log(extremeResp);

  await browser.close();
  console.log("\n✓ Done");
}

main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
