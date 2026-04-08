"""
============================================================
ABAQUS AUTOMATION SCRIPT V4 — COMPOSITE PLATE WITH
VARIABLE N CRACK-LIKE & HOLE-LIKE DEFECTS
============================================================
Purpose: Run parametric study on COMPOSITE (CFRP) shell plate
         with 1-5 randomly placed defects that range from
         round holes to thin crack-like slits. Uses Hashin
         damage initiation and Tsai-Wu failure index.

Run with (NO GUI — headless):
    abaqus cae noGUI=run_batch_simulations_v4_composite.py

What's NEW in V4 (vs V3):
    1. COMPOSITE material (T300/Epoxy, not steel)
    2. Shell elements (S4R) with CompositeLayup
    3. Crack-like defects (aspect ratio 0.05-0.2)
    4. Variable 1-5 defects per plate
    5. Hashin damage initiation criteria
    6. Tsai-Wu failure index (manually computed)
    7. Per-ply stress extraction across section points
    8. Layup rotation as variable parameter
    9. 500 LHS samples, stratified by defect count

BUGS AVOIDED (carried from V1-V3):
    - NO CutExtrude — single-sketch for all holes
    - ELEMENT_NODAL for stress extraction
    - nodeLabel > 0 validation before coordinate lookup
    - Pairwise collision detection for all hole pairs
    - Full float precision in CSV
    - Memory cleanup after every simulation
    - Resume capability from existing CSV

Output:
    simulation_results_v4.csv

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

# --- Sampling ---
NUM_SAMPLES = 500
RANDOM_SEED = 42
MAX_DEFECTS = 5

# ============================================================
# PARAMETER RANGES
# ============================================================

# Global parameters (applied to every simulation)
GLOBAL_RANGES = {
    'pressure_x':      [50.0,  200.0],   # MPa — in-plane X tension
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
OUTPUT_FILE = 'simulation_results_v4.csv'


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
# HELPER: Pairwise overlap check for N holes
# ============================================================
def validate_all_no_overlap(defects, margin=2.0):
    """O(n^2) pairwise distance check."""
    n = len(defects)
    for i in range(n):
        for j in range(i + 1, n):
            dist = math.sqrt(
                (defects[i]['x'] - defects[j]['x'])**2 +
                (defects[i]['y'] - defects[j]['y'])**2)
            min_dist = (defects[i]['semi_major'] +
                        defects[j]['semi_major'] + margin)
            if dist < min_dist:
                return False
    return True


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
# GENERATE SAMPLES — Stratified by defect count
# ============================================================
def generate_all_samples(n_total, seed=42):
    """
    Generate samples with stratified defect counts.
    ~100 samples per n_defects (1 through 5).
    Global params via LHS, defect params randomised per hole.
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

    for n_def in range(1, MAX_DEFECTS + 1):
        n_sims = counts_per_n + (1 if n_def <= remainder else 0)

        for _ in range(n_sims):
            if idx >= n_total:
                break

            sample = {
                'n_defects': n_def,
                'pressure_x': global_samples[idx]['pressure_x'],
                'pressure_y': global_samples[idx]['pressure_y'],
                'ply_thickness': global_samples[idx]['ply_thickness'],
                'layup_rotation': global_samples[idx]['layup_rotation'],
                'defects': [],
            }

            # Generate defect parameters
            for d in range(n_def):
                defect = {}
                for pname, (lo, hi) in DEFECT_RANGES.items():
                    defect[pname] = random.uniform(lo, hi)
                sample['defects'].append(defect)

            all_samples.append(sample)
            idx += 1

    # Shuffle to mix defect counts
    random.seed(seed + 999)
    random.shuffle(all_samples)
    return all_samples


# ============================================================
# VALIDATE ONE SAMPLE
# ============================================================
def validate_sample(sample):
    """Check all defects in bounds and no overlaps."""
    defects = sample['defects']
    for d in defects:
        sb = d['semi_major'] * d['aspect_ratio']
        if not validate_ellipse_bounds(
                d['x'], d['y'], d['semi_major'], sb,
                d['angle'], PLATE_LENGTH, PLATE_WIDTH):
            return False
    if not validate_all_no_overlap(defects):
        return False
    return True


