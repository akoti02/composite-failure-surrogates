/**
 * Classical Lamination Theory (CLT) engine.
 *
 * Computes ABD stiffness matrices, ply stresses/strains, and failure indices
 * for symmetric/asymmetric laminates under mechanical + thermal loading.
 *
 * Reference: Jones, "Mechanics of Composite Materials", 2nd Ed.
 *            Reddy, "Mechanics of Laminated Composite Plates and Shells"
 */

import type { MaterialProperties } from "./materials";
import { transformedStiffness } from "./materials";

/** A single ply definition */
export interface PlyDef {
  angle: number;       // degrees
  materialId: string;
  thickness?: number;  // override material default (mm)
}

/** Full laminate definition */
export interface LaminateDef {
  plies: PlyDef[];
  symmetric: boolean;  // if true, only upper half is defined; mirrored automatically
}

/** 3x3 matrix type */
type Mat3 = number[][];

/** 6x6 ABD matrix (stored as 2D array) */
export interface ABDResult {
  A: Mat3;   // Extensional stiffness (N/mm)
  B: Mat3;   // Coupling stiffness (N)
  D: Mat3;   // Bending stiffness (N·mm)
  totalThickness: number; // mm
  plyCount: number;
  // Engineering constants of equivalent plate
  Ex: number;    // Effective longitudinal modulus (GPa)
  Ey: number;    // Effective transverse modulus (GPa)
  Gxy: number;   // Effective shear modulus (GPa)
  vxy: number;   // Effective Poisson's ratio
}

/** Per-ply stress/strain results */
export interface PlyResult {
  plyIndex: number;
  angle: number;
  materialId: string;
  zBot: number;       // mm from midplane
  zTop: number;       // mm from midplane
  // Global stresses (MPa) at ply midpoint
  sigmaX: number;
  sigmaY: number;
  tauXY: number;
  // Material-axis stresses (MPa)
  sigma1: number;
  sigma2: number;
  tau12: number;
  // Failure indices
  tsaiWu: number;        // < 1.0 safe
  maxStress: number;     // < 1.0 safe
  hashinFT: number;      // Fiber tension
  hashinFC: number;      // Fiber compression
  hashinMT: number;      // Matrix tension
  hashinMC: number;      // Matrix compression
  failed: boolean;
  failureMode: string;
}

/** Full laminate analysis result */
export interface LaminateAnalysis {
  abd: ABDResult;
  plies: PlyResult[];
  firstPlyFailure: { load: number; plyIndex: number; mode: string } | null;
  lastPlyFailure: { load: number } | null;
  midplaneStrain: number[];   // [εx, εy, γxy]
  midplaneCurvature: number[]; // [κx, κy, κxy]
}

// ─── Matrix utilities ───

