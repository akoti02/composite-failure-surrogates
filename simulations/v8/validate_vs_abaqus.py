"""
Validation: CalculiX vs Abaqus for sim_id=1 from V7 dataset.
Creates a composite plate with a crack slit, runs CalculiX, compares stresses.
"""
import numpy as np
import subprocess
import os
import re
import math

# =============================================================================
# ABAQUS REFERENCE VALUES (sim_id=1)
# =============================================================================
ABAQUS_REF = {
    'max_mises': 836.40,
    'max_s11': 858.82,
    'min_s11': -63.86,
    'max_s22': 48.09,
    'tsai_wu_index': 1.198,
    'max_hashin_ft': 0.328,
    'max_hashin_mt': 1.515,
}

# =============================================================================
# SIMULATION PARAMETERS (from sim_id=1)
# =============================================================================
PLATE_L = 100.0   # mm
PLATE_W = 50.0    # mm
CRACK_X = 64.148  # center of crack
CRACK_Y = 21.898
CRACK_HALF_LEN = 12.362  # mm
CRACK_ANGLE = 112.096    # degrees from x-axis
PLY_THICKNESS = 0.1247   # mm per ply
PRESSURE_X = 59.188      # MPa
PRESSURE_Y = 46.403      # MPa

# CFRP material properties (T300/914C typical)
E1 = 135000.0   # MPa
E2 = 10000.0
E3 = 10000.0
NU12 = 0.27
NU13 = 0.27
NU23 = 0.45
G12 = 5200.0
G13 = 5200.0
G23 = 3900.0

# Strength values for Hashin/Tsai-Wu (typical T300/914C)
XT = 1500.0   # Fiber tensile strength (MPa)
XC = 1200.0   # Fiber compressive strength
YT = 50.0     # Matrix tensile strength
YC = 250.0    # Matrix compressive strength
SL = 70.0     # Longitudinal shear strength
ST = 35.0     # Transverse shear strength (YC / (2*tan(53deg)))

TOTAL_THICKNESS = 8 * PLY_THICKNESS
LAYUP = [0, 45, -45, 90, 90, -45, 45, 0]

CCX_EXE = r"C:\CalculiX\calculix_2.23_4win\ccx_static.exe"
WORK_DIR = r"C:\CalculiX\test_composite"
JOB_NAME = "validate_sim1"


