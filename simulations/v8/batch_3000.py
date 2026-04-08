"""
Batch CalculiX simulation script: 3000 composite plate simulations with random crack defects.
Uses seed=42 (independent from Abaqus seed=55).
Generates all samples upfront for deterministic resume capability.
"""

import numpy as np
import subprocess
import os
import sys
import math
import random
import csv
import time
import traceback

# =============================================================================
# Constants
# =============================================================================
PLATE_L = 100.0
PLATE_W = 50.0
NUM_SAMPLES = 3000
RANDOM_SEED = 42
MAX_DEFECTS = 5
MAX_PLACEMENT_ATTEMPTS = 200
MIN_CRACK_WIDTH = 0.15

CRACK_SEG_LEN_MIN = 0.2
CRACK_SEG_LEN_MAX = 0.8
MAX_ANGLE_DEV_DEG = 45.0
MIN_POLYGON_SEGMENTS = 12

LAYUP = [0, 45, -45, 90, 90, -45, 45, 0]

E1, E2, E3 = 135000.0, 10000.0, 10000.0
NU12, NU13, NU23 = 0.27, 0.27, 0.45
G12, G13, G23 = 5200.0, 5200.0, 3900.0

XT, XC = 1500.0, 1200.0
YT, YC = 50.0, 250.0
SL, ST = 70.0, 35.0

CCX_EXE = r"C:\CalculiX\calculix_2.23_4win\ccx_static.exe"
WORK_DIR = r"C:\CalculiX\test_composite"
OUTPUT_CSV = os.path.join(WORK_DIR, "calculix_results_3000.csv")

SOLVER_TIMEOUT = 300
CRACK_SEARCH_BUFFER = 3.0

GLOBAL_RANGES = {
    'pressure_x':     [5.0,   100.0],
    'pressure_y':     [0.0,   100.0],
    'ply_thickness':  [0.10,  0.20],
    'layup_rotation': [0.0,   90.0],
}

DEFECT_RANGES = {
    'x':           [15.0, 85.0],
    'y':           [10.0, 40.0],
    'half_length': [4.0,  15.0],
    'width':       [0.15, 0.6],
    'angle':       [0.0,  180.0],
    'roughness':   [0.15, 0.90],
}

CSV_COLUMNS = [
    'sim_id', 'n_defects',
    'defect1_x', 'defect1_y', 'defect1_half_length', 'defect1_width', 'defect1_angle', 'defect1_roughness',
    'defect2_x', 'defect2_y', 'defect2_half_length', 'defect2_width', 'defect2_angle', 'defect2_roughness',
    'defect3_x', 'defect3_y', 'defect3_half_length', 'defect3_width', 'defect3_angle', 'defect3_roughness',
    'defect4_x', 'defect4_y', 'defect4_half_length', 'defect4_width', 'defect4_angle', 'defect4_roughness',
    'defect5_x', 'defect5_y', 'defect5_half_length', 'defect5_width', 'defect5_angle', 'defect5_roughness',
    'pressure_x', 'pressure_y', 'ply_thickness', 'layup_rotation',
    'min_inter_defect_dist',
    'solver_completed', 'n_elements',
    'max_mises', 'max_s11', 'min_s11', 'max_s12',
    'tsai_wu_index',
    'max_hashin_ft', 'max_hashin_fc', 'max_hashin_mt', 'max_hashin_mc',
    'max_mises_defect1', 'max_mises_defect2', 'max_mises_defect3',
    'max_mises_defect4', 'max_mises_defect5',
    'failed_tsai_wu', 'failed_hashin',
]


