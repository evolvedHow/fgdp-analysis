# Fair Districts GA — Georgia Elections Canonical Data Model

Seats-versus-votes data for Georgia's congressional and legislative elections,
2000–2024. Replaces the manual `Ga Gen Assembly Analysis (25-02-11).xlsx`
workbook, which used 75,668 formulas across 13 per-year tabs to produce roughly
500 numbers.

Outputs land in `fdp/data/repos/main/fdga/`. That directory is **generated** —
the build clears and rewrites it, so nothing hand-written should live there.

## Commands

```bash
# Build (--fetch downloads the ~30MB OpenElections tarball on first run)
uv run --project fdp python fdp/scripts/build_fdga_cdm.py --fetch
uv run --project fdp python fdp/scripts/build_fdga_cdm.py
uv run --project fdp python fdp/scripts/build_fdga_cdm.py --cycle 2024 --dry-run

# Acceptance test against the legacy workbook
uv run --project fdp python fdp/scripts/reconcile_fdga_workbook.py

# Publish to the Google Sheets data layer.
# --extra sheets installs the Google client libraries on first run.
# Needs FDGA_SHEETS_CREDENTIALS and FDGA_SHEETS_ID (the token between
# '/d/' and '/edit' in the spreadsheet URL).
uv run --project fdp --extra sheets python fdp/scripts/push_fdga_to_sheets.py

# --dry-run needs neither the extra nor credentials
uv run --project fdp python fdp/scripts/push_fdga_to_sheets.py --dry-run

# Tests
uv run --project fdp --extra dev pytest fdp/tests/test_cdm.py
```

## Tables

| File | Grain | Rows | Use |
|---|---|---|---|
| `facts` | election × office × district × county × candidate | 32,181 | the fact table; no formulas, no judgments |
| `contests` | election × office × district | 3,230 | winner, margin, competitiveness |
| `chamber_year` | cycle × chamber | 39 | seats vs votes — the headline table |
| `statewide` | cycle × statewide office | 23 | the president/governor/senate vote baseline |
| `manifest` | source | 13 | provenance: URL, checksum, row counts |
| `corrections` | correction | 7 | documented source fixes and their evidence |
| `name_merges` | merge | 34 | candidate spelling variants that were merged |
| `validation` | check | 96 | contract-test results |
| `reconciliation` | cell | 156 | agreement with the legacy workbook |

Each data table is written as both `.csv` (Sheets, Power BI, Tableau) and
`.parquet` (platform joins). Total ≈ 3.7 MB CSV, 0.4 MB Parquet.

## Design rule: facts in, judgments out

`facts` carries only what the source states. Anything requiring a policy
decision is computed in `aggregate.py`, where the rule is visible and
changeable in one place rather than copied across thousands of cells:

- **competitive** — winner's share ≤ `COMPETITIVE_LIMIT` (0.535, matching the
  workbook's `Competitive_Limit` named range). Also materialized at 0.52, 0.55
  and 0.60 as `is_competitive_*` columns, so a UI can offer a threshold
  selector with no recomputation.
- **uncontested** — two defensible definitions, both emitted:
  - `is_uncontested` — no opponent on the ballot, ignoring write-ins. The
    workbook's rule, and the default so published history reconciles.
  - `is_uncontested_major` — no *major-party* opponent. A Republican facing
    only a Libertarian counts as uncontested. Differs from the strict rule in
    30–40 races across the 13 cycles.

## Source