def generate_mesh_with_crack():
    """Use Gmsh OCC Boolean to create a plate with a TRUE crack discontinuity."""
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("plate_crack")

    # Crack endpoints
    angle_rad = math.radians(CRACK_ANGLE)
    dx = CRACK_HALF_LEN * math.cos(angle_rad)
    dy = CRACK_HALF_LEN * math.sin(angle_rad)
    crack_x1 = CRACK_X - dx
    crack_y1 = CRACK_Y - dy
    crack_x2 = CRACK_X + dx
    crack_y2 = CRACK_Y + dy

    # Use OCC kernel: cut a thin slot out of the plate to create a real crack
    plate = gmsh.model.occ.addRectangle(0, 0, 0, PLATE_L, PLATE_W)

    # Create crack as a thin rectangle (slot) along the crack direction
    CRACK_WIDTH = 0.2  # thin slot (0.2mm) — similar to Abaqus crack width
    # Perpendicular direction to crack
    perp_rad = angle_rad + math.pi / 2
    hw = CRACK_WIDTH / 2
    nx = math.cos(perp_rad) * hw
    ny = math.sin(perp_rad) * hw

    # Four corners of the thin slot
    slot_pts = [
        gmsh.model.occ.addPoint(crack_x1 - nx, crack_y1 - ny, 0),
        gmsh.model.occ.addPoint(crack_x2 - nx, crack_y2 - ny, 0),
        gmsh.model.occ.addPoint(crack_x2 + nx, crack_y2 + ny, 0),
        gmsh.model.occ.addPoint(crack_x1 + nx, crack_y1 + ny, 0),
    ]
    slot_lines = [
        gmsh.model.occ.addLine(slot_pts[0], slot_pts[1]),
        gmsh.model.occ.addLine(slot_pts[1], slot_pts[2]),
        gmsh.model.occ.addLine(slot_pts[2], slot_pts[3]),
        gmsh.model.occ.addLine(slot_pts[3], slot_pts[0]),
    ]
    slot_loop = gmsh.model.occ.addCurveLoop(slot_lines)
    slot_surf = gmsh.model.occ.addPlaneSurface([slot_loop])

    # Boolean cut: plate minus slot
    result = gmsh.model.occ.cut([(2, plate)], [(2, slot_surf)])
    gmsh.model.occ.synchronize()

    # Get all resulting surfaces (should be 2 pieces split by crack)
    surfaces = gmsh.model.getEntities(2)
    print(f"  Surfaces after fragment: {len(surfaces)}")

    # Physical groups: all surfaces = plate
    surf_tags = [s[1] for s in surfaces]
    gmsh.model.addPhysicalGroup(2, surf_tags, tag=5, name="plate")

    # Find boundary curves for BCs
    all_curves = gmsh.model.getEntities(1)
    left_curves = []
    bottom_curves = []
    right_curves = []
    top_curves = []

    tol = 0.1
    for dim, tag in all_curves:
        bbox = gmsh.model.getBoundingBox(dim, tag)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        # Left edge: x ~ 0
        if abs(xmin) < tol and abs(xmax) < tol:
            left_curves.append(tag)
        # Right edge: x ~ PLATE_L
        elif abs(xmin - PLATE_L) < tol and abs(xmax - PLATE_L) < tol:
            right_curves.append(tag)
        # Bottom edge: y ~ 0
        elif abs(ymin) < tol and abs(ymax) < tol and xmax - xmin > 1.0:
            bottom_curves.append(tag)
        # Top edge: y ~ PLATE_W
        elif abs(ymin - PLATE_W) < tol and abs(ymax - PLATE_W) < tol and xmax - xmin > 1.0:
            top_curves.append(tag)

    if left_curves: gmsh.model.addPhysicalGroup(1, left_curves, tag=1, name="left")
    if bottom_curves: gmsh.model.addPhysicalGroup(1, bottom_curves, tag=2, name="bottom")
    if right_curves: gmsh.model.addPhysicalGroup(1, right_curves, tag=3, name="right")
    if top_curves: gmsh.model.addPhysicalGroup(1, top_curves, tag=4, name="top")

    print(f"  BC curves: L={len(left_curves)}, B={len(bottom_curves)}, R={len(right_curves)}, T={len(top_curves)}")

    # Mesh settings — use triangles (no recombination) to handle thin slot edges
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)  # triangles (S6 in CalculiX)
    gmsh.option.setNumber("Mesh.Algorithm", 6)     # Frontal-Delaunay
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", 0.15)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", 4.0)

    # Refine around crack
    # Find the crack curves after fragmentation
    crack_curves = []
    for dim, tag in all_curves:
        bbox = gmsh.model.getBoundingBox(dim, tag)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        # Check if curve is near the original crack line
        cx_mid = (crack_x1 + crack_x2) / 2
        cy_mid = (crack_y1 + crack_y2) / 2
        mid_x = (xmin + xmax) / 2
        mid_y = (ymin + ymax) / 2
        dist = math.sqrt((mid_x - cx_mid)**2 + (mid_y - cy_mid)**2)
        length = math.sqrt((xmax-xmin)**2 + (ymax-ymin)**2)
        if dist < CRACK_HALF_LEN * 1.5 and length > 1.0 and length < CRACK_HALF_LEN * 3:
            # Check this isn't a plate edge
            is_edge = (abs(xmin) < tol and abs(xmax) < tol) or \
                      (abs(xmin-PLATE_L) < tol and abs(xmax-PLATE_L) < tol) or \
                      (abs(ymin) < tol and abs(ymax) < tol) or \
                      (abs(ymin-PLATE_W) < tol and abs(ymax-PLATE_W) < tol)
            if not is_edge:
                crack_curves.append(tag)

    if crack_curves:
        field_dist = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(field_dist, "CurvesList", crack_curves)
        gmsh.model.mesh.field.setNumber(field_dist, "Sampling", 200)

        field_thresh = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(field_thresh, "InField", field_dist)
        gmsh.model.mesh.field.setNumber(field_thresh, "SizeMin", 0.3)
        gmsh.model.mesh.field.setNumber(field_thresh, "SizeMax", 4.0)
        gmsh.model.mesh.field.setNumber(field_thresh, "DistMin", 1.0)
        gmsh.model.mesh.field.setNumber(field_thresh, "DistMax", 25.0)

        gmsh.model.mesh.field.setAsBackgroundMesh(field_thresh)
        print(f"  Crack curves for refinement: {len(crack_curves)}")

    gmsh.model.mesh.generate(2)

    # Get mesh data
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    nodes = {}
    for i, tag in enumerate(node_tags):
        nodes[int(tag)] = (node_coords[3*i], node_coords[3*i+1], node_coords[3*i+2])

    # Get elements (surface elements only)
    elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(2)

    elements = []
    for etype, etags, enodes in zip(elem_types, elem_tags, elem_node_tags):
        ename = gmsh.model.mesh.getElementProperties(etype)[0]
        npe = gmsh.model.mesh.getElementProperties(etype)[3]
        for i, etag in enumerate(etags):
            enlist = [int(enodes[i*npe + j]) for j in range(npe)]
            elements.append((int(etag), ename, enlist))

    # Get boundary node sets from physical groups
    left_nodes = set()
    bottom_nodes = set()
    right_nodes = set()
    top_nodes = set()

    for phys_tag, nset_ref in [(1, left_nodes), (2, bottom_nodes), (3, right_nodes), (4, top_nodes)]:
        try:
            ents = gmsh.model.getEntitiesForPhysicalGroup(1, phys_tag)
            for ent in ents:
                ntags, _, _ = gmsh.model.mesh.getNodes(1, ent, includeBoundary=True)
                nset_ref.update(int(t) for t in ntags)
        except Exception:
            pass

    crack_node_set = set()  # not needed for this approach — crack is topological

    n_nodes = len(nodes)
    n_elems = len(elements)

    gmsh.finalize()

    print(f"  Mesh: {n_nodes} nodes, {n_elems} elements")
    print(f"  Boundary nodes: L={len(left_nodes)}, B={len(bottom_nodes)}, R={len(right_nodes)}, T={len(top_nodes)}")

    etypes_found = set(e[1] for e in elements)
    print(f"  Element types: {etypes_found}")

    return nodes, elements, left_nodes, bottom_nodes, right_nodes, top_nodes, crack_node_set