# =============================================================================
# Sampling functions (exact copies from Abaqus script)
# =============================================================================
def latin_hypercube_sample(param_ranges, n_samples, seed=42):
    random.seed(seed)
    param_names = list(param_ranges.keys())
    columns = {}
    for name in param_names:
        lo, hi = param_ranges[name]
        samples = []
        for i in range(n_samples):
            stratum_lo = lo + (hi - lo) * i / n_samples
            stratum_hi = lo + (hi - lo) * (i + 1) / n_samples
            samples.append(random.uniform(stratum_lo, stratum_hi))
        random.shuffle(samples)
        columns[name] = samples
    samples_list = []
    for i in range(n_samples):
        sample = {}
        for name in param_names:
            sample[name] = columns[name][i]
        samples_list.append(sample)
    return samples_list


def validate_crack_bounds(cx, cy, half_length, width, angle_deg,
                          roughness, plate_length, plate_width,
                          margin=2.0):
    max_lateral = width / 2.0 + half_length * 0.3
    t = math.radians(angle_deg)
    dx = abs(half_length * math.cos(t)) + abs(max_lateral * math.sin(t))
    dy = abs(half_length * math.sin(t)) + abs(max_lateral * math.cos(t))
    if cx - dx < margin:
        return False
    if cx + dx > plate_length - margin:
        return False
    if cy - dy < margin:
        return False
    if cy + dy > plate_width - margin:
        return False
    return True


def overlaps_existing(new_defect, existing_defects, margin=2.0):
    for d in existing_defects:
        dist = math.sqrt(
            (new_defect['x'] - d['x'])**2 +
            (new_defect['y'] - d['y'])**2)
        min_dist = (new_defect['half_length'] +
                    d['half_length'] + margin)
        if dist < min_dist:
            return True
    return False


def place_defects_sequentially(n_defects):
    placed = []
    for crack_idx in range(n_defects):
        placed_this_crack = False
        for attempt in range(MAX_PLACEMENT_ATTEMPTS):
            defect = {}
            for pname, (lo, hi) in DEFECT_RANGES.items():
                defect[pname] = random.uniform(lo, hi)
            if defect['width'] < MIN_CRACK_WIDTH:
                defect['width'] = MIN_CRACK_WIDTH
            if not validate_crack_bounds(
                    defect['x'], defect['y'],
                    defect['half_length'], defect['width'],
                    defect['angle'], defect['roughness'],
                    PLATE_L, PLATE_W):
                continue
            if overlaps_existing(defect, placed):
                continue
            placed.append(defect)
            placed_this_crack = True
            break
        if not placed_this_crack:
            return None
    return placed


def generate_all_samples(n_total, seed=42):
    random.seed(seed)
    counts_per_n = n_total // MAX_DEFECTS
    remainder = n_total - counts_per_n * MAX_DEFECTS
    global_samples = latin_hypercube_sample(
        GLOBAL_RANGES, n_total, seed=seed)

    all_samples = []
    idx = 0
    placement_failures = 0
    MAX_SAMPLE_FAILURES = 50

    for n_def in range(1, MAX_DEFECTS + 1):
        n_sims = counts_per_n + (1 if n_def <= remainder else 0)
        placed_count = 0
        consecutive_failures = 0

        while placed_count < n_sims and idx < n_total:
            defects = place_defects_sequentially(n_def)
            if defects is None:
                placement_failures += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_SAMPLE_FAILURES:
                    break
                continue
            consecutive_failures = 0
            sample = {
                'n_defects': n_def,
                'pressure_x': global_samples[idx]['pressure_x'],
                'pressure_y': global_samples[idx]['pressure_y'],
                'ply_thickness': global_samples[idx]['ply_thickness'],
                'layup_rotation': global_samples[idx]['layup_rotation'],
                'defects': defects,
            }
            all_samples.append(sample)
            placed_count += 1
            idx += 1

    random.seed(seed + 999)
    random.shuffle(all_samples)
    return all_samples


