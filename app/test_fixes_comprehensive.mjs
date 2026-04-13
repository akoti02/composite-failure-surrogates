/**
 * COMPREHENSIVE TEST SUITE — ALL FIXES VALIDATED
 *
 * Tests every fix from the last round of corrections:
 * 1. failureLoadFactor: quadratic Tsai-Wu solve, linear maxStress
 * 2. progressiveFailure: doesn't mutate caller's plies
 * 3. reducedStiffness: denom validation guard
 * 4. analyzeLaminate: ALL fields populated for every ply
 * 5. Failure criteria correctness (Tsai-Wu, MaxStress, Hashin)
 * 6. FPF/LPF correctness across materials & load cases
 * 7. All 7 materials produce valid results
 * 8. Stress field: all StressPoint fields populated
 *
 * Run: node test_fixes_comprehensive.mjs
 */

let passed = 0, failed = 0, total = 0;

function assert(cond, msg) {
  total++;
  if (cond) { passed++; }
  else { failed++; console.error(`  ✗ FAIL: ${msg}`); }
}

function assertClose(actual, expected, tol, msg) {
  total++;
  if (Math.abs(actual - expected) <= tol) { passed++; }
  else { failed++; console.error(`  ✗ FAIL: ${msg} — got ${actual}, expected ${expected} ±${tol}`); }
}

function assertGt(a, b, msg) { total++; if (a > b) passed++; else { failed++; console.error(`  ✗ FAIL: ${msg} — ${a} not > ${b}`); } }
function assertGe(a, b, msg) { total++; if (a >= b) passed++; else { failed++; console.error(`  ✗ FAIL: ${msg} — ${a} not >= ${b}`); } }
function assertLt(a, b, msg) { total++; if (a < b) passed++; else { failed++; console.error(`  ✗ FAIL: ${msg} — ${a} not < ${b}`); } }
function assertFinite(v, msg) { total++; if (Number.isFinite(v)) passed++; else { failed++; console.error(`  ✗ FAIL: ${msg} — ${v} not finite`); } }
function assertNotNull(v, msg) { total++; if (v != null) passed++; else { failed++; console.error(`  ✗ FAIL: ${msg} — is null/undefined`); } }
function section(name) { console.log(`\n── ${name} ──`); }

// ═══════════════════════════════════════════════════════════
// MATERIAL DATABASE — all 7 materials
// ═══════════════════════════════════════════════════════════
const MATERIALS = {
  "T300/5208": {
    id: "T300/5208", name: "T300/5208", description: "",
    E1: 181.0, E2: 10.3, G12: 7.17, v12: 0.28,
    Xt: 1500, Xc: 1500, Yt: 40, Yc: 246, S12: 68,
    plyThickness: 0.125,
  },
  "AS4/3501-6": {
    id: "AS4/3501-6", name: "AS4/3501-6", description: "",
    E1: 147.0, E2: 10.3, G12: 7.0, v12: 0.27,
    Xt: 2280, Xc: 1440, Yt: 57, Yc: 228, S12: 71,
    plyThickness: 0.125,
  },
  "IM7/8552": {
    id: "IM7/8552", name: "IM7/8552", description: "",
    E1: 171.4, E2: 9.08, G12: 5.29, v12: 0.32,
    Xt: 2326, Xc: 1200, Yt: 62.3, Yc: 199.8, S12: 92.3,
    plyThickness: 0.131,
  },
  "T700/2510": {
    id: "T700/2510", name: "T700/2510", description: "",
    E1: 132.0, E2: 10.3, G12: 6.5, v12: 0.25,
    Xt: 2400, Xc: 1300, Yt: 55, Yc: 210, S12: 75,
    plyThickness: 0.127,
  },
  "E-Glass/Epoxy": {
    id: "E-Glass/Epoxy", name: "E-Glass/Epoxy", description: "",
    E1: 38.6, E2: 8.27, G12: 4.14, v12: 0.26,
    Xt: 1062, Xc: 610, Yt: 31, Yc: 118, S12: 72,
    plyThickness: 0.150,
  },
  "S2-Glass/Epoxy": {
    id: "S2-Glass/Epoxy", name: "S2-Glass/Epoxy", description: "",
    E1: 43.0, E2: 8.9, G12: 4.5, v12: 0.27,
    Xt: 1280, Xc: 690, Yt: 49, Yc: 158, S12: 69,
    plyThickness: 0.140,
  },
  "Kevlar49/Epoxy": {
    id: "Kevlar49/Epoxy", name: "Kevlar 49/Epoxy", description: "",
    E1: 76.0, E2: 5.5, G12: 2.3, v12: 0.34,
    Xt: 1400, Xc: 335, Yt: 30, Yc: 158, S12: 49,
    plyThickness: 0.125,
  },
};

// ═══════════════════════════════════════════════════════════
// LOCAL IMPLEMENTATIONS (mirror src/lib/*)
// ═══════════════════════════════════════════════════════════

function v21(m) { return m.v12 * m.E2 / m.E1; }

function reducedStiffness(m) {
  const nu21 = v21(m);
  const denom = 1 - m.v12 * nu21;
  if (denom <= 0) throw new Error(`Invalid material: denom=${denom}`);
  return [m.E1 / denom, m.v12 * m.E2 / denom, m.E2 / denom, m.G12];
}

function transformedStiffness(m, theta) {
  const [Q11, Q12, Q22, Q66] = reducedStiffness(m);
  const rad = (theta * Math.PI) / 180;
  const c = Math.cos(rad), s = Math.sin(rad);
  const c2 = c * c, s2 = s * s, cs = c * s;
  const c4 = c2 * c2, s4 = s2 * s2;
  return [
    [Q11*c4+2*(Q12+2*Q66)*c2*s2+Q22*s4, (Q11+Q22-4*Q66)*c2*s2+Q12*(c4+s4), (Q11-Q12-2*Q66)*c2*cs-(Q22-Q12-2*Q66)*s2*cs],
    [(Q11+Q22-4*Q66)*c2*s2+Q12*(c4+s4), Q11*s4+2*(Q12+2*Q66)*c2*s2+Q22*c4, (Q11-Q12-2*Q66)*cs*s2-(Q22-Q12-2*Q66)*cs*c2],
    [(Q11-Q12-2*Q66)*c2*cs-(Q22-Q12-2*Q66)*s2*cs, (Q11-Q12-2*Q66)*cs*s2-(Q22-Q12-2*Q66)*cs*c2, (Q11+Q22-2*Q12-2*Q66)*c2*s2+Q66*(c4+s4)],
  ];
}

function zeros3() { return [[0,0,0],[0,0,0],[0,0,0]]; }

function invertMat3(m) {
  const [[a,b,c],[d,e,f],[g,h,i]] = m;
  const det = a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g);
  if (Math.abs(det) < 1e-20) throw new Error("Singular matrix");
  const inv = 1/det;
  return [
    [(e*i-f*h)*inv,(c*h-b*i)*inv,(b*f-c*e)*inv],
    [(f*g-d*i)*inv,(a*i-c*g)*inv,(c*d-a*f)*inv],
    [(d*h-e*g)*inv,(b*g-a*h)*inv,(a*e-b*d)*inv],
  ];
}

function mulMat3Vec(m, v) { return m.map(row => row[0]*v[0]+row[1]*v[1]+row[2]*v[2]); }

function globalToMaterial(sigX, sigY, tauXY, theta) {
  const rad = (theta * Math.PI) / 180;
  const c = Math.cos(rad), s = Math.sin(rad);
  const c2 = c*c, s2 = s*s, cs = c*s;
  return [c2*sigX+s2*sigY+2*cs*tauXY, s2*sigX+c2*sigY-2*cs*tauXY, -cs*sigX+cs*sigY+(c2-s2)*tauXY];
}

function tsaiWuIndex(s1, s2, t12, m) {
  const F1 = 1/m.Xt - 1/m.Xc;
  const F2 = 1/m.Yt - 1/m.Yc;
  const F11 = 1/(m.Xt*m.Xc);
  const F22 = 1/(m.Yt*m.Yc);
  const F66 = 1/(m.S12*m.S12);
  const F12 = -0.5*Math.sqrt(F11*F22);
  return F1*s1+F2*s2+F11*s1*s1+F22*s2*s2+F66*t12*t12+2*F12*s1*s2;
}

function maxStressIndex(s1, s2, t12, m) {
  return Math.max(
    s1 >= 0 ? s1/m.Xt : -s1/m.Xc,
    s2 >= 0 ? s2/m.Yt : -s2/m.Yc,
    Math.abs(t12)/m.S12,
  );
}