function zeros3(): Mat3 {
  return [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
}


function invertMat3(m: Mat3): Mat3 {
  const [[a, b, c], [d, e, f], [g, h, i]] = m;
  const det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  if (Math.abs(det) < 1e-12) throw new Error("Singular matrix in CLT");
  const invDet = 1 / det;
  return [
    [(e * i - f * h) * invDet, (c * h - b * i) * invDet, (b * f - c * e) * invDet],
    [(f * g - d * i) * invDet, (a * i - c * g) * invDet, (c * d - a * f) * invDet],
    [(d * h - e * g) * invDet, (b * g - a * h) * invDet, (a * e - b * d) * invDet],
  ];
}

function mulMat3Vec(m: Mat3, v: number[]): number[] {
  return m.map(row => row[0] * v[0] + row[1] * v[1] + row[2] * v[2]);
}

// ─── Core CLT ───

/** Expand plies if symmetric */
export function expandPlies(def: LaminateDef): PlyDef[] {
  if (!def.symmetric) return [...def.plies];
  const upper = [...def.plies];
  const lower = [...def.plies].reverse();
  return [...upper, ...lower];
}

/** Parse laminate notation like "[0/±45/90]s", "[0/90]4s", "[0]8" into PlyDef array */
export function parseLaminateCode(code: string, materialId: string): LaminateDef {
  const trimmed = code.trim();

  // Extract symmetry flag and repeat count: [...]<repeat>s or [...]<repeat>
  // Examples: [0/90]4s → repeat=4, sym=true; [0]8 → repeat=8, sym=false; [0/±45/90]s → repeat=1, sym=true
  const outerMatch = trimmed.match(/^\[(.+?)\](\d*)([sS]?)$/);
  let inner: string;
  let outerRepeat: number;
  let symmetric: boolean;

  if (outerMatch) {
    inner = outerMatch[1];
    outerRepeat = outerMatch[2] ? parseInt(outerMatch[2]) : 1;
    symmetric = outerMatch[3] === "s" || outerMatch[3] === "S";
  } else {
    // Fallback: no brackets — treat as raw angle list
    symmetric = trimmed.endsWith("s") || trimmed.endsWith("S");
    inner = trimmed.replace(/[\[\]]/g, "").replace(/[sS]$/, "").trim();
    outerRepeat = 1;
  }

  // Parse individual angle groups within brackets
  const singleGroup: PlyDef[] = [];
  const parts = inner.split("/");
  for (const part of parts) {
    const p = part.trim();
    if (p.startsWith("±") || p.startsWith("+-")) {
      const angle = parseFloat(p.replace(/[±+-]/g, ""));
      if (!isNaN(angle)) {
        singleGroup.push({ angle, materialId });
        singleGroup.push({ angle: -angle, materialId });
      }
    } else {
      const match = p.match(/^(-?\d+(?:\.\d+)?)\s*(?:_(\d+))?$/);
      if (match) {
        const angle = parseFloat(match[1]);
        const count = match[2] ? parseInt(match[2]) : 1;
        for (let i = 0; i < count; i++) singleGroup.push({ angle, materialId });
      }
    }
  }

  // Apply outer repeat count
  const plies: PlyDef[] = [];
  for (let r = 0; r < outerRepeat; r++) {
    plies.push(...singleGroup.map(p => ({ ...p })));
  }

  return { plies, symmetric };
}

/** Common laminate presets */
export const LAMINATE_PRESETS: Record<string, string> = {
  "Unidirectional [0]₈": "[0/0/0/0]s",
  "Cross-ply [0/90]₂ₛ": "[0/90/0/90]s",
  "Quasi-isotropic [0/±45/90]ₛ": "[0/±45/90]s",
  "±45 Dominated [±45/0/90]ₛ": "[±45/0/90]s",
  "Hard laminate [0/±45/0]ₛ": "[0/±45/0]s",
  "Soft laminate [±45/90]₂ₛ": "[±45/90/±45/90]s",
};

/** Compute ABD stiffness matrices for a laminate */
export function computeABD(
  plies: PlyDef[],
  materials: Record<string, MaterialProperties>
): ABDResult {
  const n = plies.length;
  const A = zeros3();
  const B = zeros3();
  const D = zeros3();

  // Compute total thickness and z-coordinates
  let totalH = 0;
  const thicknesses: number[] = [];
  for (const ply of plies) {
    const mat = materials[ply.materialId];
    const t = ply.thickness ?? mat.plyThickness;
    thicknesses.push(t);
    totalH += t;
  }

  // z-coordinates from midplane
  let z = -totalH / 2;
  for (let k = 0; k < n; k++) {
    const t = thicknesses[k];
    const zBot = z;
    const zTop = z + t;
    z = zTop;

    const mat = materials[plies[k].materialId];
    if (!mat) continue;
    const Qbar = transformedStiffness(mat, plies[k].angle);

    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        A[i][j] += Qbar[i][j] * (zTop - zBot);
        B[i][j] += 0.5 * Qbar[i][j] * (zTop * zTop - zBot * zBot);
        D[i][j] += (1 / 3) * Qbar[i][j] * (zTop * zTop * zTop - zBot * zBot * zBot);
      }
    }
  }

  // Engineering constants from A matrix (membrane only)
  // A is in GPa·mm, so a = A⁻¹ is in 1/(GPa·mm), Ex = 1/(a11·h) → GPa
  const a = invertMat3(A);
  const Ex = 1 / (a[0][0] * totalH);
  const Ey = 1 / (a[1][1] * totalH);
  const Gxy = 1 / (a[2][2] * totalH);
  const vxy = -a[0][1] / a[0][0];

  return { A, B, D, totalThickness: totalH, plyCount: n, Ex, Ey, Gxy, vxy };
}