# =============================================================================
# Crack polygon generation (exact copy from Abaqus script)
# =============================================================================
def crack_polygon_points(cx, cy, half_length, width, angle_deg, roughness):
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

    if len(centerline) > 2 and centerline[-1][0] > half_length * 1.05:
        px_prev, py_prev = centerline[-2]
        px_last, py_last = centerline[-1]
        dx_seg = px_last - px_prev
        if abs(dx_seg) > 1e-9:
            frac = (half_length - px_prev) / dx_seg
            frac = max(0.0, min(1.0, frac))
            new_y = py_prev + frac * (py_last - py_prev)
            centerline[-1] = (half_length, new_y)

    if len(centerline) < MIN_POLYGON_SEGMENTS // 2:
        refined = [centerline[0]]
        for j in range(1, len(centerline)):
            mid_x = (centerline[j - 1][0] + centerline[j][0]) / 2.0
            mid_y = (centerline[j - 1][1] + centerline[j][1]) / 2.0
            refined.append((mid_x, mid_y))
            refined.append(centerline[j])
        centerline = refined

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

    global_points = []
    for lx, ly in local_polygon:
        gx = cx + lx * cos_a - ly * sin_a
        gy = cy + lx * sin_a + ly * cos_a
        global_points.append((round(gx, 6), round(gy, 6)))

    return global_points


def polygon_self_intersects(polygon):
    """Check if a polygon has self-intersecting edges."""
    n = len(polygon)
    if n < 4:
        return False

    def ccw(A, B, C):
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

    def segments_intersect(A, B, C, D):
        return (ccw(A, C, D) != ccw(B, C, D)) and (ccw(A, B, C) != ccw(A, B, D))

    edges = []
    for i in range(n):
        edges.append((polygon[i], polygon[(i + 1) % n]))

    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # adjacent edges share a vertex
            if segments_intersect(edges[i][0], edges[i][1], edges[j][0], edges[j][1]):
                return True
    return False


# =============================================================================
# Mesh generation
# =============================================================================
def create_plate_with_cracks(polygons, job_name):
    """Create mesh using crack polygons via Gmsh OCC Boolean."""
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

    if left_c:
        gmsh.model.addPhysicalGroup(1, left_c, tag=1, name="left")
    if bottom_c:
        gmsh.model.addPhysicalGroup(1, bottom_c, tag=2, name="bottom")
    if right_c:
        gmsh.model.addPhysicalGroup(1, right_c, tag=3, name="right")
    if top_c:
        gmsh.model.addPhysicalGroup(1, top_c, tag=4, name="top")

    # Mesh settings — S6 triangular, fine mesh
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", 0.5)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", 3.0)

    # Crack refinement
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
        nodes[int(tag)] = (node_coords[3 * i], node_coords[3 * i + 1], node_coords[3 * i + 2])

    elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(2)
    elements = []
    for etype, etags, enodes in zip(elem_types, elem_tags, elem_node_tags):
        npe = gmsh.model.mesh.getElementProperties(etype)[3]
        for i, etag in enumerate(etags):
            enlist = [int(enodes[i * npe + j]) for j in range(npe)]
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

    # Corner node near (0,0)
    corner = min(nodes.keys(), key=lambda n: nodes[n][0]**2 + nodes[n][1]**2)
    bc_sets["corner"] = {corner}

    gmsh.finalize()
    return nodes, elements, bc_sets


# =============================================================================
# Write CalculiX .inp file
# =============================================================================
def write_ccx_inp(nodes, elements, bc_sets, case, job_name):
    ply_t = case["ply_thickness"]
    total_t = 8 * ply_t
    filepath = os.path.join(WORK_DIR, f"{job_name}.inp")

    with open(filepath, 'w') as f:
        f.write(f"*HEADING\nBatch3000 sim_id={case['sim_id']}\n")

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

        # BCs: left u1=0 (roller), corner u2=u3=0 (pin)
        f.write("*BOUNDARY\nLEFT, 1, 1, 0.0\n")
        for nid in bc_sets.get("corner", set()):
            f.write(f"{nid}, 2, 2, 0.0\n{nid}, 3, 3, 0.0\n")

        # Loads: CLOAD on right (+X), top (+Y), bottom (-Y)
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


