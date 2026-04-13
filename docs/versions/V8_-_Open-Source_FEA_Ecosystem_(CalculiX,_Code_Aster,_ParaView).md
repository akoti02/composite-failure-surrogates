> [!success] Decision Made
> **We are going open-source. No more Abaqus dependency.** CalculiX is the primary solver, Code_Aster is the advanced fracture mechanics option, and ParaView replaces Abaqus CAE for visualisation. The Abaqus Learning Edition's 1000-element cap and university-only license are no longer constraints. Everything runs from the home PC, on Windows 11, for free, with no license server.

---

# Why This Changes Everything

The V7 campaign produced 891 successful simulations on the university Abaqus machine — a dataset that took weeks of booking time, remote sessions, and working around the Learning Edition's 1000-element limit. The open-source ecosystem described below removes **every single one of those constraints:**

- **No element limit** — CalculiX has no mesh size restriction whatsoever
- **No license** — all tools are free and open-source
- **No university machine** — everything runs natively on Windows 11 at home
- **No GUI dependency** — batch-driven, headless execution for 1000+ parametric runs overnight
- **No Abaqus CAE needed** — ParaView handles all post-processing visualisation from CalculiX `.frd` files
- **SDEG = 0 in Abaqus anyway** — the progressive damage output we were chasing in V6/V7 never materialised in Abaqus either, so we lose nothing by switching solvers

The plan: generate 1000 additional CalculiX simulations, pool with the 891 Abaqus V7 results (with a `solver_source` column), and retrain the ML pipeline on ~1900 samples.

---

# Tool #1: CalculiX — Primary Solver (Fastest Abaqus Migration)

## What It Is
CalculiX is a free, open-source implicit static FEA solver written in Fortran/C. It uses a text-based `.inp` format that is **closely modelled on Abaqus syntax**, making it the natural first destination for Abaqus users. The solver runs as a single executable (`ccx.exe`) with no installation wizard — download, add to PATH, run.

## Why We Are Using It
- **Reads our existing `.inp` files** with minimal modification (element type change only)
- **No element count limit** — our V7 meshes were capped at 1000 elements by the Abaqus Learning Edition; CalculiX lifts this entirely
- **Runs on Windows 11 natively** — no WSL, no virtual machine, no university VPN
- **~1 minute per run** for a 100x50 mm plate with ~2000 S8R elements on a modern laptop
- **Headless batch execution** via `subprocess.run(["ccx", "job_name"])` in Python

## Critical Technical Details

**Element type change: S4R → S8R.** This is the one mandatory change. CalculiX's `*SHELL SECTION, COMPOSITE` keyword only works with S8R elements (8-node quadratic shells), which are internally expanded into 20-node brick elements (C3D20R). S4R is not supported for composite layups. For flat plates, S8R is actually *more* accurate than S4R (quadratic vs linear shape functions), so this is an upgrade.

**Per-ply stress output** is written to the `.dat` file in tabular format, with two integration points per ply layer. The `.frd` file (used for ParaView visualisation) carries the expanded 3D solid results but not the per-ply composite breakdown. For ML data extraction, we parse the `.dat` file in Python — which is exactly what we need for batch runs anyway.

**Coordinate transformation required.** Since CalculiX expands shells to 3D solids, the stresses in the `.dat` file are in the expanded solid's global coordinate system. To get per-ply S11, S22, S12 in the material frame, we apply a rotation matrix for each ply angle. This is a straightforward NumPy operation.

**Crack modelling** uses **duplicate nodes** at the crack faces (prepared in Gmsh), leaving those faces as free surfaces to model an open, traction-free slit. No XFEM or cohesive zone for shells — but for failure *initiation* studies (which is what our ML pipeline targets), duplicate nodes are the standard approach.

**Mesh quality note:** The CalculiX community confirms that S8R shells with only one element in a given direction may produce incorrect results — always use at least a 2-element mesh in each in-plane direction.

## Composite Shell Input Example (CalculiX `.inp`)

```ini
*NODE
** mesh nodes...
*ELEMENT, TYPE=S8R, ELSET=PLATE
1, 1, 2, 3, 4, 5, 6, 7, 8
...
*SHELL SECTION, COMPOSITE, ELSET=PLATE, OFFSET=0
** thickness, integration_pts, material_name, ply_angle
0.1875, 3, CFRP_UD, 0.0
0.1875, 3, CFRP_UD, 45.0
0.1875, 3, CFRP_UD, -45.0
0.1875, 3, CFRP_UD, 90.0
0.1875, 3, CFRP_UD, 90.0
0.1875, 3, CFRP_UD, -45.0
0.1875, 3, CFRP_UD, 45.0
0.1875, 3, CFRP_UD, 0.0
*MATERIAL, NAME=CFRP_UD
*ELASTIC, TYPE=ENGINEERING CONSTANTS
** E1, E2, nu12, nu13, nu23, G12, G13, G23
135000.0, 10000.0, 0.27, 0.27, 0.45, 5200.0, 5200.0, 3900.0
*STEP
*STATIC
*DLOAD
PLATE, P, 1.0
*EL FILE
S
*END STEP
```

## Batch Python Driver

```python
import subprocess, os, glob
params = [{"angle": a, "crack_len": c} for a in [0,15,30] for c in [5,10,15,20]]
for i, p in enumerate(params):
    with open(f"run_{i:04d}.inp", "w") as f:
        f.write(generate_inp(p))
    subprocess.run(["ccx", f"run_{i:04d}"], check=True)
    stresses = parse_dat(f"run_{i:04d}.dat")
    hashin = compute_hashin(stresses)
```

## Windows Installation
Download the pre-compiled binary from `calculix.de` — latest stable release is 2.22 (early 2026). Runs natively on Windows. Add `ccx.exe` to system PATH. The PrePoMax GUI can generate `.inp` files as a starting point, but all batch runs are headless.

---

# Tool #2: Code_Aster — Advanced Fracture Mechanics Option

## What It Is
Code_Aster is developed by EDF (Electricite de France) and provides the **most complete open-source capability** for the exact combination of composite shells + crack modelling + per-ply stress extraction. The command files (`.comm`) are Python scripts, making batch execution native.

## Why We Are Considering It
- **Most complete composite + fracture capability** of any open-source tool
- **Per-ply stresses already in the ply material frame** — `SIGM_ELGA` outputs S11, S22, S12 in each ply's local coordinate system, no rotation needed (unlike CalculiX)
- **Three crack modelling approaches:**
  1. `DEFI_FOND_FISS` + `CALC_G` / `POST_K1_K2_K3` — LEFM stress intensity factors (K_I, K_II, K_III) at a defined crack front
  2. `PLAN_ELDI` / `PLAN_JOINT` — cohesive zone elements with `CZM_EXP` traction-separation laws for crack opening and progressive debonding
  3. Simple topological slit in the Salome mesh with free-surface boundary conditions
