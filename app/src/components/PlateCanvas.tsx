import { useEffect, useMemo, useRef, type ReactElement } from "react";
import { contours as d3contours } from "d3-contour";
import { PLATE_LENGTH, PLATE_WIDTH, DEFECT_COLORS, COL } from "../lib/constants";
import type { DefectParams } from "../lib/types";
import { MATERIAL_DB } from "../lib/materials";
import { computeStressField, extractField, mapColor, type StressFieldResult, type FieldComponent, type ColorMap } from "../lib/stress-field";
import { useT } from "../lib/i18n";

interface Props {
  nDefects: number;
  defects: DefectParams[];
  pressureX: number;
  pressureY: number;
  materialKey?: string;
  /**
   * Use a lower canvas resolution for the small preview variant, full
   * resolution for the focus modal. 80×40 = 3200 samples, each a complex
   * Lekhnitskii evaluation — under ~100 ms on a mid-range CPU.
   */
  resolution?: number;
  /** Field component to colour (default von Mises) */
  component?: FieldComponent;
  /** Colormap (default viridis — perceptually uniform, colour-blind safe) */
  colormap?: ColorMap;
  /** Show iso-stress contour lines */
  showContours?: boolean;
  /** Show the colour legend (turn off for the tiny header preview) */
  showLegend?: boolean;
}

/**
 * PlateCanvas — analytical stress-field visualization.
 *
 * Layer stack, back-to-front:
 *   1. Canvas 2D heatmap    — pixel-level viridis-mapped stress, bilinearly
 *                             interpolated from the computed grid.
 *   2. SVG iso-stress contours (d3-contour) — thin glowing curves at
 *                             quantile thresholds of the scalar field.
 *   3. SVG carbon weave pattern — subtle ±45° crosshatch overlay hinting
 *                             at the laminate's fibre directions.
 *   4. SVG defect geometry  — crisp ellipses + rotation axis line +
 *                             numbered labels. Defects punch dark voids
 *                             through the heatmap because the Lekhnitskii
 *                             solver zeroes stress inside the ellipse.
 *   5. SVG pressure arrows  — far-field load indicators with MPa magnitude.
 *   6. SVG axis labels      — ruler ticks + x/y axis titles.
 *   7. SVG legend           — vertical colorbar with min / max stress values.
 *
 * The canvas is rendered at the stress-field grid resolution (80×40) and
 * CSS-stretched to the SVG viewBox — the browser does the smoothing. The
 * SVG overlay shares the same viewBox so geometry aligns exactly with the
 * heatmap pixels.
 */
