import React, { useMemo } from 'react';
import Section from './Section';
import FigureTools from './FigureTools';
import { fmtInt, fmtPct, PARTY } from '../lib/data';

const BINS = [
  { label: '0–2', lo: 0, hi: 0.02 },
  { label: '2–5', lo: 0.02, hi: 0.05 },
  { label: '5–10', lo: 0.05, hi: 0.1 },
  { label: '10–20', lo: 0.1, hi: 0.2 },
  { label: '20–40', lo: 0.2, hi: 0.4 },
  { label: '40+', lo: 0.4, hi: 1.01 },
];

/**
 * Section 4 — the competitiveness cliff: how many seats were actually decided
 * by a close vote, and how many were uncontested.
 */
export default function Competitiveness({ contests, chamberLabel, year }) {
  const data = useMemo(() => contests || [], [contests]);

  const stats = useMemo(() => {
    const contested = data.filter((c) => !c.uncontested && c.marginShare != null);
    const bins = BINS.map((b) => ({
      ...b,
      count: contested.filter((c) => c.marginShare >= b.lo && c.marginShare < b.hi).length,
    }));
    const closest = [...contested].sort((a, b) => a.marginShare - b.marginShare).slice(0, 6);
    const uncontested = data.filter((c) => c.uncontested).length;
    const under10 = contested.filter((c) => c.marginShare < 0.1).length;
    const avg = contested.length
      ? contested.reduce((s, c) => s + c.marginShare, 0) / contested.length
      : null;
    return { bins, closest, uncontested, under10, contested: contested.length, avg };
  }, [data]);

  if (!data.length) {
    return (
      <Section id="competition" step="06" kicker="Competition" title="No contest data for this year">
        <p className="empty">Pick another year or chamber.</p>
      </Section>
    );
  }

  const W = 640;
  const H = 190;
  const M = { top: 18, right: 12, bottom: 34, left: 12 };
  const slot = (W - M.left - M.right) / (stats.bins.length + 1);
  const plotH = H - M.top - M.bottom;

  // The unopposed seats routinely outnumber any single margin bin (90 vs ~20
  // in the 2024 House). Drawn linearly that bar is several chart-heights tall
  // and bleeds into the previous card, so past the largest margin bin the
  // axis switches to a log scale, marked by a dashed break line.
  const binMax = Math.max(1, ...stats.bins.map((b) => b.count));
  const dataMax = Math.max(binMax, stats.uncontested);
  const logBreak = binMax;
  const useLog = dataMax > binMax * 1.15;
  const linearShare = 0.7;
  const barHeight = (n) => {
    if (!useLog) return (plotH * n) / dataMax;
    if (n <= logBreak) return plotH * linearShare * (n / logBreak);
    const t = Math.log(n / logBreak) / Math.log(dataMax / logBreak);
    return plotH * (linearShare + (1 - linearShare) * t);
  };
  const breakY = H - M.bottom - plotH * linearShare;


  return (
    <Section
      id="competition"
      step="06"
      kicker={`${chamberLabel} · ${year}`}
      title="Most seats are settled before election day"
      lede={`${stats.uncontested} of ${data.length} seats had no major-party opponent. Of the ${stats.contested} contested races, only ${stats.under10} finished inside 10 points; the average margin was ${stats.avg == null ? '—' : fmtPct(stats.avg)}.`}
      footer="Source: fdga/contests.parquet. Uncontested = single major-party candidate; margin = winner share minus runner-up share."
      aside={
        <>
          <h3 className="aside-title">Closest races</h3>
          <ol className="closest-list">
            {stats.closest.map((c) => (
              <li key={c.district}>
                <span className="closest-district">
                  {chamberLabel.includes('U.S.') ? 'CD' : 'District'} {String(Number(c.district))}
                </span>
                <span className="closest-winner">
                  <i style={{ background: PARTY[c.winnerParty] || PARTY.other }} />
                  {c.winnerName || c.winnerParty}
                </span>
                <span className="closest-margin">{fmtPct(c.marginShare)}</span>
              </li>
            ))}
          </ol>
        </>
      }
    >
      <figure className="chart">
        <FigureTools
          name={`competitiveness-${chamberLabel}-${year}`}
          title="How many seats were actually competitive"
          subtitle={`${chamberLabel}, ${year}: contested seats by victory margin, plus unopposed seats`}
        />
        <figcaption>
          Contested seats by victory margin (percentage points)
          {useLog ? ' · log scale above the dashed line' : ''}
        </figcaption>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Histogram of district victory margins">
          <defs>
            <pattern
              id="unopposed-hatch"
              width="6"
              height="6"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <rect width="6" height="6" fill="#c9c4da" />
              <line x1="0" y1="0" x2="0" y2="6" stroke="#8b87a3" strokeWidth="2" />
            </pattern>
          </defs>

          {useLog && (
            <g>
              <line
                x1={M.left}
                x2={W - M.right}
                y1={breakY}
                y2={breakY}
                className="scale-break"
              />
              <text x={W - M.right} y={breakY - 5} textAnchor="end" className="axis-label">
                log scale above
              </text>
            </g>
          )}

          {stats.bins.map((b, i) => {
            const h = Math.min(plotH, barHeight(b.count));
            const x = M.left + slot * i + slot * 0.15;
            const w = slot * 0.7;
            return (
              <g key={b.label}>
                <rect
                  x={x}
                  y={H - M.bottom - h}
                  width={w}
                  height={Math.max(1, h)}
                  rx="3"
                  fill={i <= 1 ? PARTY.D : '#b9b3cd'}
                />
                <text x={x + w / 2} y={H - M.bottom - h - 6} textAnchor="middle" className="bar-value">
                  {b.count}
                </text>
                <text x={x + w / 2} y={H - M.bottom + 16} textAnchor="middle" className="axis-label">
                  {b.label}
                </text>
              </g>
            );
          })}

          <g>
            <rect
              x={M.left + slot * stats.bins.length + slot * 0.15}
              y={H - M.bottom - Math.min(plotH, barHeight(stats.uncontested))}
              width={slot * 0.7}
              height={Math.max(1, Math.min(plotH, barHeight(stats.uncontested)))}
              rx="3"
              fill="url(#unopposed-hatch)"
              stroke="#8b87a3"
              strokeWidth="0.8"
            />
            <text
              x={M.left + slot * stats.bins.length + slot * 0.15 + (slot * 0.7) / 2}
              y={H - M.bottom - Math.min(plotH, barHeight(stats.uncontested)) - 6}
              textAnchor="middle"
              className="bar-value"
            >
              {stats.uncontested}
            </text>
            <text
              x={M.left + slot * stats.bins.length + slot * 0.15 + (slot * 0.7) / 2}
              y={H - M.bottom + 16}
              textAnchor="middle"
              className="axis-label"
            >
              unopposed
            </text>
          </g>
          <line x1={M.left} x2={W - M.right} y1={H - M.bottom} y2={H - M.bottom} className="axis-line" />
        </svg>
      </figure>
      <p className="micro-note">
        {fmtInt(stats.under10)} seats inside 10 points · {stats.contested} contested ·{' '}
        {fmtInt(stats.uncontested)} uncontested
        {useLog ? ' · bars above the dashed line are log-scaled' : ''}
      </p>
    </Section>
  );
}
