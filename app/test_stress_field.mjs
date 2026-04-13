/**
 * STRESS FIELD VALIDATION
 * Tests the actual Lekhnitskii complex potential implementation
 * against known SCF values at the hole boundary.
 */

// ─── Complex number utilities (identical to stress-field.ts) ───
function cadd(a, b) { return { re: a.re + b.re, im: a.im + b.im }; }
function csub(a, b) { return { re: a.re - b.re, im: a.im - b.im }; }
function cmul(a, b) { return { re: a.re*b.re - a.im*b.im, im: a.re*b.im + a.im*b.re }; }
function cdiv(a, b) {
  const d = b.re*b.re + b.im*b.im;
  if (d < 1e-30) return {re:0, im:0};
  return { re: (a.re*b.re + a.im*b.im)/d, im: (a.im*b.re - a.re*b.im)/d };
}
function csqrt(z) {
  const r = Math.sqrt(z.re*z.re + z.im*z.im);
  const t = Math.atan2(z.im, z.re);
  const sr = Math.sqrt(r);
  return { re: sr*Math.cos(t/2), im: sr*Math.sin(t/2) };
}
function cscale(z, s) { return { re: z.re*s, im: z.im*s }; }

// ─── characteristicRoots ───
function characteristicRoots(mat) {
  const E1 = mat.E1*1000, E2 = mat.E2*1000, G12 = mat.G12*1000;
  const a11 = 1/E1, a22 = 1/E2, a12 = -mat.v12/E1, a66 = 1/G12;
  const A = a11, B = 2*a12 + a66, C = a22;
  const disc = B*B - 4*A*C;
  let mu1, mu2;
  if (disc < 0) {
    const rp = -B/(2*A), ip = Math.sqrt(-disc)/(2*A);
    mu1 = csqrt({re: rp, im: ip});
    mu2 = csqrt({re: rp, im: -ip});
  } else {
    const t1 = (-B + Math.sqrt(disc))/(2*A);
    const t2 = (-B - Math.sqrt(disc))/(2*A);
    mu1 = t1 < 0 ? {re:0, im:Math.sqrt(-t1)} : {re:Math.sqrt(t1), im:0};
    mu2 = t2 < 0 ? {re:0, im:Math.sqrt(-t2)} : {re:Math.sqrt(t2), im:0};
  }
  if (mu1.im < 0) { mu1.re = -mu1.re; mu1.im = -mu1.im; }
  if (mu2.im < 0) { mu2.re = -mu2.re; mu2.im = -mu2.im; }
  return [mu1, mu2];
}

