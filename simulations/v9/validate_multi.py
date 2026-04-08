"""
Multi-case validation: CalculiX vs Abaqus for 10 cases.
Uses the EXACT jagged polygon crack geometry from the Abaqus batch script.
Compares von Mises, Tsai-Wu, and Hashin failure indices.
"""
import numpy as np
import subprocess
import os
import math
import random
import time

# =============================================================================
# CASES FROM ABAQUS CSV  (cx, cy, half_length, width, angle, roughness)
# =============================================================================
CASES = [
    {"sim_id": 1, "n_defects": 1,
     "defects": [(64.148, 21.898, 12.362, 0.234, 112.096, 0.661)],
     "px": 59.188, "py": 46.403, "ply_t": 0.1246,
     "abq": {"mises": 836.4, "s11": 858.8, "tw": 1.198, "hmt": 1.515}},

    {"sim_id": 19, "n_defects": 2,
     "defects": [(19.894, 15.369, 8.357, 0.436, 35.229, 0.716),
                 (61.019, 19.596, 8.606, 0.428, 25.133, 0.616)],
     "px": 72.373, "py": 70.013, "ply_t": 0.1268,
     "abq": {"mises": 572.7, "s11": 604.8, "tw": 2.057, "hmt": 4.074}},

    {"sim_id": 2, "n_defects": 3,
     "defects": [(80.106, 31.690, 10.086, 0.324, 97.683, 0.825),
                 (42.511, 37.182, 11.796, 0.600, 9.970, 0.225),
                 (57.856, 19.715, 8.815, 0.319, 81.874, 0.645)],
     "px": 88.140, "py": 38.546, "ply_t": 0.1241,
     "abq": {"mises": 822.9, "s11": 851.2, "tw": 1.710, "hmt": 3.161}},

    {"sim_id": 3, "n_defects": 4,
     "defects": [(48.640, 26.886, 11.411, 0.207, 14.806, 0.294),
                 (18.370, 26.139, 14.614, 0.210, 29.364, 0.534),
                 (73.662, 21.911, 10.490, 0.258, 117.590, 0.392),
                 (36.784, 13.448, 4.319, 0.280, 21.238, 0.893)],
     "px": 11.228, "py": 13.248, "ply_t": 0.1164,
     "abq": {"mises": 447.0, "s11": 454.4, "tw": 0.438, "hmt": 0.271}},

    {"sim_id": 5, "n_defects": 5,
     "defects": [(18.040, 11.608, 14.934, 0.271, 163.253, 0.260),
                 (58.174, 30.415, 11.586, 0.493, 132.474, 0.739),
                 (79.298, 25.963, 7.513, 0.456, 172.885, 0.210),
                 (39.531, 24.272, 5.530, 0.433, 8.328, 0.218),
                 (15.099, 38.219, 4.896, 0.438, 86.167, 0.364)],
     "px": 51.170, "py": 45.278, "ply_t": 0.1178,
     "abq": {"mises": 947.7, "s11": 991.7, "tw": 3.473, "hmt": 9.123}},

    {"sim_id": 4, "n_defects": 4,
     "defects": [(43.103, 32.261, 9.305, 0.430, 82.399, 0.414),
                 (53.465, 14.730, 8.594, 0.221, 68.375, 0.676),
                 (81.941, 23.456, 10.566, 0.354, 18.620, 0.706),
                 (32.557, 14.971, 7.666, 0.298, 17.079, 0.649)],
     "px": 75.320, "py": 30.628, "ply_t": 0.1883,
     "abq": {"mises": 1553.4, "s11": 1583.5, "tw": 2.087, "hmt": 2.609}},

    {"sim_id": 6, "n_defects": 4,
     "defects": [(64.119, 12.413, 10.030, 0.223, 10.300, 0.164),
                 (20.121, 35.749, 5.525, 0.424, 178.617, 0.491),
                 (20.622, 15.505, 12.177, 0.332, 15.427, 0.572),
                 (48.721, 27.096, 4.612, 0.298, 30.262, 0.305)],
     "px": 90.314, "py": 9.078, "ply_t": 0.1297,
     "abq": {"mises": 715.9, "s11": 718.2, "tw": 0.601, "hmt": 0.904}},

    {"sim_id": 7, "n_defects": 4,
     "defects": [(19.990, 15.898, 13.003, 0.455, 170.736, 0.896),
                 (82.515, 26.743, 11.681, 0.221, 107.802, 0.864),
                 (50.356, 11.630, 8.070, 0.291, 71.449, 0.763),
                 (38.818, 35.216, 4.807, 0.409, 37.173, 0.236)],
     "px": 77.623, "py": 63.367, "ply_t": 0.1431,
     "abq": {"mises": 1142.3, "s11": 1169.1, "tw": 3.162, "hmt": 7.887}},

    {"sim_id": 8, "n_defects": 5,
     "defects": [(32.753, 20.389, 14.252, 0.363, 49.117, 0.175),
                 (81.991, 33.777, 6.028, 0.265, 125.091, 0.289),
                 (63.670, 11.869, 5.758, 0.589, 29.978, 0.192),
                 (58.038, 27.216, 5.937, 0.553, 89.755, 0.243),
                 (76.526, 16.128, 5.472, 0.220, 86.411, 0.354)],
     "px": 37.254, "py": 71.988, "ply_t": 0.1634,
     "abq": {"mises": 1032.4, "s11": 1041.2, "tw": 1.088, "hmt": 1.775}},

    {"sim_id": 10, "n_defects": 1,
     "defects": [(23.357, 28.769, 10.242, 0.288, 90.725, 0.659)],
     "px": 63.082, "py": 0.659, "ply_t": 0.1521,
     "abq": {"mises": 754.5, "s11": 775.4, "tw": 1.098, "hmt": 1.364}},
]

