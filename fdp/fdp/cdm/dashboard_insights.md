# FDGA Dashboard Insights

Ready-to-paste queries for the Fair Districts GA dashboards, each one framed as
an **insight** rather than a chart: what it surfaces, the SQL, and how to read it
out loud.

This replaces `dashboard_queries.sql`. Nothing applies it automatically — it is a
reference you copy from. Paste into Metabase (**New → SQL query**) or run in
`psql`.

Every insight below has a **backing view** in the `fdga` schema, so a Metabase
question is `SELECT ... FROM fdga.v_x` with a filter rather than a block of
pasted SQL that drifts from this document. Every query reads a `v_` view, never
a raw table, so the business definitions stay in one place
(`fdp/cdm/aggregate.py`). If you find yourself re-deriving "competitive" or
"uncontested" inside a Metabase question, stop — add it upstream instead.

The views are defined in `postgres_ddl.sql` and documented in
`postgres_comments.sql`; both are applied by `scripts/load_fdga_to_postgres.py`,
which is idempotent. For the schema itself — grain, keys, types, and every
column of every table and view — see
[`postgres_data_model.md`](postgres_data_model.md).

**Metabase filter syntax used below**

| Syntax | Meaning |
|---|---|
| `{{cycle_year}}` | required variable |
| `[[AND chamber = {{chamber}}]]` | optional clause, ignored when unset |

Delete the `[[...]]` brackets when running in `psql`.

All figures quoted in this document were verified against the loaded database on
2026-08-16 and cover cycles 2000–2024.

---

## The story in four beats

The data supports one narrative arc. Build one dashboard per beat, in this
order — each beat answers the objection the previous one raises.

| # | Dashboard | The claim | The objection it answers |
|---|---|---|---|
| 1 | **No Choice** | Half of Georgians never get a real vote for their legislator | — |
| 2 | **The Map Decides** | Seats stopped tracking votes, and the break lines up with a map | "Maybe voters just moved" |
| 3 | **Follow the Wasted Vote** | The imbalance has a measurable size and direction | "Both parties do this" |
| 4 | **Show Your Work** | Every number is auditable | "You're a partisan group" |

The single most important framing decision: **proportional is not the same as
competitive.** Measured against its own vote, Georgia's state House in 2024 looks
almost perfectly proportional — 55.0% of the vote produced 55.6% of the seats —
and *still* had 90 of 180 races with only one name on the ballot. Lead with
choice, not proportionality.

That 55.0% is itself distorted, though, and 2.3 shows by how much: measured
against the statewide vote instead, the same chamber carries an **8-seat**
Republican bonus rather than a 1-seat one. Both numbers are real. Publish both.

---

# Dashboard 1 — No Choice

## 1.1 · The village of 100 voters

**Surfaces:** what happened to 100 typical Georgians on election day, by chamber.
The whole argument compressed into one card.

**Views:** `fdga.v_100_voters` (wide) and `fdga.v_100_voters_long` (tall). Same
four buckets, two shapes — pick by chart type, never re-derive one from the other.

Wide, for a table or big-number cards:

```sql
SELECT chamber_label, had_a_real_race, race_already_decided,
       only_one_name, skipped_the_race
FROM fdga.v_100_voters
WHERE cycle_year = {{cycle_year}}
ORDER BY chamber_label;
```

Long, for a stacked bar or anything needing a series dimension — one row per
cycle, chamber and category:

```sql
SELECT chamber_label, category, voters_per_100
FROM fdga.v_100_voters_long
WHERE cycle_year = {{cycle_year}}
ORDER BY chamber_label, sort_order;
```

**Sort on `sort_order`, not `category`.** The categories run best case to worst,
and an alphabetical axis renders the story backwards.

**Visualization:** stacked horizontal bar, 100% width, three rows, from the long
view. Or three big-number cards from the wide view showing only
`had_a_real_race`.

**How to read it — 2024:**

| Out of every 100 Georgia voters | Ga House | Ga Senate | U.S. House |
|---|---|---|---|
| had a genuinely competitive race | **3** | **0** | **0** |
| had a race already decided | 47 | 42 | 98 |
| had only one name on the ballot | 41 | 48 | 0 |
| cast no vote in that race at all | 9 | 11 | 2 |

> Imagine a Georgia village of 100 voters. In 2024, three of them had a real
> choice of state representative. For state senator and for Congress, none did.

The U.S. House column is the one that stops arguments: **every single
congressional race had two candidates, and not one of them was close.** Nobody
can wave that away as "the other party didn't bother to run."

**How it works.** The four columns are the only four things a voter could have
done, so they sum to the denominator by construction — that is why the row lands
on 100 rather than needing to be checked each time:

```
votes_competitive + votes_non_competitive + votes_uncontested = votes_cast
votes_cast        + no_vote_cast                              = ballots_cast
```

`ballots_cast` is **not turnout**. It is the vote total of the highest-turnout
statewide race in the cycle — president in presidential years, governor or U.S.
Senate in midterms — picked by the `baseline` CTE inside `v_voter_choice` rather
than hard-coded. It stands in for "people who showed up," measured at the top of
the ticket where no map constrained anyone's choice. Individual cells drift by
±1 from `round()`; never print the total as a computed figure.

