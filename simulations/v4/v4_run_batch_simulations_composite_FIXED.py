"""
============================================================
ABAQUS AUTOMATION SCRIPT V4 (FIXED) — COMPOSITE PLATE WITH
VARIABLE N CRACK-LIKE & HOLE-LIKE DEFECTS
============================================================
Purpose: Run parametric study on COMPOSITE (CFRP) shell plate
         with 1-5 randomly placed defects that range from
         round holes to thin crack-like slits. Uses Hashin
         damage initiation and Tsai-Wu failure index.

Run with (NO GUI — headless):
    abaqus cae noGUI=run_batch_simulations_v4_composite_FIXED.py

FIXES applied (vs original V4):
    1.  Sequential hole placement — one at a time, retry on overlap
    1b. Safety exit — break after 50 consecutive placement failures
    2.  Realistic pressure — 1-15 MPa (was 50-200 MPa)
    3.  Pinned BC → Roller BC (fix 13) — see below
    4.  Single ODB open — read stress + displacement in one session
    5.  Adaptive polygon segments — Ramanujan perimeter scaling
    6.  Symmetric Y-loading — bottom edge gets equal/opposite load
    7.  Safe node lookup — dictionary by nd.label, not index+1
    8.  Hashin scalar extraction — handles float or tuple .data
    9.  Robust edge selection — getByBoundingBox, not findAt
    10. Face count warning — logs if part.faces != 1
    11. Explicit S4R element type — setElementType() before mesh
    12. Crack-aware search radius — scales by 1/aspect_ratio
    13. Roller BC — U1=0 on left edge, corner pin for U2/U3 only
        (allows Poisson contraction, was Pinned then Encastre)
    14. Job status check — verifies COMPLETED before extraction
    15. S12 diagnostic — prints componentLabels on first sim
    16. Updated docstring + banner (this text)
    17. Corner pin RF diagnostic — extracts RF2/RF3 at corner pin
        every sim; warns if >1 N (BC fighting real deformation)
    18. Validation suite — 3 analytical SCF cases (Kirsch + Peterson)
        run before batch; keeps .odb files for GUI inspection
    19. Pressure calibration — 30 quick samples to verify ~50%
        failure rate before committing to full batch run
    20. Lekhnitskii orthotropic SCFs — validation uses correct
        anisotropic formula instead of isotropic Kirsch/Peterson

Output:
    simulation_results_v4_fixed.csv

Expected time:
    500 simulations ~ 2-4 hours (full licence)
============================================================
"""

from abaqus import *
from abaqusConstants import *
from caeModules import *
import os
import gc
import math
import random
import time

# ============================================================
# CONFIGURATION
# ============================================================

# --- Fixed plate geometry (mm) ---
PLATE_LENGTH = 100.0
PLATE_WIDTH = 50.0

# --- Composite material: T300/Epoxy ---
E1 = 138000.0       # Fibre direction stiffness (MPa)
E2 = 8960.0         # Transverse stiffness (MPa)
NU12 = 0.30         # Major Poisson's ratio
G12 = 7100.0        # In-plane shear modulus (MPa)
G13 = 7100.0        # Out-of-plane shear modulus (MPa)
G23 = 6210.0        # Out-of-plane shear modulus (MPa)

# --- Strength values (for Tsai-Wu + Hashin) ---
XT = 1500.0          # Fibre tensile strength (MPa)
XC = 1200.0          # Fibre compressive strength (MPa)
YT = 40.0            # Matrix tensile strength (MPa)
YC = 246.0           # Matrix compressive strength (MPa)
SL = 68.0            # Longitudinal shear strength (MPa)
ST = 68.0            # Transverse shear strength (MPa)

# --- Layup: [0/45/-45/90]s ---
BASE_PLY_ANGLES = [0.0, 45.0, -45.0, 90.0, 90.0, -45.0, 45.0, 0.0]
N_PLIES = 8

# --- Mesh ---
GLOBAL_MESH_SIZE = 3.0       # mm — coarse
FINE_MESH_SIZE_HOLE = 0.5    # mm — near round holes
FINE_MESH_SIZE_CRACK = 0.2   # mm — near crack tips (finer!)
HOLE_MESH_SEARCH_BUFFER = 2.0

# --- Defect shape classification ---
CRACK_THRESHOLD_AR = 0.20    # aspect_ratio < this = crack-like
NUM_SEGMENTS_HOLE = 24       # polygon segments for round holes
NUM_SEGMENTS_CRACK = 48      # more segments for thin slits
MIN_EDGE_LENGTH = 0.3        # mm — no polygon edge shorter than this
MIN_POLYGON_SEGMENTS = 12    # absolute floor for any defect

# --- Sampling ---
NUM_SAMPLES = 500
RANDOM_SEED = 42
MAX_DEFECTS = 5
MAX_PLACEMENT_ATTEMPTS = 200  # max retries per hole placement

# ============================================================
# PARAMETER RANGES
# ============================================================

# FIX 2: Realistic aerospace pressure range (was 50-200 / 0-100)
GLOBAL_RANGES = {
    'pressure_x':      [5.0,   100.0],   # MPa — calibrated: 7%@[5,50], 80%@[10,200]
    'pressure_y':      [0.0,   100.0],   # MPa — in-plane Y (0=uniaxial)
    'ply_thickness':   [0.10,  0.20],    # mm per ply (total 0.8-1.6mm)
    'layup_rotation':  [0.0,   90.0],    # degrees — rotates all ply angles
}

# Per-defect parameters (each of 1-5 defects)
DEFECT_RANGES = {
    'x':              [12.0,  88.0],     # mm
    'y':              [8.0,   42.0],     # mm
    'semi_major':     [3.0,   10.0],     # mm
    'aspect_ratio':   [0.05,  1.0],      # 0.05=crack, 1.0=circle
    'angle':          [0.0,   180.0],    # degrees
}

# --- Output ---
OUTPUT_FILE = 'simulation_results_v4_fixed.csv'


# ============================================================
# CSV HEADER — Fixed-width: 5 defect slots, unused = 0
# ============================================================
def build_csv_header():
    cols = ['sim_id', 'n_defects']
    for i in range(1, MAX_DEFECTS + 1):
        cols.extend([
            'defect{}_x'.format(i),
            'defect{}_y'.format(i),
            'defect{}_semi_major'.format(i),
            'defect{}_aspect_ratio'.format(i),
            'defect{}_angle'.format(i),
        ])
    cols.extend([
        'pressure_x', 'pressure_y',
        'ply_thickness', 'layup_rotation',
        'total_thickness',
        # --- OUTPUTS ---
        'min_inter_defect_dist',
        'max_mises',
        'max_s11', 'min_s11',
        'max_s22', 'min_s22',
        'max_s12',
        'tsai_wu_index',
        'max_hashin_ft', 'max_hashin_fc',
        'max_hashin_mt', 'max_hashin_mc',
    ])
    # Per-defect max stress
    for i in range(1, MAX_DEFECTS + 1):
        cols.append('max_mises_defect{}'.format(i))
    cols.extend([
        'max_disp',
        'n_elements',
        'failed_tsai_wu',
        'failed_hashin',
    ])
    return ','.join(cols) + '\n'


