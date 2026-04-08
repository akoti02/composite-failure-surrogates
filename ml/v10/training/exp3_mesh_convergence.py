"""
Experiment 3: Mesh Convergence Study
=====================================
Tests how mesh density affects simulation outputs (stress, failure indices).
Uses a single representative geometry (1 defect, centered) at 5 mesh levels.

Mesh levels (CharacteristicLengthMin / Max / DistMin / DistMax):
  1. Very coarse:  2.0 / 6.0 / 2.0 / 20.0
  2. Coarse:       1.0 / 5.0 / 1.0 / 20.0
  3. Medium:       0.5 / 3.0 / 0.5 / 15.0  (production)
  4. Fine:         0.3 / 2.0 / 0.2 / 10.0
  5. Very fine:    0.15 / 1.0 / 0.1 / 5.0

Runs CalculiX at each level, compares max Mises, Tsai-Wu, Hashin, element count.
"""
import subprocess
import os
import sys
import math
import json
import time
import shutil
import tempfile

# ---- Plate / Material constants (match batch_100k.py) ----
PLATE_L = 100.0
PLATE_W = 50.0
LAYUP = [0, 45, -45, 90, 90, -45, 45, 0]

E1, E2, E3 = 135000.0, 10000.0, 10000.0
NU12, NU13, NU23 = 0.27, 0.27, 0.45
G12, G13, G23 = 5200.0, 5200.0, 3900.0

XT, XC = 1500.0, 1200.0
YT, YC = 50.0, 250.0
SL, ST = 70.0, 35.0

CCX_EXE = "/usr/bin/ccx"
WORK_DIR = os.path.expanduser("~/sims/mesh_convergence")

# ---- Fixed test case ----
TEST_CASE = {
    'sim_id': 0,
    'n_defects': 1,
    'defect1_x': 50.0,
    'defect1_y': 25.0,
    'defect1_half_length': 5.0,
    'defect1_width': 0.4,
    'defect1_angle': 0.0,
    'pressure_x': 50.0,
    'pressure_y': 25.0,
    'ply_thickness': 0.15,
}

# ---- Mesh levels ----
MESH_LEVELS = [
    {'name': 'very_coarse', 'cl_min': 2.0, 'cl_max': 6.0, 'dist_min': 2.0, 'dist_max': 20.0, 'size_min': 2.0, 'size_max': 6.0},
    {'name': 'coarse',      'cl_min': 1.0, 'cl_max': 5.0, 'dist_min': 1.0, 'dist_max': 20.0, 'size_min': 1.0, 'size_max': 5.0},
    {'name': 'medium',      'cl_min': 0.5, 'cl_max': 3.0, 'dist_min': 0.5, 'dist_max': 15.0, 'size_min': 0.5, 'size_max': 3.0},
    {'name': 'fine',        'cl_min': 0.3, 'cl_max': 2.0, 'dist_min': 0.2, 'dist_max': 10.0, 'size_min': 0.3, 'size_max': 2.0},
    {'name': 'very_fine',   'cl_min': 0.15,'cl_max': 1.0, 'dist_min': 0.1, 'dist_max': 5.0,  'size_min': 0.15,'size_max': 1.0},
]


def create_crack_polygon(cx, cy, half_length, width, angle_deg):
    """Create a simple rectangular crack (no jaggedness for reproducibility)."""
    import gmsh
    a_rad = math.radians(angle_deg)
    dx = math.cos(a_rad) * half_length
    dy = math.sin(a_rad) * half_length
    nx = -math.sin(a_rad) * width / 2
    ny = math.cos(a_rad) * width / 2

    corners = [
        (cx - dx + nx, cy - dy + ny),
        (cx + dx + nx, cy + dy + ny),
        (cx + dx - nx, cy + dy - ny),
        (cx - dx - nx, cy - dy - ny),
    ]
    return corners