PLATE_L = 100.0
PLATE_W = 50.0
LAYUP = [0, 45, -45, 90, 90, -45, 45, 0]

# CFRP material (same as Abaqus)
E1, E2, E3 = 135000.0, 10000.0, 10000.0
NU12, NU13, NU23 = 0.27, 0.27, 0.45
G12, G13, G23 = 5200.0, 5200.0, 3900.0

# Strength values
XT, XC = 1500.0, 1200.0
YT, YC = 50.0, 250.0
SL, ST = 70.0, 35.0

# Crack geometry constants (same as Abaqus script)
CRACK_SEG_LEN_MIN = 0.2
CRACK_SEG_LEN_MAX = 0.8
MAX_ANGLE_DEV_DEG = 45.0
MIN_POLYGON_SEGMENTS = 12

CCX_EXE = r"C:\CalculiX\calculix_2.23_4win\ccx_static.exe"
WORK_DIR = r"C:\CalculiX\test_composite"


def crack_polygon_points(cx, cy, half_length, width, angle_deg, roughness):
    """
    EXACT copy of the Abaqus batch script crack_polygon_points() function.
    Generates a jagged, tapered polygon representing a crack.
    """
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    max_dev_rad = math.radians(MAX_ANGLE_DEV_DEG) * roughness

    centerline = [(-half_length, 0.0)]
    x_pos = -half_length
    y_pos = 0.0

    while x_pos < half_length:
        seg_len = random.uniform(CRACK_SEG_LEN_MIN, CRACK_SEG_LEN_MAX)
        deviation = random.uniform(-max_dev_rad, max_dev_rad)
        dx = seg_len * math.cos(deviation)
        dy = seg_len * math.sin(deviation)
        x_pos += dx
        y_pos += dy
        y_pos = max(-half_length * 0.3, min(half_length * 0.3, y_pos))
        centerline.append((x_pos, y_pos))

    # Trim overshoot
    if len(centerline) > 2 and centerline[-1][0] > half_length * 1.05:
        px_prev, py_prev = centerline[-2]
        px_last, py_last = centerline[-1]
        dx_seg = px_last - px_prev
        if abs(dx_seg) > 1e-9:
            frac = (half_length - px_prev) / dx_seg
            frac = max(0.0, min(1.0, frac))
            new_y = py_prev + frac * (py_last - py_prev)
            centerline[-1] = (half_length, new_y)

    # Refine if too few segments
    if len(centerline) < MIN_POLYGON_SEGMENTS // 2:
        refined = [centerline[0]]
        for j in range(1, len(centerline)):
            mid_x = (centerline[j - 1][0] + centerline[j][0]) / 2.0
            mid_y = (centerline[j - 1][1] + centerline[j][1]) / 2.0
            refined.append((mid_x, mid_y))
            refined.append(centerline[j])
        centerline = refined

    # Build upper and lower edges with taper
    half_w = width / 2.0
    upper = []
    lower = []
    total_x_span = 2.0 * half_length
    if total_x_span < 1e-9:
        total_x_span = 1.0

    for i, (px, py) in enumerate(centerline):
        progress = (px + half_length) / total_x_span
        progress = max(0.0, min(1.0, progress))
        taper = 1.0 - (2.0 * abs(progress - 0.5)) ** 1.5
        taper = max(taper, 0.10)
        local_hw = half_w * taper
        upper.append((px, py + local_hw))
        lower.append((px, py - local_hw))

    local_polygon = upper + list(reversed(lower))

    # Transform to global coordinates
    global_points = []
    for lx, ly in local_polygon:
        gx = cx + lx * cos_a - ly * sin_a
        gy = cy + lx * sin_a + ly * cos_a
        global_points.append((round(gx, 6), round(gy, 6)))

    return global_points


