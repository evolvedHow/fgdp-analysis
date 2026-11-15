-- postgres_ddl.sql — Schema for the Fair Districts GA canonical data model.
--
-- Applied by scripts/load_fdga_to_postgres.py. Idempotent: safe to re-run.
--
-- This schema is a *sink*, not a source. The build in fdp/cdm/ is the system of
-- record; this is one of two publishing targets (the other is Google Sheets).
-- Neither is downstream of the other, so they cannot drift apart.
--
-- The apps (fdex, lrdb, map-compare) do NOT read from here. They consume static
-- Parquet/GeoJSON copied by `fdp sync-app` and deploy to GitHub Pages. Nothing
-- in this file introduces a runtime dependency for them.

CREATE SCHEMA IF NOT EXISTS fdga;

-- Table, view and column documentation lives in postgres_comments.sql,
-- applied by the loader immediately after this file. Keeping it separate
-- means one place to edit prose, and it can be re-applied on its own with
--   load_fdga_to_postgres.py --comments-only

-- ---------------------------------------------------------------------------
-- Provenance. Loaded first: facts references it.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fdga.manifest (
    source_id             text PRIMARY KEY,
    cycle_year            integer     NOT NULL,
    election_date         date        NOT NULL,
    election_type         text        NOT NULL,
    grain_published       text,        -- county | precinct, as published upstream
    files_read            integer,
    rows_in               bigint,
    rows_out              bigint,
    votes_total           bigint,
    dropped_out_of_scope  bigint,
    dropped_no_county     bigint,
    dropped_bad_votes     bigint,
    dropped_no_district   bigint,
    offices_kept          text,
    reports_incumbency    boolean,
    unmapped_parties      text,
    sha256                text,        -- digest of the source bytes
    note                  text,
    built_at              timestamptz
);


-- ---------------------------------------------------------------------------
-- Facts — county x contest x candidate. No judgments, only what the source says.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fdga.facts (
    election_date   date    NOT NULL,
    cycle_year      integer NOT NULL,
    election_type   text    NOT NULL,
    office          text    NOT NULL,
    -- Zero-padded ('001'). Deliberately text: casting to integer loses the
    -- padding and silently breaks joins to contests.
    district        text    NOT NULL DEFAULT '',
    county          text    NOT NULL,
    candidate_name  text    NOT NULL,
    party_raw       text,                       -- exactly as published, for audit
    party           text    NOT NULL,           -- R D L G I W N O
    votes           bigint  NOT NULL CHECK (votes >= 0),
    source_id       text    NOT NULL REFERENCES fdga.manifest(source_id),
    source_row      bigint,
    -- Enforces the declared grain: a bad reload fails loudly rather than
    -- silently double-counting. election_type is part of the key because two
    -- races for the same office can share a date — in 2020 the regular U.S.
    -- Senate race and the Loeffler/Warnock special were both on 2020-11-03.
    CONSTRAINT facts_grain UNIQUE
        (election_date, election_type, office, district, county,
         candidate_name, party)
);

CREATE INDEX IF NOT EXISTS facts_cycle_office_district_idx
    ON fdga.facts (cycle_year, office, district);
CREATE INDEX IF NOT EXISTS facts_county_idx ON fdga.facts (county);
CREATE INDEX IF NOT EXISTS facts_party_idx  ON fdga.facts (party);