def create_mesh(polygon, mesh_level, job_name):
    """Generate plate mesh with gmsh at given mesh density."""
    import gmsh
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add(job_name)

    plate = gmsh.model.occ.addRectangle(0, 0, 0, PLATE_L, PLATE_W)

    pts = []
    for gx, gy in polygon:
        gx = max(0.01, min(PLATE_L - 0.01, gx))
        gy = max(0.01, min(PLATE_W - 0.01, gy))
        pts.append(gmsh.model.occ.addPoint(gx, gy, 0))
    lines = []
    for i in range(len(pts)):
        lines.append(gmsh.model.occ.addLine(pts[i], pts[(i + 1) % len(pts)]))
    loop = gmsh.model.occ.addCurveLoop(lines)
    surf = gmsh.model.occ.addPlaneSurface([loop])
    gmsh.model.occ.cut([(2, plate)], [(2, surf)])
    gmsh.model.occ.synchronize()

    surfaces = gmsh.model.getEntities(2)
    gmsh.model.addPhysicalGroup(2, [s[1] for s in surfaces], tag=5, name="plate")

    all_curves = gmsh.model.getEntities(1)
    tol = 0.1
    left_c, bottom_c, right_c, top_c = [], [], [], []
    for _, tag in all_curves:
        bbox = gmsh.model.getBoundingBox(1, tag)
        xmin, ymin, _, xmax, ymax, _ = bbox
        if abs(xmin) < tol and abs(xmax) < tol:
            left_c.append(tag)
        elif abs(xmin - PLATE_L) < tol and abs(xmax - PLATE_L) < tol:
            right_c.append(tag)
        elif abs(ymin) < tol and abs(ymax) < tol and xmax - xmin > 1.0:
            bottom_c.append(tag)
        elif abs(ymin - PLATE_W) < tol and abs(ymax - PLATE_W) < tol and xmax - xmin > 1.0:
            top_c.append(tag)

    if left_c:   gmsh.model.addPhysicalGroup(1, left_c,   tag=1, name="left")
    if bottom_c: gmsh.model.addPhysicalGroup(1, bottom_c, tag=2, name="bottom")
    if right_c:  gmsh.model.addPhysicalGroup(1, right_c,  tag=3, name="right")
    if top_c:    gmsh.model.addPhysicalGroup(1, top_c,    tag=4, name="top")

    ml = mesh_level
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", ml['cl_min'])
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", ml['cl_max'])

    crack_curves = []
    for _, tag in all_curves:
        bbox = gmsh.model.getBoundingBox(1, tag)
        xmin, ymin, _, xmax, ymax, _ = bbox
        is_edge = (abs(xmin) < tol and abs(xmax) < tol) or \
                  (abs(xmin - PLATE_L) < tol and abs(xmax - PLATE_L) < tol) or \
                  (abs(ymin) < tol and abs(ymax) < tol and xmax - xmin > 5) or \
                  (abs(ymin - PLATE_W) < tol and abs(ymax - PLATE_W) < tol and xmax - xmin > 5)
        if not is_edge:
            crack_curves.append(tag)

    if crack_curves:
        fd = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(fd, "CurvesList", crack_curves)
        gmsh.model.mesh.field.setNumber(fd, "Sampling", 200)
        ft = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(ft, "InField", fd)
        gmsh.model.mesh.field.setNumber(ft, "SizeMin", ml['size_min'])
        gmsh.model.mesh.field.setNumber(ft, "SizeMax", ml['size_max'])
        gmsh.model.mesh.field.setNumber(ft, "DistMin", ml['dist_min'])
        gmsh.model.mesh.field.setNumber(ft, "DistMax", ml['dist_max'])
        gmsh.model.mesh.field.setAsBackgroundMesh(ft)

    gmsh.model.mesh.generate(2)

    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    nodes = {}
    for i, tag in enumerate(node_tags):
        nodes[int(tag)] = (node_coords[3*i], node_coords[3*i+1], node_coords[3*i+2])

    elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(2)
    elements = []
    for etype, etags, enodes in zip(elem_types, elem_tags, elem_node_tags):
        npe = gmsh.model.mesh.getElementProperties(etype)[3]
        for i, etag in enumerate(etags):
            enlist = [int(enodes[i*npe + j]) for j in range(npe)]
            elements.append((int(etag), npe, enlist))

    bc_sets = {}
    for phys_tag, name in [(1, "left"), (2, "bottom"), (3, "right"), (4, "top")]:
        nset = set()
        try:
            ents = gmsh.model.getEntitiesForPhysicalGroup(1, phys_tag)
            for ent in ents:
                ntags, _, _ = gmsh.model.mesh.getNodes(1, ent, includeBoundary=True)
                nset.update(int(t) for t in ntags)
        except:
            pass
        bc_sets[name] = nset

    corner = min(nodes.keys(), key=lambda n: nodes[n][0]**2 + nodes[n][1]**2)
    bc_sets["corner"] = {corner}

    gmsh.finalize()
    return nodes, elements, bc_sets


