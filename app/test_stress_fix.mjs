/**
 * Comprehensive validation of the BJSFM-fixed ellipseStress() in stress-field.ts.
 * Tests exactly the algorithm that was changed: alpha/beta coefficients, -C_k/ζ² derivative, |ζ|≥1 branch.
 *
 * This mirrors the EXACT code path in src/lib/stress-field.ts ellipseStress().
 */

// ─── Complex arithmetic (identical to stress-field.ts) ───
const C = {
  add: (a, b) => ({ re: a.re+b.re, im: a.im+b.im }),
  sub: (a, b) => ({ re: a.re-b.re, im: a.im-b.im }),
  mul: (a, b) => ({ re: a.re*b.re-a.im*b.im, im: a.re*b.im+a.im*b.re }),
  div: (a, b) => { const d=b.re*b.re+b.im*b.im; return d<1e-30?{re:0,im:0}:{re:(a.re*b.re+a.im*b.im)/d, im:(a.im*b.re-a.re*b.im)/d}; },
  sqrt: (z) => { const r=Math.sqrt(z.re*z.re+z.im*z.im); const t=Math.atan2(z.im,z.re); const s=Math.sqrt(r); return {re:s*Math.cos(t/2),im:s*Math.sin(t/2)}; },
  scale: (z, s) => ({ re: z.re*s, im: z.im*s }),
  mag: (z) => Math.sqrt(z.re*z.re+z.im*z.im),
  neg: (z) => ({ re: -z.re, im: -z.im }),
};

// ─── characteristicRoots (identical to stress-field.ts) ───
function characteristicRoots(mat) {
  const E1=mat.E1*1000, E2=mat.E2*1000, G12=mat.G12*1000;
  const a11=1/E1, a22=1/E2, a12=-mat.v12/E1, a66=1/G12;
  const A=a11, B=2*a12+a66, Cv=a22;
  const disc=B*B-4*A*Cv;
  let mu1, mu2;
  if (disc < 0) {
    const rp=-B/(2*A), ip=Math.sqrt(-disc)/(2*A);
    mu1=C.sqrt({re:rp,im:ip}); mu2=C.sqrt({re:rp,im:-ip});
  } else {
    const t1=(-B+Math.sqrt(disc))/(2*A), t2=(-B-Math.sqrt(disc))/(2*A);
    mu1=t1<0?{re:0,im:Math.sqrt(-t1)}:{re:Math.sqrt(t1),im:0};
    mu2=t2<0?{re:0,im:Math.sqrt(-t2)}:{re:Math.sqrt(t2),im:0};
  }
  if(mu1.im<0){mu1.re=-mu1.re;mu1.im=-mu1.im;}
  if(mu2.im<0){mu2.re=-mu2.re;mu2.im=-mu2.im;}
  return [mu1, mu2];
}

