"""
============================================================
ABAQUS TEST SCRIPT V4 — DRAMATIC VISUAL MODEL
============================================================
Purpose: Create a visually impressive plate with 5 defects
         including crack-like slits and varied orientations.
         For poster screenshots and visual verification.

Run with:
    abaqus cae script=test_single_model_v4_dramatic.py
============================================================
"""

from abaqus import *
from abaqusConstants import *
from caeModules import *
import math

# ============================================================
# PARAMETERS — 5 dramatic defects
# ============================================================

PLATE_LENGTH = 100.0
PLATE_WIDTH = 50.0
PLATE_THICKNESS = 2.5

N_HOLES = 5

# Mix of crack-like slits and holes at various angles
HOLES = [
    # Thin crack-like slit, angled — very dramatic
    {'cx': 20.0, 'cy': 25.0, 'sa': 8.0, 'ar': 0.08, 'ang': 30.0},
    # Another crack, different angle
    {'cx': 50.0, 'cy': 38.0, 'sa': 7.0, 'ar': 0.10, 'ang': 120.0},
    # Medium ellipse
    {'cx': 75.0, 'cy': 15.0, 'sa': 5.0, 'ar': 0.35, 'ang': 60.0},
    # Near-circular hole
    {'cx': 45.0, 'cy': 12.0, 'sa': 4.0, 'ar': 0.90, 'ang': 0.0},
    # Small crack near centre
    {'cx': 70.0, 'cy': 35.0, 'sa': 5.5, 'ar': 0.12, 'ang': 160.0},
]

YOUNGS_MODULUS = 210000.0
POISSONS_RATIO = 0.3
YIELD_STRENGTH = 250.0

PRESSURE_X = 100.0
PRESSURE_Y = 40.0

GLOBAL_MESH_SIZE = 3.0
FINE_MESH_SIZE = 0.3   # Extra fine for cracks
HOLE_MESH_SEARCH_BUFFER = 3.0

NUM_SEGMENTS = 36  # Higher resolution for smooth crack edges

MODEL_NAME = 'NHolePlate'
JOB_NAME = 'TestJob_V4_Dramatic'


# ============================================================
# HELPER: Generate rotated ellipse polygon points
# ============================================================
def ellipse_polygon_points(cx, cy, semi_major, semi_minor, angle_deg, n_segments):
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
# HELPER: Validate ellipse fits inside plate
# ============================================================
def validate_ellipse_bounds(cx, cy, semi_a, semi_b, angle_deg,
                            plate_length, plate_width, margin=2.0):
    t = math.radians(angle_deg)
    dx = math.sqrt((semi_a * math.cos(t))**2 + (semi_b * math.sin(t))**2)
    dy = math.sqrt((semi_a * math.sin(t))**2 + (semi_b * math.cos(t))**2)

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
# HELPER: Check ALL pairs of holes for overlap
# ============================================================
def validate_all_no_overlap(holes, margin=2.0):
    min_dist = float('inf')
    n = len(holes)

    for i in range(n):
        for j in range(i + 1, n):
            dist = math.sqrt(
                (holes[j]['cx'] - holes[i]['cx'])**2 +
                (holes[j]['cy'] - holes[i]['cy'])**2)
            required = holes[i]['sa'] + holes[j]['sa'] + margin
            gap = dist - required

            if dist < min_dist:
                min_dist = dist

            if gap < 0:
                print("  WARNING: Holes {} and {} overlap! "
                      "dist={:.1f} < required={:.1f}".format(
                          i + 1, j + 1, dist, required))
                return False, min_dist

    return True, min_dist


# ============================================================
# HELPER: Find edges near a hole for local mesh refinement
# ============================================================
def get_hole_edges(part, hole_cx, hole_cy, semi_major, buffer):
    search_radius = semi_major + buffer
    edge_list = []

    for i in range(len(part.edges)):
        edge = part.edges[i]
        pt = edge.pointOn[0]
        dx = pt[0] - hole_cx
        dy = pt[1] - hole_cy
        dist_2d = math.sqrt(dx**2 + dy**2)

        if dist_2d < search_radius:
            edge_list.append(part.edges[i:i+1])

    if not edge_list:
        return None

    combined = edge_list[0]
    for e in edge_list[1:]:
        combined = combined + e
    return combined


# ============================================================
# VALIDATE
# ============================================================
print("=" * 60)
print("V4 DRAMATIC MODEL — 5 DEFECTS (cracks + holes)")
print("=" * 60)
print("\nValidating parameters...")
print("  Plate: {:.0f} x {:.0f} x {:.1f} mm".format(
    PLATE_LENGTH, PLATE_WIDTH, PLATE_THICKNESS))
print("  Number of defects: {}".format(N_HOLES))

all_valid = True
for idx, h in enumerate(HOLES):
    sb = h['sa'] * h['ar']
    valid = validate_ellipse_bounds(
        h['cx'], h['cy'], h['sa'], sb, h['ang'],
        PLATE_LENGTH, PLATE_WIDTH)
    dtype = 'CRACK' if h['ar'] < 0.2 else ('ellipse' if h['ar'] < 0.8 else 'hole')
    print("  D{}: ({:.1f},{:.1f}) a={:.1f} ar={:.2f} ang={:.0f} [{}] -> {}".format(
        idx + 1, h['cx'], h['cy'], h['sa'], h['ar'], h['ang'],
        dtype, "PASS" if valid else "FAIL"))
    if not valid:
        all_valid = False

