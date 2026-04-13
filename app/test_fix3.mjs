/**
 * The issue: 2Re[...] BCs create COUPLING between B and B̄.
 *
 * Full BCs (ζ⁻¹ AND ζ⁺¹ matching):
 *   (I) ζ⁻¹:  B₁ + B₂ = RHS₁
 *   (I) ζ⁺¹:  B̄₁ + B̄₂ = RHS₁*  (conjugate)
 *   (II) ζ⁻¹: μ₁B₁ + μ₂B₂ = RHS₂
 *   (II) ζ⁺¹: μ̄₁B̄₁ + μ̄₂B̄₂ = RHS₂*
 *
 * For pure imaginary μ_k = iβ_k: μ̄_k = -iβ_k = -μ_k
 *
 * If B_k are COMPLEX: B_k = b_k + i·c_k
 * Then B̄_k = b_k - i·c_k
 *
 * The 2Re[...] formulation means we actually have 4 real equations from the
 * ζ⁻¹ matching (not just 2). But with ζ⁺¹ being the conjugate, they're
 * automatically satisfied.
 *
 * ACTUALLY — I think the problem is different. Let me re-examine.
 *
 * The BCs 2Re[Φ₁+Φ₂] = f₁ involve ALL Fourier modes, not just ζ⁻¹.
 * The perturbation Φ_k = B_k/ζ_k only has a ζ⁻¹ mode.
 * But 2Re[B/ζ] = B·ζ⁻¹ + B̄·ζ has BOTH ζ⁻¹ and ζ⁺¹.
 *
 * The far-field contribution also has both modes.
 *
 * So matching ζ⁻¹ AND ζ⁺¹ simultaneously from 2Re[...] = f
 * is just one equation (ζ⁻¹) since ζ⁺¹ is the conjugate.
 *
 * So I really do have just 2 equations in 2 unknowns (B₁, B₂ complex).
 * That's 4 real equations for 4 real unknowns.
 *
 * Wait — B₁ and B₂ are 2 complex numbers = 4 real unknowns.
 * And the ζ⁻¹ matching gives 2 complex equations = 4 real equations.
 * So it's fully determined!
 *
 * Let me redo this. f₁ and f₂ from the far-field:
 *
 * f₁ = -σy·a·cosθ + τxy·b·sinθ = -(σy·a/2)(ζ+ζ⁻¹) + (τxy·b/(2i))(ζ-ζ⁻¹)
 * f₂ = σx·b·sinθ - τxy·a·cosθ = (σx·b/(2i))(ζ-ζ⁻¹) - (τxy·a/2)(ζ+ζ⁻¹)
 *
 * The perturbation must cancel this:
 * 2Re[Φ₁+Φ₂] = -f₁  and  2Re[μ₁Φ₁+μ₂Φ₂] = -f₂
 *
 * Hmm wait — is it -f₁ or +f₁? The perturbation should generate equal
 * and opposite tractions to make the hole traction-free.
 *
 * 2Re[Φ₁+Φ₂] (perturbation) = -f₁ (far-field resultant)
 *
 * LHS: B₁ζ⁻¹ + B₂ζ⁻¹ + B̄₁ζ + B̄₂ζ
 * RHS: -f₁ = (σy·a/2)(ζ+ζ⁻¹) - (τxy·b/(2i))(ζ-ζ⁻¹)
 *     = (σy·a/2 + i·τxy·b/2)·ζ⁻¹ + (σy·a/2 - i·τxy·b/2)·ζ
 *
 * Matching ζ⁻¹: B₁+B₂ = σy·a/2 + i·τxy·b/2
 * Matching ζ⁺¹: B̄₁+B̄₂ = σy·a/2 - i·τxy·b/2 ← consistent (conjugate)
 *
 * 2Re[μ₁Φ₁+μ₂Φ₂] (perturbation) = -f₂
 * LHS: μ₁B₁ζ⁻¹ + μ₂B₂ζ⁻¹ + μ̄₁B̄₁ζ + μ̄₂B̄₂ζ
 * RHS: -f₂ = -(σx·b/(2i))(ζ-ζ⁻¹) + (τxy·a/2)(ζ+ζ⁻¹)
 *     = (i·σx·b/2 + τxy·a/2)·ζ⁻¹ + (-i·σx·b/2 + τxy·a/2)·ζ
 *
 * Matching ζ⁻¹: μ₁B₁+μ₂B₂ = i·σx·b/2 + τxy·a/2
 * Matching ζ⁺¹: μ̄₁B̄₁+μ̄₂B̄₂ = -i·σx·b/2 + τxy·a/2 ← consistent
 *
 * BUT WAIT — we also have ζ⁺¹ from the Φ̄ terms mixing with the ζ terms!
 *
 * The key question: does the LHS have ONLY ζ⁻¹ and ζ⁺¹ terms?
 * YES — because Φ_k = B_k/ζ_k and Φ̄_k = B̄_k·ζ_k.
 * On the boundary ζ₁ = ζ₂ = e^(iθ), so ζ⁻¹ and ζ terms only.
 *
 * BUT ACTUALLY: ζ₁ ≠ ζ₂ on the boundary for ANISOTROPIC material!
 * The mapping z_k = (a-iμ_kb)/2·ζ + (a+iμ_kb)/2·ζ⁻¹
 * When z₁ = z₂ = z (physical point), ζ₁ and ζ₂ are DIFFERENT!
 *
 * On the hole boundary, z = a·cosθ + ib·sinθ.
 * z_k = a·cosθ + μ_k·b·sinθ ← this is the PHYSICAL z_k value on boundary
 *
 * From the mapping: z_k = (a-iμ_kb)/2·ζ_k + (a+iμ_kb)/2·ζ_k⁻¹
 * For the boundary, ζ_k = e^(iθ):
 * z_k = (a-iμ_kb)/2·e^(iθ) + (a+iμ_kb)/2·e^(-iθ)
 *     = a·cosθ + μ_k·b·(e^(iθ)-e^(-iθ))/(2i)·i ...
 *     = a·cosθ - iμ_k·b·(e^(iθ)-e^(-iθ))/2 + ... hmm
 *
 * Actually: (a-iμb)/2·e^(iθ) + (a+iμb)/2·e^(-iθ)
 *         = a(e^(iθ)+e^(-iθ))/2 - iμb(e^(iθ)-e^(-iθ))/2
 *         = a·cosθ - iμb·i·sinθ
 *         = a·cosθ + μb·sinθ  ← CORRECT
 *
 * So on the hole boundary, ζ_k = e^(iθ) for ALL k.
 * This is by construction of the conformal mapping.
 * So ζ₁ = ζ₂ = e^(iθ) on boundary. ✓
 *
 * So my matching is correct. The BCs give:
 *   B₁ + B₂ = σy·a/2 + i·τxy·b/2          ... (I)
 *   μ₁B₁ + μ₂B₂ = i·σx·b/2 + τxy·a/2     ... (II)
 *
 * For pure σy (σx=0, τxy=0):
 *   B₁ + B₂ = σy·a/2 = 250
 *   μ₁B₁ + μ₂B₂ = 0
 *
 * Solving with μ₁=iβ₁, μ₂=iβ₂:
 *   B₁ = -250β₂/(β₁-β₂) = 303.04
 *   B₂ = 250β₁/(β₁-β₂) = -53.04
 *
 * Φ₁' at ζ=1 = -B₁/(β₁b) = -303.04/(0.857·5) = -70.76
 * Φ₂' at ζ=1 = -B₂/(β₂b) = 53.04/(4.894·5) = 2.17
 * Δσy = 2(Φ₁'+Φ₂') = 2(-70.76+2.17) = -137.18
 * SCF = 1 + (-137.18)/100 = -0.37  ← WRONG, negative!
 *
 * OK so the POSITIVE sign B₁+B₂ = +250 gives WRONG answer.
 * And B₁+B₂ = -250 gave SCF=2.37 (also wrong but at least positive).
 *
 * The issue is subtle. Let me think about this differently.
 *
 * The KNOWN correct SCF = 1 + β₁ + β₂ = 6.75.
 * The perturbation Δσy = 575 at the boundary.
 * This means 2(Φ₁'+Φ₂') = 575 at ζ=1.
 * Φ₁'+Φ₂' = 287.5
 *
 * With Φ_k' = -B_k/(β_k·b) at ζ=1:
 * -B₁/(β₁b) - B₂/(β₂b) = 287.5
 * -B₁/(0.857·5) - B₂/(4.894·5) = 287.5
 * -B₁/4.283 - B₂/24.47 = 287.5
 *
 * Also B₁+B₂ = ±250 (we know one of the two BCs).
 * And β₁B₁+β₂B₂ = 0 (from second BC for μ₁B₁+μ₂B₂=0).
 *
 * From β₁B₁+β₂B₂=0: B₁ = -(β₂/β₁)B₂ = -5.714·B₂
 *
 * Sub into Φ equation:
 * -(-5.714B₂)/4.283 - B₂/24.47 = 287.5
 * 5.714B₂/4.283 - B₂/24.47 = 287.5
 * 1.334B₂ - 0.0409B₂ = 287.5
 * 1.293B₂ = 287.5
 * B₂ = 222.3
 * B₁ = -5.714·222.3 = -1270.6
 * B₁+B₂ = -1048.3
 *
 * But from BC: B₁+B₂ = ±250. Neither matches -1048.3!
 *
 * This means the potential Φ_k = B_k/ζ_k is NOT sufficient.
 * The perturbation potential needs MORE terms!
 *
 * OH WAIT. Maybe the perturbation uses a DIFFERENT function form.
 * Let me reconsider. Perhaps it's not Φ_k = B_k/ζ_k but rather
 * something involving BOTH 1/ζ AND ζ terms? No — ζ terms grow at infinity.
 *
 * OR: perhaps the convention is different. Instead of
 *   σy = 2Re[Φ₁' + Φ₂']
 * it might be
 *   σy = Re[Φ₁' + Φ₂']   (without the factor 2)
 *
 * If we drop the factor 2, then:
 * Φ₁'+Φ₂' = 575 at boundary
 * -B₁/(β₁b) - B₂/(β₂b) = 575
 *
 * With β₁B₁+β₂B₂=0: B₁=-5.714B₂
 * 5.714B₂/4.283 - B₂/24.47 = 575
 * 1.293B₂ = 575
 * B₂ = 444.7
 * B₁ = -2541.2
 * B₁+B₂ = -2096.5 ← still doesn't match ±250
 *
 * So the factor 2 issue doesn't explain it.
 *
 * FUNDAMENTAL RETHINK: Maybe the Lekhnitskii potential is NOT Φ_k = B_k/ζ_k.
 * Maybe it's the LOGARITHMIC form: Φ_k = B_k·ln(ζ_k).
 *
 * With Φ_k = B_k·ln(ζ_k):
 * Φ_k' = B_k · ζ_k' / ζ_k = B_k/(ζ_k · dz_k/dζ_k)
 * At ζ=1, dz/dζ = β_k·b:
 * Φ_k' = B_k/(1·β_k·b)
 *
 * (Note: NO minus sign compared to the 1/ζ case!)
 *
 * Δσy = 2(Φ₁'+Φ₂') = 2(B₁/(β₁b) + B₂/(β₂b))
 *
 * With B₁+B₂ = -250 and β₁B₁+β₂B₂=0:
 * B₁ = 250β₂/(β₁-β₂) [from old]
 * Hmm wait: B₁ = -250β₂/(β₁-β₂) and B₂ = 250β₁/(β₁-β₂)
 *
 * Δσy = 2(-250β₂/((β₁-β₂)β₁b) + 250β₁/((β₁-β₂)β₂b))
 *      = 500/((β₁-β₂)b) · (-β₂/β₁ + β₁/β₂)
 *      = 500/((β₁-β₂)b) · (β₁²-β₂²)/(β₁β₂)
 *      = 500/((β₁-β₂)b) · (β₁-β₂)(β₁+β₂)/(β₁β₂)
 *      = 500(β₁+β₂)/(b·β₁β₂)
 *      = 500·5.750/(5·4.192) = 2875/20.96 = 137.2
 * SCF = 1 + 137.2/100 = 2.37  ← SAME RESULT!
 *
 * So both forms (1/ζ and ln(ζ)) give the same perturbation Δσy at boundary.
 * (This makes sense — they differ by a constant in Φ).
 *
 * The problem is structural: with the BC β₁B₁+β₂B₂=0 and B₁+B₂=-250,
 * the maximum achievable Δσy at the boundary is limited.
 *
 * This means the BCs themselves are WRONG. The traction-free condition
 * must involve something I'm missing.
 *
 * Let me try one more thing: what if the SECOND BC for σy loading is not
 * μ₁B₁+μ₂B₂=0 but instead μ₁B₁+μ₂B₂ = -σy·b/2 = -250 ?
 *
 * Then: iβ₁B₁+iβ₂B₂ = -250
 *       β₁B₁+β₂B₂ = 250i (COMPLEX rhs!)
 *
 * This means B values must be complex!
 * B₁+B₂ = -250 (real)
 * β₁B₁+β₂B₂ = 250i (imaginary)
 *
 * Write B_k = p_k + iq_k:
 * p₁+p₂ = -250, q₁+q₂ = 0
 * β₁p₁+β₂p₂ = 0, β₁q₁+β₂q₂ = 250
 *
 * From p₁+p₂=-250, β₁p₁+β₂p₂=0:
 * p₁ = 250β₂/(β₁-β₂) = -303.04
 * p₂ = -250-p₁ = 53.04
 *
 * From q₁+q₂=0, β₁q₁+β₂q₂=250:
 * q₁ = -q₂
 * β₁(-q₂)+β₂q₂ = 250 → q₂(β₂-β₁)=250 → q₂=250/(β₂-β₁)=250/4.037=61.92
 * q₁ = -61.92
 *
 * So: B₁ = -303.04 - 61.92i
 *     B₂ = 53.04 + 61.92i
 *
 * Now: Φ₁' at ζ=1 with LOG form = B₁/(β₁b)
 *    = (-303.04 - 61.92i)/(0.857·5) = (-303.04 - 61.92i)/4.283
 *    = -70.76 - 14.46i
 *
 * Φ₂' = B₂/(β₂b) = (53.04+61.92i)/(4.894·5) = (53.04+61.92i)/24.47
 *      = 2.17 + 2.53i
 *
 * Δσy = 2Re[Φ₁'+Φ₂'] = 2Re[-70.76-14.46i + 2.17+2.53i]
 *      = 2Re[-68.59 - 11.93i] = 2(-68.59) = -137.18
 *
 * STILL -137.18! The imaginary parts don't contribute to Re[...]!
 *
 * So the second BC being -σy·b/2 vs 0 DOESN'T CHANGE the real part of Δσy!
 * It only affects the imaginary part of Φ', which gets killed by Re[...].
 *
 * THIS IS THE KEY INSIGHT: No matter what the second BC is, as long as
 * B₁+B₂ = -250 (from first BC), the Δσy is fixed because the stress
 * formula uses 2Re[...].
 *
 * So the FIRST BC must be wrong! B₁+B₂ ≠ -σy·a/2.
 *
 * BACK TO BASICS. The entire approach of Φ_k = B_k/ζ_k or B_k·ln(ζ_k)
 * with just ONE term in the Laurent series might be insufficient.
 * Maybe we need MORE terms, or a completely different potential form.
 *
 * Actually — I think the issue is that the Lekhnitskii potentials for the
 * HOLE problem use a DIFFERENT basis than 1/ζ. The standard solution uses:
 *
 *   Φ_k(z_k) = A_k · z_k + Σ B_kn / ζ_k^n
 *
 * where A_k is determined by far-field, and only B_k1 (n=1) is needed for
 * the traction-free condition.
 *
 * WAIT — but A_k·z_k is the far-field part! So the perturbation IS just B/ζ.
 *
 * Unless... the issue is with HOW we write the boundary conditions.
 * The BC involves the TOTAL potential Φ_total = A_k·z_k + B_k/ζ_k.
 * On the boundary ζ=e^(iθ):
 * z_k = (a-iμ_kb)/2·ζ + (a+iμ_kb)/2·ζ⁻¹ = α_k·ζ + ᾱ_k·ζ⁻¹
 * where α_k = (a-iμ_kb)/2, ᾱ_k = (a+iμ_kb)/2
 *
 * Φ_k_total = A_k(α_k·ζ + ᾱ_k·ζ⁻¹) + B_k·ζ⁻¹
 *           = A_k·α_k·ζ + (A_k·ᾱ_k + B_k)·ζ⁻¹
 *
 * Conjugate on boundary:
 * Φ̄_k = Ā_k·(ᾱ_k·ζ⁻¹ + α_k·ζ) ... wait, conj of z_k on boundary?
 * Actually: Φ̄_k(z̄_k) where z̄_k = x + μ̄_k·y = x - μ_k·y
 *
 * Hmm, this is not just the conjugate of Φ_k(z_k) because z̄_k ≠ conj(z_k)
 * in general (μ_k is complex!).
 *
 * For pure imaginary μ_k = iβ_k: μ̄_k = -iβ_k = -μ_k
 * z̄_k = x - iβ_k·y
 * z_k = x + iβ_k·y
 * So z̄_k = conj(z_k) ✓ (for pure imaginary μ)
 *
 * And Φ̄_k(z̄_k) means Φ_k(z̄_k) conjugated? Or conj(Φ_k)(z̄_k)?
 *
 * In Lekhnitskii: if F₁(z₁) is analytic, then its conjugate analytic function
 * is F̄₁(z̄₁), where z̄₁ = x + μ̄₁y.
 *
 * For the special case of pure imaginary μ, z̄₁ = x - iβ₁y = conj(z₁).
 * And F̄₁(z̄₁) = conj(F₁(z₁)) when evaluated at real (x,y).
 *
 * So on the boundary:
 * 2Re[Φ₁(z₁)+Φ₂(z₂)] = Φ₁+Φ₂+Φ̄₁+Φ̄₂ = Φ₁+Φ₂+conj(Φ₁)+conj(Φ₂)
 *
 * For Φ_k_total on boundary = A_k·α_k·ζ + (A_k·ᾱ_k+B_k)·ζ⁻¹
 * conj(Φ_k) = Ā_k·ᾱ_k·ζ⁻¹ + (Ā_k·α_k+B̄_k)·ζ  (since conj(ζ)=ζ⁻¹ on unit circle)
 *
 * Wait actually for pure imaginary μ:
 * α_k = (a+β_kb)/2 (REAL)
 * ᾱ_k = (a-β_kb)/2 (REAL)
 * And if A_k and B_k are REAL (which they can be for pure imaginary μ):
 *
 * Φ_k_total = A_k·α_k·ζ + (A_k·ᾱ_k+B_k)·ζ⁻¹
 * conj(Φ_k) = A_k·α_k·ζ⁻¹ + (A_k·ᾱ_k+B_k)·ζ (just swap ζ↔ζ⁻¹)
 *
 * So: 2Re[Φ₁+Φ₂] = 2[A₁α₁+A₂α₂]cosθ + ... no wait
 *   = (A₁α₁+A₂α₂)(ζ+ζ⁻¹) + (A₁ᾱ₁+B₁+A₂ᾱ₂+B₂)(ζ+ζ⁻¹) ... hmm
 *
 * Actually:
 * Φ₁+Φ₂+conj(Φ₁)+conj(Φ₂)
 * = (A₁α₁+A₂α₂)(ζ) + (A₁ᾱ₁+B₁+A₂ᾱ₂+B₂)(ζ⁻¹)
 *   + (A₁α₁+A₂α₂)(ζ⁻¹) + (A₁ᾱ₁+B₁+A₂ᾱ₂+B₂)(ζ)
 * = (A₁α₁+A₂α₂ + A₁ᾱ₁+B₁+A₂ᾱ₂+B₂)(ζ+ζ⁻¹)
 * = (A₁(α₁+ᾱ₁)+A₂(α₂+ᾱ₂)+B₁+B₂) · 2cosθ
 *
 * Note: α_k+ᾱ_k = (a+β_kb)/2 + (a-β_kb)/2 = a
 * So: = (a(A₁+A₂) + B₁+B₂) · 2cosθ
 *
 * This must equal f₁ = -σy·a·cosθ (for σy loading)
 * Wait, f₁ = traction-free BC is 0 (not -σy·a·cosθ).
 *
 * The traction-free condition says the total traction = 0:
 * 2Re[Φ₁_total+Φ₂_total] = const on boundary
 *
 * The "const" means the constant part of f₁. The oscillating parts must vanish.
 *
 * So: (a(A₁+A₂) + B₁+B₂) · 2cosθ = 0 for all θ
 * → a(A₁+A₂) + B₁+B₂ = 0
 * → B₁+B₂ = -a(A₁+A₂)
 *
 * Recall A₁+A₂ = σy/2 (from the far-field):
 * σy∞ = 2Re[A₁+A₂] = 2(A₁+A₂) for real A values
 * → A₁+A₂ = σy∞/2 = 50
 *
 * So B₁+B₂ = -a·50 = -250 ✓ (matches our first BC)
 *
 * Now for the second BC, 2Re[μ₁Φ₁+μ₂Φ₂]:
 * μ_kΦ_k_total = μ_k·A_k·α_k·ζ + μ_k·(A_k·ᾱ_k+B_k)·ζ⁻¹
 * For μ_k=iβ_k (pure imaginary), A_k,α_k,ᾱ_k,B_k all real:
 * μ_kΦ_k = iβ_k·A_k·α_k·ζ + iβ_k·(A_k·ᾱ_k+B_k)·ζ⁻¹
 * conj(μ_kΦ_k) = -iβ_k·A_k·α_k·ζ⁻¹ - iβ_k·(A_k·ᾱ_k+B_k)·ζ
 *
 * Sum: μ_kΦ_k + conj(μ_kΦ_k)
 * = iβ_k[(A_k·α_k)(ζ-ζ⁻¹) + (A_k·ᾱ_k+B_k)(ζ⁻¹-ζ)]
 * = iβ_k(ζ-ζ⁻¹)(A_k·α_k - A_k·ᾱ_k - B_k)
 * = iβ_k·2i·sinθ·(A_k(α_k-ᾱ_k) - B_k)
 * = -2β_k·sinθ·(A_k·β_k·b - B_k)
 *
 * (using α_k-ᾱ_k = β_k·b)
 *
 * So: 2Re[μ₁Φ₁+μ₂Φ₂]
 * = -2sinθ[β₁(A₁β₁b-B₁) + β₂(A₂β₂b-B₂)]
 *
 * Traction-free: this must = 0 for all θ:
 * β₁(A₁β₁b-B₁) + β₂(A₂β₂b-B₂) = 0
 * β₁²A₁b + β₂²A₂b - β₁B₁ - β₂B₂ = 0
 * β₁B₁ + β₂B₂ = b(β₁²A₁ + β₂²A₂)
 *
 * We know: β₁²A₁ + β₂²A₂ = 0 (from far-field σx=0 condition)
 * (σx∞ = 2Re[μ₁²A₁+μ₂²A₂] = 2(-β₁²A₁-β₂²A₂) = 0)
 *
 * So: β₁B₁+β₂B₂ = 0  ✓
 *
 * HMMMM. So both BCs are confirmed. And we get SCF=2.37. But the correct
 * answer is 6.75. This is deeply confusing.
 *
 * UNLESS... the stress formula 2Re[...] is wrong.
 *
 * Let me reconsider the stress formulas.
 * From U = 2Re[F₁(z₁)+F₂(z₂)] (Airy stress function):
 *   σx = ∂²U/∂y² = 2Re[μ₁²F₁''(z₁) + μ₂²F₂''(z₂)]
 *   σy = ∂²U/∂x² = 2Re[F₁''(z₁) + F₂''(z₂)]
 *
 * IF Φ_k = F_k' (stress potential convention), then
 *   σy = 2Re[Φ₁'(z₁) + Φ₂'(z₂)]
 *
 * BUT if the code/we define Φ as F (not F'), then:
 *   σy = 2Re[Φ''(z₁) + Φ₂''(z₂)]   ← SECOND derivative!
 *
 * The AIRY FUNCTION F has the property:
 *   F_k(z_k) for the far field = (1/2)·A_k·z_k²   (quadratic)
 *   F_k' = A_k·z_k, F_k'' = A_k
 *   σy = 2Re[A₁+A₂] = σy∞  ✓
 *
 * For the perturbation: f_k(z_k) = B_k·g(ζ_k)
 * If we use the Airy convention: stress = 2Re[f''], not 2Re[f'].
 *
 * With f_k = B_k · h(ζ_k) where h gives the right Laurent structure:
 * What IS the right function?
 *
 * The total F_k_total = (1/2)A_k·z_k² + f_k(z_k)
 * On boundary, z_k = α_k·ζ + ᾱ_k·ζ⁻¹
 * The BC 2Re[F₁'+F₂'] = integrated traction
 *
 * F_k' = A_k·z_k + f_k'
 * On boundary: F_k' = A_k(α_k·ζ + ᾱ_k·ζ⁻¹) + f_k'
 *
 * WAIT. The BC involves F' (first derivative), not F''.
 * Lekhnitskii §35, the BCs are on F' (or equivalently Φ where Φ=F').
 *
 * So IF our Φ = F' = A_k·z_k + f_k', then:
 * The perturbation potential = f_k'(z_k), not f_k(z_k).
 *
 * And the stress uses Φ' = F'' = A_k + f_k''(z_k).
 *
 * If we choose f_k(z_k) = C_k · ln(ζ_k), then:
 * f_k' = C_k · ζ_k'/ζ_k
 * The perturbation Φ_pert = f_k' = C_k · ζ_k'/ζ_k
 * This is NOT simply C/ζ.
 *
 * On boundary ζ=e^(iθ):
 * ζ' = dζ/dz = 1/(α_k·ζ - ᾱ_k·ζ⁻¹) · ζ ... hmm
 * Actually ζ'/ζ = 1/[ζ·dz/dζ] = 1/[α_k·ζ² - ᾱ_k]
 * = 1/[α_k·e^(2iθ) - ᾱ_k]
 *
 * This is not a simple Fourier mode. So the Laurent series in ζ for Φ
 * is not the same as the Laurent series in ζ for F.
 *
 * I think THIS is where I went wrong. Let me use F (Airy function) directly.
 * F_k(z_k) = (1/2)A_k·z_k² + C_k · ln(ζ_k)  (log for perturbation in F)
 * F_k' = A_k·z_k + C_k·ζ_k'/ζ_k = A_k·z_k + C_k/(ζ_k·dz_k/dζ_k)
 *
 * BC: 2Re[F₁'+F₂'] = const on boundary
 *
 * On boundary ζ=e^(iθ):
 * dz_k/dζ_k = α_k - ᾱ_k·ζ⁻² (for pure imaginary μ, α and ᾱ real)
 * At ζ=e^(iθ): dz/dζ = α_k - ᾱ_k·e^(-2iθ)
 *
 * F_k' on boundary = A_k(α_k·ζ + ᾱ_k·ζ⁻¹) + C_k/(ζ·(α_k - ᾱ_k·ζ⁻²))
 *                   = A_k(α_k·ζ + ᾱ_k·ζ⁻¹) + C_k·ζ/(α_k·ζ² - ᾱ_k)
 *
 * The second term has a complicated Fourier expansion. This is not simply B/ζ.
 *
 * OK I think I've been going down a rabbit hole. Let me take a completely
 * DIFFERENT approach: use the KNOWN closed-form boundary stress formula.

 * From Lekhnitskii (1968) eq. 38.12, the tangential stress on the elliptical
 * hole boundary at angle θ (measured on the conformal map circle) is:
 *
 * σ_θ(θ) = [σx∞·sin²θ + σy∞·cos²θ - τxy∞·sin(2θ)] ·
 *           [n² + k² - (n² - k²)·cos(2θ)] /
 *           [sin²θ + k²·cos²θ]²  ... no, that's not right
 *
 * Actually, I recall the formula is much simpler for the BOUNDARY:
 * σ_t(θ) = Re[(σx∞ + σy∞)·(1 + m·e^(-2iθ))/(1 - m·e^(-2iθ))·...]
 *
 * This is getting nowhere. Let me just find an EXISTING validated
 * implementation online and compare.

 * FINAL ATTEMPT: Use direct numerical differentiation.
 * Compute U at nearby points and use finite differences for σy = ∂²U/∂x².
 */