[OpenElections for Georgia](https://github.com/openelections/openelections-data-ga),
fetched as a repository tarball. Format drift across the 13 cycles is absorbed
by `sources.py` — the only module that knows a file's shape:

| Cycles | Published grain | Files | Vote columns |
|---|---|---|---|
| 2000–2010 | county | 1 | explicit `votes` |
| 2012 | precinct | 1 | four vote-mode columns |
| 2014 | county | 1 | four vote-mode columns |
| 2016 | county | 1 | `votes` + four modes |
| 2018 | precinct | **159 per-county files** | `votes` + six modes |
| 2020–2024 | precinct | 1 | four vote-mode columns |

Office and party spellings drift independently: `State House` vs `State
Representative`, `Republican` vs `REP` vs `R` vs `(REP`.

## Known source defects, corrected

Every correction is verified against the legacy workbook, whose vote counts
match the source exactly — only the labels differ. See `corrections.csv`.

1. **Incumbency marker read as party (2012, 5 candidates).** OpenElections
   parsed the `(I)` incumbency marker in candidate names as the party
   "Independent". Stacey Abrams, Earnest Williams, Earnest Smith and Hardie
   Davis are Democrats; David Casas is a Republican. Correcting this moves 2012
   state house from 118R/58D/4I to 119R/60D/1I, matching the workbook exactly.
2. **Candidate assigned to the wrong district (2022).** Shaw Blackmon's rows
   are labeled district 145 but he represented 146 — leaving 145 with two
   Republicans and 146 with an unopposed Democrat. Correcting this yields
   101R/79D, matching the certified result.
3. **Name variants splitting one candidate's vote (34 rows, 397,374 votes).**
   The same candidate is spelled differently *by county*. Hank Johnson appears
   four ways in 2012 CD-4; Lynn Westmoreland two ways in CD-3, which is why the
   workbook records him unopposed at 100% while the raw data shows 85.7%.
   Merged within (cycle, office, district, party, surname) — see
   `name_merges.csv`.

## Known source gaps, not corrected

| Scope | Gap |
|---|---|
| 2002 state house | Georgia's 2001 plan used **multi-member districts**: 147 districts elected 180 members. The source carries no post identifier, so seat winners are not derivable. Votes are complete. `seats_derivable = False`. (Plan struck down in *Larios v. Cox*, 2004.) |
| 2018 state house | Districts 014 and 028 are absent from the source. Verified absent in the raw files, not dropped by the adapter. |

## Reconciliation against the legacy workbook

139 of 156 compared cells match (89.1%). Every remaining difference is ≤2 units
and traceable:

| Category | Cells |
|---|---|
| 2002 multi-member districts (structural) | 3 |
| 2018 missing districts (source gap) | 1 |
| `races_uncontested` edge cases, ±1–2 | 6 |
| `races_competitive` threshold boundary, ±1 | 3 |
| 2000/2004 state house single-seat disagreements | 3 |

The 2000 and 2004 seat differences are **unresolved** and worth a look: the
workbook's Summary tab notes party switching after those elections ("Two GA
House members changed parties" in 2000), so the two may be measuring
*as-elected* versus *as-seated*.

## Adding an election

1. Add one entry to `SOURCES` in `sources.py` describing the new file's shape.
2. Rebuild. The validators will report any district, county or party anomaly.

No aggregate, chart, or downstream formula changes — every derived table groups
by `election_date`, so a new cycle appends rows rather than requiring a new tab.
That property is the whole point of the migration: the old workbook needed a new
tab, a new set of copied formulas, and a new set of hand-edited cell references
for every election.

## Two sinks, one source

```
build_fdga_cdm.py  ──┬──►  PostgreSQL  ──►  Metabase   (analysts, live queries)
                     └──►  Google Sheets ─►  add-on     (spreadsheet users)
```

Neither sink is downstream of the other — both are outputs of the same
validated build, so they cannot drift apart.

**The apps are not involved.** fdex, lrdb and map-compare read static
Parquet/GeoJSON copied by `fdp sync-app` and deploy to GitHub Pages. They have
no database dependency and neither sink introduces one: if Postgres is down,
every public map still works.

## PostgreSQL layer (optional / legacy)

> The FDP API no longer requires PostgreSQL.  This section describes an
> optional analyst-facing Postgres sink used by some legacy scripts.  Install
> the extra with `uv pip install -e ".[postgres]"` before running these commands.

```bash
export FDGA_DATABASE_URL=postgresql://user:pass@host:5432/dbname
uv run --project fdp --extra postgres python fdp/scripts/load_fdga_to_postgres.py
uv run --project fdp python fdp/scripts/load_fdga_to_postgres.py --dry-run
uv run --project fdp python fdp/scripts/load_fdga_to_postgres.py --grant-read-only metabase_ro
```

Schema `fdga`, DDL in [`postgres_ddl.sql`](postgres_ddl.sql), idempotent.
**Full reference — every table, view, constraint and column — is in
[`postgres_data_model.md`](postgres_data_model.md)**, generated from the live
catalog by `scripts/gen_postgres_data_model.py`. The
reload is `TRUNCATE` + `COPY` inside **one transaction**: readers see the old
data until commit and the new data after — never a partial or empty state, and
a failure rolls back to the previous load intact.

Three type decisions that matter, all enforced by the schema:

- **`district` is `text`**, zero-padded (`'001'`). Cast it to integer and the
  padding is lost, silently breaking every join between `facts` and `contests`.
- **Seat columns are nullable.** 2002 state house is NULL because multi-member
  districts make seats non-derivable; `votes_total` is still populated. NULL
  means unknown, never zero.
- **Empty string ≠ NULL.** Statewide races carry `district = ''` (a value);
  2002's seat counts are NULL (absent). COPY uses `\N` as the NULL marker so
  the two stay distinct.

Unique constraints enforce the declared grain, so a bad reload fails loudly
instead of double-counting. Note that `election_type` is part of the key for
both `facts` and `contests`: in 2020 the regular U.S. Senate race and the
Loeffler/Warnock special were **both** held on 2020-11-03.

### View layer — the semantic contract

Analysts and Metabase models read the views, never the raw tables:

| View | Grain |
|---|---|
| `fdga.v_chamber_year` | cycle × chamber — the headline seats-vs-votes |
| `fdga.v_contest` | one row per legislative/congressional race |
| `fdga.v_statewide` | statewide race vote shares |
| `fdga.v_county_results` | county-level detail |
| `fdga.v_data_health` | one row: FAIL/WARN/KNOWN counts, corrections, workbook agreement |

Views present percentages **as percentages** (55.0, not 0.55) and friendly
chamber labels, so a Metabase model needs no transformation on top.

The rule that keeps this coherent: **a definition lives in `aggregate.py`, is
surfaced by a view, and is never re-implemented in a Metabase question.** If
someone needs a new measure it gets added upstream, and every consumer gets it.

## Google Sheets layer

`push_fdga_to_sheets.py` writes these tables into a data-layer spreadsheet as
static values — no formulas anywhere. Share it **view-only**; every refresh
overwrites it.

UI spreadsheets pull the small aggregate tabs:

```
=IMPORTRANGE("<data-layer url>", "chamber_year!A:X")
```

Do not `IMPORTRANGE` `facts` (386k cells) — IMPORTRANGE is reliable to roughly
50–100k cells per call. `contests` at 87k is near that limit, so pull a column
subset. Power BI (native Google Sheets connector) and Tableau (via the Google
Drive connector — the dedicated Sheets connector was retired mid-2023) read the
spreadsheet through the API and are not subject to that limit.
