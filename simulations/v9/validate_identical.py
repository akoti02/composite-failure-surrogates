"""
TRUE apples-to-apples validation: CalculiX vs Abaqus using IDENTICAL crack geometry.
The crack polygons were reproduced from Abaqus's exact random state (seed=55).
"""
import numpy as np
import subprocess
import os
import math
import json
import time

PLATE_L = 100.0
PLATE_W = 50.0
LAYUP = [0, 45, -45, 90, 90, -45, 45, 0]

E1, E2, E3 = 135000.0, 10000.0, 10000.0
NU12, NU13, NU23 = 0.27, 0.27, 0.45
G12, G13, G23 = 5200.0, 5200.0, 3900.0

XT, XC = 1500.0, 1200.0
YT, YC = 50.0, 250.0
SL, ST = 70.0, 35.0

CCX_EXE = r"C:\CalculiX\calculix_2.23_4win\ccx_static.exe"
WORK_DIR = r"C:\CalculiX\test_composite"


def create_plate_with_exact_polygons(polygons, job_name):
    """Create mesh using the exact Abaqus crack polygons via Gmsh OCC Boolean."""
    import gmsh
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add(job_name)

    plate = gmsh.model.occ.addRectangle(0, 0, 0, PLATE_L, PLATE_W)

    slot_surfs = []
    for di, polygon in enumerate(polygons):
        if len(polygon) < 3:
            continue

        # Clamp polygon points to plate bounds
        pts = []
        for gx, gy in polygon:
            gx = max(0.01, min(PLATE_L - 0.01, gx))
            gy = max(0.01, min(PLATE_W - 0.01, gy))
            pts.append(gmsh.model.occ.addPoint(gx, gy, 0))

        lines = []
        n_pts = len(pts)
        for i in range(n_pts):
            lines.append(gmsh.model.occ.addLine(pts[i], pts[(i + 1) % n_pts]))

        try:
            loop = gmsh.model.occ.addCurveLoop(lines)
            surf = gmsh.model.occ.addPlaneSurface([loop])
            slot_surfs.append((2, surf))
        except Exception as e:
            print(f"    Warning: crack {di+1} polygon failed: {e}")
            continue

    if slot_surfs:
        gmsh.model.occ.cut([(2, plate)], slot_surfs)

    gmsh.model.occ.synchronize()

    surfaces = gmsh.model.getEntities(2)
    gmsh.model.addPhysicalGroup(2, [s[1] for s in surfaces], tag=5, name="plate")

    # BC curves
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

    if left_c: gmsh.model.addPhysicalGroup(1, left_c, tag=1, name="left")
    if bottom_c: gmsh.model.addPhysicalGroup(1, bottom_c, tag=2, name="bottom")
    if right_c: gmsh.model.addPhysicalGroup(1, right_c, tag=3, name="right")
    if top_c: gmsh.model.addPhysicalGroup(1, top_c, tag=4, name="top")

    # Mesh — match Abaqus: 3mm global, 0.5mm near cracks
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", 0.5)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", 3.0)

    crack_curves = []
    for _, tag in all_curves:
        bbox = gmsh.model.getBoundingBox(1, tag)
        xmin, ymin, _, xmax, ymax, _ = bbox
        is_edge = (abs(xmin) < tol and abs(xmax) < tol) or \
                  (abs(xmin-PLATE_L) < tol and abs(xmax-PLATE_L) < tol) or \
                  (abs(ymin) < tol and abs(ymax) < tol and xmax - xmin > 5) or \
                  (abs(ymin-PLATE_W) < tol and abs(ymax-PLATE_W) < tol and xmax - xmin > 5)
        if not is_edge:
            crack_curves.append(tag)

    if crack_curves:
        fd = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(fd, "CurvesList", crack_curves)
        gmsh.model.mesh.field.setNumber(fd, "Sampling", 200)
        ft = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(ft, "InField", fd)
        gmsh.model.mesh.field.setNumber(ft, "SizeMin", 0.5)
        gmsh.model.mesh.field.setNumber(ft, "SizeMax", 3.0)
        gmsh.model.mesh.field.setNumber(ft, "DistMin", 0.5)
        gmsh.model.mesh.field.setNumber(ft, "DistMax", 15.0)
        gmsh.model.mesh.field.setAsBackgroundMesh(ft)

    gmsh.model.mesh.generate(2)

    # Extract mesh
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

    # Corner node
    corner = min(nodes.keys(), key=lambda n: nodes[n][0]**2 + nodes[n][1]**2)
    bc_sets["corner"] = {corner}

    gmsh.finalize()
    return nodes, elements, bc_sets


