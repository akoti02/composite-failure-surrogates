/**
 * Verify the CORRECTED boundary conditions and coefficients.
 *
 * Correct BCs (from Lekhnitskii §38):
 *   B₁ + B₂ = -(σy·a - i·τxy·b) / 2         ... (I)
 *   μ₁B₁ + μ₂B₂ = (i·σx·b + τxy·a - σy·b) / 2  ... (II) ← KEY: the -σy·b/2 term was missing!
 *
 * Wait — let me re-derive. The second BC comes from the y-component:
 *   μ₁B₁ + μ₂B₂ = -(σx·y_boundary_integral)
 *
 * For the hole boundary parametrized as x=a·cosθ, y=b·sinθ:
 *   ∫ σx∞·dy = σx∞·b·cosθ → gives σx∞·b/2 coefficient of e^(iθ)
 *   ∫ σy∞·dx = -σy∞·a·sinθ → hmm, this gives different Fourier components
 *
 * Actually the standard result (verified by the research agent):
 *   B₁ = σy·(μ₂·a - b) / [2(μ₁ - μ₂)]
 *   B₂ = -σy·(μ₁·a - b) / [2(μ₁ - μ₂)]
 *
 * For general loading, by superposition:
 *   For σy: B₁ = σy(μ₂a - b) / [2(μ₁-μ₂)],  B₂ = -σy(μ₁a - b) / [2(μ₁-μ₂)]
 *   For σx: B₁ = ?, B₂ = ?
 *   For τxy: B₁ = ?, B₂ = ?
 *
 * Let me verify the σy formula first, then derive σx and τxy.
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
  if (mu1.im<0){mu1.re=-mu1.re;mu1.im=-mu1.im;}
  if (mu2.im<0){mu2.re=-mu2.re;mu2.im=-mu2.im;}
  return [mu1, mu2];
}

/**
 * CORRECTED ellipseStress using the right Lekhnitskii coefficients.
 *
 * For far-field σy∞:
 *   B₁ = σy(μ₂·a - b) / [2(μ₁-μ₂)]
 *   B₂ = -σy(μ₁·a - b) / [2(μ₁-μ₂)]
 *
 * For far-field σx∞ (by analogy, swapping roles):
 * The boundary conditions for σx loading are:
 *   B₁ + B₂ = 0  (no x-component in first BC for pure σx)
 *   μ₁B₁ + μ₂B₂ = i·σx·b/2
 * Solving: B₁ = i·σx·b / [2(μ₁-μ₂)], B₂ = -i·σx·b / [2(μ₁-μ₂)]
 *
 * Hmm wait, let me re-derive from the general BCs.
 *
 * Lekhnitskii §38, eq. 38.6:
 * On the hole boundary (traction-free), the resultant force conditions give:
 *   Φ₁ + Φ₂ = -½(N₂ + iT₂) + const   ... (I)
 *   μ₁Φ₁ + μ₂Φ₂ = ½(N₁ + iT₁) + const  ... (II)
 *
 * where N₁, N₂, T₁, T₂ are stress resultants from the far-field:
 *   Along the hole boundary parametrized by arc length s:
 *   N₁ + iT₁ = ∫(σx dy - τxy dx)  (component in x-direction)
 *   N₂ + iT₂ = ∫(τxy dy - σy dx)  (component in y-direction)
 *
 * For hole boundary x = a cosθ, y = b sinθ:
 *   dx = -a sinθ dθ, dy = b cosθ dθ
 *
 * For uniform σy∞ (σx=0, τxy=0):
 *   N₁ + iT₁ = ∫ 0 = 0
 *   N₂ + iT₂ = ∫ -σy dx = ∫ σy·a·sinθ dθ = -σy·a·cosθ + const
 *
 * For uniform σx∞ (σy=0, τxy=0):
 *   N₁ + iT₁ = ∫ σx dy = ∫ σx·b·cosθ dθ = σx·b·sinθ + const
 *   N₂ + iT₂ = 0
 *
 * For uniform τxy∞ (σx=0, σy=0):
 *   N₁ + iT₁ = ∫ -τxy dx = ∫ τxy·a·sinθ dθ = -τxy·a·cosθ
 *   N₂ + iT₂ = ∫ τxy dy = ∫ τxy·b·cosθ dθ = τxy·b·sinθ
 *
 * On the unit circle ζ = e^(iθ):
 *   cosθ = (ζ + ζ⁻¹)/2,  sinθ = (ζ - ζ⁻¹)/(2i)
 *
 * The Φ_k = B_k/ζ_k perturbation generates ζ⁻¹ terms.
 * On boundary: Φ_k = B_k·e^(-iθ) = B_k·ζ⁻¹
 * Conjugate: Φ̄_k = B̄_k·e^(iθ) = B̄_k·ζ (for real B, same as B_k·ζ)
 *
 * The BCs (I) and (II) must hold for all θ. Matching the e^(-iθ) = ζ⁻¹ Fourier component:
 *
 * From (I), coefficient of ζ⁻¹:
 *   B₁ + B₂ = -½ · [coefficient of ζ⁻¹ in (N₂+iT₂)]
 *
 * For σy loading: N₂+iT₂ = -σy·a·cosθ = -σy·a·(ζ+ζ⁻¹)/2
 *   Coeff of ζ⁻¹ = -σy·a/2
 *   → B₁ + B₂ = -½·(-σy·a/2) = +σy·a/4  ???
 *
 * Hmm, that gives a different sign. Let me be more careful.
 *
 * Actually the matching also involves the CONJUGATE terms.
 * Φ₁(ζ⁻¹) + Φ₂(ζ⁻¹) + Φ̄₁(ζ) + Φ̄₂(ζ) = RHS
 *
 * Φ_k = B_k/ζ → on boundary: B_k·ζ⁻¹
 * Φ̄_k = B̄_k·ζ (conjugate of B_k/ζ evaluated on unit circle)
 *
 * So ζ⁻¹ coefficient of LHS: B₁ + B₂ (from Φ terms)
 * ζ⁺¹ coefficient of LHS: B̄₁ + B̄₂ (from Φ̄ terms)
 *
 * RHS for σy: -½(-σy·a·cosθ) = σy·a·cosθ/2 = σy·a·(ζ+ζ⁻¹)/4
 * ζ⁻¹ coefficient of RHS: σy·a/4
 * ζ⁺¹ coefficient of RHS: σy·a/4
 *
 * So: B₁ + B₂ = σy·a/4
 * And: B̄₁ + B̄₂ = σy·a/4 (same for real B)
 *
 * From (II), coefficient of ζ⁻¹:
 * μ₁B₁ + μ₂B₂ + μ̄₁B̄₁·(ζ coeff?) ... hmm, eq (II) is:
 *   μ₁Φ₁ + μ₂Φ₂ + μ̄₁Φ̄₁ + μ̄₂Φ̄₂ = ½(N₁+iT₁)
 *
 * Wait — does (II) also have conjugate terms? Let me re-read Lekhnitskii.
 *
 * Actually, Lekhnitskii's original BCs (§35.2, eq. 35.7) are:
 *   2Re[Φ₁(z₁) + Φ₂(z₂)] = f₁(s)    ... (I')
 *   2Re[μ₁Φ₁(z₁) + μ₂Φ₂(z₂)] = f₂(s) ... (II')
 *
 * These automatically include conjugates via 2Re[...].
 *
 * So: 2Re[Φ₁+Φ₂] = Φ₁+Φ₂+Φ̄₁+Φ̄₂ = f₁
 *     2Re[μ₁Φ₁+μ₂Φ₂] = μ₁Φ₁+μ₂Φ₂+μ̄₁Φ̄₁+μ̄₂Φ̄₂ = f₂
 *
 * On boundary with ζ=e^(iθ):
 * Φ_k = B_k·ζ⁻¹, Φ̄_k = B̄_k·ζ
 *
 * (I'): B₁ζ⁻¹ + B₂ζ⁻¹ + B̄₁ζ + B̄₂ζ = f₁
 * Matching ζ⁻¹: B₁+B₂ = [ζ⁻¹ coeff of f₁]
 * Matching ζ: B̄₁+B̄₂ = [ζ coeff of f₁]
 *
 * (II'): μ₁B₁ζ⁻¹ + μ₂B₂ζ⁻¹ + μ̄₁B̄₁ζ + μ̄₂B̄₂ζ = f₂
 * Matching ζ⁻¹: μ₁B₁+μ₂B₂ = [ζ⁻¹ coeff of f₂]
 *
 * Now for σy∞ loading:
 *   f₁(s) = ∫₀ˢ Yₙ ds = ∫ σy cos(n,y) ds
 * where n is outward normal and (n,y) is angle between n and y-axis.
 * For ellipse: cos(n,y) ds = dx (component of arc in x-direction)
 *
 * Hmm, this is getting circular. Let me just try different coefficient
 * formulas numerically and see which gives SCF=6.75.

 * APPROACH: The research agent said:
 *   B₁ = σy(μ₂·a - b) / [2(μ₁-μ₂)]
 *   B₂ = -σy(μ₁·a - b) / [2(μ₁-μ₂)]
 * Let me verify this gives the right SCF.
 */

