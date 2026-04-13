/**
 * Lekhnitskii anisotropic stress field engine.
 *
 * Computes stress concentration around elliptical holes in orthotropic plates
 * using Lekhnitskii's complex variable approach.
 *
 * Reference: Lekhnitskii, "Anisotropic Plates", 3rd Ed. (1968)
 *            Savin, "Stress Concentration around Holes" (1961)
 *            Whitney & Nuismer, "Stress Fracture Criteria" JCMA (1974)
 */

import type { MaterialProperties } from "./materials";
// Lekhnitskii stress field module
import type { DefectParams } from "./types";

/** Complex number utilities */
interface Complex {
  re: number;
  im: number;
}

function cadd(a: Complex, b: Complex): Complex {
  return { re: a.re + b.re, im: a.im + b.im };
}

function csub(a: Complex, b: Complex): Complex {
  return { re: a.re - b.re, im: a.im - b.im };
}

function cmul(a: Complex, b: Complex): Complex {
  return { re: a.re * b.re - a.im * b.im, im: a.re * b.im + a.im * b.re };
}

function cdiv(a: Complex, b: Complex): Complex {
  const d = b.re * b.re + b.im * b.im;
  if (d < 1e-30) return { re: 0, im: 0 };
  return { re: (a.re * b.re + a.im * b.im) / d, im: (a.im * b.re - a.re * b.im) / d };
}

function csqrt(z: Complex): Complex {
  const r = Math.sqrt(z.re * z.re + z.im * z.im);
  const t = Math.atan2(z.im, z.re);
  const sr = Math.sqrt(r);
  return { re: sr * Math.cos(t / 2), im: sr * Math.sin(t / 2) };
}

function cneg(z: Complex): Complex {
  return { re: -z.re, im: -z.im };
}

function cmag(z: Complex): number {
  return Math.sqrt(z.re * z.re + z.im * z.im);
}

/** Stress field grid point */
export interface StressPoint {
  x: number;     // mm
  y: number;     // mm
  sigX: number;  // MPa
  sigY: number;  // MPa
  tauXY: number; // MPa
  vonMises: number;   // MPa
  sig1: number;  // Principal stress 1
  sig2: number;  // Principal stress 2
  maxShear: number;
  // Material-axis stresses (if material given)
  sigma1?: number;
  sigma2?: number;
  tau12?: number;
  tsaiWu?: number;
}

/** Grid of stress results */
export interface StressFieldResult {
  grid: StressPoint[][];
  nx: number;
  ny: number;
  xMin: number; xMax: number;
  yMin: number; yMax: number;
  globalMax: {
    vonMises: number;
    sigX: number;
    sigY: number;
    tauXY: number;
  };
}

/**
 * Compute Lekhnitskii characteristic roots for orthotropic material.
 * Solves: a11*μ⁴ - 2*a16*μ³ + (2*a12+a66)*μ² - 2*a26*μ + a22 = 0
 * For orthotropic: a16=a26=0, simplifies to biquadratic
 */
function characteristicRoots(mat: MaterialProperties): [Complex, Complex] {
  const E1 = mat.E1 * 1000; // GPa → MPa for consistency
  const E2 = mat.E2 * 1000;
  const G12 = mat.G12 * 1000;
  const v12 = mat.v12;

  // Compliance coefficients
  const a11 = 1 / E1;
  const a22 = 1 / E2;
  const a12 = -v12 / E1;
  const a66 = 1 / G12;

  // Biquadratic: a11*μ⁴ + (2*a12+a66)*μ² + a22 = 0
  // Let t = μ², solve a11*t² + (2*a12+a66)*t + a22 = 0
  const A = a11;
  const B = 2 * a12 + a66;
  const C = a22;

  const disc = B * B - 4 * A * C;

  let mu1: Complex, mu2: Complex;

  if (disc < 0) {
    // Two pairs of complex conjugate roots
    const realPart = -B / (2 * A);
    const imagPart = Math.sqrt(-disc) / (2 * A);

    // μ² = realPart ± i*imagPart → μ = sqrt of complex
    const t1: Complex = { re: realPart, im: imagPart };
    const t2: Complex = { re: realPart, im: -imagPart };
    mu1 = csqrt(t1);
    mu2 = csqrt(t2);
  } else {
    // Real roots for μ²
    const t1 = (-B + Math.sqrt(disc)) / (2 * A);
    const t2 = (-B - Math.sqrt(disc)) / (2 * A);

    if (t1 < 0) {
      mu1 = { re: 0, im: Math.sqrt(-t1) };
    } else {
      mu1 = { re: Math.sqrt(t1), im: 0 };
    }
    if (t2 < 0) {
      mu2 = { re: 0, im: Math.sqrt(-t2) };
    } else {
      mu2 = { re: Math.sqrt(t2), im: 0 };
    }
  }

  // Ensure imaginary parts are positive (take roots in upper half-plane)
  if (mu1.im < 0) { mu1.re = -mu1.re; mu1.im = -mu1.im; }
  if (mu2.im < 0) { mu2.re = -mu2.re; mu2.im = -mu2.im; }

  return [mu1, mu2];
}