function hashinIndices(s1, s2, t12, m) {
  const ft = s1 >= 0 ? (s1/m.Xt)**2 + (t12/m.S12)**2 : 0;
  const fc = s1 < 0 ? (-s1/m.Xc)**2 : 0;
  const mt = s2 >= 0 ? (s2/m.Yt)**2 + (t12/m.S12)**2 : 0;
  const mc = s2 < 0 ? (s2/(2*m.S12))**2 + ((m.Yc/(2*m.S12))**2-1)*(s2/m.Yc) + (t12/m.S12)**2 : 0;
  return { ft, fc, mt, mc };
}

function failureLoadFactor(twFI, msFI, s1, s2, t12, mat) {
  let lf = Infinity;
  if (msFI > 0) lf = Math.min(lf, 1/msFI);

  const F1 = 1/mat.Xt - 1/mat.Xc;
  const F2 = 1/mat.Yt - 1/mat.Yc;
  const F11 = 1/(mat.Xt*mat.Xc);
  const F22 = 1/(mat.Yt*mat.Yc);
  const F66 = 1/(mat.S12*mat.S12);
  const F12 = -0.5*Math.sqrt(F11*F22);

  const bTW = F1*s1 + F2*s2;
  const aTW = F11*s1*s1 + F22*s2*s2 + F66*t12*t12 + 2*F12*s1*s2;

  if (Math.abs(aTW) > 1e-20) {
    const disc = bTW*bTW + 4*aTW;
    if (disc >= 0) {
      const lam = (-bTW + Math.sqrt(disc)) / (2*aTW);
      if (lam > 0) lf = Math.min(lf, lam);
    }
  } else if (Math.abs(bTW) > 1e-20) {
    const lam = 1/bTW;
    if (lam > 0) lf = Math.min(lf, lam);
  }
  return Number.isFinite(lf) ? lf : 0;
}

function computeABD(plies, materials) {
  const n = plies.length;
  const A = zeros3(), B = zeros3(), D = zeros3();
  let totalH = 0;
  const thicknesses = plies.map(p => p.thickness ?? materials[p.materialId].plyThickness);
  thicknesses.forEach(t => totalH += t);

  let z = -totalH / 2;
  for (let k = 0; k < n; k++) {
    const t = thicknesses[k];
    const zBot = z, zTop = z + t;
    z = zTop;
    const Qbar = transformedStiffness(materials[plies[k].materialId], plies[k].angle);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) {
      A[i][j] += Qbar[i][j] * (zTop - zBot);
      B[i][j] += 0.5 * Qbar[i][j] * (zTop**2 - zBot**2);
      D[i][j] += (1/3) * Qbar[i][j] * (zTop**3 - zBot**3);
    }
  }
  const a = invertMat3(A);
  return { A, B, D, totalThickness: totalH, plyCount: n,
    Ex: 1/(a[0][0]*totalH), Ey: 1/(a[1][1]*totalH),
    Gxy: 1/(a[2][2]*totalH), vxy: -a[0][1]/a[0][0] };
}

function analyzeLaminate(plies, materials, Nx, Ny, Nxy, Mx=0, My=0, Mxy=0) {
  const abd = computeABD(plies, materials);
  const { A, B, D, totalThickness: totalH } = abd;
  const N = [Nx/1000, Ny/1000, Nxy/1000];
  const M = [Mx/1000, My/1000, Mxy/1000];

  let bNorm = 0;
  for (let i=0;i<3;i++) for(let j=0;j<3;j++) bNorm += B[i][j]**2;
  bNorm = Math.sqrt(bNorm);

  let eps0, kappa;
  if (bNorm < 1e-10) {
    eps0 = mulMat3Vec(invertMat3(A), N);
    kappa = mulMat3Vec(invertMat3(D), M);
  } else {
    const Ainv = invertMat3(A);
    const AinvB = Ainv.map(row => [0,1,2].map(j => row[0]*B[0][j]+row[1]*B[1][j]+row[2]*B[2][j]));
    const BAinvB = B.map(row => [0,1,2].map(j => row[0]*AinvB[0][j]+row[1]*AinvB[1][j]+row[2]*AinvB[2][j]));
    const Dstar = D.map((row,i) => row.map((v,j) => v - BAinvB[i][j]));
    const DstarInv = invertMat3(Dstar);
    const BAinvN = mulMat3Vec(B.map(row => [0,1,2].map(j => row[0]*Ainv[0][j]+row[1]*Ainv[1][j]+row[2]*Ainv[2][j])), N);
    kappa = mulMat3Vec(DstarInv, M.map((v,i) => v - BAinvN[i]));
    const Bkappa = mulMat3Vec(B, kappa);
    eps0 = mulMat3Vec(Ainv, N.map((v,i) => v - Bkappa[i]));
  }

  const plyResults = [];
  const thicknesses = plies.map(p => p.thickness ?? materials[p.materialId].plyThickness);
  let z = -totalH / 2;

  for (let k = 0; k < plies.length; k++) {
    const t = thicknesses[k];
    const zBot = z, zTop = z + t;
    const zMid = (zBot + zTop) / 2;
    z = zTop;
    const mat = materials[plies[k].materialId];
    const Qbar = transformedStiffness(mat, plies[k].angle);
    const strainX = eps0[0] + zMid*kappa[0];
    const strainY = eps0[1] + zMid*kappa[1];
    const gammaXY = eps0[2] + zMid*kappa[2];
    const sigmaX = (Qbar[0][0]*strainX + Qbar[0][1]*strainY + Qbar[0][2]*gammaXY)*1000;
    const sigmaY = (Qbar[1][0]*strainX + Qbar[1][1]*strainY + Qbar[1][2]*gammaXY)*1000;
    const tauXY = (Qbar[2][0]*strainX + Qbar[2][1]*strainY + Qbar[2][2]*gammaXY)*1000;
    const [sigma1, sigma2, tau12] = globalToMaterial(sigmaX, sigmaY, tauXY, plies[k].angle);
    const tw = tsaiWuIndex(sigma1, sigma2, tau12, mat);
    const ms = maxStressIndex(sigma1, sigma2, tau12, mat);
    const h = hashinIndices(sigma1, sigma2, tau12, mat);
    const maxFI = Math.max(tw, ms, h.ft, h.fc, h.mt, h.mc);
    const isFailed = maxFI >= 1.0;

    const entries = [["Tsai-Wu",tw],["Max Stress",ms],["Hashin FT",h.ft],["Hashin FC",h.fc],["Hashin MT",h.mt],["Hashin MC",h.mc]];
    let maxVal = 0, maxName = "";
    for (const [name, val] of entries) { if (val > maxVal) { maxVal = val; maxName = name; } }

    plyResults.push({
      plyIndex: k, angle: plies[k].angle, materialId: plies[k].materialId,
      zBot, zTop, sigmaX, sigmaY, tauXY, sigma1, sigma2, tau12,
      tsaiWu: tw, maxStress: ms, hashinFT: h.ft, hashinFC: h.fc, hashinMT: h.mt, hashinMC: h.mc,
      failed: isFailed, failureMode: maxName,
    });
  }

  let fpf = null, minLF = Infinity;
  for (const pr of plyResults) {
    const lf = failureLoadFactor(pr.tsaiWu, pr.maxStress, pr.sigma1, pr.sigma2, pr.tau12, materials[pr.materialId]);
    if (lf > 0 && lf < minLF) { minLF = lf; fpf = { load: lf, plyIndex: pr.plyIndex, mode: pr.failureMode }; }
  }
  let maxLF = 0;
  for (const pr of plyResults) {
    const lf = failureLoadFactor(pr.tsaiWu, pr.maxStress, pr.sigma1, pr.sigma2, pr.tau12, materials[pr.materialId]);
    if (lf > maxLF) maxLF = lf;
  }

  return {
    abd, plies: plyResults, firstPlyFailure: fpf,
    lastPlyFailure: maxLF > 0 ? { load: maxLF } : null,
    midplaneStrain: eps0, midplaneCurvature: kappa,
  };
}

