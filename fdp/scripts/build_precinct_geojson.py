#!/usr/bin/env python3
"""
build_precinct_geojson.py — Join the 6-election VTD composite score onto VTD
boundary geometry and emit a precinct-level GeoJSON for fdex.

The Mapbox vector tileset fdex used for its precinct partisan-lean overlay
(fdgamaps.97e7r27u) was last uploaded in Sept 2021 and only carries 2018 Gov,
2020 Pres, and the 2021 runoff — no 2022 or 2024. vtd_composite.parquet
(built by build_composite_score.py) already has all six elections aggregated
to VTD; this script just joins that onto the VTD reference geometry
(ga_pl2020_vtd.zip) so fdex can render it as a local GeoJSON source instead
of a stale external tileset.

Output: data/repos/main/boundaries/reference/precinct_scored.geojson

Usage (from fdp/ directory):
    uv run python scripts/build_precinct_geojson.py
    uv run python scripts/build_precinct_geojson.py --simplify 0.0001   # degrees
"""
from __future__ import annotations

import argparse
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
_FDP_ROOT = _SCRIPT_DIR.parent

VTD_ZIP = _FDP_ROOT / "data/raw/boundaries/ga_pl2020_vtd.zip"
COMPOSITE_PARQUET = _FDP_ROOT / "data/repos/main/vtd/vtd_composite.parquet"
OUTPUT_PATH = _FDP_ROOT / "data/repos/main/boundaries/reference/precinct_scored.geojson"

ELECTION_RENAME = {
    "dem_pct_2018_gov":         "g18_pct_dem",
    "dem_pct_2020_pres":        "p20_pct_dem",
    "dem_pct_2021_war_runoff":  "r21_pct_dem",
    "dem_pct_2022_gov":         "g22_pct_dem",
    "dem_pct_2022_uss":         "s22_pct_dem",
    "dem_pct_2024_pres":        "p24_pct_dem",
}


def _log(msg: str) -> None:
    print(f"[build_precinct_geojson] {msg}")


def load_vtd_geometry() -> gpd.GeoDataFrame:
    _log(f"Reading VTD reference shapefile from {VTD_ZIP.name} …")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(VTD_ZIP) as z:
            z.extractall(tmp)
        gdf = gpd.read_file(
            Path(tmp) / "ga_pl2020_vtd.shp",
            engine="pyogrio",
            columns=[
                "GEOID20", "NAME20", "NAMELSAD20", "COUNTYFP20", "VTDST20",
                "P0010001", "P0040001",
            ],
        )
    gdf = gdf.rename(columns={
        "GEOID20": "geoid20",
        "NAME20": "name20",
        "NAMELSAD20": "namelsad20",
        "COUNTYFP20": "countyfp20",
        "VTDST20": "vtdst20",
        "P0010001": "pop",
        "P0040001": "tvap",
    })
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def build(simplify_tolerance: float | None) -> gpd.GeoDataFrame:
    vtds = load_vtd_geometry()

    _log(f"Reading composite election scores from {COMPOSITE_PARQUET.name} …")
    composite = pd.read_parquet(COMPOSITE_PARQUET)

    merged = vtds.merge(composite, left_on="geoid20", right_on="GEOID20", how="left")
    unmatched = merged["GEOID20"].isna().sum()
    if unmatched:
        _log(f"  WARNING: {unmatched}/{len(merged)} VTDs had no composite score match")

    merged = merged.rename(columns=ELECTION_RENAME)
    merged["partisan"] = merged["composite_dem_2pv"]

    keep_cols = [
        "geoid20", "name20", "namelsad20", "countyfp20", "vtdst20",
        "pop", "tvap", "partisan",
        *ELECTION_RENAME.values(),
        "geometry",
    ]
    merged = merged[keep_cols]

    if simplify_tolerance:
        _log(f"Simplifying geometry (tolerance={simplify_tolerance} degrees) …")
        merged["geometry"] = merged["geometry"].simplify(
            simplify_tolerance, preserve_topology=True,
        )

    return merged


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simplify", type=float, default=0.00008,
                     help="Douglas-Peucker tolerance in degrees (~9m). 0 to disable.")
    ap.add_argument("--out", type=Path, default=OUTPUT_PATH)
    args = ap.parse_args()

    gdf = build(args.simplify or None)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(args.out, driver="GeoJSON")

    size_mb = args.out.stat().st_size / 1_000_000
    _log(f"Wrote {len(gdf)} precincts to {args.out} ({size_mb:.1f} MB)")

    have_all_six = gdf[list(ELECTION_RENAME.values())].notna().all(axis=1).sum()
    _log(f"  {have_all_six}/{len(gdf)} precincts have all six elections")


if __name__ == "__main__":
    main()
