import React, { useMemo } from 'react';
import Section from './Section';
import FigureTools from './FigureTools';
import { fmtInt } from '../lib/data';

/**
 * Letter-grade fills for FDGA's scorecard grades: one purple ramp,
 * darkest = strongest. The letters are the scorecard's own.
 */
const GRADE_FILL = {
  A: '#4c2b86',
  B: '#6440a4',
  C: '#8b6fc4',
  D: '#a05a7e',
  F: '#7d3169',
};

/** Human ordinal for a percentile rank, e.g. 0.234 -> "23rd". */
function ordinal(pctRank) {
  const n = Math.max(0, Math.min(100, Math.round((pctRank || 0) * 100)));
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  if (n % 10 === 1) return `${n}st`;
  if (n % 10 === 2) return `${n}nd`;
  if (n % 10 === 3) return `${n}rd`;
  return `${n}th`;
}

/** Format a metric value according to its unit (seats, share, points). */
function fmtValue(metric, v) {
  if (v == null) return '—';
  if (metric.unit === 'seats') return `${Math.round(v)} seat${Math.round(v) === 1 ? '' : 's'}`;
  if (metric.unit === 'share') return `${(v * 100).toFixed(1)}%`;
  return `${(v * 100).toFixed(1)} pt`;
}

/** A metric sits outside the neutral range when it clears the 5th/95th band. */
const isOutside = (m) =>
  m.enacted != null &&
  ((m.p5 != null && m.enacted < m.p5 - 1e-9) || (m.p95 != null && m.enacted > m.p95 + 1e-9));

/** Group boundaries, used to separate competition / symmetry / safe seats. */
const GROUP_LABEL = {
  competition: 'Competition',
  proportionality: 'Seat–vote proportionality',
  symmetry: 'Symmetry',
  safe: 'Safe seats',
};

/**
 * Section 4 — the neutral-ensemble benchmark.
 *
 * FDGA scored each enacted plan against tens of thousands of ReCom maps drawn
 * without party, race, or past-result data. Each percentile says where the
 * enacted plan sits within that neutral range. The section deliberately reports
 * both parties' safe-seat counts and frames every outlier as "outside what a
 * neutral process produces", never as evidence that one party was targeted.
 */
