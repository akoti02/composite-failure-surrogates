export interface DefectParams {
  x: number;
  y: number;
  half_length: number;
  width: number;
  angle: number;
  roughness: number;
}

export interface RawInputs {
  n_defects: number;
  pressure_x: number;
  pressure_y: number;
  ply_thickness: number;
  layup_rotation: number;
  [key: string]: number; // defect{i}_{param}
}

export interface PredictionResults {
  tsai_wu_index?: number;
  max_mises?: number;
  max_s11?: number;
  min_s11?: number;
  max_s12?: number;
  max_hashin_ft?: number;
  max_hashin_fc?: number;
  max_hashin_mt?: number;
  max_hashin_mc?: number;
  failed_tsai_wu?: number;
  failed_hashin?: number;
  max_mises_defect1?: number;
  max_mises_defect2?: number;
  max_mises_defect3?: number;
  max_mises_defect4?: number;
  max_mises_defect5?: number;
}

export type VerdictLevel = "safe" | "caution" | "failure" | "awaiting";

export interface Preset {
  n_defects: number;
  pressure_x: number;
  pressure_y: number;
  ply_thickness: number;
  layup_rotation: number;
  defects: DefectParams[];
}