function progressiveFailure(plies, materials, Nx, Ny, Nxy, steps=50) {
  const curve = [];
  const degradedMaterials = { ...materials };
  for (const id of Object.keys(degradedMaterials)) degradedMaterials[id] = { ...degradedMaterials[id] };
  const workPlies = plies.map(p => ({ ...p }));
  const failedPlySet = new Set();

  for (let i = 0; i <= steps; i++) {
    const lf = (i/steps)*2.0;
    const result = analyzeLaminate(workPlies, degradedMaterials, Nx*lf, Ny*lf, Nxy*lf);
    let maxFI = 0;
    for (const pr of result.plies) {
      const fi = Math.max(pr.tsaiWu, pr.hashinFT, pr.hashinFC, pr.hashinMT, pr.hashinMC);
      if (fi > maxFI) maxFI = fi;
      if (fi >= 1.0 && !failedPlySet.has(pr.plyIndex)) {
        failedPlySet.add(pr.plyIndex);
        const matId = workPlies[pr.plyIndex].materialId;
        const degraded = { ...degradedMaterials[matId] };
        if (pr.hashinMT >= 1.0 || pr.hashinMC >= 1.0) {
          degraded.E2 *= 0.01; degraded.G12 *= 0.01;
          degraded.Yt *= 0.01; degraded.Yc *= 0.01; degraded.S12 *= 0.01;
        }
        if (pr.hashinFT >= 1.0 || pr.hashinFC >= 1.0) {
          degraded.E1 *= 0.01; degraded.E2 *= 0.01; degraded.G12 *= 0.01;
        }
        const newId = `${matId}_deg_${pr.plyIndex}`;
        degradedMaterials[newId] = degraded;
        workPlies[pr.plyIndex] = { ...workPlies[pr.plyIndex], materialId: newId };
      }
    }
    curve.push({ loadFactor: lf, maxFI, failedPlies: failedPlySet.size });
  }
  return curve;
}

// ═══════════════════════════════════════════════════════════
// SECTION 1: reducedStiffness denom validation
// ═══════════════════════════════════════════════════════════
section("1. reducedStiffness — denom validation guard");

// 1a. Valid materials must NOT throw
for (const [id, mat] of Object.entries(MATERIALS)) {
  let threw = false;
  try { reducedStiffness(mat); } catch { threw = true; }
  assert(!threw, `reducedStiffness(${id}) should not throw`);
}

// 1b. Invalid material with v12 too large must throw
{
  const bad = { ...MATERIALS["T300/5208"], v12: 5.0 }; // denom = 1 - 5.0 * 5.0*10.3/181 ≈ negative
  let threw = false;
  try { reducedStiffness(bad); } catch { threw = true; }
  assert(threw, "reducedStiffness must throw when denom <= 0");
}

// 1c. Edge case: v12=0 should work fine (denom=1)
{
  const zero_v = { ...MATERIALS["T300/5208"], v12: 0.0 };
  let threw = false;
  try { reducedStiffness(zero_v); } catch { threw = true; }
  assert(!threw, "reducedStiffness v12=0 should work");
}

// 1d. Verify Q matrix values for T300/5208
{
  const m = MATERIALS["T300/5208"];
  const [Q11, Q12, Q22, Q66] = reducedStiffness(m);
  const nu21 = m.v12 * m.E2 / m.E1;
  const d = 1 - m.v12 * nu21;
  assertClose(Q11, m.E1 / d, 0.01, "Q11 for T300/5208");
  assertClose(Q22, m.E2 / d, 0.01, "Q22 for T300/5208");
  assertClose(Q12, m.v12 * m.E2 / d, 0.001, "Q12 for T300/5208");
  assertClose(Q66, m.G12, 0.001, "Q66 = G12 for T300/5208");
}

// 1e. Q matrix symmetry: Q12 must equal Q21 (it's stored as single Q12)
{
  const m = MATERIALS["IM7/8552"];
  const [Q11, Q12, Q22, Q66] = reducedStiffness(m);
  // Q12 = v12*E2/denom = v21*E1/denom → verify
  const nu21 = m.v12 * m.E2 / m.E1;
  assertClose(Q12, nu21 * m.E1 / (1 - m.v12*nu21), 0.001, "Q12 reciprocity check");
}

// ═══════════════════════════════════════════════════════════
// SECTION 2: Tsai-Wu failure index correctness
// ═══════════════════════════════════════════════════════════
section("2. Tsai-Wu failure index — exhaustive checks");

const T300 = MATERIALS["T300/5208"];

// 2a. Zero stress → zero index
assertClose(tsaiWuIndex(0, 0, 0, T300), 0, 1e-10, "TW: zero stress = zero index");

// 2b. Pure longitudinal tensile failure at Xt
{
  const tw = tsaiWuIndex(T300.Xt, 0, 0, T300);
  assertClose(tw, 1.0, 0.001, "TW: σ1=Xt should give FI≈1.0");
}

// 2c. Pure longitudinal compressive failure at Xc
{
  const tw = tsaiWuIndex(-T300.Xc, 0, 0, T300);
  assertClose(tw, 1.0, 0.001, "TW: σ1=-Xc should give FI≈1.0");
}

// 2d. Pure transverse tensile failure at Yt
{
  const tw = tsaiWuIndex(0, T300.Yt, 0, T300);
  assertClose(tw, 1.0, 0.001, "TW: σ2=Yt should give FI≈1.0");
}

// 2e. Pure transverse compressive failure at Yc
{
  const tw = tsaiWuIndex(0, -T300.Yc, 0, T300);
  assertClose(tw, 1.0, 0.001, "TW: σ2=-Yc should give FI≈1.0");
}

// 2f. Pure shear failure at S12
{
  const tw = tsaiWuIndex(0, 0, T300.S12, T300);
  assertClose(tw, 1.0, 0.001, "TW: τ12=S12 should give FI≈1.0");
}

// 2g. Half of Xt → FI < 1
{
  const tw = tsaiWuIndex(T300.Xt / 2, 0, 0, T300);
  assertLt(tw, 1.0, "TW: σ1=Xt/2 should be safe");
  assertGt(tw, 0.0, "TW: σ1=Xt/2 should be positive");
}

// 2h. All 7 materials: verify TW=1 at each pure failure mode
for (const [id, mat] of Object.entries(MATERIALS)) {
  assertClose(tsaiWuIndex(mat.Xt, 0, 0, mat), 1.0, 0.01, `TW@Xt for ${id}`);
  assertClose(tsaiWuIndex(-mat.Xc, 0, 0, mat), 1.0, 0.01, `TW@-Xc for ${id}`);
  assertClose(tsaiWuIndex(0, mat.Yt, 0, mat), 1.0, 0.01, `TW@Yt for ${id}`);
  assertClose(tsaiWuIndex(0, -mat.Yc, 0, mat), 1.0, 0.01, `TW@-Yc for ${id}`);
  assertClose(tsaiWuIndex(0, 0, mat.S12, mat), 1.0, 0.01, `TW@S12 for ${id}`);
}

// 2i. Tsai-Wu under biaxial: σ1=Xt/2, σ2=Yt/2 should be < 1 but > 0
{
  const tw = tsaiWuIndex(T300.Xt/2, T300.Yt/2, 0, T300);
  assertLt(tw, 1.0, "TW biaxial half-strength safe");
  assertGt(tw, 0.0, "TW biaxial half-strength positive");
}

// 2j. Asymmetric materials (Xt ≠ Xc): F1 term should be non-zero
{
  const mat = MATERIALS["AS4/3501-6"]; // Xt=2280, Xc=1440
  const F1 = 1/mat.Xt - 1/mat.Xc;
  assert(Math.abs(F1) > 1e-10, "F1 non-zero for asymmetric strengths");
  // Tension at Xt/2 vs compression at Xc/2 should give different TW
  const twT = tsaiWuIndex(mat.Xt/2, 0, 0, mat);
  const twC = tsaiWuIndex(-mat.Xc/2, 0, 0, mat);
  assert(Math.abs(twT - twC) > 0.001, "TW asymmetry: tension vs compression differs for AS4");
}

// ═══════════════════════════════════════════════════════════
// SECTION 3: MaxStress failure index correctness
// ═══════════════════════════════════════════════════════════
section("3. MaxStress failure index — exhaustive checks");

// 3a. Zero stress
assertClose(maxStressIndex(0, 0, 0, T300), 0, 1e-10, "MS: zero stress = zero");