def write_inp(nodes, elements, bc_sets, case, job_name, work_dir):
    ply_t = case['ply_thickness']
    total_t = 8 * ply_t
    filepath = os.path.join(work_dir, f"{job_name}.inp")

    ori_names = {0: "ORI_0", 45: "ORI_45", -45: "ORI_M45", 90: "ORI_90"}

    with open(filepath, 'w') as f:
        f.write("** Mesh convergence study\n*HEADING\nMesh convergence\n")
        f.write("*NODE\n")
        for nid in sorted(nodes.keys()):
            x, y, z = nodes[nid]
            f.write(f"  {nid}, {x:.8f}, {y:.8f}, {z:.8f}\n")

        f.write("*ELEMENT, TYPE=S6, ELSET=PLATE\n")
        for eid, npe, enlist in elements:
            f.write(f"  {eid}, {', '.join(str(n) for n in enlist)}\n")

        f.write("*MATERIAL, NAME=CFRP_UD\n")
        f.write("*ELASTIC, TYPE=ENGINEERING CONSTANTS\n")
        f.write(f"{E1}, {E2}, {E3}, {NU12}, {NU13}, {NU23}, {G12}, {G13}\n{G23}\n")

        f.write("*ORIENTATION, NAME=ORI_0, SYSTEM=RECTANGULAR\n1.0, 0.0, 0.0, 0.0, 1.0, 0.0\n")
        f.write("*ORIENTATION, NAME=ORI_45, SYSTEM=RECTANGULAR\n0.7071068, 0.7071068, 0.0, -0.7071068, 0.7071068, 0.0\n")
        f.write("*ORIENTATION, NAME=ORI_M45, SYSTEM=RECTANGULAR\n0.7071068, -0.7071068, 0.0, 0.7071068, 0.7071068, 0.0\n")
        f.write("*ORIENTATION, NAME=ORI_90, SYSTEM=RECTANGULAR\n0.0, 1.0, 0.0, -1.0, 0.0, 0.0\n")

        f.write("*SHELL SECTION, COMPOSITE, ELSET=PLATE, OFFSET=0\n")
        for angle in LAYUP:
            f.write(f"{ply_t}, 3, CFRP_UD, {ori_names[angle]}\n")

        for name, nset in bc_sets.items():
            if nset:
                f.write(f"*NSET, NSET={name.upper()}\n")
                nids = sorted(nset)
                for k in range(0, len(nids), 16):
                    f.write(", ".join(str(n) for n in nids[k:k+16]) + "\n")

        f.write("*BOUNDARY\nLEFT, 1, 1, 0.0\nCORNER, 2, 3, 0.0\n")

        px, py = case['pressure_x'], case['pressure_y']
        f.write("*STEP\n*STATIC\n")

        if bc_sets.get("right"):
            n_right = len(bc_sets["right"])
            f.write(f"*CLOAD\nRIGHT, 1, {(px * PLATE_W * total_t) / n_right:.8f}\n")
        if bc_sets.get("top"):
            n_top = len(bc_sets["top"])
            f.write(f"*CLOAD\nTOP, 2, {(py * PLATE_L * total_t) / n_top:.8f}\n")
        if bc_sets.get("bottom"):
            n_bottom = len(bc_sets["bottom"])
            f.write(f"*CLOAD\nBOTTOM, 2, {-(py * PLATE_L * total_t) / n_bottom:.8f}\n")

        f.write("*EL PRINT, ELSET=PLATE\nS\n*END STEP\n")
    return filepath


