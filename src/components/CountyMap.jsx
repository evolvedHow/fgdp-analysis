import React, { useMemo, useState } from 'react';
import Section from './Section';
import FigureTools from './FigureTools';
import {
  featureBounds,
  fmtInt,
  fmtPct,
  geometryToPath,
  leanColor,
  makeProjection,
  PARTY,
} from '../lib/data';

/**
 * Section 3 — the county map. Choropleth of the selected chamber's county-level
 * two-party share (or the multi-election composite when a chamber result is not
 * available), clickable to drill into precincts.
 */
export default function CountyMap({
  counties,
  countyVotes,
  chamberLabel,
  year,
  selectedCounty,
  onSelectCounty,
  onExplore,
}) {
  const [hover, setHover] = useState(null);
  const [pos, setPos] = useState({ x: 0, y: 0 });

  const W = 720;
  const H = 460;
  const feats = counties.features;

  const project = useMemo(() => makeProjection(W - 16, H - 16, featureBounds(feats)), [feats]);

  const shapes = useMemo(
    () =>
      feats.map((ft) => ({
        ft,
        d: geometryToPath(ft.geometry, (lon, lat) => {
          const [x, y] = project(lon, lat);
          return [x + 8, y + 8];
        }),
      })),
    [feats, project],
  );

  const rows = useMemo(() => {
    return feats
      .map((ft) => {
        const p = ft.properties;
        const vote = countyVotes ? countyVotes[p.name.toUpperCase()] : null;
        return {
          fips: p.fips,
          name: p.name,
          pctD: vote?.pctD ?? p.composite,
          votes: vote?.total ?? p.turnout,
          source: vote ? 'chamber' : 'composite',
          demVotes: vote?.d ?? p.demVotes,
        };
      })
      .filter((r) => r.pctD != null);
  }, [feats, countyVotes]);

  const byFips = useMemo(() => new Map(rows.map((r) => [r.fips, r])), [rows]);
  const ranked = useMemo(() => [...rows].sort((a, b) => b.pctD - a.pctD), [rows]);
  const usingChamber = rows.length > 0 && rows[0].source === 'chamber';
  const selected = selectedCounty ? byFips.get(selectedCounty) : null;

  return (
    <Section
      id="counties"
      step="05"
      kicker="Geography of the vote"
      title="Where the statewide margin is manufactured"
      lede={
        usingChamber
          ? `County-level two-party share for ${chamberLabel} races in ${year}. Blue counties are not automatically Democratic seats — district lines decide that — but they are where the votes are.`
          : 'County lean from the 2018–2024 composite (no chamber county result for this year).'
      }
      footer="Source: fdga/facts.parquet aggregated by county; fallback lean is the VTD composite. Click a county to open its precincts."
      aside={
        <>
          <h3 className="aside-title">Most Democratic</h3>
          <ul className="rank-list">
            {ranked.slice(0, 5).map((r) => (
              <li key={r.fips}>
                <button type="button" onClick={() => onSelectCounty(r.fips)}>
                  <span className="rank-name">{r.name}</span>
                  <span className="rank-bar">
                    <i style={{ width: `${Math.round(r.pctD * 100)}%`, background: PARTY.D }} />
                  </span>
                  <span className="rank-val">{fmtPct(r.pctD)}</span>
                </button>
              </li>
            ))}
          </ul>
          <h3 className="aside-title">Most Republican</h3>
          <ul className="rank-list">
            {ranked.slice(-5).reverse().map((r) => (
              <li key={r.fips}>
                <button type="button" onClick={() => onSelectCounty(r.fips)}>
                  <span className="rank-name">{r.name}</span>
                  <span className="rank-bar">
                    <i style={{ width: `${Math.round((1 - r.pctD) * 100)}%`, background: PARTY.R }} />
                  </span>
                  <span className="rank-val">{fmtPct(1 - r.pctD)}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      }
    >
      <figure className="chart map-figure">
        <FigureTools
          name={`county-map-${chamberLabel}-${year}`}
          title={usingChamber ? `${chamberLabel} ${year}: county result` : 'County lean, 2018-2024 composite'}
          subtitle="Democratic share of the two-party vote by county"
          background="#f7f6fb"
        />
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="county-map"
          role="img"
          aria-label={`County choropleth of Democratic two-party share, ${usingChamber ? `${chamberLabel} ${year}` : '2018-2024 composite'}`}
        >
          {shapes.map(({ ft, d }) => {
            const row = byFips.get(ft.properties.fips);
            const isSel = selectedCounty === ft.properties.fips;
            return (
              <path
                key={ft.properties.fips}
                d={d}
                fill={leanColor(row?.pctD ?? null)}
                className={`county ${isSel ? 'is-selected' : ''}`}
                tabIndex={0}
                role="button"
                aria-label={`${ft.properties.name} County: ${row ? fmtPct(row.pctD) : 'no data'} Democratic`}
                onMouseMove={(e) => {
                  setHover(row || null);
                  const box = e.currentTarget.ownerSVGElement.getBoundingClientRect();
                  setPos({ x: e.clientX - box.left, y: e.clientY - box.top });
                }}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(row || null)}
                onBlur={() => setHover(null)}
                onClick={() => onSelectCounty(ft.properties.fips)}
              />
            );
          })}
        </svg>

        {hover && (
          <div className="map-tooltip" style={{ left: pos.x + 12, top: pos.y + 12 }} role="status">
            <strong>{hover.name} County</strong>
            <span>D {fmtPct(hover.pctD)}</span>
            <span>{fmtInt(hover.votes)} votes</span>
            <em>{hover.source === 'chamber' ? `${chamberLabel} ${year}` : 'composite lean'}</em>
          </div>
        )}

        <div className="map-legend" aria-hidden="true">
          <span>R 75%</span>
          <i className="legend-ramp" />
          <span>75% D</span>
        </div>

        {selected && (
          <div className="map-selected">
            <strong>{selected.name} County</strong>
            <span>{fmtPct(selected.pctD)} Democratic · {fmtInt(selected.demVotes)} D votes</span>
            <button type="button" className="primary-button" onClick={onExplore}>
              Open {selected.name} precincts →
            </button>
          </div>
        )}
      </figure>
    </Section>
  );
}