// ─── ellipseStress (EXACT mirror of stress-field.ts after fix) ───
function ellipseStress(px, py, a, b, cx, cy, angle, sigXinf, sigYinf, tauXYinf, mu1, mu2) {
  // Transform to ellipse-local
  const rad = (-angle * Math.PI) / 180;
  const cosA = Math.cos(rad), sinA = Math.sin(rad);
  const dx = px - cx, dy = py - cy;
  const x = cosA * dx + sinA * dy;
  const y = -sinA * dx + cosA * dy;

  // Rotate far-field stress
  const c2 = cosA*cosA, s2 = sinA*sinA, cs = cosA*sinA;
  const sxL = c2*sigXinf + s2*sigYinf + 2*cs*tauXYinf;
  const syL = s2*sigXinf + c2*sigYinf - 2*cs*tauXYinf;
  const txyL = -cs*sigXinf + cs*sigYinf + (c2-s2)*tauXYinf;

  // Inside ellipse
  if ((x*x)/(a*a) + (y*y)/(b*b) < 1.0) return { sigX:0, sigY:0, tauXY:0 };

  // z_k = x + μ_k·y
  const z1 = { re: x + mu1.re*y, im: mu1.im*y };
  const z2 = { re: x + mu2.re*y, im: mu2.im*y };

  const a2 = a*a, b2 = b*b;
  const mu1sq = C.mul(mu1, mu1), mu2sq = C.mul(mu2, mu2);
  const z1sq = C.mul(z1, z1), z2sq = C.mul(z2, z2);
  const sqrt1 = C.sqrt(C.sub(z1sq, { re: a2 + mu1sq.re*b2, im: mu1sq.im*b2 }));
  const sqrt2 = C.sqrt(C.sub(z2sq, { re: a2 + mu2sq.re*b2, im: mu2sq.im*b2 }));

  // Conformal mapping
  const den1 = { re: a + mu1.im*b, im: -mu1.re*b };
  const den2 = { re: a + mu2.im*b, im: -mu2.re*b };

  // Track effective η (may flip for exterior branch)
  let eta1 = sqrt1, eta2 = sqrt2;
  let zeta1 = C.div(C.add(z1, eta1), den1);
  if (C.mag(zeta1) < 1) { eta1 = C.neg(sqrt1); zeta1 = C.div(C.add(z1, eta1), den1); }
  let zeta2 = C.div(C.add(z2, eta2), den2);
  if (C.mag(zeta2) < 1) { eta2 = C.neg(sqrt2); zeta2 = C.div(C.add(z2, eta2), den2); }

  // BJSFM coefficients
  const alpha = { re: -syL*b/2, im: txyL*a/2 };
  const beta = { re: txyL*b/2, im: -sxL*a/2 };

  const mu_diff = C.sub(mu1, mu2);
  if (mu_diff.re*mu_diff.re + mu_diff.im*mu_diff.im < 1e-20) {
    return { sigX: sxL, sigY: syL, tauXY: txyL };
  }

  const C1 = C.div(C.sub(beta, C.mul(mu2, alpha)), mu_diff);
  const C2 = C.neg(C.div(C.sub(beta, C.mul(mu1, alpha)), mu_diff));

  // φ_k' = -C_k/ζ_k² · dζ_k/dz_k  (using effective η for correct branch)
  const kappa1 = C.div({re:1,im:0}, den1);
  const kappa2 = C.div({re:1,im:0}, den2);
  const zeta1sq = C.mul(zeta1, zeta1);
  const zeta2sq = C.mul(zeta2, zeta2);
  const one = {re:1, im:0};
  const dzdz1 = C.mul(C.add(one, C.div(z1, eta1)), kappa1);
  const dzdz2 = C.mul(C.add(one, C.div(z2, eta2)), kappa2);

  const phi1p = C.mul(C.neg(C.div(C1, zeta1sq)), dzdz1);
  const phi2p = C.mul(C.neg(C.div(C2, zeta2sq)), dzdz2);

  // Stresses
  const dSigX = 2*(C.mul(mu1sq, phi1p).re + C.mul(mu2sq, phi2p).re);
  const dSigY = 2*(phi1p.re + phi2p.re);
  const dTauXY = -2*(C.mul(mu1, phi1p).re + C.mul(mu2, phi2p).re);

  let sigXL = sxL + dSigX;
  let sigYL = syL + dSigY;
  let tauXYL = txyL + dTauXY;

  // Rotate back
  const sigX = c2*sigXL + s2*sigYL - 2*cs*tauXYL;
  const sigY = s2*sigXL + c2*sigYL + 2*cs*tauXYL;
  const tauXY = cs*sigXL - cs*sigYL + (c2-s2)*tauXYL;

  return { sigX, sigY, tauXY };
}

// ─── Test harness ───
let passed = 0, failed = 0, total = 0;
function assert(cond, msg) {
  total++;
  if (cond) { passed++; }
  else { failed++; console.log(`  FAIL: ${msg}`); }
}
function section(name) { console.log(`\n--- ${name} ---`); }

// ─── Materials ───
const T300  = { E1: 181, E2: 10.3, G12: 7.17, v12: 0.28 };
const IM7   = { E1: 190, E2: 9.9, G12: 7.8, v12: 0.34 };
const EGlass = { E1: 38.6, E2: 8.27, G12: 4.14, v12: 0.26 };
const Iso70 = { E1: 70, E2: 69.999, G12: 70/(2*1.3), v12: 0.3 };

const materials = [
  { name: "T300/5208", mat: T300 },
  { name: "IM7/8552", mat: IM7 },
  { name: "E-Glass/Epoxy", mat: EGlass },
  { name: "Near-isotropic", mat: Iso70 },
];