def write_inp(nodes, elements, left_nodes, bottom_nodes, right_nodes, top_nodes, crack_node_set):
    """Write CalculiX .inp file with composite layup."""

    # For simplicity with mixed element types, we'll handle both quad8 and tri6
    # CalculiX: S8R (8-node quad shell), S6 (6-node tri shell)

    filepath = os.path.join(WORK_DIR, f"{JOB_NAME}.inp")

    with open(filepath, 'w') as f:
        f.write("** Validation: CalculiX vs Abaqus sim_id=1\n")
        f.write("*HEADING\nComposite plate with crack - validation run\n**\n")

        # Nodes
        f.write("*NODE\n")
        for nid in sorted(nodes.keys()):
            x, y, z = nodes[nid]
            f.write(f"{nid}, {x:.6f}, {y:.6f}, {z:.6f}\n")

        # Separate elements by type
        quad8_elems = [(eid, ename, enodes) for eid, ename, enodes in elements if len(enodes) == 8]
        tri6_elems = [(eid, ename, enodes) for eid, ename, enodes in elements if len(enodes) == 6]

        all_elem_ids = []

        if quad8_elems:
            f.write(f"*ELEMENT, TYPE=S8R, ELSET=PLATE_Q\n")
            for eid, _, enodes in quad8_elems:
                f.write(f"{eid}, {', '.join(str(n) for n in enodes)}\n")
                all_elem_ids.append(eid)

        if tri6_elems:
            f.write(f"*ELEMENT, TYPE=S6, ELSET=PLATE_T\n")
            for eid, _, enodes in tri6_elems:
                f.write(f"{eid}, {', '.join(str(n) for n in enodes)}\n")
                all_elem_ids.append(eid)

        # Combined element set
        f.write("*ELSET, ELSET=PLATE\n")
        for i, eid in enumerate(all_elem_ids):
            if i > 0 and i % 10 == 0:
                f.write("\n")
            f.write(f"{eid}")
            if i < len(all_elem_ids) - 1:
                f.write(", ")
        f.write("\n")

        # Material
        f.write("**\n*MATERIAL, NAME=CFRP_UD\n")
        f.write("*ELASTIC, TYPE=ENGINEERING CONSTANTS\n")
        f.write(f"{E1}, {E2}, {E3}, {NU12}, {NU13}, {NU23}, {G12}, {G13}\n")
        f.write(f"{G23}\n")

        # Orientations
        for angle in sorted(set(LAYUP)):
            rad = math.radians(angle)
            c, s = math.cos(rad), math.sin(rad)
            name = f"ORI_{angle}".replace("-", "M")
            f.write(f"**\n*ORIENTATION, NAME={name}, SYSTEM=RECTANGULAR\n")
            f.write(f"{c:.7f}, {s:.7f}, 0.0, {-s:.7f}, {c:.7f}, 0.0\n")

        # Composite shell section for each element set
        for elset_name in (['PLATE_Q'] if quad8_elems else []) + (['PLATE_T'] if tri6_elems else []):
            f.write(f"**\n*SHELL SECTION, COMPOSITE, ELSET={elset_name}, OFFSET=0\n")
            for angle in LAYUP:
                ori_name = f"ORI_{angle}".replace("-", "M")
                f.write(f"{PLY_THICKNESS}, 3, CFRP_UD, {ori_name}\n")

        # Node sets for BCs
        def write_nset(name, nset):
            f.write(f"*NSET, NSET={name}\n")
            nlist = sorted(nset)
            for i, nid in enumerate(nlist):
                if i > 0 and i % 10 == 0:
                    f.write("\n")
                f.write(f"{nid}")
                if i < len(nlist) - 1:
                    f.write(", ")
            f.write("\n")

        write_nset("LEFT", left_nodes)
        write_nset("BOTTOM", bottom_nodes)
        write_nset("RIGHT", right_nodes)
        write_nset("TOP", top_nodes)

        # BCs: fix left edge (all DOFs), pin bottom in Y
        f.write("**\n*BOUNDARY\n")
        f.write("LEFT, 1, 3, 0.0\n")
        f.write("BOTTOM, 2, 2, 0.0\n")

        # Step: apply edge tractions as distributed loads
        # For shell elements, pressure_x on right edge and pressure_y on top edge
        # We'll apply as concentrated forces (force = pressure * area_tributary)
        # Tributary area per edge node: pressure * thickness * edge_length / n_edge_nodes

        f.write("**\n*STEP\n*STATIC\n**\n")

        # Force per node on right edge: F = pressure * total_thickness * plate_height / n_nodes_right
        # This is approximate but standard for validation
        f_right = PRESSURE_X * TOTAL_THICKNESS * PLATE_W / len(right_nodes)
        f_top = PRESSURE_Y * TOTAL_THICKNESS * PLATE_L / len(top_nodes)

        f.write("*CLOAD\n")
        for nid in sorted(right_nodes):
            f.write(f"{nid}, 1, {f_right:.6f}\n")
        for nid in sorted(top_nodes):
            f.write(f"{nid}, 2, {f_top:.6f}\n")

        # Output
        f.write("**\n*EL PRINT, ELSET=PLATE\nS\n")
        f.write("*NODE PRINT, NSET=RIGHT\nU\n")
        f.write("*NODE FILE\nU\n")
        f.write("*EL FILE\nS\n")
        f.write("*END STEP\n")

    print(f"  Written: {filepath}")
    return filepath