/**
 * Stress field around an elliptical hole in an infinite orthotropic plate.
 * Uses Lekhnitskii's complex potentials Φ₁(z₁) and Φ₂(z₂).
 *
 * Applied far-field: σx∞, σy∞, τxy∞
 * Ellipse: semi-axes a (along x), b (along y)
 */
function ellipseStress(
  px: number, py: number, // point coords (mm)
  a: number, b: number,  // ellipse semi-axes (mm)
  cx: number, cy: number, // ellipse center (mm)
  angle: number,           // ellipse rotation (degrees)
  sigXinf: number, sigYinf: number, tauXYinf: number, // far-field stress (MPa)
  mu1: Complex, mu2: Complex, // characteristic roots
): { sigX: number; sigY: number; tauXY: number } {
  // Transform point to ellipse-local coords
  const rad = (-angle * Math.PI) / 180;
  const cosA = Math.cos(rad), sinA = Math.sin(rad);
  const dx = px - cx;
  const dy = py - cy;
  const x = cosA * dx + sinA * dy;
  const y = -sinA * dx + cosA * dy;

  // Also rotate far-field stress to ellipse-local
  const c2 = cosA * cosA, s2 = sinA * sinA, cs = cosA * sinA;
  const sxL = c2 * sigXinf + s2 * sigYinf + 2 * cs * tauXYinf;
  const syL = s2 * sigXinf + c2 * sigYinf - 2 * cs * tauXYinf;
  const txyL = -cs * sigXinf + cs * sigYinf + (c2 - s2) * tauXYinf;

  // Check if point is inside ellipse
  const ellCheck = (x * x) / (a * a) + (y * y) / (b * b);
  if (ellCheck < 1.0) {
    return { sigX: 0, sigY: 0, tauXY: 0 };
  }

  // Complex coordinates z_k = x + μ_k * y
  const z1: Complex = { re: x + mu1.re * y, im: mu1.im * y };
  const z2: Complex = { re: x + mu2.re * y, im: mu2.im * y };

  // Mapping function: ζ_k = (z_k + sqrt(z_k² - a² - μ_k²*b²)) / (a - i*μ_k*b)
  // where ζ maps exterior of ellipse to exterior of unit circle

  const a2 = a * a, b2 = b * b;

  // z₁² - (a² + μ₁²·b²)
  const mu1sq = cmul(mu1, mu1);
  const z1sq = cmul(z1, z1);
  const inner1 = csub(z1sq, { re: a2 + mu1sq.re * b2, im: mu1sq.im * b2 });
  const sqrt1 = csqrt(inner1);

  // z₂² - (a² + μ₂²·b²)
  const mu2sq = cmul(mu2, mu2);
  const z2sq = cmul(z2, z2);
  const inner2 = csub(z2sq, { re: a2 + mu2sq.re * b2, im: mu2sq.im * b2 });
  const sqrt2 = csqrt(inner2);

  // Conformal mapping: ζ_k = (z_k + η_k) / (a - i·μ_k·b)
  // where η_k = sqrt(z_k² - a² - μ_k²·b²)
  // When |ζ| < 1, flip to other branch: η → -η
  const den1: Complex = { re: a + mu1.im * b, im: -mu1.re * b };
  const den2: Complex = { re: a + mu2.im * b, im: -mu2.re * b };

  // Track effective η (may flip sign for exterior branch selection)
  let eta1 = sqrt1;
  let eta2 = sqrt2;

  let zeta1 = cdiv(cadd(z1, eta1), den1);
  if (cmag(zeta1) < 1) {
    eta1 = cneg(sqrt1);
    zeta1 = cdiv(cadd(z1, eta1), den1);
  }
  let zeta2 = cdiv(cadd(z2, eta2), den2);
  if (cmag(zeta2) < 1) {
    eta2 = cneg(sqrt2);
    zeta2 = cdiv(cadd(z2, eta2), den2);
  }

  // BJSFM-validated coefficients (Lekhnitskii boundary conditions)
  // Generalized for elliptical hole: a (x semi-axis), b (y semi-axis)
  // alpha = ½(i·τxy∞·a - σy∞·b),  beta = ½(τxy∞·b - i·σx∞·a)
  const alpha: Complex = { re: -syL * b / 2, im: txyL * a / 2 };
  const beta: Complex = { re: txyL * b / 2, im: -sxL * a / 2 };

  const mu_diff = csub(mu1, mu2);
  if (mu_diff.re * mu_diff.re + mu_diff.im * mu_diff.im < 1e-20) {
    // Degenerate case (μ₁ ≈ μ₂, near-isotropic)
    return { sigX: sxL, sigY: syL, tauXY: txyL };
  }

  // C1 = (beta - mu2*alpha) / (mu1 - mu2)
  // C2 = -(beta - mu1*alpha) / (mu1 - mu2)
  const C1 = cdiv(csub(beta, cmul(mu2, alpha)), mu_diff);
  const C2 = cneg(cdiv(csub(beta, cmul(mu1, alpha)), mu_diff));

  // Potential derivatives: φ_k' = -C_k / ζ_k² · dζ_k/dz_k
  // dζ_k/dz_k = (1 + z_k/η_k_eff) · κ_k  where η_k_eff includes branch sign
  const kappa1 = cdiv({ re: 1, im: 0 }, den1);
  const kappa2 = cdiv({ re: 1, im: 0 }, den2);

  const zeta1sq = cmul(zeta1, zeta1);
  const zeta2sq = cmul(zeta2, zeta2);

  const one: Complex = { re: 1, im: 0 };
  const dzdz1 = cmul(cadd(one, cdiv(z1, eta1)), kappa1);
  const dzdz2 = cmul(cadd(one, cdiv(z2, eta2)), kappa2);

  const phi1_prime = cmul(cneg(cdiv(C1, zeta1sq)), dzdz1);
  const phi2_prime = cmul(cneg(cdiv(C2, zeta2sq)), dzdz2);

  // Stress perturbations (Lekhnitskii):
  // Δσx = 2·Re[μ₁²·φ₁' + μ₂²·φ₂']
  // Δσy = 2·Re[φ₁' + φ₂']
  // Δτxy = -2·Re[μ₁·φ₁' + μ₂·φ₂']
  const mu1sq_phi1 = cmul(mu1sq, phi1_prime);
  const mu2sq_phi2 = cmul(mu2sq, phi2_prime);
  const dSigX = 2 * (mu1sq_phi1.re + mu2sq_phi2.re);
  const dSigY = 2 * (phi1_prime.re + phi2_prime.re);
  const mu1_phi1 = cmul(mu1, phi1_prime);
  const mu2_phi2 = cmul(mu2, phi2_prime);
  const dTauXY = -2 * (mu1_phi1.re + mu2_phi2.re);

  // Total = far-field + perturbation
  let sigXL = sxL + dSigX;
  let sigYL = syL + dSigY;
  let tauXYL = txyL + dTauXY;

  // Rotate back to global
  const sigX = c2 * sigXL + s2 * sigYL - 2 * cs * tauXYL;
  const sigY = s2 * sigXL + c2 * sigYL + 2 * cs * tauXYL;
  const tauXY = cs * sigXL - cs * sigYL + (c2 - s2) * tauXYL;

  return { sigX, sigY, tauXY };
}

