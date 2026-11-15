import React, { useMemo } from 'react';
import Section from './Section';
import FigureTools from './FigureTools';
import { fmtPct } from '../lib/data';

/**
 * Section 02a — County-level vote swing scatter plot.
 *
 * For each county, plots an arrow from left (D gain) to right (R gain).
 * Arrow length is proportional to the shift in percentage points.
 * Sorted top-to-bottom by shift magnitude.
 *
 * Future enhancement: full county map background with geographic positioning.
 */
export default function CountySwing({
  countyGeoJSON,
  countyVotes,
  electionKey,
  year,
  chamberLabel,
}) {
  // Allowed pairs: { prevYear: currYear }
  const COMPARISONS = {
    president: { 2020: 2024, 2016: 2020, 2012: 2016, 2008: 2012, 2004: 2008, 2000: 2004 },
    governor: { 2018: 2022, 2014: 2018, 2010: 2014, 2006: 2010, 2002: 2006 },
    us_house: { 2020: 2024, 2016: 2020, 2012: 2016, 2008: 2012, 2004: 2008, 2000: 2004 },
    us_senate: { 2020: 2024, 2016: 2020, 2012: 2016, 2008: 2012, 2004: 2008, 2000: 2004 },
    state_house: { 2020: 2024, 2016: 2020, 2012: 2016, 2008: 2012, 2004: 2008, 2000: 2004 },
    state_senate: { 2020: 2024, 2016: 2020, 2012: 2016, 2008: 2012, 2004: 2008, 2000: 2004 },
  };

  const comparison = useMemo(() => {
    const comp = COMPARISONS[electionKey];
    if (!comp) return null;
    // Find the prev year whose value is the current year
    const prevYearStr = Object.keys(comp).find((prevY) => Number(comp[prevY]) === Number(year));
    if (!prevYearStr) return null;
    return { prev: Number(prevYearStr), curr: Number(year) };
  }, [electionKey, year]);

  const arrows = useMemo(() => {
    if (!comparison || !countyVotes[electionKey]) return [];

    const votes = countyVotes[electionKey];
    const prevVotes = votes[String(comparison.prev)];
    const currVotes = votes[String(comparison.curr)];
    if (!prevVotes || !currVotes) return [];

    const result = [];
    for (const countyName of Object.keys(currVotes)) {
      const prev = prevVotes[countyName];
      const curr = currVotes[countyName];
      if (!prev || !curr) continue;

      const shift = curr.pctD - prev.pctD; // positive = D gain
      result.push({
        county: countyName,
        shift,
        prevPct: prev.pctD,
        currPct: curr.pctD,
      });
    }

    // Sort by absolute shift descending (most dramatic first)
    result.sort((a, b) => Math.abs(b.shift) - Math.abs(a.shift));
    return result;
  }, [comparison, countyVotes, electionKey]);

  const maxShift = useMemo(() => {
    if (arrows.length === 0) return 0.01; // avoid division by zero
    return Math.max(...arrows.map((a) => Math.abs(a.shift)));
  }, [arrows]);

  if (!comparison) {
    return (
      <Section
        id="county-swing"
        step="02a"
        kicker="County swings"
        title="No prior election for comparison"
      >
        <p className="empty">
          Choose an election year with a previous cycle available to see county-level vote shifts.
        </p>
      </Section>
    );
  }

  if (arrows.length === 0) {
    return (
      <Section
        id="county-swing"
        step="02a"
        kicker="County swings"
        title="Data not available for this comparison"
      >
        <p className="empty">Swing data unavailable for {comparison.prev} → {comparison.curr}.</p>
      </Section>
    );
  }

  // SVG layout: 159 counties as rows, each with a horizontal arrow
  const W = 800;
  const rowH = 20;
  const H = arrows.length * rowH + 60;
  const M = { top: 40, right: 20, bottom: 40, left: 140 };
  const plotW = W - M.left - M.right;

  // Arrow length scale: map maxShift to ~300 px
  const arrowScale = plotW / (2 * maxShift); // center at 0, extend left/right

  return (
    <Section
      id="county-swing"
      step="02a"
      kicker="County swings"
      title={`County-level vote shifts: ${comparison.prev} → ${comparison.curr}`}
      lede={`Each arrow shows how a county's Democratic share changed from ${comparison.prev} to ${comparison.curr}. Arrows point left (blue) for Democratic gains, right (red) for Republican gains. Length is the shift in percentage points; sorted by magnitude.`}
    >
      <figure className="chart">
        <FigureTools
          name={`county-swing-${electionKey}-${comparison.prev}-${comparison.curr}`}
          title="County vote shifts"
          subtitle={`Democratic share change by county, ${comparison.prev} → ${comparison.curr}`}
        />
        <figcaption>Vote shift from {comparison.prev} to {comparison.curr}, sorted by magnitude</figcaption>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Scatter plot of county vote shifts from ${comparison.prev} to ${comparison.curr}`}
        >
          {/* Center line (zero shift) */}
          <line
            x1={M.left + plotW / 2}
            x2={M.left + plotW / 2}
            y1={M.top}
            y2={H - M.bottom}
            className="zero-line"
            strokeWidth="1"
          />

          {/* Arrows */}
          {arrows.map((arrow, i) => {
            const y0 = M.top + i * rowH + rowH / 2;
            const xCenter = M.left + plotW / 2;
            const arrowLen = Math.abs(arrow.shift) * arrowScale;
            const isLeft = arrow.shift > 0; // D gain = left
            const color = isLeft ? '#1f4bae' : '#db1623';

            const x0 = xCenter;
            const x1 = isLeft ? xCenter - arrowLen : xCenter + arrowLen;

            // Arrowhead size
            const headSize = Math.max(3, arrowLen * 0.1);

            return (
              <g key={arrow.county}>
                {/* Shaft */}
                <line x1={x0} y1={y0} x2={x1} y2={y0} stroke={color} strokeWidth="1.2" />

                {/* Arrowhead */}
                {isLeft ? (
                  // Points left
                  <polygon
                    points={`${x1},${y0} ${x1 + headSize},${y0 - headSize} ${x1 + headSize},${y0 + headSize}`}
                    fill={color}
                  />
                ) : (
                  // Points right
                  <polygon
                    points={`${x1},${y0} ${x1 - headSize},${y0 - headSize} ${x1 - headSize},${y0 + headSize}`}
                    fill={color}
                  />
                )}

                {/* County label */}
                <text
                  x={M.left - 8}
                  y={y0 + 4}
                  textAnchor="end"
                  className="county-label"
                  fontSize="11"
                  fill="#4c4863"
                >
                  {arrow.county}
                </text>

                {/* Shift value */}
                <text
                  x={x1 + (isLeft ? -8 : 8)}
                  y={y0 - 8}
                  textAnchor={isLeft ? 'end' : 'start'}
                  className="shift-value"
                  fontSize="10"
                  fill="#726d89"
                >
                  {(arrow.shift > 0 ? '+' : '') + arrow.shift.toFixed(1)}%
                </text>
              </g>
            );
          })}

          {/* Legend */}
          <g transform={`translate(${M.left}, ${H - M.bottom + 8})`}>
            <text x="0" y="0" className="axis-label" textAnchor="start" fontSize="11">
              ← D gain
            </text>
            <line x1="50" y1="-2" x2="80" y2="-2" stroke="#1f4bae" strokeWidth="1.2" />
            <polygon points="82,-4 88,0 82,4" fill="#1f4bae" />

            <text x="100" y="0" className="axis-label" textAnchor="start" fontSize="11">
              R gain →
            </text>
            <line x1="170" y1="-2" x2="200" y2="-2" stroke="#db1623" strokeWidth="1.2" />
            <polygon points="200,-4 206,0 200,4" fill="#db1623" />
          </g>
        </svg>
      </figure>

      <div className="story-footer">
        <strong>{comparison.prev} baseline:</strong> composite statewide (see "The swing") ·
        <strong>{comparison.curr}:</strong> same measure. Top shifts shown first; full sorted list
        by county above.
      </div>
    </Section>
  );
}
