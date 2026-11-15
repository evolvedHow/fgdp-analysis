# The `fdga` PostgreSQL Data Model

Complete reference for the Georgia elections schema in PostgreSQL: 9 tables,
17 views, 296 columns, cycles 2000–2024.

**This document is the reference. It is not the source of truth.** The schema is
defined in [`postgres_ddl.sql`](postgres_ddl.sql) and documented in
[`postgres_comments.sql`](postgres_comments.sql); the column tables below were
generated from the live catalog so they cannot drift from what is actually
deployed. Regenerate after any schema change.

Related reading:

| Document | Covers |
|---|---|
| [`README.md`](README.md) | the CDM build — sources, corrections, reconciliation |
| [`dashboard_insights.md`](dashboard_insights.md) | how to *use* these views: queries, narrative, Metabase metrics |
| this file | the schema itself — grain, keys, types, lineage |

---

## Where Postgres sits

**PostgreSQL is a sink, not the system of record.** The system of record is the
Python build in `fdp/cdm/`, which reads OpenElections files, applies documented
corrections, computes every derived measure, validates the result, and writes
CSV and Parquet to `fdp/data/repos/main/fdga/`.

Postgres is one of three publishing targets fed from that same build:

```
                     OpenElections (GitHub tarball)
                                 |
                        fdp/cdm/sources.py        source registry: the only
                                 |                module that knows file shape
                        fdp/cdm/adapters.py       read, roll precinct -> county
                                 |
                      fdp/cdm/corrections.py      documented fixes + evidence
                                 |
                       fdp/cdm/aggregate.py       ALL business definitions
                                 |
                       fdp/cdm/validate.py        FAIL / WARN / KNOWN / PASS
                                 |
                  fdp/data/repos/main/fdga/*.csv  the built artifact
                                 |
            +--------------------+--------------------+
            |                    |                    |
       PostgreSQL          Google Sheets        Parquet -> fdp sync-app
            |                    |                    |
        Metabase            Sheets add-on      fdex / lrdb / map-compare
      (analysts)         (spreadsheet users)     (GitHub Pages, static)
```

**No sink is downstream of another**, so they cannot drift. Each is a
publication of the same validated build.

**The apps have no database dependency.** fdex, lrdb and map-compare read static
Parquet and GeoJSON and deploy to GitHub Pages. If Postgres is down, every
public map still works. Nothing in this schema changes that.

## How this harmonizes with the CDM

The Postgres tables are a **1:1 image of the CDM's output tables** — same names,
same grain, same columns, same order. `scripts/load_fdga_to_postgres.py` carries
an explicit column list per table (`TABLES`), and the load fails loudly if the
CSV and the DDL disagree rather than silently loading a shifted row.

| CDM output | Postgres table | Grain | Rows |
|---|---|---|---|
| `manifest.csv` | `fdga.manifest` | source file set | 13 |
| `facts.csv` | `fdga.facts` | election × office × district × county × candidate | 32,181 |
| `contests.csv` | `fdga.contests` | election × office × district | 3,230 |
| `chamber_year.csv` | `fdga.chamber_year` | cycle × chamber | 39 |
| `statewide.csv` | `fdga.statewide` | cycle × statewide office | 23 |
| `corrections.csv` | `fdga.corrections` | correction | 7 |
| `name_merges.csv` | `fdga.name_merges` | merge | 34 |
| `validation.csv` | `fdga.validation` | check | 96 |
| `reconciliation.csv` | `fdga.reconciliation` | compared cell | 156 |

One name differs: the CSV column `check` becomes `check_name` in the DDL,
because `check` is reserved in SQL. The loader handles it via `_RENAMES`.

**What Postgres adds that the CDM does not have: the view layer.** Views reshape
and present; they never define. The rule that keeps this coherent:

> A business definition lives in `fdp/cdm/aggregate.py`, is tested by
> `tests/test_cdm.py`, surfaces as a view column, and is never re-implemented in
> a Metabase question, a Model, or a dashboard.

If a measure is missing, it gets added upstream and every consumer — Postgres,
Sheets, and the static apps — receives it. A calculation added only in Postgres
is a definition the Sheets add-on and the public maps cannot see.

## The three layers

```
  TABLES          facts  contests  chamber_year  statewide  + 5 audit tables
  (CDM image)         |         |            |          |
                      v         v            v          v
  CORE VIEWS      v_county_  v_contest  v_chamber_  v_statewide  v_voter_choice
  (semantic)       results                  year                 v_data_health
                      |         |            |          |
                      v         v            v          v
  DASHBOARD       v_100_voters        v_efficiency_gap    v_race_drilldown
  VIEWS           v_100_voters_long   v_which_party_...   v_county_splits
  (presentation)  v_contest_by_...    v_seat_vote_...     v_proportional_...
                  v_decided_before... v_partisan_pref...
```

**Core views** are the semantic contract: percentages scaled to percentage
points, display labels added, nothing aggregated away. Read these for ad-hoc
analysis and build Metabase Models on them.

**Dashboard views** are one per insight in `dashboard_insights.md`: fixed
shapes so a chart is a `SELECT` with a filter rather than pasted SQL that drifts
from the document. Do not build Models on these — they are already the right
shape.

Only two dashboard views reach past the core layer to a table:
`v_county_splits` and `v_proportional_allocation`, both because they need
something the core views do not expose (per-county district counts, and the
statewide baseline joined to chamber seat totals).

## Grain and keys

Every table declares its grain as a `UNIQUE` constraint, so a bad reload fails
loudly instead of double-counting.

| Table | Grain constraint |
|---|---|
| `manifest` | `PRIMARY KEY (source_id)` |
| `facts` | `UNIQUE (election_date, election_type, office, district, county, candidate_name, party)` |
| `contests` | `UNIQUE (cycle_year, election_type, office, district)` |
| `chamber_year` | `UNIQUE (cycle_year, chamber)` |
| `statewide` | `UNIQUE (cycle_year, office, election_type)` |

**`election_type` is part of the key for `facts`, `contests` and `statewide`,
and this is not decoration.** In 2020 Georgia held a regular U.S. Senate race
and the Loeffler/Warnock special election **on the same date**, 2020-11-03.
Without `election_type` the grain is not unique and the constraint fails on
load — which is how the requirement was discovered.

`facts.source_id` is a foreign key into `manifest`, which is why `manifest`
loads first.

## Type decisions that matter

**`district` is `text`, zero-padded (`'001'`).** Cast it to integer and the
padding is lost, silently breaking every join between `facts` and `contests`.
The loader forces it to stay text even though pandas would infer an integer.

**Seat columns are nullable, and NULL means unknown — never zero.** 2002 state
house carries NULL seats because multi-member districts make them non-derivable;
`votes_total` is still fully populated for that row. Do not add `NOT NULL`.