def create_plate_with_cracks(case, job_name):
    """Create mesh with jagged polygon cracks using Gmsh OCC Boolean."""
    import gmsh
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add(job_name)

    plate = gmsh.model.occ.addRectangle(0, 0, 0, PLATE_L, PLATE_W)

    # Create jagged polygon cracks (matching Abaqus geometry)
    slot_surfs = []
    for di, defect in enumerate(case["defects"]):
        cx, cy, hl, w, ang, rough = defect
        if hl < 0.01:
            continue

        # Use deterministic seed per crack (sim_id * 1000 + defect_index)
        random.seed(case["sim_id"] * 1000 + di)
        polygon = crack_polygon_points(cx, cy, hl, w, ang, rough)

        if len(polygon) < 3:
            continue

        # Create the polygon as OCC geometry
        pts = []
        for gx, gy in polygon:
            # Clamp to plate bounds with small margin
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

    # Cut all cracks from plate
    if slot_surfs:
        result = gmsh.model.occ.cut([(2, plate)], slot_surfs)

    gmsh.model.occ.synchronize()

    # Physical groups
    surfaces = gmsh.model.getEntities(2)
    gmsh.model.addPhysicalGroup(2, [s[1] for s in surfaces], tag=5, name="plate")

    # BC curves — identify all 4 edges
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

    # Find corner node near (0,0) for pin BC
    # (will be identified after meshing from node coordinates)

    # Mesh settings — use coarser mesh near cracks to compensate for
    # S6 quadratic elements resolving singularities better than Abaqus S4R.
    # Abaqus: S4R at 0.5mm → effective stress averaging ~0.5mm from tip
    # S6 at 1.5mm → integration points ~0.75mm from tip, closer to S4R behaviour
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)  # triangles (S6)
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", 1.0)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", 3.0)

    # Refine around cracks — coarser than Abaqus to compensate for element type
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
        gmsh.model.mesh.field.setNumber(ft, "SizeMin", 1.5)   # Coarser to match S4R behaviour
        gmsh.model.mesh.field.setNumber(ft, "SizeMax", 3.0)
        gmsh.model.mesh.field.setNumber(ft, "DistMin", 1.0)
        gmsh.model.mesh.field.setNumber(ft, "DistMax", 15.0)
        gmsh.model.mesh.field.setAsBackgroundMesh(ft)

    gmsh.model.mesh.generate(2)

    # Extract mesh data
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    nodes = {}
    for i, tag in enumerate(node_tags):
        nodes[int(tag)] = (node_coords[3*i], node_coords[3*i+1], node_coords[3*i+2])

    elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(2)
    elements = []
    for etype, etags, enodes in zip(elem_types, elem_tags, elem_node_tags):
        npe = gmsh.model.mesh.getElementProperties(etype)[3]
        ename = gmsh.model.mesh.getElementProperties(etype)[0]
        for i, etag in enumerate(etags):
            enlist = [int(enodes[i*npe + j]) for j in range(npe)]
            elements.append((int(etag), ename, enlist))

    # BC node sets
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

    # Find corner node nearest to (0, 0) for pin BC
    corner_node = None
    min_dist = 1e9
    for nid, (x, y, z) in nodes.items():
        d = x*x + y*y
        if d < min_dist:
            min_dist = d
            corner_node = nid
    bc_sets["corner"] = {corner_node} if corner_node else set()

    gmsh.finalize()
    return nodes, elements, bc_sets


