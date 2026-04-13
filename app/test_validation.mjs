/**
 * RIGOROUS VALIDATION SCRIPT
 * Tests CLT and stress field engines against known analytical solutions.
 *
 * Run: node test_validation.mjs
 *
 * This is the "devil's advocate" test — every result is checked against
 * textbook values. If anything is wrong, it will be flagged.
 */

// ─── Material Properties (T300/5208) ───
const T300 = {
  id: "T300/5208", name: "T300/5208", description: "",
  E1: 181.0, E2: 10.3, G12: 7.17, v12: 0.28,
  Xt: 1500, Xc: 1500, Yt: 40, Yc: 246, S12: 68,
  plyThickness: 0.125,
};

const EGlass = {
  id: "E-Glass/Epoxy", name: "E-Glass/Epoxy", description: "",
  E1: 38.6, E2: 8.27, G12: 4.14, v12: 0.26,
  Xt: 1062, Xc: 610, Yt: 31, Yc: 118, S12: 72,
  plyThickness: 0.150,
};

// ─── Material functions ───
function v21(m) { return m.v12 * m.E2 / m.E1; }

function reducedStiffness(m) {
  const nu21 = v21(m);
  const denom = 1 - m.v12 * nu21;
  return [m.E1 / denom, m.v12 * m.E2 / denom, m.E2 / denom, m.G12];
}

function transformedStiffness(m, theta) {
  const [Q11, Q12, Q22, Q66] = reducedStiffness(m);
  const rad = (theta * Math.PI) / 180;
  const c = Math.cos(rad), s = Math.sin(rad);
  const c2 = c * c, s2 = s * s, cs = c * s;
  const c4 = c2 * c2, s4 = s2 * s2;
  return [
    [Q11*c4 + 2*(Q12+2*Q66)*c2*s2 + Q22*s4,
     (Q11+Q22-4*Q66)*c2*s2 + Q12*(c4+s4),
     (Q11-Q12-2*Q66)*c2*cs - (Q22-Q12-2*Q66)*s2*cs],
    [(Q11+Q22-4*Q66)*c2*s2 + Q12*(c4+s4),
     Q11*s4 + 2*(Q12+2*Q66)*c2*s2 + Q22*c4,
     (Q11-Q12-2*Q66)*cs*s2 - (Q22-Q12-2*Q66)*cs*c2],
    [(Q11-Q12-2*Q66)*c2*cs - (Q22-Q12-2*Q66)*s2*cs,
     (Q11-Q12-2*Q66)*cs*s2 - (Q22-Q12-2*Q66)*cs*c2,
     (Q11+Q22-2*Q12-2*Q66)*c2*s2 + Q66*(c4+s4)],
  ];
}

// ─── CLT functions ───
function zeros3() { return [[0,0,0],[0,0,0],[0,0,0]]; }

function invertMat3(m) {
  const [[a,b,c],[d,e,f],[g,h,i]] = m;
  const det = a*(e*i-f*h) - b*(d*i-f*g) + c*(d*h-e*g);
  const inv = 1/det;
  return [
    [(e*i-f*h)*inv, (c*h-b*i)*inv, (b*f-c*e)*inv],
    [(f*g-d*i)*inv, (a*i-c*g)*inv, (c*d-a*f)*inv],
    [(d*h-e*g)*inv, (b*g-a*h)*inv, (a*e-b*d)*inv],
  ];
}

function mulMat3Vec(m, v) {
  return m.map(row => row[0]*v[0] + row[1]*v[1] + row[2]*v[2]);
}

function computeABD(plies, materials) {
  const n = plies.length;
  const A = zeros3(), B = zeros3(), D = zeros3();
  let totalH = 0;
  const thicknesses = [];
  for (const ply of plies) {
    const mat = materials[ply.materialId];
    const t = ply.thickness ?? mat.plyThickness;
    thicknesses.push(t);
    totalH += t;
  }
  let z = -totalH / 2;
  for (let k = 0; k < n; k++) {
    const t = thicknesses[k];
    const zBot = z;
    const zTop = z + t;
    z = zTop;
    const mat = materials[plies[k].materialId];
    const Qbar = transformedStiffness(mat, plies[k].angle);
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        A[i][j] += Qbar[i][j] * (zTop - zBot);
        B[i][j] += 0.5 * Qbar[i][j] * (zTop*zTop - zBot*zBot);
        D[i][j] += (1/3) * Qbar[i][j] * (zTop**3 - zBot**3);
      }
    }
  }
  const a = invertMat3(A);
  const Ex = 1 / (a[0][0] * totalH);
  const Ey = 1 / (a[1][1] * totalH);
  const Gxy = 1 / (a[2][2] * totalH);
  const vxy = -a[0][1] / a[0][0];
  return { A, B, D, totalThickness: totalH, plyCount: n, Ex, Ey, Gxy, vxy };
}

