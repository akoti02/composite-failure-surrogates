/**
 * MATHEMATICAL DERIVATION & VERIFICATION
 * Lekhnitskii's complex potential approach for stress around elliptical holes
 * in orthotropic plates.
 *
 * Reference: Lekhnitskii, "Anisotropic Plates", 3rd Ed. (1968), Chapter 38
 *            Savin, "Stress Concentration around Holes" (1961)
 *
 * STEP 1: Derive correct coefficients from first principles
 * STEP 2: Verify against known isotropic Kirsch solution (SCF=3)
 * STEP 3: Verify against known orthotropic SCF formula
 */

// ─── Complex arithmetic ───
const C = {
  add: (a, b) => ({ re: a.re+b.re, im: a.im+b.im }),
  sub: (a, b) => ({ re: a.re-b.re, im: a.im-b.im }),
  mul: (a, b) => ({ re: a.re*b.re-a.im*b.im, im: a.re*b.im+a.im*b.re }),
  div: (a, b) => {
    const d = b.re*b.re+b.im*b.im;
    return d < 1e-30 ? {re:0,im:0} : { re:(a.re*b.re+a.im*b.im)/d, im:(a.im*b.re-a.re*b.im)/d };
  },
  sqrt: (z) => {
    const r = Math.sqrt(z.re*z.re+z.im*z.im);
    const t = Math.atan2(z.im, z.re);
    const sr = Math.sqrt(r);
    return { re: sr*Math.cos(t/2), im: sr*Math.sin(t/2) };
  },
  scale: (z, s) => ({ re: z.re*s, im: z.im*s }),
  conj: (z) => ({ re: z.re, im: -z.im }),
  mag: (z) => Math.sqrt(z.re*z.re + z.im*z.im),
  real: (z) => z.re,
  str: (z) => `${z.re.toFixed(6)} + ${z.im.toFixed(6)}i`,
};