export default function Benchmark({ ensemble, chamberLabel }) {
  const metrics = useMemo(() => ensemble?.metrics || [], [ensemble]);
  const run = ensemble?.run;

  const comp = useMemo(
    () => metrics.find((m) => m.key === 'comp_seats_10pt') || null,
    [metrics],
  );
  const outside = useMemo(() => metrics.filter(isOutside), [metrics]);
  const demSafe = metrics.find((m) => m.key === 'dem_safe_seats');
  const repSafe = metrics.find((m) => m.key === 'rep_safe_seats');

  if (!ensemble || !metrics.length) {
    return (
      <Section id="benchmark" step="04" kicker="The benchmark" title="No benchmark data for this chamber">
        <p className="empty">The neutral-ensemble scorecard is only available for the House, Senate and Congress.</p>
      </Section>
    );
  }

  // ------------------------------------------------------------ percentile strip
  const W = 700;
  const rowH = 30;
  const M = { top: 34, right: 56, bottom: 38, left: 156 };
  const plotW = W - M.left - M.right;
  const H = M.top + metrics.length * rowH + M.bottom;
  const x = (pct) => M.left + (Math.max(0, Math.min(100, pct)) / 100) * plotW;
  const baseline = H - M.bottom;

  // ------------------------------------------------------- competitiveness histogram
  const HIST_W = 640;
  const HIST_H = 216;
  const HM = { top: 34, right: 22, bottom: 38, left: 52 };
  const histW = HIST_W - HM.left - HM.right;
  const histH = HIST_H - HM.top - HM.bottom;
  const hist = comp?.hist;
  const edges = hist?.edges || [];
  const counts = hist?.counts || [];
  const h0 = edges[0] ?? 0;
  const h1 = edges[edges.length - 1] ?? 1;
  const hx = (v) => HM.left + ((v - h0) / (h1 - h0 || 1)) * histW;
  const peak = Math.max(0.0001, ...counts);
  const yMax = peak * 1.18;
  const hy = (c) => baselineH() - (c / yMax) * histH;
  function baselineH() {
    return HM.top + histH;
  }
  const tickStep = h1 - h0 <= 9 ? 1 : 2;

  const title =
    outside.length === 0
      ? 'Every test lands inside the range a neutral process produces'
      : `${outside.length} of ${metrics.length} tests land outside the range a neutral process produces`;

  const compOutside = comp ? isOutside(comp) : false;
  const gradeList = metrics.filter((m) => m.grade);

  return (
    <Section
      id="benchmark"
      step="04"
      kicker={`The benchmark · ${chamberLabel}`}
      title={title}
      lede={`FDGA scored this map against ${fmtInt(run.draws)} alternative maps drawn by a computer that was never shown party registration, past results, or race. Inside the shaded band, geography alone could have produced the result. Outside it, fewer than 5 in 100 neutral maps land where this one does.`}
      aside={
        <>
          <p className="aside-title">Benchmark setup</p>
          <dl className="index-list">
            <div>
              <dt>Neutral maps compared</dt>
              <dd>{fmtInt(run.draws)}</dd>
            </div>
            <div>
              <dt>Drawing method</dt>
              <dd>{run.algorithm || 'ReCom'}</dd>
            </div>
            <div>
              <dt>Election basis</dt>
              <dd>{run.election || '2018–2024 composite'}</dd>
            </div>
            <div>
              <dt>Tests outside the band</dt>
              <dd>
                {outside.length} of {metrics.length}
              </dd>
            </div>
          </dl>

          <p className="aside-title" style={{ marginTop: 16 }}>
            Competition, in the scorecard&rsquo;s words
          </p>
          <blockquote className="bench-quote">
            “{(comp?.takeaway || '')
              .replace('district(s)', Number(comp?.enacted) === 1 ? 'district' : 'districts')
              .replace('fewer than 100% of neutral maps', 'fewer than any neutral map')}”
          </blockquote>
          {comp && (
            <p className="micro-note">
              In plain terms: {Math.round((1 - (comp.pctRank || 0)) * 100)}% of neutral maps keep
              more seats competitive than this one.
            </p>
          )}

          {ensemble.benchmarks?.muni_splits && (
            <>
              <p className="aside-title" style={{ marginTop: 16 }}>
                One measure where the map does well
              </p>
              <p className="micro-note">
                {ensemble.benchmarks.muni_splits.enacted} cities and towns are split across
                districts — the {ordinal(ensemble.benchmarks.muni_splits.pctRank)} percentile of
                neutral maps (fewer splits than{' '}
                {Math.max(
                  0,
                  Math.round((1 - (ensemble.benchmarks.muni_splits.pctRank || 0)) * 100),
                )}
                % of them). Keeping communities whole and drawing competitive districts can pull
                in opposite directions; a fair map has to weigh both.
              </p>
            </>
          )}

          <p className="aside-title" style={{ marginTop: 16 }}>
            Grades
          </p>
          <ul className="grade-list">
            {gradeList.map((m) => (
              <li key={m.key}>
                <span>{m.label}</span>
                <b
                  className="grade-chip"
                  style={{ background: GRADE_FILL[m.grade] || '#8b6fc4' }}
                  title={`Scorecard grade: ${m.grade}`}
                >
                  {m.grade}
                </b>
              </li>
            ))}
          </ul>
        </>
      }
      footer={`Source: FDGA neutral-ensemble scorecards (${run.algorithm || 'ReCom'}, ${fmtInt(run.draws)} maps, ${run.districts} districts, ${run.date || '2026'}). Percentiles are the share of neutral maps scoring below the enacted map; the band spans the 5th to 95th percentile. Composite basis: ${run.election || '2018–2024'}.`}
    >
      <div className="kpi-row">
        <div className="kpi">
          <span className="kpi-label">Neutral maps compared</span>
          <strong>{fmtInt(run.draws)}</strong>
          <span className="kpi-sub">no party, race or result data</span>
        </div>
        <div className={`kpi${outside.length ? ' is-flag' : ''}`}>
          <span className="kpi-label">Outside the neutral range</span>
          <strong>
            {outside.length} <small>of {metrics.length}</small>
          </strong>
          <span className="kpi-sub">
            {outside.length
              ? 'above the 95th or below the 5th percentile'
              : 'every test is within the 5th–95th band'}
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Seats decided by under 10 pts</span>
          <strong>{comp ? Math.round(comp.enacted) : '—'}</strong>
          <span className="kpi-sub">
            neutral median {comp ? Math.round(comp.p50) : '—'} ·{' '}
            {comp ? ordinal(comp.pctRank) : '—'} percentile
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Safe seats, both parties</span>
          <strong>
            {demSafe ? Math.round(demSafe.enacted) : '—'} D ·{' '}
            {repSafe ? Math.round(repSafe.enacted) : '—'} R
          </strong>
          <span className="kpi-sub">
            neutral median {demSafe ? Math.round(demSafe.p50) : '—'} D ·{' '}
            {repSafe ? Math.round(repSafe.p50) : '—'} R
          </span>
        </div>
      </div>

      <figure className="chart">
        <FigureTools
          name={`benchmark-percentiles-${ensemble.chamber}`}
          title={`${chamberLabel}: where the enacted map falls among neutral maps`}
          subtitle={`Percentile rank of the enacted ${chamberLabel} map on ${metrics.length} fairness tests, against ${fmtInt(run.draws)} neutral maps`}
        />
        <figcaption>
          Where the enacted map sits among {fmtInt(run.draws)} maps drawn without politics
        </figcaption>
        <div className="chart-scroll">
          <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Percentile strip plot: the enacted ${chamberLabel} map against ${fmtInt(run.draws)} neutral maps on ${metrics.length} tests`}
        >
          {/* the middle 90% of neutral maps, drawn once behind every row */}
          <rect
            x={x(5)}
            y={M.top - 12}
            width={x(95) - x(5)}
            height={metrics.length * rowH + 6}
            rx="10"
            fill="#6440a4"
            opacity="0.08"
          />
          <text x={x(5)} y={M.top - 18} className="axis-label">
            5th
          </text>
          <text x={x(95)} y={M.top - 18} textAnchor="end" className="axis-label">
            95th
          </text>
          <text x={(x(5) + x(95)) / 2} y={M.top - 18} textAnchor="middle" className="axis-label">
            middle 90% of neutral maps
          </text>

          {/* percentile grid */}
          {[0, 25, 50, 75, 100].map((t) => (
            <g key={t}>
              <line
                x1={x(t)}
                x2={x(t)}
                y1={M.top - 12}
                y2={baseline}
                className={t === 50 ? 'zero-line' : 'gridline'}
              />
              <text x={x(t)} y={baseline + 16} textAnchor="middle" className="axis-label">
                {t}
              </text>
            </g>
          ))}

          {metrics.map((m, i) => {
            const yc = M.top + i * rowH + rowH / 2;
            const out = isOutside(m);
            const dotX = x((m.pctRank || 0) * 100);
            const fill = GRADE_FILL[m.grade] || '#8b6fc4';
            const newGroup = i > 0 && metrics[i - 1].group !== m.group;
            return (
              <g key={m.key}>
                {newGroup && (
                  <line
                    x1={0}
                    x2={W}
                    y1={yc - rowH / 2}
                    y2={yc - rowH / 2}
                    stroke="#e4e0ee"
                    strokeWidth="1"
                  />
                )}
                <line
                  x1={x(0)}
                  x2={x(100)}
                  y1={yc}
                  y2={yc}
                  stroke="#cdc7dd"
                  strokeWidth="1"
                />
                {out && (
                  <circle
                    cx={dotX}
                    cy={yc}
                    r="9"
                    fill="none"
                    stroke="#7d3169"
                    strokeWidth="1.4"
                    strokeDasharray="2 2"
                  />
                )}
                <circle cx={dotX} cy={yc} r="4.6" fill={fill} stroke="#ffffff" strokeWidth="1.4" />
                <text
                  x={M.left - 12}
                  y={yc - 1}
                  textAnchor="end"
                  className={`bench-label${out ? ' is-outside' : ''}`}
                >
                  {m.label}
                </text>
                <text x={M.left - 12} y={yc + 10} textAnchor="end" className="bench-value">
                  {fmtValue(m, m.enacted)} · {ordinal(m.pctRank)}
                </text>
                <g>
                  <rect
                    x={W - 40}
                    y={yc - 8}
                    width="20"
                    height="16"
                    rx="4"
                    fill={fill}
                  />
                  <text
                    x={W - 30}
                    y={yc + 4}
                    textAnchor="middle"
                    className="grade-chip-text"
                  >
                    {m.grade || '–'}
                  </text>
                </g>
              </g>
            );
          })}

          <line
            x1={M.left}
            x2={W - M.right}
            y1={baseline}
            y2={baseline}
            className="axis-line"
          />
          <text x={x(0)} y={baseline + 30} className="axis-label">
            0
          </text>
          <text x={x(100)} y={baseline + 30} textAnchor="end" className="axis-label">
            percentile
          </text>
        </svg>
        </div>
      </figure>

      <p className="micro-note">
        Each row is one test; the dot is where the enacted map ranks. A dot left of the band ranks
        with the bottom 5% of neutral maps, a dot right of it with the top 5%. Neither direction is
        inherently partisan — read the label to see which way the test runs.
      </p>

      {comp && counts.length > 0 && (
        <figure className="chart">
          <FigureTools
            name={`benchmark-competition-${ensemble.chamber}`}
            title={`${chamberLabel}: competitive seats against the neutral range`}
            subtitle={`Number of ${chamberLabel} districts decided by under 10 points, across ${fmtInt(run.draws)} neutral maps; the enacted map is marked`}
          />
          <figcaption>
            Seats decided by under 10 points: the neutral range and the enacted map
          </figcaption>
          <div className="chart-scroll">
          <svg
            viewBox={`0 0 ${HIST_W} ${HIST_H}`}
            role="img"
            aria-label={`Histogram of competitive seat counts across neutral maps, with the enacted ${chamberLabel} map marked`}
          >
            <rect
              x={hx(comp.p5)}
              y={HM.top - 8}
              width={Math.max(0, hx(comp.p95) - hx(comp.p5))}
              height={histH + 8}
              fill="#6440a4"
              opacity="0.07"
            />

            {[0, 0.5, 1].map((t) => (
              <g key={t}>
                <line
                  x1={HM.left}
                  x2={HIST_W - HM.right}
                  y1={baselineH() - histH * t}
                  y2={baselineH() - histH * t}
                  className="gridline"
                />
                <text
                  x={HM.left - 8}
                  y={baselineH() - histH * t + 3}
                  textAnchor="end"
                  className="axis-label"
                >
                  {Math.round(yMax * t * 100)}%
                </text>
              </g>
            ))}

            {counts.map((c, i) => {
              const x0 = hx(edges[i]);
              const x1 = hx(edges[i + 1]);
              const h = Math.max(0.8, (c / yMax) * histH);
              return (
                <rect
                  key={`bar-${i}`}
                  x={x0 + 0.4}
                  y={baselineH() - h}
                  width={Math.max(0.8, x1 - x0 - 0.8)}
                  height={h}
                  fill={edges[i + 1] <= comp.p50 ? '#a996c6' : '#c8bcdd'}
                />
              );
            })}

            <line
              x1={hx(comp.p50)}
              x2={hx(comp.p50)}
              y1={HM.top - 8}
              y2={baselineH()}
              stroke="#4c4863"
              strokeWidth="1.2"
              strokeDasharray="4 3"
            />
            <line
              x1={hx(comp.enacted)}
              x2={hx(comp.enacted)}
              y1={HM.top - 8}
              y2={baselineH()}
              stroke="#7d3169"
              strokeWidth="2"
            />
            <circle cx={hx(comp.enacted)} cy={HM.top - 8} r="4" fill="#7d3169" />
            <text
              x={Math.min(HIST_W - HM.right - 4, Math.max(HM.left + 4, hx(comp.enacted)))}
              y={HM.top - 14}
              textAnchor="middle"
              className="bench-value is-strong"
            >
              enacted {Math.round(comp.enacted)}
            </text>

            <line
              x1={HM.left}
              x2={HIST_W - HM.right}
              y1={baselineH()}
              y2={baselineH()}
              className="axis-line"
            />
            {(() => {
              const ticks = [];
              for (let v = Math.ceil(h0); v <= Math.floor(h1); v += tickStep) ticks.push(v);
              return ticks.map((v) => (
                <text
                  key={`tick-${v}`}
                  x={hx(v)}
                  y={baselineH() + 15}
                  textAnchor="middle"
                  className="axis-label"
                >
                  {v}
                </text>
              ));
            })()}
            <text x={HM.left} y={HIST_H - 6} className="axis-label">
              districts decided by under 10 points
            </text>
          </svg>
          </div>
          <p className="micro-note">
            Shaded band: the middle 90% of neutral maps. Dashed line: their median ({Math.round(
              comp.p50,
            )}). Solid line: the enacted map ({Math.round(comp.enacted)}), at the{' '}
            {ordinal(comp.pctRank)} percentile. A neutral process keeps more seats competitive than
            this map does{compOutside ? '' : ' in most, though not all, chambers'}.
          </p>
        </figure>
      )}

      <div className="law-note">
        <p>
          <strong>What this can and cannot say.</strong> The benchmark compares this map with plans
          drawn at random from Georgia&rsquo;s geography. It shows whether an outcome is typical, not
          why any line was drawn. A map can land outside the band for reasons that have nothing to do
          with party — protecting an incumbent, keeping a county whole, or complying with the Voting
          Rights Act. The benchmark is a smoke alarm, not a verdict.
        </p>
        <p>
          <strong>Why both parties&rsquo; safe-seat counts are shown.</strong> Packing either
          party&rsquo;s voters into fewer districts shrinks competition. Showing both counts is the
          symmetry test: when one party&rsquo;s safe seats sit far above the neutral median and the
          other&rsquo;s sit near it, the map is turning votes into seats at different rates. That is
          a statement about the lines, not about the voters who live inside them.
        </p>
        <p>
          <strong>A composite, not a single election.</strong> These scores use six elections from
          2018 to 2024. The rest of this page counts one election at a time. Where the two disagree,
          both are shown; they answer different questions, and neither is wrong.
        </p>
        <p>
          <strong>No court has to call this unlawful for it to matter.</strong> Federal courts cannot
          hear partisan-gerrymandering claims at all (
          <a
            href="https://www.supremecourt.gov/opinions/18pdf/18-422_9ol1.pdf"
            target="_blank"
            rel="noreferrer"
          >
            Rucho v. Common Cause
          </a>
          ), so the benchmark is where the public argument happens. It measures how far the map sits
          from what geography alone would produce — and leaves the conclusion to the reader.
        </p>
      </div>
    </Section>
  );
}