const CC = {
  add: (a, b) => ({ re: a.re+b.re, im: a.im+b.im }),
  sub: (a, b) => ({ re: a.re-b.re, im: a.im-b.im }),
  mul: (a, b) => ({ re: a.re*b.re-a.im*b.im, im: a.re*b.im+a.im*b.re }),
  div: (a, b) => { const d=b.re*b.re+b.im*b.im; return {re:(a.re*b.re+a.im*b.im)/d, im:(a.im*b.re-a.re*b.im)/d}; },
  sqrt: (z) => { const r=Math.sqrt(z.re*z.re+z.im*z.im); const t=Math.atan2(z.im,z.re); const s=Math.sqrt(r); return {re:s*Math.cos(t/2),im:s*Math.sin(t/2)}; },
  scale: (z, s) => ({ re: z.re*s, im: z.im*s }),
  mag: (z) => Math.sqrt(z.re*z.re+z.im*z.im),
  ln: (z) => ({ re: Math.log(Math.sqrt(z.re*z.re+z.im*z.im)), im: Math.atan2(z.im, z.re) }),
};

function charRoots(mat) {
  const E1=mat.E1*1000,E2=mat.E2*1000,G12=mat.G12*1000;
  const a11=1/E1,a22=1/E2,a12=-mat.v12/E1,a66=1/G12;
  const A=a11,B=2*a12+a66,Cv=a22;
  const disc=B*B-4*A*Cv;
  const t1=(-B+Math.sqrt(disc))/(2*A),t2=(-B-Math.sqrt(disc))/(2*A);
  const mu1=t1<0?{re:0,im:Math.sqrt(-t1)}:{re:Math.sqrt(t1),im:0};
  const mu2=t2<0?{re:0,im:Math.sqrt(-t2)}:{re:Math.sqrt(t2),im:0};
  if(mu1.im<0){mu1.re=-mu1.re;mu1.im=-mu1.im;}
  if(mu2.im<0){mu2.re=-mu2.re;mu2.im=-mu2.im;}
  return [mu1,mu2];
}