# =============================================================================
# Stress parsing and failure index computation
# =============================================================================
def parse_stresses(dat_path):
    """Parse all integration point stresses from the .dat file.
    Returns list of (elem_id, sxx, syy, szz, sxy, sxz, syz) tuples.
    """
    stress_data = []
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
                        eid = int(parts[0])
                        sxx = float(parts[2])
                        syy = float(parts[3])
                        szz = float(parts[4])
                        sxy = float(parts[5])
                        sxz = float(parts[6])
                        syz = float(parts[7])
                        stress_data.append((eid, sxx, syy, szz, sxy, sxz, syz))
                    except (ValueError, IndexError):
                        if any(kw in line.lower() for kw in ['displacements', 'forces', 'step']):
                            in_block = False
    return stress_data


def compute_metrics(stress_data, element_centroids, defects):
    """Compute all failure metrics from integration point stresses."""
    if not stress_data:
        return None

    all_mises = []
    all_s11 = []
    all_s12 = []
    all_tw = []
    all_hashin_ft = []
    all_hashin_fc = []
    all_hashin_mt = []
    all_hashin_mc = []

    # Per-element mises for defect-local computation
    elem_mises = {}  # eid -> list of mises values

    for eid, sxx, syy, szz, sxy, sxz, syz in stress_data:
        # Von Mises
        vm = math.sqrt(0.5 * ((sxx - syy)**2 + (syy - szz)**2 +
                               (szz - sxx)**2 + 6 * (sxy**2 + sxz**2 + syz**2)))
        all_mises.append(vm)
        all_s11.append(sxx)
        all_s12.append(abs(sxy))

        if eid not in elem_mises:
            elem_mises[eid] = []
        elem_mises[eid].append(vm)

        # Tsai-Wu
        s11, s22, s12 = sxx, syy, sxy
        F1 = 1.0 / XT - 1.0 / XC
        F2 = 1.0 / YT - 1.0 / YC
        F11 = 1.0 / (XT * XC)
        F22 = 1.0 / (YT * YC)
        F66 = 1.0 / SL**2
        F12 = -0.5 * math.sqrt(F11 * F22)  # MULTIPLICATION not division
        tw = F1 * s11 + F2 * s22 + F11 * s11**2 + F22 * s22**2 + F66 * s12**2 + 2 * F12 * s11 * s22
        all_tw.append(tw)

        # Hashin criteria
        if sxx >= 0:
            hft = (sxx / XT)**2 + (sxy / SL)**2
            hfc = 0.0
        else:
            hft = 0.0
            hfc = (sxx / XC)**2

        if syy >= 0:
            hmt = (syy / YT)**2 + (sxy / SL)**2
            hmc = 0.0
        else:
            hmt = 0.0
            hmc = ((YC / (2 * ST))**2 - 1) * (syy / YC) + (syy / (2 * ST))**2 + (sxy / SL)**2

        all_hashin_ft.append(hft)
        all_hashin_fc.append(hfc)
        all_hashin_mt.append(hmt)
        all_hashin_mc.append(hmc)

    # Sort for percentile extraction
    all_mises_sorted = sorted(all_mises)
    all_s11_sorted = sorted(all_s11)
    all_s12_sorted = sorted(all_s12)
    all_tw_sorted = sorted(all_tw)
    all_hft_sorted = sorted(all_hashin_ft)
    all_hfc_sorted = sorted(all_hashin_fc)
    all_hmt_sorted = sorted(all_hashin_mt)
    all_hmc_sorted = sorted(all_hashin_mc)

    n = len(all_mises)

    def percentile(sorted_arr, p):
        idx = min(int(len(sorted_arr) * p), len(sorted_arr) - 1)
        return sorted_arr[idx]

    max_mises = percentile(all_mises_sorted, 0.999)
    max_s11 = percentile(all_s11_sorted, 0.999)
    min_s11 = all_s11_sorted[0]
    max_s12 = percentile(all_s12_sorted, 0.999)
    tsai_wu_index = percentile(all_tw_sorted, 0.997)
    max_hashin_ft = percentile(all_hft_sorted, 0.998)
    max_hashin_fc = percentile(all_hfc_sorted, 0.998)
    max_hashin_mt = percentile(all_hmt_sorted, 0.998)
    max_hashin_mc = percentile(all_hmc_sorted, 0.998)

    # Failure flags
    failed_tsai_wu = 1 if tsai_wu_index >= 1.0 else 0
    failed_hashin = 1 if (max_hashin_ft >= 1.0 or max_hashin_fc >= 1.0 or
                          max_hashin_mt >= 1.0 or max_hashin_mc >= 1.0) else 0

    # Per-defect max mises (within CRACK_SEARCH_BUFFER of defect center)
    mises_per_defect = []
    for di in range(MAX_DEFECTS):
        if di < len(defects):
            d = defects[di]
            dcx, dcy = d['x'], d['y']
            local_max = 0.0
            for eid, mises_list in elem_mises.items():
                if eid in element_centroids:
                    ex, ey = element_centroids[eid]
                    dist = math.sqrt((ex - dcx)**2 + (ey - dcy)**2)
                    if dist <= CRACK_SEARCH_BUFFER + d['half_length']:
                        for vm in mises_list:
                            if vm > local_max:
                                local_max = vm
            mises_per_defect.append(local_max)
        else:
            mises_per_defect.append(0.0)

    return {
        'n_elements': len(set(eid for eid, *_ in stress_data)),
        'max_mises': max_mises,
        'max_s11': max_s11,
        'min_s11': min_s11,
        'max_s12': max_s12,
        'tsai_wu_index': tsai_wu_index,
        'max_hashin_ft': max_hashin_ft,
        'max_hashin_fc': max_hashin_fc,
        'max_hashin_mt': max_hashin_mt,
        'max_hashin_mc': max_hashin_mc,
        'mises_per_defect': mises_per_defect,
        'failed_tsai_wu': failed_tsai_wu,
        'failed_hashin': failed_hashin,
    }