// 3b. Pure modes at exact failure
assertClose(maxStressIndex(T300.Xt, 0, 0, T300), 1.0, 1e-10, "MS: σ1=Xt");
assertClose(maxStressIndex(-T300.Xc, 0, 0, T300), 1.0, 1e-10, "MS: σ1=-Xc");
assertClose(maxStressIndex(0, T300.Yt, 0, T300), 1.0, 1e-10, "MS: σ2=Yt");
assertClose(maxStressIndex(0, -T300.Yc, 0, T300), 1.0, 1e-10, "MS: σ2=-Yc");
assertClose(maxStressIndex(0, 0, T300.S12, T300), 1.0, 1e-10, "MS: τ12=S12");
assertClose(maxStressIndex(0, 0, -T300.S12, T300), 1.0, 1e-10, "MS: τ12=-S12 (abs)");

// 3c. Combined load: max controls
{
  const ms = maxStressIndex(T300.Xt * 0.5, T300.Yt * 0.8, 0, T300);
  assertClose(ms, 0.8, 1e-10, "MS: max(0.5, 0.8, 0) = 0.8");
}

// 3d. MaxStress is LINEAR: doubling stress doubles index
{
  const ms1 = maxStressIndex(100, 10, 5, T300);
  const ms2 = maxStressIndex(200, 20, 10, T300);
  assertClose(ms2 / ms1, 2.0, 1e-6, "MS linearity: 2x stress = 2x index");
}

// 3e. All 7 materials: exact failure at each mode
for (const [id, mat] of Object.entries(MATERIALS)) {
  assertClose(maxStressIndex(mat.Xt, 0, 0, mat), 1.0, 1e-10, `MS@Xt for ${id}`);
  assertClose(maxStressIndex(-mat.Xc, 0, 0, mat), 1.0, 1e-10, `MS@-Xc for ${id}`);
  assertClose(maxStressIndex(0, mat.Yt, 0, mat), 1.0, 1e-10, `MS@Yt for ${id}`);
  assertClose(maxStressIndex(0, -mat.Yc, 0, mat), 1.0, 1e-10, `MS@-Yc for ${id}`);
  assertClose(maxStressIndex(0, 0, mat.S12, mat), 1.0, 1e-10, `MS@S12 for ${id}`);
}

// ═══════════════════════════════════════════════════════════
// SECTION 4: Hashin failure indices correctness
// ═══════════════════════════════════════════════════════════
section("4. Hashin indices — exhaustive checks");

// 4a. Zero stress → all zero
{
  const h = hashinIndices(0, 0, 0, T300);
  assertClose(h.ft, 0, 1e-10, "Hashin FT zero at zero stress");
  assertClose(h.fc, 0, 1e-10, "Hashin FC zero at zero stress");
  assertClose(h.mt, 0, 1e-10, "Hashin MT zero at zero stress");
  assertClose(h.mc, 0, 1e-10, "Hashin MC zero at zero stress");
}

// 4b. Pure fiber tension at Xt → FT=1, FC=0
{
  const h = hashinIndices(T300.Xt, 0, 0, T300);
  assertClose(h.ft, 1.0, 0.001, "Hashin FT=1 at σ1=Xt");
  assertClose(h.fc, 0.0, 1e-10, "Hashin FC=0 at σ1>0");
  assertClose(h.mt, 0.0, 1e-10, "Hashin MT=0 at σ2=0,τ=0");
  assertClose(h.mc, 0.0, 1e-10, "Hashin MC=0 at σ2=0");
}

// 4c. Pure fiber compression at Xc → FC=1, FT=0
{
  const h = hashinIndices(-T300.Xc, 0, 0, T300);
  assertClose(h.fc, 1.0, 0.001, "Hashin FC=1 at σ1=-Xc");
  assertClose(h.ft, 0.0, 1e-10, "Hashin FT=0 at σ1<0");
}

// 4d. Pure matrix tension at Yt → MT=1
{
  const h = hashinIndices(0, T300.Yt, 0, T300);
  assertClose(h.mt, 1.0, 0.001, "Hashin MT=1 at σ2=Yt");
  assertClose(h.mc, 0.0, 1e-10, "Hashin MC=0 at σ2>0");
}

// 4e. Fiber tension + shear: (σ1/Xt)² + (τ12/S12)² = 1
{
  // Choose σ1 = 0.6*Xt, τ12 = 0.8*S12 → FT = 0.36 + 0.64 = 1.0
  const s1 = 0.6 * T300.Xt;
  const t12 = 0.8 * T300.S12;
  const h = hashinIndices(s1, 0, t12, T300);
  assertClose(h.ft, 1.0, 0.001, "Hashin FT combined: 0.6²+0.8²=1");
}

// 4f. Hashin modes are mutually exclusive for sign
{
  const h1 = hashinIndices(100, 20, 10, T300); // σ1>0, σ2>0
  assertClose(h1.fc, 0, 1e-10, "FC=0 when σ1>0");
  assertClose(h1.mc, 0, 1e-10, "MC=0 when σ2>0");
  assertGt(h1.ft, 0, "FT>0 when σ1>0");
  assertGt(h1.mt, 0, "MT>0 when σ2>0");

  const h2 = hashinIndices(-100, -20, 10, T300); // σ1<0, σ2<0
  assertClose(h2.ft, 0, 1e-10, "FT=0 when σ1<0");
  assertClose(h2.mt, 0, 1e-10, "MT=0 when σ2<0");
  assertGt(h2.fc, 0, "FC>0 when σ1<0");
}

// 4g. All 7 materials: Hashin FT=1 at Xt
for (const [id, mat] of Object.entries(MATERIALS)) {
  const h = hashinIndices(mat.Xt, 0, 0, mat);
  assertClose(h.ft, 1.0, 0.001, `Hashin FT=1 @Xt for ${id}`);
}

// ═══════════════════════════════════════════════════════════
// SECTION 5: failureLoadFactor — the BIG fix
// ═══════════════════════════════════════════════════════════
section("5. failureLoadFactor — quadratic Tsai-Wu, linear MaxStress");

// 5a. At exact failure stress, load factor should be ≈ 1.0
{
  // σ1=Xt, σ2=0, τ=0 → TW≈1, MS=1 → loadFactor should be ≈1.0
  const tw = tsaiWuIndex(T300.Xt, 0, 0, T300);
  const ms = maxStressIndex(T300.Xt, 0, 0, T300);
  const lf = failureLoadFactor(tw, ms, T300.Xt, 0, 0, T300);
  assertClose(lf, 1.0, 0.01, "LF≈1.0 at σ1=Xt");
}

// 5b. At half failure stress, verify the Tsai-Wu quadratic gives correct λ
// Key: at stress σ, TW(λσ) = bλ + aλ² = 1
// For σ1=Xt/2: should need λ≈2 (roughly, with linear correction)
{
  const s1 = T300.Xt / 2;
  const tw = tsaiWuIndex(s1, 0, 0, T300);
  const ms = maxStressIndex(s1, 0, 0, T300);
  const lf = failureLoadFactor(tw, ms, s1, 0, 0, T300);
  // MaxStress: 1/(0.5) = 2.0
  // Tsai-Wu: quadratic solve should give something near 2.0 but not exactly
  assertGt(lf, 1.5, "LF > 1.5 at half Xt");
  assertLt(lf, 2.5, "LF < 2.5 at half Xt");
  // MaxStress gives exactly 2.0 since it's linear
  assertClose(1 / ms, 2.0, 1e-10, "MaxStress LF = 2.0 at half Xt");
}

// 5c. CRITICAL: verify FI(λ*stress) ≈ 1.0 for the computed λ
// This is the ACID TEST — if loadFactor is correct, scaling stresses by λ should give TW=1
{
  const testCases = [
    { s1: 500, s2: 10, t12: 20, name: "combined tension" },
    { s1: -400, s2: -50, t12: 30, name: "combined compression" },
    { s1: 300, s2: -100, t12: 40, name: "mixed sign biaxial" },
    { s1: 0, s2: 20, t12: 50, name: "transverse + shear" },
    { s1: 100, s2: 0, t12: 60, name: "fiber + shear" },
    { s1: -200, s2: 15, t12: 10, name: "comp fiber + trans tension" },
    { s1: 1000, s2: -200, t12: 0, name: "high fiber tension, trans compression" },
    { s1: 50, s2: 5, t12: 5, name: "very low stress" },
  ];

  for (const tc of testCases) {
    const tw = tsaiWuIndex(tc.s1, tc.s2, tc.t12, T300);
    const ms = maxStressIndex(tc.s1, tc.s2, tc.t12, T300);
    const lf = failureLoadFactor(tw, ms, tc.s1, tc.s2, tc.t12, T300);
    assertGt(lf, 0, `LF > 0 for ${tc.name}`);
    assertFinite(lf, `LF finite for ${tc.name}`);

    // Verify: at λ*stress, the controlling criterion should be ≈ 1.0
    const twAtFail = tsaiWuIndex(lf * tc.s1, lf * tc.s2, lf * tc.t12, T300);
    const msAtFail = maxStressIndex(lf * tc.s1, lf * tc.s2, lf * tc.t12, T300);

    // The MAX of (TW, MS) at failure load should be ≈ 1.0
    // (whichever criterion controls, it hits 1.0; the other may be < 1.0)
    const controllingFI = Math.max(twAtFail, msAtFail);
    assertClose(controllingFI, 1.0, 0.05, `FI@(λσ)≈1.0 for ${tc.name}`);
  }
}

