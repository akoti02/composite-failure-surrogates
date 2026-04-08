"""
============================================================
ABAQUS POST-PROCESSING: TAKE SCREENSHOTS FROM SAVED ODBs
============================================================
V7 — Enhanced for jagged crack visualisation.

Opens each ODB listed in v7_odb_for_screenshots.txt and saves:
  1. Full-plate overview (von Mises + Hashin contours)
  2. Per-crack zoomed views (stress detail around each crack)
  3. Inter-crack ligament views (stress between closest crack pairs)

Reads crack geometry from simulation_results_v7.csv so it knows
where each crack is and how to frame the camera.

MUST be run with a display (GUI mode):
    abaqus cae script=v7_take_screenshots.py

This script exists because session.printToFile() segfaults in
noGUI mode on some Abaqus installations.
============================================================
"""

from abaqus import *
from abaqusConstants import *
from caeModules import *
import os
import csv
import math
import time

# ============================================================
# CONFIG
# ============================================================
ODB_LIST_FILE = 'v7_odb_for_screenshots.txt'
CSV_FILE = 'simulation_results_v7.csv'
SCREENSHOT_DIR = 'v7_sim_captures'
LOG_FILE = 'v7_screenshots_log.txt'

MAX_DEFECTS = 5
PLATE_LENGTH = 100.0  # mm
PLATE_WIDTH = 50.0    # mm

# Zoom padding: how much extra space around a crack (as multiplier of crack extent)
ZOOM_PADDING = 2.0
# Minimum zoom window in mm (don't zoom closer than this)
MIN_ZOOM_WINDOW = 8.0

# Max ODBs to process (0 = all).
MAX_ODBS = 0
# Only process jobs with this many defects (empty list = all)
FILTER_DEFECT_COUNTS = [4, 5]
# Max ODBs per defect count
MAX_PER_DEFECT_COUNT = 5

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
# CSV GEOMETRY LOADER
# ============================================================
def load_crack_geometry(csv_path):
    """
    Read simulation_results_v7.csv and build a dict:
        sim_id -> {
            'n_defects': int,
            'cracks': [{'x', 'y', 'half_length', 'width', 'angle', 'roughness'}, ...]
        }
    Keyed by sim_id (int) AND by job name (e.g. 'Job_0001').
    """
    if not os.path.exists(csv_path):
        log('WARNING: CSV not found: {}. Zoomed views disabled.'.format(csv_path))
        return {}

    geo = {}
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    sim_id = int(float(row.get('sim_id', -1)))
                except (ValueError, TypeError):
                    continue

                try:
                    n_def = int(float(row.get('n_defects', 0)))
                except (ValueError, TypeError):
                    n_def = 0

                cracks = []
                for i in range(1, MAX_DEFECTS + 1):
                    hl_key = 'defect{}_half_length'.format(i)
                    if hl_key not in row:
                        break
                    try:
                        hl = float(row.get(hl_key, 0))
                    except (ValueError, TypeError):
                        hl = 0.0
                    if hl < 0.01:
                        continue  # unused defect slot (zero-padded)
                    try:
                        crack = {
                            'x': float(row.get('defect{}_x'.format(i), 0)),
                            'y': float(row.get('defect{}_y'.format(i), 0)),
                            'half_length': hl,
                            'width': float(row.get('defect{}_width'.format(i), 0)),
                            'angle': float(row.get('defect{}_angle'.format(i), 0)),
                            'roughness': float(row.get('defect{}_roughness'.format(i), 0)),
                        }
                        cracks.append(crack)
                    except (ValueError, TypeError):
                        continue

                entry = {'n_defects': n_def, 'cracks': cracks}
                geo[sim_id] = entry
                # Also key by job name for easy lookup
                job_name = 'Job_{:04d}'.format(sim_id)
                geo[job_name] = entry

        log('Loaded crack geometry for {} simulations from CSV'.format(
            len([k for k in geo if isinstance(k, int)])))
    except Exception as e:
        log('WARNING: Failed to parse CSV: {}'.format(str(e)))

    return geo


# ============================================================
# CRACK BOUNDING BOX MATH
# ============================================================
def crack_bounding_box(crack):
    """
    Compute the axis-aligned bounding box of a crack in global coords.
    Returns (x_min, y_min, x_max, y_max).

    Uses same logic as validate_crack_bounds in the batch script:
    the crack extends half_length along its angle, with lateral
    deviation up to half_length * 0.3 due to roughness.
    """
    cx = crack['x']
    cy = crack['y']
    hl = crack['half_length']
    w = crack['width']
    roughness = crack['roughness']
    angle_deg = crack['angle']

    # Max lateral deviation from centerline (roughness causes zig-zag)
    max_lateral = w / 2.0 + hl * 0.3
    t = math.radians(angle_deg)

    # Extent in x and y from center
    dx = abs(hl * math.cos(t)) + abs(max_lateral * math.sin(t))
    dy = abs(hl * math.sin(t)) + abs(max_lateral * math.cos(t))

    return (cx - dx, cy - dy, cx + dx, cy + dy)