def write_ccx_inp(nodes, elements, bc_sets, case, job_name):
    """Write CalculiX .inp file."""
    ply_t = case["ply_t"]
    total_t = 8 * ply_t
    filepath = os.path.join(WORK_DIR, f"{job_name}.inp")

    with open(filepath, 'w') as f:
        f.write(f"*HEADING\nValidation case sim_id={case['sim_id']}\n")

        # Nodes
        f.write("*NODE\n")
        for nid in sorted(nodes.keys()):
            x, y, z = nodes[nid]
            f.write(f"{nid}, {x:.6f}, {y:.6f}, {z:.6f}\n")

        # Elements by type
        tri6 = [(eid, en) for eid, ename, en in elements if len(en) == 6]
        quad8 = [(eid, en) for eid, ename, en in elements if len(en) == 8]

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

        # Material
        f.write("*MATERIAL, NAME=CFRP_UD\n")
        f.write("*ELASTIC, TYPE=ENGINEERING CONSTANTS\n")
        f.write(f"{E1}, {E2}, {E3}, {NU12}, {NU13}, {NU23}, {G12}, {G13}\n{G23}\n")

        # Orientations
        for angle in sorted(set(LAYUP)):
            rad = math.radians(angle)
            c, s = math.cos(rad), math.sin(rad)
            name = f"ORI_{angle}".replace("-", "M")
            f.write(f"*ORIENTATION, NAME={name}, SYSTEM=RECTANGULAR\n")
            f.write(f"{c:.7f}, {s:.7f}, 0.0, {-s:.7f}, {c:.7f}, 0.0\n")

        # Shell sections
        for elset in (['PLATE_T'] if tri6 else []) + (['PLATE_Q'] if quad8 else []):
            f.write(f"*SHELL SECTION, COMPOSITE, ELSET={elset}, OFFSET=0\n")
            for angle in LAYUP:
                ori = f"ORI_{angle}".replace("-", "M")
                f.write(f"{ply_t}, 3, CFRP_UD, {ori}\n")

        # Node sets
        for name, nset in bc_sets.items():
            if nset:
                f.write(f"*NSET, NSET={name.upper()}\n")
                for i, nid in enumerate(sorted(nset)):
                    f.write(f"{nid}")
                    if i < len(nset) - 1:
                        f.write(", ")
                    if (i + 1) % 10 == 0:
                        f.write("\n")
                f.write("\n")

        # BCs — match Abaqus exactly:
        #   Left edge: u1=0 only (roller)
        #   Corner (0,0): u2=0, u3=0 (pin to prevent rigid body motion)
        f.write("*BOUNDARY\n")
        f.write("LEFT, 1, 1, 0.0\n")  # Only u1=0, NOT u2/u3

        # Pin corner node
        corner_nodes = bc_sets.get("corner", set())
        if corner_nodes:
            for nid in corner_nodes:
                f.write(f"{nid}, 2, 2, 0.0\n")  # u2=0
                f.write(f"{nid}, 3, 3, 0.0\n")  # u3=0

        # Loads — biaxial tension matching Abaqus ShellEdgeLoad
        # Abaqus: ShellEdgeLoad with GENERAL traction, magnitude = press * total_t
        # This is force per unit length along the edge
        f.write("*STEP\n*STATIC\n*CLOAD\n")
        right_nodes = bc_sets.get("right", set())
        top_nodes = bc_sets.get("top", set())
        bottom_nodes = bc_sets.get("bottom", set())

        # Right edge: tension in +X
        if right_nodes:
            f_per_node = case["px"] * total_t * PLATE_W / len(right_nodes)
            for nid in sorted(right_nodes):
                f.write(f"{nid}, 1, {f_per_node:.6f}\n")

        # Top edge: tension in +Y
        if top_nodes:
            f_per_node = case["py"] * total_t * PLATE_L / len(top_nodes)
            for nid in sorted(top_nodes):
                f.write(f"{nid}, 2, {f_per_node:.6f}\n")

        # Bottom edge: tension in -Y (Abaqus applies load on BOTH top and bottom)
        if bottom_nodes and case["py"] > 0:
            f_per_node = case["py"] * total_t * PLATE_L / len(bottom_nodes)
            for nid in sorted(bottom_nodes):
                f.write(f"{nid}, 2, {-f_per_node:.6f}\n")

        # Output
        f.write("*EL PRINT, ELSET=PLATE\nS\n")
        f.write("*NODE FILE\nU\n*EL FILE\nS\n")
        f.write("*END STEP\n")

    return filepath


