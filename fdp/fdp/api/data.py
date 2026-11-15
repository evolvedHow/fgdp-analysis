"""
FDP REST data API — FastAPI router.

This router exposes the canonical FDP datasets as REST endpoints.  It reads
directly from the published parquet/GeoJSON files in the active FDP repo, so
there is no PostgreSQL dependency.  Data updates are file replacements.

Route prefix /api/v1 is applied in server.py.

Endpoints
---------
GET  /health                    Liveness check
GET  /catalog                   List registered datasets (parquet files)
GET  /geography                 List geography rows (filterable)
GET  /elections                 Election results (filterable, aggregated per geoid+race)
GET  /elections/{geoid}         Full election history for one geographic unit
GET  /cvap                      CVAP rows (filterable)
GET  /cvap/{geoid}              CVAP for one geographic unit
GET  /districts/{state}         GeoJSON FeatureCollection of VTD geometries
GET  /schema                    Data dictionary of available parquet datasets
POST /query                     Read-only DuckDB SQL over parquet files
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
import geopandas as gpd
import pandas as pd
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from fdp import DataPlatform

router = APIRouter()

# ---------------------------------------------------------------------------
# Caching + path resolution
# ---------------------------------------------------------------------------

_platform: DataPlatform | None = None


def _get_platform() -> DataPlatform:
    """Return a singleton DataPlatform for the active repo."""
    global _platform
    if _platform is None:
        _platform = DataPlatform(app=None, repo=None)
    return _platform


@lru_cache(maxsize=8)
def _read_parquet(rel_path: str) -> pd.DataFrame:
    """Load a repo-relative parquet file into a DataFrame."""
    path = str(_get_platform().resolve(rel_path))
    return pd.read_parquet(path)


@lru_cache(maxsize=8)
def _read_geojson(rel_path: str) -> gpd.GeoDataFrame:
    """Load a repo-relative GeoJSON file into a GeoDataFrame."""
    path = str(_get_platform().resolve(rel_path))
    return gpd.read_file(path)


def _secret_ok(token: str | None) -> bool:
    expected = os.environ.get("FDPAPI_SECRET")
    if not expected:
        return False
    return token == expected


# ---------------------------------------------------------------------------
# Dataset paths
# ---------------------------------------------------------------------------

_ELECTIONS_PATH = "election_results_vtd.parquet"
_CVAP_PATH = "vtd/cvap_vtd.parquet"
_COMPOSITE_PATH = "vtd/vtd_composite.parquet"


def _datasets_dir() -> Path:
    return _get_platform().resolve("")


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@router.get("/health", summary="Liveness check")
def health() -> dict:
    """
    Returns HTTP 200 when the API is running and can read the data files.
    Returns HTTP 503 if the data files are unreachable.
    """
    try:
        df = _read_parquet(_ELECTIONS_PATH)
        return {"status": "ok", "election_rows": len(df)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Data files unreachable: {exc}") from exc


# ---------------------------------------------------------------------------
# GET /catalog
# ---------------------------------------------------------------------------

@router.get("/catalog", summary="List registered datasets")
def catalog(
    state: str | None = Query(None, description="Filter by state (e.g. GA)"),
    category: str | None = Query(None, description="Filter by category (election | cvap | boundaries | ensemble)"),
    geography: str | None = Query(None, description="Filter by geography level (vtd | block | …)"),
    vintage: int | None = Query(None, description="Filter by data year"),
) -> list[dict]:
    """
    Return all published datasets discovered under the active repo.

    Datasets are the parquet and GeoJSON files themselves; no manifest table
    is required.  Filters are best-effort based on file paths and names.
    """
    root = _datasets_dir()
    rows: list[dict] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in (".parquet", ".geojson", ".json", ".csv"):
            continue

        rel = path.relative_to(root).as_posix()
        lower = rel.lower()

        # Guess category from path/name
        guessed_category = "other"
        if "election" in lower or "vtd_election" in lower:
            guessed_category = "election"
        elif "cvap" in lower or "bvap" in lower:
            guessed_category = "cvap"
        elif "boundary" in lower or suffix == ".geojson":
            guessed_category = "boundaries"
        elif "ensemble" in lower or "benchmark" in lower or "plans" in lower:
            guessed_category = "ensemble"
        elif "fdga" in lower:
            guessed_category = "fdga"

        # Guess geography level
        guessed_geo = None
        if "block" in lower:
            guessed_geo = "block"
        elif "vtd" in lower:
            guessed_geo = "vtd"
        elif "county" in lower:
            guessed_geo = "county"
        elif "district" in lower or "house" in lower or "senate" in lower or "congress" in lower:
            guessed_geo = "district"

        # Guess vintage from filename (e.g. 2024, 2022)
        guessed_vintage = None
        for part in reversed(path.stem.split("_")):
            if part.isdigit() and len(part) == 4:
                guessed_vintage = int(part)
                break

        # Apply filters
        if category and guessed_category != category.lower():
            continue
        if geography and guessed_geo != geography.lower():
            continue
        if vintage and guessed_vintage != vintage:
            continue
        if state and state.upper() not in path.stem.upper() and state.upper() not in rel.upper():
            # Loose filter: skip only if state is definitely absent
            pass

        rows.append({
            "id": rel,
            "category": guessed_category,
            "geography": guessed_geo,
            "vintage": guessed_vintage,
            "state": state.upper() if state else "GA",
            "source": rel,
            "row_count": None,
            "loaded_at": None,
            "notes": "Discovered from file system",
        })

    return rows


# ---------------------------------------------------------------------------
# GET /geography
# ---------------------------------------------------------------------------

@router.get("/geography", summary="List geography rows")
def geography(
    state: str | None = Query(None, description="Filter by state (e.g. GA)"),
    geo_level: str | None = Query("vtd", description="Geographic level (default: vtd)"),
    vintage_year: int | None = Query(2020, description="Boundary vintage year (default: 2020)"),
    county_fips: str | None = Query(None, description="Filter to a specific county (5-char FIPS)"),
    limit: int = Query(5000, le=10000, description="Max rows to return"),
) -> list[dict]:
    """
    Return geography dimension rows — one row per geographic unit.

    Derived from the VTD composite parquet file, which contains GEOID20 plus
    centroid coordinates.  Geometry boundaries are available via /districts.
    """
    df = _read_parquet(_COMPOSITE_PATH).copy()
    df = df.rename(columns={"GEOID20": "geoid"})

    if state:
        # GA VTD geoids start with 13
        df = df[df["geoid"].astype(str).str.startswith("13")]
    if county_fips:
        df = df[df["geoid"].astype(str).str.startswith(county_fips)]

    df["geo_level"] = geo_level
    df["geo_type"] = "vtd"
    df["state"] = state.upper() if state else "GA"
    df["vintage_year"] = vintage_year
    df["county_fips"] = df["geoid"].astype(str).str[:5]
    df["name"] = df["geoid"]

    cols = ["geoid", "geo_level", "geo_type", "state", "county_fips", "name", "vintage_year"]
    if "centroid_lat" in df.columns and "centroid_lon" in df.columns:
        cols += ["centroid_lat", "centroid_lon"]

    df = df[cols].drop_duplicates().head(limit)
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# GET /elections
# ---------------------------------------------------------------------------

@router.get("/elections", summary="Election results (aggregated per VTD per race)")
def elections(
    state: str | None = Query(None, description="Filter by state (e.g. GA)"),
    year: int | None = Query(None, description="Election year (e.g. 2022)"),
    election_type: str | None = Query(None, description="general | runoff | special | primary"),
    office: str | None = Query(None, description="governor | president | senate | …"),
    geo_level: str | None = Query("vtd", description="Geographic level (default: vtd)"),
    county_fips: str | None = Query(None, description="Restrict to a single county"),
    limit: int = Query(10000, le=100000, description="Max rows returned"),
) -> list[dict]:
    """
    Return election results rows from the canonical election_results_vtd parquet.

    Each row is one candidate's vote count in one geographic unit.
    """
    df = _read_parquet(_ELECTIONS_PATH).copy()

    if state:
        df = df[df["geoid"].astype(str).str.startswith("13")]
    if county_fips:
        df = df[df["geoid"].astype(str).str.startswith(county_fips)]
    if year is not None:
        df = df[df["year"] == year]
    if election_type:
        df = df[df["election_type"].str.lower() == election_type.lower()]
    if office:
        df = df[df["office"].str.lower() == office.lower()]
    if geo_level:
        df = df.assign(geo_level=geo_level)

    df = df.sort_values(["geoid", "year", "office", "party"]).head(limit)
    df["state"] = state.upper() if state else "GA"
    df["source"] = _ELECTIONS_PATH
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# GET /elections/{geoid}
# ---------------------------------------------------------------------------

@router.get("/elections/{geoid}", summary="Full election history for one geographic unit")
def elections_by_geoid(geoid: str) -> list[dict]:
    """Return all election results for a single geoid (e.g. a VTD)."""
    df = _read_parquet(_ELECTIONS_PATH)
    df = df[df["geoid"].astype(str) == geoid].sort_values(["year", "office", "party"])

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No election data found for geoid={geoid!r}")

    df = df.assign(geo_level="vtd", state="GA", source=_ELECTIONS_PATH)
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# GET /cvap
# ---------------------------------------------------------------------------

@router.get("/cvap", summary="CVAP rows (filterable)")
def cvap(
    state: str | None = Query(None, description="Filter by state"),
    year: int | None = Query(None, description="ACS end year (e.g. 2024)"),
    geo_level: str | None = Query("vtd", description="Geographic level (default: vtd)"),
    county_fips: str | None = Query(None, description="Restrict to a single county"),
    limit: int = Query(5000, le=10000, description="Max rows returned"),
) -> list[dict]:
    """
    Return Citizen Voting Age Population rows from cvap_vtd.parquet.

    The canonical columns are renamed to the fdp.cvap schema for compatibility.
    """
    df = _read_parquet(_CVAP_PATH).copy()
    df = df.rename(columns={
        "GEOID20": "geoid",
        "bvap_tot": "cvap_tot",
        "bvap_blk": "cvap_blk",
        "bvap_wht": "cvap_wht",
        "bvap_hsp": "cvap_hsp",
        "bvap_asn": "cvap_asn",
        "bvap_ami": "cvap_ami",
        "bvap_nhp": "cvap_nhp",
        "bvap_oth": "cvap_oth",
    })

    if state:
        df = df[df["geoid"].astype(str).str.startswith("13")]
    if county_fips:
        df = df[df["geoid"].astype(str).str.startswith(county_fips)]
    if year is not None:
        df = df.assign(year=year)
    else:
        df = df.assign(year=2024)

    df["geo_level"] = geo_level
    df["state"] = state.upper() if state else "GA"
    df["source"] = _CVAP_PATH

    # Canonical schema columns; fill missing with None so different CVAP vintages
    # still return a predictable shape.
    expected_cols = ["cvap_tot", "cvap_blk", "cvap_hsp", "cvap_wht",
                     "cvap_asn", "cvap_ami", "cvap_nhp", "cvap_oth"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None

    cols = ["geoid", "geo_level", "state", "year"] + expected_cols + ["source"]
    df = df[cols].sort_values("geoid").head(limit)
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# GET /cvap/{geoid}
# ---------------------------------------------------------------------------

@router.get("/cvap/{geoid}", summary="CVAP for one geographic unit")
def cvap_by_geoid(geoid: str) -> list[dict]:
    """Return all CVAP years available for a single geoid."""
    df = _read_parquet(_CVAP_PATH).copy()
    df = df.rename(columns={"GEOID20": "geoid"})
    df = df[df["geoid"].astype(str) == geoid]

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No CVAP data found for geoid={geoid!r}")

    expected_cols = ["cvap_tot", "cvap_blk", "cvap_hsp", "cvap_wht",
                     "cvap_asn", "cvap_ami", "cvap_nhp", "cvap_oth"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None

    df = df.assign(year=2024, geo_level="vtd", state="GA", source=_CVAP_PATH)
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# GET /districts/{state}
# ---------------------------------------------------------------------------

@router.get(
    "/districts/{state}",
    summary="VTD geometries as GeoJSON FeatureCollection",
    response_class=JSONResponse,
)
def districts(
    state: str,
    vintage_year: int = Query(2020, description="Boundary vintage year"),
    county_fips: str | None = Query(None, description="Restrict to one county"),
) -> JSONResponse:
    """
    Return a GeoJSON FeatureCollection of VTD boundaries.

    Looks for a chamber boundary GeoJSON (e.g. house_enacted_24) and falls back
    to the reference county GeoJSON.  CVAP columns are joined from the VTD
    composite parquet when available.
    """
    platform = _get_platform()

    # Prefer an explicit VTD boundary file if one exists
    candidates = [
        "boundaries/reference/county.geojson",
    ]
    for chamber in ("house", "senate", "congress"):
        for plan in ("enacted_24", "enacted_2123", "enacted_22"):
            candidates.append(f"boundaries/{chamber}/{chamber}_{plan}_2024update.geojson")
            candidates.append(f"boundaries/{chamber}/{chamber}_{plan}.geojson")

    gdf: gpd.GeoDataFrame | None = None
    for rel in candidates:
        try:
            gdf = _read_geojson(rel)
            break
        except Exception:
            continue

    if gdf is None:
        raise HTTPException(status_code=404, detail="No boundary GeoJSON found")

    # Try to join CVAP attributes from composite parquet
    try:
        cvap_df = _read_parquet(_COMPOSITE_PATH).rename(columns={"GEOID20": "geoid"})
        if "geoid" in gdf.columns:
            gdf = gdf.merge(cvap_df, left_on="geoid", right_on="geoid", how="left")
    except Exception:
        pass

    if county_fips and "geoid" in gdf.columns:
        gdf = gdf[gdf["geoid"].astype(str).str.startswith(county_fips)]

    gdf = gdf.to_crs(epsg=4326)
    return JSONResponse(content=json.loads(gdf.to_json()))


# ---------------------------------------------------------------------------
# GET /schema
# ---------------------------------------------------------------------------

@router.get("/schema", summary="Data dictionary — datasets, columns, row counts")
def schema() -> dict:
    """
    Return a data dictionary describing all published parquet datasets.

    Useful for NLQ systems to understand queryable data.
    """
    root = _datasets_dir()
    result: dict[str, Any] = {}

    for path in sorted(root.rglob("*.parquet")):
        rel = path.relative_to(root).as_posix()
        try:
            df = _read_parquet(rel)
            result[rel] = {
                "description": f"Parquet dataset at {rel}",
                "row_count": len(df),
                "columns": [
                    {"column_name": c, "data_type": str(t), "description": None}
                    for c, t in zip(df.columns, df.dtypes)
                ],
            }
        except Exception as exc:
            result[rel] = {"error": str(exc)}

    return result


# ---------------------------------------------------------------------------
# GET /ensemble/runs
# ---------------------------------------------------------------------------

@router.get("/ensemble/runs", summary="List ensemble/benchmark datasets")
def ensemble_runs(
    status: str | None = Query(None, description="Ignored in file-only mode"),
    benchmark_id: str | None = Query(None, description="Filter by benchmark template ID"),
    chamber: str | None = Query(None, description="Filter by chamber: congress|senate|house"),
    limit: int = Query(50, le=500, description="Max rows returned"),
) -> list[dict]:
    """
    Return published ensemble/benchmark parquet datasets discovered in the repo.

    In the file-only architecture these are static benchmark outputs, not
    mutable run records.
    """
    root = _datasets_dir()
    rows: list[dict] = []

    for path in sorted(root.rglob("*benchmark*.parquet")):
        rel = path.relative_to(root).as_posix()
        lower = rel.lower()

        if benchmark_id and benchmark_id.lower() not in lower:
            continue
        if chamber and chamber.lower() not in lower:
            continue

        rows.append({
            "run_name": path.stem,
            "benchmark_id": benchmark_id or "unknown",
            "status": "completed",
            "plans_file": rel if "plans" in lower else None,
            "scores_file": rel if "scores" in lower else None,
            "demographics_file": rel if "demographics" in lower else None,
            "draw_stats_file": rel if "draw_stats" in lower else None,
            "created_at": None,
            "notes": "Discovered from file system",
        })

    return rows[:limit]


# ---------------------------------------------------------------------------
# GET /ensemble/runs/{run_name}
# ---------------------------------------------------------------------------

@router.get("/ensemble/runs/{run_name}", summary="Get one ensemble dataset by name")
def ensemble_run_detail(run_name: str) -> dict:
    """Return metadata for a discovered benchmark parquet dataset."""
    root = _datasets_dir()
    for path in root.rglob("*.parquet"):
        if path.stem == run_name:
            rel = path.relative_to(root).as_posix()
            return {
                "run_name": run_name,
                "benchmark_id": "unknown",
                "status": "completed",
                "plans_file": rel,
                "created_at": None,
                "notes": "Discovered from file system",
            }
    raise HTTPException(status_code=404, detail=f"Run '{run_name}' not found")


# ---------------------------------------------------------------------------
# POST /ensemble/runs  (disabled in file-only mode)
# ---------------------------------------------------------------------------

@router.post("/ensemble/runs", summary="Register a new ensemble run", status_code=501)
def ensemble_run_create(
    body: dict,
    x_fdpapi_secret: str | None = Header(default=None, alias="X-FDPAPI-Secret"),
) -> dict:
    """
    Registering new ensemble runs is disabled in the file-only architecture.

    Runs are produced by the CLI or Modal jobs and published as parquet files.
    """
    raise HTTPException(
        status_code=501,
        detail="Run registration requires a database. Use the CLI or Modal to produce parquet files.",
    )


# ---------------------------------------------------------------------------
# POST /query  (read-only DuckDB SQL over parquet files)
# ---------------------------------------------------------------------------

@router.post(
    "/query",
    summary="Raw DuckDB SQL over parquet files (requires FDPAPI_SECRET header)",
)
def query(
    body: dict,
    x_fdpapi_secret: str | None = Header(default=None, alias="X-FDPAPI-Secret"),
) -> dict:
    """
    Execute arbitrary read-only DuckDB SQL against the published parquet files.

    Requires the ``X-FDPAPI-Secret`` header to match the ``FDPAPI_SECRET`` env var.

    Request body:
        { "sql": "SELECT * FROM read_parquet('vtd/cvap_vtd.parquet') LIMIT 10" }

    Only SELECT statements are permitted.  Tables are not available — reference
    files by path using ``read_parquet('relative/path.parquet')``.

    Response:
        { "rows": [...], "row_count": N, "columns": [...] }
    """
    if not _secret_ok(x_fdpapi_secret):
        raise HTTPException(status_code=401, detail="Missing or invalid X-FDPAPI-Secret header")

    sql_text: str = body.get("sql", "").strip()
    params: list = body.get("params", [])

    if not sql_text:
        raise HTTPException(status_code=400, detail="Request body must include a 'sql' key")

    first_token = sql_text.split()[0].upper() if sql_text else ""
    if first_token not in ("SELECT", "WITH", "EXPLAIN"):
        raise HTTPException(
            status_code=400,
            detail=f"Only SELECT/WITH/EXPLAIN statements are permitted; got {first_token!r}",
        )

    # Prevent writes even if the guard above is bypassed
    forbidden = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE")
    if any(tok in sql_text.upper() for tok in forbidden):
        raise HTTPException(status_code=400, detail="Write statements are not permitted")

    try:
        con = duckdb.connect(":memory:")
        # Make all repo parquet files accessible by relative path
        root = str(_datasets_dir())
        con.execute(f"SET file_search_path = '{root}'")
        result = con.execute(sql_text, params).fetchdf()
        columns = list(result.columns)
        rows = result.to_dict(orient="records")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"rows": rows, "row_count": len(rows), "columns": columns}