// Compute the Airy stress function U at point (x,y) using:
// U = 2Re[F₁(z₁)+F₂(z₂)]
// F_k = (1/2)A_k·z_k² + C_k·ln(ζ_k)
// where A_k are the far-field coefficients and C_k are perturbation coefficients.

const mat = { E1: 181, E2: 10.3, G12: 7.17, v12: 0.28 };
const [m1, m2] = charRoots(mat);
const b1 = m1.im, b2 = m2.im;

// Far-field: σy∞=100, σx∞=0
// A₁+A₂ = 50, β₁²A₁+β₂²A₂ = 0
const A2v = 50/(1-b2*b2/(b1*b1));
const A1v = 50-A2v;
console.log(`\n═══ Airy function approach ═══`);
console.log(`A₁ = ${A1v.toFixed(4)}, A₂ = ${A2v.toFixed(4)}`);

// Perturbation: C₁+C₂ = -a(A₁+A₂) = -250 ... wait
// The BC on F' gives the same thing we already had.
// But σy = 2Re[F₁''+F₂''], not 2Re[F₁'+F₂'].
// So we need the SECOND derivative of F_k = (1/2)A_k·z_k² + C_k·ln(ζ_k)
// F_k'' = A_k + C_k · d/dz_k [ζ_k'(z_k)/ζ_k]