def compute_element_centroids(nodes, elements):
    """Compute centroid of each element from its node coordinates."""
    centroids = {}
    for eid, npe, enlist in elements:
        xs = []
        ys = []
        for nid in enlist:
            if nid in nodes:
                xs.append(nodes[nid][0])
                ys.append(nodes[nid][1])
        if xs:
            centroids[eid] = (sum(xs) / len(xs), sum(ys) / len(ys))
    return centroids


def compute_min_inter_defect_dist(defects):
    """Compute minimum distance between defect centers."""
    if len(defects) < 2:
        return 0.0
    min_dist = float('inf')
    for i in range(len(defects)):
        for j in range(i + 1, len(defects)):
            d = math.sqrt((defects[i]['x'] - defects[j]['x'])**2 +
                          (defects[i]['y'] - defects[j]['y'])**2)
            if d < min_dist:
                min_dist = d
    return min_dist


# =============================================================================
# CSV I/O
# =============================================================================
def load_completed_sims(csv_path):
    """Load set of already-completed sim_ids from CSV."""
    completed = set()
    if not os.path.exists(csv_path):
        return completed
    try:
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    completed.add(int(row['sim_id']))
                except (ValueError, KeyError):
                    pass
    except Exception:
        pass
    return completed


def write_csv_header(csv_path):
    """Write CSV header if file doesn't exist."""
    if not os.path.exists(csv_path):
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)


def append_csv_row(csv_path, row_dict):
    """Append a single result row to the CSV."""
    with open(csv_path, 'a', newline='') as f:
        writer = csv.writer(f)
        row = []
        for col in CSV_COLUMNS:
            row.append(row_dict.get(col, 0))
        writer.writerow(row)


