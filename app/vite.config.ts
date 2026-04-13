import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { execSync } from "child_process";

// Build metadata injected at compile time — prevents stale build confusion
function getBuildMeta() {
  const now = new Date();
  const stamp = now.toISOString().replace("T", " ").slice(0, 19);
  let gitHash = "unknown";
  try { gitHash = execSync("git rev-parse --short HEAD", { encoding: "utf-8" }).trim(); } catch { /* not a git repo */ }
  return { stamp, gitHash };
}

const { stamp, gitHash } = getBuildMeta();

export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  server: { port: 5173, strictPort: true },
  envPrefix: ["VITE_", "TAURI_"],
  build: { target: "esnext", minify: "esbuild" },
  define: {
    __BUILD_TIMESTAMP__: JSON.stringify(stamp),
    __BUILD_HASH__: JSON.stringify(gitHash),
  },
});