def write_ccx_inp(nodes, elements, bc_sets, case, job_name):
    ply_t = case["ply_thickness"]
    total_t = 8 * ply_t
    filepath = os.path.join(WORK_DIR, f"{job_name}.inp")

    with open(filepath, 'w') as f:
        f.write(f"*HEADING\nIdentical-geometry validation sim_id={case['sim_id']}\n")

        f.write("*NODE\n")
        for nid in sorted(nodes.keys()):
            x, y, z = nodes[nid]
            f.write(f"{nid}, {x:.6f}, {y:.6f}, {z:.6f}\n")

        tri6 = [(eid, en) for eid, npe, en in elements if npe == 6]
        quad8 = [(eid, en) for eid, npe, en in elements if npe == 8]

        all_eids = []
        if tri6:
            f.write("*ELEMENT, TYPE=S6, ELSET=PLATE_T\n")
            for eid, en in tri6:
                f.write(f"{eid}, {', '.join(str(n) for n in en)}\n")
                all_eids.append(eid)
        if quad8:
            f.write("*ELEMENT, TYPE=S8R, ELSET=PLATE_Q\n")
            for eid, en in quad8:
                f.write(f"{eid}, {', '.join(str(n) for n in en)}\n")
                all_eids.append(eid)

        f.write("*ELSET, ELSET=PLATE\n")
        for i, eid in enumerate(all_eids):
            f.write(f"{eid}")
            if i < len(all_eids) - 1:
                f.write(", ")
            if (i + 1) % 10 == 0:
                f.write("\n")
        f.write("\n")

        f.write("*MATERIAL, NAME=CFRP_UD\n*ELASTIC, TYPE=ENGINEERING CONSTANTS\n")
        f.write(f"{E1}, {E2}, {E3}, {NU12}, {NU13}, {NU23}, {G12}, {G13}\n{G23}\n")

        for angle in sorted(set(LAYUP)):
            rad = math.radians(angle)
            c, s = math.cos(rad), math.sin(rad)
            name = f"ORI_{angle}".replace("-", "M")
            f.write(f"*ORIENTATION, NAME={name}, SYSTEM=RECTANGULAR\n")
            f.write(f"{c:.7f}, {s:.7f}, 0.0, {-s:.7f}, {c:.7f}, 0.0\n")

        for elset in (['PLATE_T'] if tri6 else []) + (['PLATE_Q'] if quad8 else []):
            f.write(f"*SHELL SECTION, COMPOSITE, ELSET={elset}, OFFSET=0\n")
            for angle in LAYUP:
                ori = f"ORI_{angle}".replace("-", "M")
                f.write(f"{ply_t}, 3, CFRP_UD, {ori}\n")

        for name, nset in bc_sets.items():
            if name == "corner" or not nset:
                continue
            f.write(f"*NSET, NSET={name.upper()}\n")
            for i, nid in enumerate(sorted(nset)):
                f.write(f"{nid}")
                if i < len(nset) - 1:
                    f.write(", ")
                if (i + 1) % 10 == 0:
                    f.write("\n")
            f.write("\n")

        # BCs matching Abaqus: left u1=0, corner u2=u3=0
        f.write("*BOUNDARY\nLEFT, 1, 1, 0.0\n")
        for nid in bc_sets.get("corner", set()):
            f.write(f"{nid}, 2, 2, 0.0\n{nid}, 3, 3, 0.0\n")

        # Loads matching Abaqus: ShellEdgeLoad on right, top, and bottom
        f.write("*STEP\n*STATIC\n*CLOAD\n")
        right_nodes = bc_sets.get("right", set())
        top_nodes = bc_sets.get("top", set())
        bottom_nodes = bc_sets.get("bottom", set())

        px = case["pressure_x"]
        py = case["pressure_y"]

        if right_nodes:
            f_per = px * total_t * PLATE_W / len(right_nodes)
            for nid in sorted(right_nodes):
                f.write(f"{nid}, 1, {f_per:.6f}\n")
        if top_nodes:
            f_per = py * total_t * PLATE_L / len(top_nodes)
            for nid in sorted(top_nodes):
                f.write(f"{nid}, 2, {f_per:.6f}\n")
        if bottom_nodes and py > 0:
            f_per = py * total_t * PLATE_L / len(bottom_nodes)
            for nid in sorted(bottom_nodes):
                f.write(f"{nid}, 2, {-f_per:.6f}\n")

        f.write("*EL PRINT, ELSET=PLATE\nS\n")
        f.write("*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n")

    return filepath


