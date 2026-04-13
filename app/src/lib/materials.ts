/**
 * Composite material property database.
 * All properties in SI-consistent units: GPa for moduli, MPa for strengths.
 * Sources: MIL-HDBK-17, ESDU datasheets, manufacturer TDS.
 */

export interface MaterialProperties {
  id: string;
  name: string;
  description: string;
  // Elastic constants (GPa)
  E1: number;   // Longitudinal modulus
  E2: number;   // Transverse modulus
  G12: number;  // In-plane shear modulus
  v12: number;  // Major Poisson's ratio
  // Strength (MPa)
  Xt: number;   // Longitudinal tensile strength
  Xc: number;   // Longitudinal compressive strength
  Yt: number;   // Transverse tensile strength
  Yc: number;   // Transverse compressive strength
  S12: number;  // In-plane shear strength
  // Thermal (1/°C) — optional
  alpha1?: number;  // CTE longitudinal
  alpha2?: number;  // CTE transverse
  // Density (g/cm³) — optional
  density?: number;
  // Ply thickness (mm)
  plyThickness: number;
}

/** Aerospace-grade CFRP materials */
export const MATERIAL_DB: Record<string, MaterialProperties> = {
  "T300/5208": {
    id: "T300/5208",
    name: "T300/5208",
    description: "Standard modulus carbon/epoxy (Toray T300, Cytec 5208). Widely used benchmark.",
    E1: 181.0, E2: 10.3, G12: 7.17, v12: 0.28,
    Xt: 1500, Xc: 1500, Yt: 40, Yc: 246, S12: 68,
    alpha1: -0.018e-6, alpha2: 24.3e-6,
    density: 1.58, plyThickness: 0.125,
  },
  "AS4/3501-6": {
    id: "AS4/3501-6",
    name: "AS4/3501-6",
    description: "Hercules AS4 fiber, 3501-6 toughened epoxy. Common aerospace prepreg.",
    E1: 147.0, E2: 10.3, G12: 7.0, v12: 0.27,
    Xt: 2280, Xc: 1440, Yt: 57, Yc: 228, S12: 71,
    alpha1: -0.9e-6, alpha2: 27.0e-6,
    density: 1.58, plyThickness: 0.125,
  },
  "IM7/8552": {
    id: "IM7/8552",
    name: "IM7/8552",
    description: "Intermediate modulus carbon, Hexcel 8552 toughened epoxy. Primary structure grade.",
    E1: 171.4, E2: 9.08, G12: 5.29, v12: 0.32,
    Xt: 2326, Xc: 1200, Yt: 62.3, Yc: 199.8, S12: 92.3,
    alpha1: -0.09e-6, alpha2: 28.8e-6,
    density: 1.59, plyThickness: 0.131,
  },
  "T700/2510": {
    id: "T700/2510",
    name: "T700/2510",
    description: "Toray T700 high-strength fiber, Cytec 2510 OOA epoxy. Out-of-autoclave capable.",
    E1: 132.0, E2: 10.3, G12: 6.5, v12: 0.25,
    Xt: 2400, Xc: 1300, Yt: 55, Yc: 210, S12: 75,
    density: 1.56, plyThickness: 0.127,
  },
  "E-Glass/Epoxy": {
    id: "E-Glass/Epoxy",
    name: "E-Glass/Epoxy",
    description: "E-glass fiber reinforced epoxy. Lower cost, moderate performance.",
    E1: 38.6, E2: 8.27, G12: 4.14, v12: 0.26,
    Xt: 1062, Xc: 610, Yt: 31, Yc: 118, S12: 72,
    alpha1: 8.6e-6, alpha2: 22.1e-6,
    density: 2.10, plyThickness: 0.150,
  },
  "S2-Glass/Epoxy": {
    id: "S2-Glass/Epoxy",
    name: "S2-Glass/Epoxy",
    description: "S2-glass high-strength fiber/epoxy. Ballistic and impact applications.",
    E1: 43.0, E2: 8.9, G12: 4.5, v12: 0.27,
    Xt: 1280, Xc: 690, Yt: 49, Yc: 158, S12: 69,
    density: 1.99, plyThickness: 0.140,
  },
  "Kevlar49/Epoxy": {
    id: "Kevlar49/Epoxy",
    name: "Kevlar 49/Epoxy",
    description: "Aramid fiber reinforced epoxy. High toughness, poor compression.",
    E1: 76.0, E2: 5.5, G12: 2.3, v12: 0.34,
    Xt: 1400, Xc: 335, Yt: 30, Yc: 158, S12: 49,
    alpha1: -4.0e-6, alpha2: 79.0e-6,
    density: 1.38, plyThickness: 0.125,
  },
};

export const DEFAULT_MATERIAL_ID = "T300/5208";

/** Derived: minor Poisson's ratio v21 = v12 * E2 / E1 */
export function v21(m: MaterialProperties): number {
  return m.v12 * m.E2 / m.E1;
}

/** Reduced stiffness matrix Q (plane stress) in material axes, GPa */
export function reducedStiffness(m: MaterialProperties): [number, number, number, number] {
  const nu21 = v21(m);
  const denom = 1 - m.v12 * nu21;
  if (denom <= 0) {
    throw new Error(`Invalid material: 1 - v12*v21 = ${denom.toFixed(6)} <= 0 (v12=${m.v12}, E1=${m.E1}, E2=${m.E2})`);
  }
  const Q11 = m.E1 / denom;
  const Q22 = m.E2 / denom;
  const Q12 = m.v12 * m.E2 / denom;
  const Q66 = m.G12;
  return [Q11, Q12, Q22, Q66];
}

/** Transformed reduced stiffness Qbar for a ply at angle theta (degrees), GPa */
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