const T300 = { E1: 181, E2: 10.3, G12: 7.17, v12: 0.28 };
const [mu1, mu2] = characteristicRoots(T300);
const mu1sq = C.mul(mu1, mu1);
const mu2sq = C.mul(mu2, mu2);
const beta1 = mu1.im, beta2 = mu2.im;

console.log(`μ₁ = ${C.str(mu1)}, μ₂ = ${C.str(mu2)}`);
console.log(`β₁ = ${beta1.toFixed(4)}, β₂ = ${beta2.toFixed(4)}`);

const a = 5, b = 5; // circular
const syL = 100;
const mu_diff = C.sub(mu1, mu2);

// Formula: B₁ = σy(μ₂·a - b) / [2(μ₁-μ₂)]
const B1 = C.div(C.scale(C.sub(C.scale(mu2, a), {re:b,im:0}), syL), C.scale(mu_diff, 2));
const B2 = C.div(C.scale(C.sub(C.scale(mu1, a), {re:b,im:0}), -syL), C.scale(mu_diff, 2));

console.log(`B₁ = ${C.str(B1)}`);
console.log(`B₂ = ${C.str(B2)}`);

// Verify BCs:
const bc1 = C.add(B1, B2);
const bc2 = C.add(C.mul(mu1, B1), C.mul(mu2, B2));
console.log(`B₁+B₂ = ${C.str(bc1)}`);
console.log(`μ₁B₁+μ₂B₂ = ${C.str(bc2)}`);