/** Stress transformation: global (x,y,xy) → material (1,2,12) */
export function globalToMaterial(sigX: number, sigY: number, tauXY: number, theta: number): [number, number, number] {
  const rad = (theta * Math.PI) / 180;
  const c = Math.cos(rad), s = Math.sin(rad);
  const c2 = c * c, s2 = s * s, cs = c * s;

  const sig1 = c2 * sigX + s2 * sigY + 2 * cs * tauXY;
  const sig2 = s2 * sigX + c2 * sigY - 2 * cs * tauXY;
  const tau12 = -cs * sigX + cs * sigY + (c2 - s2) * tauXY;
  return [sig1, sig2, tau12];
}

// ─── Failure Criteria ───

/** Tsai-Wu failure index (scalar, >= 1.0 means failure) */
export function tsaiWuIndex(s1: number, s2: number, t12: number, m: MaterialProperties): number {
  const F1 = 1 / m.Xt - 1 / m.Xc;
  const F2 = 1 / m.Yt - 1 / m.Yc;
  const F11 = 1 / (m.Xt * m.Xc);
  const F22 = 1 / (m.Yt * m.Yc);
  const F66 = 1 / (m.S12 * m.S12);
  // Interaction coefficient: typically F12 = -0.5 * sqrt(F11 * F22)
  const F12 = -0.5 * Math.sqrt(F11 * F22);

  return F1 * s1 + F2 * s2 + F11 * s1 * s1 + F22 * s2 * s2 + F66 * t12 * t12 + 2 * F12 * s1 * s2;
}

/** Maximum stress failure index */
export function maxStressIndex(s1: number, s2: number, t12: number, m: MaterialProperties): number {
  const ratios = [
    s1 >= 0 ? s1 / m.Xt : -s1 / m.Xc,
    s2 >= 0 ? s2 / m.Yt : -s2 / m.Yc,
    Math.abs(t12) / m.S12,
  ];
  return Math.max(...ratios);
}

/**
 * Compute load factor λ at which failure occurs.
 * Tsai-Wu: solve aλ² + bλ = 1 (quadratic formula for mixed linear+quadratic criterion)
 * MaxStress: λ = 1/FI (linear criterion)
 * Returns the minimum (most critical) factor, or 0 if no valid solution.
 */
function failureLoadFactor(
  _twFI: number, msFI: number,
  s1: number, s2: number, t12: number,
  mat: MaterialProperties,
): number {
  let lf = Infinity;

  // MaxStress is linear: FI scales as λ, so failure at λ = 1/FI
  if (msFI > 0) {
    lf = Math.min(lf, 1 / msFI);
  }

  // Tsai-Wu is mixed: FI(λ) = bλ + aλ² where
  //   b = F1·σ1 + F2·σ2 (linear part)
  //   a = F11·σ1² + F22·σ2² + F66·τ12² + 2F12·σ1·σ2 (quadratic part)
  // Solve aλ² + bλ - 1 = 0
  const F1 = 1 / mat.Xt - 1 / mat.Xc;
  const F2 = 1 / mat.Yt - 1 / mat.Yc;
  const F11 = 1 / (mat.Xt * mat.Xc);
  const F22 = 1 / (mat.Yt * mat.Yc);
  const F66 = 1 / (mat.S12 * mat.S12);
  const F12 = -0.5 * Math.sqrt(F11 * F22);

  const bTW = F1 * s1 + F2 * s2;
  const aTW = F11 * s1 * s1 + F22 * s2 * s2 + F66 * t12 * t12 + 2 * F12 * s1 * s2;

  if (Math.abs(aTW) > 1e-20) {
    const disc = bTW * bTW + 4 * aTW;
    if (disc >= 0) {
      const sqrtDisc = Math.sqrt(disc);
      // Take positive root: λ = (-b + √(b²+4a)) / (2a)
      const lam = (-bTW + sqrtDisc) / (2 * aTW);
      if (lam > 0) lf = Math.min(lf, lam);
    }
  } else if (Math.abs(bTW) > 1e-20) {
    // Purely linear (unlikely): λ = 1/b
    const lam = 1 / bTW;
    if (lam > 0) lf = Math.min(lf, lam);
  }

  return isFinite(lf) ? lf : 0;
}