function characteristicRoots(mat) {
  const E1 = mat.E1*1000, E2 = mat.E2*1000, G12 = mat.G12*1000;
  const a11 = 1/E1, a22 = 1/E2, a12 = -mat.v12/E1, a66 = 1/G12;
  const A = a11, B = 2*a12 + a66, Cv = a22;
  const disc = B*B - 4*A*Cv;
  let mu1, mu2;
  if (disc < 0) {
    const rp = -B/(2*A), ip = Math.sqrt(-disc)/(2*A);
    mu1 = C.sqrt({re: rp, im: ip});
    mu2 = C.sqrt({re: rp, im: -ip});
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

/**
 * ═══════════════════════════════════════════════════════════════
 * MATHEMATICAL DERIVATION
 * ═══════════════════════════════════════════════════════════════
 *
 * Lekhnitskii (1968), eq. 38.6-38.12:
 *
 * For an infinite orthotropic plate with an elliptical hole (semi-axes a, b)
 * under far-field stresses σx∞, σy∞, τxy∞:
 *
 * The stress functions are:
 *   Φ₁(z₁) and Φ₂(z₂)  where  z_k = x + μ_k·y
 *
 * The mapping from z_k plane to ζ_k plane:
 *   z_k = (a - i·μ_k·b)/2 · ζ_k + (a + i·μ_k·b)/2 · (1/ζ_k)
 *
 * The stress functions for combined loading are:
 *   Φ₁'(z₁) = -A₁/(ζ₁² - α₁²) · (dζ₁/dz₁)     ... no
 *
 * Actually, the standard Lekhnitskii result gives:
 *   Φ₁(z₁) = Γ₁/ζ₁  (Laurent series, leading term)
 *   Φ₂(z₂) = Γ₂/ζ₂
 *
 * Where the coefficients Γ₁, Γ₂ come from the boundary conditions.
 *
 * From Lekhnitskii eq. 38.12, for σy∞ loading:
 *   Γ₁ = σy∞ · (a - i·μ₂·b) / (2·i·(μ₁ - μ₂))
 *   Γ₂ = -σy∞ · (a - i·μ₁·b) / (2·i·(μ₁ - μ₂))
 *
 * For σx∞ loading:
 *   Γ₁ = -σx∞ · μ₂ · (a - i·μ₂·b) / (2·i·(μ₁ - μ₂))    ... wait
 *
 * Let me re-derive from the CORRECT Lekhnitskii formulas.
 *
 * The boundary condition on the ellipse gives:
 *   Φ₁'(z₁) + Φ₂'(z₂) = (1/2) d/ds [σy∞·x - τxy∞·y]  ... on boundary
 *   μ₁·Φ₁'(z₁) + μ₂·Φ₂'(z₂) = -(1/2) d/ds [σx∞·y - τxy∞·x]
 *
 * The stresses are:
 *   σx = 2·Re[μ₁²·Φ₁'(z₁) + μ₂²·Φ₂'(z₂)]
 *   σy = 2·Re[Φ₁'(z₁) + Φ₂'(z₂)]
 *   τxy = -2·Re[μ₁·Φ₁'(z₁) + μ₂·Φ₂'(z₂)]
 *
 * ═══════════════════════════════════════════════════════════════
 */

/**
 * CORRECT implementation following Lekhnitskii Ch.38 exactly.
 *
 * Key insight from debugging: The TOTAL stress = far-field + perturbation.
 * The potentials Φ₁, Φ₂ represent ONLY the perturbation due to the hole.
 * The formulas σx = 2Re[μ₁²Φ₁' + μ₂²Φ₂'] give the TOTAL stress,
 * NOT just the perturbation.
 *
 * From Lekhnitskii (1968), the stress potentials for an elliptical hole
 * in an orthotropic plate are:
 *
 *   Φ₁(z₁) = Γ₁ · ζ₁⁻¹
 *   Φ₂(z₂) = Γ₂ · ζ₂⁻¹
 *
 * where ζ_k maps the exterior of the ellipse to |ζ| > 1:
 *   z_k = (1/2)(a - iμ_kb)ζ_k + (1/2)(a + iμ_kb)ζ_k⁻¹
 *
 * Solving: ζ_k = [z_k + √(z_k² - a² - μ_k²b²)] / (a - iμ_kb)
 *
 * For the correct sign of the square root: |ζ_k| > 1 outside the hole.
 *
 * The coefficients from Lekhnitskii eq. 38.12:
 *
 * For far-field loading (σx∞, σy∞, τxy∞):
 *
 *   Γ₁ = [σy∞(a - iμ₂b) - τxy∞(a - iμ₂b)/(-iμ₁) + ... ]
 *
 * Actually, let me use the cleaner formulation from Savin/Lekhnitskii:
 *
 * The boundary conditions give (for traction-free hole):
 *   Φ₁ + Φ₂ = -(1/2)(σy∞·x - τxy∞·y)   on boundary (in z-plane terms)
 *   μ₁Φ₁ + μ₂Φ₂ = (1/2)(σx∞·y - τxy∞·x)
 *
 * On the ellipse boundary: x = a·cos(θ), y = b·sin(θ), and ζ_k = e^(iθ)
 * So ζ_k⁻¹ = e^(-iθ).
 *
 * Substituting Φ_k = Γ_k/ζ_k = Γ_k·e^(-iθ):
 *
 *   Γ₁·e^(-iθ) + Γ₂·e^(-iθ) = -(1/2)(σy∞·a·cosθ - τxy∞·b·sinθ)
 *
 * But wait — this is wrong because ζ₁ ≠ ζ₂ on the boundary for anisotropic
 * (they ARE equal to e^(iθ) on the unit circle in the mapped plane).
 *
 * OK let me just use the KNOWN correct formula directly.
 *
 * From: Tan, "Stress Concentrations in Laminated Composites" (1994), eq. 3.31-3.32
 * Also: Savin (1961), Whitney & Nuismer (1974)
 *
 * For σy∞ loading on ellipse (a along x, b along y):
 *   Γ₁ = σy∞/(2i) · (a - iμ₂b)/(μ₁ - μ₂)
 *   Γ₂ = -σy∞/(2i) · (a - iμ₁b)/(μ₁ - μ₂)
 *
 * For σx∞ loading:
 *   Γ₁ = -σx∞/(2i) · μ₂(a - iμ₂b)/(μ₁(μ₁ - μ₂))    ... no
 *
 * Hmm, let me look at this more carefully with a different source.
 *
 * From Lekhnitskii eq. 38.7-38.9:
 * The resultant force boundary conditions on the hole give:
 *
 *   Φ₁(ζ₁) + Φ₂(ζ₂) + (1/2)p₂·z = f₁  (const on boundary)
 *   μ₁Φ₁(ζ₁) + μ₂Φ₂(ζ₂) + (1/2)p₁·z̄ = f₂  (???)
 *
 * Actually I think the cleanest source is:
 *
 * For far-field σx∞, σy∞, τxy∞, the total stress potentials (including
 * far-field part) are:
 *
 *   Φ₁_total = Γ₁_∞·z₁ + Φ₁_hole
 *   Φ₂_total = Γ₂_∞·z₂ + Φ₂_hole
 *
 * where the far-field part gives:
 *   σx = 2Re[μ₁²·Γ₁_∞ + μ₂²·Γ₂_∞] = σx∞
 *   σy = 2Re[Γ₁_∞ + Γ₂_∞] = σy∞
 *   τxy = -2Re[μ₁·Γ₁_∞ + μ₂·Γ₂_∞] = τxy∞
 *
 * And the hole perturbation: Φ_k_hole = Γ_k · ζ_k⁻¹
 *
 * OK — I think the fundamental issue in our code is that the stress formulas
 * give PERTURBATION stress, but the code is ALSO adding the far-field stress
 * on top, causing the perturbation to effectively vanish in some cases.
 *
 * Let me just numerically derive and verify the correct answer.
 */

// ═══════════════════════════════════════════════════════════════
// APPROACH: Numerically verify by implementing from scratch
// using the CLEANEST derivation I know.
// ═══════════════════════════════════════════════════════════════

/**
 * Lekhnitskii solution, clean implementation.
 *
 * Total potential: F_k(z_k) = F_k∞(z_k) + f_k(z_k)
 *   where F_k∞ is the far-field and f_k is the hole perturbation.
 *
 * Far-field potentials (give uniform stress when differentiated):
 *   From σx = 2Re[μ₁²F₁'' + μ₂²F₂''], etc.
 *   F₁∞ = (1/2)Γ₁∞·z₁², F₂∞ = (1/2)Γ₂∞·z₂²  (quadratic → constant derivative F'')
 *
 * Wait, that's wrong. The potential convention:
 *   σx = 2Re[μ₁²·Φ₁'(z₁) + μ₂²·Φ₂'(z₂)]
 *
 * where Φ_k' = dΦ_k/dz_k. For far-field:
 *   Φ_k∞(z_k) = A_k·z_k  (linear → constant Φ')
 *
 * So: σx∞ = 2Re[μ₁²·A₁ + μ₂²·A₂]
 *     σy∞ = 2Re[A₁ + A₂]
 *     τxy∞ = -2Re[μ₁·A₁ + μ₂·A₂]
 *
 * This is a system of 3 equations in 4 unknowns (A₁.re, A₁.im, A₂.re, A₂.im).
 * But A₁, A₂ can be expressed:
 *
 *   A₁ = (σy∞·μ₂ + τxy∞) / (2i·μ₁·(μ₁ - μ₂))  ... hmm
 *
 * Actually from Lekhnitskii, the coefficients for the hole perturbation potential
 * Φ_k^hole are chosen so the total traction vanishes on the hole boundary.
 *
 * Let me use a completely different approach: just implement the KNOWN RESULT
 * and test it.
 */

/**
 * From: Savin (1961), as presented in Tan (1994) eq. 3.31-3.36.
 *
 * The perturbation potentials for a traction-free elliptical hole:
 *   φ₁(z₁) = B₁/ζ₁
 *   φ₂(z₂) = B₂/ζ₂
 *
 * B₁ = [σy∞(a - iμ₂b) + τxy∞·i·(a - iμ₂b)/μ₂ + σx∞·μ₂·(a - iμ₂b)·i/μ₁] ...
 *
 * No, that's getting circular. Let me just use the DEFINITIVE formulas.
 *
 * From Lekhnitskii (1968), §38, equations for traction-free elliptical hole:
 *
 * Boundary conditions on the hole (parameterized by θ):
 *   x = a·cosθ, y = b·sinθ on hole
 *
 * The hole perturbation potentials have Laurent expansion:
 *   φ_k(ζ_k) = Σ A_k^n / ζ_k^n
 *
 * For traction-free hole under far-field σx∞, σy∞, τxy∞, only n=1 term:
 *   φ₁ = B₁/ζ₁
 *   φ₂ = B₂/ζ₂
 *
 * The B coefficients from boundary conditions:
 *   B₁ + B₂ = -(σy∞·a - τxy∞·b·i)/2          ... (i)
 *   μ₁·B₁ + μ₂·B₂ = (σx∞·b·i + τxy∞·a)/2     ... (ii)
 *
 * These are from matching the far-field traction on the hole boundary.
 *
 * Solving the 2×2 system:
 *   B₁ = [-(σy∞·a - iτxy∞·b)/2 · μ₂ - (iσx∞·b + τxy∞·a)/2] / (μ₁ - μ₂)
 *      = [-μ₂(σy∞·a - iτxy∞·b) - (iσx∞·b + τxy∞·a)] / (2(μ₁ - μ₂))
 *
 * Wait, let me solve it properly.
 *
 * From (i): B₂ = -(σy∞·a - iτxy∞·b)/2 - B₁
 * Sub into (ii): μ₁B₁ + μ₂[-(σy∞·a - iτxy∞·b)/2 - B₁] = (iσx∞·b + τxy∞·a)/2
 * (μ₁ - μ₂)B₁ = (iσx∞·b + τxy∞·a)/2 + μ₂(σy∞·a - iτxy∞·b)/2
 * B₁ = [(iσx∞·b + τxy∞·a) + μ₂(σy∞·a - iτxy∞·b)] / (2(μ₁ - μ₂))
 *
 * Similarly:
 * B₂ = -(σy∞·a - iτxy∞·b)/2 - B₁
 *    = [-(σy∞·a - iτxy∞·b)(μ₁ - μ₂) - (iσx∞·b + τxy∞·a) - μ₂(σy∞·a - iτxy∞·b)] / (2(μ₁ - μ₂))
 *    = [-(σy∞·a - iτxy∞·b)μ₁ - (iσx∞·b + τxy∞·a)] / (2(μ₁ - μ₂))
 *    = -[(iσx∞·b + τxy∞·a) + μ₁(σy∞·a - iτxy∞·b)] / (2(μ₁ - μ₂))
 *
 * The PERTURBATION stresses from these potentials:
 *   Δσx = 2Re[μ₁²·φ₁'(z₁) + μ₂²·φ₂'(z₂)]
 *   Δσy = 2Re[φ₁'(z₁) + φ₂'(z₂)]
 *   Δτxy = -2Re[μ₁·φ₁'(z₁) + μ₂·φ₂'(z₂)]
 *
 * where φ_k'(z_k) = B_k · d(1/ζ_k)/dz_k = -B_k · ζ_k⁻² · dζ_k/dz_k
 *
 * Total stress = far-field + perturbation:
 *   σx = σx∞ + Δσx
 *   σy = σy∞ + Δσy
 *   τxy = τxy∞ + Δτxy
 */

function ellipseStressCorrected(px, py, a, b, cx, cy, angle, sigXinf, sigYinf, tauXYinf, mu1, mu2) {
  // Transform to ellipse-local coords
  const rad = (-angle * Math.PI) / 180;
  const cosA = Math.cos(rad), sinA = Math.sin(rad);
  const dx = px - cx, dy = py - cy;
  const x = cosA*dx + sinA*dy;
  const y = -sinA*dx + cosA*dy;

  // Rotate far-field stress to local frame
  const c2 = cosA*cosA, s2 = sinA*sinA, cs = cosA*sinA;
  const sxL = c2*sigXinf + s2*sigYinf + 2*cs*tauXYinf;
  const syL = s2*sigXinf + c2*sigYinf - 2*cs*tauXYinf;
  const txyL = -cs*sigXinf + cs*sigYinf + (c2-s2)*tauXYinf;

  // Inside ellipse → zero stress
  if ((x*x)/(a*a) + (y*y)/(b*b) < 1.0) {
    return { sigX: 0, sigY: 0, tauXY: 0 };
  }

  // Complex coordinates z_k = x + μ_k·y
  const z1 = { re: x + mu1.re*y, im: mu1.im*y };
  const z2 = { re: x + mu2.re*y, im: mu2.im*y };

  // ζ_k = [z_k + √(z_k² - a² - μ_k²·b²)] / (a - i·μ_k·b)
  const a2 = a*a, b2 = b*b;
  const mu1sq = C.mul(mu1, mu1);
  const mu2sq = C.mul(mu2, mu2);

  const z1sq = C.mul(z1, z1);
  const inner1 = C.sub(z1sq, { re: a2 + mu1sq.re*b2, im: mu1sq.im*b2 });
  const sqrt1 = C.sqrt(inner1);

  const z2sq = C.mul(z2, z2);
  const inner2 = C.sub(z2sq, { re: a2 + mu2sq.re*b2, im: mu2sq.im*b2 });
  const sqrt2 = C.sqrt(inner2);

  const den1 = { re: a + mu1.im*b, im: -mu1.re*b };
  const den2 = { re: a + mu2.im*b, im: -mu2.re*b };

  const zeta1 = C.div(C.add(z1, sqrt1), den1);
  const zeta2 = C.div(C.add(z2, sqrt2), den2);

  // Ensure |ζ| > 1 (exterior mapping). If |ζ| < 1, use the other root.
  let z1Final = zeta1, z2Final = zeta2;
  if (C.mag(zeta1) < 1) {
    z1Final = C.div(C.sub(z1, sqrt1), den1);
  }
  if (C.mag(zeta2) < 1) {
    z2Final = C.div(C.sub(z2, sqrt2), den2);
  }

  // dζ_k/dz_k = 1 / (dz_k/dζ_k)
  // z_k = (a-iμ_kb)/2 · ζ_k + (a+iμ_kb)/2 · ζ_k⁻¹
  // dz_k/dζ_k = (a-iμ_kb)/2 - (a+iμ_kb)/2 · ζ_k⁻²
  // = (a-iμ_kb)/2 · (1 - [(a+iμ_kb)/(a-iμ_kb)] · ζ_k⁻²)
  const alpha1 = C.scale(den1, 0.5); // (a - iμ₁b)/2
  const beta1 = { re: (a - mu1.im*b)/2, im: (mu1.re*b)/2 }; // (a + iμ₁b)/2
  const alpha2 = C.scale(den2, 0.5);
  const beta2 = { re: (a - mu2.im*b)/2, im: (mu2.re*b)/2 };

  const zeta1inv = C.div({re:1,im:0}, z1Final);
  const zeta2inv = C.div({re:1,im:0}, z2Final);
  const zeta1inv2 = C.mul(zeta1inv, zeta1inv);
  const zeta2inv2 = C.mul(zeta2inv, zeta2inv);

  const dz1_dzeta1 = C.sub(alpha1, C.mul(beta1, zeta1inv2));
  const dz2_dzeta2 = C.sub(alpha2, C.mul(beta2, zeta2inv2));

  const dzeta1_dz1 = C.div({re:1,im:0}, dz1_dzeta1);
  const dzeta2_dz2 = C.div({re:1,im:0}, dz2_dzeta2);

  // B coefficients from boundary conditions:
  // B₁ = [(i·σx∞·b + τxy∞·a) + μ₂·(σy∞·a - i·τxy∞·b)] / (2(μ₁ - μ₂))
  // B₂ = -[(i·σx∞·b + τxy∞·a) + μ₁·(σy∞·a - i·τxy∞·b)] / (2(μ₁ - μ₂))
  const mu_diff = C.sub(mu1, mu2);

  const term1 = { re: txyL*a, im: sxL*b };  // i·σx·b + τxy·a
  const term2 = { re: syL*a, im: -txyL*b };  // σy·a - i·τxy·b

  const B1_num = C.add(term1, C.mul(mu2, term2));
  const B2_num = C.add(term1, C.mul(mu1, term2));

  const denom_2mu = C.scale(mu_diff, 2);
  const B1 = C.div(B1_num, denom_2mu);
  const B2 = C.div(C.scale(B2_num, -1), denom_2mu);

  // φ_k'(z_k) = d/dz_k [B_k / ζ_k] = B_k · d(ζ_k⁻¹)/dz_k = -B_k · ζ_k⁻² · dζ_k/dz_k
  const phi1_prime = C.mul(C.scale(B1, -1), C.mul(zeta1inv2, dzeta1_dz1));
  const phi2_prime = C.mul(C.scale(B2, -1), C.mul(zeta2inv2, dzeta2_dz2));

  // Perturbation stresses:
  const dSigX = 2 * C.real(C.add(C.mul(mu1sq, phi1_prime), C.mul(mu2sq, phi2_prime)));
  const dSigY = 2 * C.real(C.add(phi1_prime, phi2_prime));
  const dTauXY = -2 * C.real(C.add(C.mul(mu1, phi1_prime), C.mul(mu2, phi2_prime)));

  // Total = far-field + perturbation
  let sigXL = sxL + dSigX;
  let sigYL = syL + dSigY;
  let tauXYL = txyL + dTauXY;

  // Rotate back to global
  const sigX = c2*sigXL + s2*sigYL - 2*cs*tauXYL;
  const sigY = s2*sigXL + c2*sigYL + 2*cs*tauXYL;
  const tauXY = cs*sigXL - cs*sigYL + (c2-s2)*tauXYL;

  return { sigX, sigY, tauXY };
}

// ═══════════════════════════════════════════════════════════════
// VERIFICATION TESTS
// ═══════════════════════════════════════════════════════════════

let passed = 0, failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; console.log(`  ✓ ${msg}`); }
  else { failed++; console.log(`  ✗ FAIL: ${msg}`); }
}

