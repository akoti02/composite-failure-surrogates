/**
 * i18n — English + Russian.
 * Translations are curated (not transliterated). Every key has both EN and RU.
 *
 * Usage:
 *   const t = useT();
 *   <div>{t("analysis")}</div>
 *
 * Switching language is done by calling setLang("en") / setLang("ru");
 * it persists to localStorage under "rp3-lang" and is broadcast via context.
 */
import { createContext, useContext, useEffect, useMemo, useState, createElement } from "react";
import type { ReactNode } from "react";

export type Lang = "en" | "ru";

export const LANG_STORAGE_KEY = "rp3-lang";

/* ────────────────────────────────────────────────────────────────────
   DICTIONARY
   ──────────────────────────────────────────────────────────────────── */

const DICT = {
  // ── App title / branding ──
  app_title:              { en: "Composite Failure Surrogate", ru: "Суррогат разрушения композита" },
  app_subtitle:           { en: "University of Bristol",       ru: "Бристольский университет" },

  // ── Tabs ──
  tab_analysis:           { en: "Analysis",                    ru: "Анализ" },
  tab_explorer:           { en: "Explorer",                    ru: "Исследование" },

  // ── Header buttons ──
  presets:                { en: "Presets",                     ru: "Пресеты" },
  export:                 { en: "Export",                      ru: "Экспорт" },
  export_tooltip:         { en: "Copy results to clipboard",   ru: "Скопировать результаты" },
  projects:               { en: "Projects",                    ru: "Проекты" },
  projects_tooltip:       { en: "Snapshots & comparison",      ru: "Снимки и сравнение" },
  laminate:               { en: "Laminate",                    ru: "Ламинат" },
  laminate_tooltip:       { en: "CLT laminate analysis",       ru: "Анализ ламината (КТЛ)" },
  reset:                  { en: "Reset all inputs",            ru: "Сбросить все входные данные" },
  run:                    { en: "Run",                         ru: "Запустить" },
  key_enter:              { en: "Enter",                       ru: "Enter" },
  computing:              { en: "Computing",                   ru: "Вычисление" },
  live:                   { en: "Live",                        ru: "В реальном времени" },
  loading:                { en: "Loading",                     ru: "Загрузка" },

  // ── Status messages ──
  status_loading_models:  { en: "Loading models...",           ru: "Загрузка моделей..." },
  status_ready:           { en: "Ready",                       ru: "Готово" },
  status_no_models:       { en: "No models loaded — check sidecar", ru: "Модели не загружены — проверьте вспомогательный модуль" },
  status_models_loaded:   { en: "models loaded",               ru: "моделей загружено" },
  status_model_failed:    { en: "Model load failed",           ru: "Не удалось загрузить модели" },
  status_standalone:      { en: "Standalone mode — no sidecar",ru: "Автономный режим — без вспомогательного модуля" },
  status_error:           { en: "Error",                       ru: "Ошибка" },
  status_copied:          { en: "Results copied to clipboard", ru: "Результаты скопированы в буфер обмена" },
  status_copy_failed:     { en: "Clipboard write failed",      ru: "Не удалось записать в буфер обмена" },
  status_analysis_complete:{ en: "Analysis complete",          ru: "Анализ завершён" },

  // ── Update banner ──
  update_available:       { en: "Version {v} is available",    ru: "Доступна версия {v}" },
  update_download:        { en: "Download update",             ru: "Скачать обновление" },
  update_dismiss:         { en: "Dismiss",                     ru: "Скрыть" },

  // ── Splash screen ──
  splash_stage_init:      { en: "Initialising engine...",      ru: "Инициализация движка..." },
  splash_stage_nn:        { en: "Loading neural networks...",  ru: "Загрузка нейросетей..." },
  splash_stage_xgb:       { en: "Preparing XGBoost models...", ru: "Подготовка моделей XGBoost..." },
  splash_stage_cal:       { en: "Calibrating inference...",    ru: "Калибровка вывода..." },

  // ── Plate preview ──
  click_to_expand:        { en: "Click to expand plate view",  ru: "Нажмите для увеличения пластины" },
  plate_preview:          { en: "Plate Preview",               ru: "Предпросмотр пластины" },

  // ── Input panel sections ──
  section_configuration:  { en: "Configuration",               ru: "Конфигурация" },
  section_loading:        { en: "Applied Loading",             ru: "Приложенная нагрузка" },
  section_defects:        { en: "Defects",                     ru: "Дефекты" },

  material:               { en: "Material",                    ru: "Материал" },
  layup:                  { en: "Layup",                       ru: "Укладка" },
  boundary_condition:     { en: "Boundary Condition",          ru: "Граничное условие" },

  pressure_x:             { en: "Pressure X",                  ru: "Давление X" },
  pressure_y:             { en: "Pressure Y",                  ru: "Давление Y" },

  count:                  { en: "Count",                       ru: "Количество" },
  defect:                 { en: "Defect",                      ru: "Дефект" },
  defect_x:               { en: "X",                           ru: "X" },
  defect_y:               { en: "Y",                           ru: "Y" },
  defect_length:          { en: "Length",                      ru: "Длина" },
  defect_width:           { en: "Width",                       ru: "Ширина" },
  defect_angle:           { en: "Angle",                       ru: "Угол" },
  defect_roughness:       { en: "Rough.",                      ru: "Шерох." },

  // ── Units ──
  unit_mpa:               { en: "MPa",                         ru: "МПа" },
  unit_mm:                { en: "mm",                          ru: "мм" },
  unit_deg:               { en: "deg",                         ru: "°" },
  unit_n_per_mm:          { en: "N/mm",                        ru: "Н/мм" },
  unit_n_mm_per_mm:       { en: "N·mm/mm",                     ru: "Н·мм/мм" },
  unit_gpa:               { en: "GPa",                         ru: "ГПа" },

  // ── Results panel ──
  section_stress:         { en: "Stress Analysis",             ru: "Анализ напряжений" },
  section_failure:        { en: "Failure Assessment",          ru: "Оценка разрушения" },
  section_damage:         { en: "Damage Modes (Hashin)",       ru: "Режимы повреждения (Хашин)" },

  max_fibre_stress:       { en: "Max Fibre Stress (S11)",      ru: "Макс. напряжение вдоль волокон (S11)" },
  min_fibre_stress:       { en: "Min Fibre Stress (S11)",      ru: "Мин. напряжение вдоль волокон (S11)" },
  peak_shear:             { en: "Peak Shear (S12)",            ru: "Пиковый сдвиг (S12)" },

  tsai_wu_verdict:        { en: "Tsai-Wu Verdict",             ru: "Вердикт Цая-Ву" },
  hashin_verdict:         { en: "Hashin Verdict",              ru: "Вердикт Хашина" },
  puck_verdict:           { en: "Puck Verdict",                ru: "Вердикт Пака" },
  larc_verdict:           { en: "LaRC Verdict",                ru: "Вердикт LaRC" },

  fibre_tension:          { en: "Fibre Tension",               ru: "Растяжение волокон" },
  matrix_tension:         { en: "Matrix Tension",              ru: "Растяжение матрицы" },
  matrix_compression:     { en: "Matrix Compression",          ru: "Сжатие матрицы" },
  fibre_compression:      { en: "Fibre Compression",           ru: "Сжатие волокон" },

  pass:                   { en: "PASS",                        ru: "ПРОЙДЕНО" },
  fail:                   { en: "FAIL",                        ru: "ПРОВАЛ" },
  exceeded:               { en: "Exceeded",                    ru: "Превышено" },
  of_limit:               { en: "of limit",                    ru: "от предела" },

  expand_results:         { en: "Expand results",              ru: "Развернуть результаты" },
  results:                { en: "Results",                     ru: "Результаты" },
  awaiting_results:       { en: "Loading models...",           ru: "Загрузка моделей..." },

  // ── Verdict card ──
  verdict_initialising:   { en: "Initialising...",             ru: "Инициализация..." },
  verdict_initialising_desc:{ en: "Predictions update live as you change inputs", ru: "Прогнозы обновляются в реальном времени при изменении входных данных" },
  verdict_failure:        { en: "FAILURE PREDICTED",           ru: "ПРЕДСКАЗАНО РАЗРУШЕНИЕ" },
  verdict_failed:         { en: "Failed",                      ru: "Разрушено" },
  verdict_tsai_exceeds:   { en: "Tsai-Wu index {v} exceeds limit", ru: "Индекс Цая-Ву {v} превышает предел" },
  verdict_caution:        { en: "CAUTION",                     ru: "ОСТОРОЖНО" },
  verdict_caution_desc:   { en: "At {pct}% of failure threshold — {m}% margin remaining", ru: "Достигнуто {pct}% порога разрушения — запас {m}%" },
  verdict_safe:           { en: "SAFE",                        ru: "БЕЗОПАСНО" },
  verdict_safe_desc:      { en: "{m}% margin of safety remaining", ru: "Запас прочности {m}%" },
  tsai_wu_index:          { en: "Tsai-Wu Index",               ru: "Индекс Цая-Ву" },
  limit:                  { en: "limit",                       ru: "предел" },
  pct_of_limit:           { en: "{pct}% of limit",             ru: "{pct}% от предела" },

  // ── Footer ──
  footer_student:         { en: "Artur Akoev",                 ru: "Артур Акоев" },

  // ── Design Explorer ──
  explorer_sweep1d:       { en: "1D Sweep",                    ru: "1D-развёртка" },
  explorer_sweep1d_desc:  { en: "Vary one parameter, plot response", ru: "Изменение одного параметра, график отклика" },
  explorer_sweep2d:       { en: "2D Sweep",                    ru: "2D-развёртка" },
  explorer_sweep2d_desc:  { en: "Vary two parameters, contour map", ru: "Изменение двух параметров, контурная карта" },
  explorer_montecarlo:    { en: "Monte Carlo",                 ru: "Монте-Карло" },
  explorer_montecarlo_desc:{ en: "Random sampling, statistics",ru: "Случайная выборка, статистика" },
  explorer_sensitivity:   { en: "Sensitivity",                 ru: "Чувствительность" },
  explorer_sensitivity_desc:{ en: "Morris screening, parameter ranking", ru: "Отбор Морриса, ранжирование параметров" },

  parameter:              { en: "Parameter",                   ru: "Параметр" },
  x_parameter:            { en: "X Parameter",                 ru: "Параметр X" },
  y_parameter:            { en: "Y Parameter",                 ru: "Параметр Y" },
  output:                 { en: "Output",                      ru: "Выход" },
  steps:                  { en: "Steps",                       ru: "Шаги" },
  samples:                { en: "Samples",                     ru: "Выборки" },
  models_loading:         { en: "Models loading...",           ru: "Модели загружаются..." },
  stop:                   { en: "Stop",                        ru: "Остановить" },
  copy_csv:               { en: "Copy CSV",                    ru: "Копировать CSV" },
  export_csv_aria:        { en: "Export results as CSV",       ru: "Экспортировать результаты в CSV" },
  explorer_hint:          { en: "Configure parameters and click Run to explore the design space", ru: "Настройте параметры и нажмите «Запустить», чтобы исследовать пространство проектирования" },
  all_outputs:            { en: "All Outputs",                 ru: "Все выходы" },
  value:                  { en: "Value",                       ru: "Значение" },
  distribution:           { en: "Distribution",                ru: "Распределение" },
  mean:                   { en: "Mean",                        ru: "Среднее" },
  std:                    { en: "Std",                         ru: "Ст. откл." },
  sensitivity_of:         { en: "Sensitivity",                 ru: "Чувствительность" },
  sensitivity_footnote:   { en: "Morris screening method · Normalized elementary effects · {n} repetitions", ru: "Метод отбора Морриса · нормированные элементарные эффекты · {n} повторений" },

  // Sweep param labels
  sp_pressure_x:          { en: "Pressure X",                  ru: "Давление X" },
  sp_pressure_y:          { en: "Pressure Y",                  ru: "Давление Y" },
  sp_defect1_half_length: { en: "Defect 1 Half-Length",        ru: "Полудлина дефекта 1" },
  sp_defect1_width:       { en: "Defect 1 Width",              ru: "Ширина дефекта 1" },
  sp_defect1_angle:       { en: "Defect 1 Angle",              ru: "Угол дефекта 1" },
  sp_defect1_roughness:   { en: "Defect 1 Roughness",          ru: "Шероховатость дефекта 1" },

  // Output labels
  of_tsai_wu:             { en: "Tsai-Wu Index",               ru: "Индекс Цая-Ву" },
  of_max_s11:             { en: "Max S11",                     ru: "Макс. S11" },
  of_min_s11:             { en: "Min S11",                     ru: "Мин. S11" },
  of_max_s12:             { en: "Max S12",                     ru: "Макс. S12" },
  of_hashin_ft:           { en: "Hashin FT",                   ru: "Хашин FT" },
  of_hashin_mt:           { en: "Hashin MT",                   ru: "Хашин MT" },
  of_hashin_mc:           { en: "Hashin MC",                   ru: "Хашин MC" },

  // ── Laminate Builder ──
  laminate_code:          { en: "Laminate Code",               ru: "Код ламината" },
  laminate_tooltip_code:  { en: "Syntax: [angle/angle/...]s — ± means both +/- angles, s = symmetric. Examples: [0/90]s, [0/±45/90]s, [45/-45]2s", ru: "Синтаксис: [угол/угол/...]s — ± означает оба угла ±, s = симметричный. Примеры: [0/90]s, [0/±45/90]s, [45/-45]2s" },
  preset:                 { en: "Preset",                      ru: "Пресет" },
  select_preset:          { en: "Select preset...",            ru: "Выберите пресет..." },
  analytical_only:        { en: "analytical only",             ru: "только аналитика" },
  plies:                  { en: "plies",                       ru: "слоёв" },
  ply_stack:              { en: "Ply Stack",                   ru: "Пакет слоёв" },
  laminate_invalid:       { en: "Enter a valid laminate code (e.g., [0/±45/90]s)", ru: "Введите корректный код ламината (например, [0/±45/90]s)" },
  tab_stiffness:          { en: "Stiffness",                   ru: "Жёсткость" },
  tab_ply_stress:         { en: "Ply Stress",                  ru: "Напряжения в слое" },
  tab_failure:            { en: "Failure",                     ru: "Разрушение" },
  progressive_failure:    { en: "Progressive failure",         ru: "Прогрессирующее разрушение" },
  stiffness_polar:        { en: "Stiffness Polar",             ru: "Полярная диаграмма жёсткости" },
  ply_stresses_title:     { en: "Ply Stresses (Material Axes)",ru: "Напряжения в слоях (материальные оси)" },
  status_col:             { en: "Status",                      ru: "Состояние" },
  ok_status:              { en: "OK",                          ru: "OK" },
  first_ply_failure:      { en: "First Ply Failure",           ru: "Разрушение первого слоя" },
  last_ply_failure:       { en: "Last Ply Failure",            ru: "Разрушение последнего слоя" },
  no_failure:             { en: "No failure",                  ru: "Нет разрушения" },
  fpf_lpf_ratio:          { en: "FPF/LPF ratio",               ru: "Отношение FPF/LPF" },
  failed_plies:           { en: "Failed Plies",                ru: "Разрушенные слои" },
  at_applied_load:        { en: "at applied load",             ru: "при приложенной нагрузке" },
  ply:                    { en: "Ply",                         ru: "Слой" },
  hashin_damage_peaks:    { en: "Hashin Damage Mode Peak Indices", ru: "Пиковые индексы режимов повреждения по Хашину" },
  progressive_envelope:   { en: "Progressive Failure Envelope (Camanho Degradation)", ru: "Огибающая прогрессирующего разрушения (деградация по Каманьо)" },
  load_factor_axis:       { en: "Load Factor (multiplier on applied Nx/Ny/Nxy)", ru: "Коэффициент нагрузки (множитель к приложенным Nx/Ny/Nxy)" },
  max_fi_axis:            { en: "Max Failure Index (≥1.0 = failure)", ru: "Макс. индекс разрушения (≥1.0 = разрушение)" },

  // ── Project Manager ──
  snapshots_title:        { en: "Snapshots",                   ru: "Снимки" },
  compare_title:          { en: "Compare",                     ru: "Сравнение" },
  history_title:          { en: "History",                     ru: "История" },
  export_rp3:             { en: "Export .rp3",                 ru: "Экспорт .rp3" },
  import_rp3:             { en: "Import",                      ru: "Импорт" },
  snapshot_placeholder:   { en: "Snapshot name...",            ru: "Название снимка..." },
  save:                   { en: "Save",                        ru: "Сохранить" },
  no_snapshots:           { en: "No saved snapshots. Run an analysis and save it.", ru: "Нет сохранённых снимков. Запустите анализ и сохраните его." },
  compare_hint:           { en: "Select 2+ snapshots to compare", ru: "Выберите 2+ снимка для сравнения" },
  metric:                 { en: "Metric",                      ru: "Метрика" },
  defects_col:            { en: "Defects",                     ru: "Дефекты" },
  verdict:                { en: "Verdict",                     ru: "Вердикт" },
  no_history:             { en: "No analysis history yet",     ru: "История анализов пока пуста" },
  n_analyses:             { en: "{n} analyses",                ru: "{n} анализов" },
  clear:                  { en: "Clear",                       ru: "Очистить" },
  just_now:               { en: "just now",                    ru: "только что" },
  minutes_ago:            { en: "{n}m ago",                    ru: "{n} мин назад" },
  hours_ago:              { en: "{n}h ago",                    ru: "{n} ч назад" },
  remove_from_compare:    { en: "Remove from compare",         ru: "Убрать из сравнения" },
  compare:                { en: "Compare",                     ru: "Сравнить" },
  delete:                 { en: "Delete",                      ru: "Удалить" },
  defects_short:          { en: "defects",                     ru: "дефектов" },
  import_failed:          { en: "Failed to import: invalid project file format", ru: "Ошибка импорта: неверный формат файла проекта" },
  import_failed_prefix:   { en: "Failed to import project",    ru: "Не удалось импортировать проект" },
  default_analysis_name:  { en: "Analysis",                    ru: "Анализ" },

  // ── Plate Canvas ──
  axis_x:                 { en: "x (mm)",                      ru: "x (мм)" },
  axis_y:                 { en: "y (mm)",                      ru: "y (мм)" },

  // ── Error boundary ──
  error_title:            { en: "Something went wrong",        ru: "Что-то пошло не так" },
  try_again:              { en: "Try Again",                   ru: "Повторить" },

  // ── Preset names ──
  preset_single_central:  { en: "Single Central Crack",        ru: "Одиночная центральная трещина" },
  preset_biaxial:         { en: "Biaxial Loading",             ru: "Двухосное нагружение" },
  preset_severe_multi:    { en: "Severe Multi-Defect",         ru: "Множественные дефекты (тяжёлый случай)" },
  preset_edge_critical:   { en: "Edge Crack (Critical)",       ru: "Краевая трещина (критическая)" },
  preset_light_surface:   { en: "Light Surface Damage",        ru: "Лёгкое поверхностное повреждение" },

  // ── Material descriptions ──
  mat_t300_desc:          { en: "Standard-modulus CFRP. Most-cited benchmark in composites literature.", ru: "Углепластик стандартного модуля. Самый цитируемый эталон в литературе по композитам." },
  mat_im7_desc:           { en: "Intermediate modulus, toughened epoxy. Aerospace primary structure grade.", ru: "Средний модуль, упрочнённая эпоксидная смола. Класс для основных авиаконструкций." },
  mat_eglass_desc:        { en: "Glass-fibre reinforced epoxy. Lower cost, fundamentally different failure behaviour.", ru: "Эпоксид, армированный стекловолокном. Дешевле, принципиально иное поведение при разрушении." },
  mat_kevlar_desc:        { en: "Aramid-fibre reinforced epoxy. Unique tension/compression asymmetry.", ru: "Эпоксид, армированный арамидными волокнами. Характерная асимметрия растяжение/сжатие." },
  mat_flax_desc:          { en: "Natural-fibre composite. Low-performance extreme, tests model generalisation.", ru: "Композит на натуральных волокнах. Низкопроизводительный крайний случай, проверяет обобщение модели." },

  // ── Layup descriptions ──
  layup_qi_desc:          { en: "Quasi-isotropic 8-ply. Balanced failure modes.", ru: "Квазиизотропный 8-слойный. Сбалансированные режимы разрушения." },
  layup_cp_desc:          { en: "Cross-ply 8-ply. Distinct 0/90 interaction.", ru: "Крестоукладка, 8 слоёв. Чёткое взаимодействие 0/90." },
  layup_ud_desc:          { en: "Unidirectional 8-ply. Pure fibre-dominated response.", ru: "Однонаправленная укладка, 8 слоёв. Чистый отклик по волокнам." },
  layup_pm45_desc:        { en: "±45 angle-ply. Shear-dominated, exercises matrix failure.", ru: "Уголковая укладка ±45. Доминирует сдвиг, активно задействует разрушение матрицы." },
  layup_pm30_desc:        { en: "±30 angle-ply. Off-axis mixed fibre/matrix response.", ru: "Уголковая укладка ±30. Внеосевой смешанный отклик волокон и матрицы." },
  layup_skin_desc:        { en: "Aerospace realistic 18-ply. Multi-angle with thickness.", ru: "Реалистичная авиационная укладка, 18 слоёв. Много углов, большая толщина." },

  // ── BC descriptions ──
  bc_tension_comp:        { en: "Tension + Compression",       ru: "Растяжение + сжатие" },
  bc_tension_comp_desc:   { en: "px on right, -py on top/bottom", ru: "px справа, -py сверху и снизу" },
  bc_biaxial:             { en: "Biaxial",                     ru: "Двухосное" },
  bc_biaxial_desc:        { en: "px on right, py on top/bottom", ru: "px справа, py сверху и снизу" },
  bc_uniaxial_shear:      { en: "Uniaxial + Shear",            ru: "Одноосное + сдвиг" },
  bc_uniaxial_shear_desc: { en: "px on right, shear via X-force on top", ru: "px справа, сдвиг за счёт X-силы сверху" },

  // ── Tooltips for engineering terms ──
  tip_pressure_x:         { en: "Applied pressure in the fibre direction (longitudinal)", ru: "Приложенное давление в направлении волокон (продольное)" },
  tip_pressure_y:         { en: "Applied pressure transverse to the fibre direction", ru: "Приложенное давление поперёк волокон" },
  tip_material:           { en: "Composite material system (fibre/matrix)", ru: "Система композитного материала (волокно/матрица)" },
  tip_layup:              { en: "Laminate stacking sequence",  ru: "Последовательность укладки слоёв ламината" },
  tip_bc_mode:            { en: "Boundary condition and loading mode", ru: "Тип граничных условий и нагружения" },
  tip_half_length:        { en: "Half the crack/defect length (semi-major axis)", ru: "Половина длины трещины/дефекта (большая полуось)" },
  tip_width:              { en: "Opening width of the defect", ru: "Ширина раскрытия дефекта" },
  tip_angle:              { en: "Orientation of the defect relative to the fibre direction", ru: "Ориентация дефекта относительно направления волокон" },
  tip_roughness:          { en: "Surface roughness at the defect site (0 = smooth, 1 = rough)", ru: "Шероховатость поверхности в области дефекта (0 = гладкая, 1 = грубая)" },
  tip_tsai_wu:            { en: "Combined stress failure index. Values ≥ 1.0 predict failure. E.g. 0.85 = 85% of failure threshold.", ru: "Комбинированный индекс разрушения по напряжениям. Значения ≥ 1.0 предсказывают разрушение. Например, 0.85 = 85% порога разрушения." },
  tip_hashin:             { en: "Damage mode indices. Values ≥ 1.0 predict mode-specific failure", ru: "Индексы режимов повреждения. Значения ≥ 1.0 предсказывают разрушение по данному режиму" },
  tip_hashin_ft:          { en: "Fibre tension — fibre breakage under tensile load", ru: "Растяжение волокон — разрыв волокон под растягивающей нагрузкой" },
  tip_hashin_fc:          { en: "Fibre compression — fibre buckling/kinking under compressive load", ru: "Сжатие волокон — потеря устойчивости/излом волокон под сжимающей нагрузкой" },
  tip_hashin_mt:          { en: "Matrix tension — resin cracking between fibres under tension", ru: "Растяжение матрицы — растрескивание смолы между волокнами при растяжении" },
  tip_hashin_mc:          { en: "Matrix compression — resin crushing between fibres under compression", ru: "Сжатие матрицы — раздавливание смолы между волокнами при сжатии" },
  tip_mises:              { en: "Von Mises equivalent stress combining all stress components", ru: "Эквивалентное напряжение фон Мизеса, объединяющее все компоненты напряжения" },
  tip_s11:                { en: "Stress in the fibre direction (longitudinal)", ru: "Напряжение в направлении волокон (продольное)" },
  tip_s12:                { en: "In-plane shear stress between fibre and transverse directions", ru: "Сдвиговое напряжение в плоскости между направлением волокон и поперечным направлением" },
  tip_n_defects:          { en: "Number of crack-like defects in the composite plate (1-5)", ru: "Количество трещиноподобных дефектов в композитной пластине (1–5)" },
  tip_x_position:         { en: "Horizontal position of defect centre on the plate (0-100 mm)", ru: "Горизонтальное положение центра дефекта на пластине (0–100 мм)" },
  tip_y_position:         { en: "Vertical position of defect centre on the plate (0-50 mm)", ru: "Вертикальное положение центра дефекта на пластине (0–50 мм)" },
  tip_max_s11_row:        { en: "Maximum stress in fibre direction", ru: "Максимальное напряжение в направлении волокон" },
  tip_min_s11_row:        { en: "Minimum stress (compression)",  ru: "Минимальное напряжение (сжатие)" },
  tip_max_s12_row:        { en: "Maximum in-plane shear stress", ru: "Максимальное сдвиговое напряжение в плоскости" },
  tip_puck_verdict:       { en: "Puck failure criterion",       ru: "Критерий разрушения Пака" },
  tip_larc_verdict:       { en: "LaRC failure criterion",       ru: "Критерий разрушения LaRC" },
  tip_hashin_ft_idx:      { en: "Fibre tensile failure index",  ru: "Индекс разрушения при растяжении волокон" },
  tip_hashin_mt_idx:      { en: "Matrix tensile failure index", ru: "Индекс разрушения при растяжении матрицы" },
  tip_hashin_mc_idx:      { en: "Matrix compressive failure index", ru: "Индекс разрушения при сжатии матрицы" },

  // ── Export text ──
  export_title:           { en: "RP3 Prediction Results",      ru: "Результаты прогноза RP3" },
  export_input:           { en: "Input Configuration",         ru: "Входная конфигурация" },
  export_n_defects:       { en: "Number of defects",           ru: "Количество дефектов" },
  export_bc_mode:         { en: "BC Mode",                     ru: "Тип ГУ" },
  export_stress:          { en: "Stress Analysis",             ru: "Анализ напряжений" },
  export_failure_assess:  { en: "Failure Assessment",          ru: "Оценка разрушения" },
  export_hashin_modes:    { en: "Hashin Damage Modes",         ru: "Режимы повреждения по Хашину" },
  export_yes:             { en: "YES",                         ru: "ДА" },
  export_no:              { en: "NO",                          ru: "НЕТ" },
  export_tsai_wu_index:   { en: "Tsai-Wu Index",               ru: "Индекс Цая-Ву" },
  export_tsai_wu_failed:  { en: "Tsai-Wu Failed",              ru: "Разрушение по Цаю-Ву" },
  export_hashin_failed:   { en: "Hashin Failed",               ru: "Разрушение по Хашину" },
  export_puck_failed:     { en: "Puck Failed",                 ru: "Разрушение по Паку" },
  export_larc_failed:     { en: "LaRC Failed",                 ru: "Разрушение по LaRC" },

  // ── Language toggle ──
  lang_en:                { en: "EN",                          ru: "EN" },
  lang_ru:                { en: "RU",                          ru: "RU" },
  lang_switch_to_en:      { en: "English",                     ru: "English" },
  lang_switch_to_ru:      { en: "Russian",                     ru: "Русский" },
} as const satisfies Record<string, { en: string; ru: string }>;