// Compute Φ' at point just outside hole edge (x=a+0.01, y=0)
function computeStressAt(px, py) {
  const x = px, y = py;
  const z1 = {re: x+mu1.re*y, im: mu1.im*y};
  const z2 = {re: x+mu2.re*y, im: mu2.im*y};
  const inner1 = C.sub(C.mul(z1,z1), {re: a*a+mu1sq.re*b*b, im: mu1sq.im*b*b});
  const inner2 = C.sub(C.mul(z2,z2), {re: a*a+mu2sq.re*b*b, im: mu2sq.im*b*b});
  const sqrt1 = C.sqrt(inner1);
  const sqrt2 = C.sqrt(inner2);
  const den1 = {re: a+mu1.im*b, im: -mu1.re*b};
  const den2 = {re: a+mu2.im*b, im: -mu2.re*b};
  let zeta1 = C.div(C.add(z1, sqrt1), den1);
  let zeta2 = C.div(C.add(z2, sqrt2), den2);
  if (C.mag(zeta1) < 1) zeta1 = C.div(C.sub(z1, sqrt1), den1);
  if (C.mag(zeta2) < 1) zeta2 = C.div(C.sub(z2, sqrt2), den2);

  // dζ/dz from explicit formula
  const dzeta1 = C.div(C.add({re:1,im:0}, C.div(z1, sqrt1)), den1);
  const dzeta2 = C.div(C.add({re:1,im:0}, C.div(z2, sqrt2)), den2);
  const zi1_2 = C.mul(C.div({re:1,im:0},zeta1), C.div({re:1,im:0},zeta1));
  const zi2_2 = C.mul(C.div({re:1,im:0},zeta2), C.div({re:1,im:0},zeta2));
  const phi1p = C.mul(C.scale(B1,-1), C.mul(zi1_2, dzeta1));
  const phi2p = C.mul(C.scale(B2,-1), C.mul(zi2_2, dzeta2));

  const dSigY = 2*(phi1p.re + phi2p.re);
  const dSigX = 2*(C.mul(mu1sq,phi1p).re + C.mul(mu2sq,phi2p).re);
  const dTauXY = -2*(C.mul(mu1,phi1p).re + C.mul(mu2,phi2p).re);
  return { sigX: dSigX, sigY: syL + dSigY, tauXY: dTauXY };
}