/** Hashin failure indices (4 modes) */
export function hashinIndices(s1: number, s2: number, t12: number, m: MaterialProperties): {
  ft: number; fc: number; mt: number; mc: number;
} {
  // Fiber tension (σ1 >= 0)
  const ft = s1 >= 0 ? (s1 / m.Xt) ** 2 + (t12 / m.S12) ** 2 : 0;

  // Fiber compression (σ1 < 0)
  const fc = s1 < 0 ? (-s1 / m.Xc) ** 2 : 0;

  // Matrix tension (σ2 >= 0)
  const mt = s2 >= 0 ? (s2 / m.Yt) ** 2 + (t12 / m.S12) ** 2 : 0;

  // Matrix compression (σ2 < 0)
  const mc = s2 < 0 ? (s2 / (2 * m.S12)) ** 2 + ((m.Yc / (2 * m.S12)) ** 2 - 1) * (s2 / m.Yc) + (t12 / m.S12) ** 2 : 0;

  return { ft, fc, mt, mc };
}

function failureMode(tw: number, ms: number, h: { ft: number; fc: number; mt: number; mc: number }): string {
  const entries: [string, number][] = [
    ["Tsai-Wu", tw],
    ["Max Stress", ms],
    ["Hashin FT", h.ft],
    ["Hashin FC", h.fc],
    ["Hashin MT", h.mt],
    ["Hashin MC", h.mc],
  ];
  let maxVal = 0, maxName = "";
  for (const [name, val] of entries) {
    if (val > maxVal) { maxVal = val; maxName = name; }
  }
  return maxName;
}

// ─── Full Laminate Analysis ───

/**
 * Analyze a laminate under given loads.
 * @param plies - Expanded ply stack (bottom to top)
 * @param materials - Material lookup table
 * @param Nx, Ny, Nxy - Force resultants (N/mm)
 * @param Mx, My, Mxy - Moment resultants (N·mm/mm) — typically 0 for in-plane
 */