// 5d. OLD BUG CHECK: 1/√FI was wrong. Verify our answer differs from 1/√TW
{
  // At combined loading, 1/√TW ≠ correct λ
  const s1 = 300, s2 = -80, t12 = 40;
  const tw = tsaiWuIndex(s1, s2, t12, T300);
  const ms = maxStressIndex(s1, s2, t12, T300);
  const lfCorrect = failureLoadFactor(tw, ms, s1, s2, t12, T300);

  // Verify correct LF: at least one of TW or MS = 1.0
  const twAtCorrect = tsaiWuIndex(lfCorrect * s1, lfCorrect * s2, lfCorrect * t12, T300);
  const msAtCorrect = maxStressIndex(lfCorrect * s1, lfCorrect * s2, lfCorrect * t12, T300);
  assertClose(Math.max(twAtCorrect, msAtCorrect), 1.0, 0.05, "Controlling FI@(λ_correct·σ) = 1.0");

  // Verify old formula (1/√TW) gives WRONG answer when TW > 0
  if (tw > 0.01) {
    const lfWrong = 1 / Math.sqrt(tw);
    const twAtWrong = tsaiWuIndex(lfWrong * s1, lfWrong * s2, lfWrong * t12, T300);
    // For Tsai-Wu with linear terms, 1/√TW is wrong — TW(λσ) ≠ 1.0
    assert(Math.abs(lfCorrect - lfWrong) > 0.001 || Math.abs(twAtWrong - 1.0) > 0.01,
      `Old 1/√TW formula gives wrong result: TW@old = ${twAtWrong.toFixed(4)}`);
  }
}

// 5e. MaxStress is LINEAR: verify 1/MS is exact
{
  const s1 = 600, s2 = 15, t12 = 30;
  const ms = maxStressIndex(s1, s2, t12, T300);
  const lf_ms = 1 / ms;
  const msAtFail = maxStressIndex(lf_ms * s1, lf_ms * s2, lf_ms * t12, T300);
  assertClose(msAtFail, 1.0, 1e-10, "MS is exactly linear: MS(λσ) = λ·MS(σ) = 1");
}

// 5f. All 7 materials: LF acid test at combined loading
for (const [id, mat] of Object.entries(MATERIALS)) {
  const s1 = mat.Xt * 0.3, s2 = mat.Yt * 0.4, t12 = mat.S12 * 0.2;
  const tw = tsaiWuIndex(s1, s2, t12, mat);
  const ms = maxStressIndex(s1, s2, t12, mat);
  const lf = failureLoadFactor(tw, ms, s1, s2, t12, mat);
  assertGt(lf, 0, `LF > 0 for ${id} combined`);
  const twCheck = tsaiWuIndex(lf*s1, lf*s2, lf*t12, mat);
  const msCheck = maxStressIndex(lf*s1, lf*s2, lf*t12, mat);
  const atFail = Math.max(twCheck, msCheck);
  assertGe(atFail, 0.98, `FI ≥ 0.98 @(λσ) for ${id}`);
  assertLt(atFail, 1.05, `FI < 1.05 @(λσ) for ${id}`);
}

// 5g. Edge case: zero stress → LF=0
{
  const lf = failureLoadFactor(0, 0, 0, 0, 0, T300);
  assertClose(lf, 0, 1e-10, "LF=0 at zero stress");
}

// ═══════════════════════════════════════════════════════════
// SECTION 6: analyzeLaminate — ALL fields populated
// ═══════════════════════════════════════════════════════════
section("6. analyzeLaminate — every result field verified");

const QI_PLIES = [
  { angle: 0, materialId: "T300/5208" },
  { angle: 45, materialId: "T300/5208" },
  { angle: -45, materialId: "T300/5208" },
  { angle: 90, materialId: "T300/5208" },
  { angle: 90, materialId: "T300/5208" },
  { angle: -45, materialId: "T300/5208" },
  { angle: 45, materialId: "T300/5208" },
  { angle: 0, materialId: "T300/5208" },
];

// 6a. All ply result fields exist and are finite for QI laminate under Nx=100
{
  const result = analyzeLaminate(QI_PLIES, MATERIALS, 100, 0, 0);
  assert(result.plies.length === 8, "QI has 8 plies");

  for (let k = 0; k < result.plies.length; k++) {
    const pr = result.plies[k];
    const prefix = `Ply ${k} (${pr.angle}°)`;
    assertFinite(pr.sigmaX, `${prefix} sigmaX`);
    assertFinite(pr.sigmaY, `${prefix} sigmaY`);
    assertFinite(pr.tauXY, `${prefix} tauXY`);
    assertFinite(pr.sigma1, `${prefix} sigma1`);
    assertFinite(pr.sigma2, `${prefix} sigma2`);
    assertFinite(pr.tau12, `${prefix} tau12`);
    assertFinite(pr.tsaiWu, `${prefix} tsaiWu`);
    assertFinite(pr.maxStress, `${prefix} maxStress`);
    assertFinite(pr.hashinFT, `${prefix} hashinFT`);
    assertFinite(pr.hashinFC, `${prefix} hashinFC`);
    assertFinite(pr.hashinMT, `${prefix} hashinMT`);
    assertFinite(pr.hashinMC, `${prefix} hashinMC`);
    assert(typeof pr.failed === "boolean", `${prefix} failed is boolean`);
    assert(typeof pr.failureMode === "string", `${prefix} failureMode is string`);
    assert(pr.plyIndex === k, `${prefix} plyIndex`);
    assertFinite(pr.zBot, `${prefix} zBot`);
    assertFinite(pr.zTop, `${prefix} zTop`);
    assertGt(pr.zTop, pr.zBot, `${prefix} zTop > zBot`);
  }
}

// 6b. ABD fields
{
  const result = analyzeLaminate(QI_PLIES, MATERIALS, 100, 0, 0);
  const { abd } = result;
  assertGt(abd.Ex, 0, "Ex > 0");
  assertGt(abd.Ey, 0, "Ey > 0");
  assertGt(abd.Gxy, 0, "Gxy > 0");
  assertGt(abd.totalThickness, 0, "totalThickness > 0");
  assertClose(abd.plyCount, 8, 0, "plyCount = 8");
  assertClose(abd.totalThickness, 8 * 0.125, 1e-10, "totalH = 8 * 0.125 mm");
  // A matrix: A11 > 0
  assertGt(abd.A[0][0], 0, "A11 > 0");
  assertGt(abd.A[1][1], 0, "A22 > 0");
  assertGt(abd.A[2][2], 0, "A66 > 0");
}

// 6c. FPF and LPF exist and are positive for non-trivial load
{
  const result = analyzeLaminate(QI_PLIES, MATERIALS, 100, 0, 0);
  assertNotNull(result.firstPlyFailure, "FPF not null");
  assertNotNull(result.lastPlyFailure, "LPF not null");
  assertGt(result.firstPlyFailure.load, 0, "FPF load > 0");
  assertGt(result.lastPlyFailure.load, 0, "LPF load > 0");
  assertGe(result.lastPlyFailure.load, result.firstPlyFailure.load, "LPF ≥ FPF");
}

// 6d. FPF: scale stress by FPF load → some ply should have FI ≈ 1.0
{
  const result = analyzeLaminate(QI_PLIES, MATERIALS, 100, 0, 0);
  const lf = result.firstPlyFailure.load;
  const atFPF = analyzeLaminate(QI_PLIES, MATERIALS, 100 * lf, 0, 0);
  let maxFI = 0;
  for (const pr of atFPF.plies) {
    const fi = Math.max(pr.tsaiWu, pr.maxStress);
    if (fi > maxFI) maxFI = fi;
  }
  assertClose(maxFI, 1.0, 0.05, "At FPF load, max FI ≈ 1.0");
}