def parse_dat_stresses(dat_path):
    """Parse per-ply stresses from CalculiX .dat file."""
    stresses = []  # list of (elem, intpt, sxx, syy, szz, sxy, sxz, syz, ori_name)

    with open(dat_path, 'r') as f:
        in_stress_block = False
        for line in f:
            if 'stresses (elem' in line:
                in_stress_block = True
                continue
            if in_stress_block:
                stripped = line.strip()
                if not stripped:
                    continue  # skip blank lines within block
                # End of block: lines starting with non-numeric content (headers, etc)
                parts = stripped.split()
                if len(parts) >= 8:
                    try:
                        elem = int(parts[0])
                        intpt = int(parts[1])
                        sxx = float(parts[2])
                        syy = float(parts[3])
                        szz = float(parts[4])
                        sxy = float(parts[5])
                        sxz = float(parts[6])
                        syz = float(parts[7])
                        ori = parts[8] if len(parts) > 8 else ""
                        stresses.append((elem, intpt, sxx, syy, szz, sxy, sxz, syz, ori))
                    except (ValueError, IndexError):
                        in_stress_block = False
                        continue
                else:
                    # Check if this is a new section header
                    if any(kw in stripped.lower() for kw in ['displacements', 'forces', 'step', 'increment']):
                        in_stress_block = False

    return stresses