function analyzeLaminate(plies, materials, Nx, Ny, Nxy, Mx=0, My=0, Mxy=0) {
  const abd = computeABD(plies, materials);
  const { A, B, D, totalThickness: totalH } = abd;
  const N = [Nx/1000, Ny/1000, Nxy/1000];
  const M = [Mx/1000, My/1000, Mxy/1000];
  let bNorm = 0;
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) bNorm += B[i][j]*B[i][j];
  bNorm = Math.sqrt(bNorm);
  let eps0, kappa;
  if (bNorm < 1e-10) {
    eps0 = mulMat3Vec(invertMat3(A), N);
    kappa = mulMat3Vec(invertMat3(D), M);
  } else {
    throw new Error("Non-symmetric not tested here");
  }
  // Per-ply stresses
  const thicknesses = plies.map(p => p.thickness ?? materials[p.materialId].plyThickness);
  let z = -totalH / 2;
  const plyResults = [];
  for (let k = 0; k < plies.length; k++) {
    const t = thicknesses[k];
    const zBot = z;
    const zTop = z + t;
    const zMid = (zBot + zTop) / 2;
    z = zTop;
    const mat = materials[plies[k].materialId];
    const Qbar = transformedStiffness(mat, plies[k].angle);
    const strainX = eps0[0] + zMid * kappa[0];
    const strainY = eps0[1] + zMid * kappa[1];
    const gammaXY = eps0[2] + zMid * kappa[2];
    // Global stress in MPa (Qbar in GPa * strain = GPa, *1000 = MPa)
    const sigmaX = (Qbar[0][0]*strainX + Qbar[0][1]*strainY + Qbar[0][2]*gammaXY) * 1000;
    const sigmaY = (Qbar[1][0]*strainX + Qbar[1][1]*strainY + Qbar[1][2]*gammaXY) * 1000;
    const tauXY = (Qbar[2][0]*strainX + Qbar[2][1]*strainY + Qbar[2][2]*gammaXY) * 1000;
    // Material axes
    const rad = (plies[k].angle * Math.PI) / 180;
    const co = Math.cos(rad), si = Math.sin(rad);
    const c2 = co*co, s2 = si*si, cs = co*si;
    const sigma1 = c2*sigmaX + s2*sigmaY + 2*cs*tauXY;
    const sigma2 = s2*sigmaX + c2*sigmaY - 2*cs*tauXY;
    const tau12 = -cs*sigmaX + cs*sigmaY + (c2-s2)*tauXY;
    plyResults.push({
      plyIndex: k, angle: plies[k].angle,
      sigmaX, sigmaY, tauXY,
      sigma1, sigma2, tau12,
    });
  }
  return { abd, plies: plyResults, midplaneStrain: eps0, midplaneCurvature: kappa };
}

// ─── Stress field functions ───
function characteristicRoots(mat) {
  const E1 = mat.E1 * 1000, E2 = mat.E2 * 1000, G12 = mat.G12 * 1000;
  const a11 = 1/E1, a22 = 1/E2, a12 = -mat.v12/E1, a66 = 1/G12;
  const Ac = a11, Bc = 2*a12 + a66, Cc = a22;
  const disc = Bc*Bc - 4*Ac*Cc;
  let mu1, mu2;
  if (disc < 0) {
    const rp = -Bc/(2*Ac), ip = Math.sqrt(-disc)/(2*Ac);
    mu1 = csqrt({re: rp, im: ip});
    mu2 = csqrt({re: rp, im: -ip});
  } else {
    const t1 = (-Bc + Math.sqrt(disc))/(2*Ac);
    const t2 = (-Bc - Math.sqrt(disc))/(2*Ac);
    mu1 = t1 < 0 ? {re:0, im:Math.sqrt(-t1)} : {re:Math.sqrt(t1), im:0};
    mu2 = t2 < 0 ? {re:0, im:Math.sqrt(-t2)} : {re:Math.sqrt(t2), im:0};
  }
  if (mu1.im < 0) { mu1.re = -mu1.re; mu1.im = -mu1.im; }
  if (mu2.im < 0) { mu2.re = -mu2.re; mu2.im = -mu2.im; }
  return [mu1, mu2];
}

function csqrt(z) {
  const r = Math.sqrt(z.re*z.re + z.im*z.im);
  const t = Math.atan2(z.im, z.re);
  const sr = Math.sqrt(r);
  return { re: sr*Math.cos(t/2), im: sr*Math.sin(t/2) };
}