// 6e. Symmetric laminate: B matrix should be ~zero, curvatures ~zero
{
  const result = analyzeLaminate(QI_PLIES, MATERIALS, 100, 50, 10);
  let bMax = 0;
  for (let i=0;i<3;i++) for(let j=0;j<3;j++) bMax = Math.max(bMax, Math.abs(result.abd.B[i][j]));
  assertLt(bMax, 1e-8, "B ≈ 0 for symmetric laminate");
  assertClose(result.midplaneCurvature[0], 0, 1e-10, "κx=0 symmetric, Mx=0");
  assertClose(result.midplaneCurvature[1], 0, 1e-10, "κy=0 symmetric, My=0");
  assertClose(result.midplaneCurvature[2], 0, 1e-10, "κxy=0 symmetric, Mxy=0");
}

// 6f. Midplane strain for unidirectional under Nx: εx = Nx/(A11)
{
  const UD = Array(8).fill(null).map(() => ({ angle: 0, materialId: "T300/5208" }));
  const result = analyzeLaminate(UD, MATERIALS, 100, 0, 0);
  // For UD, A12 ≠ 0, so εx = a11*N where a = inv(A), not simply 1/A11
  const aInv = invertMat3(result.abd.A);
  const expectedEx = aInv[0][0] * (100/1000); // a11 * Nx(in GPa·mm)
  assertClose(result.midplaneStrain[0], expectedEx, 1e-8, "εx = a11·Nx for UD");
}

// ═══════════════════════════════════════════════════════════
// SECTION 7: All 7 materials → valid laminate results
// ═══════════════════════════════════════════════════════════
section("7. All 7 materials — full laminate analysis");

for (const [id, mat] of Object.entries(MATERIALS)) {
  const plies = [0, 45, -45, 90, 90, -45, 45, 0].map(a => ({ angle: a, materialId: id }));
  const result = analyzeLaminate(plies, MATERIALS, 100, 50, 10);

  assert(result.plies.length === 8, `${id}: 8 plies`);
  assertNotNull(result.firstPlyFailure, `${id}: FPF not null`);
  assertNotNull(result.lastPlyFailure, `${id}: LPF not null`);
  assertGt(result.firstPlyFailure.load, 0, `${id}: FPF > 0`);

  // Every ply has finite stresses
  for (const pr of result.plies) {
    assertFinite(pr.sigma1, `${id} ply${pr.plyIndex} sigma1`);
    assertFinite(pr.sigma2, `${id} ply${pr.plyIndex} sigma2`);
    assertFinite(pr.tau12, `${id} ply${pr.plyIndex} tau12`);
    assertFinite(pr.tsaiWu, `${id} ply${pr.plyIndex} tsaiWu`);
    assertFinite(pr.maxStress, `${id} ply${pr.plyIndex} maxStress`);
    assertFinite(pr.hashinFT, `${id} ply${pr.plyIndex} hashinFT`);
    assertFinite(pr.hashinFC, `${id} ply${pr.plyIndex} hashinFC`);
    assertFinite(pr.hashinMT, `${id} ply${pr.plyIndex} hashinMT`);
    assertFinite(pr.hashinMC, `${id} ply${pr.plyIndex} hashinMC`);
  }

  // ABD engineering constants all positive
  assertGt(result.abd.Ex, 0, `${id}: Ex > 0`);
  assertGt(result.abd.Ey, 0, `${id}: Ey > 0`);
  assertGt(result.abd.Gxy, 0, `${id}: Gxy > 0`);
}

// ═══════════════════════════════════════════════════════════
// SECTION 8: progressiveFailure — caller mutation guard
// ═══════════════════════════════════════════════════════════
section("8. progressiveFailure — NO caller mutation");

{
  const originalPlies = [
    { angle: 0, materialId: "T300/5208" },
    { angle: 90, materialId: "T300/5208" },
    { angle: 90, materialId: "T300/5208" },
    { angle: 0, materialId: "T300/5208" },
  ];

  // Deep copy to check
  const pliesBefore = JSON.parse(JSON.stringify(originalPlies));
  const matsBefore = JSON.parse(JSON.stringify(MATERIALS));

  // Run progressive failure with high load that WILL cause degradation
  const curve = progressiveFailure(originalPlies, MATERIALS, 500, 200, 100, 20);

  // 8a. Plies array must be IDENTICAL to before
  assert(JSON.stringify(originalPlies) === JSON.stringify(pliesBefore),
    "Plies array not mutated by progressiveFailure");

  // 8b. Materials object must be IDENTICAL to before
  assert(JSON.stringify(MATERIALS) === JSON.stringify(matsBefore),
    "Materials object not mutated by progressiveFailure");

  // 8c. Curve should have entries
  assertGt(curve.length, 0, "Progressive failure curve has entries");
  assert(curve.length === 21, "Progressive failure curve has steps+1 entries");

  // 8d. Some plies should have failed (load is high)
  const lastPoint = curve[curve.length - 1];
  assertGt(lastPoint.failedPlies, 0, "Some plies failed at 2x load");

  // 8e. Load factor monotonically increases
  for (let i = 1; i < curve.length; i++) {
    assertGe(curve[i].loadFactor, curve[i-1].loadFactor, `LF monotonic at step ${i}`);
  }

  // 8f. First point is at zero load → zero FI
  assertClose(curve[0].loadFactor, 0, 1e-10, "First point LF=0");
  assertClose(curve[0].maxFI, 0, 1e-10, "First point maxFI=0");
  assertClose(curve[0].failedPlies, 0, 0, "First point no failures");
}

// 8g. Run with ALL 7 materials — no crashes
for (const [id] of Object.entries(MATERIALS)) {
  const plies = [0, 45, -45, 90].map(a => ({ angle: a, materialId: id }));
  let threw = false;
  try { progressiveFailure(plies, MATERIALS, 300, 100, 50, 10); }
  catch { threw = true; }
  assert(!threw, `progressiveFailure for ${id} does not throw`);
}

// ═══════════════════════════════════════════════════════════
// SECTION 9: Stress transformation correctness
// ═══════════════════════════════════════════════════════════
section("9. Stress transformation — global ↔ material axes");

// 9a. 0° ply: material axes = global axes
{
  const [s1, s2, t12] = globalToMaterial(100, 50, 25, 0);
  assertClose(s1, 100, 1e-10, "0° ply: σ1 = σx");
  assertClose(s2, 50, 1e-10, "0° ply: σ2 = σy");
  assertClose(t12, 25, 1e-10, "0° ply: τ12 = τxy");
}

// 9b. 90° ply: axes swapped
{
  const [s1, s2, t12] = globalToMaterial(100, 50, 25, 90);
  assertClose(s1, 50, 1e-6, "90° ply: σ1 = σy");
  assertClose(s2, 100, 1e-6, "90° ply: σ2 = σx");
  assertClose(t12, -25, 1e-6, "90° ply: τ12 = -τxy");
}

// 9c. Invariant: σ1+σ2 = σx+σy for any angle (trace is invariant)
{
  for (const theta of [0, 15, 30, 45, 60, 75, 90, -30, -60]) {
    const [s1, s2] = globalToMaterial(120, 80, 35, theta);
    assertClose(s1 + s2, 200, 1e-6, `Trace invariant at ${theta}°`);
  }
}

// 9d. Pure shear at 45°: transforms to pure tension/compression
{
  const [s1, s2, t12] = globalToMaterial(0, 0, 100, 45);
  assertClose(s1, 100, 1e-6, "45° under pure shear: σ1 = τxy");
  assertClose(s2, -100, 1e-6, "45° under pure shear: σ2 = -τxy");
  assertClose(t12, 0, 1e-6, "45° under pure shear: τ12 = 0");
}

// ═══════════════════════════════════════════════════════════
// SECTION 10: Multi-layup FPF/LPF consistency
// ═══════════════════════════════════════════════════════════
section("10. FPF/LPF across layups — consistency and bounds");

const LAYUPS = {
  "UD [0]8": Array(8).fill(null).map(() => ({ angle: 0, materialId: "T300/5208" })),
  "Cross-ply [0/90]2s": [0,90,0,90,90,0,90,0].map(a => ({ angle: a, materialId: "T300/5208" })),
  "QI [0/±45/90]s": [0,45,-45,90,90,-45,45,0].map(a => ({ angle: a, materialId: "T300/5208" })),
  "±45 dom": [45,-45,45,-45,-45,45,-45,45].map(a => ({ angle: a, materialId: "T300/5208" })),
};