/**
 * Compute von Mises equivalent stress
 */
function vonMises(sx: number, sy: number, txy: number): number {
  return Math.sqrt(sx * sx - sx * sy + sy * sy + 3 * txy * txy);
}

/**
 * Compute principal stresses and max shear
 */
function principalStresses(sx: number, sy: number, txy: number): {
  sig1: number; sig2: number; maxShear: number;
} {
  const avg = (sx + sy) / 2;
  const R = Math.sqrt(((sx - sy) / 2) ** 2 + txy * txy);
  return { sig1: avg + R, sig2: avg - R, maxShear: R };
}

/**
 * Compute full stress field for a plate with elliptical defects.
 *
 * @param plateW - Plate width (mm)
 * @param plateH - Plate height (mm)
 * @param defects - Array of defect parameters
 * @param nDefects - Number of active defects
 * @param sigXinf - Far-field stress X (MPa)
 * @param sigYinf - Far-field stress Y (MPa)
 * @param material - Optional material for failure indices
 * @param resolution - Grid resolution (default 80)
 */
export function computeStressField(
  plateW: number,
  plateH: number,
  defects: DefectParams[],
  nDefects: number,
  sigXinf: number,
  sigYinf: number,
  material?: MaterialProperties,
  resolution = 80,
  layupRotation = 0,
  tauXYinf = 0,
): StressFieldResult {
  // Default orthotropic material for characteristic roots
  const mat: MaterialProperties = material ?? {
    id: "default", name: "default", description: "",
    E1: 181, E2: 10.3, G12: 7.17, v12: 0.28,
    Xt: 1500, Xc: 1500, Yt: 40, Yc: 246, S12: 68,
    plyThickness: 0.125,
  };

  const [mu1, mu2] = characteristicRoots(mat);

  const nx = resolution;
  const ny = Math.round(resolution * plateH / plateW);
  const dx = plateW / (nx - 1);
  const dy = plateH / (ny - 1);

  const grid: StressPoint[][] = [];
  const globalMax = { vonMises: 0, sigX: -Infinity, sigY: -Infinity, tauXY: 0 };

  for (let j = 0; j < ny; j++) {
    const row: StressPoint[] = [];
    const y = j * dy;

    for (let i = 0; i < nx; i++) {
      const x = i * dx;

      // Start with far-field stress
      let sigX = sigXinf;
      let sigY = sigYinf;
      let tauXY = tauXYinf;

      // Superpose stress perturbations from each defect
      for (let d = 0; d < nDefects; d++) {
        const def = defects[d];
        if (!def) continue;

        const aAxis = Math.max(def.half_length, 0.1); // semi-major
        const bAxis = Math.max(def.width / 2, 0.05);  // semi-minor

        const result = ellipseStress(
          x, y,
          aAxis, bAxis,
          def.x, def.y,
          def.angle,
          sigXinf, sigYinf, tauXYinf,
          mu1, mu2,
        );

        // Superposition: add perturbation (subtract far-field to avoid double counting)
        sigX += result.sigX - sigXinf;
        sigY += result.sigY - sigYinf;
        tauXY += result.tauXY - tauXYinf;
      }

      const vm = vonMises(sigX, sigY, tauXY);
      const { sig1, sig2, maxShear } = principalStresses(sigX, sigY, tauXY);

      const point: StressPoint = {
        x, y, sigX, sigY, tauXY,
        vonMises: vm, sig1, sig2, maxShear,
      };

      // Material-axis stresses if material provided
      if (material) {
        // Transform global stresses to material axes using layup rotation
        const matRad = (layupRotation * Math.PI) / 180;
        const mc = Math.cos(matRad), ms = Math.sin(matRad);
        const mc2 = mc * mc, ms2 = ms * ms, mcs = mc * ms;
        point.sigma1 = mc2 * sigX + ms2 * sigY + 2 * mcs * tauXY;
        point.sigma2 = ms2 * sigX + mc2 * sigY - 2 * mcs * tauXY;
        point.tau12 = -mcs * sigX + mcs * sigY + (mc2 - ms2) * tauXY;

        // Tsai-Wu
        const F1 = 1 / material.Xt - 1 / material.Xc;
        const F2 = 1 / material.Yt - 1 / material.Yc;
        const F11 = 1 / (material.Xt * material.Xc);
        const F22 = 1 / (material.Yt * material.Yc);
        const F66 = 1 / (material.S12 * material.S12);
        const F12 = -0.5 * Math.sqrt(F11 * F22);
        point.tsaiWu = F1 * point.sigma1 + F2 * point.sigma2 +
          F11 * point.sigma1 * point.sigma1 + F22 * point.sigma2 * point.sigma2 +
          F66 * point.tau12 * point.tau12 + 2 * F12 * point.sigma1 * point.sigma2;
      }

      // Track maxima
      if (vm > globalMax.vonMises) globalMax.vonMises = vm;
      if (sigX > globalMax.sigX) globalMax.sigX = sigX;
      if (sigY > globalMax.sigY) globalMax.sigY = sigY;
      if (Math.abs(tauXY) > globalMax.tauXY) globalMax.tauXY = Math.abs(tauXY);

      row.push(point);
    }
    grid.push(row);
  }

  return {
    grid, nx, ny,
    xMin: 0, xMax: plateW, yMin: 0, yMax: plateH,
    globalMax,
  };
}