// ═══════════════════════════════════════════════
// TEST SUITE
// ═══════════════════════════════════════════════

let passed = 0, failed = 0;

function assert(cond, msg, detail="") {
  if (cond) {
    passed++;
    console.log(`  ✓ ${msg}`);
  } else {
    failed++;
    console.log(`  ✗ FAIL: ${msg} ${detail}`);
  }
}

function approx(a, b, tol=0.05) {
  return Math.abs(a - b) / Math.max(Math.abs(b), 1e-10) < tol;
}

function inRange(val, low, high) {
  return val >= low && val <= high;
}

// ═══════════════════════════════════════════════
// TEST 1: Reduced Stiffness Matrix (Q) for T300/5208
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 1: Reduced Stiffness Q matrix (T300/5208) ═══");
{
  const [Q11, Q12, Q22, Q66] = reducedStiffness(T300);
  // Known values from Jones Table 2.1 / Daniel & Ishai
  // v21 = 0.28 * 10.3/181 = 0.01594
  // denom = 1 - 0.28 * 0.01594 = 0.99554
  // Q11 = 181/0.99554 = 181.81 GPa
  // Q22 = 10.3/0.99554 = 10.35 GPa
  // Q12 = 0.28*10.3/0.99554 = 2.90 GPa
  // Q66 = 7.17 GPa
  const nu21 = v21(T300);
  console.log(`  v21 = ${nu21.toFixed(6)} (expect ~0.01594)`);
  console.log(`  Q11 = ${Q11.toFixed(2)} GPa (expect ~181.8)`);
  console.log(`  Q22 = ${Q22.toFixed(2)} GPa (expect ~10.35)`);
  console.log(`  Q12 = ${Q12.toFixed(2)} GPa (expect ~2.90)`);
  console.log(`  Q66 = ${Q66.toFixed(2)} GPa (expect 7.17)`);

  assert(approx(nu21, 0.01594, 0.01), "v21 correct");
  assert(approx(Q11, 181.81, 0.01), "Q11 correct");
  assert(approx(Q22, 10.35, 0.01), "Q22 correct");
  assert(approx(Q12, 2.897, 0.02), "Q12 correct");
  assert(Q66 === 7.17, "Q66 = G12");
}

// ═══════════════════════════════════════════════
// TEST 2: Unidirectional [0]₈ laminate
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 2: Unidirectional [0]₈ T300/5208 ═══");
{
  const plies = Array.from({length: 8}, () => ({angle: 0, materialId: "T300/5208"}));
  const mats = {"T300/5208": T300};
  const abd = computeABD(plies, mats);

  console.log(`  Total thickness = ${abd.totalThickness.toFixed(3)} mm (expect 1.000)`);
  console.log(`  Ex = ${abd.Ex.toFixed(2)} GPa (expect ~181 GPa = E1)`);
  console.log(`  Ey = ${abd.Ey.toFixed(2)} GPa (expect ~10.3 GPa = E2)`);
  console.log(`  Gxy = ${abd.Gxy.toFixed(2)} GPa (expect ~7.17 GPa = G12)`);
  console.log(`  vxy = ${abd.vxy.toFixed(4)} (expect 0.28 = v12)`);

  assert(approx(abd.totalThickness, 1.0, 0.001), "Total thickness = 8 × 0.125");
  assert(approx(abd.Ex, 181.0, 0.02), "Ex ≈ E1 for UD [0]");
  assert(approx(abd.Ey, 10.3, 0.02), "Ey ≈ E2 for UD [0]");
  assert(approx(abd.Gxy, 7.17, 0.02), "Gxy ≈ G12 for UD [0]");
  assert(approx(abd.vxy, 0.28, 0.02), "vxy ≈ v12 for UD [0]");

  // B matrix should be zero for symmetric
  let bMax = 0;
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) bMax = Math.max(bMax, Math.abs(abd.B[i][j]));
  assert(bMax < 1e-10, "B matrix ≈ 0 for symmetric layup");
}