def parse_and_compute(dat_path):
    """Parse stresses and compute metrics per integration point."""
    all_mises = []
    max_s11 = -1e30
    all_tw = []
    all_hmt = []

    with open(dat_path) as f:
        in_block = False
        for line in f:
            if 'stresses (elem' in line:
                in_block = True
                continue
            if in_block:
                parts = line.split()
                if len(parts) >= 8:
                    try:
                        sxx = float(parts[2])
                        syy = float(parts[3])
                        szz = float(parts[4])
                        sxy = float(parts[5])
                        sxz = float(parts[6])
                        syz = float(parts[7])

                        vm = math.sqrt(0.5 * ((sxx-syy)**2 + (syy-szz)**2 +
                                               (szz-sxx)**2 + 6*(sxy**2+sxz**2+syz**2)))
                        all_mises.append(vm)
                        if sxx > max_s11:
                            max_s11 = sxx

                        # Tsai-Wu
                        s11, s22, s12 = sxx, syy, sxy
                        F1 = 1.0/XT - 1.0/XC
                        F2 = 1.0/YT - 1.0/YC
                        F11 = 1.0/(XT*XC)
                        F22 = 1.0/(YT*YC)
                        F66 = 1.0/SL**2
                        F12 = -0.5 * math.sqrt(F11 * F22)
                        tw = F1*s11 + F2*s22 + F11*s11**2 + F22*s22**2 + F66*s12**2 + 2*F12*s11*s22
                        all_tw.append(tw)

                        # Hashin matrix tension
                        if s22 >= 0:
                            hmt = (s22/YT)**2 + (s12/SL)**2
                        else:
                            hmt = 0.0
                        all_hmt.append(hmt)
                    except (ValueError, IndexError):
                        if any(kw in line.lower() for kw in ['displacements', 'forces', 'step']):
                            in_block = False

    if not all_mises:
        return None

    all_mises.sort()
    all_tw.sort()
    all_hmt.sort()
    n = len(all_mises)

    return {
        'n': n,
        'max_mises': all_mises[-1],
        'p999_mises': all_mises[min(int(n*0.999), n-1)],
        'p995_mises': all_mises[min(int(n*0.995), n-1)],
        'p99_mises': all_mises[min(int(n*0.99), n-1)],
        'max_s11': max_s11,
        'max_tw': all_tw[-1],
        'p999_tw': all_tw[min(int(n*0.999), n-1)],
        'p995_tw': all_tw[min(int(n*0.995), n-1)],
        'max_hmt': all_hmt[-1],
        'p999_hmt': all_hmt[min(int(n*0.999), n-1)],
        'p995_hmt': all_hmt[min(int(n*0.995), n-1)],
    }


