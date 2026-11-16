import React, { useMemo } from 'react';
import { fmtPts } from '../lib/data';

/**
 * County heatmap grid showing partisan margin (D% - R%) for each county.
 * Non-partisan visualization: neutral scale from blue (D) through white (even) to red (R).
 */
export default function CountyHeatmap({ counties, countyVotes, chamberLabel, year }) {
  const W = 720;
  const COLS = 12;
  
  const rows = useMemo(() => {
    return counties.features
      .map((ft) => {
        const p = ft.properties;
        const vote = countyVotes ? countyVotes[p.name.toUpperCase()] : null;
        const pctD = vote?.pctD ?? p.composite;
        return {
          fips: p.fips,
          name: p.name,
          pctD,
          margin: pctD != null ? (pctD - (1 - pctD)) * 100 : null,
        };
      })
      .filter((r) => r.margin != null)
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [counties.features, countyVotes]);

  const minMargin = useMemo(() => Math.min(...rows.map((r) => r.margin)), [rows]);
  const maxMargin = useMemo(() => Math.max(...rows.map((r) => r.margin)), [rows]);
  const absMax = useMemo(() => Math.max(Math.abs(minMargin), Math.abs(maxMargin)), [minMargin, maxMargin]);

  const marginToColor = (margin) => {
    if (margin === null || margin === undefined) return '#f5f3fa';
    const normalized = margin / absMax;
    const hue = normalized < 0 ? 0 : 240;
    const sat = Math.abs(normalized) * 100;
    const lightness = 100 - Math.abs(normalized) * 35;
    return `hsl(${hue}, ${sat}%, ${lightness}%)`;
  };

  const cellWidth = W / COLS;
  const cellHeight = 36;
  
  return (
    <figure className="chart">
      <figcaption>Partisan margin by county: Democratic vs Republican (% difference)</figcaption>
      <div className="heatmap-grid" style={{ width: W, fontSize: '12px' }}>
        <table className="heatmap-table">
          <tbody>
            {Array.from({ length: Math.ceil(rows.length / COLS) }).map((_, rowIdx) => (
              <tr key={rowIdx}>
                {rows.slice(rowIdx * COLS, (rowIdx + 1) * COLS).map((row) => (
                  <td
                    key={row.fips}
                    style={{
                      background: marginToColor(row.margin),
                      border: '1px solid #e2dfeb',
                      padding: '8px',
                      textAlign: 'center',
                      minWidth: cellWidth,
                      position: 'relative',
                    }}
                    title={`${row.name}: ${fmtPts(row.margin)}`}
                  >
                    <div
                      style={{
                        fontWeight: 600,
                        fontSize: '11px',
                        color: Math.abs(row.margin) > absMax * 0.5 ? '#fff' : '#1c1a2b',
                      }}
                    >
                      {row.name.split(' County')[0]}
                    </div>
                    <div
                      style={{
                        fontSize: '10px',
                        fontWeight: 700,
                        marginTop: '2px',
                        color: Math.abs(row.margin) > absMax * 0.5 ? '#fff' : '#4c4863',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {fmtPts(row.margin)}
                    </div>
                  </td>
                ))}
                {/* Fill empty cells */}
                {rowIdx === Math.ceil(rows.length / COLS) - 1 &&
                  Array.from({ length: COLS - (rows.length % COLS) }).map((_, i) => (
                    <td
                      key={`empty-${i}`}
                      style={{
                        background: '#f5f3fa',
                        border: '1px solid #f0eefc',
                        minWidth: cellWidth,
                      }}
                    />
                  ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="heatmap-legend" style={{ marginTop: '12px', fontSize: '11px', color: '#726d89' }}>
        <span>
          <strong>Partisan margin scale:</strong> Blue = more Democratic votes, Red = more Republican votes, White = tied
        </span>
        <div style={{ marginTop: '6px', display: 'flex', gap: '2px', alignItems: 'center' }}>
          <span style={{ width: '20px', height: '16px', background: 'hsl(0, 100%, 65%)', border: '1px solid #e2dfeb' }} />
          <span>Republican margin</span>
          <span style={{ marginLeft: '12px', width: '20px', height: '16px', background: '#fff', border: '1px solid #e2dfeb' }} />
          <span>Even split</span>
          <span style={{ marginLeft: '12px', width: '20px', height: '16px', background: 'hsl(240, 100%, 65%)', border: '1px solid #e2dfeb' }} />
          <span>Democratic margin</span>
        </div>
      </div>
    </figure>
  );
}
