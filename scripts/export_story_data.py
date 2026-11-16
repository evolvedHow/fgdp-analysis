#!/usr/bin/env python3
"""Export the voting-results data story bundle from the FDP common data model.

Reads parquet + GeoJSON straight from ``fdp/data/repos/main`` and writes a
single static JSON bundle consumed by the Vite front-end. This keeps the
published site self-sufficient (GitHub Pages / Modal static hosting): no
database, no API, no server at runtime.

Outputs
-------
public/data/story.json
    meta           election + chamber dictionaries
    statewide      statewide results by cycle (fdga/statewide.parquet)
    chamber_year   seats-vs-votes by chamber/cycle (fdga/chamber_year.parquet)
    contests       per chamber/cycle district results (fdga/contests.parquet)
    counties       simplified county GeoJSON with lean/demographic props
    county_votes   county-level party totals per office/cycle (fdga/facts.parquet)
    precincts      2,698 VTDs: name, county, centroid, lean, turnout, VAP

Usage
-----
    cd ~/codebox/fgdp/fdp && .venv/bin/python ../scripts/export_story_data.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "fdp" / "data" / "repos" / "main"
OUT = ROOT / "public" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# Plan pairs used by the "map swap" analysis: the same ballots counted under two
# different sets of lines. Both GeoJSONs carry per-district election signals
# computed from the same VTD votes, so the seat difference is attributable to the
# lines alone (no spatial join, no estimation).
#
# Two transitions per chamber, matching the two comparisons FDGA/PGP published:
#   kind="remedy"     the 2021-23 lines → the 2024 court-ordered remedial lines
#   kind="enactment"  the pre-2021 map → the 2021 enacted map, i.e. the deck's own
#                     "Previous Map → Enacted Map" (pp. 16, 21, 22, 38, 53)
MAP_PLANS = [
    {
        "chamber": "state_house",
        "chamber_label": "GA House",
        "kind": "remedy",
        "event_label": "the 2024 remedial redistricting",
        "prior": "boundaries/house/house_enacted_2123_2024update.geojson",
        "prior_label": "2021-23 lines",
        "prior_years": "2022-2024",
        "current": "boundaries/house/house_enacted_24_2024update.geojson",
        "current_label": "2024 lines",
        "current_years": "2024",
        "displacement": "displacement/house_2123_to_24.json",
    },
    {
        "chamber": "state_house",
        "chamber_label": "GA House",
        "kind": "enactment",
        "event_label": "the 2021 redistricting",
        "prior": "boundaries/house/house15_census20.geojson",
        "prior_label": "2015 lines",
        "prior_years": "2018-2021",
        "current": "boundaries/house/enacted_house22.geojson",
        "current_label": "2021 enacted lines",
        "current_years": "2018-2021",
        "displacement": "displacement/house_15_to_22.json",
    },
    {
        "chamber": "state_senate",
        "chamber_label": "GA Senate",
        "kind": "remedy",
        "event_label": "the 2024 remedial redistricting",
        "prior": "boundaries/senate/senate_enacted_2123_2024update.geojson",
        "prior_label": "2021-23 lines",
        "prior_years": "2022-2024",
        "current": "boundaries/senate/senate_enacted_24_2024update.geojson",
        "current_label": "2024 lines",
        "current_years": "2024",
        "displacement": "displacement/senate_2123_to_24.json",
    },
    {
        "chamber": "state_senate",
        "chamber_label": "GA Senate",
        "kind": "enactment",
        "event_label": "the 2021 redistricting",
        "prior": "boundaries/senate/senate14_census20.geojson",
        "prior_label": "2014 lines",
        "prior_years": "2018-2021",
        "current": "boundaries/senate/enacted_senate22.geojson",
        "current_label": "2021 enacted lines",
        "current_years": "2018-2021",
        "displacement": "displacement/senate_14_to_22.json",
    },
    {
        "chamber": "us_house",
        "chamber_label": "U.S. House",
        "kind": "remedy",
        "event_label": "the 2024 remedial redistricting",
        "prior": "boundaries/congress/congress_enacted_2123_2024update.geojson",
        "prior_label": "2021-23 lines",
        "prior_years": "2022-2024",
        "current": "boundaries/congress/congress_enacted_24_2024update.geojson",
        "current_label": "2024 lines",
        "current_years": "2024",
        "displacement": "displacement/congress_2123_to_24.json",
    },
    {
        "chamber": "us_house",
        "chamber_label": "U.S. House",
        "kind": "enactment",
        "event_label": "the 2021 redistricting",
        "prior": "boundaries/congress/congress12_census20.geojson",
        "prior_label": "2012 lines",
        "prior_years": "2018-2021",
        "current": "boundaries/congress/enacted_congress22.geojson",
        "current_label": "2021 enacted lines",
        "current_years": "2018-2021",
        "displacement": "displacement/congress_21_to_22.json",
    },
]

# Court record behind the 2024 remedial plans. Every claim the story makes about
# the law links to one of these; the raw displacement figure is arithmetic, not a
# legal threshold, and is labelled that way.
MAP_SOURCES = [
    {
        "id": "alpha-phi-alpha-order-2023",
        "title": "Alpha Phi Alpha Fraternity v. Raffensperger — order approving the 2023 remedial plans",
        "publisher": "U.S. District Court, N.D. Ga., Dec. 28, 2023",
        "url": "https://redistricting.lls.edu/wp-content/uploads/GA-apa-20231228-order-approving-plans.pdf",
        "note": "Approves HB 1EX / SB 1EX for 2024; holds that redistricting with an eye to partisan advantage does not alone violate Section 2.",
    },
    {
        "id": "alpha-phi-alpha-case",
        "title": "Alpha Phi Alpha Fraternity v. Raffensperger — case history",
        "publisher": "All About Redistricting (Loyola Law School)",
        "url": "https://redistricting.lls.edu/case/alpha-phi-alpha-v-raffensperger/",
        "note": "Oct. 26, 2023: the 2021 House and Senate plans were struck down under Section 2 of the Voting Rights Act.",
    },
    {
        "id": "vra-section-2",
        "title": "Section 2 of the Voting Rights Act",
        "publisher": "U.S. Department of Justice",
        "url": "https://www.justice.gov/crt/section-2-voting-rights-act",
        "note": "The federal statute the 2021 plans were found to violate.",
    },
    {
        "id": "rucho",
        "title": "Rucho v. Common Cause, 588 U.S. 684 (2019)",
        "publisher": "Supreme Court of the United States",
        "url": "https://www.supremecourt.gov/opinions/18pdf/18-422_9ol1.pdf",
        "note": "Federal courts cannot hear partisan-gerrymandering claims; only state law and Section 2 constrain the lines.",
    },
    {
        "id": "miller",
        "title": "Miller v. Johnson, 515 U.S. 900 (1995)",
        "publisher": "Cornell Legal Information Institute",
        "url": "https://www.law.cornell.edu/supremecourt/text/515/900",
        "note": "A race-based districting decision must be narrowly tailored and respect traditional districting principles.",
    },
]


# Election signal keys map to vtd_composite.parquet columns.
ELECTIONS = [
    {"key": "composite", "label": "2018–2024 composite", "column": "composite_dem_pct"},
    {"key": "g18", "label": "2018 Governor", "column": "dem_pct_2018_gov"},
    {"key": "p20", "label": "2020 President", "column": "dem_pct_2020_pres"},
    {"key": "r21", "label": "2021 U.S. Senate runoff", "column": "dem_pct_2021_war_runoff"},
    {"key": "g22", "label": "2022 Governor", "column": "dem_pct_2022_gov"},
    {"key": "s22", "label": "2022 U.S. Senate", "column": "dem_pct_2022_uss"},
    {"key": "p24", "label": "2024 President", "column": "dem_pct_2024_pres"},
]

CHAMBERS = [
    {"key": "us_house", "office": "us_house", "label": "U.S. House", "seats": 14},
    {"key": "state_house", "office": "state_house", "label": "GA House", "seats": 180},
    {"key": "state_senate", "office": "state_senate", "label": "GA Senate", "seats": 56},
]

OFFICE_TO_CHAMBER = {c["office"]: c["key"] for c in CHAMBERS}
CHAMBER_TO_OFFICE = {c["key"]: c["office"] for c in CHAMBERS}


# Minority-representation thresholds, taken from FDGA's own scorecard config
# (`influence_min_threshold` / `influence_max_threshold`) and from the Voting
# Rights Act majority test. These are the same bands the 2022 FDGA / Princeton
# Gerrymandering Project evaluation used:
#   majority  >= 50% of the group's voting-age population
#   influence  37% - 50%
MAJORITY_THRESHOLD = 0.50
INFLUENCE_LO = 0.37
INFLUENCE_HI = 0.50

# Plan GeoJSON properties carrying racial/ethnic composition. The 2024 remedial
# plans store ready-made shares (`pct_*`); the 2021-23 plans store counts
# (`wvap`, `bvap`, ...) against `tvap`. Both spellings resolve to the same
# measure, verified district-by-district where the two plans share boundaries.
# `pct_bvp` / `bvap` is any-part Black VAP — the more expansive definition the
# 2022 FDGA/PGP evaluation also used for enacted-map counts — and is the only
# Black measure present in both plan vintages, so it is the comparison basis.
DEMOGRAPHIC_FIELDS = {
    "white": ("pct_wvap_al", "wvap"),
    "black": ("pct_bvp", "bvap"),
    "blackAlone": ("pct_bvap_al", None),
    "hispanic": ("pct_hvp", "hvap"),
    "asian": ("pct_avp", "avap"),
    "asianAlone": ("pct_avap_al", None),
}


def f(x):
    """Round floats for smaller payloads; pass through None."""
    return None if x is None else round(float(x), 5)


def demographic_shares(props):
    """Resolve one district's racial/ethnic VAP shares from either plan schema.

    Args:
        props (dict): a plan GeoJSON feature's ``properties``.

    Returns:
        dict: shares for ``white``, ``black`` (any part), ``blackAlone``,
        ``hispanic``, ``asian`` (any part), ``asianAlone`` and the derived
        ``minority`` (all non-white VAP). Values are ``None`` when the plan
        carries neither the share nor the count.
    """
    tvap = float(props.get("tvap") or 0) or None
    out = {}
    for key, (pct_field, count_field) in DEMOGRAPHIC_FIELDS.items():
        value = props.get(pct_field)
        if value is None and count_field and tvap:
            count = props.get(count_field)
            value = float(count) / tvap if count is not None else None
        out[key] = f(value)

    if props.get("bipoc_vap") is not None and tvap:
        out["minority"] = f(float(props["bipoc_vap"]) / tvap)
    elif out["white"] is not None:
        out["minority"] = f(max(0.0, 1.0 - out["white"]))
    else:
        out["minority"] = None
    return out


def classify_district(shares):
    """Assign one district to the representation categories FDGA reports.

    Categories follow the 2022 FDGA/PGP evaluation: a district is a *majority*
    district when a single group reaches 50% of VAP, a *coalition* district when
    all minorities together reach 50% but no single group does, and an
    *influence* district when a group sits in the 37-50% band.

    Args:
        shares (dict): output of :func:`demographic_shares`.

    Returns:
        dict: booleans for ``blackMajority``, ``blackInfluence``,
        ``coalitionMajority``, ``minorityInfluence``, ``hispanicMajority``,
        ``hispanicInfluence``, ``asianInfluence`` and ``whiteMajority``.
    """
    black = shares.get("black")
    hisp = shares.get("hispanic")
    asian = shares.get("asian")
    white = shares.get("white")
    minority = shares.get("minority")

    def band(v):
        return v is not None and INFLUENCE_LO <= v < INFLUENCE_HI

    return {
        "blackMajority": black is not None and black >= MAJORITY_THRESHOLD,
        "blackInfluence": band(black),
        "coalitionMajority": (
            minority is not None
            and minority >= MAJORITY_THRESHOLD
            and not (black is not None and black >= MAJORITY_THRESHOLD)
        ),
        "minorityInfluence": band(minority),
        "hispanicMajority": hisp is not None and hisp >= MAJORITY_THRESHOLD,
        "hispanicInfluence": band(hisp),
        "asianInfluence": band(asian),
        "whiteMajority": white is not None and white >= MAJORITY_THRESHOLD,
    }


CATEGORIES = [
    "blackMajority",
    "blackInfluence",
    "coalitionMajority",
    "minorityInfluence",
    "hispanicMajority",
    "hispanicInfluence",
    "asianInfluence",
    "whiteMajority",
]


def representation_summary(plan_rows):
    """Count representation categories across one plan's districts.

    Args:
        plan_rows (list[dict]): rows with ``district`` and the
            :func:`classify_district` keys.

    Returns:
        dict: ``counts`` (category → number of districts) and ``districts``
        (category → sorted district numbers), so the front-end can name the
        districts behind every count the way the 2022 evaluation did.
    """
    counts = {c: 0 for c in CATEGORIES}
    districts = {c: [] for c in CATEGORIES}
    for row in plan_rows:
        for c in CATEGORIES:
            if row.get(c):
                counts[c] += 1
                districts[c].append(row["district"])
    for c in CATEGORIES:
        districts[c].sort()
    return {"counts": counts, "districts": districts}


def rows(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def load_statewide(con):
    data = rows(con, f"SELECT * FROM '{REPO}/fdga/statewide.parquet' ORDER BY cycle_year")
    return [
        {
            "year": int(r["cycle_year"]),
            "date": r["election_date"],
            "type": r["election_type"],
            "office": r["office"],
            "winnerParty": r["winner_party"],
            "winnerName": r["winner_name"],
            "winnerShare": f(r["winner_share"]),
            "total": int(r["votes_total"] or 0),
            "r": int(r["votes_r"] or 0),
            "d": int(r["votes_d"] or 0),
            "other": int(r["votes_other"] or 0),
            "pctR": f(r["pct_votes_r"]),
            "pctD": f(r["pct_votes_d"]),
        }
        for r in data
    ]


def load_chamber_year(con):
    data = rows(
        con,
        f"""
        SELECT * FROM '{REPO}/fdga/chamber_year.parquet'
        ORDER BY chamber, cycle_year
        """,
    )
    out = []
    for r in data:
        out.append(
            {
                "year": int(r["cycle_year"]),
                "chamber": r["chamber"],
                "seats": int(r["seats_total_expected"] or 0),
                "seatsR": r["seats_r"],
                "seatsD": r["seats_d"],
                "pctSeatsR": f(r["pct_seats_r"]),
                "pctSeatsD": f(r["pct_seats_d"]),
                "pctVotesR": f(r["pct_votes_r"]),
                "pctVotesD": f(r["pct_votes_d"]),
                "racesTotal": int(r["races_total"] or 0),
                "racesContested": int(r["races_contested"] or 0),
                "racesUncontested": int(r["races_uncontested"] or 0),
                "racesCompetitive": int(r["races_competitive"] or 0),
                "votesTotal": int(r["votes_total"] or 0),
                "votesR": int(r["votes_r"] or 0),
                "votesD": int(r["votes_d"] or 0),
                "votesOther": int(r["votes_other"] or 0),
                "gapR": f(r["seats_votes_gap_r"]),
            }
        )
    return out


def load_contests(con):
    data = rows(
        con,
        f"""
        SELECT cycle_year, office, district, winner_party, winner_name,
               winner_votes, winner_share, runner_up_party, runner_up_votes,
               margin, margin_share, votes_total, votes_r, votes_d, votes_other,
               is_uncontested, is_competitive_055
        FROM '{REPO}/fdga/contests.parquet'
        WHERE office IN ('us_house','state_house','state_senate')
        ORDER BY cycle_year, office, district
        """,
    )
    out = {}
    for r in data:
        key = OFFICE_TO_CHAMBER[r["office"]]
        year = str(int(r["cycle_year"]))
        out.setdefault(key, {}).setdefault(year, []).append(
            {
                "district": r["district"],
                "winnerParty": r["winner_party"],
                "winnerName": r["winner_name"],
                "winnerVotes": int(r["winner_votes"] or 0),
                "winnerShare": f(r["winner_share"]),
                "runnerUpParty": r["runner_up_party"],
                "runnerUpVotes": int(r["runner_up_votes"] or 0),
                "margin": int(r["margin"] or 0),
                "marginShare": f(r["margin_share"]),
                "total": int(r["votes_total"] or 0),
                "r": int(r["votes_r"] or 0),
                "d": int(r["votes_d"] or 0),
                "other": int(r["votes_other"] or 0),
                "uncontested": bool(r["is_uncontested"]),
                "competitive": bool(r["is_competitive_055"]),
            }
        )
    return out


def load_county_votes(con):
    """County-level party totals per office/cycle for the drill-down panel."""
    data = rows(
        con,
        f"""
        SELECT cycle_year, office, county,
               SUM(votes) FILTER (WHERE party = 'D') AS d,
               SUM(votes) FILTER (WHERE party = 'R') AS r,
               SUM(votes) FILTER (WHERE party NOT IN ('D','R')) AS other,
               SUM(votes) AS total
        FROM '{REPO}/fdga/facts.parquet'
        WHERE office IN ('us_house','state_house','state_senate','governor','president','us_senate')
        GROUP BY 1,2,3
        ORDER BY 1,2,3
        """,
    )
    out = {}
    for r in data:
        office = r["office"]
        year = str(int(r["cycle_year"]))
        # County keys are not spelled consistently across ingests: the 2026 rows
        # arrive as "APPLING COUNTY" where every earlier cycle is "APPLING".
        # Normalise so cycles can be compared county-by-county.
        county = (r["county"] or "").strip().upper()
        if county.endswith(" COUNTY"):
            county = county[: -len(" COUNTY")].strip()
        if not county:
            continue
        d = int(r["d"] or 0)
        rep = int(r["r"] or 0)
        total = int(r["total"] or 0)
        out.setdefault(office, {}).setdefault(year, {})[county] = {
            "d": d,
            "r": rep,
            "other": int(r["other"] or 0),
            "total": total,
            "pctD": f(d / total) if total else None,
        }
    return out


def load_counties():
    src = json.loads((REPO / "boundaries" / "reference" / "county.geojson").read_text())
    # county-level lean/demographics derived from the VTD composite
    con = duckdb.connect()
    stats = {
        r["countyfp"]: r
        for r in rows(
            con,
            f"""
            SELECT substr(GEOID20, 3, 3) AS countyfp,
                   SUM(actual_total_votes) AS turnout,
                   SUM(actual_dem_votes) AS dem_votes,
                   SUM(VAP_MOD) AS vap,
                   SUM(bvap_tot) AS bvap,
                   SUM(bvap_blk) AS bvap_blk,
                   SUM(bvap_coalition) AS bvap_coalition,
                   AVG(composite_dem_pct) AS composite
            FROM '{REPO}/vtd/vtd_composite.parquet'
            GROUP BY 1
            """,
        )
    }
    feats = []
    for ft in src["features"]:
        props = ft["properties"]
        fips = str(props["COUNTYFP20"]).zfill(3)
        name = props["COUNTY"]
        st = stats.get(fips, {})
        geom = shape(ft["geometry"]).simplify(0.012, preserve_topology=True)
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "fips": fips,
                    "name": name,
                    "turnout": int(st.get("turnout") or 0),
                    "demVotes": int(st.get("dem_votes") or 0),
                    "vap": int(st.get("vap") or 0),
                    "bvap": int(st.get("bvap") or 0),
                    "bvapBlack": int(st.get("bvap_blk") or 0),
                    "bvapCoalition": int(st.get("bvap_coalition") or 0),
                    "composite": f(st.get("composite")),
                },
                "geometry": mapping(geom),
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def load_precincts():
    county_names = {}
    counties = json.loads((REPO / "boundaries" / "reference" / "county.geojson").read_text())
    for ft in counties["features"]:
        county_names[str(ft["properties"]["COUNTYFP20"]).zfill(3)] = ft["properties"]["COUNTY"]

    con = duckdb.connect()
    comp = {
        r["GEOID20"]: r
        for r in rows(con, f"SELECT * FROM '{REPO}/vtd/vtd_composite.parquet'")
    }
    precincts = []
    geo = json.loads((REPO / "boundaries" / "reference" / "precinct_scored.geojson").read_text())
    for ft in geo["features"]:
        p = ft["properties"]
        geoid = p["geoid20"]
        row = comp.get(geoid, {})
        coords = ft["geometry"]["coordinates"]
        if ft["geometry"]["type"] == "Point":
            lon, lat = coords[0], coords[1]
        else:
            # centroid fallback for any non-point geometry
            from shapely.geometry import shape as _shape

            c = _shape(ft["geometry"]).centroid
            lon, lat = c.x, c.y
        fips = str(p["countyfp20"]).zfill(3)
        pct = {e["key"]: f(row.get(e["column"])) for e in ELECTIONS if row}
        precincts.append(
            {
                "geoid": geoid,
                "name": (p.get("name20") or "").strip().title(),
                "countyFips": fips,
                "county": county_names.get(fips, fips),
                "lat": round(float(lat), 5),
                "lon": round(float(lon), 5),
                "pct": pct,
                "vap": int(row.get("VAP_MOD") or p.get("tvap") or 0),
                "bvap": int(row.get("bvap_tot") or 0),
                "bvapBlack": int(row.get("bvap_blk") or 0),
                "bvapCoalition": int(row.get("bvap_coalition") or 0),
                "demVotes": int(row.get("actual_dem_votes") or 0),
                "turnout": int(row.get("actual_total_votes") or 0),
                "pop": int(p.get("pop") or 0),
            }
        )
    precincts.sort(key=lambda x: (x["county"], x["name"]))
    return precincts


# FDGA's own benchmark scorecards: each one scores an enacted plan against
# thousands of neutral ReCom ensembles drawn without any partisan or demographic
# data. A percentile is the share of neutral maps that score below the enacted
# map, so "p5–p95" is the range a geography-driven process normally produces.
ENSEMBLE_FILES = {
    "state_house": (
        "ensemble/fdga_baseline_benchmarks_2601_house_scorecard.json",
        "GA House",
    ),
    "state_senate": (
        "ensemble/fdga_baseline_benchmarks_2601_senate_scorecard.json",
        "GA Senate",
    ),
    "us_house": (
        "ensemble/fdga_baseline_benchmarks_2601_congress_scorecard.json",
        "U.S. House",
    ),
}

# Metrics shown in the percentile panel. `direction` records which way is
# better without implying a party preference: more competitive seats is the one
# normative goal, symmetry metrics are better when nearer zero, and safe-seat
# counts are reported for both parties so neither is singled out.
ENSEMBLE_METRICS = [
    {
        "key": "comp_seats_10pt",
        "label": "Within 10 pts",
        "group": "competition",
        "unit": "seats",
        "direction": "higher",
        "note": "The share of districts where the result is genuinely in play.",
    },
    {
        "key": "comp_seats_7pt",
        "label": "Within 7 pts",
        "group": "competition",
        "unit": "seats",
        "direction": "higher",
        "note": "A stricter version of the same test.",
    },
    {
        "key": "dem_seats",
        "label": "Seats leaning D",
        "group": "proportionality",
        "unit": "seats",
        "direction": "neutral",
        "note": "A measuring stick for seat–vote proportionality, not a goal.",
    },
    {
        "key": "efficiency_gap",
        "label": "Efficiency gap",
        "group": "symmetry",
        "unit": "share",
        "direction": "lower",
        "note": "How differently the two parties' votes convert into seats. Zero is even.",
    },
    {
        "key": "mean_median",
        "label": "Median–mean gap",
        "group": "symmetry",
        "unit": "points",
        "direction": "lower",
        "note": "How far the middle district sits from the average district. Zero is even.",
    },
    {
        "key": "dem_safe_seats",
        "label": "Safe D seats",
        "group": "safe",
        "unit": "seats",
        "direction": "lower",
        "note": "Seats that are not realistically contested.",
    },
    {
        "key": "rep_safe_seats",
        "label": "Safe R seats",
        "group": "safe",
        "unit": "seats",
        "direction": "lower",
        "note": "Seats that are not realistically contested.",
    },
]


def load_ensemble():
    """Percentile benchmarks from FDGA's neutral-ensemble scorecards.

    Each scorecard compares one enacted plan with tens of thousands of ReCom
    draws made without partisan or demographic data. We keep the percentile
    ranks, the 5th/50th/95th percentiles, and a normalised 40-bin histogram, and
    drop the per-draw arrays, which are large and not needed for display.
    """
    out = {}
    for chamber, (rel, label) in ENSEMBLE_FILES.items():
        path = REPO / rel
        if not path.exists():
            print(f"  ! benchmark scorecard missing: {rel}")
            continue
        doc = json.loads(path.read_text())
        run = doc.get("run") or {}
        election = (doc.get("elections") or [{}])[0]
        raw = election.get("metrics") or {}

        metrics = []
        for spec in ENSEMBLE_METRICS:
            m = raw.get(spec["key"])
            if not m:
                continue
            hist = m.get("histogram") or {}
            counts = hist.get("counts") or []
            total = sum(counts) or 1
            a_grade = m.get("a_grade_range") or {}
            metrics.append(
                {
                    **spec,
                    "scorecardLabel": m.get("label"),
                    "headline": m.get("headline"),
                    "takeaway": m.get("takeaway"),
                    "grade": m.get("grade"),
                    "enacted": f(m.get("enacted")),
                    "pctRank": f((m.get("pct_rank") or 0.0) / 100.0),
                    "p5": f(hist.get("p5")),
                    "p25": f(hist.get("p25")),
                    "p50": f(hist.get("p50")),
                    "p75": f(hist.get("p75")),
                    "p95": f(hist.get("p95")),
                    "mean": f(hist.get("mean")),
                    # The scorecard's own "A" band: the range a plan must land in
                    # to earn the top grade. This is the second benchmark column
                    # in the FDGA/PGP evaluation tables ("98% of 1M maps" vs
                    # "'A' grade").
                    "aGradeLo": f(a_grade.get("lo")),
                    "aGradeHi": f(a_grade.get("hi")),
                    "hist": {
                        "edges": [f(e) for e in (hist.get("edges") or [])],
                        "counts": [round(c / total, 4) for c in counts],
                    },
                }
            )

        # Minority-representation benchmarks: how many Black-majority, coalition
        # and influence districts the neutral ensemble produces, against the
        # enacted map. Absent for chambers whose scorecard carries no CVAP run.
        demo_metrics = []
        demo = doc.get("demographics") or {}
        for key, val in (demo.get("metrics") or {}).items():
            if not val:
                continue
            hist = val.get("histogram") or {}
            counts = hist.get("counts") or []
            total = sum(counts) or 1
            a_grade = val.get("a_grade_range") or {}
            demo_metrics.append(
                {
                    "key": key,
                    "label": val.get("label"),
                    "category": val.get("category"),
                    "description": val.get("description"),
                    "takeaway": val.get("takeaway"),
                    "grade": val.get("grade"),
                    "enacted": f(val.get("enacted")),
                    "pctRank": f((val.get("pct_rank") or 0.0) / 100.0),
                    "p5": f(hist.get("p5")),
                    "p25": f(hist.get("p25")),
                    "p50": f(hist.get("p50")),
                    "p75": f(hist.get("p75")),
                    "p95": f(hist.get("p95")),
                    "mean": f(hist.get("mean")),
                    "aGradeLo": f(a_grade.get("lo")),
                    "aGradeHi": f(a_grade.get("hi")),
                    "hist": {
                        "edges": [f(e) for e in (hist.get("edges") or [])],
                        "counts": [round(c / total, 4) for c in counts],
                    },
                }
            )

        config = doc.get("config") or {}

        # Geographic and demographic benchmark records. The demographic grades
        # are kept as data for a later representation panel but are not shown as
        # letter grades here: a district count above the neutral median is a
        # remedy, not a fault, so the scorecard's letter would mislead.
        benchmarks = {}
        for group in ("compactness", "grades"):
            for key, val in (doc.get(group) or {}).items():
                if not val:
                    continue
                hist = val.get("histogram") or {}
                benchmarks[key] = {
                    "label": val.get("label"),
                    "grade": val.get("grade"),
                    "enacted": f(val.get("enacted")),
                    "pctRank": f((val.get("pct_rank") or 0.0) / 100.0),
                    "p5": f(hist.get("p5")),
                    "p50": f(hist.get("p50")),
                    "p95": f(hist.get("p95")),
                    "takeaway": val.get("takeaway"),
                }

        out[chamber] = {
            "chamber": chamber,
            "label": label,
            "run": {
                "draws": int(run.get("n_draws") or 0),
                "districts": int(run.get("n_districts") or 0),
                "algorithm": run.get("algorithm"),
                "date": run.get("date"),
                "election": election.get("label"),
                "source": run.get("source"),
            },
            "metrics": metrics,
            "demographics": demo_metrics,
            "demographicSource": {
                "source": demo.get("source"),
                "year": demo.get("year"),
            },
            "thresholds": {
                "influenceLo": f(config.get("influence_min_threshold") or INFLUENCE_LO),
                "influenceHi": f(config.get("influence_max_threshold") or INFLUENCE_HI),
                "competitive": [f(t) for t in (config.get("competitive_thresholds") or [])],
            },
            "benchmarks": benchmarks,
        }
    return out


def load_map_effect():
    """Same voters, different lines: both published map transitions, per chamber.

    Each plan GeoJSON already carries per-district D share for the same six
    election signals, produced from one VTD vote file. Reading the same votes
    through the prior and current lines therefore isolates the effect of the
    boundaries themselves.

    Returns:
        tuple[dict, dict]: ``(remedy, enactment)``. ``remedy`` maps chamber → the
        2021-23 → 2024 court-ordered transition; ``enactment`` maps chamber → the
        pre-2021 → 2021 enacted transition FDGA/PGP's 2022 deck compared. Both
        records share one shape, so the front-end renders either unchanged.
    """
    out = {}
    hist = {}
    for plan in MAP_PLANS:
        prior = json.loads((REPO / plan["prior"]).read_text())
        current = json.loads((REPO / plan["current"]).read_text())
        a = {int(ft["properties"]["district"]): ft["properties"] for ft in prior["features"]}
        b = {int(ft["properties"]["district"]): ft["properties"] for ft in current["features"]}
        districts = sorted(set(a) & set(b))

        # Seat counts and flips for every election signal the plans carry.
        signals = []
        for election in ELECTIONS:
            key = f"{election['key']}_pct_dem"
            if key not in next(iter(a.values())):
                continue
            pairs = [
                (d, a[d][key], b[d][key])
                for d in districts
                if a[d].get(key) is not None and b[d].get(key) is not None
            ]
            if not pairs:
                continue
            flips = [
                {
                    "district": d,
                    "priorPct": f(x),
                    "currentPct": f(y),
                    "shiftPts": f((y - x) * 100),
                    "priorParty": "D" if x > 0.5 else "R",
                    "currentParty": "D" if y > 0.5 else "R",
                    "vap": int(a[d].get("tvap") or 0),
                }
                for d, x, y in pairs
                if (x > 0.5) != (y > 0.5)
            ]
            signals.append(
                {
                    "key": election["key"],
                    "label": election["label"],
                    "priorSeatsD": sum(1 for _, x, _y in pairs if x > 0.5),
                    "currentSeatsD": sum(1 for _, _x, y in pairs if y > 0.5),
                    "flips": sorted(flips, key=lambda r: -abs(r["shiftPts"])),
                }
            )

        # Core district table for the 2024 presidential vote — the "election"
        # the map swap is measured on — plus each district's racial/ethnic VAP
        # composition under both plans, which drives the representation section.
        rows_out = []
        for d in districts:
            x = a[d].get("p24_pct_dem")
            y = b[d].get("p24_pct_dem")
            if x is None or y is None:
                continue
            prior_shares = demographic_shares(a[d])
            current_shares = demographic_shares(b[d])
            row = {
                "district": d,
                "priorPct": f(x),
                "currentPct": f(y),
                "shiftPts": f((y - x) * 100),
                "priorPartisan": f(a[d].get("partisan")),
                "currentPartisan": f(b[d].get("partisan")),
                "vap": int(a[d].get("tvap") or 0),
                "priorBvap": f(a[d].get("pct_bvp")),
                "currentBvap": f(b[d].get("pct_bvp")),
                "priorDemo": prior_shares,
                "currentDemo": current_shares,
            }
            row.update({f"prior_{c}": v for c, v in classify_district(prior_shares).items()})
            row.update({f"current_{c}": v for c, v in classify_district(current_shares).items()})
            rows_out.append(row)

        def distribution(plan_map):
            """Competitiveness shape of one plan, measured on the 2024 vote."""
            margins = sorted(
                abs(v["p24_pct_dem"] - 0.5) * 100
                for v in plan_map.values()
                if v.get("p24_pct_dem") is not None
            )
            leans = sorted(
                v["p24_pct_dem"] for v in plan_map.values() if v.get("p24_pct_dem") is not None
            )
            n = len(leans) or 1
            return {
                "seats": len(leans),
                "competitive5": sum(1 for m in margins if m < 5),
                "competitive10": sum(1 for m in margins if m < 10),
                "meanMargin": f(sum(margins) / n),
                "medianMargin": f(margins[n // 2]) if margins else None,
                "meanLean": f(sum(leans) / n),
                "medianLean": f(leans[n // 2]) if leans else None,
            }

        # Districts that crossed 50% Black voting-age population. In all three
        # chambers this reproduces the number of remedy districts the court
        # ordered, which is why the story can name them without hand-labelling.
        became_bvap = sorted(
            (
                {
                    "district": d,
                    "priorBvap": f(a[d].get("pct_bvp")),
                    "currentBvap": f(b[d].get("pct_bvp")),
                }
                for d in districts
                if a[d].get("pct_bvp") is not None
                and b[d].get("pct_bvp") is not None
                and a[d]["pct_bvp"] < 0.5 <= b[d]["pct_bvp"]
            ),
            key=lambda r: r["district"],
        )

        disp = json.loads((REPO / plan["displacement"]).read_text())["summary"]
        disp_full = json.loads((REPO / plan["displacement"]).read_text())
        minimum = int(disp.get("min_required_displaced_pop") or 0)

        # Per-district displacement, with the share each district had to move for
        # population equality (its overage above the ideal district size). This
        # mirrors the "population moved vs required" chart FDGA and PGP publish.
        ideal = disp["total_pop"] / disp["district_count"] if disp.get("district_count") else 0

        # Population arriving in each district is NOT published: the plan files'
        # `moved_to` blocks do not reconcile (for the House, 6 districts receive
        # more people than they contain, and total inbound exceeds the summary's
        # displaced population). "Moved out" and "required" both reconcile and
        # are the two series the district-cores test needs.
        current_pop = {str(int(d)): int(b[d].get("pop") or 0) for d in districts}

        district_disp = sorted(
            (
                {
                    "district": int(float(r["district_id_a"])),
                    "pop": int(r["pop_a"]),
                    "popCurrent": current_pop.get(str(int(float(r["district_id_a"]))), 0),
                    "displacedPct": f(r["displaced_pct"]),
                    "requiredPct": f(max(0.0, r["pop_a"] - ideal) / r["pop_a"])
                    if r["pop_a"]
                    else 0.0,
                    # Signed deviation from the ideal district size: the
                    # "population over/under" measure. Positive = over-populated.
                    "deviationPct": f((r["pop_a"] - ideal) / ideal) if ideal else None,
                    "deviationCurrentPct": f(
                        (current_pop.get(str(int(float(r["district_id_a"]))), 0) - ideal) / ideal
                    )
                    if ideal and current_pop.get(str(int(float(r["district_id_a"]))))
                    else None,
                }
                for r in disp_full["districts"]
            ),
            key=lambda r: -(r["displacedPct"] or 0),
        )

        # Population equality summary, both plans (PDF slide "Population
        # over/under in previous map's districts").
        deviations = [r["deviationPct"] for r in district_disp if r["deviationPct"] is not None]
        deviations_now = [
            r["deviationCurrentPct"] for r in district_disp if r["deviationCurrentPct"] is not None
        ]
        population = {
            "ideal": int(round(ideal)) if ideal else None,
            "totalPop": int(disp.get("total_pop") or 0),
            "priorMaxDeviationPct": f(max(deviations, key=abs)) if deviations else None,
            "currentMaxDeviationPct": f(max(deviations_now, key=abs)) if deviations_now else None,
            "priorOverCount": sum(1 for v in deviations if v > 0),
            "priorUnderCount": sum(1 for v in deviations if v < 0),
        }

        # Minority-representation counts under each set of lines: the same
        # majority / coalition / influence categories the 2022 FDGA-PGP
        # evaluation reported, recomputed for both plans.
        representation = {
            "thresholds": {
                "majority": MAJORITY_THRESHOLD,
                "influenceLo": INFLUENCE_LO,
                "influenceHi": INFLUENCE_HI,
            },
            "prior": representation_summary(
                [
                    {"district": r["district"], **{c: r[f"prior_{c}"] for c in CATEGORIES}}
                    for r in rows_out
                ]
            ),
            "current": representation_summary(
                [
                    {"district": r["district"], **{c: r[f"current_{c}"] for c in CATEGORIES}}
                    for r in rows_out
                ]
            ),
        }

        # Districts whose population ended up predominantly under a different
        # number. Ids are normalised: the congressional files mix "7" and "7.0".
        renumbered = sum(
            1
            for r in disp_full["districts"]
            if int(float(r["district_id_a"])) != int(float(r["district_id_b"]))
        )

        record = {
            "chamber": plan["chamber"],
            "label": plan["chamber_label"],
            "kind": plan["kind"],
            "eventLabel": plan["event_label"],
            "pairId": (Path(plan["displacement"]).stem),
            "renumberedDistricts": renumbered,
            "seats": len(districts),
            "prior": {"label": plan["prior_label"], "years": plan["prior_years"]},
            "current": {"label": plan["current_label"], "years": plan["current_years"]},
            "displacement": {
                "people": int(disp.get("displaced_pop") or 0),
                "pct": f(disp.get("displaced_pct")),
                # Arithmetic, not legal: the population that any equal-population
                # plan must move. Labelled "minimum" only in that sense.
                "arithmeticMinimum": minimum,
                "arithmeticMinimumPct": f(disp.get("min_required_displaced_pct")),
                "multiple": f(disp.get("displaced_pop") / minimum) if minimum else None,
                "minimumIsTrivial": minimum < 1000,
                "districts": district_disp,
            },
            "population": population,
            "representation": representation,
            "signals": signals,
            "districts": rows_out,
            "index": {"prior": distribution(a), "current": distribution(b)},
            "becameBvapMajority": became_bvap,
        }
        (out if plan["kind"] == "remedy" else hist)[plan["chamber"]] = record
    return out, hist


def load_state_vap(con):
    """Statewide voting-age population composition from the 2020 Census VTD file.

    The 2022 FDGA / Princeton Gerrymandering Project evaluation opened with
    Georgia's racial composition ("Diversity reigns") as the context for the
    minority-representation test. Redistricting is measured on voting-age
    population, so this reports the same breakdown on the VAP denominator that
    every district percentage in the story uses.

    Args:
        con: an open duckdb connection.

    Returns:
        dict: ``vap`` total, a ``groups`` list (label, people, share) ordered
        largest first, and ``coalition`` (all minorities combined).
    """
    row = rows(
        con,
        f"""
        SELECT SUM(bvap_tot) AS vap,
               SUM(bvap_wht) AS wht,
               SUM(bvap_blk) AS blk,
               SUM(bvap_hsp) AS hsp,
               SUM(bvap_asn) AS asn,
               SUM(bvap_coalition) AS coal
        FROM '{REPO}/vtd/vtd_composite.parquet'
        """,
    )[0]
    # bvap_tot is the Census P4 total VAP and is the denominator FDP's own
    # build scripts use; bvap_coalition is defined there as total minus
    # white-alone, i.e. every non-white group combined.
    vap = float(row["vap"] or 0)
    if not vap:
        return {"vap": 0, "groups": [], "minorityShare": None}

    named = [
        ("White alone", float(row["wht"] or 0)),
        ("Black or African American", float(row["blk"] or 0)),
        ("Hispanic or Latino", float(row["hsp"] or 0)),
        ("Asian alone", float(row["asn"] or 0)),
    ]
    accounted = sum(v for _, v in named)
    groups = [{"label": label, "people": int(v), "share": f(v / vap)} for label, v in named]
    groups.append(
        {
            "label": "Other or multiracial",
            "people": int(max(0.0, vap - accounted)),
            "share": f(max(0.0, vap - accounted) / vap),
        }
    )
    groups.sort(key=lambda g: -g["people"])
    return {
        "vap": int(vap),
        "groups": groups,
        "minorityShare": f(float(row["coal"] or 0) / vap),
        "minorityPeople": int(row["coal"] or 0),
        "source": "2020 Census voting-age population by VTD (vtd_composite.parquet, P4 tables)",
    }


# Alternative and historical plans, keyed by chamber. Ids and labels come
# straight from fdp/config/apps/map_compare.yml, the FDP plan catalogue, so the
# app never invents a name for a plan. `role` groups them for display:
#   prior      the map in force before the 2021 cycle (2012/2014/2015 lines)
#   enacted21  the map enacted in 2021 and used for the 2022 elections
#   dem        the Democratic caucus counter-proposal of October/November 2021
#   rep        Republican committee drafts
#   remedy     court-ordered remedial plans
#   current    the 2024 remedial map in force now
# In FDGA/PGP's 2022 evaluation these are the "Previous Map", "Enacted Map
# (SB 2EX / SB 1EX / HB 1EX)" and "Dem proposed map (SB 3EX / SB 4EX / HB 4EX)"
# columns of its comparison tables.
PLAN_SETS = {
    "state_house": [
        ("house15_census20", "prior"),
        ("enacted_house22", "enacted21"),
        ("house_prop1_dem", "dem"),
        ("house_prop2_rep", "rep"),
        ("house_prop3_rep", "rep"),
        ("house_remedy_1", "remedy"),
        ("house_enacted_24_2024update", "current"),
    ],
    "state_senate": [
        ("senate14_census20", "prior"),
        ("enacted_senate22", "enacted21"),
        ("senate_prop1_dem", "dem"),
        ("senate_prop2_rep", "rep"),
        ("senate_prop3_rep", "rep"),
        ("senate_remedy", "remedy"),
        ("senate_enacted_24_2024update", "current"),
    ],
    "us_house": [
        ("congress12_census20", "prior"),
        ("congress21_p2", "alt"),
        ("enacted_congress22", "enacted21"),
        ("congress_proposed3", "proposed"),
        ("congress_cooper", "remedy"),
        ("congress_enacted_24_2024update", "current"),
    ],
}

# Signals every plan file is scored with (the six elections plus the composite).
PLAN_SIGNALS = [e["key"] for e in ELECTIONS] + ["partisan"]

# The 2018-20-21 index FDGA/PGP's 2022 evaluation used: the mean Democratic
# share across the 2018 Governor, 2020 President and 2021 Senate runoff. Kept
# as its own signal so the app can reproduce that deck's published seat and
# competitive counts exactly, alongside the six-election composite.
DECK_INDEX_SIGNALS = ["g18_pct_dem", "p20_pct_dem", "r21_pct_dem"]
DECK_INDEX_KEY = "deck1821"


def plan_signal_column(key):
    """Map a signal key to the plan-GeoJSON property holding its D share."""
    if key == "composite":
        return "partisan"
    if key == "partisan":
        return "partisan"
    return f"{key}_pct_dem"


def deck_index(props):
    """Per-district 2018-20-21 Democratic share, or None where any leg is missing.

    Args:
        props (dict): one district's plan-GeoJSON properties.

    Returns:
        float | None: the mean Democratic share across the three elections the
        2022 evaluation averaged, rounded, or None if not all three are present.
    """
    vals = [props.get(k) for k in DECK_INDEX_SIGNALS]
    vals = [v for v in vals if v is not None]
    if len(vals) != len(DECK_INDEX_SIGNALS):
        return None
    return f(sum(float(v) for v in vals) / len(vals))


def load_plans():
    """Score every catalogued plan for each chamber on a common basis.

    All plan files carry the same per-district election signals, computed from
    one VTD vote file, so seat counts, competitiveness and minority-representation
    categories are directly comparable across a 2015 map, the 2021 enacted map,
    the competing proposals and the 2024 remedial map.

    Returns:
        dict: chamber → list of plan records, each with per-signal seat counts,
        competitiveness, representation counts, population equality and a compact
        per-district lean table for the composite and 2024 presidential signals.
    """
    # Plan id → catalogue label, so nothing is named by guesswork.
    labels = {}
    catalogue = (REPO.parent.parent.parent / "config" / "apps" / "map_compare.yml").read_text()
    current_id = None
    for line in catalogue.splitlines():
        stripped = line.strip()
        if stripped.startswith("- id:"):
            current_id = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("label:") and current_id:
            labels[current_id] = stripped.split(":", 1)[1].strip().strip('"')

    out = {}
    for chamber, plans in PLAN_SETS.items():
        records = []
        for plan_id, role in plans:
            matches = list((REPO / "boundaries").glob(f"*/{plan_id}.geojson"))
            if not matches:
                print(f"  ! plan missing: {plan_id}")
                continue
            geo = json.loads(matches[0].read_text())
            props = []
            for ft in geo["features"]:
                p = ft["properties"]
                if p.get("district") is None:
                    continue
                props.append(p)
            if not props:
                continue

            # Seat counts per signal.
            signals = {}
            for key in PLAN_SIGNALS:
                col = plan_signal_column(key)
                vals = [p[col] for p in props if p.get(col) is not None]
                if not vals:
                    continue
                signals[key] = {
                    "seatsD": sum(1 for v in vals if v > 0.5),
                    "competitive": sum(1 for v in vals if 0.465 <= v <= 0.535),
                    "median": f(sorted(vals)[len(vals) // 2]),
                    "mean": f(sum(vals) / len(vals)),
                    "n": len(vals),
                }

            # The 2022 evaluation's own three-election index, computed from the
            # same legs rather than read from a stored column.
            deck_vals = [v for v in (deck_index(p) for p in props) if v is not None]
            if deck_vals:
                signals[DECK_INDEX_KEY] = {
                    "seatsD": sum(1 for v in deck_vals if v > 0.5),
                    "competitive": sum(1 for v in deck_vals if 0.465 <= v <= 0.535),
                    "median": f(sorted(deck_vals)[len(deck_vals) // 2]),
                    "mean": f(sum(deck_vals) / len(deck_vals)),
                    "n": len(deck_vals),
                }

            # Representation categories, same thresholds as the map-effect block.
            classified = []
            for p in props:
                shares = demographic_shares(p)
                row = {"district": int(float(p["district"]))}
                row.update(classify_district(shares))
                classified.append(row)
            rep = representation_summary(classified)

            # Population equality within this plan.
            pops = [int(p.get("pop") or 0) for p in props]
            total = sum(pops)
            ideal = total / len(pops) if pops else 0
            deviations = [(v - ideal) / ideal for v in pops if v and ideal]

            districts = sorted(
                (
                    {
                        "district": int(float(p["district"])),
                        "composite": f(p.get("partisan")),
                        "p24": f(p.get("p24_pct_dem")),
                        DECK_INDEX_KEY: deck_index(p),
                        "bvap": f(
                            p.get("pct_bvp")
                            if p.get("pct_bvp") is not None
                            else (
                                float(p["bvap"]) / float(p["tvap"])
                                if p.get("bvap") and p.get("tvap")
                                else None
                            )
                        ),
                    }
                    for p in props
                ),
                key=lambda r: r["district"],
            )

            records.append(
                {
                    "id": plan_id,
                    "label": labels.get(plan_id, plan_id),
                    "role": role,
                    "seats": len(props),
                    "signals": signals,
                    "representation": rep["counts"],
                    "representationDistricts": {
                        k: v for k, v in rep["districts"].items() if v and len(v) <= 60
                    },
                    "population": {
                        "total": total,
                        "ideal": int(round(ideal)) if ideal else None,
                        "maxDeviationPct": f(max(deviations, key=abs)) if deviations else None,
                        "overCount": sum(1 for v in deviations if v > 0),
                        "underCount": sum(1 for v in deviations if v < 0),
                    },
                    "districts": districts,
                }
            )
        out[chamber] = records
    return out


# Plan transitions with pre-computed population displacement. The first three
# are the deck's "Previous Map → Enacted Map" comparison; the last three are the
# 2024 remedial transition section 03 already renders per district.
PLAN_PAIRS = {
    "state_house": ["house_15_to_22", "house_2123_to_24"],
    "state_senate": ["senate_14_to_22", "senate_2123_to_24"],
    "us_house": ["congress_21_to_22", "congress_2123_to_24"],
}


def load_plan_pairs():
    """Population movement between consecutive maps, per chamber.

    Reads the pre-computed displacement files and reports how many people the
    transition moved, how much of that equal populations forced, and whether
    district numbers were preserved. The last flag matters: where a transition
    renumbered districts, a district-number join would compare unrelated places,
    so per-district views are only offered for transitions that kept numbering.

    Returns:
        dict: chamber → list of transition records.
    """
    out = {}
    for chamber, pair_ids in PLAN_PAIRS.items():
        records = []
        for pair_id in pair_ids:
            path = REPO / "displacement" / f"{pair_id}.json"
            if not path.exists():
                print(f"  ! displacement pair missing: {pair_id}")
                continue
            doc = json.loads(path.read_text())
            s = doc["summary"]
            rows = doc["districts"]
            minimum = int(s.get("min_required_displaced_pop") or 0)
            displaced = int(s.get("displaced_pop") or 0)
            # Districts whose population ended up predominantly under a different
            # number. Ids are normalised because the congressional files mix "7"
            # and "7.0", which otherwise reports every district as renumbered.
            renumbered = sum(
                1
                for r in rows
                if int(float(r.get("district_id_a"))) != int(float(r.get("district_id_b")))
            )
            records.append(
                {
                    "id": pair_id,
                    "label": doc.get("label") or pair_id,
                    "planA": s.get("plan_a_id"),
                    "planB": s.get("plan_b_id"),
                    "people": displaced,
                    "pct": f(s.get("displaced_pct")),
                    "totalPop": int(s.get("total_pop") or 0),
                    "districts": int(s.get("district_count") or len(rows)),
                    "arithmeticMinimum": minimum,
                    "arithmeticMinimumPct": f(s.get("min_required_displaced_pct")),
                    "multiple": f(displaced / minimum) if minimum else None,
                    "renumberedDistricts": renumbered,
                    # Below this, districts are already equal to the person and a
                    # multiple against the minimum is meaningless (Congress).
                    "minimumIsTrivial": minimum < 1000,
                    "method": s.get("method"),
                }
            )
        out[chamber] = records
    return out


def main() -> None:
    con = duckdb.connect()
    map_effect, map_effect_history = load_map_effect()
    bundle = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "elections": ELECTIONS,
            "chambers": CHAMBERS,
            "source": "FDP common data model (fdga + vtd parquet, 2020 Census VTDs)",
        },
        "statewide": load_statewide(con),
        "state_vap": load_state_vap(con),
        "chamber_year": load_chamber_year(con),
        "contests": load_contests(con),
        "county_votes": load_county_votes(con),
        "map_effect": map_effect,
        "map_effect_history": map_effect_history,
        "plans": load_plans(),
        "plan_pairs": load_plan_pairs(),
        "ensemble": load_ensemble(),
        "sources": MAP_SOURCES,
        "counties": load_counties(),
        "precincts": load_precincts(),
    }
    path = OUT / "story.json"
    path.write_text(json.dumps(bundle, separators=(",", ":")))
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
    print(
        f"  statewide={len(bundle['statewide'])} chamber_year={len(bundle['chamber_year'])} "
        f"counties={len(bundle['counties']['features'])} precincts={len(bundle['precincts'])} "
        f"map_effect={sum(len(c['districts']) for c in bundle['map_effect'].values())} districts "
        f"+ history={sum(len(c['districts']) for c in bundle['map_effect_history'].values())} "
        f"ensemble={sum(len(c['metrics']) for c in bundle['ensemble'].values())} metrics"
    )


if __name__ == "__main__":
    main()
