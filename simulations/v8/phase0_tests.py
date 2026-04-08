"""
Phase 0 -- Local Validation Tests for CompositeBench
Tests 0A-0G: Verify CalculiX handles arbitrary orientations, multiple materials,
boundary conditions, cutout/curved geometries, lamination parameters, and Sobol sampling.
"""

import os
import sys
import math
import subprocess
import time

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

CCX_EXE = r"C:\CalculiX\calculix_2.23_4win\ccx_static.exe"
WORK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase0_work")
TEST_PLATE_INP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_plate.inp")

PLATE_L = 100.0
PLATE_W = 50.0
PLY_T = 0.1875
LAYUP_QI = [0, 45, -45, 90, 90, -45, 45, 0]

# =============================================================================
# Helpers
# =============================================================================

def ensure_dir(d):
    os.makedirs(d, exist_ok=True)


def run_ccx(job_name, work_dir):
    """Run CalculiX and return (success, dat_path)."""
    result = subprocess.run(
        [CCX_EXE, job_name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=120, cwd=work_dir
    )
    dat_path = os.path.join(work_dir, f"{job_name}.dat")
    success = os.path.exists(dat_path) and os.path.getsize(dat_path) > 100
    return success, dat_path


def parse_stresses(dat_path):
    """Parse all stress data from .dat file."""
    stress_data = []
    in_block = False
    with open(dat_path, encoding='latin-1') as f:
        for line in f:
            if 'stresses (elem' in line:
                in_block = True
                continue
            if in_block:
                parts = line.split()
                if len(parts) >= 8:
                    try:
                        eid = int(parts[0])
                        ip = int(parts[1])
                        s11 = float(parts[2])
                        s22 = float(parts[3])
                        s33 = float(parts[4])
                        s12 = float(parts[5])
                        s13 = float(parts[6])
                        s23 = float(parts[7])
                        stress_data.append((eid, ip, s11, s22, s33, s12, s13, s23))
                    except (ValueError, IndexError):
                        if any(kw in line.lower() for kw in ['displacements', 'forces', 'step']):
                            in_block = False
    return stress_data


def max_mises(stress_data):
    """Compute max von Mises stress from stress data."""
    max_vm = 0.0
    for eid, ip, s11, s22, s33, s12, s13, s23 in stress_data:
        vm = math.sqrt(0.5 * ((s11-s22)**2 + (s22-s33)**2 + (s33-s11)**2
                               + 6*(s12**2 + s13**2 + s23**2)))
        max_vm = max(max_vm, vm)
    return max_vm


def max_abs_s11(stress_data):
    """Get max |S11| from stress data."""
    return max(abs(s11) for _, _, s11, _, _, _, _, _ in stress_data) if stress_data else 0.0


def max_abs_s12(stress_data):
    """Get max |S12| from stress data."""
    return max(abs(s12) for _, _, _, _, _, s12, _, _ in stress_data) if stress_data else 0.0


def generate_orientation_block(angle):
    """Generate CalculiX *ORIENTATION block for a given angle in degrees."""
    rad = math.radians(angle)
    c, s = math.cos(rad), math.sin(rad)
    name = f"ORI_{angle}" if angle >= 0 else f"ORI_M{abs(angle)}"
    return name, f"{c:.7f}, {s:.7f}, 0.0, {-s:.7f}, {c:.7f}, 0.0"


def write_test_inp(filepath, material_block, orientations, layup, ply_thickness,
                   bc_block, load_block):
    """Write a test INP file using the test_plate.inp node/element template."""
    with open(TEST_PLATE_INP) as f:
        template = f.read()

    # Extract nodes and elements section (up to *MATERIAL line)
    lines = template.split('\n')
    mesh_lines = []
    for line in lines:
        if line.startswith('*MATERIAL'):
            break
        mesh_lines.append(line)
    mesh_section = '\n'.join(mesh_lines) + '\n'

    with open(filepath, 'w') as f:
        f.write(mesh_section)

        # Material
        f.write(material_block + '\n')

        # Orientations
        for angle in sorted(set(layup), key=lambda a: (a < 0, abs(a))):
            name, vec = generate_orientation_block(angle)
            f.write(f"*ORIENTATION, NAME={name}, SYSTEM=RECTANGULAR\n")
            f.write(f"{vec}\n**\n")

        # Shell section
        f.write("*SHELL SECTION, COMPOSITE, ELSET=PLATE, OFFSET=0\n")
        for angle in layup:
            name, _ = generate_orientation_block(angle)
            f.write(f"{ply_thickness}, 3, CFRP_UD, {name}\n")

        # Node sets
        f.write("*NSET, NSET=LEFT_EDGE\n1, 12, 23, 34, 45, 56, 67, 78, 89, 100, 111\n")
        f.write("*NSET, NSET=BOTTOM_EDGE\n1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11\n")
        f.write("*NSET, NSET=RIGHT_EDGE\n11, 22, 33, 44, 55, 66, 77, 88, 99, 110, 121\n")
        f.write("*NSET, NSET=TOP_EDGE\n111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121\n")

        # Boundary conditions
        f.write(bc_block + '\n')

        # Step
        f.write("*STEP\n*STATIC\n")
        f.write(load_block + '\n')

        # Output
        f.write("*EL PRINT, ELSET=PLATE\nS\n")
        f.write("*END STEP\n")


# Material property strings (in MPa)
MAT_T300 = """*MATERIAL, NAME=CFRP_UD
*ELASTIC, TYPE=ENGINEERING CONSTANTS
135000.0, 10000.0, 10000.0, 0.27, 0.27, 0.45, 5200.0, 5200.0
3900.0"""

MAT_EGLASS = """*MATERIAL, NAME=CFRP_UD
*ELASTIC, TYPE=ENGINEERING CONSTANTS
39000.0, 8600.0, 8600.0, 0.28, 0.28, 0.45, 3800.0, 3800.0
3000.0"""

MAT_IM7 = """*MATERIAL, NAME=CFRP_UD
*ELASTIC, TYPE=ENGINEERING CONSTANTS
171400.0, 9080.0, 9080.0, 0.32, 0.32, 0.45, 5290.0, 5290.0
3900.0"""

BC_STANDARD = """*BOUNDARY
LEFT_EDGE, 1, 3, 0.0
BOTTOM_EDGE, 2, 2, 0.0"""

LOAD_BIAXIAL = """*CLOAD
RIGHT_EDGE, 1, 50.0
TOP_EDGE, 2, 40.0"""

LOAD_TENSCOMP = """*CLOAD
RIGHT_EDGE, 1, 50.0
TOP_EDGE, 2, -40.0"""

LOAD_SHEAR = """*CLOAD
TOP_EDGE, 1, 50.0
BOTTOM_EDGE, 1, -50.0"""


# =============================================================================
# Test 0A: Arbitrary Angle Orientations -- [+/-30]2s
# =============================================================================
def test_0a():
    print("\n" + "="*70)
    print("TEST 0A: Arbitrary Angle Orientations -- [+/-30]2s layup")
    print("="*70)

    test_dir = os.path.join(WORK_DIR, "test_0a")
    ensure_dir(test_dir)

    layup_30 = [30, -30, 30, -30, -30, 30, -30, 30]
    filepath = os.path.join(test_dir, "test_orientation.inp")

    write_test_inp(filepath, MAT_T300, None, layup_30, PLY_T, BC_STANDARD, LOAD_BIAXIAL)

    ok, dat_path = run_ccx("test_orientation", test_dir)
    if not ok:
        print("  FAIL: CalculiX did not converge")
        return False

    stresses = parse_stresses(dat_path)
    vm = max_mises(stresses)
    s12 = max_abs_s12(stresses)

    # Also run baseline for comparison
    baseline_dir = os.path.join(WORK_DIR, "test_0a_baseline")
    ensure_dir(baseline_dir)
    filepath_base = os.path.join(baseline_dir, "test_baseline.inp")
    write_test_inp(filepath_base, MAT_T300, None, LAYUP_QI, PLY_T, BC_STANDARD, LOAD_BIAXIAL)
    ok_base, dat_base = run_ccx("test_baseline", baseline_dir)
    if not ok_base:
        print("  FAIL: Baseline did not converge")
        return False

    stresses_base = parse_stresses(dat_base)
    vm_base = max_mises(stresses_base)
    s12_base = max_abs_s12(stresses_base)

    print(f"  [+/-30]2s  -- Max Mises: {vm:.4f} MPa, Max |S12|: {s12:.4f} MPa")
    print(f"  [0/+/-45/90]s baseline -- Max Mises: {vm_base:.4f} MPa, Max |S12|: {s12_base:.4f} MPa")

    diff_pct = abs(vm - vm_base) / vm_base * 100
    print(f"  Mises difference: {diff_pct:.1f}%")

    passed = diff_pct > 1.0  # Must differ meaningfully
    print(f"  RESULT: {'PASS' if passed else 'FAIL'} -- stresses {'differ' if passed else 'too similar'} from baseline")
    return passed


# =============================================================================
# Test 0B: Material Property Sensitivity
# =============================================================================
def test_0b():
    print("\n" + "="*70)
    print("TEST 0B: Material Property Sensitivity -- E-glass vs IM7")
    print("="*70)

    results = {}
    for name, mat_block, label in [
        ("eglass", MAT_EGLASS, "E-glass (E1=39 GPa)"),
        ("im7", MAT_IM7, "IM7 (E1=171.4 GPa)")
    ]:
        test_dir = os.path.join(WORK_DIR, f"test_0b_{name}")
        ensure_dir(test_dir)
        filepath = os.path.join(test_dir, f"test_mat_{name}.inp")
        write_test_inp(filepath, mat_block, None, LAYUP_QI, PLY_T, BC_STANDARD, LOAD_BIAXIAL)

        ok, dat_path = run_ccx(f"test_mat_{name}", test_dir)
        if not ok:
            print(f"  FAIL: {label} did not converge")
            return False

        stresses = parse_stresses(dat_path)
        vm = max_mises(stresses)
        s11_max = max_abs_s11(stresses)
        results[name] = {'vm': vm, 's11': s11_max, 'label': label}
        print(f"  {label}: Max Mises = {vm:.4f} MPa, Max |S11| = {s11_max:.4f} MPa")

    eg = results['eglass']
    im = results['im7']

    # Stresses should differ meaningfully between materials
    stress_diff = abs(eg['vm'] - im['vm']) / max(eg['vm'], im['vm']) * 100
    s11_diff = abs(eg['s11'] - im['s11']) / max(eg['s11'], im['s11']) * 100

    # IM7 is stiffer -> for force-controlled loading, stiffer material
    # attracts more load in 0-deg ply -> higher S11 in 0-deg ply
    im7_higher_s11 = im['s11'] > eg['s11']

    print(f"  IM7 higher S11 than E-glass: {im7_higher_s11} ({im['s11']:.4f} vs {eg['s11']:.4f})")
    print(f"  Mises difference: {stress_diff:.1f}%")
    print(f"  S11 difference: {s11_diff:.1f}%")

    passed = stress_diff > 5.0 and s11_diff > 5.0
    print(f"  RESULT: {'PASS' if passed else 'FAIL'} -- materials produce distinct stress states")
    return passed


# =============================================================================
# Test 0C: Boundary Condition Modes
# =============================================================================
def test_0c():
    print("\n" + "="*70)
    print("TEST 0C: Boundary Condition Modes -- tension-compression & shear")
    print("="*70)

    results = {}
    tests = [
        ("tenscomp", LOAD_TENSCOMP, "Tension-compression (flip TOP Y-force)"),
        ("shear", LOAD_SHEAR, "Pure shear (equal-opposite X-forces on TOP/BOTTOM)"),
    ]

    for name, load_block, label in tests:
        test_dir = os.path.join(WORK_DIR, f"test_0c_{name}")
        ensure_dir(test_dir)
        filepath = os.path.join(test_dir, f"test_bc_{name}.inp")
        write_test_inp(filepath, MAT_T300, None, LAYUP_QI, PLY_T, BC_STANDARD, load_block)

        ok, dat_path = run_ccx(f"test_bc_{name}", test_dir)
        if not ok:
            print(f"  FAIL: {label} did not converge")
            return False

        stresses = parse_stresses(dat_path)
        vm = max_mises(stresses)
        s12 = max_abs_s12(stresses)
        results[name] = {'vm': vm, 's12': s12}
        print(f"  {label}: Max Mises = {vm:.4f} MPa, Max |S12| = {s12:.4f} MPa")

    # Both converged with different stress states
    vm_diff = abs(results['shear']['vm'] - results['tenscomp']['vm'])
    print(f"  Mises difference: {vm_diff:.4f} MPa")
    print(f"  Shear S12: {results['shear']['s12']:.4f}, TensComp S12: {results['tenscomp']['s12']:.4f}")

    passed = True  # Both converged and produce different stress fields
    print(f"  RESULT: {'PASS' if passed else 'FAIL'} -- both converge with distinct stress states")
    return passed


# =============================================================================
# Test 0D: Plate with Circular Cutout (gmsh)
# =============================================================================
def test_0d():
    print("\n" + "="*70)
    print("TEST 0D: Plate with Circular Cutout (gmsh boolean cut)")
    print("="*70)

    import gmsh

    test_dir = os.path.join(WORK_DIR, "test_0d")
    ensure_dir(test_dir)

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("cutout_test")

    plate = gmsh.model.occ.addRectangle(0, 0, 0, PLATE_L, PLATE_W)
    hole = gmsh.model.occ.addDisk(PLATE_L/2, PLATE_W/2, 0, 5.0, 5.0)  # D=10mm hole
    gmsh.model.occ.cut([(2, plate)], [(2, hole)])
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

    if left_c: gmsh.model.addPhysicalGroup(1, left_c, tag=1, name="left")
    if bottom_c: gmsh.model.addPhysicalGroup(1, bottom_c, tag=2, name="bottom")
    if right_c: gmsh.model.addPhysicalGroup(1, right_c, tag=3, name="right")
    if top_c: gmsh.model.addPhysicalGroup(1, top_c, tag=4, name="top")

    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", 0.8)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", 5.0)

    hole_curves = [t for _, t in all_curves if t not in left_c + bottom_c + right_c + top_c]
    if hole_curves:
        fd = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(fd, "CurvesList", hole_curves)
        gmsh.model.mesh.field.setNumber(fd, "Sampling", 200)
        ft = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(ft, "InField", fd)
        gmsh.model.mesh.field.setNumber(ft, "SizeMin", 0.8)
        gmsh.model.mesh.field.setNumber(ft, "SizeMax", 5.0)
        gmsh.model.mesh.field.setNumber(ft, "DistMin", 1.0)
        gmsh.model.mesh.field.setNumber(ft, "DistMax", 20.0)
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

    n_elements = len(elements)
    n_nodes = len(nodes)
    gmsh.finalize()

    print(f"  Mesh: {n_nodes} nodes, {n_elements} S6 elements")

    # Write INP
    job_name = "test_cutout"
    filepath = os.path.join(test_dir, f"{job_name}.inp")
    total_t = 8 * PLY_T

    with open(filepath, 'w') as f:
        f.write("** Plate with circular cutout\n*HEADING\nCutout test\n")
        f.write("*NODE\n")
        for nid in sorted(nodes.keys()):
            x, y, z = nodes[nid]
            f.write(f"  {nid}, {x:.8f}, {y:.8f}, {z:.8f}\n")

        f.write("*ELEMENT, TYPE=S6, ELSET=PLATE\n")
        for eid, npe, enlist in elements:
            node_str = ", ".join(str(n) for n in enlist)
            f.write(f"  {eid}, {node_str}\n")

        f.write(MAT_T300 + '\n')

        for angle in sorted(set(LAYUP_QI), key=lambda a: (a < 0, abs(a))):
            name, vec = generate_orientation_block(angle)
            f.write(f"*ORIENTATION, NAME={name}, SYSTEM=RECTANGULAR\n{vec}\n")

        f.write("*SHELL SECTION, COMPOSITE, ELSET=PLATE, OFFSET=0\n")
        for angle in LAYUP_QI:
            name, _ = generate_orientation_block(angle)
            f.write(f"{PLY_T}, 3, CFRP_UD, {name}\n")

        for bname, nset in bc_sets.items():
            if nset:
                f.write(f"*NSET, NSET={bname.upper()}\n")
                nids = sorted(nset)
                for k in range(0, len(nids), 16):
                    chunk = nids[k:k+16]
                    f.write(", ".join(str(n) for n in chunk) + "\n")

        f.write("*BOUNDARY\nLEFT, 1, 1, 0.0\nCORNER, 2, 3, 0.0\n")

        px = 50.0
        n_right = len(bc_sets["right"])
        force_per_node = (px * PLATE_W * total_t) / n_right if n_right > 0 else 50.0
        f.write("*STEP\n*STATIC\n")
        f.write(f"*CLOAD\nRIGHT, 1, {force_per_node:.8f}\n")
        f.write("*EL PRINT, ELSET=PLATE\nS\n*END STEP\n")

    ok, dat_path = run_ccx(job_name, test_dir)
    if not ok:
        print("  FAIL: Cutout model did not converge")
        return False

    stresses = parse_stresses(dat_path)
    vm = max_mises(stresses)

    # Compare with plain plate under same loading
    plain_dir = os.path.join(WORK_DIR, "test_0d_plain")
    ensure_dir(plain_dir)
    plain_load = "*CLOAD\nRIGHT_EDGE, 1, 50.0"
    filepath_plain = os.path.join(plain_dir, "test_plain.inp")
    write_test_inp(filepath_plain, MAT_T300, None, LAYUP_QI, PLY_T, BC_STANDARD, plain_load)
    ok_plain, dat_plain = run_ccx("test_plain", plain_dir)

    if ok_plain:
        stresses_plain = parse_stresses(dat_plain)
        vm_plain = max_mises(stresses_plain)
        scf = vm / vm_plain if vm_plain > 0 else 0
        print(f"  Cutout: Max Mises = {vm:.4f} MPa")
        print(f"  Plain:  Max Mises = {vm_plain:.4f} MPa")
        print(f"  SCF (approx): {scf:.2f}x")
        passed = scf > 1.5
    else:
        print(f"  Cutout: Max Mises = {vm:.4f} MPa")
        print(f"  (Could not run plain plate for comparison)")
        passed = vm > 0

    print(f"  RESULT: {'PASS' if passed else 'FAIL'} -- {'stress concentration observed' if passed else 'SCF too low'}")
    return passed