export type TKey = keyof typeof DICT;

/* ────────────────────────────────────────────────────────────────────
   LANGUAGE CONTEXT
   ──────────────────────────────────────────────────────────────────── */

interface LangCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: TKey, vars?: Record<string, string | number>) => string;
}

const Ctx = createContext<LangCtx | null>(null);

function interpolate(s: string, vars?: Record<string, string | number>): string {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] != null ? String(vars[k]) : `{${k}}`));
}

function detectInitialLang(): Lang {
  if (typeof window === "undefined") return "en";
  const saved = window.localStorage.getItem(LANG_STORAGE_KEY);
  if (saved === "en" || saved === "ru") return saved;
  // Fallback: browser locale
  const nav = window.navigator?.language?.toLowerCase() ?? "";
  if (nav.startsWith("ru")) return "ru";
  return "en";
}

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => detectInitialLang());

  useEffect(() => {
    try { window.localStorage.setItem(LANG_STORAGE_KEY, lang); } catch { /* storage blocked — ignore */ }
    try { document.documentElement.lang = lang; } catch { /* non-browser env — ignore */ }
  }, [lang]);

  const value = useMemo<LangCtx>(() => ({
    lang,
    setLang: setLangState,
    t: (key, vars) => {
      const entry = DICT[key];
      if (!entry) return String(key);
      return interpolate(entry[lang] ?? entry.en, vars);
    },
  }), [lang]);

  return createElement(Ctx.Provider, { value }, children);
}

export function useLang(): LangCtx {
  const ctx = useContext(Ctx);
  if (!ctx) {
    // Fallback: if used outside provider, return English
    return {
      lang: "en",
      setLang: () => { /* no-op */ },
      t: (key, vars) => {
        const entry = DICT[key];
        return entry ? interpolate(entry.en, vars) : String(key);
      },
    };
  }
  return ctx;
}

export function useT() {
  return useLang().t;
}
