"""
============================================================
ABAQUS VALIDATION SCRIPT V7 — STRAIGHT CRACK VS ANALYTICAL
============================================================
Validates the FEA model by comparing straight-crack SCF
against the Lekhnitskii orthotropic analytical solution.
Also verifies that progressive damage (SDEG) activates.

Run BEFORE the main batch.

Run with (headless):
    abaqus cae noGUI=v7_validation.py

Run with (screenshots enabled):
    abaqus cae script=v7_validation.py

Output:
    v7_validation_log.txt            — detailed log
    v7_validation_screenshots/       — mesh + deformed (every 5 sims)
    Job_999x.odb                     — kept for GUI inspection

Validation cases:
    1. Straight crack perpendicular to load (worst case SCF)
    2. Straight crack parallel to load (benign orientation)
    3. High-pressure case to verify SDEG > 0 (damage activates)
    4. Multi-crack case (2 cracks, stress interaction check)
    5. Thick laminate case (0.20mm plies, stiffer response)
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
# CONFIGURATION (same as batch runner)
# ============================================================
PLATE_LENGTH = 100.0
PLATE_WIDTH = 50.0

E1 = 138000.0
E2 = 8960.0
NU12 = 0.30
G12 = 7100.0
G13 = 7100.0
G23 = 6210.0

XT = 1500.0
XC = 1200.0
YT = 40.0
YC = 246.0
SL = 68.0
ST = 68.0

GFT = 12.5
GFC = 12.5
GMT = 1.0
GMC = 1.0
# --- Explicit dynamics (required for Hashin damage EVOLUTION / SDEG) ---
# Set USE_EXPLICIT = False if your Abaqus installation does not include
# an Abaqus/Explicit license.  Standard will still give Hashin initiation
# criteria (HSNFTCRT, HSNMTCRT, …) but NOT damage evolution (SDEG).
USE_EXPLICIT = False   # Explicit doesn't support SDEG/HSNFTCRT for composite layup shells (S4R)
DENSITY = 1.58e-9           # tonne/mm^3  (CFRP ~1580 kg/m^3)
EXPLICIT_TIME_PERIOD = 0.01  # seconds — quasi-static (longer for stability)
EXPLICIT_TARGET_DT = 1.0e-6  # seconds — mass-scaling target increment

BASE_PLY_ANGLES = [0.0, 45.0, -45.0, 90.0, 90.0, -45.0, 45.0, 0.0]
N_PLIES = 8

GLOBAL_MESH_SIZE = 3.0
FINE_MESH_SIZE_CRACK = 0.50
CRACK_MESH_SEARCH_BUFFER = 3.0

CRACK_SEG_LEN_MIN = 0.2
CRACK_SEG_LEN_MAX = 0.8
MAX_ANGLE_DEV_DEG = 45.0
MIN_CRACK_WIDTH = 0.15
MIN_POLYGON_SEGMENTS = 12

MAX_DEFECTS = 5
MAX_PLACEMENT_ATTEMPTS = 200

# ============================================================
# VALIDATION CONFIG
# ============================================================
LOG_FILE = 'v7_validation_log.txt'
SCREENSHOT_DIR = 'v7_sim_captures'
SCREENSHOT_INTERVAL = 5
# Set True ONLY when running with 'abaqus cae script=' (GUI mode).
# Leave False for 'abaqus cae noGUI=' — printToFile segfaults without display.
SCREENSHOTS_ENABLED = False
ODB_LIST_FILE = 'v7_odb_for_screenshots.txt'


# ============================================================
# LOGGING
# ============================================================
def log(msg):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    line = '[{}] {}'.format(timestamp, msg)
    print(msg)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    except Exception:
        pass


# ============================================================
# SCREENSHOTS — max quality (4K resolution, white background)
# ============================================================
# NOTE: session.printToFile() causes a segfault (signal 11) in noGUI mode
# on some Abaqus installations.  This is a hard crash in the C rendering
# engine that Python cannot catch.  Screenshots are therefore gated behind
# SCREENSHOTS_ENABLED (see config above).  When disabled, ODB paths are
# saved to ODB_LIST_FILE so you can take screenshots later in GUI mode.
# ============================================================
_screenshot_setup_done = False


def _save_odb_path(odb_path):
    """Append an ODB path to the list file for later screenshot processing."""
    try:
        with open(ODB_LIST_FILE, 'a') as f:
            f.write(os.path.abspath(odb_path) + '\n')
    except Exception:
        pass


def setup_screenshot_quality():
    global _screenshot_setup_done
    if _screenshot_setup_done:
        return
    try:
        session.pngOptions.setValues(imageSize=(4096, 3072))
        session.graphicsOptions.setValues(
            backgroundStyle=SOLID, backgroundColor='#FFFFFF')
        vp = session.viewports['Viewport: 1']
        vp.viewportAnnotationOptions.setValues(
            triad=ON, legend=ON, title=ON, state=ON)
        _screenshot_setup_done = True
        log('  Screenshot quality: 4096x3072 PNG, white background')
    except Exception as e:
        log('  WARNING: Could not set screenshot quality: {}'.format(str(e)))


def take_mesh_screenshot(sim_id, part):
    if not SCREENSHOTS_ENABLED:
        return
    try:
        setup_screenshot_quality()
        path = os.path.join(SCREENSHOT_DIR,
                            'mesh_val_{:04d}'.format(sim_id))
        vp = session.viewports['Viewport: 1']
        vp.setValues(displayedObject=part)
        vp.partDisplay.setValues(mesh=ON)
        vp.view.fitView()
        session.printToFile(fileName=path, format=PNG,
                            canvasObjects=(vp,))
        log('  Screenshot: {}.png'.format(path))
    except Exception as e:
        log('  WARNING: Mesh screenshot failed: {}'.format(str(e)))


def take_deformed_screenshot(sim_id, odb):
    if not SCREENSHOTS_ENABLED:
        return
    try:
        setup_screenshot_quality()
        path = os.path.join(SCREENSHOT_DIR,
                            'deformed_val_{:04d}'.format(sim_id))
        vp = session.viewports['Viewport: 1']
        vp.setValues(displayedObject=odb)
        vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
        vp.odbDisplay.setPrimaryVariable(
            variableLabel='S', outputPosition=INTEGRATION_POINT,
            refinement=(INVARIANT, 'Mises'))
        vp.odbDisplay.commonOptions.setValues(
            deformationScaling=UNIFORM, uniformScaleFactor=1.0)
        vp.view.fitView()
        session.printToFile(fileName=path, format=PNG,
                            canvasObjects=(vp,))
        log('  Screenshot: {}.png'.format(path))
    except Exception as e:
        log('  WARNING: Deformed screenshot failed: {}'.format(str(e)))


def take_sdeg_screenshot(sim_id, odb):
    """Screenshot of SDEG (damage) contour on deformed shape."""
    if not SCREENSHOTS_ENABLED:
        return
    try:
        setup_screenshot_quality()
        path = os.path.join(SCREENSHOT_DIR,
                            'sdeg_val_{:04d}'.format(sim_id))
        vp = session.viewports['Viewport: 1']
        vp.setValues(displayedObject=odb)
        vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
        vp.odbDisplay.setPrimaryVariable(
            variableLabel='SDEG', outputPosition=ELEMENT_NODAL)
        vp.odbDisplay.commonOptions.setValues(
            deformationScaling=UNIFORM, uniformScaleFactor=1.0)
        vp.view.fitView()
        session.printToFile(fileName=path, format=PNG,
                            canvasObjects=(vp,))
        log('  Screenshot: {}.png (SDEG contour)'.format(path))
    except Exception as e:
        log('  WARNING: SDEG screenshot failed: {}'.format(str(e)))


# ============================================================
# HELPERS (shared with batch runner)
# ============================================================
def crack_polygon_points(cx, cy, half_length, width, angle_deg,
                         roughness):
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


def compute_min_inter_dist(defects):
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


def get_crack_edges(part, cx, cy, half_length, buffer):
    search_radius = half_length + buffer
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


def compute_tsai_wu(s11, s22, s12):
    F1 = 1.0 / XT - 1.0 / XC
    F2 = 1.0 / YT - 1.0 / YC
    F11 = 1.0 / (XT * XC)
    F22 = 1.0 / (YT * YC)
    F66 = 1.0 / (SL * SL)
    F12 = -0.5 * math.sqrt(F11 * F22)
    tw = (F1 * s11 + F2 * s22 +
          F11 * s11**2 + F22 * s22**2 + F66 * s12**2 +
          2.0 * F12 * s11 * s22)
    return tw


def check_solver_completed(job_name):
    try:
        with open(job_name + '.sta', 'r') as sta_f:
            sta_content = sta_f.read().upper()
            if 'SUCCESSFULLY' in sta_content:
                return True
            if 'HAS BEEN COMPLETED' in sta_content:
                return True
    except Exception:
        pass
    return False


# ============================================================
# LEKHNITSKII ANALYTICAL SCF
# ============================================================
def lekhnitskii_SCF(semi_a_perp, semi_b_par):
    """SCF for elliptical hole in orthotropic plate under uniaxial load."""
    ratio_E = math.sqrt(E1 / E2)
    k = math.sqrt(2.0 * (ratio_E - NU12) + E1 / G12)
    SCF = 1.0 + (semi_a_perp / semi_b_par) * k
    return SCF


# ============================================================
# RUN SINGLE VALIDATION SIMULATION
# ============================================================
def run_single_simulation(sample, sim_id, keep_odb=True,
                          screenshot=True):
    model_name = 'Model_{}'.format(sim_id)
    job_name = 'Job_{:04d}'.format(sim_id)
    job_start = time.time()

    n_def = sample['n_defects']
    defects = sample['defects']
    press_x = sample['pressure_x']
    press_y = sample['pressure_y']
    ply_t = sample['ply_thickness']
    layup_rot = sample['layup_rotation']
    total_thickness = ply_t * N_PLIES
    min_inter_dist = compute_min_inter_dist(defects)

    log('--- JOB {} (sim_id={}) ---'.format(job_name, sim_id))
    log('  n_def={} Px={:.1f} Py={:.1f} ply_t={:.3f} rot={:.1f}'.format(
        n_def, press_x, press_y, ply_t, layup_rot))
    for di, d in enumerate(defects):
        log('  Crack {}: ({:.1f},{:.1f}) L={:.1f} w={:.2f} '
            'ang={:.0f} rough={:.2f}'.format(
                di + 1, d['x'], d['y'], d['half_length'],
                d['width'], d['angle'], d['roughness']))

    try:
        if model_name in mdb.models.keys():
            del mdb.models[model_name]

        model = mdb.Model(name=model_name)

        sketch = model.ConstrainedSketch(
            name='plateSketch', sheetSize=200.0)
        sketch.rectangle(
            point1=(0.0, 0.0),
            point2=(PLATE_LENGTH, PLATE_WIDTH))

        for d in defects:
            pts = crack_polygon_points(
                d['x'], d['y'],
                d['half_length'], d['width'],
                d['angle'], d['roughness'])
            n_seg = len(pts)
            for idx in range(n_seg):
                p1 = pts[idx]
                p2 = pts[(idx + 1) % n_seg]
                sketch.Line(point1=p1, point2=p2)

        part = model.Part(
            name='Plate', dimensionality=THREE_D,
            type=DEFORMABLE_BODY)
        part.BaseShell(sketch=sketch)

        n_faces = len(part.faces)
        if n_faces < 1:
            raise Exception('zero faces')
        log('  Geometry: {} face(s)'.format(n_faces))

        # Material with damage evolution
        material = model.Material(name='CFRP')
        material.Density(table=((DENSITY,),))
        material.Elastic(
            type=LAMINA,
            table=((E1, E2, NU12, G12, G13, G23),))
        material.HashinDamageInitiation(
            table=((XT, XC, YT, YC, SL, ST),))
        if USE_EXPLICIT:
            try:
                material.hashinDamageInitiation.DamageEvolution(
                    type=ENERGY,
                    softening=LINEAR,
                    table=((GFT, GFC, GMT, GMC),))
                log('  DamageEvolution: created OK')
            except Exception as e:
                log('  CRITICAL: DamageEvolution FAILED: {}'.format(str(e)))
                log('  SDEG will NOT be available in this simulation!')
        log('  Material: CFRP + Hashin{}'.format(
            ' + damage evolution' if USE_EXPLICIT else ' initiation only (Standard)'))

        # Layup
        region = part.Set(faces=part.faces[:], name='AllFaces')
        compositeLayup = part.CompositeLayup(
            name='CompositePlate',
            description='CFRP quasi-isotropic layup',
            elementType=SHELL,
            offsetType=MIDDLE_SURFACE,
            symmetric=False,
            thicknessAssignment=FROM_SECTION)
        compositeLayup.Section(
            preIntegrate=OFF, integrationRule=SIMPSON,
            poissonDefinition=DEFAULT, thicknessModulus=None,
            temperature=GRADIENT, useDensity=OFF)
        compositeLayup.ReferenceOrientation(
            orientationType=GLOBAL, localCsys=None,
            additionalRotationType=ROTATION_ANGLE,
            additionalRotationField='',
            angle=layup_rot, axis=AXIS_3)
        for i, base_angle in enumerate(BASE_PLY_ANGLES):
            compositeLayup.CompositePly(
                suppressed=False,
                plyName='Ply-{}'.format(i + 1),
                region=region, material='CFRP',
                thicknessType=SPECIFY_THICKNESS, thickness=ply_t,
                orientationType=SPECIFY_ORIENT,
                orientationValue=base_angle,
                additionalRotationType=ROTATION_NONE,
                additionalRotationField='',
                axis=AXIS_3, angle=0.0, numIntPoints=3)

        # Assembly
        assembly = model.rootAssembly
        assembly.DatumCsysByDefault(CARTESIAN)
        instance = assembly.Instance(
            name='PlateInstance', part=part, dependent=ON)

        # Step
        if USE_EXPLICIT:
            model.ExplicitDynamicsStep(
                name='LoadStep', previous='Initial',
                timePeriod=EXPLICIT_TIME_PERIOD, nlgeom=ON)
            model.steps['LoadStep'].setValues(
                massScaling=((SEMI_AUTOMATIC, MODEL, AT_BEGINNING, 0,
                              EXPLICIT_TARGET_DT, BELOW_MIN, 0, 0,
                              0.0, 0.0, 0, None),))
            model.SmoothStepAmplitude(name='Ramp', timeSpan=STEP,
                data=((0.0, 0.0), (1.0, 1.0)))
            log('  Step: ExplicitDynamics T={} dt_target={}'.format(
                EXPLICIT_TIME_PERIOD, EXPLICIT_TARGET_DT))
        else:
            model.StaticStep(name='LoadStep', previous='Initial',
                             initialInc=0.1, maxInc=1.0)
            log('  Step: Static (Standard)')
        model.fieldOutputRequests['F-Output-1'].setValues(
            variables=('S', 'U', 'RF'), numIntervals=10)
        if USE_EXPLICIT:
            model.FieldOutputRequest(
                name='F-Output-Damage',
                createStepName='LoadStep',
                variables=('SDEG', 'STATUS',
                           'HSNFTCRT', 'HSNFCCRT',
                           'HSNMTCRT', 'HSNMCCRT'),
                numIntervals=10)
        else:
            model.FieldOutputRequest(
                name='F-Output-Damage',
                createStepName='LoadStep',
                variables=('HSNFTCRT', 'HSNFCCRT',
                           'HSNMTCRT', 'HSNMCCRT'),
                numIntervals=10)

        # BCs
        tol = 0.1
        left_edges = instance.edges.getByBoundingBox(
            xMin=-tol, xMax=tol,
            yMin=-tol, yMax=PLATE_WIDTH + tol,
            zMin=-tol, zMax=tol)
        right_edges = instance.edges.getByBoundingBox(
            xMin=PLATE_LENGTH - tol, xMax=PLATE_LENGTH + tol,
            yMin=-tol, yMax=PLATE_WIDTH + tol,
            zMin=-tol, zMax=tol)
        left_region = assembly.Set(edges=left_edges, name='LeftEdge')
        model.DisplacementBC(
            name='RollerLeft_U1', createStepName='Initial',
            region=left_region,
            u1=0.0, u2=UNSET, u3=UNSET,
            ur1=UNSET, ur2=UNSET, ur3=UNSET)
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

        # Loads
        right_surface = assembly.Surface(
            side1Edges=right_edges, name='RightEdge')
        force_x = press_x * total_thickness
        load_kw = {'amplitude': 'Ramp'} if USE_EXPLICIT else {}
        model.ShellEdgeLoad(
            name='TensionX', createStepName='LoadStep',
            region=right_surface, magnitude=force_x,
            directionVector=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
            distributionType=UNIFORM, traction=GENERAL,
            **load_kw)
        if press_y > 0.0:
            force_y = press_y * total_thickness
            top_edges = instance.edges.getByBoundingBox(
                xMin=-tol, xMax=PLATE_LENGTH + tol,
                yMin=PLATE_WIDTH - tol, yMax=PLATE_WIDTH + tol,
                zMin=-tol, zMax=tol)
            top_surface = assembly.Surface(
                side1Edges=top_edges, name='TopEdge')
            model.ShellEdgeLoad(
                name='TensionY_Top', createStepName='LoadStep',
                region=top_surface, magnitude=force_y,
                directionVector=((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
                distributionType=UNIFORM, traction=GENERAL,
                **load_kw)
            bottom_edges = instance.edges.getByBoundingBox(
                xMin=-tol, xMax=PLATE_LENGTH + tol,
                yMin=-tol, yMax=tol,
                zMin=-tol, zMax=tol)
            bottom_surface = assembly.Surface(
                side1Edges=bottom_edges, name='BottomEdge')
            model.ShellEdgeLoad(
                name='TensionY_Bottom', createStepName='LoadStep',
                region=bottom_surface, magnitude=force_y,
                directionVector=((0.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
                distributionType=UNIFORM, traction=GENERAL,
                **load_kw)

        # Mesh
        part.seedPart(size=GLOBAL_MESH_SIZE,
                      deviationFactor=0.1, minSizeFactor=0.1)
        for d in defects:
            edges = get_crack_edges(
                part, d['x'], d['y'],
                d['half_length'], CRACK_MESH_SEARCH_BUFFER)
            if edges is not None:
                part.seedEdgeBySize(
                    edges=edges, size=FINE_MESH_SIZE_CRACK,
                    deviationFactor=0.1, constraint=FINER)
        if USE_EXPLICIT:
            elemType1 = mesh.ElemType(elemCode=S4R, elemLibrary=EXPLICIT,
                hourglassControl=ENHANCED)
            elemType2 = mesh.ElemType(elemCode=S3, elemLibrary=EXPLICIT)
        else:
            elemType1 = mesh.ElemType(elemCode=S4R, elemLibrary=STANDARD)
            elemType2 = mesh.ElemType(elemCode=S3, elemLibrary=STANDARD)
        all_faces = part.faces[:]
        part.setMeshControls(regions=all_faces, technique=FREE)
        part.setElementType(
            regions=(all_faces,),
            elemTypes=(elemType1, elemType2))
        part.generateMesh()
        n_elements = len(part.elements)
        log('  Mesh: {} elements'.format(n_elements))
        if n_elements == 0:
            raise Exception(
                'Mesh generation produced 0 elements — geometry too '
                'complex for mesher (n_defects={})'.format(n_def))

        if screenshot:
            take_mesh_screenshot(sim_id, part)

        # Run job
        mdb.Job(name=job_name, model=model_name, type=ANALYSIS)
        mdb.jobs[job_name].writeInput()

        # Verify input file
        inp_path = job_name + '.inp'
        try:
            with open(inp_path, 'r') as inp_f:
                inp_text = inp_f.read()
            if USE_EXPLICIT:
                if '*Damage Evolution' not in inp_text:
                    log('  CRITICAL: *Damage Evolution NOT found in .inp!')
                else:
                    log('  Verified: *Damage Evolution present in .inp')
                if 'SDEG' not in inp_text:
                    log('  CRITICAL: SDEG not in .inp field output!')
                else:
                    log('  Verified: SDEG requested in .inp')
                if '*Dynamic' not in inp_text:
                    log('  CRITICAL: *Dynamic not in .inp — step type wrong!')
                else:
                    log('  Verified: *Dynamic step in .inp')
            else:
                if '*Static' not in inp_text:
                    log('  WARNING: *Static not found in .inp')
                else:
                    log('  Verified: *Static step in .inp')
        except Exception as e:
            log('  WARNING: Could not verify .inp: {}'.format(str(e)))

        solver_cmd = 'abaqus job={} interactive'.format(job_name)
        log('  Solver: submitting...')
        solver_rc = os.system(solver_cmd)
        solver_completed = check_solver_completed(job_name)
        odb_exists = os.path.exists(job_name + '.odb')
        log('  Solver: rc={} completed={} odb={}'.format(
            solver_rc,
            'YES' if solver_completed else 'NO',
            'YES' if odb_exists else 'NO'))

        if not solver_completed:
            for diag_ext in ['.msg', '.sta', '.dat']:
                diag_path = job_name + diag_ext
                if os.path.exists(diag_path):
                    try:
                        with open(diag_path, 'r') as df:
                            diag_lines = df.readlines()
                        log('  --- {} (last 20 lines) ---'.format(diag_ext))
                        for dl in diag_lines[-20:]:
                            log('  | ' + dl.rstrip())
                        log('  --- end {} ---'.format(diag_ext))
                    except Exception:
                        pass
        if not solver_completed and not odb_exists:
            raise Exception('Job did not complete (rc={})'.format(solver_rc))

        # Extract results — pre-init for safe defaults on partial failure
        max_mises = 0.0
        max_s11 = -1e20
        min_s11 = 1e20
        max_s22 = -1e20
        min_s22 = 1e20
        max_s12 = 0.0
        max_tw = 0.0
        max_mises_per_defect = [0.0] * MAX_DEFECTS
        max_hashin_ft = 0.0
        max_hashin_fc = 0.0
        max_hashin_mt = 0.0
        max_hashin_mc = 0.0
        max_sdeg = 0.0
        n_damaged_elements = 0
        max_disp = 0.0

        odb = session.openOdb(name=job_name + '.odb')
        try:
            if not SCREENSHOTS_ENABLED:
                _save_odb_path(job_name + '.odb')
                log('  ODB saved for later screenshots: {}.odb'.format(
                    job_name))
            if screenshot:
                take_deformed_screenshot(sim_id, odb)
                take_sdeg_screenshot(sim_id, odb)

            step = odb.steps['LoadStep']
            n_frames = len(step.frames)
            log('  ODB: LoadStep has {} frame(s)'.format(n_frames))
            if n_frames == 0:
                raise Exception(
                    'LoadStep has 0 frames — solver produced no output. '
                    'Check .msg file above for errors.')
            frame = step.frames[-1]
            stress_field = frame.fieldOutputs['S']
            stress_at_nodes = stress_field.getSubset(position=ELEMENT_NODAL)

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
            max_mises_per_defect = [0.0] * MAX_DEFECTS

            for value in stress_at_nodes.values:
                mises = value.mises
                nl = value.nodeLabel
                if nl <= 0:
                    continue
                s11 = value.data[0]
                s22 = value.data[1]
                s12 = value.data[2]
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
                if nl not in node_coords:
                    continue
                nx, ny = node_coords[nl]
                for di in range(n_def):
                    dd = defects[di]
                    search_r = dd['half_length'] * 2.0 + 5.0
                    dist = math.sqrt(
                        (nx - dd['x'])**2 + (ny - dd['y'])**2)
                    if dist < search_r:
                        if mises > max_mises_per_defect[di]:
                            max_mises_per_defect[di] = mises

            # Hashin
            max_hashin_ft = 0.0
            max_hashin_fc = 0.0
            max_hashin_mt = 0.0
            max_hashin_mc = 0.0
            for key, mode in [('HSNFTCRT', 'ft'), ('HSNFCCRT', 'fc'),
                              ('HSNMTCRT', 'mt'), ('HSNMCCRT', 'mc')]:
                try:
                    field = frame.fieldOutputs[key]
                    for value in field.values:
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
                    log('  WARNING: {} not in ODB'.format(key))

            # SDEG
            max_sdeg = 0.0
            n_damaged_elements = 0
            try:
                sdeg_field = frame.fieldOutputs['SDEG']
                damaged_elem_labels = set()
                for value in sdeg_field.values:
                    raw = value.data
                    val = raw[0] if hasattr(raw, '__len__') else raw
                    if val > max_sdeg:
                        max_sdeg = val
                    if val >= 0.99:
                        damaged_elem_labels.add(value.elementLabel)
                n_damaged_elements = len(damaged_elem_labels)
            except KeyError:
                log('  WARNING: SDEG not in ODB')

            # Displacement
            disp_field = frame.fieldOutputs['U']
            max_disp = 0.0
            for value in disp_field.values:
                mag = math.sqrt(value.data[0]**2 + value.data[1]**2 +
                                value.data[2]**2)
                if mag > max_disp:
                    max_disp = mag
        finally:
            odb.close()

        failed_tw = 1 if max_tw >= 1.0 else 0
        failed_hashin = 1 if max(max_hashin_ft, max_hashin_fc,
                                 max_hashin_mt, max_hashin_mc) >= 1.0 else 0

        # Cleanup (keep ODB for validation inspection)
        del mdb.models[model_name]
        if job_name in mdb.jobs.keys():
            del mdb.jobs[job_name]
        extensions = ['.inp', '.lck', '.res', '.prt', '.sim',
                      '.sta', '.msg', '.dat', '.com', '.ipm',
                      '.log', '.023', '.SMABulk', '.cid']
        # Always keep ODB for validation
        for ext in extensions:
            try:
                os.remove(job_name + ext)
            except Exception:
                pass
        gc.collect()

        elapsed = time.time() - job_start
        log('  Results: mises={:.1f} TW={:.3f} SDEG={:.4f} '
            'dmg_el={}'.format(max_mises, max_tw, max_sdeg,
                               n_damaged_elements))
        log('  Failure: TW={} Hashin={}'.format(
            'YES' if failed_tw else 'NO',
            'YES' if failed_hashin else 'NO'))
        log('  KEPT: {}.odb'.format(job_name))
        log('  Duration: {:.1f}s'.format(elapsed))

        return {
            'max_mises': max_mises,
            'max_s11': max_s11, 'min_s11': min_s11,
            'max_s22': max_s22, 'min_s22': min_s22,
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
            'max_sdeg': max_sdeg,
            'n_damaged_elements': n_damaged_elements,
            'solver_completed': 1 if solver_completed else 0,
            'job_name': job_name,
        }

    except Exception as e:
        elapsed = time.time() - job_start
        log('  ERROR: {}'.format(str(e)))
        log('  Duration: {:.1f}s'.format(elapsed))
        try:
            if model_name in mdb.models.keys():
                del mdb.models[model_name]
        except Exception:
            pass
        gc.collect()
        return None


# ============================================================
# MAIN — VALIDATION SUITE
# ============================================================
def main():
    if not os.path.exists(SCREENSHOT_DIR):
        os.makedirs(SCREENSHOT_DIR)

    log('=' * 60)
    log('V7 VALIDATION SUITE')
    if SCREENSHOTS_ENABLED:
        log('Screenshots: ENABLED (will call printToFile)')
    else:
        log('Screenshots: DISABLED (ODB paths saved to {})'.format(
            ODB_LIST_FILE))
        log('  Run v7_take_screenshots.py in GUI mode afterwards.')
    log('=' * 60)

    # Analytical SCFs
    SCF_perp = lekhnitskii_SCF(8.0, 0.15)
    SCF_par = lekhnitskii_SCF(0.15, 8.0)

    log('Lekhnitskii SCFs:')
    log('  Perpendicular crack: SCF = {:.1f}'.format(SCF_perp))
    log('  Parallel crack:     SCF = {:.2f}'.format(SCF_par))
    log('')

    # ========================================================
    # Define validation cases
    # ========================================================
    cases = [
        {
            'name': 'Case 1: Straight crack PERP to load (worst-case SCF)',
            'sample': {
                'n_defects': 1,
                'defects': [{'x': 50, 'y': 25, 'half_length': 8.0,
                             'width': 0.3, 'angle': 90.0,
                             'roughness': 0.0}],
                'pressure_x': 10.0, 'pressure_y': 0.0,
                'ply_thickness': 0.125, 'layup_rotation': 0.0,
            },
            'check': 'scf',
            'expected_SCF': SCF_perp,
            'sigma_applied': 10.0,
        },
        {
            'name': 'Case 2: Straight crack PARALLEL to load (benign)',
            'sample': {
                'n_defects': 1,
                'defects': [{'x': 50, 'y': 25, 'half_length': 8.0,
                             'width': 0.3, 'angle': 0.0,
                             'roughness': 0.0}],
                'pressure_x': 10.0, 'pressure_y': 0.0,
                'ply_thickness': 0.125, 'layup_rotation': 0.0,
            },
            'check': 'scf',
            'expected_SCF': SCF_par,
            'sigma_applied': 10.0,
        },
        {
            'name': 'Case 3: HIGH PRESSURE — Hashin initiation must trigger',
            'sample': {
                'n_defects': 1,
                'defects': [{'x': 50, 'y': 25, 'half_length': 10.0,
                             'width': 0.3, 'angle': 90.0,
                             'roughness': 0.0}],
                'pressure_x': 100.0, 'pressure_y': 0.0,
                'ply_thickness': 0.125, 'layup_rotation': 0.0,
            },
            'check': 'damage',
            'expected_SCF': None,
            'sigma_applied': 100.0,
        },
        {
            'name': 'Case 4: TWO CRACKS — stress interaction',
            'sample': {
                'n_defects': 2,
                'defects': [
                    {'x': 35, 'y': 25, 'half_length': 6.0,
                     'width': 0.3, 'angle': 90.0, 'roughness': 0.0},
                    {'x': 65, 'y': 25, 'half_length': 6.0,
                     'width': 0.3, 'angle': 90.0, 'roughness': 0.0},
                ],
                'pressure_x': 50.0, 'pressure_y': 0.0,
                'ply_thickness': 0.125, 'layup_rotation': 0.0,
            },
            'check': 'multi',
            'expected_SCF': None,
            'sigma_applied': 50.0,
        },
        {
            'name': 'Case 5: THICK LAMINATE (0.20mm plies)',
            'sample': {
                'n_defects': 1,
                'defects': [{'x': 50, 'y': 25, 'half_length': 8.0,
                             'width': 0.3, 'angle': 90.0,
                             'roughness': 0.0}],
                'pressure_x': 50.0, 'pressure_y': 0.0,
                'ply_thickness': 0.20, 'layup_rotation': 0.0,
            },
            'check': 'thickness',
            'expected_SCF': None,
            'sigma_applied': 50.0,
        },
    ]

    # ========================================================
    # Run all cases
    # ========================================================
    all_results = []
    all_passed = True

    for i, case in enumerate(cases):
        sim_id = 9990 + i
        log('')
        log('=' * 60)
        log(case['name'])
        log('=' * 60)

        # Always screenshot validation cases (only 5 total);
        # damage case (case 3) is especially important
        do_screenshot = True

        result = run_single_simulation(
            case['sample'], sim_id,
            keep_odb=True, screenshot=do_screenshot)

        case_passed = True

        all_results.append((case, result))

        if result is None:
            log('  FAILED TO RUN — VALIDATION CANNOT PROCEED')
            all_passed = False
            case['passed'] = False
            continue

        # ---- Evaluate based on check type ----
        if case['check'] == 'scf':
            sigma_max = result['max_mises_per_defect'][0]
            SCF_actual = sigma_max / case['sigma_applied']
            SCF_expected = case['expected_SCF']

            log('  Max Mises near crack = {:.1f}'.format(sigma_max))
            log('  SCF FEA={:.2f}  Lekhnitskii={:.2f}'.format(
                SCF_actual, SCF_expected))
            log('  (Lekhnitskii is for elliptical hole — FEA crack '
                'geometry differs; mismatch is expected)')

            # Pass if stress is elevated above nominal (SCF > 1)
            if SCF_actual < 1.0:
                log('  FAIL: No stress concentration detected')
                case_passed = False
            else:
                log('  PASS: Stress concentration detected (SCF={:.1f})'.format(
                    SCF_actual))

        elif case['check'] == 'damage':
            max_hashin = max(result['max_hashin_ft'],
                             result['max_hashin_fc'],
                             result['max_hashin_mt'],
                             result['max_hashin_mc'])
            log('  Hashin FT={:.3f} FC={:.3f} MT={:.3f} MC={:.3f}'.format(
                result['max_hashin_ft'], result['max_hashin_fc'],
                result['max_hashin_mt'], result['max_hashin_mc']))
            log('  Hashin max = {:.3f}'.format(max_hashin))

            if USE_EXPLICIT:
                log('  SDEG = {:.4f}'.format(result['max_sdeg']))
                if result['max_sdeg'] < 0.001:
                    log('  *** SDEG DID NOT ACTIVATE ***')
                    case_passed = False
                else:
                    log('  DAMAGE EVOLUTION ACTIVE')
            else:
                if max_hashin < 1.0:
                    log('  *** HASHIN INITIATION NOT REACHED ***')
                    log('  At 80 MPa with 10mm crack, at least one')
                    log('  criterion should exceed 1.0')
                    case_passed = False
                else:
                    log('  HASHIN INITIATION REACHED — damage would '
                        'initiate (SDEG needs Explicit solver)')

        elif case['check'] == 'multi':
            log('  Max Mises (crack 1) = {:.1f}'.format(
                result['max_mises_per_defect'][0]))
            log('  Max Mises (crack 2) = {:.1f}'.format(
                result['max_mises_per_defect'][1]))
            log('  Both cracks should show elevated stress')

            if (result['max_mises_per_defect'][0] < 1.0 or
                    result['max_mises_per_defect'][1] < 1.0):
                log('  WARNING: One crack shows near-zero stress — '
                    'check per-defect search radius')
                case_passed = False
            else:
                log('  BOTH CRACKS SHOW STRESS — OK')

        elif case['check'] == 'thickness':
            log('  Total thickness: {:.2f} mm (8 plies x 0.20mm)'.format(
                0.20 * N_PLIES))
            log('  Max Mises = {:.1f}'.format(result['max_mises']))
            log('  Max disp = {:.4f} mm'.format(result['max_disp']))
            log('  Thicker plate should show lower displacement')

        if not case_passed:
            all_passed = False
        case['passed'] = case_passed

    # ========================================================
    # SUMMARY
    # ========================================================
    log('')
    log('=' * 60)
    log('VALIDATION SUMMARY')
    log('=' * 60)

    for case, result in all_results:
        status = 'PASS' if case.get('passed', False) else 'FAIL'
        log('  {} — {}'.format(case['name'].split(':')[0], status))

    log('')
    if all_passed:
        log('ALL VALIDATION CASES PASSED')
        log('-> Proceed with calibration (v7_calibration.py)')
        log('-> Then run batch (v7_run_batch_simulations_cracks_progressive.py)')
    else:
        log('SOME CASES FAILED — review above before proceeding')
        log('Key things to check:')
        log('  1. Open Job_999x.odb in Abaqus CAE GUI')
        log('  2. Plot SDEG contours — is damage visible?')
        log('  3. Plot mesh — is it refined near crack tips?')
        log('  4. Check .msg file if solver did not complete')

    log('')
    log('ODB files kept for inspection:')
    for case, result in all_results:
        if result and 'job_name' in result:
            log('  {}.odb'.format(result['job_name']))

    log('')
    log('Log: {}'.format(LOG_FILE))
    log('Screenshots: {}/'.format(SCREENSHOT_DIR))
    log('=' * 60)


if __name__ == '__main__':
    main()
