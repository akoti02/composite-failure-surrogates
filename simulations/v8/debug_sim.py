import batch_compositeNet as B
import os

os.makedirs(B.WORK_DIR, exist_ok=True)
print("CCX_EXE:", B.CCX_EXE)
print("CCX exists:", os.path.exists(B.CCX_EXE))
print("WORK_DIR:", B.WORK_DIR)

samples = B.generate_samples([1], [1], [1], "flat", "medium", 1, seed=2026)
sample = samples[0]
polys, failures = B.generate_polygons([sample], seed=2026)
nd = sample.get("n_defects", 0)
print("n_defects=", nd, "poly_failures=", failures)
print("Polygon valid:", polys[0] is not None)

# Try meshing only
try:
    result = B.create_plate_with_cracks(
        polys[0], "debug_test",
        geometry="flat", mesh_level="medium")
    if result[0] is None:
        print("Meshing failed: returned None")
    else:
        nodes, elements, bc_sets = result
        print("Meshing OK:", len(nodes), "nodes,", len(elements), "elements")
except Exception as e:
    print("Meshing error:", type(e).__name__, e)

# Try full sim
row = B.run_single_sim((0, sample, polys[0]))
print("solver_completed:", row.get("solver_completed"))
print("n_elements:", row.get("n_elements"))
if row.get("solver_completed") == "YES":
    print("tsai_wu:", row.get("tsai_wu_index"))