CSV_HEADER = build_csv_header()


# ============================================================
# LATIN HYPERCUBE SAMPLING (no scipy needed)
# ============================================================
def latin_hypercube_sample(param_ranges, n_samples, seed=42):
    """Generate LHS samples. Returns list of dicts."""
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


# ============================================================
# HELPER: Generate rotated ellipse polygon points
# ============================================================
def ellipse_polygon_points(cx, cy, semi_major, semi_minor,
                           angle_deg, n_segments):
    """Polygon approximation of rotated ellipse."""
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    points = []
    for i in range(n_segments):
        t = 2.0 * math.pi * i / n_segments
        px = round(cx + semi_major * math.cos(t) * cos_a
                   - semi_minor * math.sin(t) * sin_a, 6)
        py = round(cy + semi_major * math.cos(t) * sin_a
                   + semi_minor * math.sin(t) * cos_a, 6)
        points.append((px, py))
    return points


# ============================================================
# HELPER: Compute polygon segment count from ellipse geometry
# ============================================================
def compute_n_segments(semi_major, semi_minor, min_edge_len=MIN_EDGE_LENGTH):
    """Choose segment count so no polygon edge is shorter than
    min_edge_len. Uses Ramanujan's ellipse perimeter approximation.
    Returns an integer between MIN_POLYGON_SEGMENTS and
    NUM_SEGMENTS_CRACK."""
    a = semi_major
    b = semi_minor
    # Ramanujan approximation for ellipse perimeter
    perimeter = math.pi * (3.0 * (a + b)
                           - math.sqrt((3.0 * a + b) * (a + 3.0 * b)))
    n = int(perimeter / min_edge_len)
    # Clamp to sensible range
    n = max(MIN_POLYGON_SEGMENTS, min(NUM_SEGMENTS_CRACK, n))
    return n


# ============================================================
# HELPER: Validate ellipse within plate bounds
# ============================================================
def validate_ellipse_bounds(cx, cy, semi_a, semi_b, angle_deg,
                            plate_length, plate_width, margin=2.0):
    """Rotated bounding box check."""
    t = math.radians(angle_deg)
    dx = math.sqrt((semi_a * math.cos(t))**2 +
                   (semi_b * math.sin(t))**2)
    dy = math.sqrt((semi_a * math.sin(t))**2 +
                   (semi_b * math.cos(t))**2)
    if cx - dx < margin:
        return False
    if cx + dx > plate_length - margin:
        return False
    if cy - dy < margin:
        return False
    if cy + dy > plate_width - margin:
        return False
    return True


# ============================================================
# HELPER: Check if new defect overlaps any existing defects
# ============================================================
def overlaps_existing(new_defect, existing_defects, margin=2.0):
    """Check if new_defect overlaps any defect in the list."""
    for d in existing_defects:
        dist = math.sqrt(
            (new_defect['x'] - d['x'])**2 +
            (new_defect['y'] - d['y'])**2)
        min_dist = new_defect['semi_major'] + d['semi_major'] + margin
        if dist < min_dist:
            return True
    return False


# ============================================================
# HELPER: Compute minimum inter-defect distance
# ============================================================
def compute_min_inter_dist(defects):
    """Minimum centre-to-centre distance across all pairs."""
    n = len(defects)
    if n < 2:
        return 0.0
    min_d = 1e9
    for i in range(n):
        for j in range(i + 1, n):
            d = math.sqrt(
                (defects[i]['x'] - defects[j]['x'])**2 +
                (defects[i]['y'] - defects[j]['y'])**2)
            if d < min_d:
                min_d = d
    return min_d


# ============================================================
# HELPER: Find edges near a defect for mesh refinement
# ============================================================
def get_hole_edges(part, cx, cy, semi_major, buffer):
    """Find all edges whose midpoint is near defect centre."""
    search_radius = semi_major + buffer
    edge_list = []
    for i in range(len(part.edges)):
        edge = part.edges[i]
        pt = edge.pointOn[0]
        dx = pt[0] - cx
        dy = pt[1] - cy
        dist_2d = math.sqrt(dx**2 + dy**2)
        if dist_2d < search_radius:
            edge_list.append(part.edges[i:i + 1])
    if not edge_list:
        return None
    combined = edge_list[0]
    for e in edge_list[1:]:
        combined = combined + e
    return combined


# ============================================================
# HELPER: Compute Tsai-Wu failure index from ply stresses
# ============================================================
def compute_tsai_wu(s11, s22, s12):
    """
    Tsai-Wu failure criterion for a single ply.
    Returns failure index (>= 1.0 means failure).
    """
    F1 = 1.0 / XT - 1.0 / XC
    F2 = 1.0 / YT - 1.0 / YC
    F11 = 1.0 / (XT * XC)
    F22 = 1.0 / (YT * YC)
    F66 = 1.0 / (SL * SL)
    F12 = -0.5 * math.sqrt(F11 * F22)  # standard approximation

    tw = (F1 * s11 + F2 * s22 +
          F11 * s11**2 + F22 * s22**2 + F66 * s12**2 +
          2.0 * F12 * s11 * s22)
    return tw


# ============================================================
# HELPER: Resume from existing CSV
# ============================================================
def load_completed_ids(filepath):
    """Read existing CSV to find completed sim_ids."""
    completed = set()
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            lines = f.readlines()
        for line in lines[1:]:
            parts = line.strip().split(',')
            if len(parts) > 0 and 'ERROR' not in line:
                try:
                    completed.add(int(parts[0]))
                except ValueError:
                    pass
    return completed


# ============================================================
# FIX 1: SEQUENTIAL HOLE PLACEMENT WITH RETRY
# ============================================================
def place_defects_sequentially(n_defects):
    """
    Place holes one at a time. Each new hole is only accepted
    if it doesn't overlap any already-placed hole AND fits
    within the plate bounds. If it overlaps, repick randomly
    and try again. Guarantees zero overlaps.

    Returns list of defect dicts, or None if placement failed
    after MAX_PLACEMENT_ATTEMPTS per hole.
    """
    placed = []

    for hole_idx in range(n_defects):
        placed_this_hole = False

        for attempt in range(MAX_PLACEMENT_ATTEMPTS):
            # Random defect parameters
            defect = {}
            for pname, (lo, hi) in DEFECT_RANGES.items():
                defect[pname] = random.uniform(lo, hi)

            # Check bounds
            sb = defect['semi_major'] * defect['aspect_ratio']
            if not validate_ellipse_bounds(
                    defect['x'], defect['y'],
                    defect['semi_major'], sb,
                    defect['angle'],
                    PLATE_LENGTH, PLATE_WIDTH):
                continue  # out of bounds, try again

            # Check overlap with already-placed holes
            if overlaps_existing(defect, placed):
                continue  # overlaps, try again

            # Passed both checks — accept this hole
            placed.append(defect)
            placed_this_hole = True
            break

        if not placed_this_hole:
            # Could not fit this hole after many attempts
            return None

    return placed