export function PlateCanvas({
  nDefects, defects, pressureX, pressureY, materialKey,
  resolution = 80,
  component = "vonMises",
  colormap = "viridis",
  showContours = true,
  showLegend = true,
}: Props) {
  const t = useT();
  const unitMPa = t("unit_mpa");
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Layout in viewBox coordinate units (SVG + canvas share this space).
  // Canvas pixel grid lives at (mx, my) → (mx+pw, my+ph) on the SVG.
  const mx = 50, my = 28;
  const pw = 300, ph = 150;
  const svgW = pw + mx * 2;
  const svgH = ph + my * 2;
  const sx = pw / PLATE_LENGTH;
  const sy = ph / PLATE_WIDTH;
  const cx = (px: number) => mx + px * sx;
  const cy = (py: number) => my + py * sy;

  // ────────────────────────────────────────────────────────────────
  // Compute stress field (memoized). Uses the selected material's
  // orthotropic properties in the Lekhnitskii complex-variable solution.
  // When no stress is applied we still render an empty gradient so the
  // canvas isn't a solid block of colour.
  // ────────────────────────────────────────────────────────────────
  const field = useMemo<StressFieldResult | null>(() => {
    const mat = materialKey ? MATERIAL_DB[materialKey] : MATERIAL_DB["T300/5208"];
    if (!mat) return null;
    // Guard: Lekhnitskii expects something non-trivial to solve for. If
    // both loads are zero we skip — caller will see a clean (dark) field.
    if (Math.abs(pressureX) < 1e-6 && Math.abs(pressureY) < 1e-6) return null;
    try {
      return computeStressField(
        PLATE_LENGTH, PLATE_WIDTH,
        defects, nDefects,
        pressureX, pressureY,
        mat, resolution,
      );
    } catch {
      return null;
    }
  }, [materialKey, defects, nDefects, pressureX, pressureY, resolution]);

  // Extract the scalar field for the heatmap + contour generator
  const scalar = useMemo(() => field ? extractField(field, component) : null, [field, component]);

  // ────────────────────────────────────────────────────────────────
  // Paint the canvas heatmap whenever the field changes.
  // Drawing at grid resolution and stretching via CSS is ~10× cheaper
  // than filling every SVG pixel and lets the browser do bilinear
  // smoothing for us. For an 80×40 grid that's 3200 pixels per frame.
  // ────────────────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const nx = field?.nx ?? resolution;
    const ny = field?.ny ?? Math.round(resolution * (PLATE_WIDTH / PLATE_LENGTH));
    canvas.width = nx;
    canvas.height = ny;

    if (!field || !scalar) {
      // Empty state: deep indigo-black gradient so the plate isn't blinding white
      const grad = ctx.createLinearGradient(0, 0, nx, ny);
      grad.addColorStop(0, "#0b0b12");
      grad.addColorStop(1, "#11111c");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, nx, ny);
      return;
    }

    const img = ctx.createImageData(nx, ny);
    const px = img.data;
    const { data, min, max } = scalar;
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const v = data[j * nx + i];
        // Inside-defect points are set to 0 by the solver. Detect this and
        // render them as near-black voids so they "punch through" the
        // heatmap — visually reads as a true hole, not just a cold spot.
        let r: number, g: number, b: number, a: number;
        if (v === 0 && isPointInAnyDefect(
          (i / (nx - 1)) * PLATE_LENGTH,
          (j / (ny - 1)) * PLATE_WIDTH,
          defects, nDefects,
        )) {
          r = 14; g = 14; b = 22; a = 255;
        } else {
          [r, g, b, a] = mapColor(v, min, max, colormap);
        }
        const idx = (j * nx + i) * 4;
        px[idx] = r; px[idx + 1] = g; px[idx + 2] = b; px[idx + 3] = a;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [field, scalar, colormap, defects, nDefects, resolution]);

  // ────────────────────────────────────────────────────────────────
  // Iso-stress contour paths via d3-contour. Threshold count kept low
  // so the plate isn't a spider web — 6 equally-spaced quantile levels
  // read as "here's a stress gradient" rather than "here's noise".
  // ────────────────────────────────────────────────────────────────
  const contourPaths = useMemo(() => {
    if (!showContours || !field || !scalar) return [];
    const { nx, ny } = field;
    const { data, min, max } = scalar;
    if (max - min < 1e-6) return [];
    const nLevels = 7;
    const thresholds = Array.from({ length: nLevels }, (_, k) =>
      min + ((k + 1) / (nLevels + 1)) * (max - min)
    );
    const gen = d3contours()
      .size([nx, ny])
      .thresholds(thresholds);
    const features = gen(Array.from(data));
    // Convert each contour's coordinates (in grid units) into SVG path data
    // in viewBox space. Scale grid index (0..nx) into (mx..mx+pw).
    return features.map((f, idx) => {
      const t = (f.value - min) / (max - min); // 0..1 for colour
      const [r, g, b] = mapColor(f.value, min, max, colormap);
      const d = f.coordinates.map(polyGroup =>
        polyGroup.map(ring => {
          const pts = ring.map(([gx, gy]) => {
            const vx = mx + (gx / (nx - 1)) * pw;
            const vy = my + (gy / (ny - 1)) * ph;
            return `${vx.toFixed(2)},${vy.toFixed(2)}`;
          });
          return `M${pts.join("L")}Z`;
        }).join(" ")
      ).join(" ");
      return { id: idx, d, color: `rgb(${r},${g},${b})`, t };
    });
  }, [showContours, field, scalar, colormap, mx, my, pw, ph]);

  // ────────────────────────────────────────────────────────────────
  // Pressure arrows (scaled to load magnitude, colour-coded vs tension/
  // compression, drawn outside the plate boundary so they never overlap
  // the stress field).
  // ────────────────────────────────────────────────────────────────
  const arrows: ReactElement[] = [];
  const maxP = Math.max(Math.abs(pressureX), Math.abs(pressureY), 1);
  const arrowColor = "#7fdbff";
  if (pressureX !== 0) {
    const dir = pressureX > 0 ? 1 : -1;
    const len = 14 + 24 * (Math.abs(pressureX) / maxP);
    [0.2, 0.5, 0.8].forEach((frac, i) => {
      const y = cy(PLATE_WIDTH * frac);
      const startX = dir > 0 ? cx(0) - len : cx(PLATE_LENGTH) + len;
      const endX = dir > 0 ? cx(0) : cx(PLATE_LENGTH);
      arrows.push(
        <line key={`ax${i}`} x1={startX} y1={y} x2={endX} y2={y}
          stroke={arrowColor} strokeWidth={1.8} markerEnd="url(#arrowhead)"
          opacity={0.85} style={{ filter: `drop-shadow(0 0 2px ${arrowColor})` }} />
      );
    });
    arrows.push(
      <text key="plx"
        x={cx(pressureX > 0 ? 0 : PLATE_LENGTH) + (pressureX > 0 ? -len - 6 : len + 6)}
        y={cy(PLATE_WIDTH * 0.5) - 8}
        fill={arrowColor} fontSize={11} fontWeight={700} textAnchor="middle"
        style={{ filter: `drop-shadow(0 0 3px ${arrowColor})` }}>
        {Math.abs(pressureX)} {unitMPa}
      </text>
    );
  }
  if (pressureY !== 0) {
    const dir = pressureY > 0 ? 1 : -1;
    const len = 14 + 24 * (Math.abs(pressureY) / maxP);
    [0.25, 0.5, 0.75].forEach((frac, i) => {
      const x = cx(PLATE_LENGTH * frac);
      const startY = dir > 0 ? cy(0) - len : cy(PLATE_WIDTH) + len;
      const endY = dir > 0 ? cy(0) : cy(PLATE_WIDTH);
      arrows.push(
        <line key={`ay${i}`} x1={x} y1={startY} x2={x} y2={endY}
          stroke={arrowColor} strokeWidth={1.8} markerEnd="url(#arrowhead)"
          opacity={0.85} style={{ filter: `drop-shadow(0 0 2px ${arrowColor})` }} />
      );
    });
    arrows.push(
      <text key="ply"
        x={cx(PLATE_LENGTH * 0.5) + 32}
        y={cy(pressureY > 0 ? 0 : PLATE_WIDTH) + (pressureY > 0 ? -len + 4 : len + 12)}
        fill={arrowColor} fontSize={11} fontWeight={700} textAnchor="middle"
        style={{ filter: `drop-shadow(0 0 3px ${arrowColor})` }}>
        {Math.abs(pressureY)} {unitMPa}
      </text>
    );
  }

  // ────────────────────────────────────────────────────────────────
  // Defect outlines — crisp, rendered on top of the heatmap. The
  // actual dark "void" inside each ellipse is painted by the canvas
  // layer above (via isPointInAnyDefect), so here we just draw the
  // stroke + crack axis + numbered label. Previously the whole group
  // was blurred; now each element is sharp.
  // ────────────────────────────────────────────────────────────────
  const labelPositions: { x: number; y: number }[] = [];
  const defectShapes: ReactElement[] = [];
  for (let i = 0; i < nDefects; i++) {
    const d = defects[i];
    if (!d) continue;
    const rad = (d.angle * Math.PI) / 180;
    const halfW = Math.max(d.width * sy * 0.5, 1.5);
    const halfL = d.half_length * sx;
    const dcx = cx(d.x);
    const dcy = cy(d.y);

    // Pick the label position farthest from any existing label to avoid
    // overlap when defects are clustered.
    const candidates = [
      { x: dcx + halfL + 8, y: dcy + 4 },
      { x: dcx - halfL - 12, y: dcy + 4 },
      { x: dcx, y: dcy - halfW - 9 },
      { x: dcx, y: dcy + halfW + 12 },
      { x: dcx + halfL + 8, y: dcy - 10 },
      { x: dcx - halfL - 12, y: dcy - 10 },
      { x: dcx + halfL + 8, y: dcy + 14 },
      { x: dcx - halfL - 12, y: dcy + 14 },
    ];
    let bestPos = candidates[0], bestMinDist = 0;
    for (const cand of candidates) {
      let minDist = Infinity;
      for (const existing of labelPositions) {
        const dist = Math.hypot(cand.x - existing.x, cand.y - existing.y);
        if (dist < minDist) minDist = dist;
      }
      if (minDist > bestMinDist) { bestMinDist = minDist; bestPos = cand; }
    }
    labelPositions.push(bestPos);

    defectShapes.push(
      <g key={`d${i}`}>
        <ellipse
          cx={dcx} cy={dcy} rx={halfL} ry={halfW}
          transform={`rotate(${d.angle} ${dcx} ${dcy})`}
          fill="none"
          stroke={DEFECT_COLORS[i]} strokeWidth={2} strokeOpacity={1}
          style={{ filter: `drop-shadow(0 0 4px ${DEFECT_COLORS[i]}aa)` }}
        />
        <line
          x1={cx(d.x - d.half_length * Math.cos(rad))}
          y1={cy(d.y - d.half_length * Math.sin(rad))}
          x2={cx(d.x + d.half_length * Math.cos(rad))}
          y2={cy(d.y + d.half_length * Math.sin(rad))}
          stroke={DEFECT_COLORS[i]} strokeWidth={1} strokeLinecap="round"
          strokeDasharray="3 2" strokeOpacity={0.75}
        />
        <circle cx={bestPos.x} cy={bestPos.y - 1} r={7.5}
          fill={COL.canvasBg} fillOpacity={0.95}
          stroke={DEFECT_COLORS[i]} strokeWidth={1.3}
          style={{ filter: `drop-shadow(0 0 3px ${DEFECT_COLORS[i]}66)` }} />
        <text x={bestPos.x} y={bestPos.y + 3}
          fill={DEFECT_COLORS[i]} fontSize={11} fontWeight={800} textAnchor="middle">
          {i + 1}
        </text>
      </g>
    );
  }

  // ────────────────────────────────────────────────────────────────
  // Axis labels / tick marks — 10 mm divisions along x, 25 mm on y.
  // ────────────────────────────────────────────────────────────────
  const axisLabels: ReactElement[] = [];
  for (let g = 0; g <= PLATE_LENGTH; g += 25) {
    axisLabels.push(
      <text key={`lx${g}`} x={cx(g)} y={cy(PLATE_WIDTH) + 16}
        fill={COL.textMid} fontSize={10} textAnchor="middle">{g}</text>
    );
  }
  for (let g = 0; g <= PLATE_WIDTH; g += 25) {
    axisLabels.push(
      <text key={`ly${g}`} x={cx(0) - 8} y={cy(g) + 4}
        fill={COL.textMid} fontSize={10} textAnchor="end">{g}</text>
    );
  }

  // Legend (vertical colourbar with min/max) — 15 samples of the colour
  // scale stacked from max at top to min at bottom.
  const legendStops = 15;
  const legend: ReactElement[] = [];
  if (showLegend && scalar) {
    const lxRight = cx(PLATE_LENGTH) + 18;
    const lTop = cy(0) + 6;
    const lH = ph - 12;
    const lW = 8;
    for (let k = 0; k < legendStops; k++) {
      const t = 1 - k / (legendStops - 1);
      const v = scalar.min + t * (scalar.max - scalar.min);
      const [r, g, b] = mapColor(v, scalar.min, scalar.max, colormap);
      legend.push(
        <rect key={`leg${k}`} x={lxRight} y={lTop + (k / legendStops) * lH}
          width={lW} height={lH / legendStops + 0.5}
          fill={`rgb(${r},${g},${b})`} />
      );
    }
    legend.push(
      <rect key="legbox" x={lxRight} y={lTop} width={lW} height={lH}
        fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth={0.5} />
    );
    legend.push(
      <text key="legmax" x={lxRight + lW + 3} y={lTop + 4}
        fill={COL.textMid} fontSize={9}>{scalar.max.toFixed(0)}</text>
    );
    legend.push(
      <text key="legmin" x={lxRight + lW + 3} y={lTop + lH}
        fill={COL.textMid} fontSize={9}>{scalar.min.toFixed(0)}</text>
    );
    legend.push(
      <text key="legunit" x={lxRight + lW + 3} y={lTop + lH / 2}
        fill={COL.textDim} fontSize={8}>{unitMPa}</text>
    );
  }

  return (
    <div className="relative w-full" style={{ aspectRatio: `${svgW} / ${svgH}` }}>
      {/* Canvas heatmap — rendered at grid resolution, stretched to fill */}
      <canvas
        ref={canvasRef}
        style={{
          position: "absolute",
          left: `${(mx / svgW) * 100}%`,
          top: `${(my / svgH) * 100}%`,
          width: `${(pw / svgW) * 100}%`,
          height: `${(ph / svgH) * 100}%`,
          imageRendering: "auto",           // bilinear smoothing from the browser
          borderRadius: 4,
          zIndex: 0,
        }}
      />

      {/* SVG overlay — sits on top of the canvas, same viewBox */}
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        preserveAspectRatio="xMidYMid meet"
        className="w-full h-full"
        style={{
          position: "absolute", inset: 0,
          background: `radial-gradient(ellipse at 50% 45%, #141418 0%, ${COL.canvasBg} 100%)`,
          borderRadius: 10,
          border: `1px solid ${COL.border}`,
          zIndex: 1,
        }}
      >
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill={arrowColor} opacity="0.9" />
          </marker>
          {/* Carbon-weave hint — subtle ±45° crosshatch. Opacity is low so
              it reads as material texture rather than UI clutter. */}
          <pattern id="carbonWeave" width="8" height="8" patternUnits="userSpaceOnUse">
            <path d="M0,8 L8,0" stroke="rgba(255,255,255,0.03)" strokeWidth="0.5" />
            <path d="M0,0 L8,8" stroke="rgba(255,255,255,0.03)" strokeWidth="0.5" />
          </pattern>
        </defs>

        {/* Iso-stress contour lines */}
        {contourPaths.map(c => (
          <path key={c.id} d={c.d} fill="none"
            stroke="rgba(255,255,255,0.35)" strokeWidth={0.6}
            style={{ mixBlendMode: "screen" }} />
        ))}

        {/* Carbon weave overlay over the plate area only */}
        <rect x={cx(0)} y={cy(0)} width={pw} height={ph} fill="url(#carbonWeave)" />

        {/* Plate boundary */}
        <rect x={cx(0)} y={cy(0)} width={pw} height={ph}
          fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth={1.5} rx={2} />

        {/* Origin marker */}
        <circle cx={cx(0)} cy={cy(0)} r={2.5} fill="none" stroke={COL.textDim} strokeWidth={0.8} />

        {axisLabels}
        {arrows}
        {defectShapes}
        {legend}

        {/* Axis titles */}
        <text x={cx(PLATE_LENGTH / 2)} y={cy(PLATE_WIDTH) + 28}
          fill={COL.textMid} fontSize={10} textAnchor="middle">{t("axis_x")}</text>
        <text x={cx(0) - 28} y={cy(PLATE_WIDTH / 2)} fill={COL.textMid} fontSize={10}
          textAnchor="middle"
          transform={`rotate(-90 ${cx(0) - 28} ${cy(PLATE_WIDTH / 2)})`}>
          {t("axis_y")}
        </text>
      </svg>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Helper — is a world-space point inside any active defect ellipse?
// Used by the canvas heatmap pass to distinguish true voids from
// cold regions in the stress field.
// ──────────────────────────────────────────────────────────────────
function isPointInAnyDefect(
  x: number, y: number,
  defects: DefectParams[],
  nDefects: number,
): boolean {
  for (let i = 0; i < nDefects; i++) {
    const d = defects[i];
    if (!d) continue;
    const rad = (-d.angle * Math.PI) / 180;
    const cosA = Math.cos(rad), sinA = Math.sin(rad);
    const dx = x - d.x, dy = y - d.y;
    const localX = cosA * dx + sinA * dy;
    const localY = -sinA * dx + cosA * dy;
    const a = d.half_length, b = Math.max(d.width / 2, 0.05);
    if ((localX * localX) / (a * a) + (localY * localY) / (b * b) < 1.0) return true;
  }
  return false;
}
