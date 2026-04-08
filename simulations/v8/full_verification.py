"""
Full verification of all 770 material × layup combinations.
Re-computes everything from scratch and outputs structured data for documentation.
"""
import math
import sys
import json

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, r"C:\CalculiX\test_composite")
from batch_compositeNet import MATERIALS, LAYUPS, MATERIAL_PRESSURE_RANGES, LAYUP_SCALE_FACTORS

PLY_T = 0.15

# ── CLT engine (independent re-implementation for verification) ──────────────

def reduced_stiffness(E1, E2, v12, G12):
    v21 = v12 * E2 / E1
    D = 1.0 - v12 * v21
    return E1/D, E2/D, v12*E2/D, G12

def transform_Q(Q11, Q22, Q12, Q66, theta_deg):
    t = math.radians(theta_deg)
    c, s = math.cos(t), math.sin(t)
    c2, s2, cs = c*c, s*s, c*s
    Qb11 = Q11*c2*c2 + 2*(Q12+2*Q66)*c2*s2 + Q22*s2*s2
    Qb22 = Q11*s2*s2 + 2*(Q12+2*Q66)*c2*s2 + Q22*c2*c2
    Qb12 = (Q11+Q22-4*Q66)*c2*s2 + Q12*(c2*c2+s2*s2)
    Qb16 = (Q11-Q12-2*Q66)*c2*cs + (Q12-Q22+2*Q66)*s2*cs
    Qb26 = (Q11-Q12-2*Q66)*cs*s2 + (Q12-Q22+2*Q66)*cs*c2
    Qb66 = (Q11+Q22-2*Q12-2*Q66)*c2*s2 + Q66*(c2*c2+s2*s2)
    return [[Qb11, Qb12, Qb16], [Qb12, Qb22, Qb26], [Qb16, Qb26, Qb66]]

def build_ABD(Q11, Q22, Q12, Q66, angles, t_ply):
    n = len(angles)
    h = n * t_ply
    A = [[0.0]*3 for _ in range(3)]
    B = [[0.0]*3 for _ in range(3)]
    D = [[0.0]*3 for _ in range(3)]
    Qbar_list = []
    for k, th in enumerate(angles):
        Qb = transform_Q(Q11, Q22, Q12, Q66, th)
        Qbar_list.append(Qb)
        zb = -h/2 + k*t_ply
        zt = zb + t_ply
        for i in range(3):
            for j in range(3):
                A[i][j] += Qb[i][j] * (zt - zb)
                B[i][j] += 0.5 * Qb[i][j] * (zt**2 - zb**2)
                D[i][j] += (1.0/3.0) * Qb[i][j] * (zt**3 - zb**3)
    return A, B, D, Qbar_list

def gauss_jordan_6x6(abd):
    aug = [abd[r][:] + [1.0 if r == c else 0.0 for c in range(6)] for r in range(6)]
    for col in range(6):
        mx = col
        for row in range(col+1, 6):
            if abs(aug[row][col]) > abs(aug[mx][col]):
                mx = row
        aug[col], aug[mx] = aug[mx], aug[col]
        if abs(aug[col][col]) < 1e-30:
            return None
        piv = aug[col][col]
        for j in range(12):
            aug[col][j] /= piv
        for row in range(6):
            if row != col:
                f = aug[row][col]
                for j in range(12):
                    aug[row][j] -= f * aug[col][j]
    return [aug[r][6:12] for r in range(6)]

def inv3x3(m):
    a,b,c = m[0]; d,e,f = m[1]; g,h,k = m[2]
    det = a*(e*k-f*h) - b*(d*k-f*g) + c*(d*h-e*g)
    if abs(det) < 1e-30: return None
    id = 1.0/det
    return [[(e*k-f*h)*id,(c*h-b*k)*id,(b*f-c*e)*id],
            [(f*g-d*k)*id,(a*k-c*g)*id,(c*d-a*f)*id],
            [(d*h-e*g)*id,(b*g-a*h)*id,(a*e-b*d)*id]]