console.log("\n═══ SCF test with corrected B coefficients ═══");
const dists = [0.001, 0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 20.0, 100.0];
for (const d of dists) {
  const r = computeStressAt(a+d, 0);
  console.log(`  x=${(a+d).toFixed(3).padStart(8)}: σy=${r.sigY.toFixed(2).padStart(8)} (SCF=${(r.sigY/syL).toFixed(3)}), σx=${r.sigX.toFixed(2).padStart(7)}`);
}

// Also test at top of hole
const top = computeStressAt(0, a+0.01);
console.log(`  Top (0,a+ε): σy=${top.sigY.toFixed(2)} (SCF=${(top.sigY/syL).toFixed(3)})`);

// Far field
const far = computeStressAt(500, 500);
console.log(`  Far (500,500): σx=${far.sigX.toFixed(2)}, σy=${far.sigY.toFixed(2)}`);

// ═══ Now derive σx loading coefficients by analogy ═══
console.log("\n═══ σx loading ═══");
// For σx∞ loading, by analogy with the hole boundary integrals:
// The first BC RHS involves ∫σy·dx which is 0 for σx loading
// The second BC RHS involves ∫σx·dy = σx·b·sinθ
//
// Using same derivation pattern:
// B₁ = ? Let me try: swap σy→σx, a→b in the formula?
// Or derive from BCs:
//   B₁+B₂ = 0 (no σy, no τxy)
//   μ₁B₁+μ₂B₂ = i·σx·b/2 ... but with conjugate terms
//
// For σx∞, by the Lekhnitskii result:
// B₁_sx = -σx·μ₂·b / [2(μ₁-μ₂)]  ? Let me try several options.
//
// Option A: B₁ = σx·(μ₂·b - a·μ₁μ₂) / [2(μ₁-μ₂)] ... guessing
// Option B: By superposition with the known SCF for σx loading
//
// For σx loading on circular hole, SCF at (0, b) should be:
// Kt_x = 1 + 2√(E1/E2) + ... hmm, it's the same formula but at (0,a):
// At (0,a) under σx: σx = σx∞·(1 + μ₁+μ₂ for σx loading?)
//
// Actually for σx loading, the SCF at (0,a) by Lekhnitskii is:
// σx(0,a)/σx∞ = 1 + (1/β₁ + 1/β₂) + 1/(β₁β₂) ... no
//
// From Lekhnitskii's general formula for orthotropic hole:
// Under σx∞, SCF at (0,b) = 1 + E2/G12 - 2ν₂₁ + 2√(E2/E1·(E2/G12...))
// This is quite different.
//
// For now, let me just verify σy loading is correct and handle the general
// case in the actual code.

// ═══ General formula verification ═══
// For general loading on ELLIPTICAL hole:
// B₁ = [σy(μ₂a - b) - σx·μ₂·b + τxy·(μ₂a+b)·i] / [2(μ₁-μ₂)]  ???
// I'm not sure of the τxy and σx terms. Let me derive from the boundary conditions.

// The FULL Lekhnitskii BCs (matching ζ⁻¹ from 2Re[...] = f):
// Since 2Re[Φ] = Φ + Φ̄, and on ζ=e^(iθ), Φ_k=B_k/ζ gives ζ⁻¹ terms,
// Φ̄_k=B̄_k·ζ gives ζ⁺¹ terms.
// So for ζ⁻¹ matching: B₁+B₂ = [ζ⁻¹ coeff of f₁]
// And for ζ⁺¹ matching: B̄₁+B̄₂ = [ζ⁺¹ coeff of f₁]
// (these are consistent for real B or give real+imag parts for complex B)

// f₁ = ∫(Yn ds) = ∫(τxy·cos(n,x) + σy·cos(n,y)) ds
// On ellipse: cos(n,x)ds = dy = b cosθ dθ, cos(n,y)ds = -dx = a sinθ dθ
// f₁ = ∫(τxy·b·cosθ + σy·a·sinθ) dθ
//     = τxy·b·sinθ - σy·a·cosθ + const
//     = -σy·a·cosθ + τxy·b·sinθ + const
//     = -σy·a·(ζ+ζ⁻¹)/2 + τxy·b·(ζ-ζ⁻¹)/(2i) + const
//     = (-σy·a/2 - τxy·b/(2i))·ζ⁻¹ + (-σy·a/2 + τxy·b/(2i))·ζ + const
//     = (-σy·a/2 + i·τxy·b/2)·ζ⁻¹ + (-σy·a/2 - i·τxy·b/2)·ζ + const