def merge_bounding_boxes(bb1, bb2):
    """Merge two bounding boxes into one that contains both."""
    return (
        min(bb1[0], bb2[0]),
        min(bb1[1], bb2[1]),
        max(bb1[2], bb2[2]),
        max(bb1[3], bb2[3]),
    )


def pad_bounding_box(bb, padding_factor=ZOOM_PADDING, min_window=MIN_ZOOM_WINDOW):
    """Add padding to a bounding box and enforce minimum size."""
    x_min, y_min, x_max, y_max = bb
    w = x_max - x_min
    h = y_max - y_min

    # Add padding as fraction of extent
    pad_x = w * (padding_factor - 1.0) / 2.0
    pad_y = h * (padding_factor - 1.0) / 2.0

    x_min -= pad_x
    y_min -= pad_y
    x_max += pad_x
    y_max += pad_y

    # Enforce minimum window
    cx = (x_min + x_max) / 2.0
    cy = (y_min + y_max) / 2.0
    w = max(x_max - x_min, min_window)
    h = max(y_max - y_min, min_window)

    # Clamp to plate bounds (with small margin)
    x_min = max(0.0, cx - w / 2.0)
    y_min = max(0.0, cy - h / 2.0)
    x_max = min(PLATE_LENGTH, cx + w / 2.0)
    y_max = min(PLATE_WIDTH, cy + h / 2.0)

    return (x_min, y_min, x_max, y_max)


def find_closest_crack_pair(cracks):
    """Find the two closest cracks by center-to-center distance."""
    if len(cracks) < 2:
        return None
    best_dist = 1e9
    best_pair = None
    for i in range(len(cracks)):
        for j in range(i + 1, len(cracks)):
            dist = math.sqrt(
                (cracks[i]['x'] - cracks[j]['x'])**2 +
                (cracks[i]['y'] - cracks[j]['y'])**2)
            if dist < best_dist:
                best_dist = dist
                best_pair = (i, j)
    return best_pair


# ============================================================
# CAMERA CONTROL
# ============================================================
def set_zoomed_view(vp, bb):
    """
    Set viewport camera to frame a 2D bounding box.
    Strategy: fitView first (safe reset), then override width and pan
    to the target center. This two-step approach works across all
    Abaqus versions because it only changes width + cameraTarget.
    """
    x_min, y_min, x_max, y_max = bb
    cx = (x_min + x_max) / 2.0
    cy = (y_min + y_max) / 2.0
    w = x_max - x_min
    h = y_max - y_min

    # Abaqus viewport aspect ratio is ~4:3 (4096x3072)
    vp_aspect = 4096.0 / 3072.0  # ~1.333
    bb_aspect = w / max(h, 0.01)

    if bb_aspect > vp_aspect:
        view_width = w
    else:
        view_width = h * vp_aspect

    # Safety margin so cracks aren't right at the edge
    view_width *= 1.05

    try:
        # Step 1: reset to a known good state
        vp.view.fitView()
        # Step 2: zoom — set width (controls zoom level)
        vp.view.setValues(width=view_width)
        # Step 3: pan — move camera to look at the crack center
        # Get current camera position and shift it to our target
        cur = vp.view.cameraPosition
        cur_target = vp.view.cameraTarget
        # Shift camera so it looks at (cx, cy, 0)
        dx = cx - cur_target[0]
        dy = cy - cur_target[1]
        vp.view.setValues(
            cameraPosition=(cur[0] + dx, cur[1] + dy, cur[2]),
            cameraTarget=(cx, cy, cur_target[2]),
        )
    except Exception as e:
        # Last resort: at least we have the fitView from step 1
        log('    WARNING: zoom/pan failed ({}), using fitView'.format(str(e)))


# ============================================================
# SCREENSHOT SETUP
# ============================================================
def setup_screenshot_quality():
    try:
        session.pngOptions.setValues(imageSize=(4096, 3072))
        session.graphicsOptions.setValues(
            backgroundStyle=SOLID, backgroundColor='#FFFFFF')
        vp = session.viewports['Viewport: 1']
        vp.viewportAnnotationOptions.setValues(
            triad=ON, legend=ON, title=ON, state=ON)
        log('Screenshot quality: 4096x3072 PNG, white background')
    except Exception as e:
        log('WARNING: Could not set screenshot quality: {}'.format(str(e)))


