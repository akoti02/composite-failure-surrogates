/**
 * Step-by-step debug of orthotropic case.
 * T300/5208, circular hole a=b=5, σy∞=100 MPa, point at (5.01, 0)
 * Expected SCF ≈ 6.75
 */

const C = {
  add: (a, b) => ({ re: a.re+b.re, im: a.im+b.im }),
  sub: (a, b) => ({ re: a.re-b.re, im: a.im-b.im }),
  mul: (a, b) => ({ re: a.re*b.re-a.im*b.im, im: a.re*b.im+a.im*b.re }),
  div: (a, b) => { const d=b.re*b.re+b.im*b.im; return {re:(a.re*b.re+a.im*b.im)/d, im:(a.im*b.re-a.re*b.im)/d}; },
  sqrt: (z) => { const r=Math.sqrt(z.re*z.re+z.im*z.im); const t=Math.atan2(z.im,z.re); const s=Math.sqrt(r); return {re:s*Math.cos(t/2),im:s*Math.sin(t/2)}; },
  scale: (z, s) => ({ re: z.re*s, im: z.im*s }),
  mag: (z) => Math.sqrt(z.re*z.re+z.im*z.im),
  str: (z) => `(${z.re.toFixed(6)}, ${z.im.toFixed(6)}i)`,
};

// T300/5208 characteristic roots (already verified: μ₁=0.857i, μ₂=4.894i)
const T300 = { E1: 181, E2: 10.3, G12: 7.17, v12: 0.28 };
const E1=T300.E1*1000, E2=T300.E2*1000, G12=T300.G12*1000;
const a11=1/E1, a22=1/E2, a12=-T300.v12/E1, a66=1/G12;
const Ac=a11, Bc=2*a12+a66, Cc=a22;
const disc=Bc*Bc-4*Ac*Cc;
const t1=(-Bc+Math.sqrt(disc))/(2*Ac);
const t2=(-Bc-Math.sqrt(disc))/(2*Ac);
const mu1 = t1<0 ? {re:0,im:Math.sqrt(-t1)} : {re:Math.sqrt(t1),im:0};
const mu2 = t2<0 ? {re:0,im:Math.sqrt(-t2)} : {re:Math.sqrt(t2),im:0};
console.log(`μ₁ = ${C.str(mu1)}`);
console.log(`μ₂ = ${C.str(mu2)}`);
console.log(`μ₁-μ₂ = ${C.str(C.sub(mu1,mu2))}`);

const a = 5, b = 5; // circular hole
const syL = 100, sxL = 0, txyL = 0;

// Point just outside hole edge: (5.5, 0)
const x = 5.5, y = 0;

console.log(`\nPoint: (${x}, ${y})`);

// z_k = x + μ_k·y
const z1 = { re: x + mu1.re*y, im: mu1.im*y };
const z2 = { re: x + mu2.re*y, im: mu2.im*y };
console.log(`z₁ = ${C.str(z1)}`);
console.log(`z₂ = ${C.str(z2)}`);

// For y=0: z₁ = z₂ = x (real)
// ζ_k = [z_k + √(z_k² - a² - μ_k²b²)] / (a - iμ_kb)

const mu1sq = C.mul(mu1, mu1);
const mu2sq = C.mul(mu2, mu2);
console.log(`μ₁² = ${C.str(mu1sq)}`);
console.log(`μ₂² = ${C.str(mu2sq)}`);

// z_k² - a² - μ_k²·b²
// For y=0: z_k = x, so z_k² = x² (real)
// μ₁² = -(0.857)² = -0.734  (pure negative real for pure imaginary μ)
// So inner₁ = x² - 25 - (-0.734)*25 = x² - 25 + 18.35 = x² - 6.65
// For x=5.5: inner₁ = 30.25 - 6.65 = 23.6 → √inner₁ = 4.86