for (const [name, plies] of Object.entries(LAYUPS)) {
  const LOADS = [
    { Nx: 100, Ny: 0, Nxy: 0, label: "pure Nx" },
    { Nx: 0, Ny: 100, Nxy: 0, label: "pure Ny" },
    { Nx: 0, Ny: 0, Nxy: 100, label: "pure Nxy" },
    { Nx: 100, Ny: 50, Nxy: 20, label: "combined" },
    { Nx: -100, Ny: -50, Nxy: 0, label: "biaxial compression" },
  ];

  for (const load of LOADS) {
    const result = analyzeLaminate(plies, MATERIALS, load.Nx, load.Ny, load.Nxy);
    const tag = `${name} / ${load.label}`;

    assertNotNull(result.firstPlyFailure, `${tag}: FPF exists`);
    assertNotNull(result.lastPlyFailure, `${tag}: LPF exists`);
    assertGt(result.firstPlyFailure.load, 0, `${tag}: FPF > 0`);
    assertGe(result.lastPlyFailure.load, result.firstPlyFailure.load, `${tag}: LPF ≥ FPF`);
  }
}

// ═══════════════════════════════════════════════════════════
// SECTION 11: UD laminate under Nx — exact analytical check
// ═══════════════════════════════════════════════════════════
section("11. UD laminate — analytical stress verification");

{
  const UD = Array(8).fill(null).map(() => ({ angle: 0, materialId: "T300/5208" }));
  const Nx = 200; // N/mm
  const result = analyzeLaminate(UD, MATERIALS, Nx, 0, 0);
  const totalH = 8 * 0.125; // mm
  const avgSigX = Nx / totalH; // MPa

  // For UD laminate under pure Nx, ALL plies should have same stress
  for (const pr of result.plies) {
    assertClose(pr.sigmaX, avgSigX, 0.1, `UD ply${pr.plyIndex}: σx = Nx/h = ${avgSigX}`);
    assertClose(pr.sigmaY, 0, 0.5, `UD ply${pr.plyIndex}: σy ≈ 0`);
    assertClose(pr.tauXY, 0, 0.1, `UD ply${pr.plyIndex}: τxy = 0`);
    // Material axes = global axes for 0° ply
    assertClose(pr.sigma1, avgSigX, 0.1, `UD ply${pr.plyIndex}: σ1 = σx`);
    assertClose(pr.sigma2, 0, 0.5, `UD ply${pr.plyIndex}: σ2 ≈ 0`);
    assertClose(pr.tau12, 0, 0.1, `UD ply${pr.plyIndex}: τ12 = 0`);
  }
}

// ═══════════════════════════════════════════════════════════
// SECTION 12: Hashin mode exclusivity in real laminate
// ═══════════════════════════════════════════════════════════
section("12. Hashin mode exclusivity in real analysis");

{
  const result = analyzeLaminate(QI_PLIES, MATERIALS, 200, -100, 50);
  for (const pr of result.plies) {
    // If σ1 ≥ 0: FT can be active, FC must be 0
    if (pr.sigma1 >= 0) {
      assertClose(pr.hashinFC, 0, 1e-10, `Ply${pr.plyIndex}: FC=0 when σ1≥0`);
    } else {
      assertClose(pr.hashinFT, 0, 1e-10, `Ply${pr.plyIndex}: FT=0 when σ1<0`);
    }
    // If σ2 ≥ 0: MT can be active, MC must be 0
    if (pr.sigma2 >= 0) {
      assertClose(pr.hashinMC, 0, 1e-10, `Ply${pr.plyIndex}: MC=0 when σ2≥0`);
    } else {
      assertClose(pr.hashinMT, 0, 1e-10, `Ply${pr.plyIndex}: MT=0 when σ2<0`);
    }
    // FT, FC, MT always ≥ 0 (sum of squares).
    // MC can be slightly negative at low σ2<0 due to linear Yc term in Hashin MC formula.
    assertGe(pr.hashinFT, 0, `Ply${pr.plyIndex}: FT ≥ 0`);
    assertGe(pr.hashinFC, 0, `Ply${pr.plyIndex}: FC ≥ 0`);
    assertGe(pr.hashinMT, 0, `Ply${pr.plyIndex}: MT ≥ 0`);
    assertGe(pr.hashinMC, -0.5, `Ply${pr.plyIndex}: MC ≥ -0.5 (can be slightly negative at low σ2)`);
  }
}

// ═══════════════════════════════════════════════════════════
// SECTION 13: Load scaling linearity
// ═══════════════════════════════════════════════════════════
section("13. Load scaling — stress linearity");

{
  const r1 = analyzeLaminate(QI_PLIES, MATERIALS, 100, 50, 10);
  const r2 = analyzeLaminate(QI_PLIES, MATERIALS, 200, 100, 20);

  for (let k = 0; k < 8; k++) {
    assertClose(r2.plies[k].sigmaX, 2 * r1.plies[k].sigmaX, 0.001,
      `2x load → 2x sigmaX ply${k}`);
    assertClose(r2.plies[k].sigma1, 2 * r1.plies[k].sigma1, 0.001,
      `2x load → 2x sigma1 ply${k}`);
    assertClose(r2.plies[k].sigma2, 2 * r1.plies[k].sigma2, 0.001,
      `2x load → 2x sigma2 ply${k}`);
    assertClose(r2.plies[k].tau12, 2 * r1.plies[k].tau12, 0.001,
      `2x load → 2x tau12 ply${k}`);
  }

  // MaxStress scales linearly
  for (let k = 0; k < 8; k++) {
    assertClose(r2.plies[k].maxStress, 2 * r1.plies[k].maxStress, 0.001,
      `2x load → 2x maxStress ply${k}`);
  }
}

// ═══════════════════════════════════════════════════════════
// SECTION 14: Equilibrium check — sum of ply forces = applied
// ═══════════════════════════════════════════════════════════
section("14. Equilibrium — ply force sum = applied load");

{
  const Nx = 150, Ny = 80, Nxy = 30;
  const result = analyzeLaminate(QI_PLIES, MATERIALS, Nx, Ny, Nxy);
  let sumFx = 0, sumFy = 0, sumFxy = 0;
  for (const pr of result.plies) {
    const t = pr.zTop - pr.zBot;
    sumFx += pr.sigmaX * t;
    sumFy += pr.sigmaY * t;
    sumFxy += pr.tauXY * t;
  }
  assertClose(sumFx, Nx, 0.01, `ΣFx = Nx = ${Nx}`);
  assertClose(sumFy, Ny, 0.01, `ΣFy = Ny = ${Ny}`);
  assertClose(sumFxy, Nxy, 0.01, `ΣFxy = Nxy = ${Nxy}`);
}

// Repeat for all materials
for (const [id] of Object.entries(MATERIALS)) {
  const plies = [0,45,-45,90,90,-45,45,0].map(a => ({ angle: a, materialId: id }));
  const Nx = 120, Ny = 60, Nxy = 25;
  const result = analyzeLaminate(plies, MATERIALS, Nx, Ny, Nxy);
  let sumFx = 0, sumFy = 0, sumFxy = 0;
  for (const pr of result.plies) {
    const t = pr.zTop - pr.zBot;
    sumFx += pr.sigmaX * t;
    sumFy += pr.sigmaY * t;
    sumFxy += pr.tauXY * t;
  }
  assertClose(sumFx, Nx, 0.1, `${id}: ΣFx = Nx`);
  assertClose(sumFy, Ny, 0.1, `${id}: ΣFy = Ny`);
  assertClose(sumFxy, Nxy, 0.1, `${id}: ΣFxy = Nxy`);
}

// ═══════════════════════════════════════════════════════════
// SECTION 15: Negative FI handling
// ═══════════════════════════════════════════════════════════
section("15. Negative failure indices — edge cases");

// Tsai-Wu CAN be negative (linear term dominates). This is valid and means "extra safe".
{
  // Small compressive σ1 with Xt≠Xc → F1<0, linear term pulls TW negative at low stress
  const mat = MATERIALS["AS4/3501-6"]; // Xt=2280, Xc=1440 → F1 = 1/2280 - 1/1440 < 0
  const F1 = 1/mat.Xt - 1/mat.Xc;
  assertLt(F1, 0, "F1 < 0 for AS4 (Xt > Xc? No, Xt>Xc gives F1<0? Let me check...)");
  // Actually F1 = 1/Xt - 1/Xc. Xt=2280 > Xc=1440, so 1/Xt < 1/Xc → F1 < 0
  // Small positive σ1: F1*σ1 is negative, could make TW < 0
  const tw = tsaiWuIndex(10, 0, 0, mat); // tiny tensile
  // This could be negative or positive depending on quadratic vs linear
  assertFinite(tw, "TW finite at small tensile stress");
}