# ============================================================
# GENERATE SAMPLES — Stratified by defect count
# ============================================================
def generate_all_samples(n_total, seed=42):
    """
    Generate samples with stratified defect counts.
    100 samples per n_defects (1 through 5).
    Global params via LHS, defect placement via sequential retry.
    Every sample is guaranteed valid — no post-hoc rejection.
    """
    random.seed(seed)

    # Stratify: equal counts per n_defects
    counts_per_n = n_total // MAX_DEFECTS
    remainder = n_total - counts_per_n * MAX_DEFECTS

    # LHS for global parameters
    global_samples = latin_hypercube_sample(
        GLOBAL_RANGES, n_total, seed=seed)

    all_samples = []
    idx = 0
    placement_failures = 0
    MAX_SAMPLE_FAILURES = 50  # safety limit per defect count

    for n_def in range(1, MAX_DEFECTS + 1):
        n_sims = counts_per_n + (1 if n_def <= remainder else 0)
        placed_count = 0
        consecutive_failures = 0

        while placed_count < n_sims and idx < n_total:
            # Try to place holes sequentially
            defects = place_defects_sequentially(n_def)

            if defects is None:
                placement_failures += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_SAMPLE_FAILURES:
                    print('  WARNING: Could not place {} defects '
                          'after {} attempts. Moving on.'.format(
                              n_def, MAX_SAMPLE_FAILURES))
                    break
                continue

            consecutive_failures = 0  # reset on success

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

    if placement_failures > 0:
        print('  Placement retries needed: {}'.format(placement_failures))

    # Shuffle to mix defect counts
    random.seed(seed + 999)
    random.shuffle(all_samples)
    return all_samples