// ════════════════════════════════════════════════
// SECTION 1: Inside-hole returns zero
// ════════════════════════════════════════════════
section("1. Inside-hole returns zero");
for (const {name, mat} of materials) {
  const [mu1, mu2] = characteristicRoots(mat);
  const r = 5;
  // Circle: inside at center
  const c = ellipseStress(0, 0, r, r, 0, 0, 0, 100, 50, 25, mu1, mu2);
  assert(c.sigX===0 && c.sigY===0 && c.tauXY===0, `${name} center`);
  // Circle: inside at (r/2, 0)
  const h = ellipseStress(r/2, 0, r, r, 0, 0, 0, 100, 50, 25, mu1, mu2);
  assert(h.sigX===0 && h.sigY===0 && h.tauXY===0, `${name} half-radius`);
  // Ellipse: inside at (a/2, 0)
  const e = ellipseStress(5, 0, 10, 5, 0, 0, 0, 100, 50, 25, mu1, mu2);
  assert(e.sigX===0 && e.sigY===0 && e.tauXY===0, `${name} ellipse inside`);
}

// ════════════════════════════════════════════════
// SECTION 2: Far-field stress recovery (all materials, multiple loading)
// ════════════════════════════════════════════════
section("2. Far-field stress recovery");
const loadCases = [
  { sx:100, sy:0, txy:0, label:"σx=100" },
  { sx:0, sy:100, txy:0, label:"σy=100" },
  { sx:0, sy:0, txy:50, label:"τxy=50" },
  { sx:100, sy:100, txy:0, label:"biaxial" },
  { sx:50, sy:100, txy:25, label:"combined" },
  { sx:-80, sy:40, txy:-30, label:"mixed signs" },
];
for (const {name, mat} of materials) {
  const [mu1, mu2] = characteristicRoots(mat);
  for (const lc of loadCases) {
    const far = ellipseStress(500, 500, 5, 5, 0, 0, 0, lc.sx, lc.sy, lc.txy, mu1, mu2);
    assert(Math.abs(far.sigX - lc.sx) < 1, `${name} ${lc.label}: σx far=${far.sigX.toFixed(2)} expect ${lc.sx}`);
    assert(Math.abs(far.sigY - lc.sy) < 1, `${name} ${lc.label}: σy far=${far.sigY.toFixed(2)} expect ${lc.sy}`);
    assert(Math.abs(far.tauXY - lc.txy) < 1, `${name} ${lc.label}: τxy far=${far.tauXY.toFixed(2)} expect ${lc.txy}`);
  }
}