- **Windows installer available** — version 14.4 from `code-aster-windows.com`, includes `as_run.bat` for headless execution
- **MED output files are HDF5** — parseable in Python via `h5py` without Salome

## Composite Shell .comm Example

```python
DEBUT()
mesh = LIRE_MAILLAGE(FORMAT='MED', UNITE=20)
model = AFFE_MODELE(
    MAILLAGE=mesh,
    AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='COQUE_3D')
)
cfrp_UD = DEFI_MATERIAU(
    ELAS_ORTH=_F(
        E_L=135000.0, E_T=10000.0, E_N=10000.0,
        G_LT=5200.0,  G_LN=5200.0, G_TN=3900.0,
        NU_LT=0.27,   NU_LN=0.27,  NU_TN=0.45,
        RHO=1600.0,
    )
)
material = AFFE_MATERIAU(
    MAILLAGE=mesh,
    AFFE=_F(TOUT='OUI', MATER=cfrp_UD)
)
shell_prop = AFFE_CARA_ELEM(
    MODELE=model,
    COQUE=_F(
        GROUP_MA='plate',
        EPAIS=1.5,
        COQUE_NCOU=8,
        ANGL_REP=(0.0, 0.0),
    ),
    MULTI_COUCHE=(
        _F(EPAIS=0.1875, VECTEUR=(1,0,0)),          # ply 1: 0 deg
        _F(EPAIS=0.1875, VECTEUR=(0.707,0.707,0)),   # 45 deg
        _F(EPAIS=0.1875, VECTEUR=(0.707,-0.707,0)),  # -45 deg
        _F(EPAIS=0.1875, VECTEUR=(0,1,0)),            # 90 deg
        _F(EPAIS=0.1875, VECTEUR=(0,1,0)),            # 90 deg (symmetric)
        _F(EPAIS=0.1875, VECTEUR=(0.707,-0.707,0)),
        _F(EPAIS=0.1875, VECTEUR=(0.707,0.707,0)),
        _F(EPAIS=0.1875, VECTEUR=(1,0,0)),
    )
)
## ... loads, boundary conditions, MECA_STATIQUE, CALC_CHAMP ...
FIN()
```

## Batch Scripting

```python
import subprocess, os
for i, params in enumerate(param_list):
    comm_content = generate_comm_template(params)
    with open(f"run_{i:04d}.comm", "w") as f:
        f.write(comm_content)
    subprocess.run(["as_run", f"run_{i:04d}.export"], check=True)
    results = parse_med_output(f"run_{i:04d}.rmed")
```

## Performance Note
One forum user reported a 10-minute runtime for a Code_Aster composite shell model that ran in 10 seconds in ANSYS. For 500+ batch runs, reducing output verbosity (`IMPR_RESU` options) and using the MPI-enabled build is recommended. The learning curve is steeper than CalculiX.

## Windows Installation
MSI installer from `code-aster-windows.com` — version 14.4. Covers ~90% of Code_Aster functionality (missing: MPI parallelism). Headless via `as_run.bat`.

---

# Tool #3: FinEtoolsFlexStructures.jl — Julia-Native Composite Shells

## What It Is
A pure-Julia FEM package for beams and shells maintained by Petr Krysl (UCSD). As of December 2024, it explicitly supports **layered (laminated, composite) shells** and includes benchmark examples validated against published results. The developer states that "performance in linear shell problems matches the commercial software Abaqus."

## Why It Is Relevant
- **Abaqus-matching accuracy** for layered shells, independently validated
- **Cleanest scripting ergonomics** — pure Julia loops, parameter sweeps, parallel execution via `Distributed.jl` or `Threads.jl`
- **T3FF element** — flat-facet triangular shell element (robust IJNME-published formulation)
- **Fully native on Windows** — install Julia via `juliaup`, then `]add FinEtoolsFlexStructures` in the REPL. No WSL, no C++ compilation
- **ABD stiffness matrix** constructed from per-ply orthotropic material tensors automatically

## Composite Layered Shell Example (Julia)

```julia
using FinEtools
using FinEtoolsFlexStructures.CompositeLayupModule
using FinEtoolsFlexStructures.FEMMShellT3FFModule

cfrp_ply = CompositeLayup.Ply(
    E1 = 135000.0, E2 = 10000.0, G12 = 5200.0, nu12 = 0.27,
    thickness = 0.1875
)
layup = CompositeLayup.Layup([
    (ply = cfrp_ply, angle = 0.0),
    (ply = cfrp_ply, angle = 45.0),
    (ply = cfrp_ply, angle = -45.0),
    (ply = cfrp_ply, angle = 90.0),
    (ply = cfrp_ply, angle = 90.0),
    (ply = cfrp_ply, angle = -45.0),
    (ply = cfrp_ply, angle = 45.0),
    (ply = cfrp_ply, angle = 0.0),
])

results = []
for (crack_len, load) in param_combinations
    fens, fes = mesh_plate_with_crack(100.0, 50.0, crack_len)
    sigma = extract_ply_stresses(model, layup)
    push!(results, (crack_len, load, sigma))
end
```

## Crack Modelling Limitation
No built-in cohesive zone or XFEM. Cracks are introduced via duplicate nodes in the Gmsh-generated mesh — same approach as CalculiX. Valid for failure initiation studies.

## Windows Installation
`juliaup` (official Julia installer for Windows) → `]add FinEtoolsFlexStructures` in the REPL. Zero dependencies beyond Julia's package manager.

---

# Tool #4: ParaView — Visualisation (Replaces Abaqus CAE)

ParaView is the open-source visualisation tool that reads CalculiX `.frd` output files directly. It replaces everything we used Abaqus CAE for: contour plots of von Mises stress, deformed shape views, mesh visualisation, and screenshot generation.

For the ML pipeline, ParaView is a minor player (data extraction is done from `.dat` files in Python), but for report figures and visual verification of results, it is the Abaqus CAE replacement.

---

# Tool #5: Gmsh — Parametric Mesh Generation

Gmsh provides the **parametric mesh generation** capability with a Python API. Critical for our workflow:
- Generate plate geometries with varying crack lengths, positions, and orientations
- Create **duplicate nodes** along crack faces for seam crack modelling
- Export to CalculiX `.inp` format via `gmsh -format inp` or `meshio-convert`
- Script the entire meshing step so that geometry generation → meshing → solver input is fully automated

