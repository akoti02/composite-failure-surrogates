/**
 * Ply-resolved stress field computations.
 *
 * Takes a base Lekhnitskii stress field and produces:
 * - Per-ply material-axis stresses via coordinate rotation
 * - Failure indices (Tsai-Wu, Hashin) at every grid point
 * - Worst-ply envelope
 * - ML-calibrated scaling
 * - Contour line extraction (marching squares)
 */

import type { StressFieldResult, StressPoint } from "./stress-field";
import type { MaterialProperties } from "./materials";
import { globalToMaterial, tsaiWuIndex, hashinIndices, maxStressIndex } from "./clt";

/** Per-ply stress/failure at a single grid point */
export interface PlyFieldPoint {
  sigma1: number;
  sigma2: number;
  tau12: number;
  tsaiWu: number;
  maxStress: number;
  hashinFT: number;
  hashinFC: number;
  hashinMT: number;
  hashinMC: number;
  maxFI: number;
  failureMode: string;
}

/** Result for one ply across the entire grid */
export interface PlyFieldResult {
  plyIndex: number;
  angle: number;
  grid: PlyFieldPoint[][];
  nx: number;
  ny: number;
  maxFI: number;
  dominantMode: string;
}

/** Worst-ply envelope point */
export interface WorstPlyPoint {
  worstPly: number;
  maxFI: number;
  failureMode: string;
  sigma1: number;
  sigma2: number;
  tau12: number;
}

/** Contour line segment */
export interface ContourLine {
  level: number;
  segments: { x1: number; y1: number; x2: number; y2: number }[];
}

function failureModeLabel(tw: number, ms: number, h: { ft: number; fc: number; mt: number; mc: number }): string {
  const entries: [string, number][] = [
    ["Tsai-Wu", tw],
    ["Max Stress", ms],
    ["Fiber Tension", h.ft],
    ["Fiber Comp.", h.fc],
    ["Matrix Tension", h.mt],
    ["Matrix Comp.", h.mc],
  ];
  let maxVal = 0, maxName = "Safe";
  for (const [name, val] of entries) {
    if (val > maxVal) { maxVal = val; maxName = name; }
  }
  return maxName;
}

/** Compute ply-resolved stress field for a single ply angle */
export function computePlyField(
  baseResult: StressFieldResult,
  plyIndex: number,
  plyAngle: number,
  material: MaterialProperties,
): PlyFieldResult {
  const { grid, nx, ny } = baseResult;
  const plyGrid: PlyFieldPoint[][] = [];
  let overallMaxFI = 0;
  let dominantMode = "Safe";

  for (let j = 0; j < ny; j++) {
    const row: PlyFieldPoint[] = [];
    for (let i = 0; i < nx; i++) {
      const pt = grid[j][i];
      const [s1, s2, t12] = globalToMaterial(pt.sigX, pt.sigY, pt.tauXY, plyAngle);

      const tw = tsaiWuIndex(s1, s2, t12, material);
      const ms = maxStressIndex(s1, s2, t12, material);
      const h = hashinIndices(s1, s2, t12, material);
      const maxFI = Math.max(tw, ms, h.ft, h.fc, h.mt, h.mc);
      const mode = failureModeLabel(tw, ms, h);

      if (maxFI > overallMaxFI) {
        overallMaxFI = maxFI;
        dominantMode = mode;
      }

      row.push({
        sigma1: s1, sigma2: s2, tau12: t12,
        tsaiWu: tw, maxStress: ms,
        hashinFT: h.ft, hashinFC: h.fc, hashinMT: h.mt, hashinMC: h.mc,
        maxFI, failureMode: mode,
      });
    }
    plyGrid.push(row);
  }

  return {
    plyIndex, angle: plyAngle, grid: plyGrid,
    nx, ny, maxFI: overallMaxFI, dominantMode,
  };
}

/** Compute ply fields for all plies */
export function computeAllPlyFields(
  baseResult: StressFieldResult,
  plyAngles: number[],
  material: MaterialProperties,
): PlyFieldResult[] {
  return plyAngles.map((angle, idx) => computePlyField(baseResult, idx, angle, material));
}

/** Compute worst-ply envelope: at each grid point, find the ply with highest FI */
export function computeWorstPlyField(
  allPlyFields: PlyFieldResult[],
  nx: number,
  ny: number,
): WorstPlyPoint[][] {
  const result: WorstPlyPoint[][] = [];

  for (let j = 0; j < ny; j++) {
    const row: WorstPlyPoint[] = [];
    for (let i = 0; i < nx; i++) {
      let worstPly = 0;
      let maxFI = -Infinity;
      let failureMode = "Safe";
      let sigma1 = 0, sigma2 = 0, tau12 = 0;

      for (let p = 0; p < allPlyFields.length; p++) {
        const pt = allPlyFields[p].grid[j][i];
        if (pt.maxFI > maxFI) {
          maxFI = pt.maxFI;
          worstPly = p;
          failureMode = pt.failureMode;
          sigma1 = pt.sigma1;
          sigma2 = pt.sigma2;
          tau12 = pt.tau12;
        }
      }

      row.push({ worstPly, maxFI, failureMode, sigma1, sigma2, tau12 });
    }
    result.push(row);
  }

  return result;
}