// Let me compute U at several x values and use finite differences.
const av = 5, bv = 5;

function computeZeta(xp, yp, mu) {
  const z = {re: xp+mu.re*yp, im: mu.im*yp};
  const musq = CC.mul(mu,mu);
  const inner = CC.sub(CC.mul(z,z), {re:av*av+musq.re*bv*bv, im:musq.im*bv*bv});
  const sq = CC.sqrt(inner);
  const den = {re:av+mu.im*bv, im:-mu.re*bv};
  let zeta = CC.div(CC.add(z,sq),den);
  if(CC.mag(zeta)<1) zeta=CC.div(CC.sub(z,sq),den);
  return zeta;
}

// C_k from BC on F':
// We need: 2Re[F₁'+F₂'] = const on boundary
// F_k' = A_k·z_k + C_k·ζ_k'/ζ_k
// The BC matching gave us C₁ = B₁ = -303.04 (the values that satisfy traction-free)
// These are the same coefficients. The stress uses F'', not Φ'.
// So maybe the fix is just to compute F₁'' properly.

// F_k(z_k) = A_k/2·z_k² + C_k·ln(ζ_k)
function computeU(xp, yp) {
  let U = 0;
  const Ak = [A1v, A2v];
  const Ck = [-303.04, 53.04]; // our traction-free coefficients
  const mus = [m1, m2];
  for (let k = 0; k < 2; k++) {
    const mu = mus[k];
    const zk = {re: xp+mu.re*yp, im: mu.im*yp};
    const zk2 = CC.mul(zk, zk);
    const Fk_farfield = CC.scale(zk2, Ak[k]/2);
    const zeta = computeZeta(xp, yp, mu);
    const lnZeta = CC.ln(zeta);
    const Fk_pert = CC.scale(lnZeta, Ck[k]);
    const Fk = CC.add(Fk_farfield, Fk_pert);
    U += 2 * Fk.re; // 2Re[F_k]
  }
  return U;
}

// σy = ∂²U/∂x² via finite differences
const h = 0.001;
console.log(`\nσy from finite differences of Airy function:`);
for (const xv of [5.01, 5.1, 5.5, 6.0, 7.0, 10.0, 20.0]) {
  const Uc = computeU(xv, 0);
  const Up = computeU(xv+h, 0);
  const Um = computeU(xv-h, 0);
  const sigY = (Up - 2*Uc + Um) / (h*h);
  console.log(`  x=${xv.toFixed(2)}: σy = ${sigY.toFixed(2)} MPa (SCF=${(sigY/100).toFixed(3)})`);
}

// Also check σx = ∂²U/∂y²
console.log(`\nσx from finite differences:`);
for (const xv of [5.01, 5.1, 6.0, 10.0]) {
  const Uc = computeU(xv, 0);
  const Up = computeU(xv, h);
  const Um = computeU(xv, -h);
  const sigX = (Up - 2*Uc + Um) / (h*h);
  console.log(`  x=${xv.toFixed(2)}: σx = ${sigX.toFixed(2)} (expect ≈0 at hole edge)`);
}
