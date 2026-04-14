import type { Preset } from "./types";

// Map preset names (used as keys in PRESETS) → i18n keys for display.
// Keep internal preset names in English so they remain stable across languages
// (localStorage autosave, comparisons, etc.); translate only at render time.
export const PRESET_NAME_KEYS: Record<string, string> = {
  "Single Central Crack": "preset_single_central",
  "Biaxial Loading":      "preset_biaxial",
  "Severe Multi-Defect":  "preset_severe_multi",
  "Edge Crack (Critical)":"preset_edge_critical",
  "Light Surface Damage": "preset_light_surface",
};

export const PRESETS: Record<string, Preset> = {
  "Single Central Crack": {
    n_defects: 1, pressure_x: 100.0, pressure_y: 0.0,
    material_id: 1, layup_id: 1, bc_mode: "tension_comp",
    defects: [
      { x: 50.0, y: 25.0, half_length: 5.0, width: 0.5, angle: 0.0, roughness: 0.5 },
    ],
  },
  "Biaxial Loading": {
    n_defects: 2, pressure_x: 100.0, pressure_y: 100.0,
    material_id: 1, layup_id: 1, bc_mode: "biaxial",
    defects: [
      { x: 35.0, y: 20.0, half_length: 5.0, width: 0.5, angle: 0.0, roughness: 0.5 },
      { x: 65.0, y: 30.0, half_length: 5.0, width: 0.5, angle: 90.0, roughness: 0.5 },
    ],
  },
  "Severe Multi-Defect": {
    n_defects: 5, pressure_x: 200.0, pressure_y: 50.0,
    material_id: 5, layup_id: 3, bc_mode: "tension_comp",
    defects: [
      { x: 50.0, y: 25.0, half_length: 10.0, width: 1.0, angle: 0.0, roughness: 0.8 },
      { x: 30.0, y: 15.0, half_length: 7.0, width: 0.5, angle: 45.0, roughness: 0.6 },
      { x: 70.0, y: 35.0, half_length: 8.0, width: 0.7, angle: -30.0, roughness: 0.7 },
      { x: 25.0, y: 40.0, half_length: 4.0, width: 0.3, angle: 90.0, roughness: 0.4 },
      { x: 80.0, y: 10.0, half_length: 6.0, width: 0.5, angle: 15.0, roughness: 0.5 },
    ],
  },
  "Edge Crack (Critical)": {
    n_defects: 1, pressure_x: 150.0, pressure_y: 0.0,
    material_id: 8, layup_id: 4, bc_mode: "uniaxial_shear",
    defects: [
      { x: 50.0, y: 3.0, half_length: 8.0, width: 0.5, angle: 0.0, roughness: 0.7 },
    ],
  },
  "Light Surface Damage": {
    n_defects: 3, pressure_x: 50.0, pressure_y: 0.0,
    material_id: 12, layup_id: 6, bc_mode: "tension_comp",
    defects: [
      { x: 40.0, y: 20.0, half_length: 2.0, width: 0.2, angle: 0.0, roughness: 0.3 },
      { x: 60.0, y: 30.0, half_length: 1.5, width: 0.2, angle: 45.0, roughness: 0.3 },
      { x: 50.0, y: 25.0, half_length: 2.5, width: 0.3, angle: -20.0, roughness: 0.4 },
    ],
  },
};

export const DEFAULT_DEFECT = { x: 50.0, y: 25.0, half_length: 5.0, width: 0.5, angle: 0.0, roughness: 0.5 };

// Spread defaults so they don't all stack on the same spot
export const DEFAULT_DEFECTS: import("./types").DefectParams[] = [
  { x: 50, y: 25, half_length: 5.0, width: 0.5, angle: 0, roughness: 0.5 },
  { x: 30, y: 15, half_length: 5.0, width: 0.5, angle: 30, roughness: 0.5 },
  { x: 70, y: 35, half_length: 5.0, width: 0.5, angle: -20, roughness: 0.5 },
  { x: 20, y: 38, half_length: 4.0, width: 0.4, angle: 45, roughness: 0.4 },
  { x: 80, y: 12, half_length: 4.0, width: 0.4, angle: -45, roughness: 0.4 },
];