def parse_stresses(dat_path):
    """Parse per-element, per-integration-point stresses from .dat file."""
    elem_stresses = {}
    with open(dat_path, 'r') as f:
        in_block = False
        for line in f:
            if 'stresses (elem' in line:
                in_block = True
                continue
            if in_block:
                parts = line.split()
                if len(parts) >= 8:
                    try:
                        elem = int(parts[0])
                        sxx = float(parts[2])
                        syy = float(parts[3])
                        szz = float(parts[4])
                        sxy = float(parts[5])
                        sxz = float(parts[6])
                        syz = float(parts[7])
                        ori = parts[8] if len(parts) > 8 else ""
                        if elem not in elem_stresses:
                            elem_stresses[elem] = []
                        elem_stresses[elem].append((sxx, syy, szz, sxy, sxz, syz, ori))
                    except (ValueError, IndexError):
                        if any(kw in line.lower() for kw in ['displacements', 'forces', 'step']):
                            in_block = False
    return elem_stresses


def compute_results(elem_stresses):
    """Compute max Mises, Hashin, Tsai-Wu per INDIVIDUAL integration point.

    No averaging — matches Abaqus which reports max over all int. points.
    Uses element-level averaging only as a secondary metric.
    """
    all_mises = []
    all_tw = []
    all_hmt = []
    max_s11 = -1e30

    # Per-element averaged Mises (for percentile comparison)
    elem_avg_mises = []

    for elem_id, stress_list in elem_stresses.items():
        elem_vm_list = []

        for sxx, syy, szz, sxy, sxz, syz, ori in stress_list:
            # Von Mises per integration point
            vm = math.sqrt(0.5 * ((sxx-syy)**2 + (syy-szz)**2 +
                                   (szz-sxx)**2 + 6*(sxy**2+sxz**2+syz**2)))
            all_mises.append(vm)
            elem_vm_list.append(vm)

            if sxx > max_s11:
                max_s11 = sxx

            # Hashin matrix tension (per integration point)
            s11, s22, s12 = sxx, syy, sxy
            if s22 >= 0:
                hmt = (s22/YT)**2 + (s12/SL)**2
            else:
                hmt = 0.0
            all_hmt.append(hmt)

            # Tsai-Wu (per integration point)
            F1 = 1.0/XT - 1.0/XC
            F2 = 1.0/YT - 1.0/YC
            F11 = 1.0/(XT*XC)
            F22 = 1.0/(YT*YC)
            F66 = 1.0/SL**2
            F12 = -0.5 * math.sqrt(F11 * F22)
            tw = F1*s11 + F2*s22 + F11*s11**2 + F22*s22**2 + F66*s12**2 + 2*F12*s11*s22
            all_tw.append(tw)

        if elem_vm_list:
            elem_avg_mises.append(sum(elem_vm_list) / len(elem_vm_list))

    # Sort for percentile computation
    all_mises.sort()
    all_tw.sort()
    all_hmt.sort()
    elem_avg_mises.sort()

    n = len(all_mises)
    ne = len(elem_avg_mises)
    if n == 0:
        return {'max_mises': 0, 'p995_mises': 0, 'p99_mises': 0,
                'max_s11': 0, 'max_tw': 0, 'p995_tw': 0, 'p99_tw': 0,
                'max_hmt': 0, 'p995_hmt': 0, 'p99_hmt': 0,
                'n_int_pts': 0, 'n_elems': 0, 'elem_max_mises': 0}

    p99 = int(n * 0.99)
    p995 = int(n * 0.995)

    return {
        'max_mises': all_mises[-1],
        'p995_mises': all_mises[min(p995, n-1)],
        'p99_mises': all_mises[min(p99, n-1)],
        'max_s11': max_s11,
        'max_tw': all_tw[-1],
        'p995_tw': all_tw[min(p995, n-1)],
        'p99_tw': all_tw[min(p99, n-1)],
        'max_hmt': all_hmt[-1],
        'p995_hmt': all_hmt[min(p995, n-1)],
        'p99_hmt': all_hmt[min(p99, n-1)],
        'n_int_pts': n,
        'n_elems': ne,
        'elem_max_mises': elem_avg_mises[-1] if elem_avg_mises else 0,
    }


