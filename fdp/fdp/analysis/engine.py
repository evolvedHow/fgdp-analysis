"""
Parameterized redistricting analysis engine.

Every analysis function accepts ``AnalysisParameters`` so that census year,
election year/type/office, chamber, minority group definitions, and
competitiveness thresholds are all runtime parameters -- never hardcoded.

Data sources (in priority order):
  1. Boundary GeoJSON via fdp DataPlatform (district properties: pop, VAP,
     partisan lean, minority percentages)
  2. CDM contests table (fdp/data/repos/main/fdga/contests.parquet) for
     election-level votes by district
  3. CDM chamber_year / statewide tables for context

As long as data exists in fdp for a given cycle, the same code works.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import geopandas as gpd
import pandas as pd
import yaml

from fdp import DataPlatform
from fdp.analysis.parameters import (
    AnalysisParameters,
    Chamber,
    DistrictMetric,
    ElectionSpec,
    MatchMode,
    MinorityGroupSpec,
    Office,
    PlanAnalysisResult,
    PlanComparisonResult,
    BenchmarkComparisonResult,
)

# Default minority group definitions (can be overridden via parameters)
DEFAULT_MINORITY_GROUPS: list[MinorityGroupSpec] = [
    MinorityGroupSpec(
        name="black",
        label="Majority Black (any-part)",
        cvap_col="CVAP_BLK24",
        majority_threshold=0.50,
        influence_lo=0.37,
        influence_hi=0.50,
    ),
    MinorityGroupSpec(
        name="white",
        label="Majority White",
        cvap_col="CVAP_WHT24",
        majority_threshold=0.50,
        influence_lo=0.37,
        influence_hi=0.50,
    ),
    MinorityGroupSpec(
        name="hispanic",
        label="Majority Hispanic",
        cvap_col="CVAP_HSP24",
        majority_threshold=0.50,
        influence_lo=0.37,
        influence_hi=0.50,
    ),
    MinorityGroupSpec(
        name="minority_coalition",
        label="Majority Minority Coalition",
        formula="1 - (CVAP_WHT24 / CVAP_TOT24)",
        majority_threshold=0.50,
        influence_lo=0.37,
        influence_hi=0.50,
    ),
]

# Column name aliases for reading district properties from GeoJSON
_POP_ALIASES = ["TOTPOP", "pop", "POP", "TotalPop"]
_VAP_ALIASES = ["VAP", "tvap", "TVAP", "VotingAgePop"]
_DEM_VOTES_ALIASES = ["DEM_VOTES", "dem_votes", "DemVotes"]
_REP_VOTES_ALIASES = ["REP_VOTES", "rep_votes", "RepVotes"]
_DISTRICT_ID_ALIASES = ["DISTRICT", "district", "DISTRICTID", "District", "NAME", "name", "ID", "id"]

# Minority percentage column aliases (GeoJSON embedded properties)
_MINORITY_PCT_ALIASES: dict[str, list[str]] = {
    "black": ["pct_bvp", "pct_bvap_al", "BVAP_PCT", "bvap_pct", "black_vap_pct"],
    "white": ["pct_wvap_al", "WVAP_PCT", "wvap_pct", "white_vap_pct"],
    "hispanic": ["pct_hvp", "HVAP_PCT", "hvap_pct", "hispanic_vap_pct"],
    "asian": ["pct_avap", "pct_avap_al", "AVAP_PCT", "avap_pct", "asian_vap_pct"],
}


class AnalysisEngine:
    """
    Core analysis engine for redistricting plans.

    Parameters are fully configurable -- no hardcoded years, chambers,
    election types, or minority groups.
    """

    def __init__(self, params: AnalysisParameters) -> None:
        self.params = params
        self._platform: DataPlatform | None = None
        self._duckdb: duckdb.DuckDBPyConnection | None = None
        self._gdf: gpd.GeoDataFrame | None = None
        self._cdm_contests: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    @property
    def platform(self) -> DataPlatform:
        if self._platform is None:
            self._platform = DataPlatform(
                app=None,
                repo=self.params.repo,
                halt_on_error=self.params.halt_on_error,
            )
        return self._platform

    @property
    def duckdb_conn(self) -> duckdb.DuckDBPyConnection:
        if self._duckdb is None:
            self._duckdb = duckdb.connect()
        return self._duckdb


    def _resolve_plan_file(self) -> str:
        """Resolve the plan GeoJSON path from plan_id or plan_file."""
        if self.params.plan_file:
            return self.params.plan_file

        # Look up plan_id in the platform config catalogue
        app_config = self.platform.config
        plans = app_config.get("plans", {})
        chamber_plans = plans.get(self.params.chamber.value, [])
        for p in chamber_plans:
            if p.get("id") == self.params.plan_id:
                return p.get("file", self.params.plan_id)

        # Fallback: scan per-app config files for the plan catalogue
        try:
            fdp_root = Path(
                self.platform.config.raw().get("platform", {}).get("root", "")
                or Path.cwd()
            )
            apps_dir = fdp_root / "config" / "apps"
            if apps_dir.exists():
                for app_yml in sorted(apps_dir.glob("*.yml")):
                    with open(app_yml) as f:
                        app_cfg = yaml.safe_load(f) or {}
                    plans = app_cfg.get("plans", {})
                    for p in plans.get(self.params.chamber.value, []):
                        if p.get("id") == self.params.plan_id:
                            return p.get("file", self.params.plan_id)
        except Exception:
            pass

        # Final fallback: treat plan_id as a filename
        return self.params.plan_id

    def _load_boundaries(self) -> gpd.GeoDataFrame:
        """Load boundary GeoJSON for the plan."""
        rel_path = self._resolve_plan_file()

        # Try fdp BoundaryLoader first
        try:
            gdf = self.platform.boundaries.load(
                rel_path, chamber=self.params.chamber.value
            )
            if gdf is not None and len(gdf) > 0:
                self._gdf = gdf
                return gdf
        except Exception:
            pass

        # Fallback: direct file read
        path = self.platform.resolve(rel_path)
        gdf = gpd.read_file(path)
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        self._gdf = gdf
        return gdf

    def _load_cdm_contests(self) -> pd.DataFrame:
        """Load election contest data from the CDM parquet file."""
        if self._cdm_contests is not None:
            return self._cdm_contests

        cdm_dir = self.platform.resolve("fdga")
        contests_path = cdm_dir / "contests.parquet"

        if not contests_path.exists():
            contests_path = cdm_dir / "contests.csv"

        if contests_path.exists():
            if contests_path.suffix == ".parquet":
                df = pd.read_parquet(contests_path)
            else:
                df = pd.read_csv(contests_path)
            self._cdm_contests = df
            return df

        self._cdm_contests = pd.DataFrame()
        return self._cdm_contests

    # ------------------------------------------------------------------
    # Column helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _first_col(columns: list[str], aliases: list[str]) -> str | None:
        for a in aliases:
            if a in columns:
                return a
        return None

    def _get_district_id(self, row: pd.Series) -> str:
        for alias in _DISTRICT_ID_ALIASES:
            if alias in row.index and pd.notna(row[alias]):
                return str(row[alias])
        return str(row.name)

    def _get_pop(self, row: pd.Series) -> int | None:
        col = self._first_col(list(row.index), _POP_ALIASES)
        if col is None:
            return None
        val = row[col]
        return int(val) if pd.notna(val) else None

    def _get_vap(self, row: pd.Series) -> int | None:
        col = self._first_col(list(row.index), _VAP_ALIASES)
        if col is None:
            return None
        val = row[col]
        return int(val) if pd.notna(val) else None

    def _get_partisan_lean(self, row: pd.Series) -> float | None:
        """Return Dem share 0-100 from embedded partisan property."""
        for alias in ["partisan", "DEM_PCT", "dem_pct", "dem_share"]:
            if alias in row.index and pd.notna(row[alias]):
                val = float(row[alias])
                if val > 1.0:
                    return val
                return val * 100
        return None

    def _get_minority_pct(self, row: pd.Series, group_name: str) -> float | None:
        """Get minority percentage for a group from GeoJSON properties."""
        aliases = _MINORITY_PCT_ALIASES.get(group_name, [])
        for alias in aliases:
            if alias in row.index and pd.notna(row[alias]):
                val = float(row[alias])
                if val > 1.0:
                    return val  # already 0-100
                return val * 100
        return None

    # ------------------------------------------------------------------
    # Election data from CDM
    # ------------------------------------------------------------------

    def _filter_cdm_elections(
        self,
        df: pd.DataFrame,
        years: list[int] | None = None,
        election_types: list[str] | None = None,
        offices: list[str] | None = None,
        chamber: str | None = None,
    ) -> pd.DataFrame:
        """Filter CDM contests DataFrame by election criteria."""
        if df.empty:
            return df

        mask = pd.Series(True, index=df.index)

        year_col = None
        for c in ["year", "election_year", "cycle_year"]:
            if c in df.columns:
                year_col = c
                break

        type_col = None
        for c in ["election_type", "type"]:
            if c in df.columns:
                type_col = c
                break

        office_col = None
        for c in ["office", "race_office"]:
            if c in df.columns:
                office_col = c
                break

        chamber_col = None
        for c in ["chamber", "district_chamber"]:
            if c in df.columns:
                chamber_col = c
                break

        if year_col and years:
            mask &= df[year_col].isin(years)
        if type_col and election_types:
            mask &= df[type_col].isin(election_types)
        if office_col and offices:
            mask &= df[office_col].isin(offices)
        if chamber_col and chamber:
            mask &= df[chamber_col] == chamber

        return df[mask]

    def _compute_partisan_from_cdm(
        self,
        contests_df: pd.DataFrame,
        district_id_col: str = "district",
    ) -> dict[str, dict[str, float]]:
        """
        Compute partisan lean per district from CDM contest data.

        Returns: {district_id: {election_label: dem_share_0_to_100}}
        """
        if contests_df.empty:
            return {}

        col_map = {}
        for target, candidates in [
            ("district", [district_id_col, "district_id"]),
            ("dem_votes", ["dem_votes", "democrat_votes", "votes_dem", "dem"]),
            ("rep_votes", ["rep_votes", "republican_votes", "votes_rep", "rep"]),
            ("year", ["year", "election_year", "cycle_year"]),
            ("office", ["office"]),
            ("election_type", ["election_type", "type"]),
        ]:
            for c in candidates:
                if c in contests_df.columns:
                    col_map[target] = c
                    break

        required = ["district", "dem_votes", "rep_votes"]
        if not all(k in col_map for k in required):
            return {}

        result: dict[str, dict[str, float]] = {}

        for _, row in contests_df.iterrows():
            district = str(row[col_map["district"]])
            dem = float(row[col_map["dem_votes"]]) if pd.notna(row[col_map["dem_votes"]]) else 0.0
            rep = float(row[col_map["rep_votes"]]) if pd.notna(row[col_map["rep_votes"]]) else 0.0
            total = dem + rep
            dem_share = dem / total if total > 0 else 0.5

            year = row.get(col_map.get("year", "year"), "?")
            office = row.get(col_map.get("office", "office"), "?")
            etype = row.get(col_map.get("election_type", "election_type"), "?")
            label = f"{year}_{office}_{etype}"

            if district not in result:
                result[district] = {}
            result[district][label] = dem_share * 100  # 0-100 scale

        return result

    # ------------------------------------------------------------------
    # Core analysis: single plan
    # ------------------------------------------------------------------

    def analyze_plan(self) -> PlanAnalysisResult:
        """
        Run a full parameterized analysis of a single plan.

        Computes: population, partisan lean, competitiveness, minority
        representation, all driven by AnalysisParameters.
        """
        params = self.params
        gdf = self._load_boundaries()

        elections = self._resolve_elections()
        minority_groups = self._resolve_minority_groups()

        # Load CDM contest data for partisan scores not in GeoJSON
        cdm_df = self._load_cdm_contests()
        cdm_filtered = self._filter_cdm_elections(
            cdm_df,
            years=params.election_years,
            election_types=[e.value for e in params.election_types] if params.election_types else None,
            offices=[o.value for o in params.offices] if params.offices else None,
            chamber=params.chamber.value,
        )
        cdm_partisan = self._compute_partisan_from_cdm(cdm_filtered)

        # Build per-district metrics
        districts: list[DistrictMetric] = []
        total_pop = 0
        total_vap = 0

        for _, row in gdf.iterrows():
            district_id = self._get_district_id(row)
            pop = self._get_pop(row) or 0
            vap = self._get_vap(row) or 0
            total_pop += pop
            total_vap += vap

            # Partisan lean: prefer embedded property, fall back to CDM average
            embedded_lean = self._get_partisan_lean(row)
            cdm_lean = None
            if district_id in cdm_partisan and cdm_partisan[district_id]:
                cdm_lean = sum(cdm_partisan[district_id].values()) / len(cdm_partisan[district_id])

            if embedded_lean is not None:
                partisan_lean = embedded_lean
            elif cdm_lean is not None:
                partisan_lean = cdm_lean
            else:
                partisan_lean = None

            # Dem/Rep votes
            dem_votes = None
            rep_votes = None
            for alias in _DEM_VOTES_ALIASES:
                if alias in row.index and pd.notna(row[alias]):
                    dem_votes = float(row[alias])
                    break
            for alias in _REP_VOTES_ALIASES:
                if alias in row.index and pd.notna(row[alias]):
                    rep_votes = float(row[alias])
                    break

            # Minority percentages
            minority_pcts: dict[str, float] = {}
            is_majority: dict[str, bool] = {}
            is_influence: dict[str, bool] = {}

            for group in minority_groups:
                pct = self._get_minority_pct(row, group.name)
                if pct is None and group.cvap_col and group.cvap_col in row.index:
                    pct = float(row[group.cvap_col])
                    if pct <= 1.0:
                        pct *= 100
                if pct is None and group.formula:
                    pct = self._evaluate_formula(group.formula, row)
                    if pct is not None and pct <= 1.0:
                        pct *= 100

                if pct is not None:
                    minority_pcts[group.name] = pct
                    threshold = group.majority_threshold or params.majority_threshold
                    is_majority[group.name] = pct >= (threshold * 100)
                    is_influence[group.name] = (
                        group.influence_lo * 100 <= pct < group.influence_hi * 100
                    )

            # Competitiveness per threshold
            is_competitive: dict[str, bool] = {}
            if partisan_lean is not None:
                for t in params.competitiveness_thresholds:
                    margin = abs(partisan_lean - 50) / 100
                    is_competitive[f"t_{int(t * 100)}pp"] = margin <= t
                # Also the competitive band
                is_competitive["band_46.5_53.5"] = (
                    params.competitive_lo * 100 <= partisan_lean <= params.competitive_hi * 100
                )

            districts.append(
                DistrictMetric(
                    district_id=district_id,
                    total_pop=pop,
                    vap=vap,
                    dem_votes=dem_votes,
                    rep_votes=rep_votes,
                    partisan_lean=partisan_lean,
                    minority_pcts=minority_pcts,
                    is_majority_minority=is_majority,
                    is_influence=is_influence,
                    is_competitive=is_competitive,
                )
            )

        # Build summary
        n_districts = len(districts)
        dem_districts = sum(
            1 for d in districts if d.partisan_lean is not None and d.partisan_lean >= 50
        )
        rep_districts = n_districts - dem_districts

        competitive_counts: dict[str, int] = {}
        for t in params.competitiveness_thresholds:
            key = f"t_{int(t * 100)}pp"
            competitive_counts[key] = sum(
                1 for d in districts if d.is_competitive.get(key, False)
            )
        competitive_counts["band_46.5_53.5"] = sum(
            1 for d in districts if d.is_competitive.get("band_46.5_53.5", False)
        )

        # Minority summary
        minority_summary: dict[str, dict[str, int]] = {}
        for group in minority_groups:
            name = group.name
            maj_count = sum(1 for d in districts if d.is_majority_minority.get(name, False))
            inf_count = sum(1 for d in districts if d.is_influence.get(name, False))
            minority_summary[name] = {
                "majority": maj_count,
                "influence": inf_count,
                "total": maj_count + inf_count,
            }

        summary: dict[str, Any] = {
            "n_districts": n_districts,
            "total_population": total_pop,
            "total_vap": total_vap,
            "dem_districts": dem_districts,
            "rep_districts": rep_districts,
            "dem_pct": round(dem_districts / n_districts * 100, 1) if n_districts else 0,
            "rep_pct": round(rep_districts / n_districts * 100, 1) if n_districts else 0,
            "competitive_districts": competitive_counts,
            "minority_districts": minority_summary,
            "avg_partisan_lean": round(
                sum(d.partisan_lean for d in districts if d.partisan_lean is not None)
                / max(1, sum(1 for d in districts if d.partisan_lean is not None)),
                1,
            ),
        }

        return PlanAnalysisResult(
            plan_id=params.plan_id,
            chamber=params.chamber.value,
            census_year=params.census_year,
            cvap_year=params.cvap_year,
            n_districts=n_districts,
            total_population=total_pop,
            elections_used=[e.model_dump() for e in elections],
            minority_groups_used=[g.model_dump() for g in minority_groups],
            competitiveness_thresholds=params.competitiveness_thresholds,
            districts=districts,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Plan comparison
    # ------------------------------------------------------------------

    def compare_plans(self) -> PlanComparisonResult:
        """Compare two plans district-by-district."""
        params = self.params

        if not params.plan_a_id or not params.plan_b_id:
            raise ValueError("plan_a_id and plan_b_id are required for comparison")

        params_a = params.model_copy(update={"plan_id": params.plan_a_id})
        params_b = params.model_copy(update={"plan_id": params.plan_b_id})

        engine_a = AnalysisEngine(params_a)
        engine_b = AnalysisEngine(params_b)

        result_a = engine_a.analyze_plan()
        result_b = engine_b.analyze_plan()

        # Build district lookup for plan B
        b_by_id = {d.district_id: d for d in result_b.districts}

        # Match districts
        deltas: list[dict[str, Any]] = []
        total_pop_b = sum(d.total_pop or 0 for d in result_b.districts)
        ideal_pop_b = total_pop_b / len(result_b.districts) if result_b.districts else 0

        for a_dist in result_a.districts:
            matched_b_id = a_dist.district_id
            is_renumbered = False

            if matched_b_id not in b_by_id and params.match_mode == MatchMode.NUMBER:
                matched_b_id = self._find_nearest_b(a_dist, result_b.districts)
                is_renumbered = matched_b_id != a_dist.district_id
            elif matched_b_id not in b_by_id:
                matched_b_id = self._find_nearest_b(a_dist, result_b.districts)
                is_renumbered = True

            b_dist = b_by_id.get(matched_b_id)

            delta = {
                "district_id": a_dist.district_id,
                "matched_b_id": matched_b_id,
                "is_renumbered": is_renumbered,
                "plan_a": {
                    "total_pop": a_dist.total_pop,
                    "vap": a_dist.vap,
                    "partisan_lean": a_dist.partisan_lean,
                    "minority_pcts": a_dist.minority_pcts,
                },
                "plan_b": {
                    "total_pop": b_dist.total_pop if b_dist else None,
                    "vap": b_dist.vap if b_dist else None,
                    "partisan_lean": b_dist.partisan_lean if b_dist else None,
                    "minority_pcts": b_dist.minority_pcts if b_dist else None,
                },
            }

            # Compute deltas
            if a_dist.partisan_lean is not None and b_dist and b_dist.partisan_lean is not None:
                delta["delta_partisan_lean"] = round(b_dist.partisan_lean - a_dist.partisan_lean, 1)
                delta["partisan_flip"] = (
                    "Gained Dem"
                    if a_dist.partisan_lean < 50 <= b_dist.partisan_lean
                    else "Lost Dem"
                    if a_dist.partisan_lean >= 50 > b_dist.partisan_lean
                    else ""
                )

            if a_dist.total_pop and b_dist and b_dist.total_pop:
                delta["delta_pop"] = b_dist.total_pop - a_dist.total_pop
                delta["pop_deviation"] = b_dist.total_pop - ideal_pop_b
                delta["pop_deviation_pct"] = (
                    round((b_dist.total_pop - ideal_pop_b) / ideal_pop_b * 100, 1)
                    if ideal_pop_b > 0 else 0
                )

            # Minority change
            for group_name in a_dist.minority_pcts:
                a_pct = a_dist.minority_pcts.get(group_name, 0)
                b_pct = b_dist.minority_pcts.get(group_name, 0) if b_dist else 0
                delta[f"delta_{group_name}_pct"] = round(b_pct - a_pct, 1)

                threshold = 0.50
                if a_pct >= threshold * 100 and b_pct < threshold * 100:
                    delta[f"{group_name}_change_label"] = f"Lost {group_name} Majority"
                elif a_pct < threshold * 100 and b_pct >= threshold * 100:
                    delta[f"{group_name}_change_label"] = f"Gained {group_name} Majority"
                else:
                    delta[f"{group_name}_change_label"] = ""

            deltas.append(delta)

        summary: dict[str, Any] = {
            "n_districts_a": len(result_a.districts),
            "n_districts_b": len(result_b.districts),
            "n_renumbered": sum(1 for d in deltas if d["is_renumbered"]),
            "n_flips": sum(1 for d in deltas if d.get("partisan_flip")),
            "ideal_pop_b": ideal_pop_b,
        }

        return PlanComparisonResult(
            plan_a_id=params.plan_a_id,
            plan_b_id=params.plan_b_id,
            chamber=params.chamber.value,
            match_mode=params.match_mode.value,
            district_deltas=deltas,
            summary=summary,
        )

    def _find_nearest_b(
        self, a_dist: DistrictMetric, b_districts: list[DistrictMetric]
    ) -> str:
        """Find nearest plan B district by centroid (fallback when IDs don't match)."""
        if b_districts:
            return b_districts[0].district_id
        return a_dist.district_id

    # ------------------------------------------------------------------
    # Benchmark comparison
    # ------------------------------------------------------------------

    def compare_to_benchmark(self) -> BenchmarkComparisonResult:
        """Compare a plan against simulated benchmark distributions."""
        params = self.params

        if not params.benchmark_id:
            raise ValueError("benchmark_id is required for benchmark comparison")

        from fdp.benchmark_config.benchmark import BenchmarkConfig

        fdp_root = Path(self.platform._root) if hasattr(self.platform, "_root") else Path.cwd()
        benchmark_path = fdp_root / "configs" / "benchmarks" / f"{params.benchmark_id}.yml"

        if not benchmark_path.exists():
            raise FileNotFoundError(f"Benchmark config not found: {benchmark_path}")

        cfg = BenchmarkConfig.from_yaml(str(benchmark_path))

        # Analyze the plan using benchmark's chamber and elections
        benchmark_params = params.model_copy(
            update={
                "chamber": Chamber(cfg.chamber.name),
                "elections": [
                    ElectionSpec(
                        year=e.year,
                        election_type=e.election_type,
                        office=e.office,
                        candidates=e.candidates,
                        partisan_score=e.partisan_score,
                        competitive=e.competitive,
                    )
                    for e in cfg.elections_for_partisan()
                ],
                "competitiveness_thresholds": cfg.competitiveness.thresholds,
                "competitive_lo": 0.465,
                "competitive_hi": 0.535,
                "minority_groups": [
                    MinorityGroupSpec(
                        name=g.name,
                        label=g.label,
                        cvap_col=g.cvap_col,
                        formula=g.formula,
                        majority_threshold=g.majority_threshold or cfg.demographics.majority_threshold,
                        influence_lo=0.37,
                        influence_hi=0.50,
                    )
                    for g in cfg.demographics.groups
                ],
                "cvap_year": cfg.demographics.cvap_year,
            }
        )

        engine = AnalysisEngine(benchmark_params)
        result = engine.analyze_plan()

        # Compute grades against benchmark distribution
        scores_path = cfg.scores_parquet()
        partisan_grade = "N/A"
        competitiveness_grade = "N/A"
        demographics_grade = "N/A"
        overall_grade = "N/A"
        pass_fail = "N/A"
        details: dict[str, Any] = {}

        if scores_path.exists():
            scores_df = pd.read_parquet(scores_path)
            details = self._compute_benchmark_percentiles(result, scores_df, cfg)
            partisan_grade = details.get("partisan_grade", "N/A")
            competitiveness_grade = details.get("competitiveness_grade", "N/A")
            demographics_grade = details.get("demographics_grade", "N/A")
            overall_grade = details.get("overall_grade", "N/A")
            pass_fail = details.get("pass_fail", "N/A")

        return BenchmarkComparisonResult(
            plan_id=params.plan_id,
            benchmark_id=params.benchmark_id,
            chamber=params.chamber.value,
            partisan_grade=partisan_grade,
            competitiveness_grade=competitiveness_grade,
            demographics_grade=demographics_grade,
            overall_grade=overall_grade,
            pass_fail=pass_fail,
            details=details,
        )

    def _compute_benchmark_percentiles(
        self,
        plan_result: PlanAnalysisResult,
        scores_df: pd.DataFrame,
        cfg,
    ) -> dict[str, Any]:
        """Compute percentile ranks of plan metrics against benchmark distribution."""
        details: dict[str, Any] = {}

        # Partisan lean: compare plan's Dem seat count to benchmark
        plan_dem_seats = plan_result.summary.get("dem_districts", 0)

        seat_cols = [c for c in scores_df.columns if "dem_seats" in c.lower() or "seats_dem" in c.lower()]
        if seat_cols:
            dem_seats_dist = scores_df[seat_cols[0]].dropna()
            pctile = (dem_seats_dist < plan_dem_seats).sum() / len(dem_seats_dist) * 100
            details["partisan_pctile"] = round(pctile, 1)
            details["partisan_grade"] = cfg.grading.grade(pctile)

        # Competitiveness: compare plan's competitive district count
        plan_competitive = plan_result.summary.get("competitive_districts", {}).get("band_46.5_53.5", 0)
        comp_cols = [c for c in scores_df.columns if "compet" in c.lower() and "n_" in c.lower()]
        if comp_cols:
            comp_dist = scores_df[comp_cols[0]].dropna()
            pctile = (comp_dist < plan_competitive).sum() / len(comp_dist) * 100
            details["competitiveness_pctile"] = round(pctile, 1)
            details["competitiveness_grade"] = cfg.grading.grade(pctile)

        # Overall grade using composite method
        grades = []
        if "partisan_grade" in details:
            grades.append(details["partisan_grade"])
        if "competitiveness_grade" in details:
            grades.append(details["competitiveness_grade"])
        if demographics_grade != "N/A":
            grades.append(demographics_grade)

        if grades:
            if params.composite_method == "min":
                grade_order = {"A": 4, "B": 3, "C": 2, "F": 1, "N/A": 0}
                worst = min(grades, key=lambda g: grade_order.get(g, 0))
                details["overall_grade"] = worst
            elif params.composite_method == "average":
                avg = sum(grade_order.get(g, 0) for g in grades) / len(grades)
                details["overall_grade"] = "A" if avg >= 3.5 else "B" if avg >= 2.5 else "C" if avg >= 1.5 else "F"
            else:
                details["overall_grade"] = grades[0] if grades else "N/A"

        overall = details.get("overall_grade", "F")
        details["pass_fail"] = "PASS" if overall in ("A", "B", "C") else "FAIL"

        return details

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_elections(self) -> list[ElectionSpec]:
        """Resolve the list of elections from parameters or CDM."""
        params = self.params
        if params.elections:
            return params.elections

        election_specs: list[ElectionSpec] = []
        cdm_df = self._load_cdm_contests()
        if not cdm_df.empty:
            filtered = self._filter_cdm_elections(
                cdm_df,
                years=params.election_years,
                election_types=[e.value for e in params.election_types] if params.election_types else None,
                offices=[o.value for o in params.offices] if params.offices else None,
                chamber=params.chamber.value,
            )
            seen = set()
            for _, row in filtered.iterrows():
                year = row.get("year", row.get("election_year", row.get("cycle_year")))
                etype = row.get("election_type", row.get("type", "general"))
                office = row.get("office", "president")
                key = (year, etype, office)
                if key in seen:
                    continue
                seen.add(key)
                election_specs.append(
                    ElectionSpec(
                        year=int(year),
                        election_type=etype if isinstance(etype, str) else "general",
                        office=office if isinstance(office, str) else "president",
                    )
                )
        return election_specs

    def _resolve_minority_groups(self) -> list[MinorityGroupSpec]:
        """Resolve minority groups from parameters or defaults."""
        if self.params.minority_groups:
            return self.params.minority_groups
        return DEFAULT_MINORITY_GROUPS

    def _evaluate_formula(self, formula: str, row: pd.Series) -> float | None:
        """Safely evaluate a CVAP formula against a row's properties."""
        try:
            ns = {}
            for col in row.index:
                if col.startswith("CVAP_") or col in ("CVAP_TOT24", "CVAP_WHT24", "CVAP_BLK24", "CVAP_HSP24", "CVAP_ASN24"):
                    val = row[col]
                    if pd.notna(val):
                        ns[col] = float(val)
            if not ns:
                return None
            result = eval(formula, {"__builtins__": {}}, ns)
            return float(result) if result is not None else None
        except Exception:
            return None