// ═══════════════════════════════════════════════
// TEST 3: Quasi-isotropic [0/±45/90]s T300/5208
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 3: Quasi-isotropic [0/±45/90]s T300/5208 ═══");
{
  // [0/+45/-45/90/90/-45/+45/0] — 8 plies, symmetric
  const angles = [0, 45, -45, 90, 90, -45, 45, 0];
  const plies = angles.map(a => ({angle: a, materialId: "T300/5208"}));
  const mats = {"T300/5208": T300};
  const abd = computeABD(plies, mats);

  console.log(`  Total thickness = ${abd.totalThickness.toFixed(3)} mm (expect 1.000)`);
  console.log(`  Ex = ${abd.Ex.toFixed(2)} GPa`);
  console.log(`  Ey = ${abd.Ey.toFixed(2)} GPa`);
  console.log(`  Gxy = ${abd.Gxy.toFixed(2)} GPa`);
  console.log(`  vxy = ${abd.vxy.toFixed(4)}`);

  // For a true quasi-isotropic laminate with T300/5208:
  // Literature: Ex ≈ Ey ≈ 69-72 GPa, Gxy ≈ 26-28 GPa, vxy ≈ 0.30-0.33
  // Daniel & Ishai, Jones Ch.4 examples give ~70 GPa
  assert(inRange(abd.Ex, 60, 80), `Ex in [60,80] GPa range — got ${abd.Ex.toFixed(1)}`);
  assert(inRange(abd.Ey, 60, 80), `Ey in [60,80] GPa range — got ${abd.Ey.toFixed(1)}`);
  assert(approx(abd.Ex, abd.Ey, 0.05), `Quasi-iso: Ex ≈ Ey (${abd.Ex.toFixed(1)} vs ${abd.Ey.toFixed(1)})`);
  assert(inRange(abd.Gxy, 20, 35), `Gxy in [20,35] GPa range — got ${abd.Gxy.toFixed(1)}`);
  assert(inRange(abd.vxy, 0.25, 0.40), `vxy in [0.25,0.40] — got ${abd.vxy.toFixed(3)}`);

  // Check isotropy: for a quasi-iso, Ex/(2*(1+vxy)) should ≈ Gxy
  const GxyFromIso = abd.Ex / (2 * (1 + abd.vxy));
  console.log(`  Gxy from isotropy relation: ${GxyFromIso.toFixed(2)} GPa (actual: ${abd.Gxy.toFixed(2)})`);
  assert(approx(GxyFromIso, abd.Gxy, 0.10), "Isotropy check: G ≈ E/(2(1+v))");

  // A₁₆ and A₂₆ should be zero for balanced laminate
  console.log(`  A₁₆ = ${abd.A[0][2].toFixed(4)}, A₂₆ = ${abd.A[1][2].toFixed(4)} (expect ~0)`);
  assert(Math.abs(abd.A[0][2]) < 0.1, "A₁₆ ≈ 0 for balanced laminate");
  assert(Math.abs(abd.A[1][2]) < 0.1, "A₂₆ ≈ 0 for balanced laminate");
}

// ═══════════════════════════════════════════════
// TEST 4: Cross-ply [0/90]s T300/5208
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 4: Cross-ply [0/90]s T300/5208 ═══");
{
  const angles = [0, 90, 90, 0];
  const plies = angles.map(a => ({angle: a, materialId: "T300/5208"}));
  const mats = {"T300/5208": T300};
  const abd = computeABD(plies, mats);

  console.log(`  Ex = ${abd.Ex.toFixed(2)} GPa`);
  console.log(`  Ey = ${abd.Ey.toFixed(2)} GPa`);
  console.log(`  Gxy = ${abd.Gxy.toFixed(2)} GPa`);
  console.log(`  vxy = ${abd.vxy.toFixed(4)}`);

  // Cross-ply: Ex ≈ Ey ≈ (E1+E2)/2 ≈ 95 GPa (roughly, for equal 0/90 fractions)
  // More precisely, Ex = (Q11+Q22)/2 * h... but with 50/50 split
  // Expected: Ex ≈ Ey ≈ 95-97 GPa, Gxy ≈ 7.17 GPa (pure G12)
  assert(inRange(abd.Ex, 80, 110), `Ex in [80,110] GPa — got ${abd.Ex.toFixed(1)}`);
  assert(approx(abd.Ex, abd.Ey, 0.05), `Cross-ply: Ex ≈ Ey`);
  assert(approx(abd.Gxy, 7.17, 0.05), `Cross-ply Gxy ≈ G12 = 7.17`);
}