def parse_stresses(dat_path):
    stress_data = []
    in_block = False
    with open(dat_path) as f:
        for line in f:
            if 'stresses (elem' in line:
                in_block = True
                continue
            if in_block:
                parts = line.split()
                if len(parts) >= 8:
                    try:
                        s11 = float(parts[2])
                        s22 = float(parts[3])
                        s33 = float(parts[4])
                        s12 = float(parts[5])
                        s13 = float(parts[6])
                        s23 = float(parts[7])
                        vm = math.sqrt(0.5 * ((s11-s22)**2 + (s22-s33)**2 + (s33-s11)**2
                                               + 6*(s12**2 + s13**2 + s23**2)))
                        stress_data.append((s11, s22, s12, vm))
                    except (ValueError, IndexError):
                        if any(kw in line.lower() for kw in ['displacements', 'forces', 'step']):
                            in_block = False
    return stress_data


def compute_results(stress_data):
    if not stress_data:
        return None

    F1 = 1.0/XT - 1.0/XC
    F2 = 1.0/YT - 1.0/YC
    F11 = 1.0/(XT*XC)
    F22 = 1.0/(YT*YC)
    F66 = 1.0/(SL*SL)
    F12 = -0.5 * math.sqrt(F11 * F22)

    max_mises = 0
    max_s11 = -1e30
    min_s11 = 1e30
    max_s12 = 0
    max_tw = 0
    max_hft = 0
    max_hfc = 0
    max_hmt = 0
    max_hmc = 0

    for s11, s22, s12, vm in stress_data:
        max_mises = max(max_mises, vm)
        max_s11 = max(max_s11, s11)
        min_s11 = min(min_s11, s11)
        max_s12 = max(max_s12, abs(s12))

        tw = F1*s11 + F2*s22 + F11*s11**2 + F22*s22**2 + F66*s12**2 + 2*F12*s11*s22
        max_tw = max(max_tw, tw)

        hft = (s11/XT)**2 + (s12/SL)**2 if s11 > 0 else 0
        hfc = (s11/XC)**2 if s11 < 0 else 0
        hmt = (s22/YT)**2 + (s12/SL)**2 if s22 > 0 else 0
        hmc = (s22/(2*ST))**2 + ((YC/(2*ST))**2 - 1)*(s22/YC) + (s12/SL)**2 if s22 < 0 else 0
        max_hft = max(max_hft, hft)
        max_hfc = max(max_hfc, hfc)
        max_hmt = max(max_hmt, hmt)
        max_hmc = max(max_hmc, hmc)

    return {
        'max_mises': max_mises,
        'max_s11': max_s11,
        'min_s11': min_s11,
        'max_s12': max_s12,
        'tsai_wu_index': max_tw,
        'max_hashin_ft': max_hft,
        'max_hashin_fc': max_hfc,
        'max_hashin_mt': max_hmt,
        'max_hashin_mc': max_hmc,
    }