// f₂ = ∫(Xn ds) = ∫(σx·cos(n,x) + τxy·cos(n,y)) ds
// = ∫(σx·b·cosθ + τxy·a·sinθ) dθ
// = σx·b·sinθ - τxy·a·cosθ + const
// = σx·b·(ζ-ζ⁻¹)/(2i) - τxy·a·(ζ+ζ⁻¹)/2 + const
// = (i·σx·b/2 - τxy·a/2)·ζ⁻¹ + (-i·σx·b/2 - τxy·a/2)·ζ + const

// Wait — BUT the BCs are:
// 2Re[Φ₁+Φ₂] = f₁ ... no, that's not right either.
//
// Lekhnitskii §35, eq. 35.7 (adapted for the hole problem):
// The traction-free BC requires the perturbation to cancel the far-field tractions:
//   Φ₁_pert + Φ₂_pert + Φ̄₁_pert + Φ̄₂_pert = -f₁_farfield
//   μ₁Φ₁_pert + μ₂Φ₂_pert + μ̄₁Φ̄₁_pert + μ̄₂Φ̄₂_pert = -f₂_farfield

// So matching ζ⁻¹ coefficients:
// BC-I ζ⁻¹: B₁+B₂ = -[ζ⁻¹ coeff of f₁] = -(-σy·a/2 + i·τxy·b/2)
//          = σy·a/2 - i·τxy·b/2

// WAIT. That's + not -. Previously I had B₁+B₂ = -σy·a/2, but now it's +σy·a/2.

// Let me check the sign convention. f₁ is the stress resultant from the FAR-FIELD
// loading. The perturbation must CANCEL it. So:
// Perturbation: 2Re[Φ₁_pert + Φ₂_pert] = -f₁_farfield
// → Φ₁_pert + Φ₂_pert + Φ̄₁ + Φ̄₂ = -f₁
// ζ⁻¹ coeff: B₁ + B₂ = -[ζ⁻¹ coeff of f₁] = -(−σy·a/2 + i·τxy·b/2)
//           = σy·a/2 - i·τxy·b/2

// And ζ⁺¹ coeff: B̄₁ + B̄₂ = -[ζ⁺¹ coeff of f₁] = -(−σy·a/2 - i·τxy·b/2)
//               = σy·a/2 + i·τxy·b/2  ← conjugate of ζ⁻¹ result ✓

// BC-II ζ⁻¹: μ₁B₁ + μ₂B₂ = -[ζ⁻¹ coeff of f₂]
// f₂ ζ⁻¹ coeff = i·σx·b/2 - τxy·a/2
// → μ₁B₁ + μ₂B₂ = -(i·σx·b/2 - τxy·a/2) = -i·σx·b/2 + τxy·a/2

// So the CORRECT BCs are:
// B₁ + B₂ = σy·a/2 - i·τxy·b/2         ... (I)
// μ₁B₁ + μ₂B₂ = -i·σx·b/2 + τxy·a/2   ... (II)
//
// THIS IS DIFFERENT FROM WHAT I HAD BEFORE! The sign is opposite!
// Before I had B₁+B₂ = -(σy·a)/2 but now it's +(σy·a)/2.

// Solving for pure σy loading (σx=0, τxy=0):
// B₁+B₂ = σy·a/2 = 250
// μ₁B₁+μ₂B₂ = 0

// Check: with μ₁=iβ₁, μ₂=iβ₂:
// iβ₁B₁ + iβ₂B₂ = 0 → β₁B₁+β₂B₂=0 → B₁ = -β₂B₂/β₁
// B₂(1-β₂/β₁) = 250 → B₂ = 250β₁/(β₁-β₂)
// B₁ = 250 - B₂ = 250·(-β₂)/(β₁-β₂) = -250β₂/(β₁-β₂)

const B1_v2 = -250*beta2 / (beta1-beta2);
const B2_v2 = 250*beta1 / (beta1-beta2);
console.log(`\n═══ Version 2 BCs (sign fix): B₁+B₂ = +σy·a/2 ═══`);
console.log(`B₁ = ${B1_v2.toFixed(4)}`);
console.log(`B₂ = ${B2_v2.toFixed(4)}`);
console.log(`B₁+B₂ = ${(B1_v2+B2_v2).toFixed(4)} (expect 250)`);
console.log(`β₁B₁+β₂B₂ = ${(beta1*B1_v2+beta2*B2_v2).toFixed(6)} (expect 0)`);