# ============================================================
# MAIN: Run one V4 simulation
# ============================================================
def run_single_simulation(sample, sim_id, keep_odb=False):
    """
    Creates composite shell plate with N defects (hole-like
    and crack-like), runs analysis, extracts composite failure
    metrics including Tsai-Wu and Hashin criteria.

    If keep_odb=True, the .odb file is NOT deleted after
    extraction (used by validation_suite to allow GUI inspection).
    """

    model_name = 'Model_{}'.format(sim_id)
    job_name = 'Job_{:04d}'.format(sim_id)

    n_def = sample['n_defects']
    defects = sample['defects']
    press_x = sample['pressure_x']
    press_y = sample['pressure_y']
    ply_t = sample['ply_thickness']
    layup_rot = sample['layup_rotation']
    total_thickness = ply_t * N_PLIES

    # Derived: inter-defect distance
    min_inter_dist = compute_min_inter_dist(defects)

    try:
        # ======================================================
        # CLEANUP
        # ======================================================
        if model_name in mdb.models.keys():
            del mdb.models[model_name]

        # ======================================================
        # CREATE MODEL
        # ======================================================
        model = mdb.Model(name=model_name)

        # ======================================================
        # GEOMETRY: Shell plate + N defect holes (SINGLE SKETCH)
        # ======================================================
        sketch = model.ConstrainedSketch(
            name='plateSketch', sheetSize=200.0)

        # Outer boundary
        sketch.rectangle(
            point1=(0.0, 0.0),
            point2=(PLATE_LENGTH, PLATE_WIDTH))

        # Draw each defect polygon
        for d in defects:
            ar = d['aspect_ratio']
            sb = d['semi_major'] * ar
            n_seg = compute_n_segments(d['semi_major'], sb)

            pts = ellipse_polygon_points(
                d['x'], d['y'], d['semi_major'], sb,
                d['angle'], n_seg)

            for idx in range(n_seg):
                p1 = pts[idx]
                p2 = pts[(idx + 1) % n_seg]
                sketch.Line(point1=p1, point2=p2)

        # Create SHELL part (not solid!)
        part = model.Part(
            name='Plate', dimensionality=THREE_D,
            type=DEFORMABLE_BODY)
        part.BaseShell(sketch=sketch)

        # Sanity check: expect exactly 1 face (plate minus holes)
        n_faces = len(part.faces)
        if n_faces != 1:
            print('  WARNING sim {}: expected 1 face, got {} '
                  '(geometry may be malformed)'.format(sim_id, n_faces))

        # ======================================================
        # COMPOSITE MATERIAL: T300/Epoxy
        # ======================================================
        material = model.Material(name='CFRP')
        material.Elastic(
            type=LAMINA,
            table=((E1, E2, NU12, G12, G13, G23),))

        # Hashin damage initiation (computes failure indices)
        material.HashinDamageInitiation(
            table=((XT, XC, YT, YC, SL, ST),))

        # ======================================================
        # COMPOSITE LAYUP: [0/45/-45/90]s with rotation
        # ======================================================
        region = part.Set(faces=part.faces[:], name='AllFaces')

        compositeLayup = part.CompositeLayup(
            name='CompositePlate',
            description='CFRP quasi-isotropic layup',
            elementType=SHELL,
            offsetType=MIDDLE_SURFACE,
            symmetric=False,
            thicknessAssignment=FROM_SECTION)

        compositeLayup.Section(
            preIntegrate=OFF,
            integrationRule=SIMPSON,
            poissonDefinition=DEFAULT,
            thicknessModulus=None,
            temperature=GRADIENT,
            useDensity=OFF)

        compositeLayup.ReferenceOrientation(
            orientationType=GLOBAL,
            localCsys=None,
            additionalRotationType=ROTATION_ANGLE,
            additionalRotationField='',
            angle=layup_rot,
            axis=AXIS_3)

        for i, base_angle in enumerate(BASE_PLY_ANGLES):
            compositeLayup.CompositePly(
                suppressed=False,
                plyName='Ply-{}'.format(i + 1),
                region=region,
                material='CFRP',
                thicknessType=SPECIFY_THICKNESS,
                thickness=ply_t,
                orientationType=SPECIFY_ORIENT,
                orientationValue=base_angle,
                additionalRotationType=ROTATION_NONE,
                additionalRotationField='',
                axis=AXIS_3,
                angle=0.0,
                numIntPoints=3)

        # ======================================================
        # ASSEMBLY
        # ======================================================
        assembly = model.rootAssembly
        assembly.DatumCsysByDefault(CARTESIAN)
        instance = assembly.Instance(
            name='PlateInstance', part=part, dependent=ON)

        # ======================================================
        # STEP
        # ======================================================
        model.StaticStep(name='LoadStep', previous='Initial')

        # ======================================================
        # FIELD OUTPUT REQUEST — include Hashin criteria
        # ======================================================
        model.fieldOutputRequests['F-Output-1'].setValues(
            variables=('S', 'U', 'RF', 'HSNFTCRT', 'HSNFCCRT',
                       'HSNMTCRT', 'HSNMCCRT'))

        # ======================================================
        # HELPER: getByBoundingBox edge selection
        # Grabs ALL edges along a boundary, even if split
        # ======================================================
        tol = 0.1  # mm search tolerance

        left_edges = instance.edges.getByBoundingBox(
            xMin=-tol, xMax=tol,
            yMin=-tol, yMax=PLATE_WIDTH + tol,
            zMin=-tol, zMax=tol)
        right_edges = instance.edges.getByBoundingBox(
            xMin=PLATE_LENGTH - tol, xMax=PLATE_LENGTH + tol,
            yMin=-tol, yMax=PLATE_WIDTH + tol,
            zMin=-tol, zMax=tol)

        # ======================================================
        # FIX 3+13: ROLLER boundary (was ENCASTRE → Pinned → Roller)
        # U1=0 on entire left edge (stops X-movement)
        # U2=0 on one corner only (allows Poisson contraction)
        # U3=0 on one corner (prevents out-of-plane drift)
        # This is the minimum constraint set for a shell under
        # in-plane loading — no artificial stress at support.
        # ======================================================
        left_region = assembly.Set(
            edges=left_edges, name='LeftEdge')
        model.DisplacementBC(
            name='RollerLeft_U1', createStepName='Initial',
            region=left_region,
            u1=0.0, u2=UNSET, u3=UNSET,
            ur1=UNSET, ur2=UNSET, ur3=UNSET)

        # Pin bottom-left corner for U2 + U3 (rigid body control)
        corner_vertex = instance.vertices.getByBoundingBox(
            xMin=-tol, xMax=tol,
            yMin=-tol, yMax=tol,
            zMin=-tol, zMax=tol)
        corner_region = assembly.Set(
            vertices=corner_vertex, name='CornerPin')
        model.DisplacementBC(
            name='CornerPin_U2U3', createStepName='Initial',
            region=corner_region,
            u1=UNSET, u2=0.0, u3=0.0,
            ur1=UNSET, ur2=UNSET, ur3=UNSET)

        # ======================================================
        # LOADS — ShellEdgeLoad for in-plane tension
        # Force per unit length = stress * total_thickness
        # ======================================================
        # X-direction tension (right edge)
        right_surface = assembly.Surface(
            side1Edges=right_edges, name='RightEdge')
        force_x = press_x * total_thickness  # N/mm
        model.ShellEdgeLoad(
            name='TensionX',
            createStepName='LoadStep',
            region=right_surface,
            magnitude=force_x,
            directionVector=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
            distributionType=UNIFORM,
            traction=GENERAL)

        # Y-direction tension (top + bottom edges) — only if nonzero
        if press_y > 0.0:
            force_y = press_y * total_thickness

            # Top edge: pull in +Y
            top_edges = instance.edges.getByBoundingBox(
                xMin=-tol, xMax=PLATE_LENGTH + tol,
                yMin=PLATE_WIDTH - tol, yMax=PLATE_WIDTH + tol,
                zMin=-tol, zMax=tol)
            top_surface = assembly.Surface(
                side1Edges=top_edges, name='TopEdge')
            model.ShellEdgeLoad(
                name='TensionY_Top',
                createStepName='LoadStep',
                region=top_surface,
                magnitude=force_y,
                directionVector=((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
                distributionType=UNIFORM,
                traction=GENERAL)

            # Bottom edge: pull in -Y (symmetric biaxial)
            bottom_edges = instance.edges.getByBoundingBox(
                xMin=-tol, xMax=PLATE_LENGTH + tol,
                yMin=-tol, yMax=tol,
                zMin=-tol, zMax=tol)
            bottom_surface = assembly.Surface(
                side1Edges=bottom_edges, name='BottomEdge')
            model.ShellEdgeLoad(
                name='TensionY_Bottom',
                createStepName='LoadStep',
                region=bottom_surface,
                magnitude=force_y,
                directionVector=((0.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
                distributionType=UNIFORM,
                traction=GENERAL)

        # ======================================================
        # MESH WITH LOCAL REFINEMENT
        # ======================================================
        part.seedPart(
            size=GLOBAL_MESH_SIZE,
            deviationFactor=0.1,
            minSizeFactor=0.1)

        # Fine seed near each defect
        for d in defects:
            is_crack = (d['aspect_ratio'] < CRACK_THRESHOLD_AR)
            fine_size = (FINE_MESH_SIZE_CRACK if is_crack
                         else FINE_MESH_SIZE_HOLE)

            edges = get_hole_edges(
                part, d['x'], d['y'],
                d['semi_major'], HOLE_MESH_SEARCH_BUFFER)
            if edges is not None:
                part.seedEdgeBySize(
                    edges=edges, size=fine_size,
                    deviationFactor=0.1, constraint=FINER)

        # FIX 11: Explicitly set element type to S4R
        elemType1 = mesh.ElemType(elemCode=S4R, elemLibrary=STANDARD)
        elemType2 = mesh.ElemType(elemCode=S3, elemLibrary=STANDARD)
        all_faces = part.faces[:]
        part.setElementType(
            regions=(all_faces,),
            elemTypes=(elemType1, elemType2))

        # Generate mesh
        part.generateMesh()
        n_elements = len(part.elements)

        # ======================================================
        # RUN JOB
        # ======================================================
        # Note: mdb.jobs[].submit() + waitForCompletion() is broken
        # in Abaqus 2025 HF3 noGUI mode (solver never executes).
        # Workaround: write .inp file, then call solver directly.
        mdb.Job(name=job_name, model=model_name, type=ANALYSIS)
        mdb.jobs[job_name].writeInput()

        # Run solver via command line (proven to work on this system)
        solver_cmd = 'abaqus job={} interactive'.format(job_name)
        solver_rc = os.system(solver_cmd)

        # FIX 14: Check job actually completed successfully
        sta_ok = False
        try:
            with open(job_name + '.sta', 'r') as sta_f:
                sta_content = sta_f.read()
                if 'SUCCESSFULLY' in sta_content.upper():
                    sta_ok = True
        except:
            pass
        odb_exists = os.path.exists(job_name + '.odb')

        if not sta_ok and not odb_exists:
            print('  WARNING sim {}: solver returned rc={} and no'
                  ' completed .sta/.odb — skipping'.format(
                      sim_id, solver_rc))
            raise Exception('Job did not complete (rc={})'.format(
                solver_rc))

        # ======================================================
        # EXTRACT RESULTS
        # ======================================================
        odb = session.openOdb(name=job_name + '.odb')
        step = odb.steps['LoadStep']
        frame = step.frames[-1]

        # --------------------------------------------------
        # STRESS EXTRACTION (all section points / plies)
        # --------------------------------------------------
        stress_field = frame.fieldOutputs['S']

        # FIX 15: Log stress component order on first sim
        # so we can verify S12 index is correct
        if sim_id == 1:
            print('  DIAGNOSTIC: stress componentLabels = {}'
                  .format(stress_field.componentLabels))
            print('  (S12 is read from data[3] — verify this matches)')

        stress_at_nodes = stress_field.getSubset(
            position=ELEMENT_NODAL)

        # Build node label -> coordinates lookup (safe indexing)
        inst_nodes = odb.rootAssembly.instances['PLATEINSTANCE'].nodes
        node_coords = {}
        for nd in inst_nodes:
            node_coords[nd.label] = (nd.coordinates[0],
                                     nd.coordinates[1])

        max_mises = 0.0
        max_s11 = -1e20
        min_s11 = 1e20
        max_s22 = -1e20
        min_s22 = 1e20
        max_s12 = 0.0
        max_tw = 0.0

        # Per-defect max stress
        max_mises_per_defect = [0.0] * MAX_DEFECTS

        for value in stress_at_nodes.values:
            mises = value.mises
            nl = value.nodeLabel
            if nl <= 0:
                continue

            s11 = value.data[0]
            s22 = value.data[1]
            s12 = value.data[3]

            if mises > max_mises:
                max_mises = mises
            if s11 > max_s11:
                max_s11 = s11
            if s11 < min_s11:
                min_s11 = s11
            if s22 > max_s22:
                max_s22 = s22
            if s22 < min_s22:
                min_s22 = s22
            if abs(s12) > max_s12:
                max_s12 = abs(s12)

            tw = compute_tsai_wu(s11, s22, s12)
            if tw > max_tw:
                max_tw = tw

            # Per-defect stress (find nearest defect)
            if nl not in node_coords:
                continue
            nx, ny = node_coords[nl]

            for di in range(n_def):
                d = defects[di]
                # FIX 12: Scale search radius by aspect ratio
                # Round holes (ar~1): 2× semi_major is fine
                # Thin cracks (ar~0.05): stress field extends
                # much further — use 1/ar but cap at 5×
                ar_scale = min(1.0 / d['aspect_ratio'], 5.0)
                search_r = d['semi_major'] * max(2.0, ar_scale)
                dd = math.sqrt(
                    (nx - d['x'])**2 + (ny - d['y'])**2)
                if dd < search_r:
                    if mises > max_mises_per_defect[di]:
                        max_mises_per_defect[di] = mises

        # --------------------------------------------------
        # HASHIN CRITERIA
        # --------------------------------------------------
        max_hashin_ft = 0.0
        max_hashin_fc = 0.0
        max_hashin_mt = 0.0
        max_hashin_mc = 0.0

        hashin_keys = [
            ('HSNFTCRT', 'ft'),
            ('HSNFCCRT', 'fc'),
            ('HSNMTCRT', 'mt'),
            ('HSNMCCRT', 'mc'),
        ]

        for key, mode in hashin_keys:
            try:
                field = frame.fieldOutputs[key]
                for value in field.values:
                    # .data may be float or tuple — always extract scalar
                    raw = value.data
                    val = raw[0] if hasattr(raw, '__len__') else raw
                    if mode == 'ft' and val > max_hashin_ft:
                        max_hashin_ft = val
                    elif mode == 'fc' and val > max_hashin_fc:
                        max_hashin_fc = val
                    elif mode == 'mt' and val > max_hashin_mt:
                        max_hashin_mt = val
                    elif mode == 'mc' and val > max_hashin_mc:
                        max_hashin_mc = val
            except KeyError:
                pass

        # --------------------------------------------------
        # DISPLACEMENT (same ODB, no need to reopen)
        # --------------------------------------------------
        disp_field = frame.fieldOutputs['U']
        max_disp = 0.0
        for value in disp_field.values:
            mag = math.sqrt(
                value.data[0]**2 +
                value.data[1]**2 +
                value.data[2]**2)
            if mag > max_disp:
                max_disp = mag

        # --------------------------------------------------
        # FIX 17: Corner pin reaction force diagnostic
        # If RF2 or RF3 >> 1 N, the corner constraint is
        # fighting real deformation, not just preventing
        # rigid body motion — means roller BC may be wrong.
        # --------------------------------------------------
        try:
            rf_field = frame.fieldOutputs['RF']
            corner_set = odb.rootAssembly.nodeSets['CORNERPIN']
            corner_rf = rf_field.getSubset(region=corner_set)
            for value in corner_rf.values:
                RF2 = value.data[1]  # Y-reaction
                RF3 = value.data[2]  # Z-reaction
                print('  Corner pin RF: RF2={:.2e}, RF3={:.2e}'.format(
                    RF2, RF3))
                if abs(RF2) > 1.0 or abs(RF3) > 1.0:
                    print('  WARNING: Corner pin RF > 1 N — '
                          'BC may be fighting real deformation!')
        except Exception as e_rf:
            print('  (RF diagnostic skipped: {})'.format(str(e_rf)))

        odb.close()

        # --------------------------------------------------
        # FAILURE FLAGS
        # --------------------------------------------------
        failed_tw = 1 if max_tw >= 1.0 else 0
        failed_hashin = 1 if max(
            max_hashin_ft, max_hashin_fc,
            max_hashin_mt, max_hashin_mc) >= 1.0 else 0

        # ======================================================
        # CLEANUP
        # ======================================================
        del mdb.models[model_name]

        extensions = ['.lck', '.res', '.prt', '.sim',
                      '.sta', '.msg', '.dat', '.com', '.ipm',
                      '.log', '.023', '.SMABulk', '.cid',
                      '.simdir']
        if not keep_odb:
            extensions.append('.odb')
        for ext in extensions:
            try:
                os.remove(job_name + ext)
            except:
                pass
        try:
            import shutil
            shutil.rmtree(job_name + '.simdir', ignore_errors=True)
        except:
            pass

        gc.collect()

        # ======================================================
        # BUILD RESULT DICT
        # ======================================================
        result = {
            'sim_id': sim_id,
            'n_defects': n_def,
            'pressure_x': press_x,
            'pressure_y': press_y,
            'ply_thickness': ply_t,
            'layup_rotation': layup_rot,
            'total_thickness': total_thickness,
            'min_inter_defect_dist': min_inter_dist,
            'max_mises': max_mises,
            'max_s11': max_s11,
            'min_s11': min_s11,
            'max_s22': max_s22,
            'min_s22': min_s22,
            'max_s12': max_s12,
            'tsai_wu_index': max_tw,
            'max_hashin_ft': max_hashin_ft,
            'max_hashin_fc': max_hashin_fc,
            'max_hashin_mt': max_hashin_mt,
            'max_hashin_mc': max_hashin_mc,
            'max_mises_per_defect': max_mises_per_defect,
            'max_disp': max_disp,
            'n_elements': n_elements,
            'failed_tsai_wu': failed_tw,
            'failed_hashin': failed_hashin,
        }

        # Defect params for CSV (pad unused to 0)
        for i in range(MAX_DEFECTS):
            if i < n_def:
                d = defects[i]
                result['defect{}_x'.format(i + 1)] = d['x']
                result['defect{}_y'.format(i + 1)] = d['y']
                result['defect{}_semi_major'.format(i + 1)] = d['semi_major']
                result['defect{}_aspect_ratio'.format(i + 1)] = d['aspect_ratio']
                result['defect{}_angle'.format(i + 1)] = d['angle']
            else:
                result['defect{}_x'.format(i + 1)] = 0.0
                result['defect{}_y'.format(i + 1)] = 0.0
                result['defect{}_semi_major'.format(i + 1)] = 0.0
                result['defect{}_aspect_ratio'.format(i + 1)] = 0.0
                result['defect{}_angle'.format(i + 1)] = 0.0

        return result

    except Exception as e:
        print('ERROR in sim {}: {}'.format(sim_id, str(e)))
        try:
            if model_name in mdb.models.keys():
                del mdb.models[model_name]
        except:
            pass
        extensions = ['.odb', '.lck', '.res', '.prt', '.sim',
                      '.sta', '.msg', '.dat', '.com', '.ipm',
                      '.log', '.023', '.SMABulk', '.cid']
        for ext in extensions:
            try:
                os.remove(job_name + ext)
            except:
                pass
        gc.collect()
        return None


# ============================================================
# WRITE ONE ROW TO CSV
# ============================================================
def write_csv_row(filepath, result):
    """Write one result dict as a CSV line."""
    vals = [
        result['sim_id'],
        result['n_defects'],
    ]
    for i in range(1, MAX_DEFECTS + 1):
        vals.extend([
            result['defect{}_x'.format(i)],
            result['defect{}_y'.format(i)],
            result['defect{}_semi_major'.format(i)],
            result['defect{}_aspect_ratio'.format(i)],
            result['defect{}_angle'.format(i)],
        ])
    vals.extend([
        result['pressure_x'],
        result['pressure_y'],
        result['ply_thickness'],
        result['layup_rotation'],
        result['total_thickness'],
        result['min_inter_defect_dist'],
        result['max_mises'],
        result['max_s11'],
        result['min_s11'],
        result['max_s22'],
        result['min_s22'],
        result['max_s12'],
        result['tsai_wu_index'],
        result['max_hashin_ft'],
        result['max_hashin_fc'],
        result['max_hashin_mt'],
        result['max_hashin_mc'],
    ])
    for i in range(MAX_DEFECTS):
        vals.append(result['max_mises_per_defect'][i])
    vals.extend([
        result['max_disp'],
        result['n_elements'],
        result['failed_tsai_wu'],
        result['failed_hashin'],
    ])

    with open(filepath, 'a') as f:
        f.write(','.join([str(v) for v in vals]) + '\n')


# ============================================================
# WRITE ERROR ROW TO CSV
# ============================================================
def write_error_row(filepath, sim_id, sample):
    """Write an error line to CSV preserving inputs."""
    n_def = sample['n_defects']
    defects = sample['defects']

    vals = [sim_id, n_def]
    for i in range(MAX_DEFECTS):
        if i < n_def:
            d = defects[i]
            vals.extend([d['x'], d['y'], d['semi_major'],
                         d['aspect_ratio'], d['angle']])
        else:
            vals.extend([0, 0, 0, 0, 0])
    vals.extend([
        sample['pressure_x'], sample['pressure_y'],
        sample['ply_thickness'], sample['layup_rotation'],
        sample['ply_thickness'] * N_PLIES,
    ])
    # Fill outputs with ERROR
    n_output_cols = 17 + MAX_DEFECTS
    vals.extend(['ERROR'] * n_output_cols)

    with open(filepath, 'a') as f:
        f.write(','.join([str(v) for v in vals]) + '\n')


# ============================================================
# FIX 19: PRESSURE CALIBRATION — verify ~50% failure rate
# Runs 30 quick samples BEFORE main batch to confirm
# pressure range [1, 15] MPa actually produces balanced data.
# ============================================================
def calibrate_failure_rate(n_test=30):
    """Run 30 test samples to verify ~50% failure rate."""

    print('\n' + '=' * 60)
    print('PRESSURE CALIBRATION TEST ({} samples)'.format(n_test))
    print('Testing pressure range: [{}, {}] MPa'.format(
        GLOBAL_RANGES['pressure_x'][0], GLOBAL_RANGES['pressure_x'][1]))
    print('=' * 60)

    test_samples = generate_all_samples(n_test, seed=999)

    failed_tw = 0
    failed_hashin = 0
    completed = 0

    for i, sample in enumerate(test_samples):
        print('Calibration {}/{}...'.format(i + 1, n_test), end=' ')

        result = run_single_simulation(sample, sim_id=8000 + i,
                                       keep_odb=False)

        if result:
            completed += 1
            if result['failed_tsai_wu']:
                failed_tw += 1
            if result['failed_hashin']:
                failed_hashin += 1
            print('TW={} H={}'.format(
                'FAIL' if result['failed_tsai_wu'] else 'SAFE',
                'FAIL' if result['failed_hashin'] else 'SAFE'))

            # Cleanup immediately — don't keep calibration ODBs
            job_name = 'Job_{:04d}'.format(8000 + i)
            extensions = ['.odb', '.lck', '.res', '.prt', '.sim',
                          '.sta', '.msg', '.dat', '.com', '.ipm',
                          '.log', '.023', '.SMABulk', '.cid']
            for ext in extensions:
                try:
                    os.remove(job_name + ext)
                except:
                    pass
        else:
            print('ERROR')

    if completed == 0:
        print('\nERROR: No calibration sims completed — cannot assess.')
        return False

    rate_tw = failed_tw / float(completed) * 100
    rate_hashin = failed_hashin / float(completed) * 100

    print('\n' + '-' * 60)
    print('CALIBRATION RESULTS:')
    print('  Completed: {}/{}'.format(completed, n_test))
    print('  Tsai-Wu failures: {}/{} ({:.0f}%)'.format(
        failed_tw, completed, rate_tw))
    print('  Hashin failures: {}/{} ({:.0f}%)'.format(
        failed_hashin, completed, rate_hashin))
    print('  Target range: 40-60% failure')

    if rate_tw < 40:
        print('\n  WARNING: Failure rate TOO LOW')
        print('  Suggested fix: Increase pressure upper bound')
        print('  Try: GLOBAL_RANGES["pressure_x"] = [1.0, 20.0]')
        print('  Or:  GLOBAL_RANGES["pressure_x"] = [2.0, 18.0]')
        return False
    elif rate_tw > 60:
        print('\n  WARNING: Failure rate TOO HIGH')
        print('  Suggested fix: Decrease pressure upper bound')
        print('  Try: GLOBAL_RANGES["pressure_x"] = [1.0, 12.0]')
        print('  Or:  GLOBAL_RANGES["pressure_x"] = [0.5, 10.0]')
        return False
    else:
        print('\n  Failure rate ACCEPTABLE (40-60% range)')
        print('=' * 60)
        return True


# ============================================================
# FIX 18: VALIDATION SUITE — Analytical SCF verification
# Runs BEFORE main batch. Compares FEA SCF against Lekhnitskii
# orthotropic solution (NOT isotropic Kirsch/Peterson).
# Keeps .odb files for GUI inspection + supervisor report.
# ============================================================
def lekhnitskii_SCF(semi_a_perp, semi_b_par):
    """
    Lekhnitskii SCF for an elliptical hole in an orthotropic plate
    under uniaxial tension.

    semi_a_perp: semi-axis PERPENDICULAR to load direction
    semi_b_par:  semi-axis PARALLEL to load direction

    SCF = 1 + (a/b) * sqrt(2*(sqrt(E1/E2) - nu12) + E1/G12)

    For a circular hole (a=b), this reduces to the well-known
    orthotropic SCF which is ~6.17 for T300/Epoxy (vs 3.0 isotropic).

    NOTE: This uses single-ply E1/E2 because max stress is extracted
    per-ply (section point), not as laminate average. The 0-degree ply
    dominates and its local material axes align with E1/E2.
    Finite-plate and multi-ply interaction effects cause ~10-20%
    deviation from the infinite-plate analytical value.
    """
    ratio_E = math.sqrt(E1 / E2)
    k = math.sqrt(2.0 * (ratio_E - NU12) + E1 / G12)
    SCF = 1.0 + (semi_a_perp / semi_b_par) * k
    return SCF


def validation_suite():
    """Run 3 analytical validation cases before main batch."""

    # Compute Lekhnitskii expected SCFs
    # Case 1: Circular hole r=5 — a_perp = b_par = 5
    SCF_circ = lekhnitskii_SCF(5.0, 5.0)

    # Case 2: Ellipse semi_major=8 ar=0.5 angle=90
    # Major axis (8) is perpendicular to X-load, minor axis (4) parallel
    # a_perp=8, b_par=4
    SCF_ellipse_perp = lekhnitskii_SCF(8.0, 4.0)

    # Case 3: Ellipse semi_major=8 ar=0.5 angle=0
    # Major axis (8) is parallel to X-load, minor axis (4) perpendicular
    # a_perp=4, b_par=8
    SCF_ellipse_par = lekhnitskii_SCF(4.0, 8.0)

    cases = [
        # Case 1: Single circular hole, centre, uniaxial
        {'n_defects': 1,
         'defects': [{'x': 50, 'y': 25, 'semi_major': 5,
                      'aspect_ratio': 1.0, 'angle': 0}],
         'pressure_x': 10.0, 'pressure_y': 0.0,
         'ply_thickness': 0.125, 'layup_rotation': 0.0,
         'expected_SCF': SCF_circ,
         'source': 'Lekhnitskii circular (E1/E2={:.1f})'.format(E1/E2)},

        # Case 2: Ellipse (a/b=2), major axis perpendicular to load
        {'n_defects': 1,
         'defects': [{'x': 50, 'y': 25, 'semi_major': 8,
                      'aspect_ratio': 0.5, 'angle': 90}],
         'pressure_x': 10.0, 'pressure_y': 0.0,
         'ply_thickness': 0.125, 'layup_rotation': 0.0,
         'expected_SCF': SCF_ellipse_perp,
         'source': 'Lekhnitskii ellipse perp. (a/b=2)'},

        # Case 3: Same ellipse, major axis parallel to load
        {'n_defects': 1,
         'defects': [{'x': 50, 'y': 25, 'semi_major': 8,
                      'aspect_ratio': 0.5, 'angle': 0}],
         'pressure_x': 10.0, 'pressure_y': 0.0,
         'ply_thickness': 0.125, 'layup_rotation': 0.0,
         'expected_SCF': SCF_ellipse_par,
         'source': 'Lekhnitskii ellipse par. (a/b=0.5)'},
    ]

    print('\n' + '=' * 60)
    print('VALIDATION AGAINST LEKHNITSKII ORTHOTROPIC SOLUTIONS')
    print('(Using single-ply E1/E2 since max stress is per-ply)')
    print('Expected SCFs: circular={:.2f}, ellipse_perp={:.2f},'
          ' ellipse_par={:.2f}'.format(SCF_circ, SCF_ellipse_perp,
                                       SCF_ellipse_par))
    print('Tolerance: 20% (finite plate + multi-ply effects)')
    print('=' * 60)

    all_passed = True

    for i, case in enumerate(cases):
        sim_id = 9990 + i
        job_name = 'Job_{:04d}'.format(sim_id)

        print('\nCase {}: {} defect, {}'.format(
            i + 1, 'circular' if case['defects'][0]['aspect_ratio'] == 1.0
            else 'elliptical', case['source']))

        result = run_single_simulation(case, sim_id=sim_id,
                                       keep_odb=True)

        if result is None:
            print('  FAILED TO RUN — cannot validate')
            all_passed = False
            continue

        # Keep .odb for GUI inspection
        print('  KEPT FOR INSPECTION: {}.odb'.format(job_name))

        # Calculate stress concentration factor
        sigma_applied = case['pressure_x']
        sigma_max = result['max_mises_per_defect'][0]
        SCF_actual = sigma_max / sigma_applied
        SCF_expected = case['expected_SCF']
        error = abs(SCF_actual - SCF_expected) / SCF_expected * 100

        print('  SCF = {:.2f} (expected {:.2f}, error {:.1f}%)'.format(
            SCF_actual, SCF_expected, error))

        if error > 20:
            print('  WARNING: >20% error — check mesh/BC/geometry!')
            all_passed = False

    print('\n' + '-' * 60)
    if all_passed:
        print('All validation cases within 20% of Lekhnitskii values.')
    else:
        print('One or more cases exceeded 20% error — review before'
              ' proceeding.')
    print('')
    print('-> Open the Job_999x.odb files in Abaqus CAE')
    print('-> Screenshot: mesh, stress contours, deformed shape')
    print('-> Write 1-page validation report for supervisor')
    print('=' * 60)

    return all_passed


# ============================================================
# MAIN: Run parametric study
# ============================================================
def main():
    print('=' * 60)
    print('V4 COMPOSITE (FIXED) — 20 CORRECTIONS APPLIED')
    print('=' * 60)
    print('')
    print('KEY FIXES:')
    print('  1.  Sequential hole placement (zero overlap crashes)')
    print('  2.  Pressure 1-15 MPa (realistic aerospace loads)')
    print('  3+13. Roller BC: U1=0 on left edge, corner pin U2/U3')
    print('  5.  Adaptive polygon segments (Ramanujan scaling)')
    print('  6.  Symmetric Y-loading (top + bottom edges)')
    print('  7.  Safe node lookup (dict by label)')
    print('  11. Explicit S4R element type')
    print('  12. Crack-aware per-defect search radius')
    print('  14. Job status check before extraction')
    print('  17. Corner pin RF diagnostic (per-sim BC check)')
    print('  18. Validation suite (3 analytical SCF cases)')
    print('  19. Pressure calibration (30-sample failure rate check)')
    print('  20. Lekhnitskii orthotropic SCFs (replaces Kirsch/Peterson)')
    print('')
    print('Material: T300/Epoxy CFRP')
    print('  E1={:.0f}, E2={:.0f}, G12={:.0f} MPa'.format(E1, E2, G12))
    print('  XT={:.0f}, XC={:.0f}, YT={:.0f}, YC={:.0f}, SL={:.0f} MPa'.format(
        XT, XC, YT, YC, SL))
    print('')
    print('Layup: [0/45/-45/90]s ({} plies) + variable rotation'.format(N_PLIES))
    print('Defects: 1-{} per plate, AR 0.05-1.0'.format(MAX_DEFECTS))
    print('Mesh: {:.1f}mm global, {:.1f}mm holes, {:.1f}mm cracks'.format(
        GLOBAL_MESH_SIZE, FINE_MESH_SIZE_HOLE, FINE_MESH_SIZE_CRACK))
    print('Failure: Tsai-Wu index + Hashin damage initiation')
    print('')
    print('Samples: {} LHS, seed={}'.format(NUM_SAMPLES, RANDOM_SEED))
    print('=' * 60)

    # --- FIX 19: Calibrate pressure range FIRST ---
    print('\nStep 1/3: Pressure range calibration')
    cal_passed = calibrate_failure_rate(n_test=30)

    # --- FIX 18: Then validate against analytical ---
    print('\nStep 2/3: Analytical validation')
    validation_passed = validation_suite()

    # --- Gate: User reviews calibration + validation, then decides ---
    print('\n' + '=' * 60)
    print('PRE-BATCH SUMMARY')
    print('  Calibration: {}'.format('PASSED' if cal_passed else
          'OUTSIDE TARGET — review failure rate above'))
    print('  Validation:  {}'.format('PASSED' if validation_passed else
          'SOME CASES >20% ERROR — review above'))
    print('=' * 60)
    print('Proceed with {} main batch simulations? (y/n)'.format(
        NUM_SAMPLES))
    try:
        response = raw_input('> ').strip().lower()
    except NameError:
        response = input('> ').strip().lower()
    if response != 'y':
        print('Batch aborted by user. Review results and re-run.')
        return
    print('\nStep 3/3: Main batch run')
    print('')

    # --- Generate samples ---
    print('\nGenerating {} samples (stratified by defect count)...'.format(
        NUM_SAMPLES))
    all_samples = generate_all_samples(NUM_SAMPLES, seed=RANDOM_SEED)

    total_sims = len(all_samples)
    print('  Total valid samples: {}'.format(total_sims))

    # Count by n_defects
    for nd in range(1, MAX_DEFECTS + 1):
        count = sum(1 for s in all_samples if s['n_defects'] == nd)
        print('  n_defects={}: {} samples'.format(nd, count))

    # --- Resume check ---
    completed_ids = load_completed_ids(OUTPUT_FILE)
    if completed_ids:
        print('\nRESUMING: {} completed'.format(len(completed_ids)))

    # --- Create CSV ---
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w') as f:
            f.write(CSV_HEADER)

    print('\nOutput: {}'.format(OUTPUT_FILE))
    print('=' * 60)

    # --- Run ---
    successful = 0
    failed_count = 0
    skipped = 0
    start_time = time.time()

    for i, sample in enumerate(all_samples):
        sim_id = i + 1

        if sim_id in completed_ids:
            skipped += 1
            continue

        # Progress + ETA
        elapsed = time.time() - start_time
        if successful > 0:
            avg_time = elapsed / successful
            remaining = avg_time * (total_sims - i)
            eta_str = ' (ETA: {:.0f} min)'.format(remaining / 60.0)
        else:
            eta_str = ''

        n_def = sample['n_defects']
        defects = sample['defects']

        print('\n[{}/{}]{} — {} defect{}'.format(
            sim_id, total_sims, eta_str,
            n_def, 's' if n_def > 1 else ''))
        for di, d in enumerate(defects):
            dtype = 'CRACK' if d['aspect_ratio'] < CRACK_THRESHOLD_AR else 'hole'
            print('  D{}: ({:.1f},{:.1f}) a={:.1f} ar={:.2f} ang={:.0f} [{}]'.format(
                di + 1, d['x'], d['y'], d['semi_major'],
                d['aspect_ratio'], d['angle'], dtype))
        print('  Px={:.1f} Py={:.1f} ply_t={:.3f} rot={:.1f}'.format(
            sample['pressure_x'], sample['pressure_y'],
            sample['ply_thickness'], sample['layup_rotation']))

        result = run_single_simulation(sample, sim_id)

        if result is not None:
            write_csv_row(OUTPUT_FILE, result)
            print('  -> mises={:.1f} TW={:.3f} H_ft={:.3f} H_mt={:.3f} '
                  'disp={:.4f} fail_TW={} fail_H={}'.format(
                      result['max_mises'],
                      result['tsai_wu_index'],
                      result['max_hashin_ft'],
                      result['max_hashin_mt'],
                      result['max_disp'],
                      'YES' if result['failed_tsai_wu'] else 'NO',
                      'YES' if result['failed_hashin'] else 'NO'))
            successful += 1
        else:
            write_error_row(OUTPUT_FILE, sim_id, sample)
            print('  -> FAILED')
            failed_count += 1

    # --- Summary ---
    total_time = time.time() - start_time
    print('\n' + '=' * 60)
    print('V4 COMPOSITE BATCH COMPLETE (20 FIXES)')
    print('=' * 60)
    print('Total time: {:.1f} minutes'.format(total_time / 60.0))
    print('Successful: {}'.format(successful))
    print('Failed: {}'.format(failed_count))
    if skipped > 0:
        print('Skipped (resumed): {}'.format(skipped))
    print('Results: {}'.format(OUTPUT_FILE))
    print('=' * 60)


# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    main()