def build_row(sim_id, sample, metrics=None, error=False, n_elements=0):
    """Build a result row dict from sample and computed metrics."""
    row = {'sim_id': sim_id, 'n_defects': sample['n_defects']}

    # Defect columns (pad with 0 for unused)
    for di in range(MAX_DEFECTS):
        prefix = f"defect{di+1}_"
        if di < len(sample['defects']):
            d = sample['defects'][di]
            row[prefix + 'x'] = round(d['x'], 6)
            row[prefix + 'y'] = round(d['y'], 6)
            row[prefix + 'half_length'] = round(d['half_length'], 6)
            row[prefix + 'width'] = round(d['width'], 6)
            row[prefix + 'angle'] = round(d['angle'], 6)
            row[prefix + 'roughness'] = round(d['roughness'], 6)
        else:
            for field in ['x', 'y', 'half_length', 'width', 'angle', 'roughness']:
                row[prefix + field] = 0

    row['pressure_x'] = round(sample['pressure_x'], 6)
    row['pressure_y'] = round(sample['pressure_y'], 6)
    row['ply_thickness'] = round(sample['ply_thickness'], 6)
    row['layup_rotation'] = round(sample['layup_rotation'], 6)
    row['min_inter_defect_dist'] = round(compute_min_inter_defect_dist(sample['defects']), 6)

    if error or metrics is None:
        row['solver_completed'] = 'ERROR'
        row['n_elements'] = n_elements
        for col in ['max_mises', 'max_s11', 'min_s11', 'max_s12',
                     'tsai_wu_index', 'max_hashin_ft', 'max_hashin_fc',
                     'max_hashin_mt', 'max_hashin_mc']:
            row[col] = 0
        for di in range(MAX_DEFECTS):
            row[f'max_mises_defect{di+1}'] = 0
        row['failed_tsai_wu'] = 0
        row['failed_hashin'] = 0
    else:
        row['solver_completed'] = 'YES'
        row['n_elements'] = metrics['n_elements']
        row['max_mises'] = round(metrics['max_mises'], 6)
        row['max_s11'] = round(metrics['max_s11'], 6)
        row['min_s11'] = round(metrics['min_s11'], 6)
        row['max_s12'] = round(metrics['max_s12'], 6)
        row['tsai_wu_index'] = round(metrics['tsai_wu_index'], 6)
        row['max_hashin_ft'] = round(metrics['max_hashin_ft'], 6)
        row['max_hashin_fc'] = round(metrics['max_hashin_fc'], 6)
        row['max_hashin_mt'] = round(metrics['max_hashin_mt'], 6)
        row['max_hashin_mc'] = round(metrics['max_hashin_mc'], 6)
        for di in range(MAX_DEFECTS):
            row[f'max_mises_defect{di+1}'] = round(metrics['mises_per_defect'][di], 6)
        row['failed_tsai_wu'] = metrics['failed_tsai_wu']
        row['failed_hashin'] = metrics['failed_hashin']

    return row


# =============================================================================
# Cleanup
# =============================================================================
def cleanup_large_files(job_name):
    """Delete .dat and .frd files to save disk space."""
    for ext in ['.dat', '.frd']:
        fpath = os.path.join(WORK_DIR, f"{job_name}{ext}")
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except OSError:
                pass


