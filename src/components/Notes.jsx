import React from 'react';
import Section from './Section';

/**
 * Section 6 — method, sources and caveats. Kept in the story so the analysis
 * is auditable rather than a black box.
 */
export default function Notes({ meta }) {
  return (
    <Section
      id="notes"
      step="08"
      kicker="Method"
      title="What this story measures — and what it doesn't"
      lede="Every number is computed from the FDP common data model, exported once to a static JSON bundle. No live database is required to read the story."
      footer={`Bundle generated ${new Date(meta.generated).toLocaleString('en-US')} · ${meta.source}.`}
    >
      <div className="notes-grid">
        <article>
          <h3>Votes vs seats</h3>
          <p>
            Vote share is the two-party share of all votes cast in the chamber's races that
            year. Seat share counts winners. The gap is seat share minus vote share; a positive
            value is a Republican seat bonus, negative a Democratic one.
          </p>
        </article>
        <article>
          <h3>County map</h3>
          <p>
            Counties are shaded by the two-party Democratic share aggregated from county-level
            results for the selected chamber and year. Where a chamber result is unavailable,
            the map falls back to the 2018–2024 composite lean and says so.
          </p>
        </article>
        <article>
          <h3>Precinct lean</h3>
          <p>
            Precinct values are 2020 Census VTDs. The default signal is a six-election
            composite (2018 Governor, 2020 President, 2021 Senate runoff, 2022 Governor, 2022
            Senate, 2024 President); you can switch to any single election in the header.
            Precinct lean is district-independent, so it is a political baseline, not a
            district result.
          </p>
        </article>
        <article>
          <h3>Known limits</h3>
          <p>
            Uncontested seats distort vote share. Runoffs and primaries are excluded from the
            composite. Small VTDs can be filled with a county average where block-level
            coverage is thin. 2026 results are not included — they are not certified yet; the
            update path is <code>scripts/export_story_data.py</code> once they are.
          </p>
        </article>
      </div>
    </Section>
  );
}