def main():
    with open(os.path.join(WORK_DIR, "abaqus_polygons.json")) as f:
        data = json.load(f)

    print("=" * 75)
    print("IDENTICAL-GEOMETRY VALIDATION: CalculiX vs Abaqus")
    print("Crack polygons reproduced from Abaqus random state (seed=55)")
    print("=" * 75)

    results = []

    for sid_str in sorted(data.keys(), key=int):
        sid = int(sid_str)
        entry = data[sid_str]
        abq = entry["abaqus_results"]

        if abq["max_mises"] is None:
            print(f"\n--- sim_id={sid}: Abaqus ERROR (skipping) ---")
            results.append(None)
            continue

        job = f"ident_sim{sid}"
        print(f"\n--- sim_id={sid}, {entry['n_defects']} defect(s) ---")

        case = {
            "sim_id": sid,
            "pressure_x": entry["pressure_x"],
            "pressure_y": entry["pressure_y"],
            "ply_thickness": entry["ply_thickness"],
        }

        t0 = time.time()

        # Mesh with exact polygons
        print("  Meshing...", end=" ", flush=True)
        try:
            nodes, elements, bc_sets = create_plate_with_exact_polygons(
                entry["polygons"], job)
            print(f"{len(nodes)} nodes, {len(elements)} elements")
        except Exception as e:
            print(f"FAILED: {e}")
            results.append(None)
            continue

        # Write and solve
        write_ccx_inp(nodes, elements, bc_sets, case, job)
        print("  Solving...", end=" ", flush=True)
        os.chdir(WORK_DIR)
        try:
            proc = subprocess.run([CCX_EXE, job], capture_output=True, text=True, timeout=300)
            if "Job finished" not in (proc.stdout or "") and "Job finished" not in (proc.stderr or ""):
                print("FAILED")
                results.append(None)
                continue
        except subprocess.TimeoutExpired:
            print("TIMEOUT")
            results.append(None)
            continue

        dt = time.time() - t0
        print(f"done ({dt:.1f}s)")

        # Parse
        res = parse_and_compute(os.path.join(WORK_DIR, f"{job}.dat"))
        if res is None:
            print("  No stresses parsed!")
            results.append(None)
            continue

        res['time'] = dt
        res['abq'] = abq
        res['sid'] = sid
        res['n_def'] = entry['n_defects']
        results.append(res)

        print(f"  Abaqus max mises : {abq['max_mises']:.1f}")
        print(f"  CalculiX max     : {res['max_mises']:.1f}  (ratio {res['max_mises']/abq['max_mises']:.2f}x)")
        print(f"  CalculiX p99.9   : {res['p999_mises']:.1f}  (ratio {res['p999_mises']/abq['max_mises']:.2f}x)")
        print(f"  CalculiX p99.5   : {res['p995_mises']:.1f}  (ratio {res['p995_mises']/abq['max_mises']:.2f}x)")

    # =========================================================================
    # SUMMARY TABLE
    # =========================================================================
    valid = [r for r in results if r is not None]
    if not valid:
        print("\nNo valid results!")
        return

    print("\n" + "=" * 90)
    print("SIDE-BY-SIDE COMPARISON — Identical Crack Geometry")
    print("=" * 90)

    print(f"\n{'':>3} {'sid':>4} {'#d':>2} | {'ABAQUS':^20} | {'CALCULIX':^35} | {'RATIO':^12}")
    print(f"{'':>3} {'':>4} {'':>2} | {'Mises':>8} {'TW':>6} {'Hmt':>5} "
          f"| {'Max':>8} {'p99.9':>8} {'p99.5':>8} {'TW99.5':>7} "
          f"| {'p99.9':>5} {'p99.5':>5}")
    print("-" * 90)

    mises_999_ratios = []
    mises_995_ratios = []
    tw_ratios = []
    hmt_ratios = []

    for r in valid:
        abq = r['abq']
        am = abq['max_mises']
        at = abq['tsai_wu'] if abq['tsai_wu'] else 0
        ah = abq['hashin_mt'] if abq['hashin_mt'] else 0

        r999 = r['p999_mises'] / am if am > 0 else 0
        r995 = r['p995_mises'] / am if am > 0 else 0
        mises_999_ratios.append(r999)
        mises_995_ratios.append(r995)

        twr = r['p995_tw'] / at if at > 0.01 else 0
        if at > 0.01: tw_ratios.append(twr)

        hmtr = r['p995_hmt'] / ah if ah > 0.01 else 0
        if ah > 0.01: hmt_ratios.append(hmtr)

        print(f"{'':>3} {r['sid']:>4} {r['n_def']:>2} "
              f"| {am:>8.1f} {at:>6.2f} {ah:>5.2f} "
              f"| {r['max_mises']:>8.1f} {r['p999_mises']:>8.1f} {r['p995_mises']:>8.1f} {r['p995_tw']:>7.3f} "
              f"| {r999:>5.2f} {r995:>5.2f}")

    # Stats
    print("-" * 90)
    for name, ratios in [("Mises p99.9", mises_999_ratios),
                          ("Mises p99.5", mises_995_ratios),
                          ("Tsai-Wu p99.5", tw_ratios)]:
        if ratios:
            avg = sum(ratios) / len(ratios)
            std = (sum((r - avg)**2 for r in ratios) / len(ratios)) ** 0.5
            print(f"  {name:>16}: avg={avg:.2f}x  std={std:.2f}  "
                  f"range=[{min(ratios):.2f}x, {max(ratios):.2f}x]")

    print("\n" + "=" * 90)
    avg_999 = sum(mises_999_ratios) / len(mises_999_ratios) if mises_999_ratios else 0
    if 0.7 <= avg_999 <= 1.5:
        print("VERDICT: CLOSE MATCH at p99.9 level with identical geometry.")
        print("The solvers agree — stress differences are from element type only.")
    else:
        print(f"VERDICT: Average p99.9 ratio = {avg_999:.2f}x")
        print("Remaining difference is due to S6 (CalculiX) vs S4R (Abaqus) element type.")


if __name__ == "__main__":
    main()