// ─── ellipseStress (copy from stress-field.ts) ───
function ellipseStress(px, py, a, b, cx, cy, angle, sigXinf, sigYinf, tauXYinf, mu1, mu2) {
  const rad = (-angle * Math.PI) / 180;
  const cosA = Math.cos(rad), sinA = Math.sin(rad);
  const dx = px - cx, dy = py - cy;
  const x = cosA*dx + sinA*dy;
  const y = -sinA*dx + cosA*dy;

  const c2 = cosA*cosA, s2 = sinA*sinA, cs = cosA*sinA;
  const sxL = c2*sigXinf + s2*sigYinf + 2*cs*tauXYinf;
  const syL = s2*sigXinf + c2*sigYinf - 2*cs*tauXYinf;
  const txyL = -cs*sigXinf + cs*sigYinf + (c2-s2)*tauXYinf;

  const ellCheck = (x*x)/(a*a) + (y*y)/(b*b);
  if (ellCheck < 1.0) return { sigX: 0, sigY: 0, tauXY: 0 };

  const z1 = { re: x + mu1.re*y, im: mu1.im*y };
  const z2 = { re: x + mu2.re*y, im: mu2.im*y };

  const a2 = a*a, b2 = b*b;
  const mu1sq = cmul(mu1, mu1);
  const z1sq = cmul(z1, z1);
  const inner1 = csub(z1sq, { re: a2 + mu1sq.re*b2, im: mu1sq.im*b2 });
  const sqrt1 = csqrt(inner1);

  const mu2sq = cmul(mu2, mu2);
  const z2sq = cmul(z2, z2);
  const inner2 = csub(z2sq, { re: a2 + mu2sq.re*b2, im: mu2sq.im*b2 });
  const sqrt2 = csqrt(inner2);

  const num1 = cadd(z1, sqrt1);
  const den1 = { re: a + mu1.im*b, im: -mu1.re*b };
  const zeta1 = cdiv(num1, den1);

  const num2 = cadd(z2, sqrt2);
  const den2 = { re: a + mu2.im*b, im: -mu2.re*b };
  const zeta2 = cdiv(num2, den2);

  const dzeta1 = cdiv(cadd({re:1,im:0}, cdiv(z1, sqrt1)), den1);
  const dzeta2 = cdiv(cadd({re:1,im:0}, cdiv(z2, sqrt2)), den2);

  const mu_diff = csub(mu1, mu2);
  if (mu_diff.re*mu_diff.re + mu_diff.im*mu_diff.im < 1e-20) {
    return { sigX: sxL, sigY: syL, tauXY: txyL };
  }

  const im_inv = { re: 0, im: -1 };
  const c1_sy = cdiv(cmul(cscale(im_inv, syL), den2), mu_diff);
  const c2_sy = cdiv(cmul(cscale(im_inv, -syL), den1), mu_diff);
  const c1_sx = cdiv(cmul(cmul(cscale(im_inv, sxL), mu2), den2), cmul(mu_diff, mu1));
  const c2_sx = cdiv(cmul(cmul(cscale(im_inv, -sxL), mu1), den1), cmul(mu_diff, mu2));
  const c1_txy = cdiv(cmul(cscale({re:0, im:txyL/2}, 1), csub(cmul(mu2, den2), den2)), mu_diff);
  const c2_txy = cdiv(cmul(cscale({re:0, im:-txyL/2}, 1), csub(cmul(mu1, den1), den1)), mu_diff);

  const C1 = cadd(cadd(c1_sy, c1_sx), c1_txy);
  const C2 = cadd(cadd(c2_sy, c2_sx), c2_txy);

  const invZeta1 = cdiv({re:1,im:0}, zeta1);
  const invZeta2 = cdiv({re:1,im:0}, zeta2);

  const phi1_prime = cmul(C1, cmul(invZeta1, dzeta1));
  const phi2_prime = cmul(C2, cmul(invZeta2, dzeta2));

  const mu1sq_phi1 = cmul(mu1sq, phi1_prime);
  const mu2sq_phi2 = cmul(mu2sq, phi2_prime);
  const dSigX = 2 * (mu1sq_phi1.re + mu2sq_phi2.re);
  const dSigY = 2 * (phi1_prime.re + phi2_prime.re);
  const mu1_phi1 = cmul(mu1, phi1_prime);
  const mu2_phi2 = cmul(mu2, phi2_prime);
  const dTauXY = -2 * (mu1_phi1.re + mu2_phi2.re);

  let sigXL = sxL + dSigX;
  let sigYL = syL + dSigY;
  let tauXYL = txyL + dTauXY;

  const sigX = c2*sigXL + s2*sigYL - 2*cs*tauXYL;
  const sigY = s2*sigXL + c2*sigYL + 2*cs*tauXYL;
  const tauXY = cs*sigXL - cs*sigYL + (c2-s2)*tauXYL;

  return { sigX, sigY, tauXY };
}

// ═══════════════════════════════════════════════
let passed = 0, failed = 0;
function assert(cond, msg, detail="") {
  if (cond) { passed++; console.log(`  ✓ ${msg}`); }
  else { failed++; console.log(`  ✗ FAIL: ${msg} ${detail}`); }
}
function approx(a, b, tol=0.05) {
  return Math.abs(a - b) / Math.max(Math.abs(b), 1e-10) < tol;
}

// ═══════════════════════════════════════════════
// TEST A: Isotropic circular hole under σy — SCF at (a+ε, 0) should be ~3.0
// ═══════════════════════════════════════════════
console.log("\n═══ TEST A: Isotropic circular hole, σy=100 MPa ═══");
{
  const isoMat = { E1: 70, E2: 70, G12: 70/(2*1.3), v12: 0.3, Xt:500, Xc:500, Yt:500, Yc:500, S12:300, plyThickness:0.125 };
  const [mu1, mu2] = characteristicRoots(isoMat);
  const a = 5.0; // hole radius 5mm

  // Test at several distances from hole edge along x-axis (y=0)
  console.log("  Point (x, 0) — σy/σy∞ (expect 3.0 at hole edge, decaying to 1.0):");
  const sigYinf = 100;
  const distances = [0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0];

  for (const dist of distances) {
    const x = a + dist;
    const result = ellipseStress(x, 0, a, a, 0, 0, 0, 0, sigYinf, 0, mu1, mu2);
    const scf = result.sigY / sigYinf;
    console.log(`    x=${x.toFixed(2)}: σy=${result.sigY.toFixed(1)} MPa, SCF=${scf.toFixed(3)}, σx=${result.sigX.toFixed(1)}, τxy=${result.tauXY.toFixed(2)}`);
  }

  // At x=a+0.01 (just outside hole), SCF should be close to 3.0
  const edge = ellipseStress(a + 0.01, 0, a, a, 0, 0, 0, 0, sigYinf, 0, mu1, mu2);
  const scfEdge = edge.sigY / sigYinf;
  console.log(`\n  SCF at hole edge: ${scfEdge.toFixed(3)} (expect ~3.0)`);
  assert(Math.abs(scfEdge - 3.0) < 0.15, `Isotropic SCF ≈ 3.0 — got ${scfEdge.toFixed(3)}`);

  // Far from hole, stress should return to far-field
  const far = ellipseStress(50, 0, a, a, 0, 0, 0, 0, sigYinf, 0, mu1, mu2);
  const scfFar = far.sigY / sigYinf;
  assert(Math.abs(scfFar - 1.0) < 0.05, `SCF → 1.0 far from hole — got ${scfFar.toFixed(3)}`);

  // At top of hole (0, a+ε), σy should be compressive: σy/σy∞ ≈ -1.0 for isotropic
  const top = ellipseStress(0, a + 0.01, a, a, 0, 0, 0, 0, sigYinf, 0, mu1, mu2);
  const scfTop = top.sigY / sigYinf;
  console.log(`  SCF at top (0, a+ε): ${scfTop.toFixed(3)} (expect ~-1.0)`);
  assert(Math.abs(scfTop - (-1.0)) < 0.15, `Top SCF ≈ -1.0 — got ${scfTop.toFixed(3)}`);
}

