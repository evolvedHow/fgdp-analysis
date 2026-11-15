import React, { useMemo } from 'react';
import { useSvgPanZoom } from '../lib/useSvgPanZoom';
import Section from './Section';
import FigureTools from './FigureTools';
import { fmtInt, fmtPct, fmtPts, PARTY } from '../lib/data';

/**
 * Competitive zone, as FDGA and the Princeton Gerrymandering Project define it:
 * a district whose two-party Democratic share lands between 46.5% and 53.5%.
 */
const BAND = [0.465, 0.535];

/** Margin buckets used for the competitiveness composition bars. */
const MARGIN_BUCKETS = [
  { key: 'close', label: 'inside 5', test: (m) => m < 5, fill: '#4c2b86' },
  { key: 'lean', label: '5–10', test: (m) => m >= 5 && m < 10, fill: '#8b6fc4' },
  { key: 'safe', label: '10–20', test: (m) => m >= 10 && m < 20, fill: '#c3b6e0' },
  { key: 'foregone', label: '20+', test: (m) => m >= 20, fill: '#e6e2f2' },
];

/** Signed point shift, e.g. +36.1 pts (shiftPts is already in points). */
const pts = (v) => `${v > 0 ? '+' : ''}${v.toFixed(1)} pts`;

/** District label per chamber: HD / SD / CD. */
const PREFIX = { state_house: 'HD', state_senate: 'SD', us_house: 'CD' };

/**
 * Section 3 — how the 2024 map changed the election, holding the voters fixed.
 *
 * The same 2024 presidential votes are counted twice: once under the 2021–23
 * lines, once under the 2024 remedial lines. Both plan files carry per-district
 * shares derived from the same VTD vote file, so the difference between the two
 * counts is the map and nothing else — no turnout change, no candidate quality,
 * no estimation.
 */