```python
import gmsh
gmsh.initialize()
## ... create plate geometry ...
crack = gmsh.model.geo.addLine(pt_crack_start, pt_crack_tip)
gmsh.model.geo.synchronize()
gmsh.model.mesh.embed(1, [crack], 2, plate_surface)
gmsh.model.mesh.generate(2)
```

Install: `pip install gmsh` or download from gmsh.info.

---

# Tool #6: composipy & lamipy — Python Post-Processing Companions

These are not FEA solvers but **post-processing companions** that compute Hashin and Tsai-Wu failure indices from per-ply stresses extracted by any solver.

**composipy** (`pip install composipy`):
- Classical Laminate Theory (CLT) stress computation
- `Strength` class with Hashin and Tsai-Wu failure index calculation
- NASTRAN PCOMP API support
- Actively maintained

**lamipy**:
- CLT with progressive failure using the Ply Discount method
- Hashin, Tsai-Wu, Max Stress, Max Strain, and Puck criteria
- Noted as "not ready for general usage" by its author, but the failure criteria implementations are usable directly

## Practical Workflow
Extract per-ply stresses (S11, S22, S12 in material coordinates) from CalculiX `.dat` → pass to composipy/lamipy failure criteria functions → store results per element per ply → CSV for ML pipeline.

## Post-Processing Code

```python
import numpy as np

def hashin_indices(s11, s22, s12, Xt, Xc, Yt, Yc, SL, ST):
    Fft = (s11/Xt)**2 + (s12/SL)**2       if s11 >= 0 else 0.0
    Ffc = (s11/Xc)**2                      if s11 < 0  else 0.0
    Fmt = (s22/Yt)**2 + (s12/SL)**2       if s22 >= 0 else 0.0
    Fmc = ((s22/(2*ST))**2
           + ((Yc/(2*ST))**2 - 1)*(s22/Yc)
           + (s12/SL)**2)                  if s22 < 0  else 0.0
    return Fft, Ffc, Fmt, Fmc

def tsai_wu_index(s11, s22, s12, Xt, Xc, Yt, Yc, SL):
    F1   = 1/Xt - 1/Xc
    F11  = 1/(Xt*Xc)
    F2   = 1/Yt - 1/Yc
    F22  = 1/(Yt*Yc)
    F66  = 1/SL**2
    F12  = -0.5/np.sqrt(F11*F22)
    TW   = (F1*s11 + F2*s22
            + F11*s11**2 + F22*s22**2
            + F66*s12**2 + 2*F12*s11*s22)
    return TW   # failure if TW >= 1.0
```

---

# Recommended Pipeline for V8

1. **Mesh generation:** Python + Gmsh API → parametric `.msh` files (varying crack length, angle, plate dimensions). Duplicate nodes along crack face.
2. **Mesh conversion:** `gmsh -format inp` or `meshio-convert` → CalculiX `.inp` with S8R elements.
3. **Material + layup template:** Master `.inp` template with `*SHELL SECTION, COMPOSITE` for [0/45/-45/90]s.
4. **CalculiX solver:** `subprocess.run(["ccx", f"run_{i:04d}"])` — headless, ~1 min per run.
5. **Per-ply stress extraction:** Parse `.dat` file; rotate stresses to ply material frame.
6. **Failure index computation:** Hashin + Tsai-Wu in NumPy/composipy, per element per ply.
7. **Results aggregation:** Pandas DataFrame → CSV with `solver_source` column → feed into `v7_ml_pipeline.py`.

**Target: 1000 CalculiX runs + 891 Abaqus V7 = ~1900 training samples.**

---

# Windows 11 Installation Summary

| Tool | Installation Method | Notes |
|------|---------------------|-------|
| **CalculiX** | Download `ccx_2.22.exe` from calculix.de | No WSL; add to PATH |
| **Code_Aster** | MSI installer from code-aster-windows.com | Version 14.4; headless via `as_run.bat` |
| **FinEtoolsFlexStructures.jl** | `juliaup` + `]add FinEtoolsFlexStructures` | Fully native on Windows |
| **ParaView** | Download from paraview.org | Reads CalculiX `.frd` files |
| **composipy** | `pip install composipy` | Python companion for failure indices |
| **lamipy** | `pip install lamipy` | Alternative with progressive failure |
| **Gmsh** | `pip install gmsh` or gmsh.info installer | Parametric mesh generation + Python API |

---

# Master Feature Matrix

| Tool | Language | Composite Shell Layup | Per-Ply Stress Out | Crack / Seam | Batch Scripting | Windows 11 | Hashin / Tsai-Wu | Effort |
|------|----------|-----------------------|--------------------|--------------|-----------------|------------|-----------------|--------|
| **CalculiX** | Fortran/C | S8R only | .dat file (2 pts/layer) | Duplicate nodes / TIED contact | Python subprocess | Native binary | Post-process | Low-Medium |
| **Code_Aster** | Python/.comm | COQUE_3D + ELAS_ORTH | SIGM_ELGA per layer | PLAN_ELDI / DEFI_FOND_FISS | .comm = Python script | Windows installer v14.4 | Post-process | Medium-High |
| **FinEtoolsFlexStructures.jl** | Julia | Layered composite shells | Local coord stresses | Duplicate-node seam only | Pure Julia loops | Julia native on Windows | Post-process | Medium |
| **composipy** | Python | CLT only | CLT stresses only | No FEA mesh | Python | Native | **Built-in Hashin + Tsai-Wu** | N/A (companion) |
| **lamipy** | Python | CLT + progressive failure | CLT stresses only | No FEA mesh | Python | Native | **Built-in Hashin + Tsai-Wu** | N/A (companion) |
| **OpenRadioss** | C++ | /FAIL/HASHIN built-in | Yes | Yes | Yes | Yes | **Built-in** | Medium (but explicit-only) |

---

# Other Tools Evaluated (Lower Priority)

- **FEniCSx + FEniCSx-Shells** — Best for custom formulations and phase-field fracture, but composite layup requires manual CLT implementation (~2-4 weeks). Requires WSL on Windows. Very High effort.
- **OpenRadioss** — Only open-source tool with built-in `/FAIL/HASHIN`, but it is an **explicit dynamics solver** designed for crash/impact. Unusable for quasi-static biaxial pressure loading.
- **dune-composites** — Academic C++ module for large-scale composite laminates. HPC-grade preconditioner. Overkill for our plate geometry, non-trivial C++ build on Windows.
- **MOOSE** — XFEM module available, but composite support requires custom material tensor. Complex build.
- **SfePy** — shell10x element is isotropic only. Not applicable.
- **SolidsPy** — 2D plane stress only. Not applicable.
- **Gridap.jl** — Phase-field brittle fracture demonstrated, but composite shell would be manual implementation. Very High effort.