**Guardrails.**

* `no_vote_cast` is the top-of-ticket vote minus the votes cast in that chamber.
  Some of it is genuine roll-off, not despair. Say "cast no vote in that race,"
  not "stayed home."
* The buckets group **votes by the category of the race they were cast in**, not
  by whether an individual vote mattered. "Three in 100 had a real choice" is
  shorthand for "three in 100 voted in a district where the outcome was in
  doubt," and includes votes for the loser. Do not tighten it to "three votes
  counted."
* **Exclude 2002 Georgia House.** Its four cells sum to 131, not 100. That year's
  multi-member districts let a voter cast up to three state house votes, so
  `votes_cast` (2,673,452) exceeds `ballots_cast` (2,029,991); `GREATEST(..., 0)`
  clamps `no_vote_cast` to zero and the rest overflow. `v_voter_choice` carries
  no `seats_derivable` flag to catch this, so filter it out in the question:
  `AND NOT (cycle_year = 2002 AND chamber = 'state_house')`.

---

## 1.2 · Races with only one name on the ballot

**Surfaces:** the long trend in uncontested races — the clearest single indicator
of declining choice, and the workbook's original chart 1.

```sql
SELECT cycle_year,
       chamber_label,
       races_uncontested,
       races_total,
       uncontested_pct
FROM fdga.v_chamber_year
ORDER BY cycle_year, chamber_label;
```

**Visualization:** line, x = `cycle_year`, y = `uncontested_pct`, one series per
chamber.

**How to read it:** the Georgia House peaked at **82.2% uncontested in 2016**
(148 of 180 races) and has fallen to **50.0% in 2024** (90 of 180). That is real
improvement and you should say so — it buys credibility for the parts that have
not improved. The Georgia Senate went the other way over the same span: 48.2%
in 2020 back up to **58.9% in 2024**.

The U.S. House line is the outlier and reads as good news: **0% uncontested in
2020, 2022 and 2024.** Do not stop there — pair it with 1.3, which shows that
having a second candidate and having a race are different things.

---

## 1.3 · Contested, competitive, or neither

**Surfaces:** the gap between "someone filed" and "the outcome was in doubt."

**View:** `fdga.v_contest_by_category`

```sql
SELECT cycle_year, chamber_label, category, races, pct_of_total
FROM fdga.v_contest_by_category
ORDER BY cycle_year, chamber_label, category;
```

**Visualization:** stacked bar, x = `cycle_year`, one panel per chamber.

**How to read it:** "competitive" here means the winner took under 53.5% —
`COMPETITIVE_LIMIT` in `fdp/cdm/schema.py`. The middle band is the finding: in
2024 the U.S. House was 0 uncontested, 0 competitive, and 14 races in the middle.
Two names, no contest.

Georgia Senate 2024: 33 uncontested, 23 contested, **0 competitive**. Not one of
56 state senate races in 2024 was decided by less than 7 points.

**Guardrail:** 53.5% is a threshold you chose. Someone will challenge it. The
contests table carries four (`is_competitive_052`, `_0535`, `_055`, `_06`) —
swap the column and show the story survives. That is a much better answer than
defending the number.

---

## 1.4 · Decided before election day

**Surfaces:** how many *voters*, not races, were in a foregone conclusion.
Counting voters rather than districts is what makes this land.

**View:** `fdga.v_decided_before_election`

```sql
SELECT chamber_label, uncontested, won_by_20_plus, actual_race,
       votes_predecided, votes_total, predecided_pct
FROM fdga.v_decided_before_election
WHERE cycle_year = {{cycle_year}}
ORDER BY chamber_label;
```

**Visualization:** three big-number cards showing `predecided_pct`.

**How to read it — 2024:**

| Chamber | Uncontested | Won by 20+ | Actual race | Votes pre-decided |
|---|---|---|---|---|
| U.S. House | 0 | 13 | 1 | **93.9%** |
| Georgia Senate | 33 | 18 | 5 | **89.5%** |
| Georgia House | 90 | 64 | 26 | **83.6%** |

> In 2024 Georgia held 14 congressional elections. Thirteen were won by more
> than 20 points. The fourteenth — Sanford Bishop's — was won by 12.7. Not one
> was close.

---

# Dashboard 2 — The Map Decides

## 2.1 · The seats-votes gap

**Surfaces:** the headline chart. How far seat share ran ahead of vote share,
by chamber, over 13 cycles.

```sql
SELECT cycle_year,
       chamber_label,
       seats_votes_gap_r_pct
FROM fdga.v_chamber_year
WHERE seats_derivable            -- excludes 2002 Ga House (multi-member districts)
ORDER BY cycle_year, chamber_label;
```

**Visualization:** line, x = `cycle_year`, y = `seats_votes_gap_r_pct`, series =
`chamber_label`. **Add a zero reference line** — the whole chart is about
distance from zero.

**How to read it:** positive = Republicans won a larger share of seats than of
votes; negative = Democrats did.