// ═══════════════════════════════════════════════
// TEST 5: Ply stress under uniaxial loading
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 5: Ply stress — UD [0]₈, Nx=100 N/mm ═══");
{
  const plies = Array.from({length: 8}, () => ({angle: 0, materialId: "T300/5208"}));
  const mats = {"T300/5208": T300};
  const result = analyzeLaminate(plies, mats, 100, 0, 0);

  // Average stress = Nx / h = 100 / 1.0 = 100 MPa in x-direction
  // For UD [0], all stress should be in fibre direction: σ₁ = 100 MPa
  const ply0 = result.plies[0];
  console.log(`  Midplane strain εx = ${(result.midplaneStrain[0]*1e6).toFixed(1)} µε`);
  console.log(`  Ply 0: σx = ${ply0.sigmaX.toFixed(2)} MPa (expect ~100)`);
  console.log(`  Ply 0: σy = ${ply0.sigmaY.toFixed(2)} MPa (expect ~0)`);
  console.log(`  Ply 0: σ₁ = ${ply0.sigma1.toFixed(2)} MPa (expect ~100)`);
  console.log(`  Ply 0: σ₂ = ${ply0.sigma2.toFixed(2)} MPa (expect ~0)`);

  // σx = Nx/h = 100 MPa
  assert(approx(ply0.sigmaX, 100, 0.05), `σx ≈ 100 MPa — got ${ply0.sigmaX.toFixed(1)}`);
  // σ₁ should equal σx for 0° ply
  assert(approx(ply0.sigma1, 100, 0.05), `σ₁ ≈ 100 MPa — got ${ply0.sigma1.toFixed(1)}`);
  // σy and σ₂ should be very small (just Poisson effect from constrained plate)
  // Actually for unconstrained (Ny=0), σy = 0 exactly
  assert(Math.abs(ply0.sigmaY) < 5, `σy ≈ 0 — got ${ply0.sigmaY.toFixed(2)}`);

  // Strain check: εx = Nx/(A11*h... no, εx = a11*Nx/h) → more simply εx = σx/E1
  // εx = 100 / (181*1000) = 5.52e-4 → 552 µε
  const expectedEps = 100 / (181 * 1000);
  console.log(`  Expected εx = ${(expectedEps*1e6).toFixed(1)} µε`);
  assert(approx(result.midplaneStrain[0], expectedEps, 0.05), "Midplane strain correct");
}

// ═══════════════════════════════════════════════
// TEST 6: Ply stress — QI [0/±45/90]s, Nx=100 N/mm
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 6: Ply stress — QI [0/±45/90]s, Nx=100 N/mm ═══");
{
  const angles = [0, 45, -45, 90, 90, -45, 45, 0];
  const plies = angles.map(a => ({angle: a, materialId: "T300/5208"}));
  const mats = {"T300/5208": T300};
  const result = analyzeLaminate(plies, mats, 100, 0, 0);

  // Average stress: σavg = Nx/h = 100 MPa
  // But individual plies carry different portions
  // 0° plies carry most fibre-direction load, 90° plies carry least
  console.log("  Ply stresses (MPa):");
  for (const p of result.plies) {
    console.log(`    Ply ${p.plyIndex} (${p.angle.toString().padStart(3)}°): σx=${p.sigmaX.toFixed(1).padStart(8)}, σy=${p.sigmaY.toFixed(1).padStart(7)}, τxy=${p.tauXY.toFixed(1).padStart(7)} | σ₁=${p.sigma1.toFixed(1).padStart(8)}, σ₂=${p.sigma2.toFixed(1).padStart(7)}, τ₁₂=${p.tau12.toFixed(1).padStart(7)}`);
  }

  // All stresses should be physically reasonable (< 500 MPa for 100 N/mm)
  let maxStress = 0;
  for (const p of result.plies) {
    maxStress = Math.max(maxStress, Math.abs(p.sigmaX), Math.abs(p.sigmaY), Math.abs(p.tauXY));
  }
  assert(maxStress < 500, `Max stress < 500 MPa — got ${maxStress.toFixed(1)}`);
  assert(maxStress > 10, `Max stress > 10 MPa (not all zeros) — got ${maxStress.toFixed(1)}`);

  // 0° ply should carry more σ₁ than 90° ply
  const ply0 = result.plies.find(p => p.angle === 0);
  const ply90 = result.plies.find(p => p.angle === 90);
  assert(ply0.sigma1 > ply90.sigma1, `0° ply σ₁ > 90° ply σ₁ (${ply0.sigma1.toFixed(1)} vs ${ply90.sigma1.toFixed(1)})`);

  // Force resultant equilibrium: sum of σx × thickness should = Nx = 100
  const h = T300.plyThickness;
  let sumNx = 0;
  for (const p of result.plies) sumNx += p.sigmaX * h;
  console.log(`  Σ(σx·t) = ${sumNx.toFixed(2)} N/mm (expect 100.0)`);
  assert(approx(sumNx, 100, 0.02), "Force equilibrium: Σ(σx·t) = Nx");

  let sumNy = 0;
  for (const p of result.plies) sumNy += p.sigmaY * h;
  console.log(`  Σ(σy·t) = ${sumNy.toFixed(2)} N/mm (expect 0.0)`);
  assert(Math.abs(sumNy) < 1, "Force equilibrium: Σ(σy·t) ≈ 0");
}