**Empty string is a value; NULL is absence.** Statewide races carry
`district = ''` because a statewide race genuinely has no district. 2002's seat
counts are NULL because they are unknown. `COPY` uses `\N` as the NULL marker
rather than the empty string, so the two stay distinct — using `NULL ''` turned
`district = ''` into NULL against a `NOT NULL` column.

**Nullable integers round-trip through pandas as float64**, so `74` becomes
`74.0` and `COPY` rejects it. The loader restores them via pandas' nullable
`Int64` before writing.

**`votes` carries `CHECK (votes >= 0)`.** A negative vote count is a parse
failure, not data.

## Load mechanics

```bash
export FDGA_DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/fdga
uv run --project ~/codebox/fgdp/fdp python \
  ~/codebox/fgdp/fdp/scripts/load_fdga_to_postgres.py
```

| Flag | Effect |
|---|---|
| `--dry-run` | report what would load, touch nothing |
| `--comments-only` | re-apply `postgres_comments.sql` alone |
| `--grant-read-only ROLE` | `GRANT SELECT` on the schema, plus default privileges |
| `--diagnose` | check connectivity and credentials |

The whole dataset is replaced inside **one transaction**: `TRUNCATE ... CASCADE`,
then `COPY` per table, then `COMMIT`. Readers see the old data until the commit
and the new data after — never a partial or empty state, and a failure rolls
back to the previous load intact.