const inner1_val = x*x - a*a - mu1sq.re*b*b;
const inner2_val = x*x - a*a - mu2sq.re*b*b;
console.log(`\ninner₁ = x²-a²-μ₁²b² = ${x*x} - ${a*a} - ${(mu1sq.re*b*b).toFixed(4)} = ${inner1_val.toFixed(4)} (im: ${(-mu1sq.im*b*b).toFixed(4)})`);
console.log(`inner₂ = x²-a²-μ₂²b² = ${x*x} - ${a*a} - ${(mu2sq.re*b*b).toFixed(4)} = ${inner2_val.toFixed(4)} (im: ${(-mu2sq.im*b*b).toFixed(4)})`);

const inner1 = { re: x*x - a*a - mu1sq.re*b*b, im: -mu1sq.im*b*b };
const inner2 = { re: x*x - a*a - mu2sq.re*b*b, im: -mu2sq.im*b*b };
const sqrt1 = C.sqrt(inner1);
const sqrt2 = C.sqrt(inner2);
console.log(`√inner₁ = ${C.str(sqrt1)}`);
console.log(`√inner₂ = ${C.str(sqrt2)}`);

// den_k = a - iμ_kb = a + μ_k.im·b - i·μ_k.re·b
const den1 = { re: a + mu1.im*b, im: -mu1.re*b };
const den2 = { re: a + mu2.im*b, im: -mu2.re*b };
console.log(`\nden₁ = a-iμ₁b = ${C.str(den1)}`);
console.log(`den₂ = a-iμ₂b = ${C.str(den2)}`);

const zeta1 = C.div(C.add(z1, sqrt1), den1);
const zeta2 = C.div(C.add(z2, sqrt2), den2);
console.log(`ζ₁ = ${C.str(zeta1)}, |ζ₁|=${C.mag(zeta1).toFixed(4)}`);
console.log(`ζ₂ = ${C.str(zeta2)}, |ζ₂|=${C.mag(zeta2).toFixed(4)}`);

// Check |ζ| > 1
let z1F = zeta1, z2F = zeta2;
if (C.mag(zeta1) < 1) {
  z1F = C.div(C.sub(z1, sqrt1), den1);
  console.log(`  → Flipped ζ₁ = ${C.str(z1F)}, |ζ₁|=${C.mag(z1F).toFixed(4)}`);
}
if (C.mag(zeta2) < 1) {
  z2F = C.div(C.sub(z2, sqrt2), den2);
  console.log(`  → Flipped ζ₂ = ${C.str(z2F)}, |ζ₂|=${C.mag(z2F).toFixed(4)}`);
}

// B coefficients
// B₁ = [(i·σx·b + τxy·a) + μ₂·(σy·a - i·τxy·b)] / (2(μ₁ - μ₂))
// For our case: σx=0, τxy=0, σy=100
// term1 = i·0·5 + 0·5 = 0
// term2 = 100·5 - i·0·5 = 500
// B₁ = [0 + μ₂·500] / (2(μ₁-μ₂))
// B₂ = -[0 + μ₁·500] / (2(μ₁-μ₂))
const mu_diff = C.sub(mu1, mu2);

const term1 = { re: txyL*a, im: sxL*b };
const term2 = { re: syL*a, im: -txyL*b };
console.log(`\nterm1 = ${C.str(term1)}`);
console.log(`term2 = ${C.str(term2)}`);

const B1_num = C.add(term1, C.mul(mu2, term2));
const B2_num = C.add(term1, C.mul(mu1, term2));
console.log(`B₁ numerator = ${C.str(B1_num)}`);
console.log(`B₂ numerator = ${C.str(B2_num)}`);

const denom_2mu = C.scale(mu_diff, 2);
console.log(`2(μ₁-μ₂) = ${C.str(denom_2mu)}`);

const B1 = C.div(B1_num, denom_2mu);
const B2 = C.div(C.scale(B2_num, -1), denom_2mu);
console.log(`B₁ = ${C.str(B1)}`);
console.log(`B₂ = ${C.str(B2)}`);

