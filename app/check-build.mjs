#!/usr/bin/env node
/**
 * Build Staleness Checker
 *
 * Compares timestamps of source files vs built artifacts.
 * Flags any situation where you'd be running old code.
 *
 * Run: node check-build.mjs
 *   --fix     also rebuild (npm run build + cargo build --release)
 *   --strict  exit(1) on any staleness (use in CI/pre-launch)
 */

import { statSync, readdirSync, existsSync } from "fs";
import { join, relative } from "path";
import { execSync } from "child_process";

const ROOT = import.meta.dirname;
const STRICT = process.argv.includes("--strict");
const FIX = process.argv.includes("--fix");

let warnings = 0;
const warn = (msg) => { warnings++; console.error(`  \u26A0 ${msg}`); };
const ok = (msg) => console.log(`  \u2713 ${msg}`);
const head = (msg) => console.log(`\n\u2500\u2500 ${msg} \u2500\u2500`);

// ── Collect newest source timestamp ──
function newestInDir(dir, extensions) {
  let newest = 0;
  let newestFile = "";
  function walk(d) {
    if (!existsSync(d)) return;
    for (const entry of readdirSync(d, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name === ".git" || entry.name === "target") continue;
      const full = join(d, entry.name);
      if (entry.isDirectory()) { walk(full); continue; }
      if (!extensions.some(ext => entry.name.endsWith(ext))) continue;
      const mtime = statSync(full).mtimeMs;
      if (mtime > newest) { newest = mtime; newestFile = full; }
    }
  }
  walk(dir);
  return { newest, newestFile };
}

function fileTime(p) {
  try { return statSync(p).mtimeMs; } catch { return 0; }
}

const fmt = (ms) => ms ? new Date(ms).toISOString().replace("T", " ").slice(0, 19) : "MISSING";

// ═══════════════════════════════════════════════
// CHECK 1: Frontend source vs dist/ bundle
// ═══════════════════════════════════════════════
head("Frontend: src/ vs dist/");

const srcInfo = newestInDir(join(ROOT, "src"), [".ts", ".tsx", ".css", ".html"]);
const distDir = join(ROOT, "dist", "assets");
const distInfo = newestInDir(distDir, [".js", ".css"]);

if (distInfo.newest === 0) {
  warn("dist/ not found — run: npm run build");
} else if (srcInfo.newest > distInfo.newest) {
  warn(`Source newer than dist!`);
  warn(`  Source: ${relative(ROOT, srcInfo.newestFile)} (${fmt(srcInfo.newest)})`);
  warn(`  Dist:   ${relative(ROOT, distInfo.newestFile)} (${fmt(distInfo.newest)})`);
  warn(`  Run: npm run build`);
} else {
  ok(`dist/ is up to date (${fmt(distInfo.newest)})`);
}

// ═══════════════════════════════════════════════
// CHECK 2: Rust source vs release exe
// ═══════════════════════════════════════════════
head("Tauri: src-tauri/ vs release exe");

const rustInfo = newestInDir(join(ROOT, "src-tauri", "src"), [".rs"]);
const cargoToml = fileTime(join(ROOT, "src-tauri", "Cargo.toml"));
const rustNewest = Math.max(rustInfo.newest, cargoToml);
const exePath = join(ROOT, "src-tauri", "target", "release", "rp3.exe");
const exeTime = fileTime(exePath);

if (exeTime === 0) {
  warn("Release exe not found — run: npx tauri build");
} else if (rustNewest > exeTime) {
  warn(`Rust source newer than exe!`);
  warn(`  Rust: ${fmt(rustNewest)}`);
  warn(`  Exe:  ${fmt(exeTime)}`);
  warn(`  Run: npx tauri build`);
} else {
  ok(`rp3.exe is up to date (${fmt(exeTime)})`);
}

// ═══════════════════════════════════════════════
// CHECK 3: dist/ must be newer than exe (frontend baked into exe)
// ═══════════════════════════════════════════════
head("Tauri exe vs frontend dist/");

if (exeTime > 0 && distInfo.newest > 0) {
  if (distInfo.newest > exeTime) {
    warn(`dist/ is newer than rp3.exe — exe has STALE frontend!`);
    warn(`  dist: ${fmt(distInfo.newest)}, exe: ${fmt(exeTime)}`);
    warn(`  Run: npx tauri build`);
  } else {
    ok(`exe contains current frontend`);
  }
}

// ═══════════════════════════════════════════════
// CHECK 4: Sidecar binary
// ═══════════════════════════════════════════════
head("Sidecar binary");

const sidecarSrc = newestInDir(join(ROOT, "sidecar"), [".py"]);
const sidecarExe = fileTime(join(ROOT, "sidecar", "dist", "rp3-sidecar.exe"));

if (sidecarExe === 0) {
  warn("Sidecar exe not found — run PyInstaller");
} else if (sidecarSrc.newest > sidecarExe) {
  warn(`Python source newer than sidecar exe!`);
  warn(`  Python: ${relative(ROOT, sidecarSrc.newestFile)} (${fmt(sidecarSrc.newest)})`);
  warn(`  Exe:    ${fmt(sidecarExe)}`);
} else {
  ok(`Sidecar exe is up to date (${fmt(sidecarExe)})`);
}

// ═══════════════════════════════════════════════
// CHECK 5: NSIS installer
// ═══════════════════════════════════════════════
head("NSIS installer");

const nsisDir = join(ROOT, "src-tauri", "target", "release", "bundle", "nsis");
const nsisInfo = newestInDir(nsisDir, [".exe"]);

if (nsisInfo.newest === 0) {
  warn("No NSIS installer found");
} else if (exeTime > 0 && nsisInfo.newest < exeTime - 5000) {
  // 5s tolerance — exe and installer are built in same run
  warn(`Installer is older than exe — rebuild: npx tauri build`);
} else {
  ok(`Installer is current (${fmt(nsisInfo.newest)})`);
}

// ═══════════════════════════════════════════════
// CHECK 6: Vite cache
// ═══════════════════════════════════════════════
head("Vite cache");

const viteCacheDir = join(ROOT, "node_modules", ".vite");
if (existsSync(viteCacheDir)) {
  const cacheInfo = newestInDir(viteCacheDir, [".js"]);
  if (cacheInfo.newest > 0 && srcInfo.newest > cacheInfo.newest + 60000) {
    warn(`Vite dep cache may be stale — run: rm -rf node_modules/.vite`);
  } else {
    ok("Vite cache looks fine");
  }
} else {
  ok("No Vite cache (will be created on next dev)");
}

// ═══════════════════════════════════════════════
// SUMMARY
// ═══════════════════════════════════════════════
console.log(`\n${"=".repeat(50)}`);
if (warnings === 0) {
  console.log(`ALL CLEAR — no stale builds detected.`);
} else {
  console.log(`${warnings} WARNING(S) — stale artifacts detected!`);
  if (FIX) {
    console.log("\n--fix requested, rebuilding...\n");
    try {
      console.log(">>> npm run build");
      execSync("npm run build", { cwd: ROOT, stdio: "inherit" });
      console.log("\n>>> npx tauri build");
      execSync("npx tauri build", { cwd: ROOT, stdio: "inherit", timeout: 600000 });
      console.log("\nRebuild complete.");
    } catch (e) {
      console.error("Build failed:", e.message);
      process.exit(1);
    }
  } else if (STRICT) {
    process.exit(1);
  }
}
