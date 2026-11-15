import React, { useMemo, useState } from 'react';
import Section from './Section';
import FigureTools from './FigureTools';
import { useSvgPanZoom } from '../lib/useSvgPanZoom';
import {
  featureBounds,
  fmtInt,
  fmtPct,
  fmtPts,
  geometryToPath,
  leanColor,
  makeProjection,
  PARTY,
  scaleLinear,
} from '../lib/data';

/**
 * Section 5 — the drill-down. State → county → precinct, with a dot map,
 * searchable tables and a precinct fact card.
 */
export default function PrecinctXray({
  precincts,
  counties,
  election,
  electionLabel,
  selectedCounty,
  onSelectCounty,
  selectedPrecinct,
  onSelectPrecinct,
  countyVotes,
  chamberLabel,
  year,
}) {
  const [query, setQuery] = useState('');
  const [hover, setHover] = useState(null);
  const [pos, setPos] = useState({ x: 0, y: 0 });

  const countyFeats = counties.features;
  const countyName = useMemo(
    () => (selectedCounty ? countyFeats.find((f) => f.properties.fips === selectedCounty)?.properties.name : null),
    [countyFeats, selectedCounty],
  );

  const scoped = useMemo(
    () => (selectedCounty ? precincts.filter((p) => p.countyFips === selectedCounty) : precincts),
    [precincts, selectedCounty],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return scoped;
    return scoped.filter((p) => `${p.name} ${p.county}`.toLowerCase().includes(q));
  }, [scoped, query]);

  const selected = useMemo(
    () => precincts.find((p) => p.geoid === selectedPrecinct) || null,
    [precincts, selectedPrecinct],
  );

  const countyStats = useMemo(() => {
    const pool = selectedCounty ? scoped : precincts;
    const turnout = pool.reduce((s, p) => s + (p.turnout || 0), 0);
    const lean = pool.reduce((s, p) => s + (p.pct[election] || 0) * (p.turnout || 0), 0);
    const vap = pool.reduce((s, p) => s + (p.vap || 0), 0);
    const bvap = pool.reduce((s, p) => s + (p.bvapBlack || 0), 0);
    return {
      turnout,
      vap,
      bvapShare: vap ? bvap / vap : null,
      lean: turnout ? lean / turnout : null,
      count: pool.length,
    };
  }, [scoped, precincts, selectedCounty, election]);

  const voteShare = useMemo(() => {
    if (!selectedCounty || !countyVotes) return null;
    return countyVotes[countyName?.toUpperCase()] || null;
  }, [countyVotes, countyName, selectedCounty]);

  const W = 700;
  const H = 430;

  // Pan/zoom for precinct dot map
  const { viewBox: precincViewBox, svgRef: precincRef } = useSvgPanZoom(W, H, 1, 10);

  const bounds = useMemo(() => {
    if (!selectedCounty) return featureBounds(countyFeats);
    const pool = scoped;
    if (!pool.length) return featureBounds(countyFeats);
    const lon = pool.map((p) => p.lon);
    const lat = pool.map((p) => p.lat);
    const pad = 0.03;
    return [Math.min(...lon) - pad, Math.min(...lat) - pad, Math.max(...lon) + pad, Math.max(...lat) + pad];
  }, [scoped, selectedCounty, countyFeats]);

  const project = useMemo(() => makeProjection(W - 30, H - 30, bounds), [bounds]);

  const countyPaths = useMemo(
    () =>
      countyFeats.map((ft) => ({
        fips: ft.properties.fips,
        name: ft.properties.name,
        d: geometryToPath(ft.geometry, (lon, lat) => {
          const [x, y] = project(lon, lat);
          return [x + 15, y + 15];
        }),
      })),
    [countyFeats, project],
  );

  const maxTurnout = useMemo(
    () => Math.max(100, ...scoped.map((p) => p.turnout || 0)),
    [scoped],
  );
  const rScale = scaleLinear([0, maxTurnout], [1.6, 8.5]);

  const points = useMemo(
    () =>
      filtered.map((p) => {
        const [x, y] = project(p.lon, p.lat);
        return { p, x: x + 15, y: y + 15 };
      }),
    [filtered, project],
  );

  const topList = useMemo(() => {
    // With a search active, rank every match (not just the biggest precincts),
    // otherwise a small precinct could never be found from the list.
    const pool = query.trim() ? filtered : scoped;
    const limit = query.trim() ? 20 : 12;
    return [...pool].sort((a, b) => (b.turnout || 0) - (a.turnout || 0)).slice(0, limit);
  }, [scoped, filtered, query]);

  return (
    <Section
      id="precincts"
      step="07"
      kicker="All the way down"
      title={countyName ? `Inside ${countyName} County` : 'Every precinct in Georgia'}
      lede={
        selectedCounty
          ? `The county's ${scoped.length} precincts, coloured by ${electionLabel} lean. Click any dot — or a row — for the precinct card.`
          : 'Start with any county below, or click a precinct dot directly. Each dot is one of the 2,698 2020 Census VTDs; size shows total votes cast.'
      }
      footer="Source: vtd/vtd_composite.parquet + boundaries/reference/precinct_scored.geojson (2020 Census VTDs). Precinct lean is the selected election's two-party Democratic share."
      aside={
        <>
          <div className="breadcrumb" aria-label="Drill-down location">
            <button type="button" onClick={() => onSelectCounty(null)} className={!selectedCounty ? 'is-current' : ''}>
              Georgia
            </button>
            {countyName && (
              <>
                <span aria-hidden="true">›</span>
                <button type="button" className="is-current" onClick={() => onSelectPrecinct(null)}>
                  {countyName}
                </button>
              </>
            )}
            {selected && (
              <>
                <span aria-hidden="true">›</span>
                <span className="crumb-current">{selected.name || selected.geoid}</span>
              </>
            )}
          </div>

          <label className="field">
            <span>County</span>
            <select
              value={selectedCounty || ''}
              onChange={(e) => {
                onSelectPrecinct(null);
                onSelectCounty(e.target.value || null);
              }}
            >
              <option value="">All Georgia ({precincts.length} precincts)</option>
              {[...countyFeats]
                .sort((a, b) => a.properties.name.localeCompare(b.properties.name))
                .map((f) => (
                  <option key={f.properties.fips} value={f.properties.fips}>
                    {f.properties.name}
                  </option>
                ))}
            </select>
          </label>

          <label className="field">
            <span>Find precinct</span>
            <input
              type="search"
              placeholder="e.g. Atlanta, 12B, Midway"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>

          <dl className="mini-stats">
            <div>
              <dt>Precincts</dt>
              <dd>{fmtInt(scoped.length)}</dd>
            </div>
            <div>
              <dt>Votes ({electionLabel})</dt>
              <dd>{fmtInt(countyStats.turnout)}</dd>
            </div>
            <div>
              <dt>Weighted D share</dt>
              <dd>{fmtPct(countyStats.lean)}</dd>
            </div>
            <div>
              <dt>Black share of VAP</dt>
              <dd>{fmtPct(countyStats.bvapShare)}</dd>
            </div>
          </dl>

          {voteShare && (
            <p className="micro-note">
              {countyName} County voted {fmtPct(voteShare.pctD)} Democratic in {chamberLabel} {year} races.
            </p>
          )}
        </>
      }
    >
      <figure className="chart map-figure precinct-figure">
        <FigureTools
          name={`precincts-${countyName || 'georgia'}-${election}`}
          title={countyName ? `${countyName} County precincts` : 'Every precinct in Georgia'}
          subtitle={`${electionLabel} two-party share; dot size shows votes cast`}
          background="#f7f6fb"
        />
        <svg
          viewBox={precincViewBox}
          ref={precincRef}
          style={{ cursor: 'grab', userSelect: 'none' }}
          role="img"
          aria-label={
            selectedCounty
              ? `Precinct dot map for ${countyName} County. Use mouse wheel to zoom, drag to pan.`
              : 'Statewide precinct dot map of Georgia. Use mouse wheel to zoom, drag to pan.'
          }
        >
          {countyPaths.map((c) => (
            <path
              key={c.fips}
              d={c.d}
              className={`county-outline ${selectedCounty === c.fips ? 'is-strong' : ''}`}
            />
          ))}
          {points.map(({ p, x, y }) => (
            <circle
              key={p.geoid}
              cx={x}
              cy={y}
              r={rScale(p.turnout || 0)}
              fill={leanColor(p.pct[election])}
              className={`precinct-dot ${selectedPrecinct === p.geoid ? 'is-selected' : ''}`}
              tabIndex={0}
              role="button"
              aria-label={`${p.name}, ${p.county}: ${fmtPct(p.pct[election])} Democratic, ${fmtInt(p.turnout)} votes`}
              onMouseMove={(e) => {
                setHover(p);
                const box = e.currentTarget.ownerSVGElement.getBoundingClientRect();
                setPos({ x: e.clientX - box.left, y: e.clientY - box.top });
              }}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(p)}
              onBlur={() => setHover(null)}
              onClick={() => onSelectPrecinct(p.geoid)}
            />
          ))}
        </svg>

        {hover && (
          <div className="map-tooltip" style={{ left: pos.x + 12, top: pos.y + 12 }} role="status">
            <strong>{hover.name || hover.geoid}</strong>
            <span>{hover.county} County</span>
            <span>D {fmtPct(hover.pct[election])}</span>
            <span>{fmtInt(hover.turnout)} votes</span>
          </div>
        )}

        <div className="map-legend" aria-hidden="true">
          <span>R 75%</span>
          <i className="legend-ramp" />
          <span>75% D</span>
        </div>
      </figure>

      <div className="precinct-grid">
        <div>
          <h3 className="aside-title">
            {query ? `${filtered.length} matches` : 'Largest precincts'}
          </h3>
          <ul className="precinct-list">
            {topList
              .filter((p) => filtered.some((f) => f.geoid === p.geoid))
              .map((p) => (
                <li key={p.geoid}>
                  <button
                    type="button"
                    className={selectedPrecinct === p.geoid ? 'is-selected' : ''}
                    onClick={() => onSelectPrecinct(p.geoid)}
                  >
                    <span className="p-name">{p.name || p.geoid}</span>
                    <span className="p-county">{p.county}</span>
                    <span className="p-bar">
                      <i style={{ width: `${Math.round((p.pct[election] || 0) * 100)}%`, background: PARTY.D }} />
                    </span>
                    <span className="p-val">{fmtPct(p.pct[election])}</span>
                  </button>
                </li>
              ))}
            {!topList.some((p) => filtered.some((f) => f.geoid === p.geoid)) && (
              <li className="empty">No precinct matches “{query}”.</li>
            )}
          </ul>
        </div>

        <div className="precinct-card">
          {selected ? (
            <>
              <p className="kicker">{selected.county} County precinct</p>
              <h3>{selected.name || selected.geoid}</h3>
              <p className="geoid">GEOID {selected.geoid}</p>

              <div className="vote-split">
                <div
                  className="vote-half"
                  style={{ background: PARTY.D, width: `${(selected.pct[election] || 0) * 100}%` }}
                >
                  {(selected.pct[election] || 0) > 0.15 ? fmtPct(selected.pct[election]) : ''}
                </div>
                <div
                  className="vote-half"
                  style={{ background: PARTY.R, width: `${(1 - (selected.pct[election] || 0)) * 100}%` }}
                >
                  {(1 - (selected.pct[election] || 0)) > 0.15 ? fmtPct(1 - (selected.pct[election] || 0)) : ''}
                </div>
              </div>
              <p className="micro-note">{electionLabel} two-party share</p>

              <dl className="mini-stats">
                <div>
                  <dt>Votes cast</dt>
                  <dd>{fmtInt(selected.turnout)}</dd>
                </div>
                <div>
                  <dt>Democratic votes</dt>
                  <dd>{fmtInt(selected.demVotes)}</dd>
                </div>
                <div>
                  <dt>Voting-age pop.</dt>
                  <dd>{fmtInt(selected.vap)}</dd>
                </div>
                <div>
                  <dt>Black VAP</dt>
                  <dd>
                    {fmtInt(selected.bvapBlack)}
                    <em> ({fmtPct(selected.vap ? selected.bvapBlack / selected.vap : null)})</em>
                  </dd>
                </div>
                <div>
                  <dt>Black coalition VAP</dt>
                  <dd>
                    {fmtInt(selected.bvapCoalition)}
                    <em> ({fmtPct(selected.vap ? selected.bvapCoalition / selected.vap : null)})</em>
                  </dd>
                </div>
                <div>
                  <dt>Vs. {selectedCounty ? 'county' : 'state'} lean</dt>
                  <dd>
                    {fmtPts((selected.pct[election] || 0) - (countyStats.lean || 0))}
                  </dd>
                </div>
              </dl>

              <div className="card-actions">
                {!selectedCounty && (
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => onSelectCounty(selected.countyFips)}
                  >
                    Zoom to {selected.county} County
                  </button>
                )}
                <button type="button" className="ghost-button" onClick={() => onSelectPrecinct(null)}>
                  Clear precinct
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="kicker">Precinct card</p>
              <h3>Pick a precinct</h3>
              <p className="lede small">
                Hover the dots for a quick read, click one to pin it here. The card shows the
                two-party share, turnout, voting-age population, Black VAP share and how far the
                precinct sits from its county's weighted lean.
              </p>
            </>
          )}
        </div>
      </div>
    </Section>
  );
}