export default function MapEffect({ effect, sources, chamberLabel, year }) {
  const districts = useMemo(() => {
    if (!effect) return [];
    // Sorted by gain: Democrats' largest gains at the top, losses at the bottom.
    return [...effect.districts].sort((a, b) => b.shiftPts - a.shiftPts);
  }, [effect]);

  const p24 = useMemo(
    () => effect?.signals.find((s) => s.key === 'p24') || effect?.signals[0],
    [effect],
  );

  if (!effect || !p24) return null;

  const prior = effect.index.prior;
  const current = effect.index.current;
  const disp = effect.displacement;

  const lostByD = p24.flips.filter((f) => f.priorParty === 'D');
  const wonByD = p24.flips.filter((f) => f.priorParty === 'R');
  const netSeats = p24.currentSeatsD - p24.priorSeatsD;
  const seatWord = netSeats === 0 ? 'no net change' : `${netSeats > 0 ? '+' : ''}${netSeats} seat`;

  const remedyIds = effect.becameBvapMajority.map((r) => r.district);
  const source = (id) => sources?.find((s) => s.id === id);
  const dc = PREFIX[effect.chamber] || 'District';

  // Congressional districts are already equal to the person, so the population
  // that equality "requires" is a handful of people; a multiple against it is
  // meaningless and is replaced with the plain share.
  const minimumIsTrivial = disp.arithmeticMinimum < 1000;
  const multipleLabel =
    !minimumIsTrivial && disp.multiple
      ? `${disp.multiple.toFixed(0)}× the arithmetic minimum`
      : 'against almost no required movement';

  const inBand = (pct) => pct >= BAND[0] && pct <= BAND[1];
  const bandPrior = effect.districts.filter((d) => inBand(d.priorPct)).length;
  const bandCurrent = effect.districts.filter((d) => inBand(d.currentPct)).length;

  const moved = disp.districts || [];
  const heavy = moved.filter((d) => d.displacedPct >= 0.3).length;
  const worst = moved.slice(0, 6);

  // ---------------------------------------------------------------- figure 1
  const W = 640;
  const rowH = 3.2;
  const M = { top: 24, right: 140, bottom: 26, left: 12 };
  const plotW = W - M.left - M.right;
  const H = M.top + districts.length * rowH + M.bottom;
  const domain = [0.2, 0.85];
  const x = (v) => {
    const t = (Math.min(domain[1], Math.max(domain[0], v)) - domain[0]) / (domain[1] - domain[0]);
    return M.left + t * plotW;
  };

  // ---------------------------------------------------------------- figure 2
  const CW = 640;
  const CH = 116;
  const CM = { top: 20, right: 74, bottom: 34, left: 66 };
  const cPlotW = CW - CM.left - CM.right;
  const barH = 20;
  const buckets = MARGIN_BUCKETS.map((b) => ({
    ...b,
    prior: effect.districts.filter((d) => b.test(Math.abs(d.priorPct - 0.5) * 100)).length,
    current: effect.districts.filter((d) => b.test(Math.abs(d.currentPct - 0.5) * 100)).length,
  }));
  const rowsFor = [
    { key: 'prior', label: effect.prior.label, y: CM.top },
    { key: 'current', label: effect.current.label, y: CM.top + 46 },
  ];

  // ---------------------------------------------------------------- figure 3
  const DW = 640;
  const DH = 200;
  const DM = { top: 40, right: 14, bottom: 30, left: 12 };
  const dPlotW = DW - DM.left - DM.right;
  const dPlotH = DH - DM.top - DM.bottom;
  const slot = dPlotW / Math.max(1, moved.length);
  const maxMove = Math.max(0.05, ...moved.map((d) => d.displacedPct || 0));

  // Pan/zoom for dumbbell chart
  const { viewBox: dumbViewBox, svgRef: dumbRef } = useSvgPanZoom(W, H, 1, 10);

  return (
    <Section
      id="mapswap"
      step="03"
      kicker={`The map swap · ${chamberLabel}`}
      title={
        lostByD.length && wonByD.length
          ? `The new map gave Democrats ${wonByD.length} district${wonByD.length === 1 ? '' : 's'} and took ${lostByD.length} away`
          : 'Same voters, different lines'
      }
      lede={`The 2024 presidential vote, counted twice: under the ${effect.prior.label} and under the ${effect.current.label}. The seat count moves from ${p24.priorSeatsD} to ${p24.currentSeatsD} (${seatWord}), while ${fmtInt(disp.people)} people — ${fmtPct(disp.pct)} of the state — land in a different district.`}
      aside={
        <>
          <p className="aside-title">What the swap did not change</p>
          <dl className="index-list">
            <div>
              <dt>Seats leaning Democratic</dt>
              <dd>
                {p24.priorSeatsD} → <strong>{p24.currentSeatsD}</strong>
              </dd>
            </div>
            <div>
              <dt>Inside the competitive zone</dt>
              <dd>
                {bandPrior} → <strong>{bandCurrent}</strong>
              </dd>
            </div>
            <div>
              <dt>Decided by less than 5 points</dt>
              <dd>
                {prior.competitive5} → <strong>{current.competitive5}</strong>
              </dd>
            </div>
            <div>
              <dt>Decided by less than 10 points</dt>
              <dd>
                {prior.competitive10} → <strong>{current.competitive10}</strong>
              </dd>
            </div>
            <div>
              <dt>Average margin</dt>
              <dd>
                {prior.meanMargin.toFixed(1)} → <strong>{current.meanMargin.toFixed(1)} pts</strong>
              </dd>
            </div>
            <div>
              <dt>Median district lean</dt>
              <dd>
                {(prior.medianLean * 100).toFixed(1)} →{' '}
                <strong>{(current.medianLean * 100).toFixed(1)}% D</strong>
              </dd>
            </div>
          </dl>
          <p className="micro-note">
            The median district sits {Math.abs((0.5 - current.medianLean) * 100).toFixed(1)} points
            from a tie ({current.medianLean < 0.5 ? 'toward Republicans' : 'toward Democrats'}) while
            the average district sits at {(current.meanLean * 100).toFixed(1)}% D. When the middle
            district and the average district disagree, one party is packed into fewer districts.
          </p>
        </>
      }
      footer={`Method: both plan files carry district-level shares computed from one VTD vote file, so the two counts differ only by the lines. Displacement is area-weighted population reassignment; the "arithmetic minimum" is the population that equalising district sizes requires (${fmtInt(disp.arithmeticMinimum)} people, ${fmtPct(disp.arithmeticMinimumPct, 2)}). Competitive zone = 46.5–53.5% two-party Democratic share, the threshold used in FDGA's 2022 evaluation with the Princeton Gerrymandering Project.`}
    >
      <div className="kpi-row">
        <div className="kpi is-flag">
          <span className="kpi-label">People reassigned</span>
          <strong>{fmtInt(disp.people)}</strong>
          <span className="kpi-sub">
            {fmtPct(disp.pct)} of Georgia · {multipleLabel}
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Districts changing hands</span>
          <strong>{p24.flips.length}</strong>
          <span className="kpi-sub">
            {wonByD.length} to Democrats, {lostByD.length} to Republicans
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Net seat change</span>
          <strong>{seatWord}</strong>
          <span className="kpi-sub">
            {p24.priorSeatsD} → {p24.currentSeatsD} of {effect.seats} seats
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Competitive seats</span>
          <strong>{bandCurrent}</strong>
          <span className="kpi-sub">
            inside 3.5 points, out of {effect.seats}
          </span>
        </div>
      </div>

      <figure className="chart">
        <FigureTools
          name={`map-swap-${effect.chamber}`}
          title={`${effect.label}: each district's 2024 vote under both maps`}
          subtitle="Every district, sorted by how far the 2024 presidential vote moved when the lines changed"
        />
        <figcaption>
          The 2024 presidential vote in every district, under the old lines and the new ones
        </figcaption>
        <svg
          viewBox={dumbViewBox}
          ref={dumbRef}
          style={{ cursor: 'grab', userSelect: 'none' }}
          role="img"
          aria-label={`Dumbbell chart: 2024 Democratic share in all ${effect.seats} districts under the 2021-23 lines and the 2024 lines. Use mouse wheel to zoom, drag to pan.`}
        >
          <rect
            x={x(BAND[0])}
            y={M.top - 6}
            width={x(BAND[1]) - x(BAND[0])}
            height={H - M.top - M.bottom + 10}
            fill="#6440a4"
            opacity="0.07"
          />

          {[0.25, 0.5, 0.75].map((t) => (
            <g key={t}>
              <line
                x1={x(t)}
                x2={x(t)}
                y1={M.top - 6}
                y2={H - M.bottom + 4}
                className={t === 0.5 ? 'zero-line' : 'gridline'}
              />
              <text x={x(t)} y={M.top - 10} textAnchor="middle" className="axis-label">
                {Math.round(t * 100)}% D
              </text>
            </g>
          ))}

          {districts.map((d, i) => {
            const y = M.top + i * rowH + rowH / 2;
            const up = d.shiftPts > 0;
            const big = Math.abs(d.shiftPts) >= 10;
            const flip = (d.priorPct > 0.5) !== (d.currentPct > 0.5);
            return (
              <g key={d.district} opacity={big ? 1 : 0.55}>
                <line
                  x1={x(d.priorPct)}
                  x2={x(d.currentPct)}
                  y1={y}
                  y2={y}
                  stroke={up ? PARTY.D : PARTY.R}
                  strokeWidth={flip ? 1.6 : 1}
                  opacity={flip ? 0.9 : 0.45}
                />
                <circle cx={x(d.priorPct)} cy={y} r={big ? 1.9 : 1.5} fill="#a9a3bf" />
                <circle
                  cx={x(d.currentPct)}
                  cy={y}
                  r={big ? 2.2 : 1.6}
                  fill={d.currentPct > 0.5 ? PARTY.D : PARTY.R}
                />
                {big && (
                  <text
                    x={W - M.right + 8}
                    y={y + 3}
                    className="axis-label is-current"
                    fontSize="9.5"
                    fill={up ? PARTY.D : PARTY.R}
                  >
                    {dc} {d.district}
                  </text>
                )}
              </g>
            );
          })}

          <line
            x1={M.left}
            x2={W - M.right}
            y1={H - M.bottom}
            y2={H - M.bottom}
            className="axis-line"
          />
          <text
            x={(x(BAND[0]) + x(BAND[1])) / 2}
            y={H - M.bottom + 16}
            textAnchor="middle"
            className="axis-label"
          >
            competitive zone
          </text>
        </svg>
      </figure>

      <p className="micro-note">
        Grey dot: the same district under the {effect.prior.label}. Coloured dot: under the{' '}
        {effect.current.label}. A line crossing the shaded band is a district that left the
        competitive zone without a single voter changing their mind.
      </p>

      <figure className="chart">
        <FigureTools
          name={`map-swap-margins-${effect.chamber}`}
          title={`${effect.label}: how safe each seat is, before and after`}
          subtitle="Districts grouped by the 2024 presidential margin, under each set of lines"
        />
        <figcaption>How many seats are decided by how much</figcaption>
        <svg
          viewBox={`0 0 ${CW} ${CH}`}
          role="img"
          aria-label="Two stacked bars comparing the number of safe and competitive seats under both maps"
        >
          {rowsFor.map((row) => {
            let offset = 0;
            return (
              <g key={row.key}>
                <text
                  x={CM.left - 8}
                  y={row.y + barH / 2 + 4}
                  textAnchor="end"
                  className={`axis-label ${row.key === 'current' ? 'is-current' : ''}`}
                >
                  {row.label}
                </text>
                {buckets.map((b) => {
                  const count = b[row.key];
                  const w = (count / effect.seats) * cPlotW;
                  const bx = CM.left + offset;
                  offset += w;
                  return (
                    <g key={b.key}>
                      <rect x={bx} y={row.y} width={Math.max(0, w)} height={barH} fill={b.fill} />
                      {w > 26 && (
                        <text
                          x={bx + w / 2}
                          y={row.y + barH / 2 + 3.5}
                          textAnchor="middle"
                          className="bar-value"
                          fill={b.key === 'close' ? '#ffffff' : '#3a3550'}
                        >
                          {count}
                        </text>
                      )}
                    </g>
                  );
                })}
                <text
                  x={CM.left + cPlotW + 8}
                  y={row.y + barH / 2 + 4}
                  className="axis-label"
                >
                  {buckets[3][row.key]} seats 20+
                </text>
              </g>
            );
          })}
          {buckets.map((b, i) => {
            const priorOffset = buckets
              .slice(0, i)
              .reduce((s, prev) => s + (prev.prior / effect.seats) * cPlotW, 0);
            return (
              <g key={`legend-${b.key}`}>
                <rect
                  x={CM.left + priorOffset}
                  y={CH - 22}
                  width={9}
                  height={9}
                  rx="2"
                  fill={b.fill}
                />
                <text x={CM.left + priorOffset + 13} y={CH - 14} className="axis-label">
                  {b.label}
                </text>
              </g>
            );
          })}
          <text x={CW - 6} y={CH - 14} textAnchor="end" className="axis-label">
            margin in points
          </text>
        </svg>
      </figure>

      <figure className="chart">
        <FigureTools
          name={`map-swap-displacement-${effect.chamber}`}
          title={`${effect.label}: how much of each district's population was moved`}
          subtitle="Share of each district's residents reassigned to a different district, sorted largest first; tick shows the share population equality required"
        />
        <figcaption>Population moved out of each district, against what equality required</figcaption>
        <svg
          viewBox={`0 0 ${DW} ${DH}`}
          role="img"
          aria-label="Bar chart of the share of each district's population reassigned, compared with the share required for population equality"
        >
          {[0, 0.25, 0.5, 0.75].map((t) => (
            <g key={t}>
              <line
                x1={DM.left}
                x2={DW - DM.right}
                y1={DM.top + dPlotH * t}
                y2={DM.top + dPlotH * t}
                className="gridline"
              />
              <text x={DM.left} y={DM.top + dPlotH * t - 4} className="axis-label">
                {Math.round((1 - t) * maxMove * 100)}%
              </text>
            </g>
          ))}

          {moved.map((d, i) => {
            const pct = d.displacedPct || 0;
            const h = (pct / maxMove) * dPlotH;
            const bx = DM.left + i * slot;
            const requiredH = Math.max(0.6, ((d.requiredPct || 0) / maxMove) * dPlotH);
            return (
              <g key={d.district}>
                <rect
                  x={bx}
                  y={DM.top + dPlotH - h}
                  width={Math.max(1, slot - 0.6)}
                  height={Math.max(0.6, h)}
                  fill={pct >= 0.3 ? '#7d3169' : '#b9a7c9'}
                />
                <rect
                  x={bx}
                  y={DM.top + dPlotH - requiredH}
                  width={Math.max(1, slot - 0.6)}
                  height={requiredH}
                  fill="#1c1a2b"
                  opacity="0.55"
                />
              </g>
            );
          })}

          <line
            x1={DM.left}
            x2={DW - DM.right}
            y1={DM.top + dPlotH}
            y2={DM.top + dPlotH}
            className="axis-line"
          />
          {worst.slice(0, 6).map((d, i) => {
            const barIdx = moved.indexOf(d);
            const barX = DM.left + barIdx * slot + slot / 2;
            const barTopY = DM.top + dPlotH - (d.displacedPct / maxMove) * dPlotH;
            // Alternate label position: above and below to avoid overlap
            const isAbove = i % 2 === 0;
            const labelY = isAbove ? barTopY - 14 : barTopY + 12;
            return (
              <g key={`lbl-${d.district}`}>
                {isAbove && (
                  <line
                    x1={barX}
                    x2={barX}
                    y1={barTopY}
                    y2={barTopY - 10}
                    stroke="#d7d3e3"
                    strokeWidth="0.5"
                    opacity="0.6"
                  />
                )}
                <text
                  x={barX}
                  y={labelY}
                  textAnchor="middle"
                  className="axis-label"
                  fontSize="9"
                  fontWeight="600"
                  fill="#4c4863"
                >
                  {d.district}
                </text>
              </g>
            );
          })}
          <text x={DW - DM.right} y={DH - 10} textAnchor="end" className="axis-label">
            {moved.length} districts · dark bar above 30% moved
          </text>
        </svg>
      </figure>

      <p className="micro-note">
        {heavy} districts had at least 30% of their residents reassigned; the four largest are
        labelled. The black tick on each bar is the share that had to move to equalise population —
        under 1% almost everywhere. Districts keep their numbers between plans, so “moved” means
        residents of district {worst[0]?.district} were handed to a different member.
      </p>

      <div className="law-note">
        <p>
          <strong>There is no legal limit on how many voters a map may move.</strong>{' '}
          {minimumIsTrivial ? (
            <>
              Equalising district populations required moving {fmtInt(disp.arithmeticMinimum)}{' '}
              people, so the {fmtInt(disp.people)} reassigned here are not explained by population
              equality at all.
            </>
          ) : (
            <>
              The {fmtInt(disp.people)} people above are {disp.multiple?.toFixed(0)}× the{' '}
              {fmtInt(disp.arithmeticMinimum)} ({fmtPct(disp.arithmeticMinimumPct, 2)}) that
              equalising district populations forces any map to move.
            </>
          )}{' '}
          That is arithmetic, not a rule: exceeding it is not, by itself, unlawful, and this story
          does not claim that it is.
        </p>
        <p>
          <strong>What the court did order:</strong> on 26 October 2023 a federal court held that
          the 2021 House and Senate plans violated{' '}
          {source('vra-section-2') ? (
            <a href={source('vra-section-2').url} target="_blank" rel="noreferrer">
              Section 2 of the Voting Rights Act
            </a>
          ) : (
            'Section 2 of the Voting Rights Act'
          )}{' '}
          and required five new Black-majority House districts (
          {source('alpha-phi-alpha-case') ? (
            <a href={source('alpha-phi-alpha-case').url} target="_blank" rel="noreferrer">
              case record
            </a>
          ) : (
            'case record'
          )}
          ). Measured by voting-age population, the 2024 map created exactly{' '}
          {remedyIds.length === 1 ? 'one' : remedyIds.length}: {dc}{' '}
          {remedyIds.join(`, ${dc} `)} — and no district lost Black-majority status.
        </p>
        <p>
          <strong>The same map moved three Democratic districts to the Republican column</strong> —
          {dc} {lostByD.map((f) => f.district).join(`, ${dc} `)} — and four Republican districts to the
          Democrats. The court then approved the plans, holding that drawing with “an eye toward
          securing partisan advantage” does “not alone violate Section 2” (
          {source('alpha-phi-alpha-order-2023') ? (
            <a href={source('alpha-phi-alpha-order-2023').url} target="_blank" rel="noreferrer">
              28 December 2023 order
            </a>
          ) : (
            '28 December 2023 order'
          )}
          ). Federal courts cannot hear the partisan claim at all (
          {source('rucho') ? (
            <a href={source('rucho').url} target="_blank" rel="noreferrer">
              Rucho v. Common Cause
            </a>
          ) : (
            'Rucho v. Common Cause'
          )}
          ). That is the gap this page exists to make visible.
        </p>
      </div>

      {year !== 2024 && (
        <p className="micro-note">
          This comparison is fixed to 2024, the only election fought on two different sets of
          lines. The year filter above does not change it.
        </p>
      )}
    </Section>
  );
}
