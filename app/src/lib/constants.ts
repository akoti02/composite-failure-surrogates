export const PLATE_LENGTH = 100.0; // mm
export const PLATE_WIDTH = 50.0; // mm
export const MAX_DEFECTS = 5;

// Luminescent defect palette — glow-in-the-dark tones
export const DEFECT_COLORS = ["#ff6ad5", "#00eaff", "#b794ff", "#ffb347", "#b4ff3d"];

/* ────────────────────────────────────────────────────────────────────
   LUMINESCENT PALETTE
   Dark base with neon cyan as primary accent. Accents "glow" (have halo
   shadows applied in index.css + inline styles). Text lifted for
   readability against the slightly warmer/blue-tinted backdrop.
   ──────────────────────────────────────────────────────────────────── */
export const COL = {
  // Layered backgrounds — lifted from near-black to soft near-black with a cool cast
  bg: "#16161d",
  bgDark: "#101016",
  panel: "#1d1d26",
  panelAlt: "#232330",
  card: "#21212c",
  cardHover: "#2a2a38",
  canvasBg: "#0f0f15",

  // Primary accent — luminescent ice-blue / neon cyan
  accent: "#00eaff",
  accentMuted: "rgba(0, 234, 255, 0.15)",
  accent2: "#7fdbff",
  accentGlow: "0 0 16px rgba(0, 234, 255, 0.45)",
  accentGlowSoft: "0 0 10px rgba(0, 234, 255, 0.25)",

  // Secondary luminescent hues (used selectively)
  neonViolet: "#b794ff",
  neonPink: "#ff6ad5",
  neonLime: "#b4ff3d",

  // Semantic — all bumped to high-luminance glow-ready variants
  success: "#5effb0",            // neon mint
  successMuted: "rgba(94, 255, 176, 0.10)",
  successGlow: "0 0 14px rgba(94, 255, 176, 0.35)",
  warning: "#ffd84d",            // neon amber
  warningMuted: "rgba(255, 216, 77, 0.10)",
  warningGlow: "0 0 14px rgba(255, 216, 77, 0.35)",
  danger: "#ff5e87",             // neon rose
  dangerMuted: "rgba(255, 94, 135, 0.10)",
  dangerGlow: "0 0 14px rgba(255, 94, 135, 0.40)",

  // Text hierarchy — brightened across the board
  text: "#fafaff",
  textMid: "#c7c7d4",
  textDim: "#8b8b9c",            // was #6b6b78 — readable without being harsh

  // Borders — slightly more visible to define sections
  border: "rgba(255, 255, 255, 0.09)",
  borderMed: "rgba(255, 255, 255, 0.14)",
  borderBright: "rgba(0, 234, 255, 0.35)",

  // Verdict backgrounds — luminescent washes
  safeBg: "rgba(94, 255, 176, 0.07)",
  warnBg: "rgba(255, 216, 77, 0.07)",
  critBg: "rgba(255, 94, 135, 0.08)",
} as const;

// Tooltips for engineering terms — translation keys into i18n.
// Keep this export for backward compatibility; callers should prefer
// `useT()` with the `tip_*` keys directly. See `i18n.ts`.
export const TOOLTIPS: Record<string, string> = {
  pressure_x: "Applied pressure in the fibre direction (longitudinal)",
  pressure_y: "Applied pressure transverse to the fibre direction",
  material: "Composite material system (fibre/matrix)",
  layup: "Laminate stacking sequence",
  bc_mode: "Boundary condition and loading mode",
  half_length: "Half the crack/defect length (semi-major axis)",
  width: "Opening width of the defect",
  angle: "Orientation of the defect relative to the fibre direction",
  roughness: "Surface roughness at the defect site (0 = smooth, 1 = rough)",
  tsai_wu: "Combined stress failure index. Values >= 1.0 predict failure. E.g. 0.85 = 85% of failure threshold.",
  hashin: "Damage mode indices. Values >= 1.0 predict mode-specific failure",
  hashin_ft: "Fibre tension — fibre breakage under tensile load",
  hashin_fc: "Fibre compression — fibre buckling/kinking under compressive load",
  hashin_mt: "Matrix tension — resin cracking between fibres under tension",
  hashin_mc: "Matrix compression — resin crushing between fibres under compression",
  mises: "von Mises equivalent stress combining all stress components",
  s11: "Stress in the fibre direction (longitudinal)",
  s12: "In-plane shear stress between fibre and transverse directions",
  n_defects: "Number of crack-like defects in the composite plate (1-5)",
  x_position: "Horizontal position of defect centre on the plate (0-100 mm)",
  y_position: "Vertical position of defect centre on the plate (0-50 mm)",
};