export function analyzeLaminate(
  plies: PlyDef[],
  materials: Record<string, MaterialProperties>,
  Nx: number, Ny: number, Nxy: number,
  Mx = 0, My = 0, Mxy = 0,
): LaminateAnalysis {
  if (plies.length === 0) {
    const zero3: Mat3 = [[0,0,0],[0,0,0],[0,0,0]];
    return {
      abd: { A: zero3, B: zero3, D: zero3, totalThickness: 0, plyCount: 0, Ex: 0, Ey: 0, Gxy: 0, vxy: 0 },
      plies: [], firstPlyFailure: null, lastPlyFailure: null,
      midplaneStrain: [0,0,0], midplaneCurvature: [0,0,0],
    };
  }

  const abd = computeABD(plies, materials);
  const { A, B, D, totalThickness: totalH } = abd;

  // Solve [A B; B D] * [ε0; κ] = [N; M]
  // A is in GPa·mm, B in GPa·mm², D in GPa·mm³
  // N is in N/mm, M in N·mm/mm → convert to GPa·mm and GPa·mm² by dividing by 1000
  const N = [Nx / 1000, Ny / 1000, Nxy / 1000];
  const M = [Mx / 1000, My / 1000, Mxy / 1000];

  // Check if coupling is negligible
  let bNorm = 0;
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) bNorm += B[i][j] * B[i][j];
  bNorm = Math.sqrt(bNorm);

  let eps0: number[], kappa: number[];

  try {
  if (bNorm < 1e-10) {
    // Decoupled: symmetric laminate
    eps0 = mulMat3Vec(invertMat3(A), N);
    kappa = mulMat3Vec(invertMat3(D), M);
  } else {
    // Full 6x6 solution via block elimination
    const Ainv = invertMat3(A);
    const AinvB = Ainv.map(row =>
      [0, 1, 2].map(j => row[0] * B[0][j] + row[1] * B[1][j] + row[2] * B[2][j])
    );
    // D* = D - B A⁻¹ B
    const BAinvB = B.map(row =>
      [0, 1, 2].map(j => row[0] * AinvB[0][j] + row[1] * AinvB[1][j] + row[2] * AinvB[2][j])
    );
    const Dstar = D.map((row, i) => row.map((v, j) => v - BAinvB[i][j]));
    const DstarInv = invertMat3(Dstar);

    // κ = D*⁻¹ (M - B A⁻¹ N)
    const BAinvN = mulMat3Vec(B.map(row =>
      [0, 1, 2].map(j => row[0] * Ainv[0][j] + row[1] * Ainv[1][j] + row[2] * Ainv[2][j])
    ), N);
    const rhs_kappa = M.map((v, i) => v - BAinvN[i]);
    kappa = mulMat3Vec(DstarInv, rhs_kappa);

    // ε0 = A⁻¹ (N - B κ)
    const Bkappa = mulMat3Vec(B, kappa);
    eps0 = mulMat3Vec(Ainv, N.map((v, i) => v - Bkappa[i]));
  }
  } catch {
    // Singular stiffness matrix (e.g. zero-thickness or degenerate layup)
    eps0 = [0, 0, 0];
    kappa = [0, 0, 0];
  }

  // Per-ply analysis
  const plyResults: PlyResult[] = [];
  const thicknesses = plies.map(p => p.thickness ?? materials[p.materialId]?.plyThickness ?? 0.125);
  let z = -totalH / 2;

  for (let k = 0; k < plies.length; k++) {
    const t = thicknesses[k];
    const zBot = z;
    const zTop = z + t;
    const zMid = (zBot + zTop) / 2;
    z = zTop;

    const mat = materials[plies[k].materialId];
    if (!mat) continue;
    const Qbar = transformedStiffness(mat, plies[k].angle);

    // Strain at ply midpoint: ε = ε0 + z·κ
    const strainX = eps0[0] + zMid * kappa[0];
    const strainY = eps0[1] + zMid * kappa[1];
    const gammaXY = eps0[2] + zMid * kappa[2];

    // Global stress: σ = Q̄ · ε (GPa · strain = GPa → convert to MPa × 1000)
    const sigmaX = (Qbar[0][0] * strainX + Qbar[0][1] * strainY + Qbar[0][2] * gammaXY) * 1000;
    const sigmaY = (Qbar[1][0] * strainX + Qbar[1][1] * strainY + Qbar[1][2] * gammaXY) * 1000;
    const tauXY = (Qbar[2][0] * strainX + Qbar[2][1] * strainY + Qbar[2][2] * gammaXY) * 1000;

    // Transform to material axes
    const [sigma1, sigma2, tau12] = globalToMaterial(sigmaX, sigmaY, tauXY, plies[k].angle);

    // Failure criteria
    const tw = tsaiWuIndex(sigma1, sigma2, tau12, mat);
    const ms = maxStressIndex(sigma1, sigma2, tau12, mat);
    const h = hashinIndices(sigma1, sigma2, tau12, mat);
    const maxFI = Math.max(tw, ms, h.ft, h.fc, h.mt, h.mc);
    const failed = maxFI >= 1.0;
    const mode = failureMode(tw, ms, h);

    plyResults.push({
      plyIndex: k,
      angle: plies[k].angle,
      materialId: plies[k].materialId,
      zBot, zTop,
      sigmaX, sigmaY, tauXY,
      sigma1, sigma2, tau12,
      tsaiWu: tw, maxStress: ms,
      hashinFT: h.ft, hashinFC: h.fc, hashinMT: h.mt, hashinMC: h.mc,
      failed, failureMode: mode,
    });
  }

  // First ply failure (FPF): find which ply fails first as load increases
  // For Tsai-Wu (mixed linear+quadratic): solve aλ² + bλ - 1 = 0 where FI(λ) = bλ + aλ²
  // For maxStress (linear): λ = 1/FI
  let fpf: LaminateAnalysis["firstPlyFailure"] = null;
  let minLoadFactor = Infinity;
  for (const pr of plyResults) {
    const loadFactor = failureLoadFactor(pr.tsaiWu, pr.maxStress, pr.sigma1, pr.sigma2, pr.tau12,
      materials[pr.materialId]);
    if (loadFactor > 0 && loadFactor < minLoadFactor) {
      minLoadFactor = loadFactor;
      fpf = { load: loadFactor, plyIndex: pr.plyIndex, mode: pr.failureMode };
    }
  }

  // Last ply failure (LPF): upper bound estimate without progressive degradation.
  // This gives the load factor at which the strongest ply fails in the undegraded laminate.
  // True LPF (with stiffness redistribution) requires progressiveFailure().
  let maxLoadFactor = 0;
  for (const pr of plyResults) {
    const loadFactor = failureLoadFactor(pr.tsaiWu, pr.maxStress, pr.sigma1, pr.sigma2, pr.tau12,
      materials[pr.materialId]);
    if (loadFactor > maxLoadFactor) maxLoadFactor = loadFactor;
  }

  return {
    abd,
    plies: plyResults,
    firstPlyFailure: fpf,
    lastPlyFailure: maxLoadFactor > 0 ? { load: maxLoadFactor } : null,
    midplaneStrain: eps0,
    midplaneCurvature: kappa,
  };
}