/**
 * Extract a field component from the stress grid as a flat Float64Array
 * for efficient rendering.
 */
export type FieldComponent = "vonMises" | "sigX" | "sigY" | "tauXY" | "sig1" | "sig2" | "maxShear" | "tsaiWu";

export function extractField(result: StressFieldResult, component: FieldComponent): {
  data: Float64Array; min: number; max: number;
} {
  const { grid, nx, ny } = result;
  const data = new Float64Array(nx * ny);
  let min = Infinity, max = -Infinity;

  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const val = grid[j][i][component] ?? 0;
      data[j * nx + i] = val;
      if (val < min) min = val;
      if (val > max) max = val;
    }
  }

  return { data, min, max };
}

/**
 * Color mapping for heatmap rendering.
 * Returns [r, g, b, a] in 0-255 range.
 */
export type ColorMap = "viridis" | "plasma" | "inferno" | "turbo" | "coolwarm" | "jet";

const COLORMAPS: Record<ColorMap, number[][]> = {
  viridis: [
    [68, 1, 84], [72, 35, 116], [64, 67, 135], [52, 94, 141],
    [41, 120, 142], [32, 144, 140], [34, 167, 132], [68, 190, 112],
    [121, 209, 81], [189, 222, 38], [253, 231, 37],
  ],
  plasma: [
    [13, 8, 135], [75, 3, 161], [125, 3, 168], [168, 34, 150],
    [203, 70, 121], [229, 107, 93], [248, 148, 65], [253, 195, 40],
    [240, 249, 33],
  ],
  inferno: [
    [0, 0, 4], [22, 11, 57], [66, 10, 104], [106, 23, 110],
    [147, 38, 103], [188, 55, 84], [221, 81, 58], [243, 118, 27],
    [252, 165, 10], [246, 215, 70], [252, 255, 164],
  ],
  turbo: [
    [48, 18, 59], [67, 84, 187], [55, 148, 237], [30, 206, 193],
    [67, 237, 118], [160, 252, 52], [228, 231, 26], [255, 181, 39],
    [246, 112, 29], [209, 49, 20], [122, 4, 3],
  ],
  coolwarm: [
    [59, 76, 192], [98, 130, 234], [141, 176, 254], [184, 208, 249],
    [221, 221, 221], [245, 196, 173], [241, 152, 115], [222, 96, 69],
    [180, 4, 38],
  ],
  jet: [
    [0, 0, 127], [0, 0, 255], [0, 127, 255], [0, 255, 255],
    [127, 255, 127], [255, 255, 0], [255, 127, 0], [255, 0, 0],
    [127, 0, 0],
  ],
};