# =============================================================================
# Main batch runner
# =============================================================================
def main():
    print("=" * 75)
    print("BATCH 3000: CalculiX Composite Plate Simulations with Crack Defects")
    print(f"Output: {OUTPUT_CSV}")
    print(f"Solver: {CCX_EXE}")
    print(f"Random seed: {RANDOM_SEED}")
    print("=" * 75)

    # Step 1: Generate ALL 3000 samples deterministically
    print("\nStep 1: Generating all samples (seed=42)...")
    t_gen_start = time.time()
    all_samples = generate_all_samples(NUM_SAMPLES, seed=RANDOM_SEED)
    print(f"  Generated {len(all_samples)} samples in {time.time() - t_gen_start:.1f}s")

    # Count per n_defects
    counts = {}
    for s in all_samples:
        nd = s['n_defects']
        counts[nd] = counts.get(nd, 0) + 1
    for nd in sorted(counts):
        print(f"    n_defects={nd}: {counts[nd]} samples")

    # Step 2: Generate ALL crack polygons deterministically
    # We need to replay the random state for polygon generation
    # The random state after generate_all_samples is at seed+999 post-shuffle
    # We use a separate seed for polygon generation to keep it deterministic
    print("\nStep 2: Generating crack polygons for all samples...")
    random.seed(RANDOM_SEED + 7777)  # Separate deterministic seed for polygons
    all_polygons = []
    polygon_failures = set()
    for i, sample in enumerate(all_samples):
        crack_polys = []
        valid = True
        for d in sample['defects']:
            poly = crack_polygon_points(
                d['x'], d['y'], d['half_length'],
                d['width'], d['angle'], d['roughness'])
            if polygon_self_intersects(poly):
                valid = False
                break
            crack_polys.append(poly)
        if valid:
            all_polygons.append(crack_polys)
        else:
            all_polygons.append(None)
            polygon_failures.add(i)
    print(f"  Polygons generated: {len(all_samples) - len(polygon_failures)} valid, "
          f"{len(polygon_failures)} self-intersecting (will be ERROR)")

    # Step 3: Check resume state
    completed_sims = load_completed_sims(OUTPUT_CSV)
    write_csv_header(OUTPUT_CSV)
    print(f"\nStep 3: Resume check - {len(completed_sims)} sims already completed")

    # Step 4: Run simulations
    total = len(all_samples)
    to_run = total - len(completed_sims)
    print(f"\nStep 4: Running {to_run} simulations (of {total} total)...")
    print("-" * 75)

    t_batch_start = time.time()
    n_success = 0
    n_fail = 0
    n_skipped = 0

    for i, sample in enumerate(all_samples):
        sim_id = i + 1

        # Skip already completed
        if sim_id in completed_sims:
            n_skipped += 1
            continue

        job_name = f"batch3k_sim{sim_id}"
        polygons = all_polygons[i]

        # Progress logging every 10 sims
        done_so_far = n_success + n_fail
        if done_so_far > 0 and done_so_far % 10 == 0:
            elapsed = time.time() - t_batch_start
            rate = done_so_far / elapsed if elapsed > 0 else 0
            eta = (to_run - done_so_far) / rate if rate > 0 else 0
            print(f"  [Progress] {done_so_far}/{to_run} done | "
                  f"{n_success} OK, {n_fail} ERR | "
                  f"{elapsed:.0f}s elapsed, ETA {eta:.0f}s ({eta/60:.1f}min)")

        # Handle polygon self-intersection
        if polygons is None:
            print(f"  sim {sim_id}: SKIP (self-intersecting polygon)")
            row = build_row(sim_id, sample, error=True)
            append_csv_row(OUTPUT_CSV, row)
            n_fail += 1
            continue

        # Mesh generation
        t0 = time.time()
        try:
            nodes, elements, bc_sets = create_plate_with_cracks(polygons, job_name)
            n_elements = len(elements)
        except Exception as e:
            print(f"  sim {sim_id}: MESH FAIL - {e}")
            row = build_row(sim_id, sample, error=True)
            append_csv_row(OUTPUT_CSV, row)
            n_fail += 1
            continue

        # Write .inp
        case = {
            'sim_id': sim_id,
            'pressure_x': sample['pressure_x'],
            'pressure_y': sample['pressure_y'],
            'ply_thickness': sample['ply_thickness'],
        }
        write_ccx_inp(nodes, elements, bc_sets, case, job_name)

        # Solve
        try:
            proc = subprocess.run(
                [CCX_EXE, job_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=SOLVER_TIMEOUT,
                cwd=WORK_DIR)
            # Check success by .dat file existence and size (stdout unreliable in detached mode)
            dat_check = os.path.join(WORK_DIR, f"{job_name}.dat")
            if not os.path.exists(dat_check) or os.path.getsize(dat_check) < 100:
                dt = time.time() - t0
                print(f"  sim {sim_id}: SOLVER FAIL ({dt:.1f}s, {n_elements} elems)")
                row = build_row(sim_id, sample, error=True, n_elements=n_elements)
                append_csv_row(OUTPUT_CSV, row)
                cleanup_large_files(job_name)
                n_fail += 1
                continue
        except subprocess.TimeoutExpired:
            print(f"  sim {sim_id}: TIMEOUT ({SOLVER_TIMEOUT}s)")
            row = build_row(sim_id, sample, error=True, n_elements=n_elements)
            append_csv_row(OUTPUT_CSV, row)
            cleanup_large_files(job_name)
            n_fail += 1
            continue
        except Exception as e:
            print(f"  sim {sim_id}: SOLVER ERROR - {e}")
            row = build_row(sim_id, sample, error=True, n_elements=n_elements)
            append_csv_row(OUTPUT_CSV, row)
            cleanup_large_files(job_name)
            n_fail += 1
            continue

        # Parse stresses
        dat_path = os.path.join(WORK_DIR, f"{job_name}.dat")
        if not os.path.exists(dat_path):
            print(f"  sim {sim_id}: NO .dat FILE")
            row = build_row(sim_id, sample, error=True, n_elements=n_elements)
            append_csv_row(OUTPUT_CSV, row)
            n_fail += 1
            continue

        try:
            stress_data = parse_stresses(dat_path)
            if not stress_data:
                print(f"  sim {sim_id}: NO STRESSES IN .dat")
                row = build_row(sim_id, sample, error=True, n_elements=n_elements)
                append_csv_row(OUTPUT_CSV, row)
                cleanup_large_files(job_name)
                n_fail += 1
                continue

            element_centroids = compute_element_centroids(nodes, elements)
            metrics = compute_metrics(stress_data, element_centroids, sample['defects'])

            if metrics is None:
                print(f"  sim {sim_id}: METRIC COMPUTATION FAILED")
                row = build_row(sim_id, sample, error=True, n_elements=n_elements)
                append_csv_row(OUTPUT_CSV, row)
                cleanup_large_files(job_name)
                n_fail += 1
                continue

        except Exception as e:
            print(f"  sim {sim_id}: PARSE ERROR - {e}")
            row = build_row(sim_id, sample, error=True, n_elements=n_elements)
            append_csv_row(OUTPUT_CSV, row)
            cleanup_large_files(job_name)
            n_fail += 1
            continue

        dt = time.time() - t0
        row = build_row(sim_id, sample, metrics=metrics)
        append_csv_row(OUTPUT_CSV, row)

        # Cleanup large files
        cleanup_large_files(job_name)

        n_success += 1

        # Print occasional detail
        if sim_id <= 5 or sim_id % 100 == 0:
            print(f"  sim {sim_id}: OK ({dt:.1f}s, {n_elements} elems, "
                  f"mises={metrics['max_mises']:.1f}, tw={metrics['tsai_wu_index']:.3f})")

    # ==========================================================================
    # Summary
    # ==========================================================================
    t_total = time.time() - t_batch_start
    print("\n" + "=" * 75)
    print("BATCH COMPLETE")
    print("=" * 75)
    print(f"  Total samples:    {total}")
    print(f"  Skipped (resume): {n_skipped}")
    print(f"  Ran this session: {n_success + n_fail}")
    print(f"  Successful:       {n_success}")
    print(f"  Failed/Error:     {n_fail}")
    print(f"  Total time:       {t_total:.1f}s ({t_total/60:.1f} min)")
    if n_success + n_fail > 0:
        print(f"  Avg per sim:      {t_total / (n_success + n_fail):.1f}s")
    print(f"  Output CSV:       {OUTPUT_CSV}")
    print("=" * 75)


if __name__ == "__main__":
    main()