/** Scale stress field to match ML-predicted peak */
export function applyMLScaling(
  baseResult: StressFieldResult,
  mlPeak: number,
  material?: MaterialProperties,
): { scaled: StressFieldResult; factor: number } {
  const analyticalPeak = baseResult.globalMax.vonMises;
  if (analyticalPeak < 1e-10) return { scaled: baseResult, factor: 1.0 };

  const factor = mlPeak / analyticalPeak;

  const newGrid: StressPoint[][] = baseResult.grid.map(row =>
    row.map(pt => {
      const sigX = pt.sigX * factor;
      const sigY = pt.sigY * factor;
      const tauXY = pt.tauXY * factor;
      const s1 = pt.sigma1 != null ? pt.sigma1 * factor : undefined;
      const s2 = pt.sigma2 != null ? pt.sigma2 * factor : undefined;
      const t12 = pt.tau12 != null ? pt.tau12 * factor : undefined;

      // Recalculate tsaiWu from scaled material-axis stresses (quadratic — doesn't scale linearly)
      let tsaiWu = pt.tsaiWu;
      if (material && s1 != null && s2 != null && t12 != null) {
        tsaiWu = tsaiWuIndex(s1, s2, t12, material);
      }

      return {
        ...pt,
        sigX, sigY, tauXY,
        vonMises: pt.vonMises * factor,
        sig1: pt.sig1 * factor,
        sig2: pt.sig2 * factor,
        maxShear: pt.maxShear * factor,
        sigma1: s1,
        sigma2: s2,
        tau12: t12,
        tsaiWu,
      };
    })
  );

  return {
    scaled: {
      ...baseResult,
      grid: newGrid,
      globalMax: {
        vonMises: baseResult.globalMax.vonMises * factor,
        sigX: baseResult.globalMax.sigX * factor,
        sigY: baseResult.globalMax.sigY * factor,
        tauXY: baseResult.globalMax.tauXY * factor,
      },
    },
    factor,
  };
}

/** Extract iso-value contour lines using marching squares */
export function extractContours(
  data: Float64Array,
  nx: number,
  ny: number,
  xMin: number,
  xMax: number,
  yMin: number,
  yMax: number,
  numLevels = 10,
): ContourLine[] {
  // Find data range
  let dMin = Infinity, dMax = -Infinity;
  for (let k = 0; k < data.length; k++) {
    if (data[k] < dMin) dMin = data[k];
    if (data[k] > dMax) dMax = data[k];
  }
  if (dMax - dMin < 1e-10) return [];

  const dx = (xMax - xMin) / (nx - 1);
  const dy = (yMax - yMin) / (ny - 1);

  const contours: ContourLine[] = [];

  for (let l = 1; l < numLevels; l++) {
    const level = dMin + (l / numLevels) * (dMax - dMin);
    const segments: ContourLine["segments"] = [];

    for (let j = 0; j < ny - 1; j++) {
      for (let i = 0; i < nx - 1; i++) {
        const v00 = data[j * nx + i];
        const v10 = data[j * nx + i + 1];
        const v01 = data[(j + 1) * nx + i];
        const v11 = data[(j + 1) * nx + i + 1];

        const x0 = xMin + i * dx;
        const y0 = yMin + j * dy;
        const x1 = x0 + dx;
        const y1 = y0 + dy;

        // Marching squares case index
        let caseIdx = 0;
        if (v00 >= level) caseIdx |= 1;
        if (v10 >= level) caseIdx |= 2;
        if (v11 >= level) caseIdx |= 4;
        if (v01 >= level) caseIdx |= 8;

        if (caseIdx === 0 || caseIdx === 15) continue;

        // Interpolation helper
        const lerp = (va: number, vb: number, pa: number, pb: number) => {
          const t = (level - va) / (vb - va);
          return pa + t * (pb - pa);
        };

        // Edge midpoints
        const bottom = { x: lerp(v00, v10, x0, x1), y: y0 };
        const right = { x: x1, y: lerp(v10, v11, y0, y1) };
        const top = { x: lerp(v01, v11, x0, x1), y: y1 };
        const left = { x: x0, y: lerp(v00, v01, y0, y1) };

        const addSeg = (a: { x: number; y: number }, b: { x: number; y: number }) => {
          segments.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y });
        };

        switch (caseIdx) {
          case 1: case 14: addSeg(bottom, left); break;
          case 2: case 13: addSeg(bottom, right); break;
          case 3: case 12: addSeg(left, right); break;
          case 4: case 11: addSeg(right, top); break;
          case 5: addSeg(bottom, right); addSeg(left, top); break;
          case 6: case 9: addSeg(bottom, top); break;
          case 7: case 8: addSeg(left, top); break;
          case 10: addSeg(bottom, left); addSeg(right, top); break;
        }
      }
    }

    if (segments.length > 0) {
      contours.push({ level, segments });
    }
  }

  return contours;
}
