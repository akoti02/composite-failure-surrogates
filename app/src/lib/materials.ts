/**
 * V11 Composite material property database.
 * These 5 materials match the V11 CompositeBench training dataset exactly.
 * Properties in MPa (moduli and strengths).
 */

export interface MaterialProperties {
  id: number;       // V11 material_id (used by ML models)
  name: string;
  description: string;
  E1: number;   // Longitudinal modulus (MPa)
  E2: number;   // Transverse modulus (MPa)
  G12: number;  // In-plane shear modulus (MPa)
  v12: number;  // Major Poisson's ratio
  Xt: number;   // Longitudinal tensile strength (MPa)
  Xc: number;   // Longitudinal compressive strength (MPa)
  Yt: number;   // Transverse tensile strength (MPa)
  Yc: number;   // Transverse compressive strength (MPa)
  S12: number;  // In-plane shear strength (MPa)
  plyThickness: number;  // mm
}

export const MATERIAL_DB: Record<string, MaterialProperties> = {
  "T300/5208": {
    id: 1, name: "T300/5208",
    description: "Standard modulus CFRP. Most-cited benchmark in composites literature.",
    E1: 135000, E2: 10000, G12: 5200, v12: 0.27,
    Xt: 1500, Xc: 1200, Yt: 50, Yc: 250, S12: 70,
    plyThickness: 0.15,
  },
  "IM7/8552": {
    id: 5, name: "IM7/8552",
    description: "Intermediate modulus, toughened epoxy. Aerospace primary structure grade.",
    E1: 171400, E2: 9080, G12: 5290, v12: 0.32,
    Xt: 2326, Xc: 1200, Yt: 62, Yc: 200, S12: 92,
    plyThickness: 0.15,
  },
  "E-glass/Epoxy": {
    id: 8, name: "E-glass/Epoxy",
    description: "Glass fiber reinforced epoxy. Lower cost, fundamentally different failure behavior.",
    E1: 39000, E2: 8600, G12: 3800, v12: 0.28,
    Xt: 1000, Xc: 700, Yt: 40, Yc: 120, S12: 70,
    plyThickness: 0.15,
  },
  "Kevlar49/Epoxy": {
    id: 12, name: "Kevlar 49/Epoxy",
    description: "Aramid fiber reinforced epoxy. Unique tension/compression asymmetry.",
    E1: 80000, E2: 5500, G12: 2200, v12: 0.34,
    Xt: 1400, Xc: 335, Yt: 30, Yc: 158, S12: 49,
    plyThickness: 0.15,
  },
  "Flax/Epoxy": {
    id: 15, name: "Flax/Epoxy",
    description: "Natural fiber composite. Low-performance extreme, tests model generalization.",
    E1: 35000, E2: 5500, G12: 3000, v12: 0.30,
    Xt: 350, Xc: 150, Yt: 25, Yc: 100, S12: 40,
    plyThickness: 0.15,
  },
};

export const DEFAULT_MATERIAL_ID = "T300/5208";

export function v21(m: MaterialProperties): number {
  return m.v12 * m.E2 / m.E1;
}

export function reducedStiffness(m: MaterialProperties): [number, number, number, number] {
  const nu21 = v21(m);
  const denom = 1 - m.v12 * nu21;
  if (denom <= 0) {
    throw new Error(`Invalid material: 1 - v12*v21 = ${denom.toFixed(6)} <= 0`);
  }
  const Q11 = m.E1 / denom;
  const Q22 = m.E2 / denom;
  const Q12 = m.v12 * m.E2 / denom;
  const Q66 = m.G12;
  return [Q11, Q12, Q22, Q66];
}

export function transformedStiffness(m: MaterialProperties, theta: number): number[][] {
  const [Q11, Q12, Q22, Q66] = reducedStiffness(m);
  const rad = (theta * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  const c2 = c * c, s2 = s * s, cs = c * s;
  const c4 = c2 * c2, s4 = s2 * s2;

  const Qbar11 = Q11 * c4 + 2 * (Q12 + 2 * Q66) * c2 * s2 + Q22 * s4;
  const Qbar12 = (Q11 + Q22 - 4 * Q66) * c2 * s2 + Q12 * (c4 + s4);
  const Qbar22 = Q11 * s4 + 2 * (Q12 + 2 * Q66) * c2 * s2 + Q22 * c4;
  const Qbar16 = (Q11 - Q12 - 2 * Q66) * c2 * cs - (Q22 - Q12 - 2 * Q66) * s2 * cs;
  const Qbar26 = (Q11 - Q12 - 2 * Q66) * cs * s2 - (Q22 - Q12 - 2 * Q66) * cs * c2;
  const Qbar66 = (Q11 + Q22 - 2 * Q12 - 2 * Q66) * c2 * s2 + Q66 * (c4 + s4);

  return [
    [Qbar11, Qbar12, Qbar16],
    [Qbar12, Qbar22, Qbar26],
    [Qbar16, Qbar26, Qbar66],
  ];
}

/**
 * V11 layup definitions — 6 selected, all symmetric (B matrix = 0).
 */
export interface LayupDefinition {
  id: number;       // V11 layup_id (used by ML models)
  name: string;
  description: string;
  angles: number[];
}

export const LAYUP_DB: Record<string, LayupDefinition> = {
  "QI_8": {
    id: 1, name: "QI [0/45/-45/90]s",
    description: "Quasi-isotropic 8-ply. Balanced failure modes.",
    angles: [0, 45, -45, 90, 90, -45, 45, 0],
  },
  "CP_8": {
    id: 3, name: "CP [0/90]2s",
    description: "Cross-ply 8-ply. Distinct 0/90 interaction.",
    angles: [0, 90, 0, 90, 90, 0, 90, 0],
  },
  "UD_0_8": {
    id: 4, name: "UD [0]8",
    description: "Unidirectional 8-ply. Pure fiber-dominated response.",
    angles: [0, 0, 0, 0, 0, 0, 0, 0],
  },
  "Angle_pm45": {
    id: 6, name: "[±45]2s",
    description: "±45 angle-ply. Shear-dominated, exercises matrix failure.",
    angles: [45, -45, 45, -45, -45, 45, -45, 45],
  },
  "Angle_pm30": {
    id: 7, name: "[±30]2s",
    description: "±30 angle-ply. Off-axis mixed fiber/matrix response.",
    angles: [30, -30, 30, -30, -30, 30, -30, 30],
  },
  "Skin_25_50_25": {
    id: 13, name: "Skin 25/50/25",
    description: "Aerospace realistic 18-ply. Multi-angle with thickness.",
    angles: [45, -45, 0, 0, 90, 0, 0, -45, 45, 45, -45, 0, 0, 90, 0, 0, -45, 45],
  },
};

export const DEFAULT_LAYUP_ID = "QI_8";

/**
 * V11 boundary conditions — 3 modes.
 */
export const BC_MODES = [
  { id: "tension_comp", name: "Tension + Compression", description: "px on right, -py on top/bottom" },
  { id: "biaxial", name: "Biaxial", description: "px on right, py on top/bottom" },
  { id: "uniaxial_shear", name: "Uniaxial + Shear", description: "px on right, shear via X-force on top" },
] as const;

export const DEFAULT_BC_MODE = "tension_comp";