# ============================================================
# MAIN: Run one V4 simulation
# ============================================================
def run_single_simulation(sample, sim_id):
    """
    Creates composite shell plate with N defects (hole-like
    and crack-like), runs analysis, extracts composite failure
    metrics including Tsai-Wu and Hashin criteria.
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
            is_crack = (ar < CRACK_THRESHOLD_AR)
            n_seg = NUM_SEGMENTS_CRACK if is_crack else NUM_SEGMENTS_HOLE

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
        # Modify default output request to include damage
        model.fieldOutputRequests['F-Output-1'].setValues(
            variables=('S', 'U', 'HSNFTCRT', 'HSNFCCRT',
                       'HSNMTCRT', 'HSNMCCRT'))

        # ======================================================
        # BOUNDARY CONDITIONS — left edge (x=0)
        # For shell: edges, not faces
        # ======================================================
        left_edge = instance.edges.findAt(
            ((0.0, PLATE_WIDTH / 2, 0.0),))
        left_region = assembly.Set(
            edges=left_edge, name='LeftEdge')
        model.EncastreBC(
            name='FixedLeft', createStepName='Initial',
            region=left_region)

        # ======================================================
        # LOADS — ShellEdgeLoad for in-plane tension
        # Force per unit length = stress * total_thickness
        # ======================================================
        # X-direction tension (right edge)
        right_edge = instance.edges.findAt(
            ((PLATE_LENGTH, PLATE_WIDTH / 2, 0.0),))
        right_surface = assembly.Surface(
            side1Edges=right_edge, name='RightEdge')
        force_x = press_x * total_thickness  # N/mm
        model.ShellEdgeLoad(
            name='TensionX',
            createStepName='LoadStep',
            region=right_surface,
            magnitude=force_x,
            directionVector=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
            distributionType=UNIFORM,
            traction=GENERAL)

        # Y-direction tension (top edge) — only if nonzero
        if press_y > 0.0:
            top_edge = instance.edges.findAt(
                ((PLATE_LENGTH / 2, PLATE_WIDTH, 0.0),))
            top_surface = assembly.Surface(
                side1Edges=top_edge, name='TopEdge')
            force_y = press_y * total_thickness
            model.ShellEdgeLoad(
                name='TensionY',
                createStepName='LoadStep',
                region=top_surface,
                magnitude=force_y,
                directionVector=((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
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

        # Generate mesh
        part.generateMesh()
        n_elements = len(part.elements)

        # ======================================================
        # RUN JOB
        # ======================================================
        mdb.Job(name=job_name, model=model_name, type=ANALYSIS)
        mdb.jobs[job_name].submit()
        mdb.jobs[job_name].waitForCompletion()

        # ======================================================
        # EXTRACT RESULTS
        # ======================================================
        odb = session.openOdb(name=job_name + '.odb')
        step = odb.steps['LoadStep']
        frame = step.frames[-1]

        # --------------------------------------------------
        # STRESS EXTRACTION (all section points / plies)
        # Shell stresses: S11, S22, S12 per section point
        # --------------------------------------------------
        stress_field = frame.fieldOutputs['S']
        stress_at_nodes = stress_field.getSubset(
            position=ELEMENT_NODAL)

        max_mises = 0.0
        max_s11 = -1e20
        min_s11 = 1e20
        max_s22 = -1e20
        min_s22 = 1e20
        max_s12 = 0.0
        max_tw = 0.0  # Tsai-Wu index

        # Per-defect max stress
        max_mises_per_defect = [0.0] * MAX_DEFECTS

        for value in stress_at_nodes.values:
            mises = value.mises
            nl = value.nodeLabel
            if nl <= 0:
                continue

            # Ply stresses: S11, S22, S12
            s11 = value.data[0]
            s22 = value.data[1]
            s12 = value.data[3]  # S12 is index 3 in [S11,S22,S33,S12,...]

            # Global maxima
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

            # Tsai-Wu
            tw = compute_tsai_wu(s11, s22, s12)
            if tw > max_tw:
                max_tw = tw

            # Per-defect stress (find nearest defect)
            node = odb.rootAssembly.instances[
                'PLATEINSTANCE'].nodes[nl - 1]
            nx = node.coordinates[0]
            ny = node.coordinates[1]

            for di in range(n_def):
                d = defects[di]
                search_r = d['semi_major'] * 2.0
                dd = math.sqrt(
                    (nx - d['x'])**2 + (ny - d['y'])**2)
                if dd < search_r:
                    if mises > max_mises_per_defect[di]:
                        max_mises_per_defect[di] = mises

        # --------------------------------------------------
        # HASHIN CRITERIA (if available)
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
                    val = value.data
                    if mode == 'ft' and val > max_hashin_ft:
                        max_hashin_ft = val
                    elif mode == 'fc' and val > max_hashin_fc:
                        max_hashin_fc = val
                    elif mode == 'mt' and val > max_hashin_mt:
                        max_hashin_mt = val
                    elif mode == 'mc' and val > max_hashin_mc:
                        max_hashin_mc = val
            except KeyError:
                pass  # Hashin output may not be available

        odb.close()

        # --------------------------------------------------
        # DISPLACEMENT
        # --------------------------------------------------
        odb = session.openOdb(name=job_name + '.odb')
        frame = odb.steps['LoadStep'].frames[-1]
        disp_field = frame.fieldOutputs['U']
        max_disp = 0.0
        for value in disp_field.values:
            mag = math.sqrt(
                value.data[0]**2 +
                value.data[1]**2 +
                value.data[2]**2)
            if mag > max_disp:
                max_disp = mag
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

        extensions = ['.odb', '.lck', '.res', '.prt', '.sim',
                      '.sta', '.msg', '.dat', '.com', '.ipm',
                      '.log', '.023', '.SMABulk', '.cid',
                      '.simdir']
        for ext in extensions:
            try:
                os.remove(job_name + ext)
            except:
                pass
        # Remove .simdir folder
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
    n_output_cols = 17 + MAX_DEFECTS  # count output columns
    vals.extend(['ERROR'] * n_output_cols)

    with open(filepath, 'a') as f:
        f.write(','.join([str(v) for v in vals]) + '\n')


# ============================================================
# MAIN: Run parametric study
# ============================================================
def main():
    print('=' * 60)
    print('V4 COMPOSITE + CRACK-LIKE DEFECTS + VARIABLE N-HOLES')
    print('=' * 60)
    print('')
    print('Material: T300/Epoxy CFRP')
    print('  E1={:.0f}, E2={:.0f}, G12={:.0f} MPa'.format(E1, E2, G12))
    print('  XT={:.0f}, XC={:.0f}, YT={:.0f}, YC={:.0f}, SL={:.0f} MPa'.format(
        XT, XC, YT, YC, SL))
    print('')
    print('Layup: [0/45/-45/90]s ({} plies) + variable rotation'.format(N_PLIES))
    print('Defects: 1-{} per plate, AR 0.05-1.0 (cracks to circles)'.format(
        MAX_DEFECTS))
    print('Mesh: {:.1f}mm global, {:.1f}mm holes, {:.1f}mm cracks'.format(
        GLOBAL_MESH_SIZE, FINE_MESH_SIZE_HOLE, FINE_MESH_SIZE_CRACK))
    print('Failure: Tsai-Wu index + Hashin damage initiation')
    print('')
    print('Shell elements (S4R) — full Abaqus licence')
    print('Samples: {} LHS, seed={}'.format(NUM_SAMPLES, RANDOM_SEED))
    print('=' * 60)

    # --- Generate samples ---
    print('\nGenerating {} samples (stratified by defect count)...'.format(
        NUM_SAMPLES))
    all_samples = generate_all_samples(NUM_SAMPLES, seed=RANDOM_SEED)

    # --- Validate ---
    valid_samples = []
    rejected = 0
    for s in all_samples:
        if validate_sample(s):
            valid_samples.append(s)
        else:
            rejected += 1

    total_sims = len(valid_samples)
    print('  Valid: {}'.format(total_sims))
    if rejected > 0:
        print('  Rejected: {}'.format(rejected))

    # Count by n_defects
    for nd in range(1, MAX_DEFECTS + 1):
        count = sum([1 for s in valid_samples if s['n_defects'] == nd])
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

    for i, sample in enumerate(valid_samples):
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
        print('  Px={:.0f} Py={:.0f} ply_t={:.3f} rot={:.1f}'.format(
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
    print('V4 COMPOSITE BATCH COMPLETE')
    print('=' * 60)
    print('Total time: {:.1f} minutes'.format(total_time / 60.0))
    print('Successful: {}'.format(successful))
    print('Failed: {}'.format(failed_count))
    if skipped > 0:
        print('Skipped (resumed): {}'.format(skipped))
    print('Results: {}'.format(OUTPUT_FILE))
    print('')
    print('Key outputs:')
    print('  tsai_wu_index — composite failure (>=1.0 = failed)')
    print('  max_hashin_ft/fc/mt/mc — per-mode damage initiation')
    print('  max_s11/s22/s12 — peak ply stresses')
    print('  max_mises — von Mises (for comparison with V1-V3)')
    print('')
    print('Next: Train ML on V4 data with composite failure targets')
    print('=' * 60)


# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    main()