# ============================================================
# CONTOUR SETUP HELPERS
# ============================================================
def setup_mises_contour(vp, odb):
    """Configure viewport for von Mises stress contour on deformed shape."""
    vp.setValues(displayedObject=odb)
    vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
    vp.odbDisplay.setPrimaryVariable(
        variableLabel='S', outputPosition=INTEGRATION_POINT,
        refinement=(INVARIANT, 'Mises'))
    vp.odbDisplay.commonOptions.setValues(
        deformationScaling=UNIFORM, uniformScaleFactor=1.0)


def setup_hashin_contour(vp, odb, component='HSNMTCRT'):
    """Configure viewport for a Hashin damage criterion contour."""
    try:
        step = odb.steps[odb.steps.keys()[0]]
        frame = step.frames[-1]
        if component in frame.fieldOutputs:
            vp.odbDisplay.setPrimaryVariable(
                variableLabel=component, outputPosition=ELEMENT_NODAL)
            return True
        else:
            return False
    except Exception:
        return False


# ============================================================
# MAIN SCREENSHOT FUNCTION
# ============================================================
def take_screenshots(odb_path, crack_info):
    """
    Open an ODB and save:
      1. Full-plate von Mises overview
      2. Full-plate Hashin MT overview
      3. Per-crack zoomed von Mises views
      4. Per-crack zoomed Hashin MT views
      5. Inter-crack ligament view (closest pair)
    """
    basename = os.path.splitext(os.path.basename(odb_path))[0]

    if not os.path.exists(odb_path):
        log('  SKIP (file not found): {}'.format(odb_path))
        return False

    cracks = crack_info.get('cracks', []) if crack_info else []
    n_cracks = len(cracks)
    has_geometry = n_cracks > 0

    odb = None
    try:
        odb = session.openOdb(name=odb_path)
        vp = session.viewports['Viewport: 1']

        # ---- 0. UNDEFORMED MESH ----
        vp.setValues(displayedObject=odb)
        vp.odbDisplay.display.setValues(plotState=(UNDEFORMED,))
        vp.odbDisplay.commonOptions.setValues(
            visibleEdges=FEATURE, renderStyle=FILLED)
        vp.view.fitView()
        mesh_path = os.path.join(SCREENSHOT_DIR, 'mesh_{}'.format(basename))
        session.printToFile(fileName=mesh_path, format=PNG,
                            canvasObjects=(vp,))
        log('  Saved: {}.png (undeformed mesh)'.format(mesh_path))

        # ---- 1. FULL-PLATE VON MISES ----
        setup_mises_contour(vp, odb)
        vp.view.fitView()
        full_path = os.path.join(SCREENSHOT_DIR, 'full_mises_{}'.format(basename))
        session.printToFile(fileName=full_path, format=PNG,
                            canvasObjects=(vp,))
        log('  Saved: {}.png (full-plate Mises)'.format(full_path))

        if not has_geometry:
            log('  No crack geometry available — skipping zoomed views')
            return True

        # ---- 3. PER-CRACK ZOOMED VON MISES ----
        setup_mises_contour(vp, odb)
        for ci, crack in enumerate(cracks):
            bb = crack_bounding_box(crack)
            bb = pad_bounding_box(bb)
            set_zoomed_view(vp, bb)

            zoom_path = os.path.join(
                SCREENSHOT_DIR,
                'zoom_mises_{}_crack{}'.format(basename, ci + 1))
            session.printToFile(fileName=zoom_path, format=PNG,
                                canvasObjects=(vp,))
            log('  Saved: {}.png (crack {} zoom, Mises)'.format(
                zoom_path, ci + 1))

        # ---- 4. INTER-CRACK LIGAMENT VIEW ----
        if n_cracks >= 2:
            pair = find_closest_crack_pair(cracks)
            if pair is not None:
                i, j = pair
                bb1 = crack_bounding_box(cracks[i])
                bb2 = crack_bounding_box(cracks[j])
                merged_bb = merge_bounding_boxes(bb1, bb2)
                merged_bb = pad_bounding_box(merged_bb, padding_factor=1.5)

                # Mises ligament view
                setup_mises_contour(vp, odb)
                set_zoomed_view(vp, merged_bb)
                lig_path = os.path.join(
                    SCREENSHOT_DIR,
                    'ligament_mises_{}_cracks{}_{}'.format(
                        basename, i + 1, j + 1))
                session.printToFile(fileName=lig_path, format=PNG,
                                    canvasObjects=(vp,))
                log('  Saved: {}.png (ligament view, cracks {}&{})'.format(
                    lig_path, i + 1, j + 1))

        return True

    except Exception as e:
        log('  ERROR processing {}: {}'.format(odb_path, str(e)))
        return False

    finally:
        if odb is not None:
            try:
                odb.close()
            except Exception:
                pass