---

---

## Appendix: Full Perplexity AI Research Response (Verbatim)

> The following is the complete, unedited Perplexity AI research response that informed the decisions documented above. Preserved here as a primary reference.

---

## Open-Source FEA for CFRP Composite Shell + Crack Simulations: Full Ecosystem Ranking

## Executive Summary

This report evaluates every major open-source FEA ecosystem across Python, Julia, C++, and Fortran for simulating 2D CFRP composite shell plates ([0/45/-45/90]s layup) under biaxial pressure loading with seam cracks. Five requirements drive the ranking: (1) composite layup with arbitrary ply angles, (2) crack/discontinuity geometry, (3) per-ply stress extraction (S11, S22, S12), (4) scriptable batch execution, and (5) Windows 11 compatibility.

**Bottom line:** No single tool satisfies all five requirements without some custom work. **CalculiX** is the fastest migration from Abaqus due to .inp format similarity, but requires switching from S4R to S8R and manual post-processing of per-ply stresses. **Code_Aster** is the most complete FEA environment for composite shells and crack modeling but has a steep learning curve. **FinEtoolsFlexStructures.jl** (Julia) is the cleanest scripting path for composite layup accuracy with Windows-native Julia, but crack handling requires manual mesh preparation. All three tools require per-ply Hashin/Tsai-Wu failure indices to be computed in post-processing Python or Julia code — none have them built-in for shell composites.

---

# Master Feature Matrix

| Tool | Language | Composite Shell Layup | Per-Ply Stress Out | Crack / Seam | Batch Scripting | Windows 11 | Hashin / Tsai-Wu | Effort to Start |
|------|----------|-----------------------|--------------------|--------------|-----------------|------------|-----------------|-----------------|
| **CalculiX** | Fortran/C | S8R only [1] | .dat file (2 pts/layer) [1] | Duplicate nodes / TIED contact [2] | Python subprocess | Native binary | Post-process [1] | Low-Medium |
| **Code_Aster** | Python/.comm | COQUE_3D + ELAS_ORTH [3][4] | SIGM_ELGA per layer [5] | PLAN_ELDI / DEFI_FOND_FISS [6][7] | .comm = Python script [8] | Windows installer v14.4 [9] | Post-process | Medium-High |
| **FinEtoolsFlexStructures.jl** | Julia | Layered composite shells [10] | Local coord stresses | Duplicate-node seam only | Pure Julia loops | Julia native on Windows | Post-process | Medium |
| **FEniCSx + FEniCSx-Shells** | Python | Manual CLT implementation [11] | Custom UFL post-proc | Phase-field [12] | Python | WSL required [13] | No | Very High |
| **SfePy** | Python | shell10x is isotropic only [14] | N/A | N/A | Python | Cross-platform | No | Not applicable |
| **dune-composites** | C++ / DUNE | 3D anisotropic laminates [15] | Yes | Research code | C++ build | Complex build | No | Very High |
| **MOOSE** | C++ | Via material tensor | Yes | XFEM module | Python interface | Build required | No | Very High |
| **OpenRadioss** | C++ | /FAIL/HASHIN built-in! | Yes | Yes | Yes | Yes | Built-in! | Medium |
| **composipy** | Python | CLT only [16] | CLT stresses only | No FEA mesh | Python | Yes | Hashin + Tsai-Wu | N/A (companion) |
| **lamipy** | Python | CLT + progressive failure [17] | CLT stresses only | No FEA mesh | Python | Yes | Hashin + Tsai-Wu | N/A (companion) |
| **SolidsPy** | Python | 2D plane stress only [18] | 2D only | No | Python | Yes | No | Not applicable |
| **Gridap.jl** | Julia | Manual implementation | Manual | Phase-field fracture [12] | Julia | Yes | No | Very High |

---

## Tier 1: Best Overall Choices

## 1. CalculiX — Fastest Migration from Abaqus

CalculiX uses a text-based `.inp` format closely modeled on Abaqus syntax, making it the natural first destination for Abaqus users. However, there is one critical constraint that affects this migration: the `*SHELL SECTION, COMPOSITE` keyword only works with `S8R` elements (which are internally expanded into 20-node brick elements `C3D20R`), not with `S4R`. The S8R expansion into 3D solids provides two integration points per ply layer, which delivers accurate bending and membrane behavior for thin laminated plates.[1][19]

Per-ply stress output is written to the `.dat` file in tabular format, with two integration points per ply. The `.frd` file used for contour visualization does not carry per-ply composites — only the expanded 3D solid results are available there. For batch runs, this is not a limitation: a Python script can trivially parse the `.dat` file and compute Hashin/Tsai-Wu indices per element per ply.[1]

