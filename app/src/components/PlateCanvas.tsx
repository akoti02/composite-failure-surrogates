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
  resolution?: number;
  component?: FieldComponent;
  colormap?: ColorMap;
  showContours?: boolean;
  showLegend?: boolean;
}

/**
 * PlateCanvas — analytical stress-field visualization.
 *
 * Layered rendering, back-to-front:
 *
 *   [parent div] provides the radial-gradient ambient background AND the
 *                aspect-ratio box. Canvas + SVG are absolutely positioned
 *                inside and share the same pixel rectangle.
 *
 *   Layer 0 (parent background)   — radial gradient, deep indigo-black.
 *   Layer 1 (canvas)              — Lekhnitskii stress field painted at
 *                                   grid resolution (e.g. 80×40) via
 *                                   ImageData, stretched with CSS to the
 *                                   plate rectangle. Viridis colourmap.
 *   Layer 2 (svg, TRANSPARENT)    — iso-stress contours, carbon-weave
 *                                   pattern, defect shapes, pressure
 *                                   arrows, axis labels, colorbar legend.
 *                                   No fill/background, so the canvas
 *                                   underneath is visible.
 *
 * Previously the SVG had its own radial-gradient background, which hid
 * the canvas heatmap entirely — that's why v0.3.6 looked broken. This
 * version moves the gradient to the parent div and keeps the SVG
 * fully transparent except for its explicit strokes and fills.
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

  // viewBox layout. Note the generous top/right margins: the top
  // accommodates the PY pressure label *above* the plate, the right
  // accommodates the legend colorbar without overlapping axis labels.
  const mx = 56;           // left margin
  const my = 44;           // top margin (holds PY label cleanly above plate)
  const mRight = 64;       // right margin (axis labels + legend)
  const mBottom = 56;      // bottom margin (axis labels + optional PY label)
  const pw = 360;          // plate width in viewBox units
  const ph = 180;          // plate height in viewBox units
  const svgW = pw + mx + mRight;
  const svgH = ph + my + mBottom;
  const sx = pw / PLATE_LENGTH;
  const sy = ph / PLATE_WIDTH;
  const cx = (px: number) => mx + px * sx;
  const cy = (py: number) => my + py * sy;

  // ────────────────────────────────────────────────────────────────
  // Compute stress field (memoized by inputs).
  // ────────────────────────────────────────────────────────────────
  const field = useMemo<StressFieldResult | null>(() => {
    const mat = materialKey ? MATERIAL_DB[materialKey] : MATERIAL_DB["T300/5208"];
    if (!mat) return null;
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

  const scalar = useMemo(() => field ? extractField(field, component) : null, [field, component]);

  // ────────────────────────────────────────────────────────────────
  // Paint the canvas heatmap. Runs whenever the field or colourmap changes.
  // ────────────────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const nx = field?.nx ?? resolution;
    const ny = field?.ny ?? Math.max(2, Math.round(resolution * (PLATE_WIDTH / PLATE_LENGTH)));
    canvas.width = nx;
    canvas.height = ny;

    if (!field || !scalar) {
      // No stress applied — fill with a cool dark tone so the plate
      // region reads as a material surface rather than transparent.
      ctx.fillStyle = "#14141a";
      ctx.fillRect(0, 0, nx, ny);
      return;
    }

    const img = ctx.createImageData(nx, ny);
    const px = img.data;
    const { data, min, max } = scalar;
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const v = data[j * nx + i];
        // World-space sample point at this canvas pixel (pixel centres)
        const wx = (i / (nx - 1)) * PLATE_LENGTH;
        const wy = (j / (ny - 1)) * PLATE_WIDTH;
        // If this pixel falls inside any defect ellipse, paint a near-
        // black void so the heatmap clearly shows the hole. Always run
        // this check (not just when v === 0) — with multiple defects the
        // superposition may yield a non-zero residual even when a point
        // sits inside one of them.
        let r: number, g: number, b: number;
        if (isPointInAnyDefect(wx, wy, defects, nDefects)) {
          r = 6; g = 6; b = 10;
        } else {
          [r, g, b] = mapColor(v, min, max, colormap);
        }
        const idx = (j * nx + i) * 4;
        px[idx] = r; px[idx + 1] = g; px[idx + 2] = b; px[idx + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [field, scalar, colormap, defects, nDefects, resolution]);

  // ────────────────────────────────────────────────────────────────
  // Iso-stress contour paths (d3-contour). Grid units → viewBox units.
  // ────────────────────────────────────────────────────────────────
  const contourPaths = useMemo(() => {
    if (!showContours || !field || !scalar) return [];
    const { nx, ny } = field;
    const { data, min, max } = scalar;
    if (max - min < 1e-6) return [];
    const nLevels = 6;
    const thresholds = Array.from({ length: nLevels }, (_, k) =>
      min + ((k + 1) / (nLevels + 1)) * (max - min)
    );
    const gen = d3contours().size([nx, ny]).thresholds(thresholds);
    const features = gen(Array.from(data));
    return features.map((f, idx) => {
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
      return { id: idx, d };
    });
  }, [showContours, field, scalar, mx, my, pw, ph]);

  // ────────────────────────────────────────────────────────────────
  // Pressure arrows + labels.
  // PX arrows live to the LEFT or RIGHT of the plate, with the magnitude
  // label centered alongside them (vertically centered on the plate).
  // PY arrows live ABOVE or BELOW the plate, with the magnitude label
  // placed in the outer margin so it never overlaps the plate body.
  // ────────────────────────────────────────────────────────────────
  const arrowColor = "#7fdbff";
  const arrowEls: ReactElement[] = [];
  const maxP = Math.max(Math.abs(pressureX), Math.abs(pressureY), 1);

  if (pressureX !== 0) {
    const dir = pressureX > 0 ? 1 : -1;
    const len = 18 + 28 * (Math.abs(pressureX) / maxP);
    // 3 arrow lines
    [0.22, 0.5, 0.78].forEach((frac, i) => {
      const y = cy(PLATE_WIDTH * frac);
      const startX = dir > 0 ? cx(0) - len : cx(PLATE_LENGTH) + len;
      const endX = dir > 0 ? cx(0) : cx(PLATE_LENGTH);
      arrowEls.push(
        <line key={`ax${i}`} x1={startX} y1={y} x2={endX} y2={y}
          stroke={arrowColor} strokeWidth={2} strokeLinecap="round"
          markerEnd="url(#arrowhead)"
          style={{ filter: `drop-shadow(0 0 3px ${arrowColor}88)` }} />
      );
    });
    // Label: just past the arrow tails, vertically centered, always outside plate
    const labelX = dir > 0 ? cx(0) - len - 8 : cx(PLATE_LENGTH) + len + 8;
    arrowEls.push(
      <text key="plx" x={labelX} y={cy(PLATE_WIDTH * 0.5) + 4}
        fill={arrowColor} fontSize={12} fontWeight={700}
        textAnchor={dir > 0 ? "end" : "start"}
        style={{ filter: `drop-shadow(0 0 4px ${arrowColor}aa)` }}>
        {Math.abs(pressureX)} {unitMPa}
      </text>
    );
  }

  if (pressureY !== 0) {
    const dir = pressureY > 0 ? 1 : -1;
    const len = 18 + 28 * (Math.abs(pressureY) / maxP);
    [0.22, 0.5, 0.78].forEach((frac, i) => {
      const x = cx(PLATE_LENGTH * frac);
      const startY = dir > 0 ? cy(0) - len : cy(PLATE_WIDTH) + len;
      const endY = dir > 0 ? cy(0) : cy(PLATE_WIDTH);
      arrowEls.push(
        <line key={`ay${i}`} x1={x} y1={startY} x2={x} y2={endY}
          stroke={arrowColor} strokeWidth={2} strokeLinecap="round"
          markerEnd="url(#arrowhead)"
          style={{ filter: `drop-shadow(0 0 3px ${arrowColor}88)` }} />
      );
    });
    // Label: OUTSIDE the plate, centered horizontally, just past the arrow tails
    const labelY = dir > 0
      ? cy(0) - len - 8             // above the top arrows
      : cy(PLATE_WIDTH) + len + 16; // below the bottom arrows
    arrowEls.push(
      <text key="ply" x={cx(PLATE_LENGTH * 0.5)} y={labelY}
        fill={arrowColor} fontSize={12} fontWeight={700} textAnchor="middle"
        style={{ filter: `drop-shadow(0 0 4px ${arrowColor}aa)` }}>
        {Math.abs(pressureY)} {unitMPa}
      </text>
    );
  }

  // ────────────────────────────────────────────────────────────────
  // Defect shapes — now with a dark semi-opaque fill so they always
  // read as holes/cracks, not just two parallel stroke lines. A minimum
  // visual radius ensures thin cracks (0.5 mm wide) are still legible.
  // ────────────────────────────────────────────────────────────────
  const labelPositions: { x: number; y: number }[] = [];
  const defectShapes: ReactElement[] = [];
  const plateLeft = cx(0), plateRight = cx(PLATE_LENGTH);
  const plateTop = cy(0), plateBottom = cy(PLATE_WIDTH);
  for (let i = 0; i < nDefects; i++) {
    const d = defects[i];
    if (!d) continue;
    const rad = (d.angle * Math.PI) / 180;
    // Minimum visual radius of 2.5 px for either axis — cracks stay
    // legible even at tiny widths. This is a display-only clamp; the
    // underlying stress-field math uses the real geometry.
    const halfW = Math.max(d.width * sy * 0.5, 2.5);
    const halfL = Math.max(d.half_length * sx, 3);
    const dcx = cx(d.x);
    const dcy = cy(d.y);

    // Candidate label anchor points around the defect. Discard any that
    // fall outside the plate rectangle so labels stay visible.
    const rawCandidates = [
      { x: dcx + halfL + 10, y: dcy + 4 },
      { x: dcx - halfL - 10, y: dcy + 4 },
      { x: dcx, y: dcy - halfW - 10 },
      { x: dcx, y: dcy + halfW + 14 },
      { x: dcx + halfL + 10, y: dcy - 10 },
      { x: dcx - halfL - 10, y: dcy - 10 },
      { x: dcx + halfL + 10, y: dcy + 16 },
      { x: dcx - halfL - 10, y: dcy + 16 },
    ];
    const candidates = rawCandidates.filter(c =>
      c.x > plateLeft + 6 && c.x < plateRight - 6 &&
      c.y > plateTop + 10 && c.y < plateBottom - 4
    );
    const pickFrom = candidates.length > 0 ? candidates : rawCandidates;
    let bestPos = pickFrom[0], bestMinDist = 0;
    for (const cand of pickFrom) {
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
        {/* Defect body — dark fill reads as a hole; coloured stroke
            makes the outline crisp against the heatmap. */}
        <ellipse
          cx={dcx} cy={dcy} rx={halfL} ry={halfW}
          transform={`rotate(${d.angle} ${dcx} ${dcy})`}
          fill="rgba(8, 8, 14, 0.92)"
          stroke={DEFECT_COLORS[i]} strokeWidth={1.8}
          style={{ filter: `drop-shadow(0 0 5px ${DEFECT_COLORS[i]}bb)` }}
        />
        {/* Crack axis line inside the defect, showing orientation */}
        <line
          x1={cx(d.x - d.half_length * Math.cos(rad))}
          y1={cy(d.y - d.half_length * Math.sin(rad))}
          x2={cx(d.x + d.half_length * Math.cos(rad))}
          y2={cy(d.y + d.half_length * Math.sin(rad))}
          stroke={DEFECT_COLORS[i]} strokeWidth={1} strokeLinecap="round"
          strokeDasharray="4 2.5" strokeOpacity={0.85}
        />
        {/* Numbered label — circle with solid bg so the number stays
            readable even if placed over a bright region of the heatmap. */}
        <circle cx={bestPos.x} cy={bestPos.y - 1} r={8}
          fill="rgba(15, 15, 22, 0.96)"
          stroke={DEFECT_COLORS[i]} strokeWidth={1.3}
          style={{ filter: `drop-shadow(0 0 3px ${DEFECT_COLORS[i]}77)` }} />
        <text x={bestPos.x} y={bestPos.y + 3}
          fill={DEFECT_COLORS[i]} fontSize={11} fontWeight={800} textAnchor="middle">
          {i + 1}
        </text>
      </g>
    );
  }

  // ────────────────────────────────────────────────────────────────
  // Axis labels — 25 mm increments. Placed outside the plate rectangle.
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

  // ────────────────────────────────────────────────────────────────
  // Colorbar legend (vertical). Positioned well clear of axis labels.
  // ────────────────────────────────────────────────────────────────
  const legendEls: ReactElement[] = [];
  if (showLegend && scalar) {
    const lxRight = cx(PLATE_LENGTH) + 28;
    const lTop = cy(0) + 6;
    const lH = ph - 12;
    const lW = 10;
    const stops = 20;
    for (let k = 0; k < stops; k++) {
      const t = 1 - k / (stops - 1);
      const v = scalar.min + t * (scalar.max - scalar.min);
      const [r, g, b] = mapColor(v, scalar.min, scalar.max, colormap);
      legendEls.push(
        <rect key={`leg${k}`} x={lxRight} y={lTop + (k / stops) * lH}
          width={lW} height={lH / stops + 0.5}
          fill={`rgb(${r},${g},${b})`} />
      );
    }
    legendEls.push(
      <rect key="legbox" x={lxRight} y={lTop} width={lW} height={lH}
        fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth={0.6} />
    );
    legendEls.push(
      <text key="legmax" x={lxRight + lW + 4} y={lTop + 5}
        fill={COL.textMid} fontSize={9} fontWeight={600}>{scalar.max.toFixed(0)}</text>
    );
    legendEls.push(
      <text key="legmin" x={lxRight + lW + 4} y={lTop + lH + 2}
        fill={COL.textMid} fontSize={9} fontWeight={600}>{scalar.min.toFixed(0)}</text>
    );
    legendEls.push(
      <text key="legunit" x={lxRight + lW / 2} y={lTop + lH + 14}
        fill={COL.textDim} fontSize={9} textAnchor="middle">{unitMPa}</text>
    );
  }

  return (
    <div
      className="relative w-full"
      style={{
        aspectRatio: `${svgW} / ${svgH}`,
        background: `radial-gradient(ellipse at 50% 45%, #141418 0%, ${COL.canvasBg} 100%)`,
        borderRadius: 10,
        border: `1px solid ${COL.border}`,
        overflow: "hidden",
      }}
    >
      {/* Canvas heatmap — occupies exactly the plate rectangle, stretched
          from grid-resolution pixels to the plate rectangle in viewBox
          units. Positioned in % so it tracks any container size. */}
      <canvas
        ref={canvasRef}
        style={{
          position: "absolute",
          left: `${(mx / svgW) * 100}%`,
          top: `${(my / svgH) * 100}%`,
          width: `${(pw / svgW) * 100}%`,
          height: `${(ph / svgH) * 100}%`,
          imageRendering: "auto",
          borderRadius: 3,
          zIndex: 0,
        }}
      />

      {/* SVG overlay — fully transparent, sits on top of the canvas */}
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        preserveAspectRatio="xMidYMid meet"
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          zIndex: 1,
          pointerEvents: "none",
        }}
      >
        <defs>
          <marker id="arrowhead" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
            <polygon points="0 0, 7 2.5, 0 5" fill={arrowColor} opacity="0.95" />
          </marker>
          <pattern id="carbonWeave" width="8" height="8" patternUnits="userSpaceOnUse">
            <path d="M0,8 L8,0" stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
            <path d="M0,0 L8,8" stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
          </pattern>
        </defs>

        {/* Iso-stress contour lines */}
        {contourPaths.map(c => (
          <path key={c.id} d={c.d} fill="none"
            stroke="rgba(255,255,255,0.35)" strokeWidth={0.7}
            style={{ mixBlendMode: "screen" }} />
        ))}

        {/* Carbon weave overlay, only inside the plate rectangle */}
        <rect x={cx(0)} y={cy(0)} width={pw} height={ph} fill="url(#carbonWeave)" />

        {/* Plate border */}
        <rect x={cx(0)} y={cy(0)} width={pw} height={ph}
          fill="none" stroke="rgba(255,255,255,0.28)" strokeWidth={1.5} rx={2} />

        {/* Origin marker */}
        <circle cx={cx(0)} cy={cy(0)} r={2.5} fill="none" stroke={COL.textDim} strokeWidth={0.8} />

        {axisLabels}
        {arrowEls}
        {defectShapes}
        {legendEls}

        {/* Axis titles */}
        <text x={cx(PLATE_LENGTH / 2)} y={cy(PLATE_WIDTH) + 34}
          fill={COL.textMid} fontSize={11} textAnchor="middle" fontWeight={500}>{t("axis_x")}</text>
        <text x={cx(0) - 34} y={cy(PLATE_WIDTH / 2)} fill={COL.textMid} fontSize={11}
          textAnchor="middle" fontWeight={500}
          transform={`rotate(-90 ${cx(0) - 34} ${cy(PLATE_WIDTH / 2)})`}>
          {t("axis_y")}
        </text>
      </svg>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Helper: is a world-space point inside any active defect ellipse?
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