# ============================================================
# EXTRACT SIM_ID FROM JOB NAME
# ============================================================
def extract_sim_id(odb_path):
    """
    Extract sim_id from ODB path like 'Job_0042.odb' -> 42.
    Also returns the job name 'Job_0042' for dict lookup.
    """
    basename = os.path.splitext(os.path.basename(odb_path))[0]
    # Try to parse 'Job_XXXX' format
    parts = basename.split('_')
    if len(parts) >= 2:
        try:
            sim_id = int(parts[-1])
            return sim_id, basename
        except ValueError:
            pass
    return None, basename


# ============================================================
# MAIN
# ============================================================
def main():
    log('=' * 60)
    log('V7 POST-PROCESSING SCREENSHOT SCRIPT (ENHANCED)')
    log('Per-crack zoom + ligament views + Hashin contours')
    log('=' * 60)

    if not os.path.exists(ODB_LIST_FILE):
        log('ERROR: {} not found. Run simulations first.'.format(
            ODB_LIST_FILE))
        return

    if not os.path.exists(SCREENSHOT_DIR):
        os.makedirs(SCREENSHOT_DIR)

    # Load crack geometry from CSV
    geo = load_crack_geometry(CSV_FILE)

    setup_screenshot_quality()

    with open(ODB_LIST_FILE, 'r') as f:
        odb_paths = [line.strip() for line in f if line.strip()]

    # Deduplicate while preserving order
    seen = set()
    unique_paths = []
    for p in odb_paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)

    # Remove paths to ODBs that no longer exist on disk
    existing_paths = [p for p in unique_paths if os.path.exists(p)]
    if len(existing_paths) < len(unique_paths):
        log('Note: {} of {} ODB files exist on disk (others were cleaned up)'.format(
            len(existing_paths), len(unique_paths)))
    unique_paths = existing_paths

    # Filter by defect count if configured
    if FILTER_DEFECT_COUNTS:
        filtered_paths = []
        counts_seen = {}  # n_defects -> count
        for p in unique_paths:
            sim_id, job_name = extract_sim_id(p)
            info = geo.get(job_name) or geo.get(sim_id)
            if info and len(info.get('cracks', [])) in FILTER_DEFECT_COUNTS:
                n_c = len(info['cracks'])
                if counts_seen.get(n_c, 0) < MAX_PER_DEFECT_COUNT:
                    filtered_paths.append(p)
                    counts_seen[n_c] = counts_seen.get(n_c, 0) + 1
        log('Filtered: {} ODBs with {} defects (max {} each)'.format(
            len(filtered_paths), FILTER_DEFECT_COUNTS, MAX_PER_DEFECT_COUNT))
        unique_paths = filtered_paths
    elif MAX_ODBS > 0 and len(unique_paths) > MAX_ODBS:
        log('Limiting to first {} ODBs (MAX_ODBS={})'.format(
            MAX_ODBS, MAX_ODBS))
        unique_paths = unique_paths[:MAX_ODBS]

    log('Found {} ODB files to process'.format(len(unique_paths)))
    log('Crack geometry available for {} simulations'.format(
        len([k for k in geo if isinstance(k, int)])))

    success = 0
    failed = 0
    total_screenshots = 0

    for i, odb_path in enumerate(unique_paths):
        basename = os.path.basename(odb_path)
        log('[{}/{}] Processing: {}'.format(
            i + 1, len(unique_paths), basename))

        # Look up crack geometry
        sim_id, job_name = extract_sim_id(odb_path)
        crack_info = None
        if job_name in geo:
            crack_info = geo[job_name]
        elif sim_id is not None and sim_id in geo:
            crack_info = geo[sim_id]

        if crack_info:
            n_c = len(crack_info.get('cracks', []))
            # Count expected screenshots:
            # 2 full-plate + n_c*2 zoomed + (2 ligament if n_c >= 2)
            expected = 2 + n_c * 2 + (2 if n_c >= 2 else 0)
            log('  {} cracks found, expecting ~{} screenshots'.format(
                n_c, expected))
        else:
            log('  No geometry data — full-plate views only')

        if take_screenshots(odb_path, crack_info):
            success += 1
        else:
            failed += 1

    log('=' * 60)
    log('DONE: {} succeeded, {} failed out of {} total'.format(
        success, failed, len(unique_paths)))
    log('Screenshots saved to: {}/'.format(SCREENSHOT_DIR))
    log('=' * 60)


main()