**Crack modeling in CalculiX** does not include XFEM or a cohesive zone model for shell elements. The practical approach for a narrow slit crack is to prepare the mesh with **duplicate nodes** at the crack faces (e.g., using Gmsh's `setCompound` or node duplication), leaving those faces as free surfaces. A pre-existing delamination or interface debond can be approximated with a `*CONTACT PAIR` using `SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=TIED` initially, then released by changing the contact interaction. For a simple seam crack in a plate, duplicate nodes are the least-effort approach.[2]

**Composite shell input example (CalculiX .inp):**

```ini
*NODE
** mesh nodes...
*ELEMENT, TYPE=S8R, ELSET=PLATE
1, 1, 2, 3, 4, 5, 6, 7, 8
...
*SHELL SECTION, COMPOSITE, ELSET=PLATE, OFFSET=0
** thickness, integration_pts, material_name, ply_angle
0.1875, 3, CFRP_UD, 0.0
0.1875, 3, CFRP_UD, 45.0
0.1875, 3, CFRP_UD, -45.0
0.1875, 3, CFRP_UD, 90.0
0.1875, 3, CFRP_UD, 90.0
0.1875, 3, CFRP_UD, -45.0
0.1875, 3, CFRP_UD, 45.0
0.1875, 3, CFRP_UD, 0.0
*MATERIAL, NAME=CFRP_UD
*ELASTIC, TYPE=ENGINEERING CONSTANTS
** E1, E2, nu12, nu13, nu23, G12, G13, G23
135000.0, 10000.0, 0.27, 0.27, 0.45, 5200.0, 5200.0, 3900.0
*STEP
*STATIC
*DLOAD
PLATE, P, 1.0
*EL FILE
S
*END STEP
```

**Batch Python driver:**

```python
import subprocess, os, glob
params = [{"angle": a, "crack_len": c} for a in [0,15,30] for c in [5,10,15,20]]
for i, p in enumerate(params):
    with open(f"run_{i:04d}.inp", "w") as f:
        f.write(generate_inp(p))
    subprocess.run(["ccx", f"run_{i:04d}"], check=True)
    stresses = parse_dat(f"run_{i:04d}.dat")
    hashin = compute_hashin(stresses)
```

**Windows setup:** Download the pre-compiled CalculiX binary from `calculix.de`. The latest stable release (2.22 as of early 2026) runs natively on Windows or under WSL. The PrePoMax GUI can generate `.inp` files as a starting point, but all batch runs can be driven headlessly.[20]

**Key limitation:** The CalculiX community forum confirms that S8R shells with only one element in a given direction may produce incorrect results — always use at least a 2-element mesh in each in-plane direction. Also, since CalculiX expands shells to 3D solids, extracting stresses in the original ply material coordinate system (S11, S22, S12) requires a coordinate transformation from the expanded solid's global stress tensor back to the ply frame.[21]

---

## 2. Code_Aster — Most Complete Capability for Composite + Crack

Code_Aster, developed by EDF (Electricite de France), provides the most complete open-source capability for the exact combination of requirements in this use case: composite shell elements with per-ply orthotropic properties, multiple crack modeling approaches, and Python-native scripting. The trade-off is a steep initial learning curve for the `.comm` command file syntax.[3][8]

**Composite shell definition** uses `AFFE_MODELE` with `MODELISATION='COQUE_3D'`, and materials are defined per-ply using `DEFI_MATERIAU` with `ELAS_ORTH` (fully orthotropic elasticity: E1, E2, G12, nu12, etc.). Per-ply stresses are accessed via `CALC_CHAMP` requesting `SIGM_ELGA` (stresses at Gauss integration points) — these are naturally expressed in each ply's local material coordinate system, exactly the S11, S22, S12 needed for Hashin post-processing.[4][5][3]

**Crack modeling** in Code_Aster is the most capable among open-source tools. Two approaches are relevant:[6][7]

- `DEFI_FOND_FISS` + `CALC_G` / `POST_K1_K2_K3`: LEFM fracture mechanics (stress intensity factors) for a defined crack front — appropriate if the goal is to study fracture parameters at a pre-existing crack tip.
- `PLAN_ELDI` / `PLAN_JOINT` modelling: Discontinuity elements that can carry cohesive zone (traction-separation) laws using `CZM_EXP` — appropriate for studying crack opening and progressive debonding.
- Simpler seam slit: create a topological slit in the Salome mesh and impose free-surface boundary conditions on crack faces.

**Composite shell .comm example:**

```python
DEBUT()
mesh = LIRE_MAILLAGE(FORMAT='MED', UNITE=20)
model = AFFE_MODELE(
    MAILLAGE=mesh,
    AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='COQUE_3D')
)
cfrp_UD = DEFI_MATERIAU(
    ELAS_ORTH=_F(
        E_L=135000.0, E_T=10000.0, E_N=10000.0,
        G_LT=5200.0,  G_LN=5200.0, G_TN=3900.0,
        NU_LT=0.27,   NU_LN=0.27,  NU_TN=0.45,
        RHO=1600.0,
    )
)
material = AFFE_MATERIAU(
    MAILLAGE=mesh,
    AFFE=_F(TOUT='OUI', MATER=cfrp_UD)
)
shell_prop = AFFE_CARA_ELEM(
    MODELE=model,
    COQUE=_F(
        GROUP_MA='plate',
        EPAIS=1.5,
        COQUE_NCOU=8,
        ANGL_REP=(0.0, 0.0),
    ),
    MULTI_COUCHE=(
        _F(EPAIS=0.1875, VECTEUR=(1,0,0)),
        _F(EPAIS=0.1875, VECTEUR=(0.707,0.707,0)),
        _F(EPAIS=0.1875, VECTEUR=(0.707,-0.707,0)),
        _F(EPAIS=0.1875, VECTEUR=(0,1,0)),
        _F(EPAIS=0.1875, VECTEUR=(0,1,0)),
        _F(EPAIS=0.1875, VECTEUR=(0.707,-0.707,0)),
        _F(EPAIS=0.1875, VECTEUR=(0.707,0.707,0)),
        _F(EPAIS=0.1875, VECTEUR=(1,0,0)),
    )
)
## ... loads, boundary conditions, MECA_STATIQUE, CALC_CHAMP ...
FIN()
```

**Scripting for batch runs:** Since `.comm` files are Python scripts executed by Code_Aster's Python runtime, a batch loop can be driven from an outer Python process that generates `.comm` files from templates and invokes `as_run` from the command line:[22]

```python
import subprocess, os
for i, params in enumerate(param_list):
    comm_content = generate_comm_template(params)
    with open(f"run_{i:04d}.comm", "w") as f:
        f.write(comm_content)
    subprocess.run(["as_run", f"run_{i:04d}.export"], check=True)
    results = parse_med_output(f"run_{i:04d}.rmed")
```

**Windows:** A native Windows installer is available from `code-aster-windows.com` (version 14.4), which includes `as_run.bat` for headless command-line execution. This version covers approximately 90% of Code_Aster functionality, with the missing 10% being primarily MPI parallelism. The MED file output can be parsed in Python using the `h5py` library (MED files are HDF5) to extract per-ply stress tensors without Salome.[23][9]

**Performance note:** One forum user reported a 10-minute runtime for a Code_Aster composite shell model that ran in 10 seconds in ANSYS, attributing this partly to console output overhead and integration-point density in multi-layer shells. For 500+ batch runs, reducing output verbosity (`IMPR_RESU` options) and using the MPI-enabled build (available on request from code-aster-windows.com) is recommended.[22]

---

## 3. FinEtoolsFlexStructures.jl — Cleanest Scripting with Abaqus-Level Accuracy

`FinEtoolsFlexStructures.jl` is a pure-Julia FEM package for beams and shells maintained by Petr Krysl (UCSD). As of December 2024, it explicitly supports **layered (laminated, composite) shells** and includes benchmark examples for angle-ply and cross-ply laminated composites validated against published results. The developer states that "performance in linear shell problems matches the commercial software Abaqus". Julia's package manager makes installation reproducible, and Julia runs natively on Windows without WSL.[10][24]

The shell element is a flat-facet triangular T3FF element (based on a robust formulation published in the International Journal for Numerical Methods in Engineering). The layered shell module constructs the ABD stiffness matrix from per-ply orthotropic material tensors, with each ply defined by its angle, thickness, and orthotropic material constants (E1, E2, G12, nu12, etc.).[25][26][10]

**Composite layered shell example (Julia):**

```julia
using FinEtools
using FinEtoolsFlexStructures.CompositeLayupModule
using FinEtoolsFlexStructures.FEMMShellT3FFModule
using FinEtoolsFlexStructures.ViscoelasticityModule

cfrp_ply = CompositeLayup.Ply(
    E1 = 135000.0, E2 = 10000.0, G12 = 5200.0, nu12 = 0.27,
    thickness = 0.1875
)
layup = CompositeLayup.Layup([
    (ply = cfrp_ply, angle = 0.0),
    (ply = cfrp_ply, angle = 45.0),
    (ply = cfrp_ply, angle = -45.0),
    (ply = cfrp_ply, angle = 90.0),
    (ply = cfrp_ply, angle = 90.0),
    (ply = cfrp_ply, angle = -45.0),
    (ply = cfrp_ply, angle = 45.0),
    (ply = cfrp_ply, angle = 0.0),
])

results = []
for (crack_len, load) in param_combinations
    fens, fes = mesh_plate_with_crack(100.0, 50.0, crack_len)
    sigma = extract_ply_stresses(model, layup)
    push!(results, (crack_len, load, sigma))
end
```

**Crack modeling** is the main gap. `FinEtoolsFlexStructures.jl` has no built-in cohesive zone or XFEM. The recommended approach for a seam crack is to generate the mesh in Gmsh with duplicate nodes along the crack line (using `gmsh.model.mesh.setCompound` or physical group tagging), then constrain or leave free the duplicate DOFs to represent an open or closed crack. This is exactly how seam cracks are typically handled in any shell FEA code, including early Abaqus workflows before XFEM.[10]

**Batch scripting** is native Julia: for loops, parameter sweeps, and parallel execution via `Distributed.jl` or `Threads.jl` are all possible without any infrastructure beyond Julia itself.

**Windows setup:** Install Julia via `juliaup` (the official Julia installer for Windows), then `]add FinEtoolsFlexStructures` in the Julia REPL. No WSL, no C++ compilation, no dependencies beyond Julia's package manager.[27][25]

---

## Tier 2: High Effort, Specific Advantages

## 4. FEniCSx + FEniCSx-Shells

FEniCSx-Shells is an experimental extension providing Reissner-Mindlin and Kirchhoff-Love plate/shell implementations for the DOLFINx finite element platform. The critical limitation for this use case is that **composite layup with per-ply orthotropic stiffness is not built-in** — it must be implemented manually by constructing the ABD matrix in UFL (Unified Form Language) and applying it as a custom constitutive law. This is tractable for a researcher familiar with UFL and CLT but represents perhaps 2-4 weeks of implementation work compared to CalculiX or FinEtools.[11]

FEniCSx has strong support for crack and fracture problems. The FEniCSx community has published phase-field fracture implementations, and Gridap.jl (Julia, same paradigm) has demonstrated open-source phase-field brittle fracture for notched plates. For a seam-type crack (not a propagating crack), one can simply mark facets as internal boundaries and apply prescribed displacement or traction conditions.[12]

FEniCSx is **not available natively on Windows** due to its PETSc dependency. WSL2 (Windows Subsystem for Linux) is required, which works well but adds an installation layer.[13]

## 5. OpenRadioss — The One Tool with Built-In Hashin

OpenRadioss (the open-sourced version of Altair Radioss, formerly PRADIOSS) is the **only** open-source code in this survey with a genuine `/FAIL/HASHIN` built-in material card for composite shells. It defines fiber tension/compression and matrix tension/compression failure modes in the Hashin 1980 form, and supports multi-ply composite shell definitions with arbitrary ply angles.

The fundamental incompatibility with this use case is that OpenRadioss is an **explicit dynamics solver** designed for high-speed impact, crash, and manufacturing simulations. Applying it to quasi-static biaxial pressure on a plate will either require extremely long simulation times (running to pseudo-static equilibrium) or produce physically incorrect inertial artifacts. For a fracture mechanics study of cracked composite plates under static pressure loading, OpenRadioss is not the right tool despite its superior built-in damage modeling.

## 6. dune-composites (C++/DUNE)

`dune-composites` is an academic C++ module built on the DUNE numerical framework, specifically designed for large-scale composite laminate simulations. It uses a custom preconditioner guaranteeing mesh-independent iteration counts for highly anisotropic laminates — a genuine technical innovation for aerospace-scale models with millions of degrees of freedom. For a 100x50 mm plate with 500 parametric runs, this HPC machinery is unnecessary, and the C++ DUNE build system is non-trivial to set up on Windows.[15][28]

---

## Tier 3: Companion Tools (No FEA Mesh)

## Python CLT Libraries: composipy and lamipy

These tools do not perform FEA but are valuable as **post-processing companions** once per-ply stresses are extracted from any FEA solver.

**composipy** (`pip install composipy`) computes classical laminate theory (CLT) stresses, implements a `Strength` class with Hashin and Tsai-Wu failure index calculation, and has NASTRAN PCOMP API support. It is actively maintained and installable in seconds.[16]

**lamipy** implements CLT with progressive failure using the Ply Discount method and includes Hashin, Tsai-Wu, Max Stress, Max Strain, and Puck criteria. It is noted as "not ready for general usage" by its author but the failure criteria implementations can be used directly.[17]

The practical workflow: extract element-level per-ply stresses (S11, S22, S12 in material coordinates) from CalculiX, Code_Aster, or FinEtools, then pass them to composipy/lamipy's failure criteria functions element-by-element across all plies.

---

## Hashin and Tsai-Wu Post-Processing

Since no shell-composite FEA tool in the open-source ecosystem provides built-in Hashin or Tsai-Wu output (except OpenRadioss, which is explicit-only), a Python post-processor is the standard approach. The criteria are closed-form and trivial to implement once per-ply stresses are available.

**Hashin 1980 failure indices** (plane-stress form, 4 modes):

$$F_{ft} = \left(\frac{\sigma_{11}}{X_t}\right)^2 + \left(\frac{\sigma_{12}}{S_L}\right)^2$$

$$F_{fc} = \left(\frac{\sigma_{11}}{X_c}\right)^2$$

$$F_{mt} = \left(\frac{\sigma_{22}}{Y_t}\right)^2 + \left(\frac{\sigma_{12}}{S_L}\right)^2$$

$$F_{mc} = \left(\frac{\sigma_{22}}{2S_T}\right)^2 + \left[\left(\frac{Y_c}{2S_T}\right)^2 - 1\right]\frac{\sigma_{22}}{Y_c} + \left(\frac{\sigma_{12}}{S_L}\right)^2$$

**Tsai-Wu** (plane stress):

$$F_1\sigma_{11} + F_2\sigma_{22} + F_{11}\sigma_{11}^2 + F_{22}\sigma_{22}^2 + F_{66}\sigma_{12}^2 + 2F_{12}\sigma_{11}\sigma_{22} = 1$$

where $F_1 = \frac{1}{X_t} - \frac{1}{X_c}$, $F_{11} = \frac{1}{X_t X_c}$, $F_2 = \frac{1}{Y_t} - \frac{1}{Y_c}$, $F_{22} = \frac{1}{Y_t Y_c}$, $F_{66} = \frac{1}{S_L^2}$, and $F_{12}$ is determined empirically (commonly set to $-\frac{1}{2\sqrt{F_{11}F_{22}}}$).[29]

**Python post-processor:**

```python
import numpy as np
def hashin_indices(s11, s22, s12, Xt, Xc, Yt, Yc, SL, ST):
    Fft = (s11/Xt)**2 + (s12/SL)**2       if s11 >= 0 else 0.0
    Ffc = (s11/Xc)**2                      if s11 < 0  else 0.0
    Fmt = (s22/Yt)**2 + (s12/SL)**2       if s22 >= 0 else 0.0
    Fmc = ((s22/(2*ST))**2
           + ((Yc/(2*ST))**2 - 1)*(s22/Yc)
           + (s12/SL)**2)                  if s22 < 0  else 0.0
    return Fft, Ffc, Fmt, Fmc

def tsai_wu_index(s11, s22, s12, Xt, Xc, Yt, Yc, SL):
    F1   = 1/Xt - 1/Xc
    F11  = 1/(Xt*Xc)
    F2   = 1/Yt - 1/Yc
    F22  = 1/(Yt*Yc)
    F66  = 1/SL**2
    F12  = -0.5/np.sqrt(F11*F22)
    TW   = (F1*s11 + F2*s22
            + F11*s11**2 + F22*s22**2
            + F66*s12**2 + 2*F12*s11*s22)
    return TW   # failure if TW >= 1.0

for elem_id, ply_stresses in simulation_results.items():
    for ply_idx, (s11, s22, s12) in enumerate(ply_stresses):
        h = hashin_indices(s11, s22, s12, *cfrp_strengths)
        tw = tsai_wu_index(s11, s22, s12, *cfrp_strengths)
        critical_ply = (elem_id, ply_idx, max(h), tw)
```

---

## Crack Modeling Strategies for Shell FEA

Seam cracks (narrow slits / partition-based discontinuities) can be introduced into any of the recommended tools using meshing techniques rather than solver-level fracture mechanics features. This is appropriate for **failure initiation studies** (which stress and failure index field does a crack produce?) rather than crack propagation studies.

## Method 1: Duplicate Nodes (All Tools)

Generate the mesh with **coincident duplicate nodes** along the crack faces using Gmsh. The two sets of nodes occupy the same geometric location but belong to different elements on either side of the crack. Leave the duplicate-node faces as free surfaces (no boundary condition), which models an open, traction-free slit. This is the zero-effort approach for a pre-existing crack and is valid for any mesh-based FEA solver including CalculiX, Code_Aster, and FinEtools.

Gmsh scripting for a crack slit in a 2D plate:

```python
import gmsh
gmsh.initialize()
## ... create plate geometry ...
crack = gmsh.model.geo.addLine(pt_crack_start, pt_crack_tip)
gmsh.model.geo.synchronize()
gmsh.model.mesh.embed(1, [crack], 2, plate_surface)
gmsh.model.mesh.generate(2)
```

## Method 2: Code_Aster PLAN_ELDI Cohesive Elements

For crack opening and energy release analysis, Code_Aster's `PLAN_ELDI` elements sit along the crack line and carry a cohesive zone traction-separation law (`CZM_EXP`). This is validated in Code_Aster test cases `SSNP128` and `SSNP133` and is the appropriate method if studying crack opening displacement or mixed-mode fracture parameters.[7]

## Method 3: Code_Aster DEFI_FOND_FISS (LEFM)

For stress intensity factor computation at a crack tip (without crack propagation), `DEFI_FOND_FISS` defines the crack front geometry in the mesh, and `CALC_G` / `POST_K1_K2_K3` extract the energy release rate and K_I, K_II, K_III. This approach is well-suited to comparing K fields across the 500-run parametric study.[30][6]

## Method 4: Phase-Field (FEniCSx / Gridap.jl)

Phase-field fracture replaces a discrete crack with a diffuse damage band parameterized by a scalar damage variable d. Gridap.jl has a published implementation for brittle fracture. This approach does not require pre-defined crack geometry and can capture crack nucleation and path evolution, making it the most physically complete option — but it adds implementation complexity and requires careful calibration of the regularization length parameter l.[12]

---

## Recommended Workflow for 500+ Parametric Runs

The most practical setup for a student without an Abaqus license is a **CalculiX + Python** pipeline:

1. **Mesh generation:** Python + Gmsh API to generate parametric `.msh` files (varying crack length, crack angle, plate dimensions). Duplicate nodes along crack face programmatically.
2. **Mesh conversion:** `gmsh -format inp` or `meshio-convert` to produce CalculiX `.inp` files with S8R elements.
3. **Material + layup template:** A master `.inp` template with `*SHELL SECTION, COMPOSITE` for [0/45/-45/90]s with substitution placeholders.
4. **CalculiX solver:** `subprocess.run(["ccx", f"run_{i:04d}"])` — no GUI, pure command line.[20]
5. **Per-ply stress extraction:** Parse `.dat` file; transform stresses from expanded-solid coordinates back to ply material frame using the rotation matrix for each ply angle.
6. **Failure index computation:** Apply Hashin and Tsai-Wu formulae in NumPy (composipy can assist), store results per element per ply.
7. **Results aggregation:** Pandas DataFrame → CSV/HDF5 for the entire parametric space.

This pipeline has no GUI dependency, runs entirely on Windows 11 without WSL, and each CalculiX run for a 100x50 mm plate with a modest mesh (~2000 S8R elements) completes in under a minute on a modern laptop.

---

# Windows 11 Installation Summary

| Tool | Installation Method | Notes |
|------|---------------------|-------|
| CalculiX | Download `ccx_2.22.exe` from calculix.de | No WSL needed; add to PATH [20] |
| Code_Aster | MSI installer from code-aster-windows.com | Version 14.4; headless via `as_run.bat` [9][23] |
| FinEtoolsFlexStructures.jl | `juliaup` + `]add FinEtoolsFlexStructures` | Fully native on Windows [27][10] |
| FEniCSx | WSL2 + Ubuntu + `pip install fenics-dolfinx` | Not available natively [13] |
| composipy | `pip install composipy` (standard Python) | Companion post-processing tool [16] |
| Gmsh | `pip install gmsh` or gmsh.info installer | Parametric mesh generation + Python API |

---

## Ranking Summary

Ranked by the composite criterion: (a) time to get composite shell + crack running x (b) accuracy x (c) Windows compatibility:

1. **CalculiX** — Lowest migration effort from Abaqus; near-Abaqus accuracy for linear composite shells; native Windows binary. Main gotcha: must use S8R (not S4R) and parse per-ply stresses from `.dat`.
2. **FinEtoolsFlexStructures.jl** — Best scripting ergonomics for parametric batch runs; Abaqus-matching accuracy for layered shells; native Windows. Requires learning Julia and manual crack mesh preparation.
3. **Code_Aster** — Richest composite + fracture capability (PLAN_ELDI, DEFI_FOND_FISS, per-ply SIGM_ELGA); native Windows installer. Steepest learning curve of the three; slower runtime for large composite models without MPI.
4. **FEniCSx** — Best flexibility for custom formulations and phase-field fracture; excellent batch scripting in pure Python. Requires WSL on Windows and significant implementation work for composite layup.
5. **OpenRadioss** — Only tool with built-in Hashin damage; but explicit-dynamics-only makes it unsuitable for quasi-static biaxial pressure loading.

For the specific use case described — linear elastic CFRP plate, failure initiation study, seam crack geometry, 500+ parametric runs on Windows 11 — **CalculiX with a Python batch driver and post-processing in composipy/NumPy** represents the shortest path to valid results.

---

# V8 Batch Run Log (20,000+ Simulations)

## 28 March 2026 — 20k Parallel Batch Setup

### Previous Completed Run
- **3,000 simulations** completed successfully on 27 March (serial, seed=42)
- Results: `calculix_results_3000.csv` (1.2 MB), ~7.6% solver failure rate
- Average time per sim: 24.1s (serial)
- Element type: S6 (6-node quadratic triangle), mesh: SizeMin=0.5, SizeMax=3.0

### Previous Crashed Attempt (28 March ~01:00)
- Attempted 20,750 sims with 14 parallel workers via `batch_3000_parallel.py`
- The monitoring session crashed, killing all 14 ccx processes
- No output CSV was produced — zero results saved from this attempt
- Root cause: session crash, not script failure

### 20k Batch Script: `batch_20k.py`
- **Location**: `C:\CalculiX\test_composite\batch_20k.py`
- **Seed**: 101 (independent from 3k run seed=42)
- **Target**: 20,750 samples (4,150 per defect count 1-5)
- **CSV columns**: 103 (includes engineered features: cos/sin angle, aspect ratio, SIF estimate, ligament ratio, boundary proximity)
- **Resume support**: reads existing CSV and skips completed sim_ids
- **Periodic backup**: every 500 completed sims
- **Logging**: `batch_20k.log` with timestamps

### Testing Results (28 March 02:50-03:10)

| Test | Workers | Sims | OK | Fail | Sims/min | Notes |
|------|---------|------|----|------|----------|-------|
| Serial baseline | 1 | 1 | 1 | 0 | 6.8 | Pipeline verified |
| Small parallel | 12 | 10 | 10 | 0 | 8.7 | All passed |
| Medium parallel | 12 | 50 | 50 | 0 | 16.7 | Resume verified |

### Worker Count Benchmark (shared directory, before fix)

| Workers | OK/40 | Fail/40 | Fail% | Sims/min |
|---------|-------|---------|-------|----------|
| 8 | 40 | 0 | 0% | 9.0 |
| 10 | 40 | 0 | 0% | 9.0 |
| 12 | 39 | 1 | 2.5% | 9.4 |
| 14 | 34 | 6 | 15% | 10.0 |
| 16 | 30 | 10 | 25% | 14.1 |

> [!danger] File Contention Bug Found
> **Failure rate scales with worker count** — 0% at 8-10 workers, 15% at 14, 25% at 16. Root cause: all ccx processes writing to the same directory causes file contention. Fix: per-worker temp directories (`tempfile.mkdtemp`) so each ccx instance runs in isolation.

### Fix Applied: Per-Worker Temp Directories
- Each worker creates `ccx_{sim_id}_XXXXX/` temp dir inside `WORK_DIR`
- .inp written to temp dir, ccx runs with `cwd=tmp_dir`
- .dat parsed from temp dir, then entire temp dir deleted
- No shared file access between workers

### Re-Benchmark With Temp Dirs (results unchanged — memory pressure is the real cause)

| Workers | OK/40 | Fail/40 | Fail% | Sims/min |
|---------|-------|---------|-------|----------|
| 8 | 40 | 0 | 0% | 9.1 |
| **10** | **40** | **0** | **0%** | **9.9** |
| 12 | 38 | 2 | 5% | 9.2 |
| 14 | 34 | 6 | 15% | 10.6 |
| 16 | 29 | 11 | 28% | 14.3 |

> [!tip] Conclusion: 10 workers is optimal
> 10 workers has **zero failures** and the highest *successful* sims/min. 14-16 workers cause memory pressure that crashes the solver on larger meshes.

### Final Validation Test (production seed=101)
- 100 sims, 10 workers, 0% failure, 15.3 sims/min
- CSV validated: 101 lines (header + 100 rows), 103 columns

### Safety Features Added
- Auto-pause if failure rate exceeds 10% (after 200+ sims)
- Periodic CSV backup every 500 sims
- Full log file: `batch_20k.log`

### PRODUCTION RUN LAUNCHED: 28 March 2026, 03:48 UTC
- **Script**: `batch_20k.py --workers 10`
- **Resuming from**: sim 101 (100 already completed from validation test)
- **Remaining**: 20,650 simulations
- **Throughput**: ~13 sims/min steady-state
- **Estimated completion**: ~26 hours (by ~06:00 29 March)
- **Status at 250 sims**: 250 OK, 0 ERR (0% failure rate)

### How to Monitor
```bash
# Check latest progress
tail -5 C:\CalculiX\test_composite\batch_20k.log

# Count completed rows
wc -l C:\CalculiX\test_composite\calculix_results_20k.csv

# Check for running processes
tasklist | findstr ccx
```

### How to Resume If Interrupted
The script automatically resumes from the last completed sim. Just re-run:
```bash
cd C:\CalculiX\test_composite
python batch_20k.py --workers 10
```