/**
 * Progressive failure analysis: increase load factor from 0 to target,
 * degrading failed plies (Camanho degradation).
 * Returns load-factor vs max-failure-index curve.
 */
export function progressiveFailure(
  plies: PlyDef[],
  materials: Record<string, MaterialProperties>,
  Nx: number, Ny: number, Nxy: number,
  steps = 50,
): { loadFactor: number; maxFI: number; failedPlies: number }[] {
  const curve: { loadFactor: number; maxFI: number; failedPlies: number }[] = [];
  const degradedMaterials = { ...materials };

  // Deep copy materials for degradation
  for (const id of Object.keys(degradedMaterials)) {
    degradedMaterials[id] = { ...degradedMaterials[id] };
  }

  // Deep copy plies to avoid mutating caller's array
  const workPlies = plies.map(p => ({ ...p }));

  const failedPlySet = new Set<number>();

  for (let i = 0; i <= steps; i++) {
    const lf = (i / steps) * 2.0; // sweep from 0 to 2x applied load
    const result = analyzeLaminate(workPlies, degradedMaterials, Nx * lf, Ny * lf, Nxy * lf);

    let maxFI = 0;
    for (const pr of result.plies) {
      const fi = Math.max(pr.tsaiWu, pr.hashinFT, pr.hashinFC, pr.hashinMT, pr.hashinMC);
      if (fi > maxFI) maxFI = fi;

      // Degrade failed plies (Camanho: reduce transverse and shear to ~1%)
      if (fi >= 1.0 && !failedPlySet.has(pr.plyIndex)) {
        failedPlySet.add(pr.plyIndex);
        // Create degraded copy of this ply's material
        const matId = workPlies[pr.plyIndex].materialId;
        const degraded = { ...degradedMaterials[matId] };
        // Determine failure mode for degradation strategy
        const hasFiber = pr.hashinFT >= 1.0 || pr.hashinFC >= 1.0;
        const hasMatrix = pr.hashinMT >= 1.0 || pr.hashinMC >= 1.0;
        // If only Tsai-Wu/MaxStress triggered (no Hashin mode active),
        // apply general matrix degradation as conservative default
        const noHashinMode = !hasFiber && !hasMatrix;
        // Matrix-dominated failure: degrade E2, G12
        if ((hasMatrix || noHashinMode) && !hasFiber) {
          degraded.E2 *= 0.01;
          degraded.G12 *= 0.01;
          degraded.Yt *= 0.01;
          degraded.Yc *= 0.01;
          degraded.S12 *= 0.01;
        }
        // Fiber failure: degrade everything (including E2, G12 — no double degradation)
        if (hasFiber) {
          degraded.E1 *= 0.01;
          degraded.E2 *= 0.01;
          degraded.G12 *= 0.01;
          degraded.Yt *= 0.01;
          degraded.Yc *= 0.01;
          degraded.S12 *= 0.01;
        }
        // Use unique ID for this degraded ply
        const newId = `${matId}_deg_${pr.plyIndex}`;
        degradedMaterials[newId] = degraded;
        workPlies[pr.plyIndex] = { ...workPlies[pr.plyIndex], materialId: newId };
      }
    }

    curve.push({ loadFactor: lf, maxFI, failedPlies: failedPlySet.size });
  }

  return curve;
}
