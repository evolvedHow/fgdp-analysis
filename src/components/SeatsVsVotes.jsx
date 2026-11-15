import React, { useMemo } from 'react';
import Section from './Section';
import FigureTools from './FigureTools';
import { fmtInt, fmtPct, fmtPts, PARTY } from '../lib/data';

/**
 * Section 2 — votes versus seats for the selected chamber and year, with the
 * gap tracked across every cycle.
 */
export default function SeatsVsVotes({ rows, year, chamberLabel }) {
  const current = rows.find((r) => r.year === year) || rows[rows.length - 1];

  const trend = useMemo(
    () => [...rows].sort((a, b) => a.year - b.year),
    [rows],
  );

  const W = 640;
  const H = 180;
  const M = { top: 16, right: 10, bottom: 26, left: 10 };
  const barH = 26;
  const zero = H / 2 + 4;
  const maxGap = Math.max(0.12, ...trend.map((r) => Math.abs(r.gapR || 0)));
  const slot = (W - M.left - M.right) / trend.length;

  if (!current) return null;

  const gap = current.pctSeatsR - current.pctVotesR;
  const dVotes = current.pctVotesD ?? 0;
  const rVotes = current.pctVotesR ?? 0;
  const dSeats = current.pctSeatsD ?? 0;
  const rSeats = current.pctSeatsR ?? 0;

  const declared = current.racesContested;
  const uncontested = current.racesUncontested;

  return (
    <Section
      id="seats"
      step="02"
      kicker={`${chamberLabel} · ${year}`}
      title={
        Math.abs(gap) < 0.01
          ? 'Seats track votes almost exactly'
          : gap > 0
            ? 'A Republican seat bonus, district by district'
            : 'A Democratic seat bonus, district by district'
      }
      lede={`${fmtInt(current.votesD)} Democratic and ${fmtInt(current.votesR)} Republican votes were cast across ${fmtInt(current.racesTotal)} seats. Those votes became ${current.seatsD ?? '—'} Democratic and ${current.seatsR ?? '—'} Republican seats.`}
      footer={`Source: fdga/chamber_year.parquet. Gap = seat share minus two-party vote share (positive = Republican bonus). ${uncontested} of ${current.racesTotal} seats were uncontested.`}
    >
      <div className="split-bars">
        <div className="split-row">
          <span className="split-label">Votes</span>
          <div className="split-track" role="img" aria-label={`Votes: ${fmtPct(dVotes)} Democratic, ${fmtPct(rVotes)} Republican`}>
            <div className="split-part" style={{ width: `${dVotes * 100}%`, background: PARTY.D }}>
              {dVotes > 0.08 ? fmtPct(dVotes) : ''}
            </div>
            <div className="split-part" style={{ width: `${rVotes * 100}%`, background: PARTY.R }}>
              {rVotes > 0.08 ? fmtPct(rVotes) : ''}
            </div>
          </div>
        </div>
        <div className="split-row">
          <span className="split-label">Seats</span>
          <div className="split-track" role="img" aria-label={`Seats: ${fmtPct(dSeats)} Democratic, ${fmtPct(rSeats)} Republican`}>
            <div className="split-part" style={{ width: `${dSeats * 100}%`, background: PARTY.D }}>
              {dSeats > 0.08 ? fmtPct(dSeats) : ''}
            </div>
            <div className="split-part" style={{ width: `${rSeats * 100}%`, background: PARTY.R }}>
              {rSeats > 0.08 ? fmtPct(rSeats) : ''}
            </div>
          </div>
        </div>
        <p className={`gap-callout ${Math.abs(gap) >= 0.02 ? 'is-flag' : ''}`}>
          Seat bonus for Republicans: <strong>{fmtPts(gap)}</strong>
          <span>
            {uncontested} uncontested seats · {current.racesCompetitive} races inside 5.5 points
          </span>
        </p>
      </div>

      <figure className="chart">
        <FigureTools
          name={`seats-vs-votes-${chamberLabel}-${year}`}
          title="Seats versus votes"
          subtitle={`${chamberLabel}, ${year}: seat share minus two-party vote share, every cycle`}
        />
        <figcaption>Seat-minus-votes gap, every cycle</figcaption>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Bar chart of the seat-minus-votes gap by election year">
          <line x1={M.left} x2={W - M.right} y1={zero} y2={zero} className="zero-line" />
          {trend.map((r, i) => {
            const g = r.gapR || 0;
            const h = (Math.abs(g) / maxGap) * (H / 2 - 28);
            const cx = M.left + slot * i + slot / 2;
            return (
              <g key={r.year}>
                <rect
                  x={cx - Math.min(16, slot * 0.32)}
                  y={g >= 0 ? zero - h : zero}
                  width={Math.min(32, slot * 0.64)}
                  height={Math.max(1, h)}
                  rx="2"
                  fill={g >= 0 ? PARTY.R : PARTY.D}
                  opacity={r.year === year ? 1 : 0.45}
                />
                <text x={cx} y={H - 8} textAnchor="middle" className={`axis-label ${r.year === year ? 'is-current' : ''}`}>
                  {String(r.year).slice(2)}
                </text>
                {r.year === year && (
                  <text
                    x={cx}
                    y={g >= 0 ? zero - h - 6 : zero + h + 14}
                    textAnchor="middle"
                    className="bar-value"
                  >
                    {fmtPts(g)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </figure>
    </Section>
  );
}
