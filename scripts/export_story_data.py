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

# Plan pairs used by the "map swap" analysis: the same 2024 ballots counted
# under the 2021-23 lines and under the 2024 remedial lines. Both GeoJSONs carry
# per-district election signals computed from the same VTD votes, so the seat
# difference is attributable to the lines alone (no spatial join, no estimation).
MAP_PLANS = [
    {
        "chamber": "state_house",
        "chamber_label": "GA House",
        "prior": "boundaries/house/house_enacted_2123_2024update.geojson",
        "prior_label": "2021-23 lines",
        "prior_years": "2022-2024",
        "current": "boundaries/house/house_enacted_24_2024update.geojson",
        "current_label": "2024 lines",
        "current_years": "2024",
        "displacement": "displacement/house_2123_to_24.json",
    },
    {
        "chamber": "state_senate",
        "chamber_label": "GA Senate",
        "prior": "boundaries/senate/senate_enacted_2123_2024update.geojson",
        "prior_label": "2021-23 lines",
        "prior_years": "2022-2024",
        "current": "boundaries/senate/senate_enacted_24_2024update.geojson",
        "current_label": "2024 lines",
        "current_years": "2024",
        "displacement": "displacement/senate_2123_to_24.json",
    },
    {
        "chamber": "us_house",
        "chamber_label": "U.S. House",
        "prior": "boundaries/congress/congress_enacted_2123_2024update.geojson",
        "prior_label": "2021-23 lines",
        "prior_years": "2022-2024",
        "current": "boundaries/congress/congress_enacted_24_2024update.geojson",
        "current_label": "2024 lines",
        "current_years": "2024",
        "displacement": "displacement/congress_2123_to_24.json",
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


def f(x):
    """Round floats for smaller payloads; pass through None."""
    return None if x is None else round(float(x), 5)


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
        county = (r["county"] or "").strip().upper()
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
                    "hist": {
                        "edges": [f(e) for e in (hist.get("edges") or [])],
                        "counts": [round(c / total, 4) for c in counts],
                    },
                }
            )

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
            "benchmarks": benchmarks,
        }
    return out


def load_map_effect():
    """Same voters, different lines: the 2024 map swap for every chamber.

    Each plan GeoJSON already carries per-district D share for the same six
    election signals, produced from one VTD vote file. Reading the same 2024
    votes through the prior and current lines therefore isolates the effect of
    the boundaries themselves.
    """
    out = {}
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
        # the map swap is measured on.
        rows_out = []
        for d in districts:
            x = a[d].get("p24_pct_dem")
            y = b[d].get("p24_pct_dem")
            if x is None or y is None:
                continue
            rows_out.append(
                {
                    "district": d,
                    "priorPct": f(x),
                    "currentPct": f(y),
                    "shiftPts": f((y - x) * 100),
                    "priorPartisan": f(a[d].get("partisan")),
                    "currentPartisan": f(b[d].get("partisan")),
                    "vap": int(a[d].get("tvap") or 0),
                    "priorBvap": f(a[d].get("pct_bvp")),
                    "currentBvap": f(b[d].get("pct_bvp")),
                }
            )

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
        district_disp = sorted(
            (
                {
                    "district": int(r["district_id_a"]),
                    "pop": int(r["pop_a"]),
                    "displacedPct": f(r["displaced_pct"]),
                    "requiredPct": f(max(0.0, r["pop_a"] - ideal) / r["pop_a"])
                    if r["pop_a"]
                    else 0.0,
                }
                for r in disp_full["districts"]
            ),
            key=lambda r: -(r["displacedPct"] or 0),
        )
        out[plan["chamber"]] = {
            "chamber": plan["chamber"],
            "label": plan["chamber_label"],
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
                "districts": district_disp,
            },
            "signals": signals,
            "districts": rows_out,
            "index": {"prior": distribution(a), "current": distribution(b)},
            "becameBvapMajority": became_bvap,
        }
    return out


def main() -> None:
    con = duckdb.connect()
    bundle = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "elections": ELECTIONS,
            "chambers": CHAMBERS,
            "source": "FDP common data model (fdga + vtd parquet, 2020 Census VTDs)",
        },
        "statewide": load_statewide(con),
        "chamber_year": load_chamber_year(con),
        "contests": load_contests(con),
        "county_votes": load_county_votes(con),
        "map_effect": load_map_effect(),
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
        f"ensemble={sum(len(c['metrics']) for c in bundle['ensemble'].values())} metrics"
    )


if __name__ == "__main__":
    main()