// ═══════════════════════════════════════════════
// TEST B: T300/5208 circular hole under σy — SCF should be ~6.75
// ═══════════════════════════════════════════════
console.log("\n═══ TEST B: T300/5208 circular hole, σy=100 MPa ═══");
{
  const T300 = { E1: 181, E2: 10.3, G12: 7.17, v12: 0.28, Xt:1500, Xc:1500, Yt:40, Yc:246, S12:68, plyThickness:0.125 };
  const [mu1, mu2] = characteristicRoots(T300);
  const a = 5.0;
  const sigYinf = 100;

  // Expected SCF from Lekhnitskii formula:
  // Kt = 1 + sqrt(2*(sqrt(E1/E2) - v12) + E1/G12)
  const expectedKt = 1 + Math.sqrt(2*(Math.sqrt(T300.E1/T300.E2) - T300.v12) + T300.E1/T300.G12);
  console.log(`  Expected SCF (formula): ${expectedKt.toFixed(2)}`);

  const edge = ellipseStress(a + 0.01, 0, a, a, 0, 0, 0, 0, sigYinf, 0, mu1, mu2);
  const scf = edge.sigY / sigYinf;
  console.log(`  Computed SCF at edge: ${scf.toFixed(2)}`);
  assert(Math.abs(scf - expectedKt) < 0.5, `Orthotropic SCF ≈ ${expectedKt.toFixed(1)} — got ${scf.toFixed(2)}`);

  // Profile along x-axis
  console.log("  Decay profile:");
  for (const dist of [0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]) {
    const x = a + dist;
    const r = ellipseStress(x, 0, a, a, 0, 0, 0, 0, sigYinf, 0, mu1, mu2);
    console.log(`    x=${x.toFixed(2)}: σy=${r.sigY.toFixed(1)} MPa (SCF=${(r.sigY/sigYinf).toFixed(2)})`);
  }
}

// ═══════════════════════════════════════════════
// TEST C: Inside hole should be zero stress
// ═══════════════════════════════════════════════
console.log("\n═══ TEST C: Stress inside hole = 0 ═══");
{
  const T300 = { E1: 181, E2: 10.3, G12: 7.17, v12: 0.28, Xt:1500, Xc:1500, Yt:40, Yc:246, S12:68, plyThickness:0.125 };
  const [mu1, mu2] = characteristicRoots(T300);
  const inside = ellipseStress(2, 1, 5, 5, 0, 0, 0, 0, 100, 0, mu1, mu2);
  console.log(`  Inside: σx=${inside.sigX}, σy=${inside.sigY}, τxy=${inside.tauXY}`);
  assert(inside.sigX === 0 && inside.sigY === 0, "Zero stress inside hole");
}