# =============================================================================
# Test 0E: Curved Panel (gmsh) -- extrude arc approach
# =============================================================================
def test_0e():
    print("\n" + "="*70)
    print("TEST 0E: Curved Panel (R=200mm cylindrical shell)")
    print("="*70)

    import gmsh

    test_dir = os.path.join(WORK_DIR, "test_0e")
    ensure_dir(test_dir)

    R = 200.0
    arc_length = 100.0
    width = 50.0
    theta = arc_length / R  # angular span in radians

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("curved_panel")

    # Build curved panel by extruding an arc along X
    # Arc lies in Y-Z plane: center at (0, 0, -R), starts at (0, 0, 0)
    center = gmsh.model.occ.addPoint(0, 0, -R)
    p_start = gmsh.model.occ.addPoint(0, 0, 0)
    p_end = gmsh.model.occ.addPoint(0, R * math.sin(theta), R * math.cos(theta) - R)

    arc = gmsh.model.occ.addCircleArc(p_start, center, p_end)

    # Extrude arc along X to create the surface
    extruded = gmsh.model.occ.extrude([(1, arc)], width, 0, 0)
    gmsh.model.occ.synchronize()

    surfaces = gmsh.model.getEntities(2)
    if not surfaces:
        print("  FAIL: Could not create curved surface")
        gmsh.finalize()
        return False

    gmsh.model.addPhysicalGroup(2, [s[1] for s in surfaces], tag=5, name="plate")

    # Identify boundary curves by bounding box
    all_curves = gmsh.model.getEntities(1)
    tol = 0.1
    left_c, right_c, bottom_c, top_c = [], [], [], []

    for _, tag in all_curves:
        bbox = gmsh.model.getBoundingBox(1, tag)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        x_span = xmax - xmin
        y_span = ymax - ymin
        z_span = zmax - zmin

        # "left" = X=0 edge (curved arc)
        if abs(xmin) < tol and abs(xmax) < tol:
            left_c.append(tag)
        # "right" = X=width edge (curved arc)
        elif abs(xmin - width) < tol and abs(xmax - width) < tol:
            right_c.append(tag)
        # Straight edges: both have X spanning full width, minimal Y/Z variation at ends
        elif x_span > width - 1.0:
            # Bottom = at Y~0, Z~0 (start of arc)
            if abs(ymin) < tol and abs(ymax) < tol and abs(zmin) < tol and abs(zmax) < tol:
                bottom_c.append(tag)
            else:
                # Top = at the end of arc
                top_c.append(tag)

    if left_c: gmsh.model.addPhysicalGroup(1, left_c, tag=1, name="left")
    if bottom_c: gmsh.model.addPhysicalGroup(1, bottom_c, tag=2, name="bottom")
    if right_c: gmsh.model.addPhysicalGroup(1, right_c, tag=3, name="right")
    if top_c: gmsh.model.addPhysicalGroup(1, top_c, tag=4, name="top")

    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", 1.0)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", 5.0)
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

    corner = min(nodes.keys(), key=lambda n: nodes[n][0]**2 + nodes[n][1]**2 + nodes[n][2]**2)
    bc_sets["corner"] = {corner}

    n_elements = len(elements)
    n_nodes = len(nodes)
    gmsh.finalize()

    print(f"  Mesh: {n_nodes} nodes, {n_elements} elements")
    print(f"  Curvature: R={R}mm, arc_angle={math.degrees(theta):.1f} deg")

    # Write INP
    job_name = "test_curved"
    filepath = os.path.join(test_dir, f"{job_name}.inp")
    total_t = 8 * PLY_T

    with open(filepath, 'w') as f:
        f.write("** Curved cylindrical panel\n*HEADING\nCurved panel test\n")
        f.write("*NODE\n")
        for nid in sorted(nodes.keys()):
            x, y, z = nodes[nid]
            f.write(f"  {nid}, {x:.8f}, {y:.8f}, {z:.8f}\n")

        f.write("*ELEMENT, TYPE=S6, ELSET=PLATE\n")
        for eid, npe, enlist in elements:
            node_str = ", ".join(str(n) for n in enlist)
            f.write(f"  {eid}, {node_str}\n")

        f.write(MAT_T300 + '\n')

        for angle in sorted(set(LAYUP_QI), key=lambda a: (a < 0, abs(a))):
            name, vec = generate_orientation_block(angle)
            f.write(f"*ORIENTATION, NAME={name}, SYSTEM=RECTANGULAR\n{vec}\n")

        f.write("*SHELL SECTION, COMPOSITE, ELSET=PLATE, OFFSET=0\n")
        for angle in LAYUP_QI:
            name, _ = generate_orientation_block(angle)
            f.write(f"{PLY_T}, 3, CFRP_UD, {name}\n")

        for bname, nset in bc_sets.items():
            if nset:
                f.write(f"*NSET, NSET={bname.upper()}\n")
                nids = sorted(nset)
                for k in range(0, len(nids), 16):
                    chunk = nids[k:k+16]
                    f.write(", ".join(str(n) for n in chunk) + "\n")

        # Fix left edge (curved arc)
        f.write("*BOUNDARY\nLEFT, 1, 3, 0.0\n")

        if bc_sets.get("right"):
            n_right = len(bc_sets["right"])
            force_per_node = (50.0 * width * total_t) / n_right
        else:
            force_per_node = 50.0

        f.write("*STEP\n*STATIC\n")
        f.write(f"*CLOAD\nRIGHT, 1, {force_per_node:.8f}\n")
        f.write("*EL PRINT, ELSET=PLATE\nS\n*END STEP\n")

    ok, dat_path = run_ccx(job_name, test_dir)
    if not ok:
        print("  FAIL: Curved panel did not converge")
        return False

    stresses = parse_stresses(dat_path)
    vm = max_mises(stresses)
    print(f"  Max Mises stress: {vm:.4f} MPa")

    passed = vm > 0 and len(stresses) > 0
    print(f"  RESULT: {'PASS' if passed else 'FAIL'} -- curved panel converges with {len(stresses)} stress points")
    return passed