def compute_fpf(mat, angles, t_ply=0.15):
    """Full CLT FPF with ABD. Returns (fpf_MPa, crit_ply_angle, mode, ply_stresses)."""
    E1,E2,v12,G12 = float(mat['E1']),float(mat['E2']),float(mat['v12']),float(mat['G12'])
    XT,XC,YT,YC,SL = float(mat['XT']),float(mat['XC']),float(mat['YT']),float(mat['YC']),float(mat['SL'])
    Q11,Q22,Q12,Q66 = reduced_stiffness(E1,E2,v12,G12)
    n = len(angles)
    h = n * t_ply
    A,Bm,Dm,Qbar_list = build_ABD(Q11,Q22,Q12,Q66,angles,t_ply)

    # Check symmetry
    bn = sum(abs(Bm[i][j]) for i in range(3) for j in range(3))
    an = sum(abs(A[i][j]) for i in range(3) for j in range(3))
    sym = bn < 0.001 * an

    if sym:
        Ainv = inv3x3(A)
        if Ainv is None: return None, None, None, None
        ex,ey,gxy = Ainv[0][0], Ainv[1][0], Ainv[2][0]
        kx=ky=kxy=0.0
    else:
        abd = [[0.0]*6 for _ in range(6)]
        for i in range(3):
            for j in range(3):
                abd[i][j]=A[i][j]; abd[i][j+3]=Bm[i][j]
                abd[i+3][j]=Bm[i][j]; abd[i+3][j+3]=Dm[i][j]
        abd_inv = gauss_jordan_6x6(abd)
        if abd_inv is None: return None, None, None, None
        ex,ey,gxy = abd_inv[0][0], abd_inv[1][0], abd_inv[2][0]
        kx,ky,kxy = abd_inv[3][0], abd_inv[4][0], abd_inv[5][0]

    max_fi = 0.0
    crit_angle = 0
    crit_mode = ""
    ply_data = []

    for pk, th in enumerate(angles):
        zb = -h/2 + pk*t_ply
        zm = zb + t_ply/2.0
        exx = ex + zm*kx; eyy = ey + zm*ky; gxxyy = gxy + zm*kxy
        Qb = Qbar_list[pk]
        sx = Qb[0][0]*exx + Qb[0][1]*eyy + Qb[0][2]*gxxyy
        sy = Qb[0][1]*exx + Qb[1][1]*eyy + Qb[1][2]*gxxyy
        txy = Qb[0][2]*exx + Qb[1][2]*eyy + Qb[2][2]*gxxyy

        t = math.radians(th)
        cc,ss = math.cos(t), math.sin(t)
        s1 = sx*cc*cc + sy*ss*ss + 2*txy*cc*ss
        s2 = sx*ss*ss + sy*cc*cc - 2*txy*cc*ss
        t12 = -sx*cc*ss + sy*cc*ss + txy*(cc*cc - ss*ss)

        fi1 = s1/XT if s1>=0 else abs(s1)/XC
        fi2 = s2/YT if s2>=0 else abs(s2)/YC
        fi12 = abs(t12)/SL if SL>0 else 0.0
        fi = max(fi1, fi2, fi12)

        if fi1>=fi2 and fi1>=fi12:
            mode = "fibre_T" if s1>=0 else "fibre_C"
        elif fi2>=fi12:
            mode = "matrix_T" if s2>=0 else "matrix_C"
        else:
            mode = "shear"

        ply_data.append({
            'ply': pk+1, 'angle': th, 'z_mid': round(zm,4),
            'sig1': round(s1,4), 'sig2': round(s2,4), 'tau12': round(t12,4),
            'fi1': round(fi1,6), 'fi2': round(fi2,6), 'fi12': round(fi12,6),
            'fi_max': round(fi,6), 'mode': mode
        })

        if fi > max_fi:
            max_fi = fi
            crit_angle = th
            crit_mode = mode

    if max_fi < 1e-15:
        return 1e6, crit_angle, "none", ply_data

    fpf_Nx = 1.0 / max_fi
    fpf_p = fpf_Nx / (n * t_ply)
    return round(fpf_p, 4), crit_angle, crit_mode, ply_data

def lekhnitskii_scf(E1, E2, v12, G12):
    return 1.0 + math.sqrt(2.0*(math.sqrt(E1/E2) - v12) + E1/G12)

# ── Main computation ─────────────────────────────────────────────────────────