def main():
    t0 = time.time()
    print("=" * 70)
    print("EXPERIMENT 3: MESH CONVERGENCE STUDY")
    print("=" * 70)

    os.makedirs(WORK_DIR, exist_ok=True)

    # Create crack polygon
    c = TEST_CASE
    polygon = create_crack_polygon(
        c['defect1_x'], c['defect1_y'],
        c['defect1_half_length'], c['defect1_width'],
        c['defect1_angle']
    )
    print(f"Crack: center=({c['defect1_x']},{c['defect1_y']}), "
          f"half_len={c['defect1_half_length']}, width={c['defect1_width']}, "
          f"angle={c['defect1_angle']}°")
    print(f"Loading: px={c['pressure_x']} MPa, py={c['pressure_y']} MPa")
    print(f"Layup: {LAYUP}, ply_t={c['ply_thickness']} mm")

    all_results = []

    for ml in MESH_LEVELS:
        print(f"\n{'='*50}")
        print(f"MESH LEVEL: {ml['name']}")
        print(f"  cl_min={ml['cl_min']}, cl_max={ml['cl_max']}")
        print(f"  size_min={ml['size_min']}, size_max={ml['size_max']}")
        print(f"  dist_min={ml['dist_min']}, dist_max={ml['dist_max']}")

        job = f"mesh_{ml['name']}"
        sub_dir = os.path.join(WORK_DIR, job)
        os.makedirs(sub_dir, exist_ok=True)

        # Mesh
        t1 = time.time()
        nodes, elements, bc_sets = create_mesh(polygon, ml, job)
        mesh_time = time.time() - t1
        n_nodes = len(nodes)
        n_elems = len(elements)
        print(f"  Mesh: {n_nodes} nodes, {n_elems} elements ({mesh_time:.1f}s)")

        # Write .inp
        inp_path = write_inp(nodes, elements, bc_sets, TEST_CASE, job, sub_dir)

        # Run ccx
        t2 = time.time()
        try:
            result = subprocess.run(
                [CCX_EXE, job],
                cwd=sub_dir,
                capture_output=True, text=True,
                timeout=600
            )
            solve_time = time.time() - t2
            print(f"  Solver: {solve_time:.1f}s, returncode={result.returncode}")
        except subprocess.TimeoutExpired:
            print(f"  Solver: TIMEOUT (600s)")
            all_results.append({'name': ml['name'], 'n_nodes': n_nodes,
                                'n_elements': n_elems, 'status': 'TIMEOUT'})
            continue

        # Parse results
        dat_path = os.path.join(sub_dir, f"{job}.dat")
        if not os.path.exists(dat_path):
            print(f"  ERROR: no .dat file")
            all_results.append({'name': ml['name'], 'n_nodes': n_nodes,
                                'n_elements': n_elems, 'status': 'NO_DAT'})
            continue

        stress_data = parse_stresses(dat_path)
        if not stress_data:
            print(f"  ERROR: no stress data parsed")
            all_results.append({'name': ml['name'], 'n_nodes': n_nodes,
                                'n_elements': n_elems, 'status': 'NO_STRESS'})
            continue

        metrics = compute_results(stress_data)
        metrics['name'] = ml['name']
        metrics['n_nodes'] = n_nodes
        metrics['n_elements'] = n_elems
        metrics['n_stress_points'] = len(stress_data)
        metrics['mesh_time_s'] = mesh_time
        metrics['solve_time_s'] = solve_time
        metrics['status'] = 'OK'
        all_results.append(metrics)

        print(f"  Integration points: {len(stress_data)}")
        print(f"  max_mises = {metrics['max_mises']:.2f}")
        print(f"  tsai_wu   = {metrics['tsai_wu_index']:.4f}")
        print(f"  hashin_mt = {metrics['max_hashin_mt']:.4f}")

    # Summary table
    print(f"\n\n{'='*70}")
    print("CONVERGENCE SUMMARY")
    print(f"{'='*70}")
    print(f"{'Level':<12} {'Elems':>7} {'Nodes':>7} {'IPs':>8} "
          f"{'Mises':>10} {'TW':>10} {'H_mt':>10} {'Solve(s)':>8}")
    print("-" * 85)
    for r in all_results:
        if r['status'] != 'OK':
            print(f"{r['name']:<12} {r['n_elements']:>7} {r['n_nodes']:>7} {'---':>8} "
                  f"{'---':>10} {'---':>10} {'---':>10} {'---':>8}  [{r['status']}]")
        else:
            print(f"{r['name']:<12} {r['n_elements']:>7} {r['n_nodes']:>7} {r['n_stress_points']:>8} "
                  f"{r['max_mises']:>10.2f} {r['tsai_wu_index']:>10.4f} {r['max_hashin_mt']:>10.4f} "
                  f"{r['solve_time_s']:>8.1f}")

    # Richardson extrapolation for max_mises (if 2+ OK results)
    ok = [r for r in all_results if r['status'] == 'OK']
    if len(ok) >= 2:
        finest = ok[-1]
        second = ok[-2]
        print(f"\n  Relative change (finest vs second-finest):")
        for key in ['max_mises', 'tsai_wu_index', 'max_hashin_mt', 'max_hashin_ft']:
            v1 = second.get(key, 0)
            v2 = finest.get(key, 0)
            if abs(v1) > 1e-10:
                pct = abs(v2 - v1) / abs(v1) * 100
                print(f"    {key}: {pct:.2f}% change")

    # Save
    out_path = os.path.join(os.path.expanduser("~/sims"), "exp3_mesh_convergence_results.json")
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {out_path}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == '__main__':
    main()