| | 2000 | 2016 | 2024 |
|---|---|---|---|
| Georgia House | −10.6 | +1.3 | **+0.6** |
| Georgia Senate | −12.1 | +3.8 | **+3.3** |
| U.S. House | +10.7 | +11.2 | **+11.7** |

The counterintuitive finding, and the honest one: **by this measure the state
House gap closed.** It ran −10.6 in favor of Democrats in 2000 and sits at +0.6
today. The congressional gap never closed — it has been in double digits in five
of the last six cycles.

"By this measure" is load-bearing. This chart divides seats by the chamber's own
vote, which 90 uncontested races distort. Against the statewide vote (2.3) the
2024 Georgia House still carries an 8-seat Republican bonus. The direction of
travel is genuinely improving; the destination is not "closed".

**Say this out loud on the dashboard.** An organization arguing against
gerrymandering that publishes data indicting both parties is far harder to
dismiss as partisan than one that only shows the half that helps.

**Guardrail:** chamber vote share only counts votes actually cast, and an
uncontested seat contributes 100% to one party. With 90 uncontested Georgia House
races in 2024, that line is soft. The U.S. House line has **zero** uncontested
races in 2020–2024, so it is clean. Put 2.2 next to it.

---

## 2.2 · Statewide baseline — the sanity check

**Surfaces:** partisan preference measured where every voter gets a say, so
uncontested districts cannot distort it.

**View:** `fdga.v_partisan_preference_baseline`

```sql
SELECT cycle_year, office_label, election_type, party, pct
FROM fdga.v_partisan_preference_baseline
ORDER BY cycle_year, office_label, party;
```

**Visualization:** line, x = `cycle_year`, y = `pct`, series = party. Overlay the
relevant `vote_share_r_pct` from 2.1 as a dashed line.

**How to read it:** 2024 president was **R 50.7% / D 48.5%** statewide. The
congressional vote was 52.6% R and the congressional seats were 64.3% R. A state
that splits roughly 50–50 elects a 9–5 delegation.

**This chart is the referee.** When the chamber line and the statewide line
agree, your claim is solid. When they diverge, uncontested races are doing the
work and you want to know that before an opponent tells you. Georgia in 2000 is
the cautionary case: Bush carried the state 55.0–43.2 while Zell Miller won the
Senate seat 58.2–39.4 as a Democrat. Genuinely split-ticket, not a clean read of
partisan preference.

---

## 2.3 · Seats a party would hold under proportional allocation

**Surfaces:** the gap from 2.1 restated in seats, which is the unit people
actually feel.

**View:** `fdga.v_proportional_allocation`

```sql
SELECT cycle_year, chamber_label, seats_r, seats_d, seats_total,
       seats_r_proportional_chamber,   r_seat_bonus_chamber,
       seats_r_proportional_statewide, r_seat_bonus_statewide
FROM fdga.v_proportional_allocation
WHERE chamber = {{chamber}}
ORDER BY cycle_year;
```

**Visualization:** bar, x = `cycle_year`, y = both bonus columns as two series,
with a zero line. Showing them together is the point — see below.

**Two benchmarks, and the space between them is a finding.**

`r_seat_bonus_chamber` divides seats by the chamber's *own* two-party vote.
`r_seat_bonus_statewide` uses the cycle's highest-turnout statewide race, which
no district line can skew.

**How to read it — 2024:**

| Chamber | Actual | Chamber benchmark | Statewide benchmark |
|---|---|---|---|
| U.S. House | 9 R / 5 D | 7 R (**+2**) | 7 R (**+2**) |
| Georgia Senate | 33 R / 23 D | 31 R (+2) | 29 R (**+4**) |
| Georgia House | 100 R / 80 D | 99 R (+1) | 92 R (**+8**) |

**The U.S. House row is the validation.** It has zero uncontested races, and the
two benchmarks agree exactly. Where half the seats go uncontested, they diverge
hard. That is not a contradiction — it is the uncontested distortion made
visible, and it tells you which benchmark to trust in which chamber.

The Georgia House trend under the statewide benchmark, which the chamber
benchmark hides almost entirely:

| Cycle | Chamber bonus | Statewide bonus |
|---|---|---|
| 2012 | +6 | **+22** |
| 2016 | +2 | **+23** |
| 2020 | +10 | +13 |
| 2024 | +1 | **+8** |

> Georgians split their congressional vote 53–47. Fourteen seats divided that way
> is 7 and 7. Georgia sent 9 Republicans and 5 Democrats.

**Guardrails.**

* Proportional representation is *not* the legal standard, and no court requires
  it. *Rucho v. Common Cause* (2019) closed the federal courts to partisan
  gerrymandering claims entirely. Say "if seats tracked votes," never "the fair
  number of seats is."
* The statewide benchmark assumes voters split the same way down-ballot as at
  the top of the ticket. Split-ticket cycles show they do not always — in 2000
  Bush carried Georgia 55.0–43.2 while Zell Miller won the Senate seat
  58.2–39.4 as a Democrat. Do not quote the statewide benchmark for 2000 or 2002
  without that caveat.