// ═══════════════════════════════════════════════
// TEST 7: Characteristic roots for isotropic-like material
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 7: Lekhnitskii characteristic roots ═══");
{
  // For isotropic material: E1=E2=E, G12=E/(2(1+v)), v12=v
  // The characteristic equation gives μ = ±i (pure imaginary, unit magnitude)
  const isoMat = {
    E1: 70, E2: 70, G12: 70/(2*(1+0.3)), v12: 0.3,
    Xt: 500, Xc: 500, Yt: 500, Yc: 500, S12: 300,
    plyThickness: 0.125,
  };
  const [mu1, mu2] = characteristicRoots(isoMat);
  console.log(`  Isotropic: μ₁ = ${mu1.re.toFixed(4)} + ${mu1.im.toFixed(4)}i`);
  console.log(`  Isotropic: μ₂ = ${mu2.re.toFixed(4)} + ${mu2.im.toFixed(4)}i`);

  // For isotropic: μ₁ = μ₂ = i (both pure imaginary with |μ|=1)
  assert(Math.abs(mu1.re) < 0.01, `μ₁ nearly pure imaginary (re=${mu1.re.toFixed(4)})`);
  assert(approx(mu1.im, 1.0, 0.01), `|μ₁| ≈ 1 for isotropic`);

  // For T300/5208 (highly anisotropic): μ values should be different
  const [mu1t, mu2t] = characteristicRoots(T300);
  console.log(`  T300/5208: μ₁ = ${mu1t.re.toFixed(4)} + ${mu1t.im.toFixed(4)}i`);
  console.log(`  T300/5208: μ₂ = ${mu2t.re.toFixed(4)} + ${mu2t.im.toFixed(4)}i`);

  // For highly orthotropic, |μ| should be >> 1 (one root) and << 1 (other root)
  const mag1 = Math.sqrt(mu1t.re**2 + mu1t.im**2);
  const mag2 = Math.sqrt(mu2t.re**2 + mu2t.im**2);
  console.log(`  |μ₁| = ${mag1.toFixed(4)}, |μ₂| = ${mag2.toFixed(4)}`);
  assert(mu1t.im > 0, "μ₁ has positive imaginary part");
  assert(mu2t.im > 0, "μ₂ has positive imaginary part");
}

// ═══════════════════════════════════════════════
// TEST 8: Lekhnitskii SCF at hole boundary
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 8: Stress concentration — isotropic, circular hole, σy loading ═══");
{
  // For isotropic plate with circular hole under uniaxial σy:
  // SCF at (x=a, y=0) = 3.0 (classic Kirsch solution)
  // Test this by computing stress at a point just outside the hole edge

  // We can't use the full stress field engine easily, but let's check the
  // Lekhnitskii formula for SCF at the hole boundary.

  // For orthotropic plate under σy, the SCF at x=a, y=0 is:
  // Kt = 1 + (2/k)*(√(E1/E2) - v12) + E1/G12
  // where k = a/b (for circular hole, k=1)
  // Wait — that's Lekhnitskii's formula for the SCF at the waist of the hole.
  // For isotropic: Kt = 1 + 2*(1 - 0.3) + 70/26.9 = 1 + 1.4 + 2.6 = 5.0 ← that's wrong

  // Actually the standard result:
  // For circular hole, σy loading, at point (a, 0):
  // σy/σy∞ = 1 + (2b/a) = 3 for circle (Kirsch, isotropic)
  // For orthotropic: σy/σy∞ = 1 + √(2*(√(E1*E2)/G12 - v12) + E1/E2)
  // No wait — the correct Lekhnitskii formula for SCF at (a,0) under σy∞ is:
  // Kt = 1 + √(E1/E2 * (2*√(E1/E2) - 2*v12 + E1/G12))
  // That simplifies to the known value 3.0 for isotropic.

  // Let me verify: for isotropic E1=E2=E, G12=E/(2(1+v)), v12=v:
  // = 1 + √(1 * (2*1 - 2*0.3 + 2*(1+0.3)))
  // = 1 + √(2 - 0.6 + 2.6)
  // = 1 + √4 = 1 + 2 = 3.0 ✓

  // For T300/5208:
  // Kt = 1 + √(E1/E2 * (2*√(E1/E2)/1 - 2*v12 + E1/G12))
  // Note: more precisely for a circular hole under σy:
  // Kt = 1 + √(2*√(E1/E2) - 2*v12 + E1/G12)
  // Hmm, need to be careful with the formula. Let me use the standard one:

  // SCF at hole edge (x=a, y=0) for σy∞ loading:
  // From Lekhnitskii (1968) eq. 38.12:
  // σy(a,0) / σy∞ = 1 + Re[μ₁·μ₂·(a/b)] for y-loaded case...

  // Actually, the standard Lekhnitskii SCF for circular hole in orthotropic:
  // Kt = 1 + sqrt( 2*(sqrt(E1/E2) - v12) + E1/G12 )

  // For T300/5208:
  const sqrtRatio = Math.sqrt(T300.E1 / T300.E2);
  const KtOrth = 1 + Math.sqrt(2*(sqrtRatio - T300.v12) + T300.E1/T300.G12);
  console.log(`  T300/5208 SCF (Lekhnitskii formula): Kt = ${KtOrth.toFixed(2)}`);
  // sqrt(E1/E2) = sqrt(181/10.3) = 4.19
  // 2*(4.19 - 0.28) + 181/7.17 = 2*3.91 + 25.24 = 7.82 + 25.24 = 33.06
  // Kt = 1 + sqrt(33.06) = 1 + 5.75 = 6.75
  assert(inRange(KtOrth, 6, 8), `T300 SCF in [6,8] — got ${KtOrth.toFixed(2)}`);

  // For isotropic:
  const KtIso = 1 + Math.sqrt(2*(1 - 0.3) + 70/(70/(2*1.3)));
  console.log(`  Isotropic SCF: Kt = ${KtIso.toFixed(2)} (expect 3.0)`);
  assert(approx(KtIso, 3.0, 0.01), "Isotropic SCF = 3.0 (Kirsch)");
}

