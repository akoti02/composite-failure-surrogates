export const PLATE_LENGTH = 100.0; // mm
export const PLATE_WIDTH = 50.0; // mm
export const MAX_DEFECTS = 5;

export const DEFECT_COLORS = ["#f472b6", "#38bdf8", "#a78bfa", "#fb923c", "#4ade80"];

export const COL = {
  // Layered backgrounds (Linear/Raycast pattern)
  bg: "#111113",
  bgDark: "#0a0a0b",
  panel: "#161618",
  panelAlt: "#1e1e22",
  card: "#1a1a1f",
  cardHover: "#222228",
  canvasBg: "#0e0e11",

  // Accent
  accent: "#6366f1",
  accentMuted: "rgba(99, 102, 241, 0.15)",
  accent2: "#818cf8",

  // Semantic
  success: "#34d399",
  successMuted: "rgba(52, 211, 153, 0.08)",
  warning: "#fbbf24",
  warningMuted: "rgba(251, 191, 36, 0.08)",
  danger: "#f87171",
  dangerMuted: "rgba(248, 113, 113, 0.08)",

  // Text hierarchy
  text: "#ededef",
  textMid: "#a0a0a8",
  textDim: "#6b6b78", // bumped from #5a5a65 for WCAG AA contrast

  // Borders
  border: "rgba(255, 255, 255, 0.06)",
  borderMed: "rgba(255, 255, 255, 0.09)",
  borderBright: "rgba(255, 255, 255, 0.14)",

  // Verdict backgrounds
  safeBg: "rgba(52, 211, 153, 0.06)",
  warnBg: "rgba(251, 191, 36, 0.06)",
  critBg: "rgba(248, 113, 113, 0.06)",
} as const;

// Tooltips for engineering terms
export const TOOLTIPS: Record<string, string> = {
  pressure_x: "Applied pressure in the fibre direction (longitudinal)",
  pressure_y: "Applied pressure transverse to the fibre direction",
  ply_thickness: "Thickness of a single composite ply",
  layup_rotation: "Rotation of the laminate layup schedule",
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