// Now SCF at (a, 0):
// Φ₁' = -B₁/(β₁·b) (at ζ=1)
// Φ₂' = -B₂/(β₂·b)
const p1 = -B1_v2/(beta1*b);
const p2 = -B2_v2/(beta2*b);
console.log(`Φ₁'|_{ζ=1} = ${p1.toFixed(4)}`);
console.log(`Φ₂'|_{ζ=1} = ${p2.toFixed(4)}`);
const dSigY_v2 = 2*(p1+p2);
console.log(`Δσy = 2(Φ₁'+Φ₂') = ${dSigY_v2.toFixed(4)}`);
console.log(`SCF = ${((syL+dSigY_v2)/syL).toFixed(4)} (expect 6.75)`);

// Now also check with the formula B₁ = σy(μ₂a-b)/[2(μ₁-μ₂)]:
// μ₂a-b = i·4.894·5 - 5 = -5 + 24.47i
// 2(μ₁-μ₂) = 2·(i·0.857 - i·4.894) = -8.074i
// B₁ = 100·(-5+24.47i)/(-8.074i)
//    = 100·(-5+24.47i)·(i)/(8.074)
//    = 100·(-5i - 24.47)/(8.074) hmm, complex result

const B1_formula = C.div(C.scale(C.sub(C.scale(mu2,a),{re:b,im:0}),syL), C.scale(mu_diff,2));
console.log(`\nB₁ from (μ₂a-b) formula: ${C.str(B1_formula)}`);
// This gives a complex B₁, which means the agent's formula might be wrong for
// the pure-imaginary root case.

// MY VERSION 2 gives REAL B values. Let me test them numerically.
console.log(`\n═══ Numerical test with Version 2 B coefficients ═══`);
function computeV2(px, py) {
  const x=px, y=py;
  const z1={re:x+mu1.re*y, im:mu1.im*y};
  const z2={re:x+mu2.re*y, im:mu2.im*y};
  const in1=C.sub(C.mul(z1,z1),{re:a*a+mu1sq.re*b*b,im:mu1sq.im*b*b});
  const in2=C.sub(C.mul(z2,z2),{re:a*a+mu2sq.re*b*b,im:mu2sq.im*b*b});
  const s1=C.sqrt(in1), s2=C.sqrt(in2);
  const d1={re:a+mu1.im*b,im:-mu1.re*b};
  const d2={re:a+mu2.im*b,im:-mu2.re*b};
  let z1f=C.div(C.add(z1,s1),d1);
  let z2f=C.div(C.add(z2,s2),d2);
  if(C.mag(z1f)<1) z1f=C.div(C.sub(z1,s1),d1);
  if(C.mag(z2f)<1) z2f=C.div(C.sub(z2,s2),d2);
  const dz1=C.div(C.add({re:1,im:0},C.div(z1,s1)),d1);
  const dz2=C.div(C.add({re:1,im:0},C.div(z2,s2)),d2);
  const zi12=C.mul(C.div({re:1,im:0},z1f),C.div({re:1,im:0},z1f));
  const zi22=C.mul(C.div({re:1,im:0},z2f),C.div({re:1,im:0},z2f));
  const ph1=C.mul({re:-B1_v2,im:0},C.mul(zi12,dz1));
  const ph2=C.mul({re:-B2_v2,im:0},C.mul(zi22,dz2));
  const dsY=2*(ph1.re+ph2.re);
  const dsX=2*(C.mul(mu1sq,ph1).re+C.mul(mu2sq,ph2).re);
  return {sigX:dsX, sigY:syL+dsY};
}

for (const d of [0.001, 0.01, 0.1, 0.5, 1.0, 5.0, 50.0]) {
  const r = computeV2(a+d, 0);
  console.log(`  x=${(a+d).toFixed(3).padStart(7)}: σy=${r.sigY.toFixed(1).padStart(7)} (SCF=${(r.sigY/syL).toFixed(3)}), σx=${r.sigX.toFixed(2)}`);
}
const farV2 = computeV2(500, 500);
console.log(`  Far: σx=${farV2.sigX.toFixed(2)}, σy=${farV2.sigY.toFixed(2)}`);