no_overlap, min_dist = validate_all_no_overlap(HOLES)
print("  Overlap check: {}".format("PASSED" if no_overlap else "FAILED"))
print("  Min distance: {:.1f} mm".format(min_dist))

if not (all_valid and no_overlap):
    print("\n  *** VALIDATION FAILED ***")
else:
    print("  All checks: PASSED")


# ============================================================
# CREATE MODEL
# ============================================================
print("\nCreating model...")
model = mdb.Model(name=MODEL_NAME)
if 'Model-1' in mdb.models.keys():
    del mdb.models['Model-1']


# ============================================================
# CREATE PLATE WITH ALL DEFECTS (single sketch)
# ============================================================
print("Creating plate with {} defects...".format(N_HOLES))

sketch = model.ConstrainedSketch(name='plateSketch', sheetSize=200.0)
sketch.rectangle(point1=(0.0, 0.0), point2=(PLATE_LENGTH, PLATE_WIDTH))

for idx, h in enumerate(HOLES):
    sb = h['sa'] * h['ar']
    points = ellipse_polygon_points(
        h['cx'], h['cy'], h['sa'], sb, h['ang'], NUM_SEGMENTS)

    for i in range(NUM_SEGMENTS):
        p1 = points[i]
        p2 = points[(i + 1) % NUM_SEGMENTS]
        sketch.Line(point1=p1, point2=p2)

    dtype = 'CRACK' if h['ar'] < 0.2 else ('ellipse' if h['ar'] < 0.8 else 'hole')
    print("  D{}: {} at ({:.1f},{:.1f})".format(idx + 1, dtype, h['cx'], h['cy']))

part = model.Part(name='Plate', dimensionality=THREE_D, type=DEFORMABLE_BODY)
part.BaseSolidExtrude(sketch=sketch, depth=PLATE_THICKNESS)
print("  Plate created")


# ============================================================
# MATERIAL + SECTION
# ============================================================
print("Assigning material...")
material = model.Material(name='Steel')
material.Elastic(table=((YOUNGS_MODULUS, POISSONS_RATIO),))
model.HomogeneousSolidSection(
    name='PlateSection', material='Steel', thickness=None)
region = part.Set(cells=part.cells[:], name='AllCells')
part.SectionAssignment(region=region, sectionName='PlateSection')


# ============================================================
# ASSEMBLY
# ============================================================
print("Creating assembly...")
assembly = model.rootAssembly
assembly.DatumCsysByDefault(CARTESIAN)
instance = assembly.Instance(name='PlateInstance', part=part, dependent=ON)


# ============================================================
# STEP + BOUNDARY CONDITIONS + LOADS
# ============================================================
print("Setting up analysis...")
model.StaticStep(name='LoadStep', previous='Initial')

left_face = instance.faces.findAt(
    ((0.0, PLATE_WIDTH / 2, PLATE_THICKNESS / 2),))
left_region = assembly.Set(faces=left_face, name='LeftFace')
model.EncastreBC(name='FixedLeft', createStepName='Initial', region=left_region)

right_face = instance.faces.findAt(
    ((PLATE_LENGTH, PLATE_WIDTH / 2, PLATE_THICKNESS / 2),))
right_surface = assembly.Surface(side1Faces=right_face, name='RightSurface')
model.Pressure(
    name='PressureX', createStepName='LoadStep',
    region=right_surface, magnitude=PRESSURE_X)

if PRESSURE_Y > 0.0:
    top_face = instance.faces.findAt(
        ((PLATE_LENGTH / 2, PLATE_WIDTH, PLATE_THICKNESS / 2),))
    top_surface = assembly.Surface(side1Faces=top_face, name='TopSurface')
    model.Pressure(
        name='PressureY', createStepName='LoadStep',
        region=top_surface, magnitude=PRESSURE_Y)

print("  Encastre left, biaxial tension right + top")


# ============================================================
# MESH WITH LOCAL REFINEMENT
# ============================================================
print("Meshing...")
part.seedPart(size=GLOBAL_MESH_SIZE, deviationFactor=0.1, minSizeFactor=0.1)

for idx, h in enumerate(HOLES):
    edges = get_hole_edges(
        part, h['cx'], h['cy'], h['sa'], HOLE_MESH_SEARCH_BUFFER)
    if edges is not None:
        part.seedEdgeBySize(
            edges=edges, size=FINE_MESH_SIZE,
            deviationFactor=0.1, constraint=FINER)
        dtype = 'CRACK' if h['ar'] < 0.2 else 'hole'
        print("  D{} [{}]: {:.1f}mm local mesh".format(
            idx + 1, dtype, FINE_MESH_SIZE))

part.generateMesh()

num_nodes = len(part.nodes)
num_elements = len(part.elements)
print("  Mesh: {} nodes, {} elements".format(num_nodes, num_elements))


# ============================================================
# CREATE JOB
# ============================================================
job = mdb.Job(name=JOB_NAME, model=MODEL_NAME, type=ANALYSIS)


# ============================================================
# DONE
# ============================================================
print("\n" + "=" * 60)
print("V4 DRAMATIC MODEL READY")
print("=" * 60)
print("  5 defects: 3 cracks + 1 ellipse + 1 hole")
print("  {} nodes, {} elements".format(num_nodes, num_elements))
print("  Biaxial loading: Px={:.0f}, Py={:.0f} MPa".format(
    PRESSURE_X, PRESSURE_Y))
print("")
print("  Submit job -> Results tab -> Stress contour")
print("  That is your poster screenshot!")
print("=" * 60)