// ═══════════════════════════════════════════════
// TEST D: Elliptical hole — higher SCF expected
// ═══════════════════════════════════════════════
console.log("\n═══ TEST D: Isotropic elliptical hole (a=10, b=2), σy=100 ═══");
{
  const isoMat = { E1: 70, E2: 70, G12: 70/(2*1.3), v12: 0.3, Xt:500, Xc:500, Yt:500, Yc:500, S12:300, plyThickness:0.125 };
  const [mu1, mu2] = characteristicRoots(isoMat);
  const a = 10, b = 2;
  const sigYinf = 100;

  // For isotropic ellipse under σy, SCF at (a, 0) = 1 + 2a/b = 1 + 2*10/2 = 11
  // Wait — the formula depends on loading direction.
  // Under σy (tension perpendicular to major axis):
  // SCF at (a, 0) = 1 + 2*b/a = 1 + 2*2/10 = 1.4 ← this is for stress at END of major axis
  // SCF at (0, b) under σy = ... hmm

  // Actually for σy loading, the max stress is at the tip of the minor axis on the x-axis
  // Wait — for σy loading on an ellipse with semi-major a along x:
  // At point (a, 0): σy = σy∞ * (1 + 2b/a)
  // At point (0, b): σy depends on orientation

  // For ellipse a (along x), b (along y), under uniform σy:
  // The SCF at (a, 0) on the x-axis = 1 + 2b/a
  const expectedSCF = 1 + 2*b/a; // = 1 + 0.4 = 1.4
  console.log(`  Expected SCF at (a,0) = 1 + 2b/a = ${expectedSCF.toFixed(1)}`);

  const edge = ellipseStress(a + 0.01, 0, a, b, 0, 0, 0, 0, sigYinf, 0, mu1, mu2);
  const scf = edge.sigY / sigYinf;
  console.log(`  Computed SCF at (a+ε, 0): ${scf.toFixed(3)}`);
  assert(Math.abs(scf - expectedSCF) < 0.3, `Ellipse SCF ≈ ${expectedSCF.toFixed(1)} — got ${scf.toFixed(3)}`);

  // At (0, b+ε), SCF should be negative (compressive)
  const topEdge = ellipseStress(0, b + 0.01, a, b, 0, 0, 0, 0, sigYinf, 0, mu1, mu2);
  const scfTop = topEdge.sigY / sigYinf;
  console.log(`  SCF at (0, b+ε): ${scfTop.toFixed(3)}`);
}

// ═══════════════════════════════════════════════
// TEST E: Stress field consistency — far-field recovery
// ═══════════════════════════════════════════════
console.log("\n═══ TEST E: Far-field stress recovery ═══");
{
  const T300 = { E1: 181, E2: 10.3, G12: 7.17, v12: 0.28, Xt:1500, Xc:1500, Yt:40, Yc:246, S12:68, plyThickness:0.125 };
  const [mu1, mu2] = characteristicRoots(T300);

  // Very far from hole, stress should equal far-field exactly
  const cases = [
    { sigX: 100, sigY: 0 },
    { sigX: 0, sigY: 100 },
    { sigX: 50, sigY: 50 },
  ];

  for (const c of cases) {
    const far = ellipseStress(200, 200, 5, 5, 0, 0, 0, c.sigX, c.sigY, 0, mu1, mu2);
    console.log(`  Far-field (σx∞=${c.sigX}, σy∞=${c.sigY}): σx=${far.sigX.toFixed(2)}, σy=${far.sigY.toFixed(2)}`);
    assert(Math.abs(far.sigX - c.sigX) < 1 && Math.abs(far.sigY - c.sigY) < 1,
      `Recovery: (${c.sigX},${c.sigY}) → (${far.sigX.toFixed(1)},${far.sigY.toFixed(1)})`);
  }
}

// ═══════════════════════════════════════════════
// TEST F: σx loading — SCF at (0, b+ε) for circular hole
// ═══════════════════════════════════════════════
console.log("\n═══ TEST F: Isotropic circular hole, σx=100 MPa ═══");
{
  const isoMat = { E1: 70, E2: 70, G12: 70/(2*1.3), v12: 0.3, Xt:500, Xc:500, Yt:500, Yc:500, S12:300, plyThickness:0.125 };
  const [mu1, mu2] = characteristicRoots(isoMat);
  const a = 5;

  // Under σx loading, the SCF at (0, a+ε) should be 3.0 (by symmetry with σy case)
  const edge = ellipseStress(0, a + 0.01, a, a, 0, 0, 0, 100, 0, 0, mu1, mu2);
  const scf = edge.sigX / 100;
  console.log(`  σx loading: SCF at (0, a+ε) = ${scf.toFixed(3)} (expect ~3.0)`);
  assert(Math.abs(scf - 3.0) < 0.15, `σx SCF ≈ 3.0 — got ${scf.toFixed(3)}`);
}

// ═══════════════════════════════════════════════
console.log(`\n${"═".repeat(50)}`);
console.log(`STRESS FIELD VALIDATION: ${passed} passed, ${failed} failed out of ${passed + failed} tests`);
console.log(`${"═".repeat(50)}`);
if (failed > 0) {
  console.log("\n⚠ ISSUES detected in stress field engine!");
  process.exit(1);
} else {
  console.log("\n✓ All stress field tests passed.");
  process.exit(0);
}