// Verify boundary conditions:
// B₁ + B₂ should = -(σy·a)/2 = -250
// μ₁B₁ + μ₂B₂ should = (i·σx·b)/2 = 0
const sumB = C.add(B1, B2);
const muB = C.add(C.mul(mu1, B1), C.mul(mu2, B2));
console.log(`\nBC check: B₁+B₂ = ${C.str(sumB)} (expect -250 + 0i)`);
console.log(`BC check: μ₁B₁+μ₂B₂ = ${C.str(muB)} (expect 0 + 0i)`);

// φ_k' = -B_k · ζ_k⁻² · dζ_k/dz_k
// dζ_k/dz_k = 1/(dz_k/dζ_k)
// dz_k/dζ_k = (a-iμ_kb)/2 · (1 - [(a+iμ_kb)/(a-iμ_kb)]·ζ_k⁻²)
// = (a-iμ_kb)/2 - (a+iμ_kb)/2 · ζ_k⁻²

const alpha1 = C.scale(den1, 0.5);
const beta1 = { re: (a - mu1.im*b)/2, im: (mu1.re*b)/2 };
const alpha2 = C.scale(den2, 0.5);
const beta2 = { re: (a - mu2.im*b)/2, im: (mu2.re*b)/2 };

const z1inv = C.div({re:1,im:0}, z1F);
const z2inv = C.div({re:1,im:0}, z2F);
const z1inv2 = C.mul(z1inv, z1inv);
const z2inv2 = C.mul(z2inv, z2inv);

const dz1_dz = C.sub(alpha1, C.mul(beta1, z1inv2));
const dz2_dz = C.sub(alpha2, C.mul(beta2, z2inv2));
const dzeta1_dz1 = C.div({re:1,im:0}, dz1_dz);
const dzeta2_dz2 = C.div({re:1,im:0}, dz2_dz);

console.log(`\ndζ₁/dz₁ = ${C.str(dzeta1_dz1)}`);
console.log(`dζ₂/dz₂ = ${C.str(dzeta2_dz2)}`);

const phi1_prime = C.mul(C.scale(B1, -1), C.mul(z1inv2, dzeta1_dz1));
const phi2_prime = C.mul(C.scale(B2, -1), C.mul(z2inv2, dzeta2_dz2));
console.log(`φ₁' = ${C.str(phi1_prime)}`);
console.log(`φ₂' = ${C.str(phi2_prime)}`);

// Perturbation stresses
const dSigX = 2 * (C.mul(mu1sq, phi1_prime).re + C.mul(mu2sq, phi2_prime).re);
const dSigY = 2 * (phi1_prime.re + phi2_prime.re);
const dTauXY = -2 * (C.mul(mu1, phi1_prime).re + C.mul(mu2, phi2_prime).re);

console.log(`\nΔσx = ${dSigX.toFixed(4)}`);
console.log(`Δσy = ${dSigY.toFixed(4)}`);
console.log(`Δτxy = ${dTauXY.toFixed(4)}`);

const totalSigY = syL + dSigY;
console.log(`\nTotal σy = ${syL} + ${dSigY.toFixed(4)} = ${totalSigY.toFixed(4)}`);
console.log(`SCF = ${(totalSigY/syL).toFixed(4)} (expect ~6.75)`);