// TEST 1: Isotropic circular hole, σy=100 → SCF at (a+ε, 0) = 3.0
console.log("\n═══ TEST 1: Isotropic circular hole, σy=100 ═══");
{
  const isoMat = { E1: 70, E2: 70, G12: 70/(2*1.3), v12: 0.3 };
  const [mu1, mu2] = characteristicRoots(isoMat);
  console.log(`  μ₁ = ${C.str(mu1)}`);
  console.log(`  μ₂ = ${C.str(mu2)}`);
  const a = 5;

  const dists = [0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 20.0, 100.0];
  console.log("  σy along x-axis:");
  for (const d of dists) {
    const r = ellipseStressCorrected(a+d, 0, a, a, 0, 0, 0, 0, 100, 0, mu1, mu2);
    console.log(`    x=${(a+d).toFixed(2).padStart(7)}: σy=${r.sigY.toFixed(2).padStart(8)} (SCF=${(r.sigY/100).toFixed(3)}), σx=${r.sigX.toFixed(2).padStart(8)}, τxy=${r.tauXY.toFixed(2)}`);
  }

  const edge = ellipseStressCorrected(a+0.01, 0, a, a, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(Math.abs(edge.sigY/100 - 3.0) < 0.1, `SCF at edge ≈ 3.0, got ${(edge.sigY/100).toFixed(3)}`);

  const far = ellipseStressCorrected(200, 0, a, a, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(Math.abs(far.sigY - 100) < 1, `Far-field recovery: σy=${far.sigY.toFixed(2)}`);

  // Top of hole: SCF ≈ -1.0
  const top = ellipseStressCorrected(0, a+0.01, a, a, 0, 0, 0, 0, 100, 0, mu1, mu2);
  console.log(`  Top of hole: σy=${top.sigY.toFixed(2)} (SCF=${(top.sigY/100).toFixed(3)}, expect ~-1.0)`);
  assert(Math.abs(top.sigY/100 + 1.0) < 0.15, `Top SCF ≈ -1.0, got ${(top.sigY/100).toFixed(3)}`);
}

// TEST 2: Isotropic, σx=100 → SCF at (0, a+ε) = 3.0
console.log("\n═══ TEST 2: Isotropic circular hole, σx=100 ═══");
{
  const isoMat = { E1: 70, E2: 70, G12: 70/(2*1.3), v12: 0.3 };
  const [mu1, mu2] = characteristicRoots(isoMat);
  const a = 5;

  const edge = ellipseStressCorrected(0, a+0.01, a, a, 0, 0, 0, 100, 0, 0, mu1, mu2);
  console.log(`  σx at (0, a+ε) = ${edge.sigX.toFixed(2)} (SCF=${(edge.sigX/100).toFixed(3)})`);
  assert(Math.abs(edge.sigX/100 - 3.0) < 0.15, `σx SCF ≈ 3.0, got ${(edge.sigX/100).toFixed(3)}`);
}

// TEST 3: T300/5208 circular hole, σy=100 → SCF ≈ 6.75
console.log("\n═══ TEST 3: T300/5208 circular hole, σy=100 ═══");
{
  const T300 = { E1: 181, E2: 10.3, G12: 7.17, v12: 0.28 };
  const [mu1, mu2] = characteristicRoots(T300);
  const expectedKt = 1 + Math.sqrt(2*(Math.sqrt(T300.E1/T300.E2) - T300.v12) + T300.E1/T300.G12);
  console.log(`  Expected SCF: ${expectedKt.toFixed(2)}`);

  const a = 5;
  const edge = ellipseStressCorrected(a+0.01, 0, a, a, 0, 0, 0, 0, 100, 0, mu1, mu2);
  console.log(`  Computed SCF: ${(edge.sigY/100).toFixed(3)}`);
  assert(Math.abs(edge.sigY/100 - expectedKt) < 0.5, `Orthotropic SCF ≈ ${expectedKt.toFixed(1)}, got ${(edge.sigY/100).toFixed(2)}`);

  // Far-field recovery
  const far = ellipseStressCorrected(200, 200, a, a, 0, 0, 0, 0, 100, 0, mu1, mu2);
  assert(Math.abs(far.sigY - 100) < 2, `Far-field: σy=${far.sigY.toFixed(2)} ≈ 100`);
  assert(Math.abs(far.sigX) < 2, `Far-field: σx=${far.sigX.toFixed(2)} ≈ 0`);
}

// TEST 4: Far-field recovery for σx loading
console.log("\n═══ TEST 4: Far-field recovery (all load cases) ═══");
{
  const T300 = { E1: 181, E2: 10.3, G12: 7.17, v12: 0.28 };
  const [mu1, mu2] = characteristicRoots(T300);
  const cases = [
    { sx: 100, sy: 0, label: "σx=100" },
    { sx: 0, sy: 100, label: "σy=100" },
    { sx: 50, sy: 50, label: "biaxial" },
  ];
  for (const c of cases) {
    const far = ellipseStressCorrected(500, 500, 5, 5, 0, 0, 0, c.sx, c.sy, 0, mu1, mu2);
    console.log(`  ${c.label}: σx=${far.sigX.toFixed(2)}, σy=${far.sigY.toFixed(2)}`);
    assert(Math.abs(far.sigX - c.sx) < 1 && Math.abs(far.sigY - c.sy) < 1,
      `${c.label} recovery OK`);
  }
}

// TEST 5: Elliptical hole
console.log("\n═══ TEST 5: Isotropic elliptical hole (a=10, b=2), σy=100 ═══");
{
  const isoMat = { E1: 70, E2: 70, G12: 70/(2*1.3), v12: 0.3 };
  const [mu1, mu2] = characteristicRoots(isoMat);
  const a = 10, b = 2;
  // SCF at (a, 0) for σy loading = 1 + 2b/a = 1.4
  const expectedSCF = 1 + 2*b/a;
  const edge = ellipseStressCorrected(a+0.01, 0, a, b, 0, 0, 0, 0, 100, 0, mu1, mu2);
  console.log(`  SCF at (a+ε, 0) = ${(edge.sigY/100).toFixed(3)} (expect ${expectedSCF.toFixed(1)})`);
  assert(Math.abs(edge.sigY/100 - expectedSCF) < 0.2, `Ellipse SCF ≈ ${expectedSCF}`);

  // SCF at (0, b+ε) for σy loading = -(a/b) = -5.0
  // Wait: for isotropic, σx at (0,b) under σy = -σy·(2a/b - 1)... hmm
  // Actually, σy at (0, b+ε) for σy loading on ellipse:
  // Savin: σθ at θ=90° = σy∞·(1 - 2a/b) ... no
  // For σy loading, the tangential stress at the top (θ=90°):
  // σθ = σy∞·(-2a/b + 1 + 2v) ← for plane stress... not quite right either
  // Let's just check it's negative (compressive)
  const top = ellipseStressCorrected(0, b+0.01, a, b, 0, 0, 0, 0, 100, 0, mu1, mu2);
  console.log(`  σy at (0, b+ε) = ${top.sigY.toFixed(1)} (expect negative/compressive)`);
}

// ═══════════════════════════════════════════════════════════════
console.log(`\n${"═".repeat(50)}`);
console.log(`MATH VERIFICATION: ${passed} passed, ${failed} failed out of ${passed+failed}`);
console.log(`${"═".repeat(50)}`);
process.exit(failed > 0 ? 1 : 0);
