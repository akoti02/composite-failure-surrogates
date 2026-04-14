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
  material_id: number;
  layup_id: number;
  bc_mode: string;
  pressure_x: number;
  pressure_y: number;
  [key: string]: number | string; // defect{i}_{param}
}

export interface PredictionResults {
  tsai_wu_index?: number;
  max_s11?: number;
  min_s11?: number;
  max_s12?: number;
  max_hashin_ft?: number;
  max_hashin_mt?: number;
  max_hashin_mc?: number;
  failed_tsai_wu?: number;
  failed_hashin?: number;
  failed_puck?: number;
  failed_larc?: number;
}

export type VerdictLevel = "safe" | "caution" | "failure" | "awaiting";

export interface Preset {
  n_defects: number;
  material_id: number;
  layup_id: number;
  bc_mode: string;
  pressure_x: number;
  pressure_y: number;
  defects: DefectParams[];
}