// ═══════════════════════════════════════
// Let me also verify analytically.
// For σy loading on circular hole (a=b), the SCF at (a, 0) is:
//   σy(a,0)/σy∞ = 1 + μ₁·μ₂ + (μ₁+μ₂)²/(μ₁·μ₂)   ... no
//
// The correct Lekhnitskii formula for SCF at the waist:
//   K = 1 + Re[-μ₁μ₂(a/b) + (μ₁+μ₂)] for σy loading at (a,0)
//   = 1 + Re[-(0.857i)(4.894i) + (0.857i + 4.894i)]
//   = 1 + Re[4.193 + 5.751i]
//   = 1 + 4.193 = 5.193 ← hmm, that's not 6.75 either...
//
// Wait, the correct formula from Lekhnitskii (eq. 38.13):
// For circular hole (a=b=R) under σy∞:
//   σy at (R,0) = σy∞ · (1 - μ₁μ₂ + μ₁ + μ₂)
//   = 100 · (1 - (0.857i)(4.894i) + 0.857i + 4.894i)
//   = 100 · (1 + 4.193 + 5.751i)
//   = 100 · (5.193 + 5.751i)  ← complex?? That can't be right for real stress at (R,0)
//
// Hmm no. The formula for SCF at the hole boundary (θ=0) under σy∞:
// From Lekhnitskii eq 38.12:
//   σθ(0) = σy∞ · [1 + (a/b)(μ₁+μ₂)] when hole is circular (a=b)
//         = 100 · [1 + 1·(0.857i + 4.894i)]
//         = 100 · [1 + 5.751i] ← still complex??
//
// Something is wrong with my formula lookup. Let me use the known result:
//   K_t = 1 + √(2(√(E1/E2) - v12) + E1/G12)
//   = 1 + √(2(4.192 - 0.28) + 25.24)
//   = 1 + √(7.824 + 25.24)
//   = 1 + √33.064
//   = 1 + 5.750
//   = 6.750
//
// So the SCF is 6.75. Let me verify this formula is actually the Lekhnitskii result.
// From Lekhnitskii (1968), the tangential stress at point A (θ=0) on the hole:
//   σθ(A) = σy∞·Re[1 - iμ₁ - iμ₂ + μ₁μ₂·(a²/b²)]  ... for σy loading
//
// For circular a=b:
//   = σy∞·Re[1 - iμ₁ - iμ₂ + μ₁μ₂]
//   μ₁ = iβ₁, μ₂ = iβ₂ (pure imaginary)
//   -iμ₁ = -i·iβ₁ = β₁
//   -iμ₂ = β₂
//   μ₁μ₂ = (iβ₁)(iβ₂) = -β₁β₂
//   = σy∞·[1 + β₁ + β₂ - β₁β₂]
//   β₁ = 0.857, β₂ = 4.894
//   = 100·[1 + 0.857 + 4.894 - 0.857·4.894]
//   = 100·[1 + 5.751 - 4.193]
//   = 100·[2.558]  ← hmm, 2.56 not 6.75
//
// That doesn't match the formula either! Let me re-derive from Lekhnitskii eq 38.12.

console.log("\n═══ Analytical SCF check ═══");
const beta1v = mu1.im;  // 0.857
const beta2v = mu2.im;  // 4.894
console.log(`β₁ = ${beta1v.toFixed(4)}, β₂ = ${beta2v.toFixed(4)}`);

// From Lekhnitskii eq 38.12, for circular hole under σy∞:
// The tangential stress at point A (x=a, y=0):
// σ_t(A) / σy∞ = 1 + 2b/a · √(a11/a22) ... no, that's the general formula

// The CORRECT Lekhnitskii formula for SCF at (a,0) under σy∞:
// For an ORTHOTROPIC plate with circular hole:
//   K = 1 + 2√(E2(2a12+a66)/(2a22)) + E2/G12  ... no

// OK let me just use the compliance-based formula.
// Lekhnitskii SCF for circular hole at θ=0 under σy∞:
//   K = 1 + 2√(a11/a22) + (2a12+a66)/(2a22) · a22 ...
//
// Actually the simplest derivation:
//   For circular hole, at boundary point (a, 0):
//   σθ = σy (tangential = y-direction at this point)
//   Lekhnitskii gives: σθ/σy∞ = 1 + (a/b)[iμ₁+iμ₂] + (a/b)²μ₁μ₂  ... for general ellipse
//
// Hmm, I keep going in circles (pun intended). Let me just use the indisputable formula:
//   Kt = 1 + √(2(√(E1/E2) - v12) + E1/G12)
// and verify my roots give this.

