/**
 * Debug the derivative computation.
 * The issue: φ_k' = -B_k · ζ_k⁻² · dζ_k/dz_k
 *
 * But we need to verify dζ/dz is correct.
 * Alternative: compute dζ/dz from the explicit ζ formula.
 * ζ = [z + √(z² - a² - μ²b²)] / (a - iμb)
 * dζ/dz = [1 + z/√(z² - a² - μ²b²)] / (a - iμb)
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

// T300/5208 μ values
const mu1 = {re: 0, im: 0.856574};
const mu2 = {re: 0, im: 4.893910};
const mu1sq = C.mul(mu1, mu1);
const mu2sq = C.mul(mu2, mu2);

const a = 5, b = 5;
const syL = 100;

// Approach 1: dζ/dz from explicit formula
// ζ = [z + √(z² - a² - μ²b²)] / (a - iμb) = [z + S] / D
// dζ/dz = [1 + z/S] / D

// Approach 2: dζ/dz from inverse of dz/dζ
// z = D/2 · ζ + D̄/2 · ζ⁻¹  where D = a-iμb, D̄ = a+iμb
// dz/dζ = D/2 - D̄/2 · ζ⁻²
// dζ/dz = 1/(D/2 - D̄/2 · ζ⁻²) = 2/(D - D̄·ζ⁻²)

// These should be identical. Let me check.

const x = 5.01, y = 0; // very close to hole edge

console.log(`Point: (${x}, ${y})`);

const z1 = { re: x, im: 0 }; // y=0

// Method 1:
const inner1 = { re: x*x - a*a - mu1sq.re*b*b, im: 0 };
const S1 = C.sqrt(inner1);
const D1 = { re: a + mu1.im*b, im: 0 }; // a-iμ₁b with μ₁=iβ₁ → a+β₁b
const Dbar1 = { re: a - mu1.im*b, im: 0 }; // a+iμ₁b with μ₁=iβ₁ → a-β₁b
const zeta1 = C.div(C.add(z1, S1), D1);

// dζ/dz method 1
const dzeta_dz_m1 = C.div(C.add({re:1,im:0}, C.div(z1, S1)), D1);

// dζ/dz method 2
const zeta1inv2 = C.div({re:1,im:0}, C.mul(zeta1, zeta1));
const dzeta_dz_m2 = C.div({re:2,im:0}, C.sub(D1, C.mul(Dbar1, zeta1inv2)));

console.log(`S₁ = ${C.str(S1)}`);
console.log(`D₁ = ${C.str(D1)}`);
console.log(`D̄₁ = ${C.str(Dbar1)}`);
console.log(`ζ₁ = ${C.str(zeta1)}, |ζ₁|=${C.mag(zeta1).toFixed(6)}`);
console.log(`dζ/dz method1 = ${C.str(dzeta_dz_m1)}`);
console.log(`dζ/dz method2 = ${C.str(dzeta_dz_m2)}`);

// Now compute φ₁' two ways and see which gives SCF=6.75

// The perturbation potential: φ₁(z₁) = B₁/ζ₁
// φ₁'(z₁) = d(B₁/ζ₁)/dz₁ = -B₁/ζ₁² · dζ₁/dz₁

const mu_diff = C.sub(mu1, mu2);
const B1 = C.div(C.mul(mu2, {re: 500, im: 0}), C.scale(mu_diff, 2));
const B2 = C.div(C.scale(C.mul(mu1, {re: 500, im: 0}), -1), C.scale(mu_diff, 2));

console.log(`\nB₁ = ${C.str(B1)}`);
console.log(`B₂ = ${C.str(B2)}`);

// φ₁' using method 1 derivative
const phi1_m1 = C.mul(C.scale(B1, -1), C.mul(zeta1inv2, dzeta_dz_m1));

// Same for μ₂
const inner2 = { re: x*x - a*a - mu2sq.re*b*b, im: 0 };
const S2 = C.sqrt(inner2);
const D2 = { re: a + mu2.im*b, im: 0 };
const Dbar2 = { re: a - mu2.im*b, im: 0 };
const zeta2 = C.div(C.add(z1, S2), D2);
const zeta2inv2 = C.div({re:1,im:0}, C.mul(zeta2, zeta2));
const dzeta2_dz_m1 = C.div(C.add({re:1,im:0}, C.div(z1, S2)), D2);

const phi2_m1 = C.mul(C.scale(B2, -1), C.mul(zeta2inv2, dzeta2_dz_m1));

console.log(`\nφ₁' = ${C.str(phi1_m1)}`);
console.log(`φ₂' = ${C.str(phi2_m1)}`);

const dSigY = 2 * (phi1_m1.re + phi2_m1.re);
const totalSigY = syL + dSigY;
console.log(`\nΔσy = ${dSigY.toFixed(4)}`);
console.log(`Total σy = ${totalSigY.toFixed(4)}`);
console.log(`SCF = ${(totalSigY/syL).toFixed(4)} (expect ~6.75)`);

// ═══════════════════════════════════════════════
// ALTERNATIVE: Try the BOUNDARY formula directly.
// On the hole boundary (ζ = e^(iθ)), at θ=0 (point A):
// ζ = 1
//
// The tangential stress at the boundary is given by Lekhnitskii eq 38.11:
// σ_θ = Re[μ₁²·φ₁'(z₁) + μ₂²·φ₂'(z₂)] ... at boundary
//
// Actually, at the boundary of the hole, the TANGENTIAL stress can be found
// from the boundary formula directly. Let me use a different approach:
//
// From Lekhnitskii, the tangential stress on the hole boundary at angle θ is:
// σ_t(θ) = (σx∞ + σy∞) · [... complex formula involving μ₁, μ₂ ...]
//
// But for σy∞ loading at θ=0 (point (a,0)):
// σ_t = σ_y (tangential = y-direction)
//
// The boundary stress formula (Lekhnitskii eq 38.11, corrected):
// On ζ₁ = ζ₂ = e^(iθ), at θ=0: ζ = 1
//
// At ζ=1: φ_k(ζ_k=1) = B_k
// dζ_k/dz_k at boundary needs care...
//
// Actually, let me try yet another approach. On the boundary, z₁ = z₂ = z.
// The conformal map: z_k = (a-iμ_kb)/2 · ζ + (a+iμ_kb)/2 · ζ⁻¹
// At θ=0, ζ=1: z_k = (a-iμ_kb+a+iμ_kb)/2 = a (real!) ← makes sense
//
// dz_k/dζ at ζ=1: = (a-iμ_kb)/2 - (a+iμ_kb)/2 · 1 = (a-iμ_kb-a-iμ_kb)/2 = -iμ_kb
// For μ₁=iβ₁: dz₁/dζ₁|_{ζ=1} = -i·(iβ₁)·b = β₁·b
// For μ₂=iβ₂: dz₂/dζ₂|_{ζ=1} = β₂·b
//
// dζ_k/dz_k|_{ζ=1} = 1/(β_k·b)
//
// φ_k' = -B_k · 1 · 1/(β_k·b)   (ζ⁻² = 1 at ζ=1)
//
// For our values:
// φ₁'|_{ζ=1} = -B₁/(β₁·b) = -(-303.04)/(0.857·5) = 303.04/4.283 = 70.77
// φ₂'|_{ζ=1} = -B₂/(β₂·b) = -(53.04)/(4.894·5) = -53.04/24.47 = -2.168
//
// Δσy = 2·Re[φ₁' + φ₂'] = 2·(70.77 - 2.168) = 2·68.60 = 137.2
// Total σy = 100 + 137.2 = 237.2 → SCF = 2.37
//
// Still not 6.75! The formula φ_k' = -B_k · ζ⁻² · dζ/dz must be wrong,
// or the stress formula itself is wrong.
//
// Let me reconsider. Maybe the stress formulas are:
//   σx = 2·Re[μ₁²·Φ₁'' + μ₂²·Φ₂'']
// where Φ is the stress function (not its derivative).
// Φ_k = B_k · ln(ζ_k) ... for a single term?
// No. Let's go back to basics.
//
// Lekhnitskii's stress functions F₁(z₁), F₂(z₂):
//   σx = ∂²F₁/∂y² + ∂²F₂/∂y²  = Re[μ₁²·F₁''(z₁) + μ₂²·F₂''(z₂)]  ... wait
//
// Standard Lekhnitskii convention:
//   σx = 2·Re[μ₁²·ψ₁'(z₁) + μ₂²·ψ₂'(z₂)]
//   σy = 2·Re[ψ₁'(z₁) + ψ₂'(z₂)]
//   τxy = -2·Re[μ₁·ψ₁'(z₁) + μ₂·ψ₂'(z₂)]
//
// where ψ_k' = dF_k/dz_k (Lekhnitskii uses F, not Φ or ψ, but it's the same).
//
// The TOTAL stress function = far-field + perturbation:
//   F_k(z_k) = A_k·z_k² / 2 + f_k(z_k)
//
// where A_k gives the far-field part:
//   σx∞ = 2Re[μ₁²A₁ + μ₂²A₂]
//   σy∞ = 2Re[A₁ + A₂]
//   τxy∞ = -2Re[μ₁A₁ + μ₂A₂]
//
// And F_k' = A_k·z_k + f_k'(z_k), so ψ_k' = F_k'' = A_k + f_k''(z_k)
//
// Wait — this means ψ_k' = F_k'' (second derivative), not first!
// Then the perturbation part contributes f_k''(z_k) to the stress.
//
// If f_k(z_k) uses a Laurent series in ζ_k:
//   f_k(z_k) = Σ c_n · ζ_k^(-n)  (for exterior problem)
//
// For n=1: f_k = c_k / ζ_k
// f_k' = -c_k · ζ_k⁻² · dζ_k/dz_k
// f_k'' = c_k · [2·ζ_k⁻³·(dζ_k/dz_k)² - ζ_k⁻²·d²ζ_k/dz_k²]
//
// That's much more complex! And the stresses use f_k'' not f_k'.
//
// OH. This is the bug. The original code uses Φ₁'(z₁) in the stress formula,
// but the convention is that the stress involves the SECOND derivative of F.
// If Φ = F' (i.e., Φ' = F''), then using Φ' is correct.
// But if the perturbation is f = B/ζ, then:
//   f' = dB/dz · (1/ζ) = -B·ζ⁻²·dζ/dz   ← this is Φ = F'
//   So Φ' = f'' = ...                       ← this is what goes into stress formula
//
// OK SO THE BUG IS: we need F_k'' for the stress formula, but we're computing F_k'.
//
// Let me recheck. Lekhnitskii defines:
//   U = 2Re[F₁(z₁) + F₂(z₂)]   (Airy stress function)
//   σx = ∂²U/∂y²
//   σy = ∂²U/∂x²
//   τxy = -∂²U/∂x∂y
//
// Since z_k = x + μ_k·y:
//   ∂F_k/∂x = F_k'(z_k)
//   ∂F_k/∂y = μ_k·F_k'(z_k)
//   ∂²F_k/∂x² = F_k''(z_k)
//   ∂²F_k/∂y² = μ_k²·F_k''(z_k)
//   ∂²F_k/∂x∂y = μ_k·F_k''(z_k)
//
// So: σx = 2Re[μ₁²·F₁'' + μ₂²·F₂'']
//     σy = 2Re[F₁'' + F₂'']
//     τxy = -2Re[μ₁·F₁'' + μ₂·F₂'']
//
// This means the stress uses F_k'' (second derivative).
//
// If our perturbation is f_k = B_k/ζ_k, then:
//   f_k'(z_k) = -B_k · ζ_k⁻² · ζ_k'     where ζ_k' = dζ_k/dz_k
//   f_k''(z_k) = B_k · [2ζ_k⁻³·(ζ_k')² - ζ_k⁻²·ζ_k'']
//
// This is what we need for the stress formula.
//
// Alternatively, define Φ_k = F_k' (Muskhelishvili-like convention):
//   Then σx = 2Re[μ₁²·Φ₁' + μ₂²·Φ₂']
//   And Φ_k = f_k' = -B_k·ζ_k⁻²·ζ_k'     ... for the perturbation
//   And Φ_k' = f_k'' = the messy expression above
//
// OR use the logarithmic representation:
//   F_k = B_k · ln(ζ_k)
//   F_k' = B_k · ζ_k'/ζ_k                  = B_k/(ζ_k) · dζ/dz
//   F_k'' = B_k · [ζ_k''/ζ_k - (ζ_k')²/ζ_k²]
//
// Hmm, this is getting complicated. Let me try the LOG representation since
// that gives a nicer second derivative.

console.log("\n═══ TRYING LOG REPRESENTATION ═══");
// F_k = B_k · ln(ζ_k)
// F_k' = B_k · (1/ζ_k) · dζ_k/dz_k
// F_k'' = B_k · [-(1/ζ_k²)(dζ_k/dz_k)² + (1/ζ_k)(d²ζ_k/dz_k²)]

// At ζ=1 (boundary, θ=0):
// dζ/dz = 1/(β_k·b)   (computed above)
// d²ζ/dz² = ?

// From dz/dζ = (a-iμb)/2 - (a+iμb)/2·ζ⁻²
// d²z/dζ² = (a+iμb)·ζ⁻³
// d²ζ/dz² = -(d²z/dζ²)·(dζ/dz)³ = -(a+iμb)·ζ⁻³ · (dζ/dz)³

// At ζ=1:
// d²z₁/dζ₁² = (a+iμ₁b) = a - β₁b (since iμ₁ = i·iβ₁ = -β₁)
// Wait: a+iμ₁b where μ₁=iβ₁: a + i·(iβ₁)·b = a - β₁b
const dbar1 = a - mu1.im * b; // = 5 - 0.857*5 = 0.717
const dbar2 = a - mu2.im * b; // = 5 - 4.894*5 = -19.47

const dz1_dzeta_at1 = mu1.im * b; // β₁b = 4.283
const dz2_dzeta_at1 = mu2.im * b; // β₂b = 24.47

const dzeta1_dz_at1 = 1 / dz1_dzeta_at1; // = 0.2335
const dzeta2_dz_at1 = 1 / dz2_dzeta_at1; // = 0.04088

const d2z1_dzeta2_at1 = dbar1; // = 0.717
const d2z2_dzeta2_at1 = dbar2; // = -19.47

const d2zeta1_dz2_at1 = -d2z1_dzeta2_at1 * dzeta1_dz_at1**3;
const d2zeta2_dz2_at1 = -d2z2_dzeta2_at1 * dzeta2_dz_at1**3;

console.log(`At ζ=1 (hole boundary, θ=0):`);
console.log(`  dζ₁/dz = ${dzeta1_dz_at1.toFixed(6)}`);
console.log(`  dζ₂/dz = ${dzeta2_dz_at1.toFixed(6)}`);
console.log(`  d²ζ₁/dz² = ${d2zeta1_dz2_at1.toFixed(6)}`);
console.log(`  d²ζ₂/dz² = ${d2zeta2_dz2_at1.toFixed(6)}`);

// Using F_k = B_k·ln(ζ_k):
// F_k' = B_k/ζ · dζ/dz   → at ζ=1: B_k · dζ/dz
// F_k'' = B_k·[-1/ζ²·(dζ/dz)² + 1/ζ·d²ζ/dz²]  → at ζ=1: B_k·[-(dζ/dz)² + d²ζ/dz²]

// Hmm but we also need the far-field A_k. The full F includes both parts.
// For just the perturbation f_k = B_k·ln(ζ_k):
// Perturbation stress contribution: 2Re[f₁'' + f₂''] (for σy component)

const f1pp = -303.04 * (-(dzeta1_dz_at1**2) + d2zeta1_dz2_at1);
const f2pp = 53.04 * (-(dzeta2_dz_at1**2) + d2zeta2_dz2_at1);

console.log(`\nUsing F=B·ln(ζ):`);
console.log(`  f₁'' at boundary = ${f1pp.toFixed(4)}`);
console.log(`  f₂'' at boundary = ${f2pp.toFixed(4)}`);
console.log(`  Δσy = 2·Re[f₁''+f₂''] = ${(2*(f1pp+f2pp)).toFixed(4)}`);
console.log(`  Total σy = ${(100 + 2*(f1pp+f2pp)).toFixed(4)}`);
console.log(`  SCF = ${((100 + 2*(f1pp+f2pp))/100).toFixed(4)}`);

// ═══════════════════════════════════════════════
// ACTUALLY: Let me try the 1/ζ representation with CORRECT derivative.
// f_k = B_k / ζ_k
// f_k' = -B_k · ζ_k⁻² · dζ_k/dz_k
// f_k'' = B_k · [2·ζ_k⁻³·(dζ_k/dz_k)² - ζ_k⁻²·d²ζ_k/dz_k²]

console.log(`\n═══ Using F=B/ζ: ═══`);
const g1pp = -303.04 * (2 * dzeta1_dz_at1**2 - d2zeta1_dz2_at1);
const g2pp = 53.04 * (2 * dzeta2_dz_at1**2 - d2zeta2_dz2_at1);
console.log(`  f₁'' = B₁·[2(dζ/dz)²-d²ζ/dz²] = ${g1pp.toFixed(4)}`);
console.log(`  f₂'' = ${g2pp.toFixed(4)}`);
console.log(`  Δσy = 2(f₁''+f₂'') = ${(2*(g1pp+g2pp)).toFixed(4)}`);
console.log(`  Total = ${(100+2*(g1pp+g2pp)).toFixed(4)}`);
console.log(`  SCF = ${((100+2*(g1pp+g2pp))/100).toFixed(4)}`);

// ═══════════════════════════════════════════════
// Let me also try the CORRECT approach per standard texts.
// The Lekhnitskii approach uses Φ_k(z_k) where the stresses are:
//   σx = 2Re[μ₁²Φ₁'(z₁) + μ₂²Φ₂'(z₂)]
// and Φ_k is the stress POTENTIAL (= F_k' in terms of Airy function).
//
// The hole perturbation of Φ_k is:
//   Φ_k^hole(z_k) = A_k / ζ_k   (or B_k·ln(ζ_k) depending on convention)
//
// Then Φ_k' = -A_k/ζ_k² · dζ/dz   ← this is what goes in the stress formula
//
// This means the ORIGINAL code was using the right level of derivative!
// The stress formula uses Φ' (first derivative of potential),
// and Φ = A/ζ is the potential itself.
//
// So the bug is NOT in the derivative level. Let me recheck the B coefficients.
//
// For Φ convention (Φ = F'):
// The far-field: Φ_k∞(z_k) = A_k·z_k  (linear)
//   σx∞ = 2Re[μ₁²A₁ + μ₂²A₂]
//   σy∞ = 2Re[A₁ + A₂]
//   τxy∞ = -2Re[μ₁A₁ + μ₂A₂]
//
// Solving for A₁, A₂ given σx∞, σy∞, τxy∞:
// 2Re[A₁ + A₂] = σy∞  ... (i)
// -2Re[μ₁A₁ + μ₂A₂] = τxy∞  ... (ii)
// 2Re[μ₁²A₁ + μ₂²A₂] = σx∞  ... (iii)
//
// For σy∞=100, σx∞=0, τxy∞=0, and μ₁=iβ₁, μ₂=iβ₂ (pure imaginary):
// A₁ + Ā₁ + A₂ + Ā₂ = 100 (only real parts)
// -(iβ₁A₁ - iβ₁Ā₁ + iβ₂A₂ - iβ₂Ā₂) = 0
// → β₁·Im(A₁) + β₂·Im(A₂) = 0 ... wait, that's not right either
// Actually: 2Re[μ₁A₁] = 2Re[(iβ₁)(a₁+ib₁)] = 2Re[iβ₁a₁ - β₁b₁] = -2β₁b₁
// So eq (ii): -2(-β₁·Im(A₁) - β₂·Im(A₂)) = 0 → β₁Im(A₁)+β₂Im(A₂) = 0
// For real A₁, A₂: Im(A₁)=Im(A₂)=0, so eq (ii) is auto-satisfied.
// Then eq (i): 2(A₁+A₂) = 100 → A₁+A₂ = 50
// And eq (iii): 2(-β₁²A₁ - β₂²A₂) = 0 → β₁²A₁ + β₂²A₂ = 0
// → A₁ = -β₂²A₂/β₁²
// → A₂(1 - β₂²/β₁²) = 50
// Hmm, but A₁,A₂ are complex in general...
//
// Actually for the orthotropic case where μ are purely imaginary,
// A₁ and A₂ can be real. Let me compute:
// A₁ + A₂ = 50
// β₁²A₁ + β₂²A₂ = 0
// → A₁ = -β₂²A₂/β₁²
// → -β₂²A₂/β₁² + A₂ = 50
// → A₂(1 - β₂²/β₁²) = 50
// → A₂ = 50/(1 - 23.95/0.734) = 50/(1-32.63) = 50/(-31.63) = -1.581
// → A₁ = 50 - (-1.581) = 51.581
//
// Check: β₁²·51.581 + β₂²·(-1.581) = 0.734·51.581 - 23.95·1.581 = 37.86 - 37.86 = 0 ✓

const A2_far = 50 / (1 - (mu2.im**2)/(mu1.im**2));
const A1_far = 50 - A2_far;
console.log(`\n═══ Far-field coefficients ═══`);
console.log(`A₁∞ = ${A1_far.toFixed(4)}`);
console.log(`A₂∞ = ${A2_far.toFixed(4)}`);

// The hole boundary condition for Φ convention:
// On the ellipse, the traction-free condition gives:
//   Φ₁^hole + Φ₂^hole = -Φ₁∞ - Φ₂∞ + const
//   μ₁Φ₁^hole + μ₂Φ₂^hole = -μ₁Φ₁∞ - μ₂Φ₂∞ + const
//
// On the boundary ζ=e^(iθ), the far-field part is:
//   Φ_k∞ = A_k · z_k = A_k · [(a-iμ_kb)/2·e^(iθ) + (a+iμ_kb)/2·e^(-iθ)]
//
// Matching Laurent terms (ζ⁻¹ term):
//   Φ_k^hole = C_k/ζ_k
//
// From boundary condition (ζ⁻¹ terms):
//   C₁ + C₂ = -A₁·(a+iμ₁b)/2 - A₂·(a+iμ₂b)/2
//   μ₁C₁ + μ₂C₂ = -μ₁A₁·(a+iμ₁b)/2 - μ₂A₂·(a+iμ₂b)/2

// Actually, let's be more careful. On the boundary (ζ_k = e^(iθ)):
// x = a cosθ, y = b sinθ
// z_k = a cosθ + μ_k b sinθ = (a-iμ_kb)/2 · e^(iθ) + (a+iμ_kb)/2 · e^(-iθ)
//
// So Φ_k∞ on boundary = A_k · [(a-iμ_kb)/2 · ζ + (a+iμ_kb)/2 · ζ⁻¹]
//
// The boundary condition (Lekhnitskii):
// Φ₁_total + Φ₂_total = prescribed   (on boundary)
// μ₁Φ₁_total + μ₂Φ₂_total = prescribed
//
// For traction-free hole:
// Φ₁_total + Φ₂_total = const  (on boundary)
// μ₁Φ₁_total + μ₂Φ₂_total = const  (on boundary)
//
// Φ_k_total = A_k[(a-iμ_kb)/2·ζ + (a+iμ_kb)/2·ζ⁻¹] + C_k·ζ⁻¹
//           = A_k(a-iμ_kb)/2·ζ + [A_k(a+iμ_kb)/2 + C_k]·ζ⁻¹
//
// For the sum to be constant (no θ-dependent terms):
// Coefficient of ζ (i.e., e^(iθ)):
//   A₁(a-iμ₁b)/2 + A₂(a-iμ₂b)/2 = 0   ... for first BC
//   Hmm, but that would constrain A₁,A₂ which are already determined by far-field.
//   This can't be right — the ζ terms don't vanish in general.
//
// OH WAIT. The boundary conditions involve CONJUGATES. Lekhnitskii's BCs are:
//   Φ₁(z₁) + Ā₂·Φ̄₂(z̄₂) = ... (involves conjugates!)
//
// This is getting really tangled. Let me use the SIMPLEST known correct approach.

console.log(`\n═══ SIMPLEST APPROACH: Direct boundary formula ═══`);
// For SCF at hole boundary under σy∞, the answer is KNOWN:
// SCF = 1 + β₁ + β₂ = 6.75
//
// The perturbation at (a+ε, 0) should approach this as ε→0.
// Our code gives SCF≈2.08 which means the perturbation potentials are ~3x too small.
//
// Looking at the original code more carefully:
//
// ORIGINAL CODE uses:
//   im_inv = {re:0, im:-1}  i.e. -i  (which is 1/(2i)·2 = -i, but should be 1/(2i))
//   Wait: 1/(2i) = 1/(2i) · (-2i)/(-2i) = -2i/(4i²+0) = -i/2... no, 1/(2i) = -i/2
//   So im_inv = {re:0, im:-1} is -i, but 1/(2i) = -i/2
//
//   THAT'S THE BUG! The code uses im_inv as -i but it should be -i/2!
//   Then multiplied by syL, it should give -i·syL/2 = coefficient of -σy/(2i)
//   But code does cscale(im_inv, syL) = -i·syL instead of -i·syL/2
//
//   Wait, let me re-read: the comment says "1/(2i) = -i/2" but im_inv = {re:0,im:-1}
//   which is -i, not -i/2. So there's a factor of 2 error!

// Alternatively, the factor of 2 could be compensated elsewhere.
// The stress formulas use 2·Re[...], so maybe the 2× cancels.
//
// Let me just compute with the factor-of-2 fix:
// C₁ = -i·syL/2 · den₂ / (μ₁-μ₂)  ← our formula with the /2
//    = -i·50 · (29.47) / (-4.037i)
//    = -i·50·29.47 / (-4.037i)
//    = 50·29.47/4.037
//    = 364.9
//
// vs. without the /2:
// = -i·100·29.47/(-4.037i) = 100·29.47/4.037 = 729.9
//
// Hmm but in the original code, the perturbation stress formula is:
//   dSigY = 2 * (phi1.re + phi2.re)
// which already has the factor 2. So the coefficient should NOT include 2.
//
// In our B-coefficient approach:
//   B₁ = [μ₂·(syL·a)] / [2(μ₁-μ₂)]  (for pure σy loading)
//   At boundary: Φ'|_{ζ=1} = -B₁/(β₁b)
//   Δσy = 2·Re[Φ₁' + Φ₂'] at ζ=1
//
// Let me compute: our B₁ = -303.04
// Φ₁'|_{ζ=1} = -(-303.04)/(0.857·5) = 303.04/4.283 = 70.77
// Similarly Φ₂'|_{ζ=1} = -(53.04)/(4.894·5) = -2.168
// Δσy = 2·(70.77 + (-2.168)) = 2·68.60 = 137.2
// Total σy = 237.2, SCF = 2.37
//
// But expected perturbation = (6.75-1)·100 = 575
// So we need Δσy = 575. We're getting 137.2.
// Ratio: 575/137.2 ≈ 4.19 = β₁β₂ = √(E1/E2)
//
// AH HA! The missing factor is β₁β₂!
//
// This suggests the potential should be Φ_k = B_k · ln(ζ_k), not B_k/ζ_k !
//
// With F_k = B_k·ln(ζ_k) (Airy function convention):
// F_k' = B_k · ζ_k'/ζ_k
// F_k'' = B_k · [ζ_k''/ζ_k - (ζ_k')²/ζ_k²]
//
// At ζ=1:
// F₁'' = B₁·[d²ζ₁/dz² - (dζ₁/dz)²]
//       = -303.04·[-0.009126 - 0.05452]
//       = -303.04·(-0.06365) = 19.28
//
// Hmm, that gives even less.
//
// Wait, I'm confusing conventions. Let me carefully distinguish:
// Convention A (Muskhelishvili-like): σy = 2Re[Φ₁'(z₁) + Φ₂'(z₂)]
// Convention B (Lekhnitskii): σy = ∂²U/∂x² where U = 2Re[F₁(z₁)+F₂(z₂)]
//   → σy = 2Re[F₁'' + F₂'']
//
// In convention A, Φ is the "potential" and its derivative Φ' enters stress.
// In convention B, F is the "stress function" and F'' enters stress.
// If Φ = F', then Φ' = F'', and both conventions agree.
//
// In our code, if we set Φ_k^pert = B_k/ζ_k, then:
// Φ_k' = -B_k/ζ_k² · dζ/dz   ← this enters stress formula
//
// This is what the code computes. BUT maybe the potential should be
// Φ_k = B_k · something_else / ζ_k ?
//
// Going back to the boundary conditions I derived:
//   B₁ + B₂ = -(syL·a)/2 = -250    ✓ (verified)
//   μ₁B₁ + μ₂B₂ = 0                 ✓ (verified)
//
// These BCs come from:
//   Φ₁^pert + Φ₂^pert = -(something)  on boundary
//
// At ζ=1: Φ_k = B_k/ζ = B_k
// So: B₁ + B₂ = -(σy·a - i·τxy·b)/2 = -250  ✓
//
// This is the standard result for the Muskhelishvili-style Φ potential.
// The BCs are correct, the potential form is correct.
// Something must be wrong with the derivative.
//
// Let me compute the EXPECTED Φ₁' at the boundary:
// σy at boundary = σy∞ + 2Re[Φ₁' + Φ₂'] = 6.75 · σy∞
// → 2Re[Φ₁' + Φ₂'] = 5.75 · 100 = 575
// → Re[Φ₁' + Φ₂'] = 287.5
//
// We got: Φ₁' + Φ₂' = 70.77 + (-2.17) = 68.6
// Expected: 287.5
// Ratio: 287.5/68.6 = 4.19 ≈ β₁β₂
//
// So somehow we're missing a factor of β₁β₂ ≈ 4.19.
//
// Wait — maybe the issue is that the mapping ζ_k is defined differently.
// Standard mapping: z_k = (a/2)(ζ + ζ⁻¹) + (iμ_kb/2)(ζ - ζ⁻¹) ... no
//
// Actually from Lekhnitskii, the mapping is:
//   z_k = (1/2)(a - iμ_kb)ζ_k + (1/2)(a + iμ_kb)ζ_k⁻¹
//
// For μ₁ = iβ₁: a - iμ₁b = a + β₁b
// At ζ₁=1: z₁ = (a+β₁b)/2 + (a-β₁b)/2 = a ✓
//
// dz₁/dζ₁ = (a+β₁b)/2 - (a-β₁b)/2 · ζ₁⁻²
// At ζ₁=1: = (a+β₁b)/2 - (a-β₁b)/2 = β₁b
//
// So dζ₁/dz₁|_{ζ=1} = 1/(β₁b) ✓ (matches what I had)
//
// Now, Φ₁^pert = B₁/ζ₁
// dΦ₁/dζ₁ = -B₁/ζ₁²
// Φ₁' = dΦ₁/dz₁ = (dΦ₁/dζ₁)(dζ₁/dz₁) = -B₁/ζ₁² · 1/(dz₁/dζ₁)
// At ζ=1: = -B₁/(β₁b) = 303.04/(0.857·5) = 70.77 ✓
//
// So the computation is correct for what it is. The issue must be in the BCs.
// Our BCs give B₁+B₂ = -250, but maybe they should give something larger.
//
// Hmm, let me look up the ACTUAL Lekhnitskii boundary conditions more carefully.
// The traction-free hole requires:
//   ∮ (σ_n · ds) = 0  on hole boundary
//
// In Lekhnitskii's formulation, the BCs on the potentials are:
//   Φ₁(t₁) + Φ₂(t₂) + x̄(t)·p₁ + ȳ(t)·q₁ = C₁  (complex constant)
//   μ₁Φ₁(t₁) + μ₂Φ₂(t₂) + x̄(t)·p₂ + ȳ(t)·q₂ = C₂
//
// Wait, the BCs involve the stress resultants, which for far-field loading:
//   The tractions on the hole from the far-field are:
//   X_n = σx∞·nx + τxy∞·ny
//   Y_n = τxy∞·nx + σy∞·ny
//
// Integrating around boundary:
//   ∫ Y_n ds = σy∞ · Δx + τxy∞ · Δy
//   ∫ X_n ds = σx∞ · Δy + τxy∞ · Δx  (accumulated around a full loop = 0? no...)
//
// Actually the conditions are:
//   Φ₁ + Φ₂ + conjugates = -(1/2)∫(Xn + iYn)ds
//
// For the Airy function approach (Lekhnitskii §35):
//   F₁'(t₁) + F₂'(t₂) + F̄₁'(t̄₁) + F̄₂'(t̄₂) = ∫(Y_n)ds + const
//
// This involves CONJUGATES which is the standard Lekhnitskii BC.
// Let me write it properly:
//   Φ₁(t₁) + Φ₂(t₂) + conj[Φ₁(t₁)] + conj[Φ₂(t₂)] = ...
//   Which is: 2Re[Φ₁+Φ₂] = prescribed
//
// Hmm no, that's also not right because t₁ ≠ t̄₁ in general.
//
// I think the fundamental issue is that Lekhnitskii's BCs involve both
// Φ and its conjugate Φ̄, evaluated at DIFFERENT points (z₁, z̄₁, z₂, z̄₂).
// On the boundary of the unit circle ζ=e^(iθ), ζ̄=e^(-iθ)=ζ⁻¹.
// So the conjugate evaluation involves 1/ζ terms too.
//
// This means the 1/ζ perturbation interacts with the conjugate terms,
// and the boundary conditions I wrote above are INCOMPLETE — they don't
// account for the conjugate terms.

// ═══════════════════════════════════════════════
// OK let me just use the DEFINITIVE known-correct result from a textbook.
// From Tan, S.C., "Stress Concentrations in Laminated Composites" (1994),
// eq. 3.34-3.35:
//
// For an orthotropic plate with elliptical hole (a along x, b along y),
// under far-field stress σx∞, σy∞, τxy∞:
//
// The potentials are:
//   Φ₁ = Γ₁/ζ₁,  Φ₂ = Γ₂/ζ₂
//
// where:
//   Γ₁ = (1/(μ₁-μ₂)) · [σy∞·(a-iμ₂b)/2 - σx∞·μ₂·(a-iμ₂b)/(2μ₁) + ...]
//
// Hmm, this also gets complicated. Let me try a completely different approach:
// use NUMERICAL boundary checking.

console.log(`\n═══ NUMERICAL BC CHECK ═══`);
// The traction on the hole should be zero. At boundary point (a, 0):
// σy(a,0) is the normal stress (pointing outward = y-direction? no, it's radial)
// Actually at (a, 0) on a circular hole, the normal is in the x-direction.
// σ_nn = σ_x at (a,0)
// τ_nt = τ_xy at (a,0)
// So the traction-free condition requires σ_x(a,0) = 0 and τ_xy(a,0) = 0.
// NOT σ_y = 0! σ_y at (a,0) is the TANGENTIAL stress = σ_θ.

// So let me check: does our solution give σ_x(a+ε, 0) → 0 as ε→0?
// From our computation at x=5.5:
// Δσx = 2Re[μ₁²Φ₁' + μ₂²Φ₂'] = 2(-β₁²·70.77 + (-β₂²)·(-2.168))
//      = 2(-0.734·70.77 + 23.95·2.168)
//      = 2(-51.95 + 51.91) = 2(-0.04) = -0.08 ≈ 0 ✓
// Good — σx perturbation cancels to give near-zero at boundary.
// Total σx ≈ σx∞ + (-0.08) = 0 + (-0.08) ≈ 0 ✓

// So σ_x → 0 at hole boundary ✓ (traction-free condition satisfied!)
// And σ_y = 100 + 137.2 = 237.2 at x=5.5

// But wait — at x=5.01 (closer to boundary), the SCF should be closer to 6.75.
// Our earlier test showed SCF=1.0 at x=5.01 — that was with the old (buggy) formula.
// Let me compute with the corrected B coefficients approach at x=5.01.

const x2 = 5.01;
const z_k = {re: x2, im: 0};
const inner_1 = {re: x2*x2 - 25 + mu1.im*mu1.im*25, im: 0};
const inner_2 = {re: x2*x2 - 25 + mu2.im*mu2.im*25, im: 0};
const s_1 = C.sqrt(inner_1);
const s_2 = C.sqrt(inner_2);
const D_1 = {re: a + mu1.im*b, im: 0};
const D_2 = {re: a + mu2.im*b, im: 0};
let zeta_1 = C.div(C.add(z_k, s_1), D_1);
let zeta_2 = C.div(C.add(z_k, s_2), D_2);
if (C.mag(zeta_1) < 1) zeta_1 = C.div(C.sub(z_k, s_1), D_1);
if (C.mag(zeta_2) < 1) zeta_2 = C.div(C.sub(z_k, s_2), D_2);

console.log(`\nAt x=${x2}:`);
console.log(`  ζ₁=${C.str(zeta_1)}, |ζ₁|=${C.mag(zeta_1).toFixed(6)}`);
console.log(`  ζ₂=${C.str(zeta_2)}, |ζ₂|=${C.mag(zeta_2).toFixed(6)}`);

// dζ/dz = [1 + z/S] / D
const dz1 = C.div(C.add({re:1,im:0}, C.div(z_k, s_1)), D_1);
const dz2_v = C.div(C.add({re:1,im:0}, C.div(z_k, s_2)), D_2);

const zi1_2 = C.mul(C.div({re:1,im:0}, zeta_1), C.div({re:1,im:0}, zeta_1));
const zi2_2 = C.mul(C.div({re:1,im:0}, zeta_2), C.div({re:1,im:0}, zeta_2));

const p1 = C.mul(C.scale({re:-303.04,im:0}, -1), C.mul(zi1_2, dz1));
const p2 = C.mul(C.scale({re:53.04,im:0}, -1), C.mul(zi2_2, dz2_v));

const dsY = 2*(p1.re + p2.re);
const dsX = 2*(C.mul(mu1sq,p1).re + C.mul(mu2sq,p2).re);
console.log(`  Φ₁'=${C.str(p1)}`);
console.log(`  Φ₂'=${C.str(p2)}`);
console.log(`  Δσy = ${dsY.toFixed(2)}`);
console.log(`  Δσx = ${dsX.toFixed(2)}`);
console.log(`  Total σy = ${(100+dsY).toFixed(2)}, SCF = ${((100+dsY)/100).toFixed(4)}`);
console.log(`  Total σx = ${dsX.toFixed(2)} (expect ≈0 for traction-free)`);