-- ---------------------------------------------------------------------------
-- Contests — one row per race. Mechanical properties plus the two policy flags.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fdga.contests (
    cycle_year            integer NOT NULL,
    election_date         date    NOT NULL,
    election_type         text    NOT NULL,
    office                text    NOT NULL,
    district              text    NOT NULL,
    candidate_count       integer NOT NULL,
    party_count           integer NOT NULL,
    winner_party          text,
    winner_name           text,
    winner_votes          bigint,
    winner_share          double precision,
    runner_up_party       text,
    runner_up_votes       bigint,
    margin                bigint,
    margin_share          double precision,
    votes_total           bigint  NOT NULL,
    votes_r               bigint  NOT NULL,
    votes_d               bigint  NOT NULL,
    votes_other           bigint  NOT NULL,
    counties              integer,
    -- No opponent on the ballot, write-ins aside (the legacy workbook's rule).
    is_uncontested        boolean NOT NULL,
    -- Broader: no major-party opponent.
    is_uncontested_major  boolean NOT NULL,
    is_competitive        boolean NOT NULL,   -- at the default 0.535 threshold
    is_competitive_052    boolean,
    is_competitive_0535   boolean,
    is_competitive_055    boolean,
    is_competitive_06     boolean,
    -- election_type is part of the key: 2020 held both a regular and a special
    -- U.S. Senate race, so (cycle_year, office, district) alone is not unique.
    CONSTRAINT contests_grain UNIQUE
        (cycle_year, election_type, office, district)
);

CREATE INDEX IF NOT EXISTS contests_office_idx ON fdga.contests (office, cycle_year);

-- ---------------------------------------------------------------------------
-- Chamber-year — the headline seats-vs-votes table.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fdga.chamber_year (
    cycle_year               integer NOT NULL,
    chamber                  text    NOT NULL,
    seats_total_expected     integer,
    districts_present        integer,
    -- FALSE where seats cannot be attributed from district results alone.
    -- 2002 state house: 147 multi-member districts elected 180 members and the
    -- source carries no post identifier. Seat columns are NULL there, which is
    -- why they are nullable — do not add NOT NULL.
    seats_derivable          boolean NOT NULL,
    seats_r                  integer,
    seats_d                  integer,
    seats_other              integer,
    pct_seats_r              double precision,
    pct_seats_d              double precision,
    races_total              integer NOT NULL,
    races_uncontested        integer NOT NULL,
    races_contested          integer NOT NULL,
    races_competitive        integer NOT NULL,
    races_uncontested_major  integer,
    pct_uncontested          double precision,
    pct_competitive          double precision,
    votes_total              bigint  NOT NULL,
    votes_r                  bigint  NOT NULL,
    votes_d                  bigint  NOT NULL,
    votes_other              bigint  NOT NULL,
    pct_votes_r              double precision,
    pct_votes_d              double precision,
    seats_votes_gap_r        double precision,
    CONSTRAINT chamber_year_grain UNIQUE (cycle_year, chamber)
);


-- ---------------------------------------------------------------------------
-- Statewide races — the baseline chamber results are measured against.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fdga.statewide (
    cycle_year     integer NOT NULL,
    election_date  date    NOT NULL,
    election_type  text    NOT NULL,
    office         text    NOT NULL,
    winner_party   text,
    winner_name    text,
    winner_share   double precision,
    votes_total    bigint,
    votes_r        bigint,
    votes_d        bigint,
    votes_other    bigint,
    pct_votes_r    double precision,
    pct_votes_d    double precision,
    CONSTRAINT statewide_grain UNIQUE (cycle_year, office, election_type)
);

-- ---------------------------------------------------------------------------
-- Audit tables. Small, and the reason anyone should trust the numbers above.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fdga.corrections (
    correction    text,
    rows_matched  integer,
    status        text,      -- APPLIED | NO_MATCH
    evidence      text
);

CREATE TABLE IF NOT EXISTS fdga.name_merges (
    cycle_year   integer,
    office       text,
    district     text,
    party        text,
    merged_from  text,
    merged_into  text,
    votes_moved  bigint
);

CREATE TABLE IF NOT EXISTS fdga.validation (
    check_name  text,
    severity    text,        -- FAIL | WARN | KNOWN | PASS
    scope       text,
    detail      text
);

CREATE TABLE IF NOT EXISTS fdga.reconciliation (
    cycle_year  integer,
    chamber     text,
    field       text,
    cdm         integer,
    workbook    integer,
    delta       integer,
    status      text         -- MATCH | DIFF | CDM_NULL | BOOK_NULL | BOTH_NULL
);


-- ===========================================================================
-- View layer — the semantic contract.
--
-- Analysts and Metabase models read these, never the raw tables. Business
-- definitions live upstream in fdp/cdm/aggregate.py and surface here as
-- columns; nothing downstream should re-implement them.
--
-- Naming conventions, so a query never needs a quoted identifier:
--   snake_case throughout
--   <thing>          the machine-readable code you filter on (chamber, office)
--   <thing>_label    the human-readable form for display
--   *_pct            already scaled to percentage points (55.6, not 0.556).
--                    The underlying tables store these as 0-1 ratios under
--                    pct_* names — the suffix marks the scaled version.
-- ===========================================================================

CREATE OR REPLACE VIEW fdga.v_chamber_year AS
SELECT
    cy.cycle_year,
    cy.chamber,
    CASE cy.chamber
        WHEN 'us_house'     THEN 'U.S. House'
        WHEN 'state_senate' THEN 'Georgia Senate'
        WHEN 'state_house'  THEN 'Georgia House'
        ELSE cy.chamber
    END                                             AS chamber_label,
    cy.seats_r,
    cy.seats_d,
    cy.seats_other,
    round((cy.pct_seats_r  * 100)::numeric, 1)      AS seat_share_r_pct,
    round((cy.pct_seats_d  * 100)::numeric, 1)      AS seat_share_d_pct,
    round((cy.pct_votes_r  * 100)::numeric, 1)      AS vote_share_r_pct,
    round((cy.pct_votes_d  * 100)::numeric, 1)      AS vote_share_d_pct,
    round((cy.seats_votes_gap_r * 100)::numeric, 1) AS seats_votes_gap_r_pct,
    cy.races_total,
    cy.races_uncontested,
    cy.races_contested,
    cy.races_competitive,
    round((cy.pct_uncontested * 100)::numeric, 1)   AS uncontested_pct,
    round((cy.pct_competitive * 100)::numeric, 1)   AS competitive_pct,
    cy.votes_total,
    cy.votes_r,
    cy.votes_d,
    cy.seats_derivable
FROM fdga.chamber_year cy;

CREATE OR REPLACE VIEW fdga.v_contest AS
SELECT
    c.cycle_year,
    c.office                                  AS chamber,
    CASE c.office
        WHEN 'us_house'     THEN 'U.S. House'
        WHEN 'state_senate' THEN 'Georgia Senate'
        WHEN 'state_house'  THEN 'Georgia House'
        ELSE c.office
    END                                       AS chamber_label,
    c.district,
    c.winner_name,
    c.winner_party,
    round((c.winner_share * 100)::numeric, 1) AS winner_share_pct,
    round((c.margin_share * 100)::numeric, 1) AS margin_pct,
    c.margin,
    c.votes_total,
    c.votes_r,
    c.votes_d,
    c.votes_other,
    c.candidate_count,
    c.is_uncontested,
    c.is_uncontested_major,
    c.is_competitive,
    c.is_competitive_052,
    c.is_competitive_0535,
    c.is_competitive_055,
    c.is_competitive_06,
    -- Wasted-vote components, so the efficiency gap is a sum of columns rather
    -- than CASE logic re-typed into a Metabase expression. A vote is wasted if
    -- it went to a loser, or to a winner beyond the half needed to win.
    -- Appended, not inserted: CREATE OR REPLACE VIEW only allows new columns at
    -- the end.
    c.votes_r + c.votes_d                                   AS votes_two_party,
    CASE WHEN c.votes_r > c.votes_d
         THEN c.votes_r - (c.votes_r + c.votes_d) / 2.0
         ELSE c.votes_r END                                 AS wasted_votes_r,
    CASE WHEN c.votes_d > c.votes_r
         THEN c.votes_d - (c.votes_r + c.votes_d) / 2.0
         ELSE c.votes_d END                                 AS wasted_votes_d,
    -- Carried down from chamber_year so seat-share metrics can exclude 2002
    -- state house semantically instead of hard-coding the year. The join is
    -- 1:1 — chamber_year is unique on (cycle_year, chamber).
    cy.seats_derivable
FROM fdga.contests c
LEFT JOIN fdga.chamber_year cy
       ON cy.cycle_year = c.cycle_year
      AND cy.chamber    = c.office
WHERE c.office IN ('us_house', 'state_senate', 'state_house');

CREATE OR REPLACE VIEW fdga.v_statewide AS
SELECT
    s.cycle_year,
    s.office,
    initcap(replace(s.office, '_', ' '))      AS office_label,
    s.election_type,
    s.winner_name,
    s.winner_party,
    round((s.winner_share * 100)::numeric, 1) AS winner_share_pct,
    round((s.pct_votes_r * 100)::numeric, 1)  AS vote_share_r_pct,
    round((s.pct_votes_d * 100)::numeric, 1)  AS vote_share_d_pct,
    s.votes_total,
    s.votes_r,
    s.votes_d
FROM fdga.statewide s;

CREATE OR REPLACE VIEW fdga.v_county_results AS
SELECT
    f.cycle_year,
    f.county,
    f.office,
    CASE f.office
        WHEN 'us_house'     THEN 'U.S. House'
        WHEN 'state_senate' THEN 'Georgia Senate'
        WHEN 'state_house'  THEN 'Georgia House'
        WHEN 'president'    THEN 'President'
        WHEN 'governor'     THEN 'Governor'
        WHEN 'us_senate'    THEN 'U.S. Senate'
        ELSE f.office
    END                                       AS office_label,
    f.district,
    f.candidate_name,
    f.party,
    f.votes
FROM fdga.facts f;

-- Data-quality surface, so a dashboard can show trust at a glance.
CREATE OR REPLACE VIEW fdga.v_data_health AS
SELECT
    (SELECT count(*) FROM fdga.validation WHERE severity = 'FAIL')  AS failing_checks,
    (SELECT count(*) FROM fdga.validation WHERE severity = 'WARN')  AS warnings,
    (SELECT count(*) FROM fdga.validation WHERE severity = 'KNOWN') AS known_gaps,
    (SELECT count(*) FROM fdga.validation WHERE severity = 'PASS')  AS passing_checks,
    (SELECT count(*) FROM fdga.corrections WHERE status = 'APPLIED') AS corrections_applied,
    (SELECT count(*) FROM fdga.name_merges)                          AS name_variants_merged,
    (SELECT count(*) FROM fdga.reconciliation WHERE status = 'MATCH') AS workbook_cells_matching,
    (SELECT count(*) FROM fdga.reconciliation)                        AS workbook_cells_compared,
    (SELECT max(built_at) FROM fdga.manifest)                         AS last_built_at,
    (SELECT sum(votes_total) FROM fdga.manifest)                      AS total_votes_loaded,
    (SELECT count(*) FILTER (WHERE status = 'MATCH') || ' / ' || count(*)
       FROM fdga.reconciliation)                                      AS legacy_workbook_agreement;

-- ---------------------------------------------------------------------------
-- Voter choice / ballot roll-off.
--
-- The legacy workbook's most persuasive measure, and the only one not derivable
-- from a single table: how many people cast a ballot but had no meaningful
-- choice further down it. Computed as the top-of-ticket turnout minus the votes
-- actually cast in a chamber's races.
--
-- The baseline is the highest-turnout statewide race in the cycle — president
-- in presidential years, governor or U.S. Senate in midterms — which is the top
-- of the ticket by definition, without hard-coding which office that was.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW fdga.v_voter_choice AS
WITH baseline AS (
    SELECT DISTINCT ON (cycle_year)
           cycle_year,
           office       AS baseline_office,
           votes_total  AS ballots_cast
    FROM fdga.statewide
    ORDER BY cycle_year, votes_total DESC
),
chamber AS (
    SELECT
        cycle_year,
        office AS chamber,
        COALESCE(SUM(votes_total) FILTER (WHERE is_competitive), 0)
            AS votes_competitive,
        COALESCE(SUM(votes_total) FILTER (
            WHERE NOT is_competitive AND NOT is_uncontested), 0)
            AS votes_non_competitive,
        COALESCE(SUM(votes_total) FILTER (WHERE is_uncontested), 0)
            AS votes_uncontested,
        COALESCE(SUM(votes_total), 0) AS votes_cast
    FROM fdga.contests
    WHERE office IN ('us_house', 'state_senate', 'state_house')
    GROUP BY 1, 2
)
SELECT
    c.cycle_year,
    c.chamber,
    CASE c.chamber
        WHEN 'us_house'     THEN 'U.S. House'
        WHEN 'state_senate' THEN 'Georgia Senate'
        WHEN 'state_house'  THEN 'Georgia House'
    END                                        AS chamber_label,
    b.baseline_office,
    b.ballots_cast,
    c.votes_competitive,
    c.votes_non_competitive,
    c.votes_uncontested,
    c.votes_cast,
    GREATEST(b.ballots_cast - c.votes_cast, 0) AS no_vote_cast,
    round(100.0 * c.votes_competitive     / NULLIF(b.ballots_cast, 0), 1)
        AS competitive_pct,
    round(100.0 * c.votes_non_competitive / NULLIF(b.ballots_cast, 0), 1)
        AS non_competitive_pct,
    round(100.0 * c.votes_uncontested     / NULLIF(b.ballots_cast, 0), 1)
        AS uncontested_pct,
    round(100.0 * GREATEST(b.ballots_cast - c.votes_cast, 0)
                / NULLIF(b.ballots_cast, 0), 1)
        AS no_vote_cast_pct,
    round(100.0 * (c.votes_uncontested + GREATEST(b.ballots_cast - c.votes_cast, 0))
                / NULLIF(b.ballots_cast, 0), 1)
        AS no_meaningful_choice_pct
FROM chamber c
JOIN baseline b USING (cycle_year);


-- ===========================================================================
-- Dashboard views — one per insight in dashboard_insights.md.
--
-- These exist so a Metabase question is `SELECT * FROM fdga.v_x` with a filter,
-- not a block of pasted SQL that drifts from the document. Same rule as the
-- views above: no business definition originates here, it only gets reshaped.
--
-- Every view carries both `chamber` (the code you filter on) and
-- `chamber_label` (display). Filtering on the label works but breaks the day a
-- label is reworded.
--
-- No ORDER BY inside these views. It is not guaranteed to survive when the view
-- is wrapped in another query, and Metabase applies its own sort anyway.
-- ===========================================================================

-- Dropped before creation, not CREATE OR REPLACE: these views gained a
-- `chamber` code column in position 2, and Postgres refuses to rename or
-- reorder an existing view's columns in place. Nothing depends on them.

DROP VIEW IF EXISTS fdga.v_100_voters;
DROP VIEW IF EXISTS fdga.v_100_voters_long;
DROP VIEW IF EXISTS fdga.v_contest_by_category;
DROP VIEW IF EXISTS fdga.v_decided_before_election;
DROP VIEW IF EXISTS fdga.v_partisan_preference_baseline;
DROP VIEW IF EXISTS fdga.v_proportional_allocation;
DROP VIEW IF EXISTS fdga.v_county_splits;
DROP VIEW IF EXISTS fdga.v_efficiency_gap;
DROP VIEW IF EXISTS fdga.v_which_party_benefits;
DROP VIEW IF EXISTS fdga.v_seat_vote_inversions;
DROP VIEW IF EXISTS fdga.v_race_drilldown;

-- 1.1  The village of 100 voters. Four mutually exclusive buckets that sum to
--      ballots_cast, so the row lands on 100 by construction.
--
--      2002 state house is excluded: its multi-member districts let one voter
--      cast up to three state house votes, so votes_cast (2,673,452) exceeds
--      the top-of-ticket ballots_cast (2,029,991), GREATEST(...,0) clamps
--      no_vote_cast to zero, and the remaining three shares sum to 131.
CREATE OR REPLACE VIEW fdga.v_100_voters AS
SELECT
    vc.cycle_year,
    vc.chamber,
    vc.chamber_label,
    vc.ballots_cast,
    round(100.0 * vc.votes_competitive     / vc.ballots_cast) AS had_a_real_race,
    round(100.0 * vc.votes_non_competitive / vc.ballots_cast) AS race_already_decided,
    round(100.0 * vc.votes_uncontested     / vc.ballots_cast) AS only_one_name,
    round(100.0 * vc.no_vote_cast          / vc.ballots_cast) AS skipped_the_race
FROM fdga.v_voter_choice vc
WHERE NOT (vc.cycle_year = 2002 AND vc.chamber = 'state_house');

-- 1.1b The same four buckets long-form: one row per cycle, chamber and
--      category, instead of four columns on one row. Use this for a stacked bar
--      or any chart that needs a series dimension; use v_100_voters (wide) for
--      a table or big-number cards.
--
--      CROSS JOIN LATERAL (VALUES ...) unpivots in a single pass over
--      v_voter_choice. A four-way UNION ALL would re-scan it four times.
--
--      sort_order exists because Metabase orders a category axis
--      alphabetically, which would render the narrative backwards.
CREATE OR REPLACE VIEW fdga.v_100_voters_long AS
SELECT
    vc.cycle_year,
    vc.chamber,
    vc.chamber_label,
    vc.ballots_cast,
    b.sort_order,
    b.category,
    b.votes,
    round(100.0 * b.votes / vc.ballots_cast)      AS voters_per_100,
    round(100.0 * b.votes / vc.ballots_cast, 1)   AS pct
FROM fdga.v_voter_choice vc
CROSS JOIN LATERAL (VALUES
    (1, 'Had a real race',      vc.votes_competitive),
    (2, 'Race already decided', vc.votes_non_competitive),
    (3, 'Only one name',        vc.votes_uncontested),
    (4, 'Skipped the race',     vc.no_vote_cast)
) AS b(sort_order, category, votes)
WHERE NOT (vc.cycle_year = 2002 AND vc.chamber = 'state_house');

-- 1.3  Races by category, long-form for a stacked bar.
CREATE OR REPLACE VIEW fdga.v_contest_by_category AS
WITH unpivoted AS (
    SELECT cycle_year, chamber, chamber_label,
           'Uncontested' AS category, races_uncontested AS races
    FROM fdga.v_chamber_year
    UNION ALL
    SELECT cycle_year, chamber, chamber_label,
           'Contested, not competitive', races_contested - races_competitive
    FROM fdga.v_chamber_year
    UNION ALL
    SELECT cycle_year, chamber, chamber_label,
           'Competitive', races_competitive
    FROM fdga.v_chamber_year
)
SELECT
    u.cycle_year,
    u.chamber,
    u.chamber_label,
    u.category,
    u.races,
    round(100.0 * u.races
          / NULLIF(SUM(u.races) OVER (PARTITION BY u.cycle_year, u.chamber), 0), 1)
        AS pct_of_total
FROM unpivoted u;

-- 1.4  How many voters, not races, were in a foregone conclusion.
--      cycle_year MUST be in the grain — without it this pools all 13 cycles
--      and reports 1,516 uncontested Georgia House races instead of 2024's 90.
CREATE OR REPLACE VIEW fdga.v_decided_before_election AS
SELECT
    c.cycle_year,
    c.chamber,
    c.chamber_label,
    COUNT(*) FILTER (WHERE c.is_uncontested)                          AS uncontested,
    COUNT(*) FILTER (WHERE NOT c.is_uncontested AND c.margin_pct >= 20) AS won_by_20_plus,
    COUNT(*) FILTER (WHERE NOT c.is_uncontested AND c.margin_pct <  20) AS actual_race,
    COALESCE(SUM(c.votes_total) FILTER
             (WHERE c.is_uncontested OR c.margin_pct >= 20), 0)       AS votes_predecided,
    SUM(c.votes_total)                                                AS votes_total,
    round(100.0 * COALESCE(SUM(c.votes_total) FILTER
                  (WHERE c.is_uncontested OR c.margin_pct >= 20), 0)
                / NULLIF(SUM(c.votes_total), 0), 1)                   AS predecided_pct
FROM fdga.v_contest c
GROUP BY 1, 2, 3;

-- 2.2  Statewide partisan baseline, long-form. Uncontested races cannot distort
--      it because every voter votes in a statewide race.
CREATE OR REPLACE VIEW fdga.v_partisan_preference_baseline AS
SELECT cycle_year, office, office_label, election_type,
       'Republican' AS party, vote_share_r_pct AS pct
FROM fdga.v_statewide
UNION ALL
SELECT cycle_year, office, office_label, election_type,
       'Democratic', vote_share_d_pct
FROM fdga.v_statewide;

-- 2.3  Seats under proportional allocation, against two different benchmarks.
--
--      seats_r_proportional_chamber uses the chamber's own two-party vote,
--      which an uncontested seat distorts (it contributes 100% to one party).
--      seats_r_proportional_statewide uses the cycle's highest-turnout
--      statewide race instead, which no district line can skew — but assumes
--      voters split the same way down-ballot, which split-ticket years like
--      2000 show they do not always do. Quote both or neither.
CREATE OR REPLACE VIEW fdga.v_proportional_allocation AS
WITH baseline AS (
    SELECT DISTINCT ON (cycle_year)
           cycle_year,
           office                                              AS baseline_office,
           votes_r::numeric / NULLIF(votes_r + votes_d, 0)     AS baseline_r_share
    FROM fdga.statewide
    ORDER BY cycle_year, votes_total DESC
)
SELECT
    cy.cycle_year,
    cy.chamber,
    cy.chamber_label,
    cy.seats_r,
    cy.seats_d,
    (cy.seats_r + cy.seats_d + COALESCE(cy.seats_other, 0))    AS seats_total,
    b.baseline_office,
    round(100.0 * b.baseline_r_share, 1)                       AS statewide_r_share_pct,
    round((cy.seats_r + cy.seats_d + COALESCE(cy.seats_other, 0))
          * cy.votes_r::numeric / NULLIF(cy.votes_r + cy.votes_d, 0))
        AS seats_r_proportional_chamber,
    cy.seats_r - round((cy.seats_r + cy.seats_d + COALESCE(cy.seats_other, 0))
          * cy.votes_r::numeric / NULLIF(cy.votes_r + cy.votes_d, 0))
        AS r_seat_bonus_chamber,
    round((cy.seats_r + cy.seats_d + COALESCE(cy.seats_other, 0)) * b.baseline_r_share)
        AS seats_r_proportional_statewide,
    cy.seats_r - round((cy.seats_r + cy.seats_d + COALESCE(cy.seats_other, 0))
          * b.baseline_r_share)
        AS r_seat_bonus_statewide
FROM fdga.v_chamber_year cy
JOIN baseline b ON b.cycle_year = cy.cycle_year
WHERE cy.seats_derivable;

-- 2.5  Counties reporting votes in more than one district. A reported-results
--      proxy for the boundary, not the boundary itself — directional only.
CREATE OR REPLACE VIEW fdga.v_county_splits AS
SELECT
    x.cycle_year,
    x.office                          AS chamber,
    CASE x.office
        WHEN 'us_house'     THEN 'U.S. House'
        WHEN 'state_senate' THEN 'Georgia Senate'
        WHEN 'state_house'  THEN 'Georgia House'
    END                               AS chamber_label,
    COUNT(*) FILTER (WHERE x.districts > 1) AS counties_split,
    COUNT(*)                                AS counties_reporting
FROM (SELECT cycle_year, office, county, COUNT(DISTINCT district) AS districts
      FROM fdga.facts
      WHERE office IN ('us_house', 'state_senate', 'state_house')
      GROUP BY 1, 2, 3) x
GROUP BY 1, 2, 3;

-- 3.1  Efficiency gap. Reads the wasted-vote columns on v_contest rather than
--      repeating the CASE logic, so the definition has exactly one home.
--      uncontested_races is carried so a consumer can see when the measure is
--      not trustworthy — see the guardrail in dashboard_insights.md.
CREATE OR REPLACE VIEW fdga.v_efficiency_gap AS
SELECT
    c.cycle_year,
    c.chamber,
    c.chamber_label,
    round(100.0 * SUM(c.wasted_votes_r) / NULLIF(SUM(c.votes_two_party), 0), 1)
        AS wasted_r_pct,
    round(100.0 * SUM(c.wasted_votes_d) / NULLIF(SUM(c.votes_two_party), 0), 1)
        AS wasted_d_pct,
    round(100.0 * (SUM(c.wasted_votes_d) - SUM(c.wasted_votes_r))
                / NULLIF(SUM(c.votes_two_party), 0), 1)
        AS efficiency_gap_r_pct,
    COUNT(*)                                 AS races,
    COUNT(*) FILTER (WHERE c.is_uncontested) AS uncontested_races
FROM fdga.v_contest c
GROUP BY 1, 2, 3;

-- 3.2  Who runs unopposed. COALESCE to 0 matters: SUM over an empty set is
--      NULL, and U.S. House 2020-2024 had no uncontested races at all.
CREATE OR REPLACE VIEW fdga.v_which_party_benefits AS
SELECT
    c.cycle_year,
    c.chamber,
    c.chamber_label,
    COUNT(*) FILTER (WHERE c.is_uncontested AND c.winner_party = 'R') AS unopposed_r,
    COUNT(*) FILTER (WHERE c.is_uncontested AND c.winner_party = 'D') AS unopposed_d,
    COALESCE(SUM(c.votes_total) FILTER
             (WHERE c.is_uncontested AND c.winner_party = 'R'), 0)   AS votes_unopposed_r,
    COALESCE(SUM(c.votes_total) FILTER
             (WHERE c.is_uncontested AND c.winner_party = 'D'), 0)   AS votes_unopposed_d
FROM fdga.v_contest c
GROUP BY 1, 2, 3;

-- 3.3  Cycles where the party with more votes won fewer seats, both directions.
CREATE OR REPLACE VIEW fdga.v_seat_vote_inversions AS
SELECT
    cy.cycle_year,
    cy.chamber,
    cy.chamber_label,
    cy.vote_share_r_pct,
    cy.seats_r,
    cy.seats_d,
    CASE WHEN cy.vote_share_r_pct > 50 AND cy.seats_r < cy.seats_d
              THEN 'Won votes, lost seats: R'
         WHEN cy.vote_share_r_pct < 50 AND cy.seats_d < cy.seats_r
              THEN 'Won votes, lost seats: D'
    END AS inversion
FROM fdga.v_chamber_year cy
WHERE cy.seats_derivable
  AND ((cy.vote_share_r_pct > 50 AND cy.seats_r < cy.seats_d)
    OR (cy.vote_share_r_pct < 50 AND cy.seats_d < cy.seats_r));

-- 3.4  Race-level receipts. cycle_year and chamber are required in the output:
--      without them the view returns 3,207 undifferentiated rows and district
--      '001' appears 39 times with no way to tell the years apart.
CREATE OR REPLACE VIEW fdga.v_race_drilldown AS
SELECT
    c.cycle_year,
    c.chamber,
    c.chamber_label,
    c.district,
    c.winner_name,
    c.winner_party,
    c.winner_share_pct,
    c.margin_pct,
    c.votes_total,
    CASE WHEN c.is_uncontested THEN 'Uncontested'
         WHEN c.is_competitive THEN 'Competitive'
         ELSE 'Not competitive' END AS category
FROM fdga.v_contest c;


-- ---------------------------------------------------------------------------
-- Retired view names. Dropped so the schema cannot carry two definitions of
-- one idea; each is superseded by a view above.
--
--   v_$data_health                              -> v_data_health
--        (the '$' forced quoted identifiers everywhere; the concatenated
--         legacy_workbook_agreement it added is now a v_data_health column)
--   v_proportional_allocation_vs_state_baseline -> v_proportional_allocation
--        (the name promised a statewide baseline but computed chamber vote
--         share, which is the exact distortion the baseline is meant to avoid.
--         The replacement reports both, labelled.)
--   v_seat_vote_bidirectional_inversions        -> v_seat_vote_inversions
-- ---------------------------------------------------------------------------

DROP VIEW IF EXISTS fdga."v_$data_health";
DROP VIEW IF EXISTS fdga.v_proportional_allocation_vs_state_baseline;
DROP VIEW IF EXISTS fdga.v_seat_vote_bidirectional_inversions;
