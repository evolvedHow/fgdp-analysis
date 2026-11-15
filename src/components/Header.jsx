import React from 'react';

/**
 * Sticky masthead: logo, story title, global filters and the flow-layout switch.
 *
 * Every filter here is global — changing it re-renders every section of the
 * story, which is what makes the continuous flow coherent.
 */
export default function Header({
  meta,
  chamber,
  onChamber,
  year,
  years,
  onYear,
  election,
  onElection,
  layout,
  onLayout,
  onReset,
  hasDrill,
  onExportPng,
  onExportPdf,
  exporting,
}) {
  const chambers = meta.chambers;
  const elections = meta.elections;

  return (
    <header className="masthead">
      <div className="masthead-row">
        <a className="brand" href="#top" aria-label="FDGA X-Ray home">
          <img src={`${import.meta.env.BASE_URL}fdga_icon.png`} alt="Fair Districts GA" width="44" height="42" />
          <span className="brand-text">
            <span className="brand-name">FDGA X-Ray</span>
            <span className="brand-sub">Georgia votes, seats &amp; precincts</span>
          </span>
        </a>

        <div className="masthead-actions">
          <div className="segmented" role="group" aria-label="Story flow direction">
            <button
              type="button"
              className={layout === 'vertical' ? 'is-active' : ''}
              aria-pressed={layout === 'vertical'}
              onClick={() => onLayout('vertical')}
            >
              Vertical flow
            </button>
            <button
              type="button"
              className={layout === 'horizontal' ? 'is-active' : ''}
              aria-pressed={layout === 'horizontal'}
              onClick={() => onLayout('horizontal')}
            >
              Horizontal flow
            </button>
          </div>

          <div className="export-group" role="group" aria-label="Export this story">
            <button
              type="button"
              className="ghost-button"
              onClick={onExportPng}
              disabled={exporting}
              title="Download the entire story as one PNG image"
            >
              {exporting ? 'Preparing…' : 'Report PNG'}
            </button>
            <button
              type="button"
              className="ghost-button"
              onClick={onExportPdf}
              title="Save the entire story as a PDF (opens your browser's print dialog)"
            >
              Report PDF
            </button>
          </div>

          {hasDrill && (
            <button type="button" className="ghost-button" onClick={onReset}>
              Reset drill-down
            </button>
          )}
        </div>
      </div>

      <div className="filterbar" role="group" aria-label="Global story filters">
        <label className="field">
          <span>Chamber</span>
          <select value={chamber} onChange={(e) => onChamber(e.target.value)}>
            {chambers.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Election year</span>
          <select value={year} onChange={(e) => onYear(Number(e.target.value))}>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Precinct lean signal</span>
          <select value={election} onChange={(e) => onElection(e.target.value)}>
            {elections.map((e) => (
              <option key={e.key} value={e.key}>
                {e.label}
              </option>
            ))}
          </select>
        </label>

        <p className="filter-note">
          Filters drive every panel below. Pick a county on the map, then a precinct dot,
          to walk from state → county → precinct.
        </p>
      </div>
    </header>
  );
}