def main():
    results = {
        'materials': {},
        'layups': {},
        'combos': [],
        'qi_fpf': {},
        'scf': {},
        'summary': {}
    }

    # Material info
    for mid in sorted(MATERIALS.keys()):
        m = MATERIALS[mid]
        scf = lekhnitskii_scf(m['E1'], m['E2'], m['v12'], m['G12'])
        results['materials'][mid] = {
            'name': m['name'], 'E1': m['E1'], 'E2': m['E2'],
            'G12': m['G12'], 'v12': m['v12'],
            'XT': m['XT'], 'XC': m['XC'], 'YT': m['YT'], 'YC': m['YC'], 'SL': m['SL'],
            'source': m['source'], 'E1_E2': round(m['E1']/m['E2'], 2),
            'scf_lekhnitskii': round(scf, 3)
        }
        results['scf'][mid] = round(scf, 3)

    # Layup info
    for lid in sorted(LAYUPS.keys()):
        l = LAYUPS[lid]
        n = len(l['angles'])
        # Check symmetry
        sym = True
        for i in range(n//2):
            if l['angles'][i] != l['angles'][n-1-i]:
                sym = False
                break
        if n % 2 == 1:
            sym = False
        results['layups'][lid] = {
            'name': l['name'], 'angles': l['angles'], 'n_plies': n,
            'symmetric': sym, 'scale_factor': round(LAYUP_SCALE_FACTORS[lid], 4)
        }

    # QI FPF for each material (baseline)
    qi_angles = LAYUPS[1]['angles']
    for mid in sorted(MATERIALS.keys()):
        fpf, ca, cm, _ = compute_fpf(MATERIALS[mid], qi_angles)
        results['qi_fpf'][mid] = {
            'fpf_MPa': fpf, 'crit_angle': ca, 'mode': cm,
            'px_lo': MATERIAL_PRESSURE_RANGES[mid][0],
            'px_hi': MATERIAL_PRESSURE_RANGES[mid][1]
        }

    # All 770 combos
    print("Computing all 770 material x layup combinations...", flush=True)
    n_good = n_marginal = n_bad = 0
    combo_count = 0

    for mid in sorted(MATERIALS.keys()):
        mat = MATERIALS[mid]
        px_lo_base, px_hi_base = MATERIAL_PRESSURE_RANGES[mid]

        for lid in sorted(LAYUPS.keys()):
            combo_count += 1
            angles = LAYUPS[lid]['angles']
            fpf, ca, cm, ply_data = compute_fpf(mat, angles)

            if fpf is None:
                fpf = 0.0; ca = 0; cm = "error"

            bs = LAYUP_SCALE_FACTORS[lid]
            px_lo = round(px_lo_base * bs, 2)
            px_hi = round(px_hi_base * bs, 2)

            lo_frac = px_lo / fpf if fpf > 0 else 999
            hi_frac = px_hi / fpf if fpf > 0 else 999

            if 0.01 < lo_frac < 0.5 and 0.3 < hi_frac < 3.0:
                quality = "good"
                n_good += 1
            elif 0.001 < lo_frac < 1.0 and 0.1 < hi_frac < 5.0:
                quality = "marginal"
                n_marginal += 1
            else:
                quality = "bad"
                n_bad += 1

            combo = {
                'mat_id': mid, 'mat_name': mat['name'],
                'layup_id': lid, 'layup_name': LAYUPS[lid]['name'],
                'n_plies': len(angles),
                'fpf_MPa': fpf, 'crit_angle': ca, 'mode': cm,
                'scale_factor': round(bs, 4),
                'px_lo': px_lo, 'px_hi': px_hi,
                'lo_over_fpf': round(lo_frac, 4),
                'hi_over_fpf': round(hi_frac, 4),
                'quality': quality
            }
            results['combos'].append(combo)

        if combo_count % 140 == 0:
            print(f"  {combo_count}/770 done...", flush=True)

    results['summary'] = {
        'total': n_good + n_marginal + n_bad,
        'good': n_good, 'marginal': n_marginal, 'bad': n_bad,
        'good_pct': round(100*n_good/(n_good+n_marginal+n_bad), 1)
    }

    print(f"\nResults: {n_good} good, {n_marginal} marginal, {n_bad} bad out of {combo_count}")

    # Save JSON for documentation script
    with open(r"C:\CalculiX\test_composite\verification_results.json", 'w') as f:
        json.dump(results, f, indent=2)
    print("Saved verification_results.json")

    # Also print summary table
    print("\n=== QI FPF Summary ===")
    for mid in sorted(results['qi_fpf'].keys(), key=int):
        q = results['qi_fpf'][mid]
        m = results['materials'][mid]
        print(f"  {mid:>2}. {m['name']:<20} FPF={q['fpf_MPa']:>8.1f} MPa  "
              f"crit={q['crit_angle']:>3}° {q['mode']:<10}  "
              f"px=[{q['px_lo']:.1f}, {q['px_hi']:.1f}]")

if __name__ == "__main__":
    main()