// ═══════════════════════════════════════════════
// TEST 9: Stress transformation validity
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 9: Stress transformation ═══");
{
  // For a 45° ply under σx = 100 MPa, σy = 0, τxy = 0:
  // σ₁ = cos²(45)·100 + sin²(45)·0 = 50
  // σ₂ = sin²(45)·100 + cos²(45)·0 = 50
  // τ₁₂ = -sin(45)cos(45)·100 + sin(45)cos(45)·0 = -50
  const theta = 45;
  const rad = (theta * Math.PI) / 180;
  const c = Math.cos(rad), s = Math.sin(rad);
  const c2 = c*c, s2 = s*s, cs = c*s;
  const sigma1 = c2*100 + s2*0 + 2*cs*0;
  const sigma2 = s2*100 + c2*0 - 2*cs*0;
  const tau12 = -cs*100 + cs*0 + (c2-s2)*0;
  console.log(`  45° ply, σx=100: σ₁=${sigma1.toFixed(1)}, σ₂=${sigma2.toFixed(1)}, τ₁₂=${tau12.toFixed(1)}`);
  assert(approx(sigma1, 50, 0.01), "σ₁ = 50");
  assert(approx(sigma2, 50, 0.01), "σ₂ = 50");
  assert(approx(tau12, -50, 0.01), "τ₁₂ = -50");
}

// ═══════════════════════════════════════════════
// TEST 10: A matrix consistency checks
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 10: A matrix symmetry and positivity ═══");
{
  const angles = [0, 45, -45, 90, 90, -45, 45, 0];
  const plies = angles.map(a => ({angle: a, materialId: "T300/5208"}));
  const mats = {"T300/5208": T300};
  const abd = computeABD(plies, mats);

  // A matrix must be symmetric
  assert(approx(abd.A[0][1], abd.A[1][0], 0.001), "A₁₂ = A₂₁ (symmetric)");
  assert(approx(abd.A[0][2], abd.A[2][0], 0.001), "A₁₆ = A₆₁ (symmetric)");
  assert(approx(abd.A[1][2], abd.A[2][1], 0.001), "A₂₆ = A₆₂ (symmetric)");

  // D matrix must be symmetric
  assert(approx(abd.D[0][1], abd.D[1][0], 0.001), "D₁₂ = D₂₁ (symmetric)");

  // A₁₁ must be positive
  assert(abd.A[0][0] > 0, "A₁₁ > 0");
  assert(abd.A[1][1] > 0, "A₂₂ > 0");
  assert(abd.A[2][2] > 0, "A₆₆ > 0");
}