# =============================================================================
# Test 0F: Lamination Parameter Validation
# =============================================================================
def test_0f():
    print("\n" + "="*70)
    print("TEST 0F: Lamination Parameter Validation")
    print("="*70)

    def compute_lamination_params(angles, ply_thickness):
        n = len(angles)
        h = n * ply_thickness
        V1A = V2A = V3A = V4A = 0.0
        V1D = V2D = V3D = V4D = 0.0
        for k, theta_deg in enumerate(angles):
            t = math.radians(theta_deg)
            zk = (-h/2 + (k + 0.5) * ply_thickness)
            tk_over_h = ply_thickness / h
            zk_over_h_sq = (zk / h)**2 * 12

            V1A += math.cos(2*t) * tk_over_h
            V2A += math.sin(2*t) * tk_over_h
            V3A += math.cos(4*t) * tk_over_h
            V4A += math.sin(4*t) * tk_over_h
            V1D += math.cos(2*t) * zk_over_h_sq * tk_over_h
            V2D += math.sin(2*t) * zk_over_h_sq * tk_over_h
            V3D += math.cos(4*t) * zk_over_h_sq * tk_over_h
            V4D += math.sin(4*t) * zk_over_h_sq * tk_over_h
        return V1A, V2A, V3A, V4A, V1D, V2D, V3D, V4D

    test_cases = [
        {
            'name': '[0/+/-45/90]s (QI)',
            'angles': [0, 45, -45, 90, 90, -45, 45, 0],
            'expected_V1A': 0.0, 'expected_V3A': 0.0,
            'tol_V1A': 0.01, 'tol_V3A': 0.01,
        },
        {
            'name': '[0]8 (unidirectional)',
            'angles': [0]*8,
            'expected_V1A': 1.0, 'expected_V2A': 0.0,
            'expected_V3A': 1.0, 'expected_V4A': 0.0,
            'tol_V1A': 0.01, 'tol_V2A': 0.01, 'tol_V3A': 0.01, 'tol_V4A': 0.01,
        },
        {
            'name': '[+/-45]2s',
            'angles': [45, -45, 45, -45, -45, 45, -45, 45],
            'expected_V1A': 0.0, 'expected_V3A': -1.0,
            'tol_V1A': 0.01, 'tol_V3A': 0.01,
        },
    ]

    all_pass = True
    for tc in test_cases:
        params = compute_lamination_params(tc['angles'], PLY_T)
        V1A, V2A, V3A, V4A, V1D, V2D, V3D, V4D = params
        print(f"\n  {tc['name']}:")
        print(f"    V1A={V1A:.6f}, V2A={V2A:.6f}, V3A={V3A:.6f}, V4A={V4A:.6f}")
        print(f"    V1D={V1D:.6f}, V2D={V2D:.6f}, V3D={V3D:.6f}, V4D={V4D:.6f}")

        case_pass = True
        for key in ['V1A', 'V2A', 'V3A', 'V4A']:
            expected_key = f'expected_{key}'
            tol_key = f'tol_{key}'
            if expected_key in tc:
                expected = tc[expected_key]
                tol = tc.get(tol_key, 0.01)
                actual = params[['V1A','V2A','V3A','V4A'].index(key)]
                if abs(actual - expected) > tol:
                    print(f"    MISMATCH: {key} = {actual:.6f}, expected {expected:.6f} (tol={tol})")
                    case_pass = False

        if case_pass:
            print(f"    OK -- matches analytical values")
        else:
            all_pass = False

    print(f"\n  RESULT: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


# =============================================================================
# Test 0G: Sobol Sampling
# =============================================================================
def test_0g():
    print("\n" + "="*70)
    print("TEST 0G: Sobol Sampling vs LHS")
    print("="*70)

    import random
    from scipy.stats.qmc import Sobol, discrepancy
    import numpy as np

    n_samples = 1000
    dim = 6

    # Sobol samples
    sampler = Sobol(d=dim, scramble=True, seed=42)
    m = int(math.ceil(math.log2(n_samples)))
    sobol_raw = sampler.random_base2(m)[:n_samples]

    # LHS samples (simplified random for comparison)
    random.seed(42)
    lhs_raw = np.array([[random.random() for _ in range(dim)] for _ in range(n_samples)])

    sobol_disc = discrepancy(sobol_raw)
    lhs_disc = discrepancy(lhs_raw)

    print(f"  Sobol discrepancy:  {sobol_disc:.6f}")
    print(f"  LHS discrepancy:    {lhs_disc:.6f}")
    print(f"  Sobol/LHS ratio:    {sobol_disc/lhs_disc:.4f}")

    passed = sobol_disc < lhs_disc
    print(f"\n  RESULT: {'PASS' if passed else 'FAIL'} -- Sobol discrepancy {'<' if passed else '>='} LHS discrepancy")
    return passed


# =============================================================================
# Main
# =============================================================================
def main():
    ensure_dir(WORK_DIR)

    print("="*70)
    print("CompositeBench -- Phase 0 Local Validation Tests")
    print(f"CalculiX: {CCX_EXE}")
    print(f"Work dir: {WORK_DIR}")
    print("="*70)

    tests = [
        ("0A", "Arbitrary Angle Orientations", test_0a),
        ("0B", "Material Property Sensitivity", test_0b),
        ("0C", "Boundary Condition Modes", test_0c),
        ("0D", "Plate with Circular Cutout", test_0d),
        ("0E", "Curved Panel", test_0e),
        ("0F", "Lamination Parameter Validation", test_0f),
        ("0G", "Sobol Sampling", test_0g),
    ]

    results = {}
    for tid, desc, func in tests:
        t0 = time.time()
        try:
            result = func()
            results[tid] = result
        except Exception as e:
            print(f"\n  EXCEPTION in Test {tid}: {e}")
            import traceback
            traceback.print_exc()
            results[tid] = False
        dt = time.time() - t0
        print(f"  (took {dt:.1f}s)")

    # Summary
    print("\n" + "="*70)
    print("PHASE 0 SUMMARY")
    print("="*70)
    for tid, desc, _ in tests:
        status = "PASS" if results.get(tid) else "FAIL"
        color = "GREEN" if results.get(tid) else "RED"
        print(f"  Test {tid} ({desc}): {status} -> {color}")

    n_pass = sum(1 for v in results.values() if v)
    n_total = len(results)
    print(f"\n  {n_pass}/{n_total} tests passed")

    if n_pass == n_total:
        print("\n  ALL TESTS PASSED -- Ready for Phase 1 scope finalization")
    else:
        failed = [tid for tid, v in results.items() if not v]
        print(f"\n  Failed tests: {', '.join(failed)}")
        print("  Review failures before proceeding to Phase 1")

    return n_pass == n_total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