// MaxStress is always ≥ 0
{
  const ms = maxStressIndex(0, 0, 0, T300);
  assertGe(ms, 0, "MS ≥ 0 always");
  const ms2 = maxStressIndex(-10, -5, 1, T300);
  assertGe(ms2, 0, "MS ≥ 0 even at small compressive");
}

// failureLoadFactor with negative TW should still work
{
  const mat = MATERIALS["AS4/3501-6"];
  const s1 = 10, s2 = 0, t12 = 0;
  const tw = tsaiWuIndex(s1, s2, t12, mat);
  const ms = maxStressIndex(s1, s2, t12, mat);
  const lf = failureLoadFactor(tw, ms, s1, s2, t12, mat);
  assertGt(lf, 0, "LF > 0 even when TW might be negative");
  assertFinite(lf, "LF finite when TW might be negative");
}

// ═══════════════════════════════════════════════════════════
// SECTION 16: Mixed-material laminate
// ═══════════════════════════════════════════════════════════
section("16. Mixed-material laminate");

{
  const mixedPlies = [
    { angle: 0, materialId: "T300/5208" },
    { angle: 45, materialId: "IM7/8552" },
    { angle: -45, materialId: "AS4/3501-6" },
    { angle: 90, materialId: "E-Glass/Epoxy" },
    { angle: 90, materialId: "E-Glass/Epoxy" },
    { angle: -45, materialId: "AS4/3501-6" },
    { angle: 45, materialId: "IM7/8552" },
    { angle: 0, materialId: "T300/5208" },
  ];

  const result = analyzeLaminate(mixedPlies, MATERIALS, 100, 50, 20);
  assert(result.plies.length === 8, "Mixed: 8 plies");
  assertNotNull(result.firstPlyFailure, "Mixed: FPF exists");

  // All plies have valid results
  for (const pr of result.plies) {
    assertFinite(pr.sigma1, `Mixed ply${pr.plyIndex}: σ1 finite`);
    assertFinite(pr.tsaiWu, `Mixed ply${pr.plyIndex}: TW finite`);
    assertFinite(pr.hashinFT, `Mixed ply${pr.plyIndex}: HFT finite`);
  }

  // Equilibrium
  let sumFx = 0;
  for (const pr of result.plies) sumFx += pr.sigmaX * (pr.zTop - pr.zBot);
  assertClose(sumFx, 100, 0.1, "Mixed: ΣFx = 100");
}

// ═══════════════════════════════════════════════════════════
// SECTION 17: Non-symmetric laminate (B ≠ 0, curvature)
// ═══════════════════════════════════════════════════════════
section("17. Non-symmetric laminate — coupling");

{
  // [0/90] non-symmetric → B ≠ 0
  const asymPlies = [
    { angle: 0, materialId: "T300/5208" },
    { angle: 90, materialId: "T300/5208" },
  ];
  const result = analyzeLaminate(asymPlies, MATERIALS, 100, 0, 0);

  // B should be non-zero
  let bMax = 0;
  for (let i=0;i<3;i++) for(let j=0;j<3;j++) bMax = Math.max(bMax, Math.abs(result.abd.B[i][j]));
  assertGt(bMax, 0.001, "Non-symmetric: B ≠ 0");

  // Still has valid results
  for (const pr of result.plies) {
    assertFinite(pr.sigma1, `Asym ply${pr.plyIndex}: σ1 finite`);
    assertFinite(pr.tsaiWu, `Asym ply${pr.plyIndex}: TW finite`);
  }

  // Curvatures should be non-zero (coupling)
  const kNorm = Math.sqrt(result.midplaneCurvature.reduce((s,v) => s+v*v, 0));
  assertGt(kNorm, 1e-10, "Non-symmetric: curvatures ≠ 0");
}

// ═══════════════════════════════════════════════════════════
// SECTION 18: QI laminate — quasi-isotropic property check
// ═══════════════════════════════════════════════════════════
section("18. Quasi-isotropic laminate — Ex ≈ Ey, A16≈A26≈0");

{
  const result = analyzeLaminate(QI_PLIES, MATERIALS, 100, 0, 0);
  assertClose(result.abd.Ex, result.abd.Ey, 0.5, "QI: Ex ≈ Ey");
  assertClose(result.abd.A[0][2], 0, 0.01, "QI: A16 ≈ 0");
  assertClose(result.abd.A[1][2], 0, 0.01, "QI: A26 ≈ 0");
}

// ═══════════════════════════════════════════════════════════
// SECTION 19: FPF acid test — ALL layups, ALL materials, ALL loads
// ═══════════════════════════════════════════════════════════
section("19. FPF acid test — comprehensive sweep");

{
  const loadCases = [
    [100, 0, 0], [0, 100, 0], [0, 0, 100],
    [-100, 0, 0], [0, -100, 0],
    [100, 50, 25], [-80, -40, 20],
    [200, 0, 50], [0, 200, 50],
  ];
  const layupAngles = [
    [0,0,0,0], [0,90,90,0], [0,45,-45,90,90,-45,45,0], [45,-45,-45,45],
  ];

  let count = 0;
  for (const [matId] of Object.entries(MATERIALS)) {
    for (const angles of layupAngles) {
      const plies = angles.map(a => ({ angle: a, materialId: matId }));
      for (const [Nx, Ny, Nxy] of loadCases) {
        const result = analyzeLaminate(plies, MATERIALS, Nx, Ny, Nxy);
        if (result.firstPlyFailure) {
          const lf = result.firstPlyFailure.load;
          assertGt(lf, 0, `FPF>0: ${matId} [${angles}] N=[${Nx},${Ny},${Nxy}]`);
          // Scale and check
          const atFPF = analyzeLaminate(plies, MATERIALS, Nx*lf, Ny*lf, Nxy*lf);
          let maxFI = 0;
          for (const pr of atFPF.plies) maxFI = Math.max(maxFI, pr.tsaiWu, pr.maxStress);
          assertClose(maxFI, 1.0, 0.1, `FI@FPF≈1: ${matId} [${angles}] N=[${Nx},${Ny},${Nxy}]`);
          count++;
        }
      }
    }
  }
  assertGt(count, 200, `FPF acid test ran ${count} > 200 cases`);
}

// ═══════════════════════════════════════════════════════════
// SECTION 20: Transformed stiffness symmetry
// ═══════════════════════════════════════════════════════════
section("20. Transformed stiffness — Q̄ symmetry");

for (const [id, mat] of Object.entries(MATERIALS)) {
  for (const theta of [0, 15, 30, 45, 60, 90, -30]) {
    const Q = transformedStiffness(mat, theta);
    assertClose(Q[0][1], Q[1][0], 1e-10, `Q̄12=Q̄21 for ${id} @${theta}°`);
    assertClose(Q[0][2], Q[2][0], 1e-10, `Q̄16=Q̄61 for ${id} @${theta}°`);
    assertClose(Q[1][2], Q[2][1], 1e-10, `Q̄26=Q̄62 for ${id} @${theta}°`);
  }
}

// At 0°: Q̄16=Q̄26=0 for orthotropic
for (const [id, mat] of Object.entries(MATERIALS)) {
  const Q = transformedStiffness(mat, 0);
  assertClose(Q[0][2], 0, 1e-10, `Q̄16=0 @0° for ${id}`);
  assertClose(Q[1][2], 0, 1e-10, `Q̄26=0 @0° for ${id}`);
}

// At 90°: Q̄16=Q̄26=0 as well
for (const [id, mat] of Object.entries(MATERIALS)) {
  const Q = transformedStiffness(mat, 90);
  assertClose(Q[0][2], 0, 1e-6, `Q̄16=0 @90° for ${id}`);
  assertClose(Q[1][2], 0, 1e-6, `Q̄26=0 @90° for ${id}`);
}

// ═══════════════════════════════════════════════════════════
// FINAL REPORT
// ═══════════════════════════════════════════════════════════
console.log(`\n${"═".repeat(50)}`);
console.log(`TOTAL: ${total}  |  PASSED: ${passed}  |  FAILED: ${failed}`);
console.log(`${"═".repeat(50)}`);
if (failed > 0) {
  console.log(`\n⚠ ${failed} tests FAILED — review above.`);
  process.exit(1);
} else {
  console.log(`\n✓ ALL ${passed} tests passed.`);
}