* **Quote both columns or neither.** Publishing only the one that helps your
  argument is exactly what the opposition will accuse you of, and here you have
  the receipts to show you did not.

---

## 2.4 · Before and after the map changed

**Surfaces:** the same electorate, two maps. This is the cleanest natural
experiment in the dataset.

```sql
SELECT cycle_year,
       vote_share_r_pct,
       seat_share_r_pct,
       seats_r, seats_d,
       races_competitive,
       races_uncontested
FROM fdga.v_chamber_year
WHERE chamber = 'us_house'
  AND cycle_year BETWEEN 2018 AND 2024
ORDER BY cycle_year;
```

**Visualization:** small table, or a slope chart from 2020 to 2022.

**How to read it:**

| Cycle | R vote share | R seat share | Seats | Competitive races |
|---|---|---|---|---|
| 2018 | 52.3% | 64.3% | 9–5 | 2 |
| 2020 | 51.0% | 57.1% | 8–6 | 1 |
| **2022** *(new map)* | 52.3% | 64.3% | 9–5 | **0** |
| 2024 | 52.6% | 64.3% | 9–5 | **0** |

> Between 2020 and 2022 the Republican share of Georgia's congressional vote rose
> 1.3 points. The Republican share of seats rose 7.2 points, and the number of
> competitive races fell to zero. The voters barely moved. The lines did.