export function mapColor(value: number, min: number, max: number, colormap: ColorMap = "turbo"): [number, number, number, number] {
  const stops = COLORMAPS[colormap];
  const n = stops.length - 1;
  const range = max - min;
  if (range < 1e-10) return [stops[0][0], stops[0][1], stops[0][2], 255];

  const t = Math.max(0, Math.min(1, (value - min) / range));
  const idx = t * n;
  const i = Math.min(Math.floor(idx), n - 1);
  const f = idx - i;

  const r = Math.round(stops[i][0] + (stops[i + 1][0] - stops[i][0]) * f);
  const g = Math.round(stops[i][1] + (stops[i + 1][1] - stops[i][1]) * f);
  const b = Math.round(stops[i][2] + (stops[i + 1][2] - stops[i][2]) * f);

  return [r, g, b, 255];
}

/**
 * Render stress field to an ImageData buffer for Canvas2D display.
 */
export function renderToImageData(
  result: StressFieldResult,
  component: FieldComponent,
  width: number,
  height: number,
  colormap: ColorMap = "turbo",
  customMin?: number,
  customMax?: number,
): ImageData {
  const { data, min: fieldMin, max: fieldMax } = extractField(result, component);
  const min = customMin ?? fieldMin;
  const max = customMax ?? fieldMax;
  const { nx, ny } = result;

  const imgData = new ImageData(width, height);
  const pixels = imgData.data;

  for (let py = 0; py < height; py++) {
    for (let px = 0; px < width; px++) {
      // Map pixel to grid coords via bilinear interpolation
      const gx = (px / (width - 1)) * (nx - 1);
      const gy = (py / (height - 1)) * (ny - 1);

      const ix = Math.min(Math.floor(gx), nx - 2);
      const iy = Math.min(Math.floor(gy), ny - 2);
      const fx = gx - ix;
      const fy = gy - iy;

      // Bilinear interpolation
      const v00 = data[iy * nx + ix];
      const v10 = data[iy * nx + ix + 1];
      const v01 = data[(iy + 1) * nx + ix];
      const v11 = data[(iy + 1) * nx + ix + 1];
      const val = v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) +
                  v01 * (1 - fx) * fy + v11 * fx * fy;

      const [r, g, b, a] = mapColor(val, min, max, colormap);
      const idx = (py * width + px) * 4;
      pixels[idx] = r;
      pixels[idx + 1] = g;
      pixels[idx + 2] = b;
      pixels[idx + 3] = a;
    }
  }

  return imgData;
}