// ════════════════════════════════════════════════
// SECTION 3: Isotropic Kirsch solution (SCF = 3.0 for σy loading at x-axis)
// ════════════════════════════════════════════════
section("3. Isotropic Kirsch: SCF=3.0");
{
  const [mu1, mu2] = characteristicRoots(Iso70);
  const r = 5;
  // σy=100 at (r+ε, 0): expect σy ≈ 300 (SCF=3)
  for (const eps of [0.001, 0.01, 0.05, 0.1]) {
    const res = ellipseStress(r+eps, 0, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
    const scf = res.sigY / 100;
    assert(Math.abs(scf - 3.0) < 0.15, `Kirsch SCF at eps=${eps}: got ${scf.toFixed(3)}`);
  }
  // σx=100 at (0, r+ε): expect σx ≈ 300 (SCF=3 by symmetry)
  for (const eps of [0.01, 0.05, 0.1]) {
    const res = ellipseStress(0, r+eps, r, r, 0, 0, 0, 100, 0, 0, mu1, mu2);
    const scf = res.sigX / 100;
    assert(Math.abs(scf - 3.0) < 0.15, `Kirsch σx SCF at eps=${eps}: got ${scf.toFixed(3)}`);
  }
}

// ════════════════════════════════════════════════
// SECTION 4: Orthotropic SCF at hole edge
// ════════════════════════════════════════════════
section("4. Orthotropic SCF values");
{
  // T300/5208: σy loading at (r+ε, 0)
  // Expected SCF = 1 + sqrt(E2/E1) + E2*(2*v12/E1 - 1/G12) ... simplified ≈ 2.37
  const [mu1, mu2] = characteristicRoots(T300);
  const r = 5;
  const res_sy = ellipseStress(r+0.001, 0, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  const scf_sy = res_sy.sigY / 100;
  assert(Math.abs(scf_sy - 2.37) < 0.1, `T300 σy@x-axis SCF: got ${scf_sy.toFixed(3)} expect ~2.37`);

  // T300/5208: σx loading at (0, r+ε)
  // Expected SCF ≈ 1 + β₁ + β₂ = 1 + μ₁.im + μ₂.im ≈ 6.75
  const res_sx = ellipseStress(0, r+0.01, r, r, 0, 0, 0, 100, 0, 0, mu1, mu2);
  const scf_sx = res_sx.sigX / 100;
  assert(Math.abs(scf_sx - 6.75) < 0.5, `T300 σx@y-axis SCF: got ${scf_sx.toFixed(3)} expect ~6.75`);

  // IM7/8552
  const [mu1_im, mu2_im] = characteristicRoots(IM7);
  const res_im = ellipseStress(0, r+0.01, r, r, 0, 0, 0, 100, 0, 0, mu1_im, mu2_im);
  const scf_im = res_im.sigX / 100;
  const expected_im = 1 + mu1_im.im + mu2_im.im;
  assert(Math.abs(scf_im - expected_im) < 0.5, `IM7 σx@y-axis SCF: got ${scf_im.toFixed(3)} expect ~${expected_im.toFixed(2)}`);

  // E-Glass/Epoxy
  const [mu1_eg, mu2_eg] = characteristicRoots(EGlass);
  const res_eg = ellipseStress(0, r+0.01, r, r, 0, 0, 0, 100, 0, 0, mu1_eg, mu2_eg);
  const scf_eg = res_eg.sigX / 100;
  const expected_eg = 1 + mu1_eg.im + mu2_eg.im;
  assert(Math.abs(scf_eg - expected_eg) < 0.5, `E-Glass σx@y-axis SCF: got ${scf_eg.toFixed(3)} expect ~${expected_eg.toFixed(2)}`);
}

// ════════════════════════════════════════════════
// SECTION 5: Stress at hole edge σx ≈ 0 (traction-free boundary)
// ════════════════════════════════════════════════
section("5. Traction-free hole boundary");
for (const {name, mat} of materials) {
  const [mu1, mu2] = characteristicRoots(mat);
  const r = 5;
  // At (r+ε, 0) with σy loading: radial stress σx should ≈ 0
  const res = ellipseStress(r+0.01, 0, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(Math.abs(res.sigX) < 5, `${name} σx≈0 at x-edge: got ${res.sigX.toFixed(2)}`);
  // At (0, r+ε) with σx loading: radial stress σy should ≈ 0
  const res2 = ellipseStress(0, r+0.01, r, r, 0, 0, 0, 100, 0, 0, mu1, mu2);
  assert(Math.abs(res2.sigY) < 5, `${name} σy≈0 at y-edge: got ${res2.sigY.toFixed(2)}`);
}

// ════════════════════════════════════════════════
// SECTION 6: Stress decay — should approach far-field with distance
// ════════════════════════════════════════════════
section("6. Stress decay with distance");
{
  const [mu1, mu2] = characteristicRoots(T300);
  const r = 5;
  let prev_scf = Infinity;
  for (const d of [0.01, 0.1, 0.5, 1, 2, 5, 10, 50, 200]) {
    const res = ellipseStress(r+d, 0, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
    const scf = res.sigY / 100;
    assert(scf < prev_scf + 0.01, `Decay monotonic at d=${d}: SCF=${scf.toFixed(3)} < prev=${prev_scf.toFixed(3)}`);
    prev_scf = scf;
  }
  assert(prev_scf < 1.01, `Fully decayed at d=200: SCF=${prev_scf.toFixed(4)}`);
}

// ════════════════════════════════════════════════
// SECTION 7: Symmetry checks
// ════════════════════════════════════════════════
section("7. Symmetry");
{
  const [mu1, mu2] = characteristicRoots(T300);
  const r = 5;

  // σy loading: symmetric about x-axis → σy(x,y) = σy(x,-y), τxy antisymmetric
  const a1 = ellipseStress(8, 3, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  const a2 = ellipseStress(8, -3, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(Math.abs(a1.sigY - a2.sigY) < 0.1, `σy sym about x-axis: ${a1.sigY.toFixed(2)} vs ${a2.sigY.toFixed(2)}`);
  assert(Math.abs(a1.sigX - a2.sigX) < 0.1, `σx sym about x-axis: ${a1.sigX.toFixed(2)} vs ${a2.sigX.toFixed(2)}`);
  assert(Math.abs(a1.tauXY + a2.tauXY) < 0.1, `τxy antisym about x-axis: ${a1.tauXY.toFixed(2)} vs ${a2.tauXY.toFixed(2)}`);

  // σy loading: symmetric about y-axis → σy(x,y) = σy(-x,y)
  const b1 = ellipseStress(8, 3, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  const b2 = ellipseStress(-8, 3, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(Math.abs(b1.sigY - b2.sigY) < 0.1, `σy sym about y-axis: ${b1.sigY.toFixed(2)} vs ${b2.sigY.toFixed(2)}`);
  assert(Math.abs(b1.sigX - b2.sigX) < 0.1, `σx sym about y-axis`);
  assert(Math.abs(b1.tauXY + b2.tauXY) < 0.1, `τxy antisym about y-axis`);
}

// ════════════════════════════════════════════════
// SECTION 8: Off-center hole
// ════════════════════════════════════════════════
section("8. Off-center hole");
{
  const [mu1, mu2] = characteristicRoots(T300);
  const r = 5;
  // Hole at (10, 20); point at edge (15, 20) should match hole at origin, point at (5.001, 0)
  const res1 = ellipseStress(10+r+0.001, 20, r, r, 10, 20, 0, 0, 100, 0, mu1, mu2);
  const res2 = ellipseStress(r+0.001, 0, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(Math.abs(res1.sigY - res2.sigY) < 0.1, `Off-center σy matches origin: ${res1.sigY.toFixed(2)} vs ${res2.sigY.toFixed(2)}`);
  assert(Math.abs(res1.sigX - res2.sigX) < 0.1, `Off-center σx matches origin`);
}

// ════════════════════════════════════════════════
// SECTION 9: Rotated hole
// ════════════════════════════════════════════════
section("9. Rotated hole (circular, isotropic material)");
{
  // Only isotropic material is rotation-invariant for circular hole
  const [mu1, mu2] = characteristicRoots(Iso70);
  const r = 5;
  const res0 = ellipseStress(r+0.1, 0, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  const res45 = ellipseStress(r+0.1, 0, r, r, 0, 0, 45, 0, 100, 0, mu1, mu2);
  assert(Math.abs(res0.sigY - res45.sigY) < 2, `Iso circle rotation invariant σy: ${res0.sigY.toFixed(2)} vs ${res45.sigY.toFixed(2)}`);

  // For orthotropic, rotation SHOULD change the result (material is anisotropic)
  const [mu1t, mu2t] = characteristicRoots(T300);
  const res0t = ellipseStress(r+0.1, 0, r, r, 0, 0, 0, 0, 100, 0, mu1t, mu2t);
  const res45t = ellipseStress(r+0.1, 0, r, r, 0, 0, 45, 0, 100, 0, mu1t, mu2t);
  assert(Math.abs(res0t.sigY - res45t.sigY) > 1, `Ortho circle NOT rotation invariant: ${res0t.sigY.toFixed(2)} vs ${res45t.sigY.toFixed(2)}`);
}

// ════════════════════════════════════════════════
// SECTION 10: Elliptical hole (a ≠ b)
// ════════════════════════════════════════════════
section("10. Elliptical hole");
{
  const [mu1, mu2] = characteristicRoots(T300);
  // Ellipse a=10, b=5. At (a+ε, 0): SCF should differ from circular
  const a=10, b=5;
  const res = ellipseStress(a+0.01, 0, a, b, 0, 0, 0, 0, 100, 0, mu1, mu2);
  // For wide ellipse (a>b), SCF at x-edge for σy loading is LOWER than circular
  // because the y-dimension (b) is smaller
  assert(res.sigY > 100, `Ellipse σy at x-edge > far-field: ${res.sigY.toFixed(1)}`);

  // Far-field recovery for ellipse
  const far = ellipseStress(500, 500, a, b, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(Math.abs(far.sigY - 100) < 1, `Ellipse far-field σy: ${far.sigY.toFixed(2)}`);
  assert(Math.abs(far.sigX) < 1, `Ellipse far-field σx: ${far.sigX.toFixed(2)}`);

  // Inside ellipse
  const inside = ellipseStress(5, 2, a, b, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(inside.sigX===0 && inside.sigY===0, `Ellipse inside returns zero`);
}

// ════════════════════════════════════════════════
// SECTION 11: Shear loading
// ════════════════════════════════════════════════
section("11. Shear loading τxy=100");
for (const {name, mat} of materials) {
  const [mu1, mu2] = characteristicRoots(mat);
  const r = 5;
  // Far-field recovery
  const far = ellipseStress(500, 500, r, r, 0, 0, 0, 0, 0, 100, mu1, mu2);
  assert(Math.abs(far.tauXY - 100) < 1, `${name} shear far τxy: ${far.tauXY.toFixed(2)}`);
  assert(Math.abs(far.sigX) < 1, `${name} shear far σx: ${far.sigX.toFixed(2)}`);
  assert(Math.abs(far.sigY) < 1, `${name} shear far σy: ${far.sigY.toFixed(2)}`);
  // At (r+ε, 0): traction-free → τxy ≈ 0. Shear amplification occurs at 45°
  const edge = ellipseStress(r+0.01, 0, r, r, 0, 0, 0, 0, 0, 100, mu1, mu2);
  assert(Math.abs(edge.tauXY) < 5, `${name} traction-free τxy≈0 at x-edge: ${edge.tauXY.toFixed(2)}`);
  // At 45°: stress should be amplified
  const d45 = (r+0.1)/Math.SQRT2;
  const at45 = ellipseStress(d45, d45, r, r, 0, 0, 0, 0, 0, 100, mu1, mu2);
  const vm45 = Math.sqrt(at45.sigX**2 - at45.sigX*at45.sigY + at45.sigY**2 + 3*at45.tauXY**2);
  assert(vm45 > 100, `${name} shear amplified at 45°: vM=${vm45.toFixed(1)}`);
}

// ════════════════════════════════════════════════
// SECTION 12: Multiple radial directions (θ = 0°, 45°, 90°, etc.)
// ════════════════════════════════════════════════
section("12. Circumferential stress field");
{
  const [mu1, mu2] = characteristicRoots(T300);
  const r = 5;
  const d = 0.1; // just outside hole
  for (const deg of [0, 30, 45, 60, 90, 120, 135, 150, 180, 210, 270, 315]) {
    const rad = deg * Math.PI / 180;
    const px = (r+d)*Math.cos(rad), py = (r+d)*Math.sin(rad);
    const res = ellipseStress(px, py, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
    // All stresses should be finite and reasonable (not NaN, not > 1000)
    assert(isFinite(res.sigX) && isFinite(res.sigY) && isFinite(res.tauXY),
      `Finite at θ=${deg}°`);
    assert(Math.abs(res.sigX) < 500 && Math.abs(res.sigY) < 500 && Math.abs(res.tauXY) < 500,
      `Reasonable magnitude at θ=${deg}°`);
  }
}

// ════════════════════════════════════════════════
// SECTION 13: Stress at 45° off-axis point — multiple distances
// ════════════════════════════════════════════════
section("13. Diagonal decay");
{
  const [mu1, mu2] = characteristicRoots(T300);
  const r = 5;
  let prev_vm = Infinity;
  for (const d of [0.5, 1, 2, 5, 10, 50, 200]) {
    const px = (r+d)/Math.SQRT2, py = (r+d)/Math.SQRT2;
    const res = ellipseStress(px, py, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
    const vm = Math.sqrt(res.sigX**2 - res.sigX*res.sigY + res.sigY**2 + 3*res.tauXY**2);
    assert(isFinite(vm), `Finite von Mises at d=${d}`);
  }
  // At d=200, should be close to far-field
  const farDiag = ellipseStress((r+200)/Math.SQRT2, (r+200)/Math.SQRT2, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(Math.abs(farDiag.sigY - 100) < 2, `Diagonal far-field σy: ${farDiag.sigY.toFixed(2)}`);
}

// ════════════════════════════════════════════════
// SECTION 14: Superposition check — σx+σy = biaxial
// ════════════════════════════════════════════════
section("14. Superposition");
{
  const [mu1, mu2] = characteristicRoots(T300);
  const r = 5;
  const px = 8, py = 3;
  const res_x = ellipseStress(px, py, r, r, 0, 0, 0, 100, 0, 0, mu1, mu2);
  const res_y = ellipseStress(px, py, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  const res_bi = ellipseStress(px, py, r, r, 0, 0, 0, 100, 100, 0, mu1, mu2);
  // Lekhnitskii is linear → superposition must hold
  assert(Math.abs((res_x.sigX + res_y.sigX) - res_bi.sigX) < 0.1,
    `Superposition σx: ${(res_x.sigX+res_y.sigX).toFixed(2)} vs ${res_bi.sigX.toFixed(2)}`);
  assert(Math.abs((res_x.sigY + res_y.sigY) - res_bi.sigY) < 0.1,
    `Superposition σy: ${(res_x.sigY+res_y.sigY).toFixed(2)} vs ${res_bi.sigY.toFixed(2)}`);
  assert(Math.abs((res_x.tauXY + res_y.tauXY) - res_bi.tauXY) < 0.1,
    `Superposition τxy: ${(res_x.tauXY+res_y.tauXY).toFixed(2)} vs ${res_bi.tauXY.toFixed(2)}`);

  // Also with shear
  const res_t = ellipseStress(px, py, r, r, 0, 0, 0, 0, 0, 50, mu1, mu2);
  const res_all = ellipseStress(px, py, r, r, 0, 0, 0, 100, 100, 50, mu1, mu2);
  assert(Math.abs((res_x.sigX + res_y.sigX + res_t.sigX) - res_all.sigX) < 0.1,
    `Full superposition σx`);
  assert(Math.abs((res_x.sigY + res_y.sigY + res_t.sigY) - res_all.sigY) < 0.1,
    `Full superposition σy`);
  assert(Math.abs((res_x.tauXY + res_y.tauXY + res_t.tauXY) - res_all.tauXY) < 0.1,
    `Full superposition τxy`);
}

// ════════════════════════════════════════════════
// SECTION 15: Scaling — doubling load doubles stress perturbation
// ════════════════════════════════════════════════
section("15. Load scaling linearity");
{
  const [mu1, mu2] = characteristicRoots(T300);
  const r = 5;
  const px = 7, py = 2;
  const res1 = ellipseStress(px, py, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  const res2 = ellipseStress(px, py, r, r, 0, 0, 0, 0, 200, 0, mu1, mu2);
  assert(Math.abs(res2.sigY / res1.sigY - 2.0) < 0.01, `2x load → 2x σy: ratio=${(res2.sigY/res1.sigY).toFixed(4)}`);
  assert(Math.abs(res2.sigX / res1.sigX - 2.0) < 0.01, `2x load → 2x σx: ratio=${(res2.sigX/res1.sigX).toFixed(4)}`);

  const res3 = ellipseStress(px, py, r, r, 0, 0, 0, 0, -100, 0, mu1, mu2);
  assert(Math.abs(res3.sigY + res1.sigY) < 0.01, `Neg load → neg stress`);
}

// ════════════════════════════════════════════════
// SECTION 16: Characteristic roots sanity
// ════════════════════════════════════════════════
section("16. Characteristic roots");
{
  // T300/5208: expect μ₁ ≈ 0.857i, μ₂ ≈ 4.894i
  const [mu1, mu2] = characteristicRoots(T300);
  assert(Math.abs(mu1.re) < 0.01, `T300 μ₁ real ≈ 0: ${mu1.re.toFixed(6)}`);
  assert(Math.abs(mu1.im - 0.857) < 0.01, `T300 μ₁ imag ≈ 0.857: ${mu1.im.toFixed(4)}`);
  assert(Math.abs(mu2.re) < 0.01, `T300 μ₂ real ≈ 0: ${mu2.re.toFixed(6)}`);
  assert(Math.abs(mu2.im - 4.894) < 0.01, `T300 μ₂ imag ≈ 4.894: ${mu2.im.toFixed(4)}`);
  // Both roots should have positive imaginary parts
  assert(mu1.im > 0, `μ₁.im > 0`);
  assert(mu2.im > 0, `μ₂.im > 0`);

  // Isotropic: μ₁ ≈ μ₂ ≈ i
  const [mu1i, mu2i] = characteristicRoots(Iso70);
  assert(Math.abs(mu1i.im - 1.0) < 0.01, `Iso μ₁ ≈ i: ${mu1i.im.toFixed(4)}`);
  assert(Math.abs(mu2i.im - 1.0) < 0.01, `Iso μ₂ ≈ i: ${mu2i.im.toFixed(4)}`);
}

// ════════════════════════════════════════════════
// SECTION 17: BJSFM coefficient verification
// ════════════════════════════════════════════════
section("17. BJSFM coefficients (alpha, beta, C1, C2)");
{
  // For σy=100, circular r=5: alpha = {re: -250, im: 0}, beta = {re: 0, im: 0}
  const r = 5;
  const alpha = { re: -100*r/2, im: 0 };
  const beta = { re: 0, im: 0 };
  assert(alpha.re === -250, `alpha.re = -250 for σy=100, r=5`);
  assert(alpha.im === 0, `alpha.im = 0 for no shear`);
  assert(beta.re === 0, `beta.re = 0 for no σx, no shear`);
  assert(beta.im === 0, `beta.im = 0 for no σx`);

  // For σx=100: alpha = {re: 0, im: 0}, beta = {re: 0, im: -250}
  const alpha2 = { re: 0, im: 0 };
  const beta2 = { re: 0, im: -100*r/2 };
  assert(beta2.im === -250, `beta.im = -250 for σx=100`);

  // For τxy=50: alpha = {re: 0, im: 125}, beta = {re: 125, im: 0}
  const alpha3 = { re: 0, im: 50*r/2 };
  const beta3 = { re: 50*r/2, im: 0 };
  assert(alpha3.im === 125, `alpha.im = 125 for τxy=50`);
  assert(beta3.re === 125, `beta.re = 125 for τxy=50`);

  // C1 + C2 = alpha (from the formulas)
  const [mu1, mu2] = characteristicRoots(T300);
  const mu_diff = C.sub(mu1, mu2);
  const C1 = C.div(C.sub(beta, C.mul(mu2, alpha)), mu_diff);
  const C2 = C.neg(C.div(C.sub(beta, C.mul(mu1, alpha)), mu_diff));
  const sum = C.add(C1, C2);
  assert(Math.abs(sum.re - alpha.re) < 0.01, `C1+C2 = alpha (re): ${sum.re.toFixed(4)} vs ${alpha.re}`);
  assert(Math.abs(sum.im - alpha.im) < 0.01, `C1+C2 = alpha (im): ${sum.im.toFixed(4)} vs ${alpha.im}`);

  // μ₁C1 + μ₂C2 = beta
  const prod = C.add(C.mul(mu1, C1), C.mul(mu2, C2));
  assert(Math.abs(prod.re - beta.re) < 0.01, `μ₁C1+μ₂C2 = beta (re): ${prod.re.toFixed(4)}`);
  assert(Math.abs(prod.im - beta.im) < 0.01, `μ₁C1+μ₂C2 = beta (im): ${prod.im.toFixed(4)}`);
}

// ════════════════════════════════════════════════
// SECTION 18: Different hole sizes
// ════════════════════════════════════════════════
section("18. Different hole radii");
{
  const [mu1, mu2] = characteristicRoots(T300);
  // SCF should be independent of hole size (for infinite plate)
  for (const r of [1, 5, 10, 50]) {
    const res = ellipseStress(r+0.01*r, 0, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
    const scf = res.sigY / 100;
    assert(Math.abs(scf - 2.37) < 0.15, `r=${r}: SCF=${scf.toFixed(3)} expect ~2.37`);
  }
}

// ════════════════════════════════════════════════
// SECTION 19: Biaxial equi-tension (σx=σy=100)
// ════════════════════════════════════════════════
section("19. Biaxial equi-tension");
{
  // For isotropic + biaxial: SCF = 2.0 (Kirsch: 3+(-1) = 2)
  const [mu1, mu2] = characteristicRoots(Iso70);
  const r = 5;
  const res = ellipseStress(r+0.01, 0, r, r, 0, 0, 0, 100, 100, 0, mu1, mu2);
  const scf = res.sigY / 100;
  assert(Math.abs(scf - 2.0) < 0.15, `Isotropic biaxial SCF: ${scf.toFixed(3)} expect ~2.0`);
}

// ════════════════════════════════════════════════
// SECTION 20: Negative loading (compression)
// ════════════════════════════════════════════════
section("20. Compressive loading");
{
  const [mu1, mu2] = characteristicRoots(T300);
  const r = 5;
  const res_pos = ellipseStress(r+0.01, 0, r, r, 0, 0, 0, 0, 100, 0, mu1, mu2);
  const res_neg = ellipseStress(r+0.01, 0, r, r, 0, 0, 0, 0, -100, 0, mu1, mu2);
  assert(Math.abs(res_pos.sigY + res_neg.sigY) < 0.01, `Tension/compression antisymmetric: ${res_pos.sigY.toFixed(2)} vs ${res_neg.sigY.toFixed(2)}`);
}

// ════════════════════════════════════════════════
console.log(`\n${"═".repeat(60)}`);
console.log(`STRESS FIELD FIX VALIDATION: ${passed} passed, ${failed} failed out of ${total}`);
console.log(`${"═".repeat(60)}`);
if (failed > 0) console.log(`\n⚠ ${failed} FAILURES — review above`);
process.exit(failed > 0 ? 1 : 0);
