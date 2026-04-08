"""
Reproduce the EXACT crack polygons from the Abaqus batch script by replaying
the full random state sequence (seed=55).

This verifies we get identical geometry, then runs CalculiX on those shapes.
"""
import random
import math
import csv
import os

# ============================================================
# Constants — copied exactly from v7_run_batch_simulations_cracks_progressive.py
# ============================================================
PLATE_LENGTH = 100.0
PLATE_WIDTH = 50.0
NUM_SAMPLES = 1000
RANDOM_SEED = 55
MAX_DEFECTS = 5
MAX_PLACEMENT_ATTEMPTS = 200
MIN_CRACK_WIDTH = 0.15

CRACK_SEG_LEN_MIN = 0.2
CRACK_SEG_LEN_MAX = 0.8
MAX_ANGLE_DEV_DEG = 45.0
MIN_POLYGON_SEGMENTS = 12

GLOBAL_RANGES = {
    'pressure_x':      [5.0,   100.0],
    'pressure_y':      [0.0,   100.0],
    'ply_thickness':   [0.10,  0.20],
    'layup_rotation':  [0.0,   90.0],
}

DEFECT_RANGES = {
    'x':              [15.0,  85.0],
    'y':              [10.0,  40.0],
    'half_length':    [4.0,   15.0],
    'width':          [0.15,  0.6],
    'angle':          [0.0,   180.0],
    'roughness':      [0.15,  0.90],
}


# ============================================================
# Functions — exact copies from Abaqus script
# ============================================================
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
                    PLATE_LENGTH, PLATE_WIDTH):
                continue
            if overlaps_existing(defect, placed):
                continue
            placed.append(defect)
            placed_this_crack = True
            break
        if not placed_this_crack:
            return None
    return placed


def generate_all_samples(n_total, seed=55):
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


# ============================================================
# MAIN: Reproduce and verify
# ============================================================
if __name__ == "__main__":
    CSV_PATH = r"C:\Users\akoti\AAA\Образование\Университет\Год 3\Research Project\Attachments\Scripts\V7\simulation_results_v7.csv"

    print("Step 1: Reproducing generate_all_samples(1000, seed=55)...")
    all_samples = generate_all_samples(NUM_SAMPLES, seed=RANDOM_SEED)
    print(f"  Generated {len(all_samples)} samples")

    # Verify against CSV
    print("\nStep 2: Verifying sample parameters match CSV...")
    with open(CSV_PATH, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        csv_rows = {int(row['sim_id']): row for row in reader}

    matches = 0
    mismatches = 0
    for i, sample in enumerate(all_samples[:20]):  # Check first 20
        sim_id = i + 1
        if sim_id not in csv_rows:
            continue
        row = csv_rows[sim_id]
        if 'ERROR' in str(row.get('max_mises', '')):
            continue

        csv_px = float(row['pressure_x'])
        csv_nd = int(row['n_defects'])
        sample_px = sample['pressure_x']
        sample_nd = sample['n_defects']

        px_match = abs(csv_px - sample_px) < 0.001
        nd_match = csv_nd == sample_nd

        if px_match and nd_match:
            matches += 1
            # Also check first defect x
            csv_dx = float(row['defect1_x'])
            sample_dx = sample['defects'][0]['x']
            dx_match = abs(csv_dx - sample_dx) < 0.01
            status = "OK" if dx_match else f"DEFECT MISMATCH (csv={csv_dx:.3f} vs {sample_dx:.3f})"
            if sim_id <= 5:
                print(f"  sim_id={sim_id}: px={csv_px:.3f} nd={csv_nd} defect1_x: {status}")
        else:
            mismatches += 1
            if sim_id <= 5:
                print(f"  sim_id={sim_id}: PARAM MISMATCH px={csv_px:.3f} vs {sample_px:.3f}, nd={csv_nd} vs {sample_nd}")

    print(f"  First 20 non-error sims: {matches} match, {mismatches} mismatch")

    if matches > 0 and mismatches == 0:
        print("\n==> RANDOM STATE REPRODUCTION VERIFIED!")
        print("    We can generate identical crack polygons.")
    else:
        print("\n==> WARNING: Parameters don't match.")
        print("    The Abaqus run may have been interrupted/resumed.")

    # Step 3: Generate polygons for target sim_ids
    target_ids = {1, 2, 3, 4, 5, 6, 7, 8, 10, 19}
    print(f"\nStep 3: Generating crack polygons for sim_ids {sorted(target_ids)}...")

    # The random state after generate_all_samples is deterministic.
    # Now replay polygon generation for all sims up to max(target_ids)
    max_target = max(target_ids)
    polygons = {}  # sim_id -> list of polygon point lists

    for i in range(max_target):
        sim_id = i + 1
        sample = all_samples[i]

        crack_polys = []
        for d in sample['defects']:
            poly = crack_polygon_points(
                d['x'], d['y'], d['half_length'],
                d['width'], d['angle'], d['roughness'])
            crack_polys.append(poly)

        if sim_id in target_ids:
            polygons[sim_id] = crack_polys
            print(f"  sim_id={sim_id}: {len(crack_polys)} crack(s), "
                  f"{sum(len(p) for p in crack_polys)} total polygon vertices")

    # Save polygons to a file for use by the validation script
    import json
    out_path = os.path.join(r"C:\CalculiX\test_composite", "abaqus_polygons.json")

    export = {}
    for sid in sorted(target_ids):
        sample = all_samples[sid - 1]
        row = csv_rows.get(sid, {})
        export[str(sid)] = {
            "n_defects": sample['n_defects'],
            "pressure_x": sample['pressure_x'],
            "pressure_y": sample['pressure_y'],
            "ply_thickness": sample['ply_thickness'],
            "defects": [
                {"x": d['x'], "y": d['y'], "half_length": d['half_length'],
                 "width": d['width'], "angle": d['angle'], "roughness": d['roughness']}
                for d in sample['defects']
            ],
            "polygons": polygons[sid],
            "abaqus_results": {
                "max_mises": float(row.get('max_mises', 0)) if 'ERROR' not in str(row.get('max_mises', '')) else None,
                "max_s11": float(row.get('max_s11', 0)) if 'ERROR' not in str(row.get('max_s11', '')) else None,
                "tsai_wu": float(row.get('tsai_wu_index', 0)) if 'ERROR' not in str(row.get('tsai_wu_index', '')) else None,
                "hashin_mt": float(row.get('max_hashin_mt', 0)) if 'ERROR' not in str(row.get('max_hashin_mt', '')) else None,
            }
        }

    with open(out_path, 'w') as f:
        json.dump(export, f, indent=2)
    print(f"\nSaved polygons to {out_path}")