**Guardrail:** 2022 and 2024 were run on different congressional maps — the 2023
special session redrew districts after the VRA ruling in *Grant v. Raffensperger*.
The seat totals are unchanged, but do not describe 2022–2024 as one map. Precise
era boundaries land with `dim_district` (open task #7); until then, annotate the
chart manually rather than encoding eras in SQL.

---

## 2.5 · Counties split between districts

**Surfaces:** a redistricting-craft measure that is intuitive to a general
audience and does not require any partisan claim.

**View:** `fdga.v_county_splits`

```sql
SELECT cycle_year, chamber_label, counties_split, counties_reporting
FROM fdga.v_county_splits
ORDER BY chamber_label, cycle_year;
```

**Visualization:** line, x = `cycle_year`, series = `office`.

**How to read it:** Georgia has 159 counties. In 2024, **68 were split between
Georgia House districts** and 16 between congressional districts. County
splitting is not evidence of gerrymandering by itself — population equality
requires some of it — but a rising count against flat population is worth asking
about.

**Guardrail:** this counts counties that reported votes in more than one
district, which is a *reported-results* proxy for the district boundary, not the
boundary itself. Treat it as directional. The authoritative version comes from
the plan GeoJSONs in `data/repos/main/boundaries/` once `dim_district` exists.

---

# Dashboard 3 — Follow the Wasted Vote

## 3.1 · The efficiency gap

**Surfaces:** the standard academic measure of partisan advantage. A vote is
"wasted" if it was cast for a loser, or for a winner beyond the 50% needed. Pack
your opponents into a few districts and their wasted votes pile up.

**View:** `fdga.v_efficiency_gap` — which reads the `wasted_votes_r` /
`wasted_votes_d` columns on `v_contest`, so the wasted-vote definition has
exactly one home.

```sql
SELECT cycle_year, chamber_label, wasted_r_pct, wasted_d_pct,
       efficiency_gap_r_pct, uncontested_races
FROM fdga.v_efficiency_gap
ORDER BY chamber_label, cycle_year;
```

**Visualization:** line, y = `efficiency_gap_r_pct`, zero reference line, series =
chamber. Show `uncontested_races` in the tooltip — see the guardrail.

**How to read it:** positive favors Republicans. For the U.S. House, where 2020,
2022 and 2024 had **no uncontested races at all**, the measure is clean:

| Cycle | Efficiency gap (R) | Wasted R votes | Wasted D votes |
|---|---|---|---|
| 2020 | +4.9 | 22.5% | 27.5% |
| 2022 | +11.8 | 19.1% | 30.9% |
| 2024 | **+11.9** | **19.0%** | **31.0%** |

The Georgia House in 2024 scores **−0.2** — essentially zero. Two chambers, two
completely different findings, from the same map-drawers in the same year.

> Half of every vote cast is "wasted" — that is arithmetic, not injustice. What
> is not arithmetic is *whose*. In Georgia's 2024 congressional elections, of
> every 100 votes cast, 19 wasted votes were Republican and 31 were Democratic.

**Guardrail — this one matters.** The efficiency gap is badly distorted by
uncontested races: an unopposed winner racks up enormous "surplus" waste against
zero opposing waste. The Georgia House had 90 uncontested races in 2024, so its
−0.2 should be quoted as "not measurable," not as "fair." Only the U.S. House
figures are safe to publish without an asterisk.

**On thresholds:** the 7% figure sometimes cited as a presumptive gerrymander
came from the plaintiffs' proposed standard in *Gill v. Whitford*. The Supreme
Court did not adopt it — *Gill* was decided on standing, and *Rucho v. Common
Cause* (2019) held that federal courts cannot hear partisan gerrymandering claims
at all. Cite 7% as a scholarly benchmark, never as a legal test.

---

## 3.2 · Who runs unopposed

**Surfaces:** which party benefits from uncontested races. The answer defuses the
most common attack on this work.

**View:** `fdga.v_which_party_benefits`

```sql
SELECT cycle_year, unopposed_r, unopposed_d,
       votes_unopposed_r, votes_unopposed_d
FROM fdga.v_which_party_benefits
WHERE chamber = {{chamber}}
ORDER BY cycle_year;
```

**Visualization:** diverging bar, R above the axis, D below.

**How to read it:** in the 2024 Georgia House, **47 Republicans and 43 Democrats
ran unopposed.** Non-competition is close to bipartisan, and it has been for
most of the series — the exception is 2012–2016, when Republicans held roughly
twice as many unopposed seats (91–47, 94–52, 97–51).

> Both parties have seats they never have to defend. That is not a Republican
> problem or a Democratic problem. It is a map problem.

**Guardrail:** compare vote *counts*, not just race counts. In the 2000 Georgia
Senate, Republicans ran unopposed in 14 seats carrying 640,065 votes while
Democrats ran unopposed in 16 seats carrying only 415,749. Fewer free seats,
more banked votes. Race counts alone would have told you the opposite story.

---

## 3.3 · Seat/vote inversions — both directions

**Surfaces:** cycles where the party that won more votes won fewer seats. Publish
all of them, including the ones that cut against your side.

**View:** `fdga.v_seat_vote_inversions`

```sql
SELECT cycle_year, chamber_label, vote_share_r_pct,
       seats_r, seats_d, inversion
FROM fdga.v_seat_vote_inversions
ORDER BY cycle_year;
```

**Visualization:** table. Four rows — it should stay small.

**How to read it:** four inversions in 13 cycles. Three favored Democrats (2000
Georgia House, 2000 Georgia Senate, 2002 Georgia Senate); one favored Republicans
(2008 U.S. House, where Democrats took 50.8% of the vote and 6 of 13 seats).

**Guardrail — do not overclaim the 2000/2002 rows.** All three rest on chamber
vote share in cycles with more than half the seats uncontested, and 3.2's vote
counts show Republicans banking more votes in fewer free seats. The defensible
sentence is:

> Georgia's maps have produced seat/vote inversions in both directions —
> Democratic-favoring in 2000 and 2002, Republican-favoring in Congress since
> 2014.

What will not survive scrutiny is "Democrats stole seats in 2000." Someone will
point at the uncontested distribution and at Zell Miller's 58%.

---

## 3.4 · Race-level drill-down

**Surfaces:** the receipts. Every race, sortable, so a skeptic can find their own
district.

**View:** `fdga.v_race_drilldown`

```sql
SELECT district, winner_name, winner_party, winner_share_pct,
       margin_pct, votes_total, category
FROM fdga.v_race_drilldown
WHERE cycle_year = {{cycle_year}}
  AND chamber    = {{chamber}}
ORDER BY margin_pct;
```

**Visualization:** table. Wire it up as the click-through target from every chart
above — a dashboard people can interrogate is worth three they can only look at.

**How to read it — 2024 U.S. House, sorted by margin:** Bishop (D-02) at 12.7,
then Allen (R-12) at 20.6, and it climbs to Nikema Williams (D-05) at 71.4.
Nobody within 12 points of losing.

---

# Dashboard 4 — Show Your Work

Put at least one of these on every dashboard, not on a page of its own. Trust
shown next to the claim is worth more than trust filed somewhere else.

## 4.1 · Data health

```sql
SELECT failing_checks,
       warnings,
       known_gaps,
       passing_checks,
       corrections_applied,
       name_variants_merged,
       legacy_workbook_agreement,
       last_built_at
FROM fdga.v_data_health;
```

**Visualization:** a row of small number cards. `failing_checks` should read 0,
and that is the point.

## 4.2 · What was corrected and why

```sql
SELECT correction, rows_matched, status, evidence
FROM fdga.corrections
ORDER BY status, correction;
```

**How to read it:** this returns **7 rows covering two classes of defect** found
in the published source data — the 2012 `(I)` incumbency marker misread as party
"Independent" (6 candidates, including Stacey Abrams recorded as an Independent),
and Shaw Blackmon filed under district 145 instead of 146 in 2022. Each carries
its evidence. Correcting the 2012 marker turns that year's Georgia House from
118R/58D/4I into 119R/60D/1I, matching the legacy workbook exactly.

A third class of fix lives in its own table — **34 candidate-name variants**
(397,374 votes) that were splitting one candidate's total across counties:

```sql
SELECT cycle_year, office, district, party,
       merged_from, merged_into, votes_moved
FROM fdga.name_merges
ORDER BY votes_moved DESC;
```

When someone challenges a number, these two tables are the answer.

## 4.3 · Known gaps

```sql
SELECT check_name, severity, scope, detail
FROM fdga.validation
WHERE severity IN ('FAIL', 'WARN', 'KNOWN')
ORDER BY severity, check_name;
```

**How to read it:** publishing your own gaps is the strongest available signal
that you are not hiding any. The two that matter: 2002 Georgia House had 147
multi-member districts electing 180 members with no post identifier in the
source, so seat counts are not derivable that year; and 2018 is missing districts
014 and 028.

---

# Human-scale translations

Percentages do not move people; ratios they can picture do. Every framing below
is derived from a query above — check it against the data before it goes in a
deck, and re-check after any rebuild.

### The village of 100 — voter choice (2024, Georgia House)

> Picture a Georgia village of 100 voters. In November 2024, 41 of them found
> only one name on the ballot for state representative. Another 47 voted in a
> race the winner took by more than seven points. Nine skipped the race
> entirely. **Three had a real choice.**

*Source: 1.1. Rounds to exactly 100.*

### The village of 100 — Congress (2024)

> Same village, voting for Congress. This time everyone had two names to choose
> between. **Not one of them lived in a district where the outcome was in
> doubt.** Ninety-eight voted in a race that was already settled; two skipped it.

*Source: 1.1.*

### Fourteen seats, split 53–47

> Georgians cast about 53 votes in 100 for Republican congressional candidates
> and 47 for Democrats. They elect 14 representatives. Split 14 seats the way
> the votes split and you get 7 and 7. Georgia sent **9 Republicans and 5
> Democrats.**

*Source: 2.3. Only quote this for the U.S. House — the state chambers' vote share
is distorted by uncontested races.*

### Whose vote got thrown away

> In any election about half the votes cast don't elect anyone — they went to a
> loser, or piled on top of a winner who had already won. That's arithmetic.
> Here's what isn't: of every 100 votes cast in Georgia's 2024 congressional
> elections, **19 of the wasted ones were Republican and 31 were Democratic.**

*Source: 3.1.*

### The map changed, the voters didn't

> Between 2020 and 2022, Republicans gained **1.3 points** of Georgia's
> congressional vote. They gained **7.2 points** of its seats. In between, the
> lines were redrawn — and the number of competitive races went from one to
> zero.

*Source: 2.4.*

### Thirteen out of fourteen

> Georgia held 14 congressional elections in 2024. **Thirteen were won by more
> than 20 points.** The closest — Sanford Bishop's, by 12.7 — still wasn't close.

*Source: 1.4, 3.4.*

### Eight seats

> Georgians split their 2024 presidential vote almost down the middle — 51 to 49
> once you set the minor parties aside. Split 180 state house seats that way and
> you get 92 Republicans. Georgia's House seated **100**.

*Source: 2.3, statewide benchmark. Pair it with the chamber benchmark's +1 and
explain the difference — 90 uncontested races — rather than quoting whichever
number is larger.*

### The bipartisan part

> In the 2024 Georgia House, 47 Republicans and 43 Democrats ran with nobody on
> the ballot against them. Roughly half of the chamber's members faced no
> opponent at all. **This is not one party's problem.**

*Source: 3.2. This is your credibility line. Lead with it when you're accused of
partisanship, not after.*

---

# Guardrails, collected

Reread this list before anything goes public.

1. **Chamber vote share is distorted by uncontested races.** An unopposed winner
   contributes 100% to one party. Use `v_statewide` (2.2) as the partisan
   baseline whenever more than a handful of seats are uncontested, and read both
   benchmark columns in `v_proportional_allocation` (2.3) rather than one. The
   workbook knew this — its charts 5 and 6 carried "highly skewed by uncontested
   races" in their own titles. The size of the distortion in the 2024 Georgia
   House is 7 seats.

2. **The efficiency gap is only safe for the U.S. House**, where 2020–2024 had
   zero uncontested races. Do not publish the Georgia House's −0.2 as evidence
   of fairness.

3. **Proportional representation is not the legal standard.** *Rucho* (2019)
   closed the federal courts to partisan gerrymandering claims entirely. Use
   proportionality to describe a gap's size, never to assert a legal entitlement.

4. **2002 Georgia House is a special case in two places.** Filter on
   `seats_derivable` before charting seats or the line breaks. Separately, its
   multi-member districts let one voter cast up to three state house votes, so
   `votes_cast` exceeds the top-of-ticket `ballots_cast` and the voter-choice
   shares in 1.1 overflow to 131%. `v_voter_choice` has no flag for this —
   exclude the row explicitly. Race counts and raw vote totals are valid.

5. **Both directions, always.** Three of the four seat/vote inversions favored
   Democrats. Showing them costs nothing and buys the credibility that makes the
   congressional finding stick.

6. **"Competitive" is a threshold you picked** (53.5%). Show the story at 52%,
   55% and 60% too. `v_contest` carries all four flags.

7. **The roll-off baseline is the highest-turnout statewide race in the cycle** —
   president in presidential years, governor or U.S. Senate in midterms. For
   2022 that is U.S. Senate (3,935,924) rather than governor (3,653,926), so the
   2022 roll-off figure is slightly larger than the legacy workbook's.

8. **Workbook chart 2 was titled "Competitive Races — DRAFT, NOT for
   Distribution."** Someone marked it unfinished and it stayed that way for
   years. Find out what was wrong with it before reproducing it.

---

# Metabase semantic layer

Metabase v0.63. Models and Metrics are worth using, but only within a rule that
keeps them from becoming a fourth definition of your business logic.

## The rule: metadata in Models, logic in views

Most teams reach for Models because they cannot change their warehouse. You can.
The `v_*` views already are your curated surface, and `postgres_comments.sql`
already supplies field descriptions over JDBC.

So a Model here should be a **thin passthrough that adds only what Postgres
cannot express** — semantic types, display names, hidden columns. Nothing more.

**A calculation inside a Model is a definition only Metabase can see.** The build
publishes to three sinks that cannot drift — Postgres, Sheets, Parquet. Logic
added in Metabase is invisible to the Sheets add-on, invisible to the static
apps on GitHub Pages, and untestable by `tests/test_cdm.py`. When you are tempted
to write a `CASE` in a Model, it belongs in `fdp/cdm/aggregate.py` and should
surface as a view column — the same rule that already governs questions.

## Dashboard views vs Models — they do different jobs

The `v_*` dashboard views back the **questions** in this document: fixed shapes,
one per insight, so a chart is a `SELECT` with a filter. Models back **ad-hoc
exploration**: someone opening the query builder to ask something nobody
anticipated.

Do not build a Model on each dashboard view. They are already the right shape,
and wrapping each one in a Model adds a layer that can only go stale.

## Models to create

Build them with the **notebook editor, not SQL**: pick the table, apply no
filters, save as a Model. A GUI-based model inherits column metadata from the
table, so the `COMMENT ON` descriptions keep flowing. A SQL-based model makes you
re-enter every description by hand and it goes stale the moment a view changes.

| Model | Why | Curation |
|---|---|---|
| **`v_contest`** — build this first | one row per race; every metric below lives here | `margin_pct`, `winner_share_pct` → Percentage. `chamber_label`, `winner_party`, `district` → Category. Hide `is_competitive_052/_055/_06` unless someone is actively testing thresholds. |
| **`v_chamber_year`** | the seats-votes surface | all `*_pct` → Percentage |
| **`v_voter_choice`** | the roll-off surface | all `*_pct` → Percentage |

Leave `cycle_year` typed as a plain number, not a date — it is a label, and
Metabase will otherwise try to do date arithmetic on it.

**Skip** `v_county_results` (32,181 rows, a drill-down target rather than an
exploration surface) and `v_data_health` (one row — just a question).

**Do not enable model persistence.** The largest table here is 3,230 rows.
Caching that adds a moving part for no gain.

## Metrics — define them on `v_contest`

This is the decision that matters. `v_contest` is one row per race, so
aggregations over it compose correctly and break out by `cycle_year`,
`chamber_label`, `winner_party` or `district`. `v_chamber_year` and
`v_voter_choice` are already aggregated to one row per chamber-year, so a metric
defined there silently averages across rows.

The trap, in your own 2024 data:

| | 2024, all chambers |
|---|---|
| `Share([is_uncontested] = true)` over `v_contest` | **49.2%** ← correct |
| `Average([uncontested_pct])` over `v_chamber_year` | **36.3%** ← wrong |

The second weights every chamber equally, so the U.S. House's 14 races count as
much as the Georgia House's 180. Nobody who builds it will notice.

### One metric each — not one per chamber, not one per year

A Metric is an **aggregation, not an answer.** It takes no parameters because it
does not need any: the chamber and the cycle come from the *breakout* and
*filters* of the question that consumes it.

Define `Share Uncontested` once. A question that uses it with breakouts on
`cycle_year` and `chamber_label` returns all 39 chamber-years from that single
definition. Wire a dashboard filter to `cycle_year` and the same card answers
2024 or 2012 without the metric changing at all.

**Wire dashboard filters to `chamber`, not `chamber_label`.** The code is the
stable value; the label is display text that a future edit can reword.

The only filters that belong *inside* a metric are the ones that are part of its
definition rather than a user's choice:

| Filter | Metric | Why it is intrinsic |
|---|---|---|
| `[is_uncontested] = false` | Median Margin | uncontested races carry `margin_pct = 100` and would swamp the median |
| `[seats_derivable] = true` | the seats-votes trio | 2002 state house has 147 rows but elected 180 members |

Everything else — chamber, cycle, party — is slicing, and slicing belongs to the
question. A metric per chamber is how you end up with 39 metrics that drift.

Write every expression out in full rather than referencing one metric inside
another — metric-in-metric support varies by Metabase version and is not worth
the debugging.

**The chamber columns below are verification targets, not separate metrics.**
They are what one metric returns when broken out by chamber for 2024. A metric
that does not reproduce them is wrong.

### Tier 1 — the workhorses

| Metric | Expression | Ga House | Ga Senate | U.S. House |
|---|---|---|---|---|
| Races | `Count` | 180 | 56 | 14 |
| Votes Cast | `Sum([votes_total])` | 4,788,613 | 4,684,968 | 5,137,102 |
| Uncontested Races | `CountIf([is_uncontested] = true)` | 90 | 33 | 0 |
| Share Uncontested | `Share([is_uncontested] = true)` | 50.0% | 58.9% | 0.0% |
| Competitive Races | `CountIf([is_competitive] = true)` | 6 | 0 | 0 |
| Share Competitive | `Share([is_competitive] = true)` | 3.3% | 0.0% | 0.0% |
| Share Pre-Decided | `Share([is_uncontested] = true OR [margin_pct] >= 20)` | 85.6% | 91.1% | 92.9% |
| Median Margin (contested) | `Median([margin_pct])`, filtered `[is_uncontested] = false` | 28.7 | 30.5 | 33.6 |
| Votes in Uncontested Races | `SumIf([votes_total], [is_uncontested] = true)` | 2,127,186 | 2,504,427 | 0 |

**Median Margin (contested)** is the addition worth making that no dashboard
above uses. It is threshold-free — no 53.5% to defend.

**The filter is not optional.** Uncontested races carry `margin_pct = 100`, so
an unfiltered median over the 2024 Georgia House returns **90.8** and is really
just measuring the uncontested share. Filtered to contested races it returns
**28.7**, which is the number worth saying:

> Even among the Georgia House races that had two candidates on the ballot in
> 2024, the typical one was won by **29 points**.

### Tier 2 — the seats-votes trio

Verified to reproduce `v_chamber_year` exactly in every cycle, while remaining
breakable-out by any dimension:

| Metric | Expression | Ga House | Ga Senate | U.S. House |
|---|---|---|---|---|
| Republican Seat Share | `Share([winner_party] = "R")` | 55.6% | 58.9% | 64.3% |
| Republican Vote Share | `Sum([votes_r]) / Sum([votes_total])` | 55.0% | 55.7% | 52.6% |
| Seats-Votes Gap (R) | `Share([winner_party] = "R") - Sum([votes_r]) / Sum([votes_total])` | +0.6 | +3.3 | +11.7 |

**Bake `[seats_derivable] = true` into all three as a metric filter.** 2002 state
house has 147 rows in `v_contest` but elected 180 members, so an unfiltered seat
share divides by the wrong denominator.

### Tier 3 — the efficiency gap

`v_contest` carries the wasted-vote components as columns precisely so this stays
a sum rather than `CASE` logic re-typed into an expression:

| Metric | Expression | Ga House | Ga Senate | U.S. House |
|---|---|---|---|---|
| Efficiency Gap (R) | `(Sum([wasted_votes_d]) - Sum([wasted_votes_r])) / Sum([votes_two_party])` | −0.2% | +1.6% | **+11.9%** |

This is the most quotable metric here and the most misusable, so **put the
caveat in the metric's own description field** where it travels with the number:

> Only interpretable where uncontested races are few. The Georgia House's
> near-zero score reflects 90 uncontested races, not fairness.

See guardrail 2 below.

## Why not PostgreSQL functions

Metabase's query builder cannot call one. A function would be reachable only
from a raw SQL question, which loses breakouts, reuse, and any presence in the
semantic layer — everything Metrics exist to provide. The one case that might
have justified one, variable competitiveness thresholds, is already covered by
the four `is_competitive_*` columns on `v_contest`.

Postgres's job in this stack is the views. Aggregation belongs in Metabase;
definitions belong in `fdp/cdm/aggregate.py`. A function would sit between the
two and be visible to neither.

## What not to make a metric

**The village-of-100 percentages (1.1).** Their denominator is statewide
`ballots_cast`, which does not exist in `v_contest`. Defining "Share of Votes
With No Choice" there gives **44.4%** (2,127,186 ÷ 4,788,613 chamber votes), not
the **41%** on the dashboard (÷ 5,250,066 ballots). Both are correct and they
answer different questions — but two near-identical numbers with different
denominators loose in one dashboard is how an organisation gets caught
contradicting itself. Keep 1.1 as a SQL question.

**Anything on `v_chamber_year` or `v_voter_choice`.** Pre-aggregated. Leave them
as questions.

## The layering, end to end

```
fdp/cdm/aggregate.py     business definitions live here, tested
        v
fdga.v_* views           definitions surface as columns, documented
        v
Metabase Models          display metadata ONLY
        v
Metabase Metrics         aggregations over the models
        v
Questions and dashboards
```

Each layer adds only what the one below genuinely cannot express. Finding
yourself adding something at one layer that *could* have lived lower down is the
signal to push it down instead.

---

# Not yet buildable

These need `dim_district` (open task #7), which gives actual results and ensemble
counterfactuals a shared join key.

- **"A neutral computer would have drawn 7–7."** Comparing the enacted map to the
  GerryChain and ALARM ensembles is the single most powerful chart this project
  could produce, and it is one join away. It converts "the gap is 11.9%" into
  "out of 100,000 neutrally drawn maps, none produced a delegation this
  lopsided" — if that is in fact what the ensembles show.
- **District-level trends across redistricting.** District numbers are reused
  across map eras, so any join on `(chamber, district)` without an era is
  silently wrong. HD-145 in 2022 is not the same geography as HD-145 in 2020.
- **Precise era annotations** on 2.4. Build from
  `fdp/config/schema/redistricting_history.yml` rather than inferring eras from
  district counts — some Georgia changes are mid-decade and not decade-aligned.
