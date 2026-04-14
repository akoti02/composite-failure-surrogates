import type { ReactElement } from "react";
import { PLATE_LENGTH, PLATE_WIDTH, DEFECT_COLORS, COL } from "../lib/constants";
import type { DefectParams } from "../lib/types";
import { useT } from "../lib/i18n";

interface Props {
  nDefects: number;
  defects: DefectParams[];
  pressureX: number;
  pressureY: number;
}

export function PlateCanvas({ nDefects, defects, pressureX, pressureY }: Props) {
  const t = useT();
  const unitMPa = t("unit_mpa");
  const mx = 50, my = 28;
  const pw = 300, ph = 150;
  const sx = pw / PLATE_LENGTH;
  const sy = ph / PLATE_WIDTH;
  const cx = (px: number) => mx + px * sx;
  const cy = (py: number) => my + py * sy;
  const svgW = pw + mx * 2;
  const svgH = ph + my * 2;

  // Grid lines
  const gridLines: ReactElement[] = [];
  for (let g = 25; g < PLATE_LENGTH; g += 25) {
    gridLines.push(<line key={`gx${g}`} x1={cx(g)} y1={cy(0)} x2={cx(g)} y2={cy(PLATE_WIDTH)} stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4" />);
  }
  for (let g = 25; g < PLATE_WIDTH; g += 25) {
    gridLines.push(<line key={`gy${g}`} x1={cx(0)} y1={cy(g)} x2={cx(PLATE_LENGTH)} y2={cy(g)} stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4" />);
  }

  // Axis tick labels
  const axisLabels: ReactElement[] = [];
  for (let g = 0; g <= PLATE_LENGTH; g += 25) {
    axisLabels.push(<text key={`lx${g}`} x={cx(g)} y={cy(PLATE_WIDTH) + 16} fill={COL.textMid} fontSize={10} textAnchor="middle">{g}</text>);
  }
  for (let g = 0; g <= PLATE_WIDTH; g += 25) {
    axisLabels.push(<text key={`ly${g}`} x={cx(0) - 8} y={cy(g) + 4} fill={COL.textMid} fontSize={10} textAnchor="end">{g}</text>);
  }

  // Pressure arrows
  const arrows: ReactElement[] = [];
  const maxP = Math.max(Math.abs(pressureX), Math.abs(pressureY), 1);
  if (pressureX !== 0) {
    const dir = pressureX > 0 ? 1 : -1;
    const len = 10 + 20 * (Math.abs(pressureX) / maxP);
    [0.25, 0.5, 0.75].forEach((frac, i) => {
      const y = cy(PLATE_WIDTH * frac);
      const startX = dir > 0 ? cx(0) - len : cx(PLATE_LENGTH) + len;
      const endX = dir > 0 ? cx(0) : cx(PLATE_LENGTH);
      arrows.push(
        <line key={`ax${i}`} x1={startX} y1={y} x2={endX} y2={y}
          stroke="#60a5fa" strokeWidth={1.5} markerEnd="url(#arrowhead)" opacity={0.7} />
      );
    });
    arrows.push(
      <text key="plx" x={cx(pressureX > 0 ? 0 : PLATE_LENGTH) + (pressureX > 0 ? -len - 4 : len + 4)} y={cy(PLATE_WIDTH * 0.5) - 6}
        fill="#7fdbff" fontSize={11} fontWeight={600} textAnchor="middle" opacity={0.95}>{Math.abs(pressureX)} {unitMPa}</text>
    );
  }
  if (pressureY !== 0) {
    const dir = pressureY > 0 ? 1 : -1;
    const len = 10 + 20 * (Math.abs(pressureY) / maxP);
    [0.25, 0.5, 0.75].forEach((frac, i) => {
      const x = cx(PLATE_LENGTH * frac);
      const startY = dir > 0 ? cy(0) - len : cy(PLATE_WIDTH) + len;
      const endY = dir > 0 ? cy(0) : cy(PLATE_WIDTH);
      arrows.push(
        <line key={`ay${i}`} x1={x} y1={startY} x2={x} y2={endY}
          stroke="#60a5fa" strokeWidth={1.5} markerEnd="url(#arrowhead)" opacity={0.7} />
      );
    });
    arrows.push(
      <text key="ply" x={cx(PLATE_LENGTH * 0.5) + 30} y={cy(pressureY > 0 ? 0 : PLATE_WIDTH) + (pressureY > 0 ? -len + 2 : len + 10)}
        fill="#7fdbff" fontSize={11} fontWeight={600} textAnchor="middle" opacity={0.95}>{Math.abs(pressureY)} {unitMPa}</text>
    );
  }

  // Defect visualisation — compute label positions that avoid overlap
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

    // Try 8 candidate positions around the defect, pick the one farthest from existing labels
    const candidates = [
      { x: dcx + halfL + 6, y: dcy + 3 },      // right
      { x: dcx - halfL - 10, y: dcy + 3 },      // left
      { x: dcx, y: dcy - halfW - 6 },            // top
      { x: dcx, y: dcy + halfW + 10 },           // bottom
      { x: dcx + halfL + 6, y: dcy - 8 },        // top-right
      { x: dcx - halfL - 10, y: dcy - 8 },       // top-left
      { x: dcx + halfL + 6, y: dcy + 12 },       // bottom-right
      { x: dcx - halfL - 10, y: dcy + 12 },      // bottom-left
    ];

    let bestPos = candidates[0];
    let bestMinDist = 0;
    for (const cand of candidates) {
      let minDist = Infinity;
      for (const existing of labelPositions) {
        const dist = Math.hypot(cand.x - existing.x, cand.y - existing.y);
        if (dist < minDist) minDist = dist;
      }
      if (minDist > bestMinDist) {
        bestMinDist = minDist;
        bestPos = cand;
      }
    }
    labelPositions.push(bestPos);

    defectShapes.push(
      <g key={`d${i}`}>
        {/* Blurred halo — a duplicate of the ellipse, rendered below the
           crisp one. Isolating the glow to its own element means the
           label and shape stroke stay razor-sharp, unlike before when
           the filter was on the whole group and softened everything. */}
        <ellipse
          cx={dcx} cy={dcy}
          rx={halfL} ry={halfW}
          transform={`rotate(${d.angle} ${dcx} ${dcy})`}
          fill={DEFECT_COLORS[i]} fillOpacity={0.35}
          stroke="none"
          filter={`url(#defectGlow${i})`}
        />
        {/* Crisp shape */}
        <ellipse
          cx={dcx} cy={dcy}
          rx={halfL} ry={halfW}
          transform={`rotate(${d.angle} ${dcx} ${dcy})`}
          fill={DEFECT_COLORS[i]} fillOpacity={0.15}
          stroke={DEFECT_COLORS[i]} strokeWidth={1.5} strokeOpacity={1}
        />
        <line
          x1={cx(d.x - d.half_length * Math.cos(rad))}
          y1={cy(d.y - d.half_length * Math.sin(rad))}
          x2={cx(d.x + d.half_length * Math.cos(rad))}
          y2={cy(d.y + d.half_length * Math.sin(rad))}
          stroke={DEFECT_COLORS[i]} strokeWidth={1} strokeLinecap="round" strokeDasharray="3 2" strokeOpacity={0.7}
        />
        {/* Label with background for readability — outside the filter */}
        <circle cx={bestPos.x} cy={bestPos.y - 1} r={7}
          fill={COL.canvasBg} fillOpacity={0.92} stroke={DEFECT_COLORS[i]} strokeWidth={1.2} />
        <text x={bestPos.x} y={bestPos.y + 3} fill={DEFECT_COLORS[i]} fontSize={11} fontWeight="700" textAnchor="middle">
          {i + 1}
        </text>
      </g>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${svgW} ${svgH}`}
      className="w-full"
      style={{
        background: `radial-gradient(ellipse at 50% 45%, #141418 0%, ${COL.canvasBg} 100%)`,
        borderRadius: 10,
        border: `1px solid ${COL.border}`,
      }}
    >
      <defs>
        <marker id="arrowhead" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
          <polygon points="0 0, 7 2.5, 0 5" fill="#60a5fa" opacity="0.7" />
        </marker>
        {/* Fiber direction pattern */}
        <pattern id="fiberPattern" width="6" height="6" patternUnits="userSpaceOnUse">
          <line x1="3" y1="0" x2="3" y2="6" stroke="rgba(99,102,241,0.06)" strokeWidth="0.8" />
        </pattern>
        {/* Glow filters for each defect colour. Now applied only to the
           blurred halo ellipse (not the label), and with a tighter
           stdDeviation (2 instead of 4) so the glow reads as a subtle
           luminescence rather than a dust cloud. */}
        {DEFECT_COLORS.map((color, i) => (
          <filter key={`glow${i}`} id={`defectGlow${i}`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur" />
            <feFlood floodColor={color} floodOpacity="0.6" result="color" />
            <feComposite in="color" in2="blur" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
            </feMerge>
          </filter>
        ))}
      </defs>

      {/* Plate area */}
      {gridLines}
      {axisLabels}

      {/* Fiber direction overlay */}
      <rect x={cx(0)} y={cy(0)} width={pw} height={ph} fill="url(#fiberPattern)" />

      {/* Plate border */}
      <rect x={cx(0)} y={cy(0)} width={pw} height={ph}
        fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth={1.5} rx={2} />

      {/* Origin marker */}
      <circle cx={cx(0)} cy={cy(0)} r={2.5} fill="none" stroke={COL.textDim} strokeWidth={0.8} />

      {arrows}
      {defectShapes}

      {/* Axis labels */}
      <text x={cx(PLATE_LENGTH / 2)} y={cy(PLATE_WIDTH) + 18} fill={COL.textDim} fontSize={9} textAnchor="middle">
        {t("axis_x")}
      </text>
      <text x={cx(0) - 20} y={cy(PLATE_WIDTH / 2)} fill={COL.textDim} fontSize={9} textAnchor="middle"
        transform={`rotate(-90 ${cx(0) - 20} ${cy(PLATE_WIDTH / 2)})`}>
        {t("axis_y")}
      </text>
    </svg>
  );
}