The DDL is idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE VIEW`),
so re-running it is safe. The dashboard views are an exception: they are
`DROP`ped before creation, because `CREATE OR REPLACE VIEW` can append a column
but cannot rename or reorder one.

## Naming conventions

snake_case throughout, no quoted identifiers ever.

| Pattern | Meaning | Example |
|---|---|---|
| `<thing>` | the machine-readable code you filter on | `chamber = 'state_house'` |
| `<thing>_label` | the display form | `chamber_label = 'Georgia House'` |
| `*_pct` | **already scaled** to percentage points | `vote_share_r_pct = 55.0` |
| `pct_*` | the underlying 0–1 ratio, tables only | `pct_votes_r = 0.550` |

The affix flips with the scale, deliberately: `pct_x` is a ratio in a table,
`x_pct` is percentage points in a view. If you see both in one query you are
mixing layers.

**Filter and group on the code, not the label.** The code is stable; the label
is display text that a future edit can reword.

## Documentation and Metabase

All 296 columns carry `COMMENT ON`. Metabase reads these over JDBC as field
descriptions, which is why the comments are written as guidance rather than
restatements of the column name — they are what an analyst sees in the data
reference panel.

Two operational notes:

- Metabase only populates a description that is **currently empty**
  ([metabase#38694](https://github.com/metabase/metabase/issues/38694)). Apply
  comments before connecting the database, or clear the description in Metabase
  and re-sync.
- New views do not appear until you run **Admin → Databases → Sync database
  schema now**.

## Known gaps encoded in the schema

These are in the data, flagged rather than hidden. `fdga.validation` carries
them at severity `KNOWN`.

| Scope | Gap | How the schema flags it |
|---|---|---|
| 2002 state house | 147 multi-member districts elected 180 members; the source has no post identifier, so seat winners are not derivable | `chamber_year.seats_derivable = false`, seat columns NULL, carried onto `v_contest.seats_derivable` |
| 2002 state house | one voter could cast several state house votes, so chamber votes exceed top-of-ticket ballots | excluded from `v_100_voters` and `v_100_voters_long`, whose shares would otherwise sum to 131 |
| 2018 state house | districts 014 and 028 absent from the source | seats sum to 178, `districts_present = 178` |
| 2000 / 2004 state house | one-seat disagreements with the legacy workbook, possibly as-elected vs as-seated | `fdga.reconciliation`, status `DIFF` |

## Extending the model

**A new election cycle** needs one entry in `SOURCES` in `sources.py` and a
rebuild. No schema change: every derived table groups by `election_date`, so a
new cycle appends rows. This is the property the whole migration existed to buy —
the legacy workbook needed a new tab and a new set of hand-edited formulas per
election.

**A new measure** goes in `aggregate.py`, gains a test, becomes a column on the
relevant table, and surfaces through a view. Never add it as a view-only
calculation unless it is pure presentation (a label, a rescale, an unpivot).

**A new dashboard view** goes in the dashboard-views block of
`postgres_ddl.sql` with a `DROP VIEW IF EXISTS` line, gets `COMMENT ON` for
every column, and gets an entry in `dashboard_insights.md`. Carry both `chamber`
and `chamber_label`.

**Not yet built:** `dim_district`, the bridge that would let actual results join
to the GerryChain and ALARM ensemble counterfactuals. District numbers are
reused across map eras — HD-145 in 2022 is not the geography HD-145 was in
2020 — so any join on `(chamber, district)` without an era qualifier is silently
wrong. See `dashboard_insights.md`, "Not yet buildable".

<!-- BEGIN GENERATED REFERENCE — everything below is rewritten by
     scripts/gen_postgres_data_model.py. Edit the narrative above instead. -->

---

# Table reference

## `fdga.chamber_year`

Seats versus votes, one row per election cycle and chamber. 39 rows.  The headline table: it replaces the Summary and Percentages tabs of the legacy "Ga Gen Assembly Analysis" workbook, which used 75,668 formulas to produce roughly these numbers.  seats_votes_gap_r is the measure the whole analysis exists to show.  Seat columns are NULL for 2002 state house, where multi-member districts make seats non-derivable. NULL there means unknown, never zero — check seats_derivable before charting seat counts.

**Rows:** 39 · **Size:** 32 kB · **Columns:** 24

**Constraints**

- `chamber_year_grain` — `UNIQUE (cycle_year, chamber)`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | no | Election cycle, e.g. 2024. |
| `chamber` | text | no | us_house, state_senate or state_house. |
| `seats_total_expected` | integer | yes | Seats the chamber holds for this cycle: 180 state house, 56 state senate, and 11 to 14 congressional depending on apportionment (Georgia gained a 14th seat in 2012). |
| `districts_present` | integer | yes | Districts actually found in the source. Below seats_total_expected means a source gap — 2018 state house is missing districts 014 and 028. |
| `seats_derivable` | boolean | no | FALSE when seats cannot be attributed from district results alone, in which case every seat column is NULL. Only 2002 state house: Georgia's 2001 plan used multi-member districts (147 districts electing 180 members) and the source carries no post identifier. Vote columns are still valid for that row. |
| `seats_r` | integer | yes | Seats won by Republicans. NULL where seats_derivable is FALSE. |
| `seats_d` | integer | yes | Seats won by Democrats. NULL where seats_derivable is FALSE. |
| `seats_other` | integer | yes | Seats won by any other party or by an independent. |
| `pct_seats_r` | double precision | yes | Republican share of seats, 0-1. Multiply by 100 for a percentage, or use fdga.v_chamber_year which has done it. |
| `pct_seats_d` | double precision | yes | Democratic share of seats, 0-1. |
| `races_total` | integer | no | Races on the ballot for this chamber and cycle. |
| `races_uncontested` | integer | no | Races with nobody else on the ballot, write-ins ignored. See fdga.contests.is_uncontested for the definition. |
| `races_contested` | integer | no | races_total minus races_uncontested. |
| `races_competitive` | integer | no | Races where the winner took 53.5% or less. Uncontested races are never counted as competitive. |
| `races_uncontested_major` | integer | yes | Races with no major-party opponent — the broader definition, which also counts a race whose only opposition was a minor party. |
| `pct_uncontested` | double precision | yes | Share of races uncontested, 0-1. A rising line here is the clearest single indicator of a chamber becoming less competitive. |
| `pct_competitive` | double precision | yes | Share of races competitive, 0-1. |
| `votes_total` | bigint | no | All votes cast across the chamber. Valid even where seats are not derivable. |
| `votes_r` | bigint | no | Votes for Republican candidates across the chamber. |
| `votes_d` | bigint | no | Votes for Democratic candidates across the chamber. |
| `votes_other` | bigint | no | Votes for all other candidates across the chamber. |
| `pct_votes_r` | double precision | yes | Republican share of all votes cast in the chamber, 0-1. Note that uncontested races inflate the winning party's share, since the other party has no candidate to vote for — compare with fdga.statewide for a cleaner partisan baseline. |
| `pct_votes_d` | double precision | yes | Democratic share of all votes cast in the chamber, 0-1. Same uncontested-race caveat as pct_votes_r. |
| `seats_votes_gap_r` | double precision | yes | pct_seats_r minus pct_votes_r, as a 0-1 ratio. Positive means Republicans held a larger share of seats than of votes; negative means the reverse. This is the headline gerrymandering measure. Georgia's state house ran -10.6% in 2000 and +0.6% in 2024. NULL where seats are not derivable. |

## `fdga.contests`

One row per race: election x office x district, with the outcome.  Mechanical properties (winner, margin, totals) are derived directly. The two policy flags — is_uncontested and is_competitive — encode decisions that are documented on their own columns; both alternatives are provided so you can choose rather than re-derive.  Includes statewide races (district = ''); fdga.v_contest filters those out.

**Rows:** 3,230 · **Size:** 864 kB · **Columns:** 27

**Constraints**

- `contests_grain` — `UNIQUE (cycle_year, election_type, office, district)`

**Indexes**

- `contests_office_idx` — `btree (office, cycle_year)`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | no | Election cycle, e.g. 2024. |
| `election_date` | date | no | Date of the election. |
| `election_type` | text | no | general, runoff or special. Part of the key — 2020 held two U.S. Senate races on the same date. |
| `office` | text | no | Normalized office: us_house, state_senate, state_house, president, us_senate, governor. |
| `district` | text | no | Zero-padded district number as text, e.g. 001. Empty string for statewide races. |
| `candidate_count` | integer | no | Number of candidates on the ballot, including write-ins. |
| `party_count` | integer | no | Number of distinct parties contesting. |
| `winner_party` | text | yes | Party of the candidate with the most votes. |
| `winner_name` | text | yes | Candidate with the most votes. Determined from the vote counts, not from a certified result, so a race decided by a later runoff shows the November leader. |
| `winner_votes` | bigint | yes | Votes for the leading candidate. |
| `winner_share` | double precision | yes | Leading candidate votes divided by total votes, as a 0-1 ratio. 0.535 means 53.5%. |
| `runner_up_party` | text | yes | Party of the second-placed candidate; empty when the race had only one candidate. |
| `runner_up_votes` | bigint | yes | Votes for the second-placed candidate; 0 when unopposed. |
| `margin` | bigint | yes | Winner votes minus runner-up votes, in whole votes. |
| `margin_share` | double precision | yes | Margin as a share of total votes, 0-1. Useful for "close race" filters — under 0.05 is a 5-point race. |
| `votes_total` | bigint | no | All votes cast in this race, every party and write-ins included. |
| `votes_r` | bigint | no | Votes for Republican candidates in this race. |
| `votes_d` | bigint | no | Votes for Democratic candidates in this race. |
| `votes_other` | bigint | no | Votes for everyone else: Libertarian, Green, Independent, write-in, other. |
| `counties` | integer | yes | Number of counties this district drew votes from. Legislative districts do not nest in counties, so this is often greater than 1. |
| `is_uncontested` | boolean | no | TRUE when nobody else was on the ballot, ignoring write-ins. This is the legacy workbook rule and the default. Write-ins are excluded deliberately: in 2008 CD-5 John Lewis drew 231,368 votes against two write-ins totalling 93, which no reading of "contested" should count. |
| `is_uncontested_major` | boolean | no | TRUE when there was no MAJOR-PARTY opponent — a Republican facing only a Libertarian counts here. Broader than is_uncontested, and arguably the better measure of an uncompetitive seat. The two differ in 30-40 races across the 13 cycles. |
| `is_competitive` | boolean | no | TRUE when the race was contested and the winner took 53.5% or less. 53.5% matches the legacy workbook Competitive_Limit. For a different threshold use one of the is_competitive_* columns rather than recomputing. |
| `is_competitive_052` | boolean | yes | Competitive at a 52% threshold — winner took 52.0% or less. |
| `is_competitive_0535` | boolean | yes | Competitive at a 53.5% threshold. Identical to is_competitive; present so all four thresholds read alike. |
| `is_competitive_055` | boolean | yes | Competitive at a 55% threshold — winner took 55.0% or less. |
| `is_competitive_06` | boolean | yes | Competitive at a 60% threshold — winner took 60.0% or less. |

## `fdga.corrections`

Documented fixes applied to confirmed errors in the source data, with the evidence for each.  Every correction was verified against the legacy workbook, whose vote counts match the source exactly — only the labels differ. The dominant upstream error is OpenElections reading the "(I)" incumbency marker in a candidate name as the party "Independent".  A row with status NO_MATCH means the correction no longer matches any source row, usually because the upstream data was fixed; that entry should be retired.

**Rows:** 7 · **Size:** 16 kB · **Columns:** 4

| Column | Type | Null | Description |
|---|---|---|---|
| `correction` | text | yes | Short label: cycle/office/target and what changed. |
| `rows_matched` | integer | yes | How many fact rows this correction touched on the most recent build. |
| `status` | text | yes | APPLIED when the correction matched rows; NO_MATCH when it matched none, which usually means the upstream source was fixed and this entry can be retired. |
| `evidence` | text | yes | Why this correction is justified, and against what independent source it was verified. A correction without evidence would be a guess. |

## `fdga.facts`

Vote counts at county x contest x candidate grain — the fact table.  Carries only what the source states: no derived flags, no thresholds, no judgments. Anything requiring a policy decision (what counts as competitive, what counts as uncontested) is computed in fdga.contests and fdga.chamber_year, so the rule lives in one place.  Note that legislative districts do NOT nest inside counties. A district spanning four counties has four rows per candidate. To get a district total, sum over county — or use fdga.contests, which has already done it.

**Rows:** 32,181 · **Size:** 7544 kB · **Columns:** 12

**Constraints**

- `facts_grain` — `UNIQUE (election_date, election_type, office, district, county, candidate_name, party)`
- `facts_source_id_fkey` — `FOREIGN KEY (source_id) REFERENCES fdga.manifest(source_id)`
- `facts_votes_check` — `CHECK ((votes >= 0))`

**Indexes**

- `facts_county_idx` — `btree (county)`
- `facts_cycle_office_district_idx` — `btree (cycle_year, office, district)`
- `facts_party_idx` — `btree (party)`

| Column | Type | Null | Description |
|---|---|---|---|
| `election_date` | date | no | Date of the election, e.g. 2024-11-05. |
| `cycle_year` | integer | no | Election cycle, e.g. 2024. Use this for grouping rather than extracting the year from election_date. |
| `election_type` | text | no | general, runoff or special. Part of the key: in 2020 the regular U.S. Senate race and the Loeffler/Warnock special were both held on 2020-11-03. |
| `office` | text | no | Normalized office: us_house, state_senate, state_house, president, us_senate, governor. Source spellings vary by cycle ("State House" vs "State Representative") and are normalized on load. |
| `district` | text | no | Zero-padded district number as text, e.g. 001. Empty string for statewide offices — an empty string means "not applicable", it is never NULL. Deliberately text: casting to integer loses the padding and breaks joins to fdga.contests. |
| `county` | text | no | Georgia county name in title case. "Unknown" holds votes the source could not attribute to a county (11 write-in rows in 2006). |
| `candidate_name` | text | no | Candidate name as printed by the source, whitespace normalized. Spelling variants of the same person within one contest have been merged — see fdga.name_merges. |
| `party_raw` | text | yes | Party string exactly as the source wrote it, kept for audit. Values vary wildly by cycle: Republican, REP, R, and a stray-paren artifact "(REP" all appear. |
| `party` | text | no | Normalized party: R Republican, D Democratic, L Libertarian, G Green, I Independent, W Write-In, N Nonpartisan, O Other. |
| `votes` | bigint | no | Votes cast for this candidate in this county for this contest. Never negative. |
| `source_id` | text | no | Which source file set produced this row. Join to fdga.manifest for provenance and checksum. |
| `source_row` | bigint | yes | Row index within the source file, for tracing a value back to its origin line. |

## `fdga.manifest`

One row per source file set — the provenance record for every load.  Answers "where did this number come from": which upstream file, fetched when, how many rows it held, and the checksum of the bytes that produced it. fdga.facts.source_id is a foreign key into this table.

**Rows:** 13 · **Size:** 32 kB · **Columns:** 19

**Constraints**

- `manifest_pkey` — `PRIMARY KEY (source_id)`

| Column | Type | Null | Description |
|---|---|---|---|
| `source_id` | text | no | Stable identifier for one source file set, e.g. oe_ga_20241105_general. Referenced by fdga.facts.source_id. |
| `cycle_year` | integer | no | Election cycle this source belongs to, e.g. 2024. |
| `election_date` | date | no | Date of the election, e.g. 2024-11-05. |
| `election_type` | text | no | general, runoff or special. |
| `grain_published` | text | yes | Geographic grain of the rows as the upstream source published them (county or precinct). Precinct sources are summed to county during load, so all facts are county grain regardless. |
| `files_read` | integer | yes | Number of source files combined. Usually 1; the 2018 general was published as 159 separate per-county files. |
| `rows_in` | bigint | yes | Rows read from the source before any filtering. |
| `rows_out` | bigint | yes | Rows written to fdga.facts after out-of-scope offices were dropped and precincts summed to county. |
| `votes_total` | bigint | yes | Sum of all votes loaded from this source, across every office in scope. |
| `dropped_out_of_scope` | bigint | yes | Rows discarded because the office is outside the analysis: ballot questions, District Attorney, PSC, Attorney General, Lieutenant Governor and similar. Expected to be large. |
| `dropped_no_county` | bigint | yes | Rows discarded for having no usable county. Should be 0; anything else warrants a look. |
| `dropped_bad_votes` | bigint | yes | Rows discarded because the vote count could not be parsed as a number. Should be 0. |
| `dropped_no_district` | bigint | yes | Rows discarded because a districted office carried no district number. Should be 0. |
| `offices_kept` | text | yes | Comma-separated list of normalized offices retained from this source. |
| `reports_incumbency` | boolean | yes | TRUE if the source marks incumbents at all (an "(I)" in the candidate name). FALSE means the source is silent on incumbency, not that there were no incumbents. |
| `unmapped_parties` | text | yes | Raw party strings that fell through to the "O" (Other) bucket, with counts. Non-empty means a party label appeared that the normalizer does not recognize. |
| `sha256` | text | yes | Truncated SHA-256 of the source file bytes. Lets you prove which upstream data produced a given load, and detect a source that changed underneath you. |
| `note` | text | yes | Free-text note about this source vintage, e.g. known format quirks. |
| `built_at` | timestamp with time zone | yes | UTC timestamp of the build that produced this load. |

## `fdga.name_merges`

Candidate spelling variants that were merged into one candidate.  Several sources spell the same candidate differently BY COUNTY, splitting one person''s vote across multiple rows and corrupting every derived share. Hank Johnson appears four ways in the 2012 CD-4 data; Lynn Westmoreland twice in CD-3, which is why the legacy workbook records him unopposed at 100% while the raw data showed 85.7%.  Merges are conservative: same election, office, district, party AND surname.

**Rows:** 34 · **Size:** 16 kB · **Columns:** 7

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle in which the merge happened. |
| `office` | text | yes | Normalized office of the affected contest. |
| `district` | text | yes | District of the affected contest. |
| `party` | text | yes | Party of the merged candidate. Merges never cross party lines. |
| `merged_from` | text | yes | The variant spelling that was replaced. |
| `merged_into` | text | yes | The canonical spelling kept — the variant carrying the most votes. |
| `votes_moved` | bigint | yes | Votes reassigned from the variant spelling to the canonical one. |

## `fdga.reconciliation`

Cell-by-cell agreement with the legacy "Ga Gen Assembly Analysis" workbook — the acceptance test for the migration.  139 of 156 compared cells match. Every remaining difference is 2 units or less and traceable: 2002 multi-member districts, the 2018 source gap, threshold boundary cases, and three unresolved single-seat disagreements in 2000 and 2004 that may reflect as-elected versus as-seated counting.  A difference here is not automatically a defect in this data — the workbook has a documented history of copy-paste errors, several of which this pipeline found and corrected.

**Rows:** 156 · **Size:** 24 kB · **Columns:** 7

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle compared. |
| `chamber` | text | yes | Chamber compared. |
| `field` | text | yes | Which measure was compared: seats_r, seats_d, races_uncontested or races_competitive. |
| `cdm` | integer | yes | Value produced by this pipeline. |
| `workbook` | integer | yes | Value published by the legacy Excel workbook. |
| `delta` | integer | yes | cdm minus workbook. NULL where one side has no value. |
| `status` | text | yes | MATCH identical. DIFF they disagree. CDM_NULL this pipeline cannot derive the value, with the reason in fdga.validation. BOOK_NULL the workbook has no value. |

## `fdga.statewide`

Statewide race results: president, governor and U.S. Senate. 23 rows.  The partisan baseline that chamber seat shares are measured against. Because every voter in the state can vote in these races, they give a cleaner read on statewide partisan lean than chamber vote totals, which are distorted by uncontested seats.

**Rows:** 23 · **Size:** 32 kB · **Columns:** 13

**Constraints**

- `statewide_grain` — `UNIQUE (cycle_year, office, election_type)`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | no | Election cycle, e.g. 2024. |
| `election_date` | date | no | Date of the election. |
| `election_type` | text | no | general, runoff or special. Part of the key: 2020 held both a regular and a special U.S. Senate race. |
| `office` | text | no | president, governor or us_senate. |
| `winner_party` | text | yes | Party of the leading candidate. |
| `winner_name` | text | yes | Leading candidate by vote count. |
| `winner_share` | double precision | yes | Leading candidate share of total votes, 0-1. |
| `votes_total` | bigint | yes | All votes cast in this race. |
| `votes_r` | bigint | yes | Votes for the Republican candidate. |
| `votes_d` | bigint | yes | Votes for the Democratic candidate. |
| `votes_other` | bigint | yes | Votes for all other candidates. |
| `pct_votes_r` | double precision | yes | Republican share of all votes cast, 0-1. |
| `pct_votes_d` | double precision | yes | Democratic share of all votes cast, 0-1. |

## `fdga.validation`

Contract-test results from the most recent build. One row per check.  The legacy workbook had no automated checks — its Ballotpedia check tab was done by hand, once, in 2019, and the 2024 check was never done. Three separate audits over six years each found a hardcoded value that had silently replaced a formula. These checks are the replacement, and they run on every build.  If failing_checks in fdga.v_data_health is above zero, do not trust the load.

**Rows:** 96 · **Size:** 24 kB · **Columns:** 4

| Column | Type | Null | Description |
|---|---|---|---|
| `check_name` | text | yes | Which check ran: district_coverage, county_coverage, party_domain, votes_sane, grain_unique, contest_has_votes, votes_reconcile, seat_totals. |
| `severity` | text | yes | FAIL a real defect, do not publish. WARN worth a look, not blocking. KNOWN a documented source limitation with a recorded reason. PASS the check succeeded. |
| `scope` | text | yes | What the check covered, e.g. 2018/state_house or all. |
| `detail` | text | yes | Human-readable result, including the documented reason for anything marked KNOWN. |

---

# View reference

## `fdga.v_100_voters`

Insight 1.1 — what happened to 100 typical Georgians, by chamber. The four shares sum to 100 by construction. 2002 state house is excluded: multi-member districts let one voter cast several state house votes, so its shares sum to 131.

**Columns:** 8 · **Reads:** `v_voter_choice`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `ballots_cast` | bigint | yes | The denominator: votes in the cycle's highest-turnout statewide race. NOT turnout, and not this chamber's votes. |
| `had_a_real_race` | numeric | yes | Of 100 voters, how many voted in a competitive race. Counts votes cast in competitive districts, including votes for the loser — not a claim that an individual vote was decisive. |
| `race_already_decided` | numeric | yes | Of 100 voters, how many voted in a race with two or more candidates that the winner took by more than the competitive threshold. |
| `only_one_name` | numeric | yes | Of 100 voters, how many found a single candidate printed on the ballot. The most robust number here — no threshold, no model. |
| `skipped_the_race` | numeric | yes | Of 100 voters, how many cast a ballot but no vote in this chamber. A residual between two totals, not a headcount — do not attribute motive. |

## `fdga.v_100_voters_long`

Insight 1.1 long-form — one row per cycle, chamber and category, for stacked bars and any chart needing a series dimension. v_100_voters is the wide equivalent for tables and big-number cards. Same four buckets, same exclusion of 2002 state house.

**Columns:** 9 · **Reads:** `v_voter_choice`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle (even years, 2000-2024). |
| `chamber` | text | yes | us_house \| state_senate \| state_house. Filter and group on this, not on chamber_label. |
| `chamber_label` | text | yes | Display form of chamber: U.S. House, Georgia Senate, Georgia House. |
| `ballots_cast` | bigint | yes | The denominator: votes in the cycle's highest-turnout statewide race. NOT turnout, and not this chamber's votes. |
| `sort_order` | integer | yes | Narrative order 1-4, best case to worst. Sort on this: an alphabetical category axis renders the story backwards. |
| `category` | text | yes | Had a real race \| Race already decided \| Only one name \| Skipped the race. Mutually exclusive and exhaustive, so the four rows sum to ballots_cast. |
| `votes` | numeric | yes | Raw votes in this bucket. The four rows of a chamber-year sum to ballots_cast. |
| `voters_per_100` | numeric | yes | Whole voters out of 100 — the village framing. Rounded, so the four rows can sum to 99 or 101; never print the total as a computed figure. |
| `pct` | numeric | yes | Same share to one decimal place, for charts where the rounding to whole voters is too coarse. |

## `fdga.v_chamber_year`

Seats versus votes by cycle and chamber — start here.  Percentages are already percentages (55.0, not 0.55) and chamber names are readable, so a Metabase model needs no transformation on top.  Seat columns are NULL for 2002 state house, where multi-member districts make seats non-derivable. Treat NULL as unknown, never as zero.

**Columns:** 21 · **Reads:** `chamber_year`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `seats_r` | integer | yes | Seats won by Republicans. NULL for 2002 Georgia House, where multi-member districts make seats non-derivable — NULL means unknown, not zero. |
| `seats_d` | integer | yes | Seats won by Democrats. NULL for 2002 Georgia House — see seats_r. |
| `seats_other` | integer | yes | Seats won by any other party or by an independent. |
| `seat_share_r_pct` | numeric | yes | Republican share of seats in percentage points (55.6 means 55.6%). |
| `seat_share_d_pct` | numeric | yes | Democratic share of seats in percentage points. |
| `vote_share_r_pct` | numeric | yes | Republican share of all votes cast in the chamber, in percentage points. Uncontested seats inflate this — compare with v_statewide for a cleaner partisan baseline. |
| `vote_share_d_pct` | numeric | yes | Democratic share of all votes cast in the chamber, in percentage points. Same uncontested-race caveat as the Republican figure. |
| `seats_votes_gap_r_pct` | numeric | yes | Seat share minus vote share for Republicans, in percentage points. Positive means the party held more seats than its vote share alone implies. The headline gerrymandering measure: Georgia's state house ran -10.6 in 2000 and +0.6 in 2024. |
| `races_total` | integer | yes | Races on the ballot for this chamber and cycle. |
| `races_uncontested` | integer | yes | Races with nobody else on the ballot, write-ins ignored. |
| `races_contested` | integer | yes | races_total minus races_uncontested. |
| `races_competitive` | integer | yes | Races where the winner took 53.5% or less. Uncontested races never count as competitive. |
| `uncontested_pct` | numeric | yes | Share of races uncontested, in percentage points. A rising line is the clearest single indicator of a chamber becoming less competitive. |
| `competitive_pct` | numeric | yes | Share of races competitive, in percentage points. |
| `votes_total` | bigint | yes | All votes cast across the chamber. Valid even where seats are not derivable. |
| `votes_r` | bigint | yes | Votes for Republican candidates across the chamber. |
| `votes_d` | bigint | yes | Votes for Democratic candidates across the chamber. |
| `seats_derivable` | boolean | yes | FALSE when seat counts cannot be attributed and the seat columns are NULL. Only 2002 Georgia House. Filter this out before charting seats. |

## `fdga.v_contest`

One row per legislative or congressional race, with friendly labels.  Statewide races are excluded — see fdga.v_statewide for those.  "Uncontested" ignores write-ins. For the broader "no major-party opponent" reading use is_uncontested_major. For a competitiveness threshold other than 53.5%, use one of the is_competitive_* columns rather than recomputing.

**Columns:** 25 · **Reads:** `chamber_year`, `contests`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display. |
| `district` | text | yes | Zero-padded district number, e.g. 001. District numbering is only meaningful within a redistricting era — district 145 in 2022 is not the same geography as district 145 in 2020. |
| `winner_name` | text | yes | Candidate with the most votes. Derived from vote counts, so a race later decided by a runoff shows the November leader. |
| `winner_party` | text | yes | R Republican, D Democratic, or another party code. |
| `winner_share_pct` | numeric | yes | Winner votes as a share of all votes cast in the race, in percentage points. |
| `margin_pct` | numeric | yes | Winner minus runner-up as a share of all votes cast, in percentage points. Under 5 is a close race. |
| `margin` | bigint | yes | Winner votes minus runner-up votes, in whole votes. |
| `votes_total` | bigint | yes | All votes cast in this race, every party and write-ins included. |
| `votes_r` | bigint | yes | Votes for Republican candidates in this race. |
| `votes_d` | bigint | yes | Votes for Democratic candidates in this race. |
| `votes_other` | bigint | yes | Votes for everyone else: Libertarian, Green, Independent, write-in, other. |
| `candidate_count` | integer | yes | Number of candidates on the ballot, write-ins included. |
| `is_uncontested` | boolean | yes | TRUE when nobody else was on the ballot, write-ins ignored. In 2008 CD-5 John Lewis drew 231,368 votes against two write-ins totalling 93 — that counts as uncontested. |
| `is_uncontested_major` | boolean | yes | TRUE when there was no major-party opponent — a Republican facing only a Libertarian counts here. Broader than is_uncontested, and arguably the better measure of an uncompetitive seat. |
| `is_competitive` | boolean | yes | TRUE when the race was contested and the winner took 53.5% or less. |
| `is_competitive_052` | boolean | yes | Competitive at a 52% threshold. Use instead of recomputing from winner_share_pct. |
| `is_competitive_0535` | boolean | yes | Competitive at a 53.5% threshold — the default, identical to is_competitive. |
| `is_competitive_055` | boolean | yes | Competitive at a 55% threshold. |
| `is_competitive_06` | boolean | yes | Competitive at a 60% threshold. |
| `votes_two_party` | bigint | yes | Republican plus Democratic votes. The denominator for the efficiency gap — third parties are excluded by construction. |
| `wasted_votes_r` | numeric | yes | Republican votes that elected nobody: all of them if the Republican lost, or the surplus above half the two-party vote if they won. Sum this to build an efficiency gap without re-typing CASE logic into a Metabase expression. Meaningless in uncontested races — filter on is_uncontested first. |
| `wasted_votes_d` | numeric | yes | Democratic votes that elected nobody, defined as for wasted_votes_r. Efficiency gap toward Republicans = (sum(wasted_votes_d) - sum(wasted_votes_r)) / sum(votes_two_party). |
| `seats_derivable` | boolean | yes | FALSE where seats cannot be attributed from district results — 2002 state house only, whose 147 multi-member districts elected 180 members. Carried down from chamber_year so seat-share metrics can exclude it without hard-coding a year. |

## `fdga.v_contest_by_category`

Insight 1.3 — races split into uncontested / contested-but-not-competitive / competitive, long-form for a stacked bar.

**Columns:** 6 · **Reads:** `v_chamber_year`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `category` | text | yes | Uncontested \| Contested, not competitive \| Competitive. Mutually exclusive and exhaustive. |
| `races` | integer | yes | Number of races in this category. |
| `pct_of_total` | numeric | yes | Share of that chamber-year's races, percentage points. |

## `fdga.v_county_results`

County-level detail, one row per county, office, district and candidate.  Legislative districts do NOT nest inside counties: a district spanning four counties has four rows per candidate. Sum over county to get a district total, or use fdga.v_contest, which has already done it.

**Columns:** 8 · **Reads:** `facts`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. |
| `county` | text | yes | Georgia county name. "Unknown" holds votes the source could not attribute to a county. |
| `office` | text | yes | Office code you filter on, including statewide offices: us_house, state_senate, state_house, president, governor, us_senate. |
| `office_label` | text | yes | Readable office name for display. |
| `district` | text | yes | Zero-padded district number; empty string for statewide offices. |
| `candidate_name` | text | yes | Candidate name as printed by the source. Spelling variants of one person have been merged — see fdga.name_merges. |
| `party` | text | yes | R Republican, D Democratic, L Libertarian, G Green, I Independent, W Write-In, N Nonpartisan, O Other. |
| `votes` | bigint | yes | Votes for this candidate in this county for this race. Legislative districts do not nest in counties, so a district spanning four counties has four rows per candidate — sum over county for a district total. |

## `fdga.v_county_splits`

Insight 2.5 — counties reporting votes in more than one district. A reported-results proxy for the boundary, not the boundary itself; treat as directional. Georgia has 159 counties. County splitting is not evidence of gerrymandering on its own — population equality requires some of it.

**Columns:** 5 · **Reads:** `facts`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `counties_split` | bigint | yes | Counties that reported votes in two or more districts of this chamber. |
| `counties_reporting` | bigint | yes | Counties reporting any vote in this chamber — the denominator. |

## `fdga.v_data_health`

One row summarising whether this load can be trusted. Worth a dashboard card.  failing_checks above zero means do not trust the data. known_gaps are documented source limitations, not defects — currently 4, covering 2002 multi-member districts and two districts missing from the 2018 source.

**Columns:** 11 · **Reads:** `corrections`, `manifest`, `name_merges`, `reconciliation`, `validation`

| Column | Type | Null | Description |
|---|---|---|---|
| `failing_checks` | bigint | yes | Contract tests that failed. Anything above zero means the load should not be published. |
| `warnings` | bigint | yes | Non-blocking issues worth a look. |
| `known_gaps` | bigint | yes | Documented source limitations with a recorded reason — expected, not defects. |
| `passing_checks` | bigint | yes | Contract tests that passed. |
| `corrections_applied` | bigint | yes | Documented source corrections applied on this build. See fdga.corrections for the evidence behind each. |
| `name_variants_merged` | bigint | yes | Candidate spelling variants merged into a single candidate. See fdga.name_merges. |
| `workbook_cells_matching` | bigint | yes | Cells agreeing with the legacy Excel workbook. |
| `workbook_cells_compared` | bigint | yes | Cells compared against the legacy workbook in total. |
| `last_built_at` | timestamp with time zone | yes | UTC timestamp of the build behind this load. If this is stale, re-run build_fdga_cdm.py and reload. |
| `total_votes_loaded` | numeric | yes | Sum of all votes across every source, as a coarse completeness check. |
| `legacy_workbook_agreement` | text | yes | Cells matching the legacy workbook Summary tab, as "matching / compared". Every remaining difference is at most 2 units and categorised. |

## `fdga.v_decided_before_election`

Insight 1.4 — how many voters, not races, were in a foregone conclusion. Grain is (cycle_year, chamber): without cycle_year this pools 13 cycles and reports 1,516 uncontested Georgia House races instead of 2024's 90.

**Columns:** 9 · **Reads:** `v_contest`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `uncontested` | bigint | yes | Races with a single candidate printed on the ballot, write-ins ignored. |
| `won_by_20_plus` | bigint | yes | Contested races the winner took by 20 points or more. |
| `actual_race` | bigint | yes | Contested races decided by less than 20 points. In 2024 this was 1 of 14 U.S. House races. |
| `votes_predecided` | numeric | yes | Votes cast in races that were uncontested or won by 20+. |
| `votes_total` | numeric | yes | All votes cast across the chamber. Valid even where seats are not derivable. |
| `predecided_pct` | numeric | yes | votes_predecided as a share of the chamber's votes. 93.9% for the 2024 U.S. House. |

## `fdga.v_efficiency_gap`

Insight 3.1 — the standard academic measure of partisan advantage. Reads the wasted-vote columns on v_contest rather than repeating the CASE logic. Positive favours Republicans. Check uncontested_races before quoting: the measure is badly distorted when seats go uncontested.

**Columns:** 8 · **Reads:** `v_contest`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `wasted_r_pct` | numeric | yes | Republican wasted votes as a share of the two-party vote. Roughly half of all votes are wasted by construction — the finding is whose. |
| `wasted_d_pct` | numeric | yes | Democratic wasted votes as a share of the two-party vote. |
| `efficiency_gap_r_pct` | numeric | yes | wasted_d_pct minus wasted_r_pct. The 7% sometimes cited as a presumptive gerrymander was the plaintiffs' proposed standard in Gill v. Whitford; the Supreme Court never adopted it. Cite as a scholarly benchmark, never a legal test. |
| `races` | bigint | yes | Number of races in this category. |
| `uncontested_races` | bigint | yes | Carried deliberately: read the gap only when this is low. The 2024 Georgia House scores -0.2 with 90 uncontested races, which means "not measurable", not "fair". |

## `fdga.v_partisan_preference_baseline`

Insight 2.2 — statewide vote share by party, long-form. The referee for every chamber-level claim: uncontested districts cannot skew it, because every voter votes in a statewide race.

**Columns:** 6 · **Reads:** `v_statewide`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `office` | text | yes | Office code you filter on: president, governor or us_senate. |
| `office_label` | text | yes | Readable office name for display. |
| `election_type` | text | yes | general, runoff or special. 2020 held both a regular and a special U.S. Senate race, so this distinguishes them. |
| `party` | text | yes | Republican \| Democratic. Long-form so one series column drives the chart. |
| `pct` | numeric | yes | That party's share of all votes in the statewide race, percentage points. |

## `fdga.v_proportional_allocation`

Insight 2.3 — seats a party would hold if seats tracked votes, against two benchmarks. Proportionality is a communication device for the size of a gap, NOT a legal standard: Rucho v. Common Cause (2019) closed the federal courts to partisan gerrymandering claims entirely.

**Columns:** 12 · **Reads:** `statewide`, `v_chamber_year`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `seats_r` | integer | yes | Seats won by Republicans. NULL for 2002 Georgia House, where multi-member districts make seats non-derivable — NULL means unknown, not zero. |
| `seats_d` | integer | yes | Seats won by Democrats. NULL for 2002 Georgia House — see seats_r. |
| `seats_total` | integer | yes | Seats actually filled, including any won by neither major party. |
| `baseline_office` | text | yes | The statewide race used as the down-ballot benchmark — the cycle's highest-turnout race. |
| `statewide_r_share_pct` | numeric | yes | Republican share of the two-party vote in that statewide race, percentage points. |
| `seats_r_proportional_chamber` | numeric | yes | Seats implied by the chamber's OWN two-party vote. Distorted wherever seats go uncontested, because an unopposed winner contributes 100% to one party. |
| `r_seat_bonus_chamber` | numeric | yes | Actual Republican seats minus seats_r_proportional_chamber. Understates the gap in chambers with many uncontested races. |
| `seats_r_proportional_statewide` | numeric | yes | Seats implied by the statewide baseline, which no district line can skew. Assumes voters split the same way down-ballot — split-ticket cycles like 2000 show they do not always. |
| `r_seat_bonus_statewide` | numeric | yes | Actual Republican seats minus seats_r_proportional_statewide. Where a chamber has no uncontested races the two bonus columns agree (U.S. House 2020-2024); where half the seats go uncontested they diverge sharply (Georgia House 2024: +1 chamber, +8 statewide). That divergence is a diagnostic, not a contradiction. |

## `fdga.v_race_drilldown`

Insight 3.4 — every race, the click-through target for the charts above. cycle_year and chamber are part of the output by necessity: without them the view returns 3,207 undifferentiated rows and district 001 appears 39 times.

**Columns:** 10 · **Reads:** `v_contest`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `district` | text | yes | Zero-padded district number, e.g. 001. District numbering is only meaningful within a redistricting era — district 145 in 2022 is not the same geography as district 145 in 2020. |
| `winner_name` | text | yes | Candidate with the most votes. Derived from vote counts, so a race later decided by a runoff shows the November leader. |
| `winner_party` | text | yes | R Republican, D Democratic, or another party code. |
| `winner_share_pct` | numeric | yes | Winner votes as a share of all votes cast in the race, in percentage points. |
| `margin_pct` | numeric | yes | Winner minus runner-up as a share of all votes cast, in percentage points. Under 5 is a close race. |
| `votes_total` | bigint | yes | All votes cast across the chamber. Valid even where seats are not derivable. |
| `category` | text | yes | Uncontested \| Competitive \| Not competitive. |

## `fdga.v_seat_vote_inversions`

Insight 3.3 — cycles where the party with more votes won fewer seats. Four rows across 13 cycles; three favour Democrats (2000-2002), one favours Republicans (2008 U.S. House). Publish all of them.

**Columns:** 7 · **Reads:** `v_chamber_year`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `vote_share_r_pct` | numeric | yes | Republican share of all votes cast in the chamber, in percentage points. Uncontested seats inflate this — compare with v_statewide for a cleaner partisan baseline. |
| `seats_r` | integer | yes | Seats won by Republicans. NULL for 2002 Georgia House, where multi-member districts make seats non-derivable — NULL means unknown, not zero. |
| `seats_d` | integer | yes | Seats won by Democrats. NULL for 2002 Georgia House — see seats_r. |
| `inversion` | text | yes | Which party won more votes but fewer seats. The 2000 and 2002 rows rest on chamber vote share in cycles with over half the seats uncontested — say "inversions in both directions", not "party X stole seats". |

## `fdga.v_statewide`

Statewide race vote shares by cycle — president, governor and U.S. Senate.  The partisan baseline that chamber seat shares are measured against. Cleaner than chamber vote totals, which uncontested seats distort.

**Columns:** 12 · **Reads:** `statewide`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. |
| `office` | text | yes | Office code you filter on: president, governor or us_senate. |
| `office_label` | text | yes | Readable office name for display. |
| `election_type` | text | yes | general, runoff or special. 2020 held both a regular and a special U.S. Senate race, so this distinguishes them. |
| `winner_name` | text | yes | Leading candidate by vote count. |
| `winner_party` | text | yes | Party of the leading candidate. |
| `winner_share_pct` | numeric | yes | Leading candidate share of all votes cast, in percentage points. |
| `vote_share_r_pct` | numeric | yes | Republican share of all votes cast, in percentage points. The cleanest available read on statewide partisan lean. |
| `vote_share_d_pct` | numeric | yes | Democratic share of all votes cast, in percentage points. |
| `votes_total` | bigint | yes | All votes cast in this statewide race. |
| `votes_r` | bigint | yes | Votes for the Republican candidate. |
| `votes_d` | bigint | yes | Votes for the Democratic candidate. |

## `fdga.v_voter_choice`

Ballot roll-off: how many voters cast a ballot but had no meaningful choice further down it. The legacy workbook's most persuasive measure.  Baseline is the highest-turnout statewide race in the cycle — president in presidential years, governor or U.S. Senate in midterms — which is the top of the ticket by definition without hard-coding which office that was.  no_meaningful_choice_pct combines two things: voters whose race was uncontested, and voters who cast no vote in that chamber at all. For the Georgia House it was 82.7% in 2016 and 49.3% in 2024.

**Columns:** 15 · **Reads:** `contests`, `statewide`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display. |
| `baseline_office` | text | yes | Which statewide race supplied the turnout baseline — the highest-turnout one in that cycle. Shown so the denominator is never a mystery. |
| `ballots_cast` | bigint | yes | Votes cast in the top-of-ticket statewide race — the best available proxy for how many people voted at all. |
| `votes_competitive` | numeric | yes | Votes cast in races the winner took by 53.5% or less. |
| `votes_non_competitive` | numeric | yes | Votes cast in contested races the winner took by more than 53.5%. |
| `votes_uncontested` | numeric | yes | Votes cast in races with only one candidate on the ballot. |
| `votes_cast` | numeric | yes | All votes cast in this chamber, across every race. |
| `no_vote_cast` | numeric | yes | Voters who cast a ballot but no vote in this chamber — ballot roll-off. Floored at zero, since a legislative race can in principle outdraw the top of the ticket. |
| `competitive_pct` | numeric | yes | Votes in competitive races as a share of all ballots cast, in percentage points. |
| `non_competitive_pct` | numeric | yes | Votes in non-competitive races as a share of all ballots cast. |
| `uncontested_pct` | numeric | yes | Votes in uncontested races as a share of all ballots cast. |
| `no_vote_cast_pct` | numeric | yes | Roll-off as a share of all ballots cast. |
| `no_meaningful_choice_pct` | numeric | yes | Uncontested votes plus roll-off, as a share of all ballots cast — the headline advocacy number. Georgia House: 82.7% in 2016, 49.3% in 2024. |

## `fdga.v_which_party_benefits`

Insight 3.2 — which party runs unopposed. Defuses the most common attack on this work: in the 2024 Georgia House, 47 Republicans and 43 Democrats faced nobody.

**Columns:** 7 · **Reads:** `v_contest`

| Column | Type | Null | Description |
|---|---|---|---|
| `cycle_year` | integer | yes | Election cycle, e.g. 2024. Georgia holds these every two years. |
| `chamber` | text | yes | Chamber code you filter on: us_house, state_senate or state_house. |
| `chamber_label` | text | yes | Readable chamber name for display: U.S. House, Georgia Senate, Georgia House. |
| `unopposed_r` | bigint | yes | Races Republicans won with nobody else on the ballot. |
| `unopposed_d` | bigint | yes | Races Democrats won with nobody else on the ballot. |
| `votes_unopposed_r` | numeric | yes | Votes cast in races Republicans won unopposed. Compare counts AND votes: in the 2000 Georgia Senate, Republicans ran unopposed in 14 seats carrying 640,065 votes against Democrats' 16 seats carrying 415,749. Race counts alone tell the opposite story. |
| `votes_unopposed_d` | numeric | yes | Votes cast in races Democrats won unopposed. Zero, not NULL, where there were none. |