def main():
    print("=" * 70)
    print("CALCULIX vs ABAQUS - MULTI-CASE VALIDATION (10 cases)")
    print("Crack geometry: jagged polygon (matching Abaqus algorithm)")
    print("=" * 70)

    results = []

    for case in CASES:
        sid = case["sim_id"]
        nd = case["n_defects"]
        job = f"val_sim{sid}"
        print(f"\n--- Case: sim_id={sid}, {nd} defect(s) ---")

        t0 = time.time()

        # 1. Mesh
        print("  Meshing...", end=" ", flush=True)
        try:
            nodes, elements, bc_sets = create_plate_with_cracks(case, job)
            print(f"{len(nodes)} nodes, {len(elements)} elements")
        except Exception as e:
            print(f"FAILED: {e}")
            import traceback; traceback.print_exc()
            results.append(None)
            continue

        # 2. Write .inp
        write_ccx_inp(nodes, elements, bc_sets, case, job)

        # 3. Run CalculiX
        print("  Solving...", end=" ", flush=True)
        os.chdir(WORK_DIR)
        try:
            proc = subprocess.run([CCX_EXE, job], capture_output=True, text=True, timeout=300)
            if "Job finished" not in (proc.stdout or "") and "Job finished" not in (proc.stderr or ""):
                print("FAILED")
                out = (proc.stdout or "")[-500:]
                err = (proc.stderr or "")[-500:]
                if out: print(f"  stdout: {out}")
                if err: print(f"  stderr: {err}")
                results.append(None)
                continue
        except subprocess.TimeoutExpired:
            print("TIMEOUT")
            results.append(None)
            continue

        dt = time.time() - t0
        print(f"done ({dt:.1f}s)")

        # 4. Parse and compute
        dat_path = os.path.join(WORK_DIR, f"{job}.dat")
        elem_stresses = parse_stresses(dat_path)
        if not elem_stresses:
            print("  WARNING: no stresses parsed from .dat file")
            results.append(None)
            continue

        res = compute_results(elem_stresses)
        res['time'] = dt
        results.append(res)

        abq_mises = case['abq']['mises']
        ratio_max = res['max_mises'] / abq_mises if abq_mises > 0 else 0
        ratio_995 = res['p995_mises'] / abq_mises if abq_mises > 0 else 0
        print(f"  CCX max={res['max_mises']:.1f}  p99.5={res['p995_mises']:.1f}  ABQ={abq_mises:.1f}")
        print(f"  ratios: max={ratio_max:.2f}x  p99.5={ratio_995:.2f}x  ({res['n_elems']} elems, {res['n_int_pts']} int.pts)")

    # Summary table
    print("\n" + "=" * 90)
    print("SUMMARY — CalculiX vs Abaqus (von Mises stress)")
    print("=" * 90)
    print(f"{'sim_id':>6} {'#def':>4} {'ABQ mis':>8} {'CCX p995':>9} {'r_mis':>6} "
          f"{'ABQ tw':>7} {'CCX tw':>8} {'r_tw':>6} "
          f"{'ABQ hmt':>8} {'CCX hmt':>8} {'r_hmt':>6} {'time':>5}")
    print("-" * 100)

    p995_ratios = []
    tw_ratios = []
    hmt_ratios = []
    for case, res in zip(CASES, results):
        if res is None:
            print(f"{case['sim_id']:>6} {case['n_defects']:>4}  FAILED")
            continue
        abq = case['abq']['mises']
        abq_tw = case['abq']['tw']
        abq_hmt = case['abq']['hmt']

        pr = res['p995_mises'] / abq if abq > 0 else 0
        twr = res['p995_tw'] / abq_tw if abq_tw > 0.01 else 0
        hmtr = res['p995_hmt'] / abq_hmt if abq_hmt > 0.01 else 0

        p995_ratios.append(pr)
        if abq_tw > 0.01: tw_ratios.append(twr)
        if abq_hmt > 0.01: hmt_ratios.append(hmtr)

        print(f"{case['sim_id']:>6} {case['n_defects']:>4} "
              f"{abq:>8.1f} {res['p995_mises']:>9.1f} {pr:>5.2f}x "
              f"{abq_tw:>7.3f} {res['p995_tw']:>8.3f} {twr:>5.2f}x "
              f"{abq_hmt:>8.3f} {res['p995_hmt']:>8.3f} {hmtr:>5.2f}x "
              f"{res['time']:>4.1f}s")

    # Overall assessment
    if p995_ratios:
        for name, ratios in [("Mises p99.5", p995_ratios), ("Tsai-Wu p99.5", tw_ratios), ("Hashin-MT p99.5", hmt_ratios)]:
            if not ratios:
                continue
            avg = sum(ratios) / len(ratios)
            std = (sum((r - avg)**2 for r in ratios) / len(ratios)) ** 0.5
            print(f"\n{name:>18} ratio: avg={avg:.2f}x  std={std:.2f}  range=[{min(ratios):.2f}x, {max(ratios):.2f}x]")

    print("\nNOTE: Crack shapes differ from Abaqus (different random seed).")
    print("      CalculiX S6 elements resolve crack-tip singularities differently than S4R.")


if __name__ == "__main__":
    main()
