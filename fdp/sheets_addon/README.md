# Fair Districts GA — Sheets add-on

Custom spreadsheet functions over the Fair Districts GA canonical data
model, so a power user can pull numbers without knowing the table names,
column names, or where the data lives.

```
=FDGA_SEATS(2024, "house", "R")            -> 100
=FDGA_GAP(2024, "house")                   -> 0.0056
=FDGA_TREND("house", "gap")                -> 13 rows, ready to chart
=FDGA_RACES(2024, "house", "competitive")  -> the 6 competitive races
=FDGA_MEASURES()                           -> everything you can ask for
```

Chamber and party arguments take whatever a person would naturally type:
`"house"`, `"GA House"`, `"state house"` all work, as do `"R"`, `"rep"`,
`"Republican"`.

## Install

The script goes on a **UI spreadsheet** — not the data layer. Make a new
spreadsheet for it (or use an existing one where you build charts).

1. In that spreadsheet: **Extensions → Apps Script**.
2. Delete the placeholder `Code.gs` contents.
3. Create the files and paste in the matching contents:
   - `Code.gs` ← [`Code.gs`](Code.gs)
   - `Functions.gs` ← [`Functions.gs`](Functions.gs) (File → New → Script)
   - `Sidebar.html` ← [`Sidebar.html`](Sidebar.html) (File → New → HTML)
4. Confirm `DATA_LAYER_ID` at the top of `Code.gs` matches the data layer
   spreadsheet id.
5. **Save**, then reload the spreadsheet. A **FDGA** menu appears.
6. **FDGA → Refresh data**. Approve the authorization prompt the first time —
   it needs read access to the data layer and write access to this sheet.

Or with [clasp](https://github.com/google/clasp), from this directory:

```bash
clasp create --type sheets --title "FDGA Explorer"
clasp push
```

## How it works

Apps Script custom functions run in a restricted context: they can read the
*active* spreadsheet but cannot open another one, because that needs
authorization a custom function never gets. So the data is copied locally
first:

```
data layer spreadsheet          this spreadsheet
(fdp_analytics)          --->   _fdga_chamber_year   (hidden)
  written by                    _fdga_contests       (hidden)
  push_fdga_to_sheets.py         _fdga_statewide      (hidden)
                                _fdga_manifest       (hidden)
                                      ^
                                      |  read by
                                =FDGA_SEATS(), =FDGA_GAP(), ...
```

**FDGA → Refresh data** runs as the signed-in user, which *does* carry
authorization, so it can read the data layer and write the hidden tabs. The
custom functions then only ever read local ranges.

This also sidesteps `IMPORTRANGE`'s ~50-100k cell ceiling — a local tab has no
such limit, so `contests` (87k cells) copies fine where `IMPORTRANGE` would be
unreliable.

The copy is a snapshot. Re-run **Refresh data** after each `push_fdga_to_sheets.py`;
**FDGA → About** shows when it last ran.

## Functions

### One number

| Function | Returns |
|---|---|
| `FDGA_SEATS(year, chamber, party)` | Seats won |
| `FDGA_SEAT_SHARE(year, chamber, party)` | Share of seats, 0–1 |
| `FDGA_VOTE_SHARE(year, chamber, party)` | Share of votes, 0–1 |
| `FDGA_GAP(year, chamber)` | Seats-votes gap for Republicans, 0–1 |
| `FDGA_UNCONTESTED(year, chamber, [includeMinorPartyOnly])` | Uncontested race count |
| `FDGA_COMPETITIVE(year, chamber, [threshold])` | Competitive race count |
| `FDGA_VALUE(year, chamber, measure)` | Any measure — the escape hatch |

`FDGA_COMPETITIVE` accepts a threshold of `0.52`, `0.535` (default), `0.55` or
`0.6`. Those four are precomputed, so switching costs nothing.

### Tables that spill

| Function | Returns |
|---|---|
| `FDGA_TREND(chamber, measure, [includeHeader])` | One measure across all 13 elections |
| `FDGA_BY_CHAMBER(year, measure)` | All three chambers for one election |
| `FDGA_RACES(year, chamber, [filter])` | Individual races |
| `FDGA_STATEWIDE([year])` | Statewide race vote shares |

`FDGA_RACES` filters: `"all"`, `"competitive"`, `"uncontested"`, `"contested"`,
`"close"` (under 5%). These spill down and right — leave room.

### Discovery

| Function | Returns |
|---|---|
| `FDGA_MEASURES()` | Every measure name, with descriptions |
| `FDGA_CYCLES()` | Election years available |
| `FDGA_SOURCE([year])` | Provenance: source file, row counts, checksum |

`FDGA_MEASURES()` is the one to point people at — it's the built-in
documentation, and it stays correct because it's generated from the same list
the functions use.

## The sidebar

**FDGA → Insert a formula…** builds a formula from dropdowns and writes it into
the selected cell. It shows only the inputs the chosen shape actually uses, and
prefers the readable purpose-built function (`FDGA_SEATS(...)`) over the generic
`FDGA_VALUE(...)` where one exists.

## Notes

- **Blank, not zero, where a number isn't derivable.** 2002 state house used
  multi-member districts and the source carries no post identifier, so seats
  aren't attributable — `FDGA_SEATS(2002, "house", "R")` returns blank rather
  than a made-up figure. Vote measures still work for that year.
- **Shares are 0–1 ratios.** Format the cell as a percentage; the value is
  `0.55`, not `55`.
- **Custom functions are cached by Google.** If a refresh doesn't seem to take
  effect, edit and re-enter the cell, or press Ctrl+R.
- **`facts` is opt-in.** FDGA → *Also copy facts* pulls the 32k-row county-level
  table. Every headline measure comes from `chamber_year` and `contests`, so
  only do it if you need county detail — it makes the spreadsheet heavier.