// √(E1/E2) = √(181/10.3) = √17.573 = 4.192
const sqE = Math.sqrt(T300.E1/T300.E2);
console.log(`√(E1/E2) = ${sqE.toFixed(4)}`);
// 2(4.192 - 0.28) + 181/7.17 = 7.824 + 25.244 = 33.068
const innerK = 2*(sqE - T300.v12) + T300.E1/T300.G12;
console.log(`2(√(E1/E2)-v12) + E1/G12 = ${innerK.toFixed(4)}`);
const Kt = 1 + Math.sqrt(innerK);
console.log(`Kt = 1 + √${innerK.toFixed(4)} = ${Kt.toFixed(4)}`);

// Now, can we express Kt in terms of μ₁, μ₂?
// The compliance-based characteristic equation:
// a11μ⁴ + (2a12+a66)μ² + a22 = 0
// Roots: μ₁² = -t₁, μ₂² = -t₂ where t₁,t₂ > 0
// t₁ + t₂ = -(2a12+a66)/a11 = (2v12/E1 - 1/G12)·E1 = 2v12 - E1/G12
// Wait: t₁+t₂ = -B/A = -(2a12+a66)/a11
// = -(−2v12/E1 + 1/G12) / (1/E1) = (2v12 - E1/G12)·(-E1/E1)... let me just compute
console.log(`\nμ₁² = ${C.str(mu1sq)} → β₁²=${beta1v*beta1v}`);
console.log(`μ₂² = ${C.str(mu2sq)} → β₂²=${beta2v*beta2v}`);
console.log(`β₁² + β₂² = ${beta1v*beta1v + beta2v*beta2v}`);
console.log(`β₁²·β₂² = ${beta1v*beta1v * beta2v*beta2v}`);
console.log(`β₁·β₂ = ${beta1v*beta2v}`);
console.log(`β₁+β₂ = ${beta1v+beta2v}`);

// By Vieta's formulas for the biquadratic a11t²+(2a12+a66)t+a22=0:
// β₁² + β₂² = -(2a12+a66)/a11  (sum of roots)
// β₁²·β₂² = a22/a11 = E1/E2  (product of roots)
// So β₁·β₂ = √(E1/E2) = 4.192
console.log(`\nβ₁·β₂ should = √(E1/E2) = ${sqE.toFixed(4)}, actual = ${(beta1v*beta2v).toFixed(4)}`);

// The Kt formula:
// Kt = 1 + √(2(β₁β₂ - v12) + E1/G12)
// But also: 2a12+a66 = -2v12/E1 + 1/G12
// β₁²+β₂² = (2v12/E1 - 1/G12) / (-1/E1) = E1·(1/G12 - 2v12/E1) = E1/G12 - 2v12
console.log(`β₁²+β₂² should = E1/G12-2v12 = ${T300.E1/T300.G12-2*T300.v12}, actual = ${(beta1v*beta1v+beta2v*beta2v).toFixed(4)}`);

// So: Kt = 1 + √(2β₁β₂ - 2v12 + E1/G12)
//       = 1 + √(2β₁β₂ + β₁²+β₂²)  (substituting E1/G12 - 2v12 = β₁²+β₂²)
//       = 1 + √((β₁+β₂)²)
//       = 1 + |β₁+β₂|
//       = 1 + β₁ + β₂
console.log(`\n1 + β₁ + β₂ = ${1 + beta1v + beta2v}`);
console.log(`Kt from formula = ${Kt.toFixed(4)}`);
console.log(`These should match!`);

// So SCF = 1 + β₁ + β₂ = 1 + 0.857 + 4.894 = 6.751 ✓
// This is the tangential stress at hole boundary point (a, 0)
