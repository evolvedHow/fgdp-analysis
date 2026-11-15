import React, { useMemo, useState } from 'react';
import Section from './Section';
import FigureTools from './FigureTools';
import { fmtCompact, fmtPct, fmtPts, scaleLinear, PARTY } from '../lib/data';

const SERIES = [
  { office: 'president', label: 'President', color: '#6440a4' },
  { office: 'governor', label: 'Governor', color: '#1f4bae' },
  { office: 'us_senate', label: 'U.S. Senate', color: '#7d3169' },
];

/**
 * Section 1 — the statewide swing line plus the headline numbers for the
 * selected chamber and year.
 */
export default function Statewide({ statewide, chamberRow, chamberLabel, year, onYear }) {
  const [hover, setHover] = useState(null);
  const W = 640;
  const H = 260;
  const M = { top: 18, right: 18, bottom: 28, left: 44 };

  const years = useMemo(
    () => Array.from(new Set(statewide.map((d) => d.year))).sort((a, b) => a - b),
    [statewide],
  );

  const x = scaleLinear([years[0], years[years.length - 1]], [M.left, W - M.right]);
  const y = scaleLinear([0.34, 0.62], [H - M.bottom, M.top]);

  const series = SERIES.map((s) => ({
    ...s,
    points: statewide
      .filter((d) => d.office === s.office && d.election_type === 'general')
      .sort((a, b) => a.year - b.year),
  }));

  const selected = chamberRow;
  const gap = selected ? selected.pctSeatsR - selected.pctVotesR : null;
  const favour = gap == null ? null : gap > 0 ? 'Republicans' : 'Democrats';

  return (
    <Section
      id="swing"
      step="01"
      kicker="Statewide baseline"
      title="Georgia is a coin-flip that keeps producing landslides"
      lede="Statewide contests have landed within a few points of 50–50 since 2018. The chamber you picked is decided district by district — and those districts do not always follow the statewide result."
      footer="Source: fdga/statewide.parquet (two-party vote share, general elections)."
    >
      <div className="kpi-row">
        <div className="kpi">
          <span className="kpi-label">{year} Democratic votes</span>
          <strong>{selected ? fmtCompact(selected.votesD) : '—'}</strong>
          <span className="kpi-sub">{selected ? fmtPct(selected.pctVotesD) : '—'} of two-party</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">{year} Republican votes</span>
          <strong>{selected ? fmtCompact(selected.votesR) : '—'}</strong>
          <span className="kpi-sub">{selected ? fmtPct(selected.pctVotesR) : '—'} of two-party</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">{chamberLabel} seats</span>
          <strong>
            {selected ? `${selected.seatsD ?? '—'} D · ${selected.seatsR ?? '—'} R` : '—'}
          </strong>
          <span className="kpi-sub">
            {selected
              ? `${fmtPct(selected.pctSeatsD)} / ${fmtPct(selected.pctSeatsR)} of seats`
              : '—'}
          </span>
        </div>
        <div className={`kpi ${gap != null && Math.abs(gap) >= 0.02 ? 'is-flag' : ''}`}>
          <span className="kpi-label">Seats-minus-votes gap</span>
          <strong>{gap == null ? '—' : fmtPts(gap)}</strong>
          <span className="kpi-sub">
            {gap == null
              ? '—'
              : Math.abs(gap) < 0.01
                ? 'Seats track votes'
                : `${favour} win a larger seat share than vote share`}
          </span>
        </div>
      </div>

      <figure className="chart">
        <FigureTools
          name={`statewide-swing-${year}`}
          title="Democratic share of the statewide vote"
          subtitle="Georgia general elections, 2000-2024; the highlighted year is selected above"
        />
        <figcaption>Democratic share of the two-party vote, statewide contests</figcaption>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Line chart of Democratic two-party vote share in Georgia statewide elections, 2000 to 2024">
          {[0.4, 0.45, 0.5, 0.55, 0.6].map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} className="gridline" />
              <text x={M.left - 8} y={y(t) + 4} textAnchor="end" className="axis-label">
                {(t * 100).toFixed(0)}%
              </text>
            </g>
          ))}

          <line x1={M.left} x2={W - M.right} y1={y(0.5)} y2={y(0.5)} className="zero-line" />

          {years.map((yr) => (
            <text key={yr} x={x(yr)} y={H - 8} textAnchor="middle" className="axis-label">
              {String(yr).slice(2)}
            </text>
          ))}

          <line x1={x(year)} x2={x(year)} y1={M.top} y2={H - M.bottom} className="year-rule" />
          <text x={x(year)} y={M.top - 5} textAnchor="middle" className="year-flag">
            {year}
          </text>

          {series.map((s) => (
            <g key={s.office}>
              <path
                d={s.points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.year)},${y(p.pctD)}`).join('')}
                fill="none"
                stroke={s.color}
                strokeWidth="2.2"
                strokeLinejoin="round"
              />
              {s.points.map((p) => (
                <circle
                  key={p.year}
                  cx={x(p.year)}
                  cy={y(p.pctD)}
                  r={p.year === year ? 5 : 3.2}
                  fill={p.year === year ? s.color : '#fff'}
                  stroke={s.color}
                  strokeWidth="1.8"
                  tabIndex={0}
                  role="button"
                  aria-label={`${s.label} ${p.year}: ${fmtPct(p.pctD)} Democratic`}
                  onMouseEnter={() => setHover({ ...p, label: s.label, color: s.color })}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover({ ...p, label: s.label, color: s.color })}
                  onBlur={() => setHover(null)}
                  onClick={() => onYear(p.year)}
                  className="dot"
                />
              ))}
            </g>
          ))}
        </svg>
        <div className="legend">
          {series.map((s) => (
            <span key={s.office} className="legend-item">
              <i style={{ background: s.color }} /> {s.label}
            </span>
          ))}
          <span className="legend-hint">Click a point to jump to that year</span>
        </div>
        {hover && (
          <div className="chart-tooltip" role="status">
            <strong>{hover.label}</strong> {hover.year}
            <span>D {fmtPct(hover.pctD)}</span>
            <span>R {fmtPct(hover.pctR)}</span>
          </div>
        )}
      </figure>
    </Section>
  );
}