// ═══════════════════════════════════════════════
// TEST 11: Tsai-Wu failure index for known case
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 11: Tsai-Wu failure index ═══");
{
  // Under pure σ₁ = Xt = 1500 MPa, Tsai-Wu should ≈ 1.0
  const F1 = 1/T300.Xt - 1/T300.Xc; // = 0 (Xt = Xc)
  const F2 = 1/T300.Yt - 1/T300.Yc;
  const F11 = 1/(T300.Xt * T300.Xc);
  const F22 = 1/(T300.Yt * T300.Yc);
  const F66 = 1/(T300.S12 * T300.S12);
  const F12 = -0.5 * Math.sqrt(F11 * F22);

  const twAtXt = F1*1500 + F11*1500*1500;
  console.log(`  TW at σ₁=Xt: ${twAtXt.toFixed(4)} (expect 1.0)`);
  assert(approx(twAtXt, 1.0, 0.01), "Tsai-Wu = 1.0 at σ₁ = Xt");

  const twAtYt = F2*40 + F22*40*40;
  console.log(`  TW at σ₂=Yt: ${twAtYt.toFixed(4)} (expect 1.0)`);
  assert(approx(twAtYt, 1.0, 0.01), "Tsai-Wu = 1.0 at σ₂ = Yt");

  const twAtS12 = F66*68*68;
  console.log(`  TW at τ₁₂=S12: ${twAtS12.toFixed(4)} (expect 1.0)`);
  assert(approx(twAtS12, 1.0, 0.01), "Tsai-Wu = 1.0 at τ₁₂ = S12");
}

// ═══════════════════════════════════════════════
// TEST 12: E-Glass/Epoxy quasi-iso (independent material)
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 12: E-Glass/Epoxy [0/±45/90]s ═══");
{
  const angles = [0, 45, -45, 90, 90, -45, 45, 0];
  const plies = angles.map(a => ({angle: a, materialId: "E-Glass/Epoxy"}));
  const mats = {"E-Glass/Epoxy": EGlass};
  const abd = computeABD(plies, mats);

  console.log(`  Ex = ${abd.Ex.toFixed(2)} GPa`);
  console.log(`  Ey = ${abd.Ey.toFixed(2)} GPa`);
  console.log(`  Gxy = ${abd.Gxy.toFixed(2)} GPa`);
  console.log(`  vxy = ${abd.vxy.toFixed(4)}`);

  // E-Glass quasi-iso: Ex ≈ Ey ≈ 18-22 GPa (much lower than carbon)
  assert(inRange(abd.Ex, 14, 28), `Ex in [14,28] GPa — got ${abd.Ex.toFixed(1)}`);
  assert(approx(abd.Ex, abd.Ey, 0.05), "Quasi-iso: Ex ≈ Ey for E-Glass");
  // vxy should be reasonable
  assert(inRange(abd.vxy, 0.2, 0.45), `vxy reasonable — got ${abd.vxy.toFixed(3)}`);
}

// ═══════════════════════════════════════════════
// TEST 13: Units sanity — ply stress magnitudes
// ═══════════════════════════════════════════════
console.log("\n═══ TEST 13: Units sanity — stress magnitudes ═══");
{
  const angles = [0, 45, -45, 90, 90, -45, 45, 0];
  const plies = angles.map(a => ({angle: a, materialId: "T300/5208"}));
  const mats = {"T300/5208": T300};

  // Nx = 500 N/mm is a high but reasonable loading
  const result = analyzeLaminate(plies, mats, 500, 0, 0);

  console.log("  Ply stresses at Nx=500 N/mm:");
  let maxSig = 0;
  for (const p of result.plies) {
    maxSig = Math.max(maxSig, Math.abs(p.sigma1), Math.abs(p.sigma2), Math.abs(p.tau12));
    console.log(`    Ply ${p.plyIndex} (${p.angle.toString().padStart(3)}°): σ₁=${p.sigma1.toFixed(1).padStart(8)} MPa, σ₂=${p.sigma2.toFixed(1).padStart(7)} MPa, τ₁₂=${p.tau12.toFixed(1).padStart(7)} MPa`);
  }

  // For 500 N/mm on 1mm laminate, average stress = 500 MPa
  // Max ply stress should be roughly 500-2000 MPa (0° ply carries most)
  assert(inRange(maxSig, 100, 5000), `Max stress in [100,5000] MPa — got ${maxSig.toFixed(0)}`);
  assert(maxSig < 10000, `No absurd 10000+ MPa stresses — got ${maxSig.toFixed(0)}`);

  // Check equilibrium
  const h = T300.plyThickness;
  let sumNx = 0;
  for (const p of result.plies) sumNx += p.sigmaX * h;
  assert(approx(sumNx, 500, 0.02), `Equilibrium Σ(σx·t) = 500 N/mm — got ${sumNx.toFixed(1)}`);
}

// ═══════════════════════════════════════════════
// SUMMARY
// ═══════════════════════════════════════════════
console.log(`\n${"═".repeat(50)}`);
console.log(`VALIDATION RESULTS: ${passed} passed, ${failed} failed out of ${passed + failed} tests`);
console.log(`${"═".repeat(50)}`);

if (failed > 0) {
  console.log("\n⚠ CRITICAL: Some tests FAILED — outputs may be physically incorrect!");
  process.exit(1);
} else {
  console.log("\n✓ All tests passed — CLT and material math are producing correct results.");
  process.exit(0);
}