def compute_von_mises(sxx, syy, szz, sxy, sxz, syz):
    """Compute von Mises stress from 3D stress tensor."""
    return math.sqrt(0.5 * ((sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2
                             + 6 * (sxy**2 + sxz**2 + syz**2)))


def compute_hashin(s11, s22, s12):
    """Compute Hashin damage indices for a single ply."""
    # Fiber tension
    if s11 >= 0:
        Fft = (s11 / XT)**2 + (s12 / SL)**2
    else:
        Fft = 0.0

    # Fiber compression
    if s11 < 0:
        Ffc = (s11 / XC)**2
    else:
        Ffc = 0.0

    # Matrix tension
    if s22 >= 0:
        Fmt = (s22 / YT)**2 + (s12 / SL)**2
    else:
        Fmt = 0.0

    # Matrix compression
    if s22 < 0:
        Fmc = (s22 / (2 * ST))**2 + ((YC / (2 * ST))**2 - 1) * (s22 / YC) + (s12 / SL)**2
    else:
        Fmc = 0.0

    return Fft, Ffc, Fmt, Fmc


def compute_tsai_wu(s11, s22, s12):
    """Compute Tsai-Wu failure index."""
    F1 = 1.0/XT - 1.0/XC
    F2 = 1.0/YT - 1.0/YC
    F11 = 1.0 / (XT * XC)
    F22 = 1.0 / (YT * YC)
    F66 = 1.0 / SL**2
    F12 = -0.5 / math.sqrt(F11 * F22)

    tw = (F1*s11 + F2*s22 + F11*s11**2 + F22*s22**2 + F66*s12**2 + 2*F12*s11*s22)
    return tw


def main():
    print("=" * 60)
    print("CALCULIX vs ABAQUS VALIDATION (sim_id=1)")
    print("=" * 60)

    # Step 1: Generate mesh
    print("\n1. Generating mesh with Gmsh...")
    nodes, elements, left, bottom, right, top, crack_nodes = generate_mesh_with_crack()

    # Step 2: Write .inp
    print("\n2. Writing CalculiX input file...")
    inp_path = write_inp(nodes, elements, left, bottom, right, top, crack_nodes)

    # Step 3: Run CalculiX
    print("\n3. Running CalculiX...")
    os.chdir(WORK_DIR)
    result = subprocess.run(
        [CCX_EXE, JOB_NAME],
        capture_output=True, text=True, timeout=120
    )

    if "Job finished" not in result.stdout and "Job finished" not in result.stderr:
        print("  ERROR: CalculiX did not finish successfully!")
        print(result.stdout[-500:] if result.stdout else "")
        print(result.stderr[-500:] if result.stderr else "")
        return

    print("  CalculiX completed successfully.")

    # Step 4: Parse stresses
    print("\n4. Parsing stress output...")
    dat_path = os.path.join(WORK_DIR, f"{JOB_NAME}.dat")
    stresses = parse_dat_stresses(dat_path)
    print(f"  Parsed {len(stresses)} stress integration points")

    if not stresses:
        print("  ERROR: No stresses found in .dat file!")
        return

    # Step 5: Compute max von Mises, Hashin, Tsai-Wu
    print("\n5. Computing failure indices...")

    max_mises = 0
    max_s11 = -1e30
    min_s11 = 1e30
    max_s22 = -1e30
    min_s22 = 1e30
    max_tw = 0
    max_hft = 0
    max_hfc = 0
    max_hmt = 0
    max_hmc = 0

    for elem, intpt, sxx, syy, szz, sxy, sxz, syz, ori in stresses:
        vm = compute_von_mises(sxx, syy, szz, sxy, sxz, syz)
        if vm > max_mises:
            max_mises = vm

        # sxx = S11 in ply coords, syy = S22, sxy = S12 (for shell in ply orientation)
        if sxx > max_s11: max_s11 = sxx
        if sxx < min_s11: min_s11 = sxx
        if syy > max_s22: max_s22 = syy
        if syy < min_s22: min_s22 = syy

        tw = compute_tsai_wu(sxx, syy, sxy)
        if tw > max_tw: max_tw = tw

        hft, hfc, hmt, hmc = compute_hashin(sxx, syy, sxy)
        if hft > max_hft: max_hft = hft
        if hfc > max_hfc: max_hfc = hfc
        if hmt > max_hmt: max_hmt = hmt
        if hmc > max_hmc: max_hmc = hmc

    # Step 6: Compare
    print("\n" + "=" * 60)
    print("COMPARISON: CalculiX vs Abaqus")
    print("=" * 60)
    print(f"{'Metric':<20s} {'Abaqus':>12s} {'CalculiX':>12s} {'Ratio':>8s}")
    print("-" * 55)

    comparisons = [
        ('max_mises', ABAQUS_REF['max_mises'], max_mises),
        ('max_s11', ABAQUS_REF['max_s11'], max_s11),
        ('min_s11', ABAQUS_REF['min_s11'], min_s11),
        ('max_s22', ABAQUS_REF['max_s22'], max_s22),
        ('tsai_wu_index', ABAQUS_REF['tsai_wu_index'], max_tw),
        ('max_hashin_ft', ABAQUS_REF['max_hashin_ft'], max_hft),
        ('max_hashin_mt', ABAQUS_REF['max_hashin_mt'], max_hmt),
    ]

    for name, abq, ccx in comparisons:
        if abs(abq) > 1e-6:
            ratio = ccx / abq
            print(f"{name:<20s} {abq:>12.3f} {ccx:>12.3f} {ratio:>7.2f}x")
        else:
            print(f"{name:<20s} {abq:>12.3f} {ccx:>12.3f}     N/A")

    print("\nVERDICT: ", end="")
    mises_ratio = max_mises / ABAQUS_REF['max_mises'] if ABAQUS_REF['max_mises'] > 0 else 999
    if 0.5 < mises_ratio < 2.0:
        print("PASS — Stresses are in the same order of magnitude.")
        print("  CalculiX data is viable for ML training.")
    else:
        print(f"WARNING — Mises ratio {mises_ratio:.2f}x is outside [0.5, 2.0].")
        print("  Consider adding 'solver_source' feature or investigating differences.")


if __name__ == "__main__":
    main()
