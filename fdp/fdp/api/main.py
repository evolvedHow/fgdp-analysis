"""
FDP Analysis REST API.

Exposes the parameterized analysis engine as versioned REST endpoints.
Every dimension (census year, election year/type/office, chamber, minority
groups, competitiveness thresholds) is a query parameter -- nothing is
hardcoded for a specific cycle.

Endpoints:
  POST /api/v1/analysis/plan          -> single-plan analysis
  POST /api/v1/analysis/compare       -> two-plan comparison
  POST /api/v1/analysis/benchmark     -> benchmark comparison
  POST /api/v1/analysis/question      -> natural language query (NLQ)
  GET  /api/v1/analysis/catalog       -> list available plans
  GET  /api/v1/analysis/health        -> health check

Run standalone:
    uv run --project fdp python -m fdp.api.main
    # or with uvicorn:
    uv run --project fdp uvicorn fdp.api.main:app --reload --port 8000
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fdp import DataPlatform
from fdp.analysis.engine import AnalysisEngine
from fdp.analysis.nlq import analyze_question as nlq_analyze_question
from fdp.analysis.parameters import (
    AnalysisParameters,
    BenchmarkComparisonResult,
    Chamber,
    ElectionSpec,
    MatchMode,
    MinorityGroupSpec,
    PlanAnalysisResult,
    PlanComparisonResult,
)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/analysis")


# ---------------------------------------------------------------------------
# Request/Response wrappers
# ---------------------------------------------------------------------------

class AnalyzePlanRequest(BaseModel):
    """Request body for single-plan analysis."""

    chamber: Chamber = Chamber.CONGRESS
    census_year: int = 2020
    geo_level: str = "vtd"
    plan_id: str
    plan_file: str | None = None
    plan_a_id: str | None = None
    plan_b_id: str | None = None
    elections: list[ElectionSpec] | None = None
    election_years: list[int] | None = None
    election_types: list[str] | None = None
    offices: list[str] | None = None
    cvap_year: int = 2024
    minority_groups: list[MinorityGroupSpec] | None = None
    majority_threshold: float = 0.50
    competitiveness_thresholds: list[float] | None = None
    competitive_lo: float = 0.465
    competitive_hi: float = 0.535
    reference_layer: str = "county"
    match_mode: MatchMode = MatchMode.NUMBER
    match_threshold_km: float = 20.0
    benchmark_id: str | None = None
    composite_method: str = "min"
    repo: str | None = None
    halt_on_error: bool = False


class AnalyzePlanResponse(BaseModel):
    ok: bool
    result: PlanAnalysisResult | None = None
    error: str | None = None


class ComparePlansRequest(BaseModel):
    """Request body for two-plan comparison."""

    chamber: Chamber = Chamber.CONGRESS
    census_year: int = 2020
    geo_level: str = "vtd"
    plan_a_id: str
    plan_b_id: str
    plan_file_a: str | None = None
    plan_file_b: str | None = None
    elections: list[ElectionSpec] | None = None
    election_years: list[int] | None = None
    election_types: list[str] | None = None
    offices: list[str] | None = None
    cvap_year: int = 2024
    minority_groups: list[MinorityGroupSpec] | None = None
    majority_threshold: float = 0.50
    competitiveness_thresholds: list[float] | None = None
    competitive_lo: float = 0.465
    competitive_hi: float = 0.535
    reference_layer: str = "county"
    match_mode: MatchMode = MatchMode.NUMBER
    match_threshold_km: float = 20.0
    repo: str | None = None
    halt_on_error: bool = False


class ComparePlansResponse(BaseModel):
    ok: bool
    result: PlanComparisonResult | None = None
    error: str | None = None


class BenchmarkRequest(BaseModel):
    """Request body for benchmark comparison."""

    chamber: Chamber = Chamber.CONGRESS
    census_year: int = 2020
    geo_level: str = "vtd"
    plan_id: str
    cvap_year: int = 2024
    minority_groups: list[MinorityGroupSpec] | None = None
    majority_threshold: float = 0.50
    competitiveness_thresholds: list[float] | None = None
    competitive_lo: float = 0.465
    competitive_hi: float = 0.535
    benchmark_id: str
    composite_method: str = "min"
    repo: str | None = None
    halt_on_error: bool = False


class BenchmarkResponse(BaseModel):
    ok: bool
    result: BenchmarkComparisonResult | None = None
    error: str | None = None


class QuestionRequest(BaseModel):
    """Request body for natural language query."""

    question: str = Field(..., description="Free-form redistricting question in natural language")


class QuestionResponse(BaseModel):
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "service": "fdp-analysis-api"}


@router.get("/catalog")
def catalog(
    chamber: Chamber | None = Query(None, description="Filter by chamber"),
) -> dict[str, Any]:
    """List available plans from fdp app configs.

    Reads all ``config/apps/*.yml`` files directly since DataPlatform(app=None)
    only loads global + defaults, not per-app overrides.
    """
    platform = DataPlatform(app=None, repo=None)
    fdp_root = Path(platform.config.raw().get("platform", {}).get("root", "")) or Path.cwd()
    apps_dir = fdp_root / "config" / "apps"

    catalog: dict[str, list[dict[str, Any]]] = {}
    if apps_dir.exists():
        for app_yml in sorted(apps_dir.glob("*.yml")):
            with open(app_yml) as f:
                app_cfg = yaml.safe_load(f) or {}
            plans = app_cfg.get("plans", {})
            for ch, plan_list in plans.items():
                if chamber and ch != chamber.value:
                    continue
                entries = []
                for p in plan_list or []:
                    entries.append({
                        "id": p.get("id"),
                        "label": p.get("label"),
                        "chamber": ch,
                        "file": p.get("file"),
                        "app": app_yml.stem,
                    })
                catalog.setdefault(ch, []).extend(entries)

    return {"plans": catalog, "chambers": [c.value for c in Chamber]}


@router.post("/plan", response_model=AnalyzePlanResponse)
def analyze_plan(req: AnalyzePlanRequest) -> AnalyzePlanResponse:
    """Run a full parameterized analysis of a single plan."""
    try:
        params = AnalysisParameters(
            chamber=req.chamber,
            census_year=req.census_year,
            geo_level=req.geo_level,
            plan_id=req.plan_id,
            plan_file=req.plan_file,
            plan_a_id=req.plan_a_id,
            plan_b_id=req.plan_b_id,
            elections=req.elections or [],
            election_years=req.election_years,
            election_types=req.election_types,
            offices=req.offices,
            cvap_year=req.cvap_year,
            minority_groups=req.minority_groups or [],
            majority_threshold=req.majority_threshold,
            competitiveness_thresholds=req.competitiveness_thresholds or [0.035, 0.05],
            competitive_lo=req.competitive_lo,
            competitive_hi=req.competitive_hi,
            reference_layer=req.reference_layer,
            match_mode=req.match_mode,
            match_threshold_km=req.match_threshold_km,
            repo=req.repo,
            halt_on_error=req.halt_on_error,
        )

        engine = AnalysisEngine(params)
        result = engine.analyze_plan()
        return AnalyzePlanResponse(ok=True, result=result)

    except Exception as exc:
        return AnalyzePlanResponse(ok=False, error=str(exc))


@router.post("/compare", response_model=ComparePlansResponse)
def compare_plans(req: ComparePlansRequest) -> ComparePlansResponse:
    """Compare two plans district-by-district."""
    try:
        params = AnalysisParameters(
            chamber=req.chamber,
            census_year=req.census_year,
            geo_level=req.geo_level,
            plan_id=req.plan_a_id,
            plan_file=None,
            plan_a_id=req.plan_a_id,
            plan_b_id=req.plan_b_id,
            elections=req.elections or [],
            election_years=req.election_years,
            election_types=req.election_types,
            offices=req.offices,
            cvap_year=req.cvap_year,
            minority_groups=req.minority_groups or [],
            majority_threshold=req.majority_threshold,
            competitiveness_thresholds=req.competitiveness_thresholds or [0.035, 0.05],
            competitive_lo=req.competitive_lo,
            competitive_hi=req.competitive_hi,
            reference_layer=req.reference_layer,
            match_mode=req.match_mode,
            match_threshold_km=req.match_threshold_km,
            repo=req.repo,
            halt_on_error=req.halt_on_error,
        )

        engine = AnalysisEngine(params)
        result = engine.compare_plans()
        return ComparePlansResponse(ok=True, result=result)

    except Exception as exc:
        return ComparePlansResponse(ok=False, error=str(exc))


@router.post("/benchmark", response_model=BenchmarkResponse)
def benchmark(req: BenchmarkRequest) -> BenchmarkResponse:
    """Compare a plan against a simulated benchmark distribution."""
    try:
        params = AnalysisParameters(
            chamber=req.chamber,
            census_year=req.census_year,
            geo_level=req.geo_level,
            plan_id=req.plan_id,
            plan_file=None,
            elections=[],
            cvap_year=req.cvap_year,
            minority_groups=req.minority_groups or [],
            majority_threshold=req.majority_threshold,
            competitiveness_thresholds=req.competitiveness_thresholds or [0.035, 0.05],
            competitive_lo=req.competitive_lo,
            competitive_hi=req.competitive_hi,
            benchmark_id=req.benchmark_id,
            composite_method=req.composite_method,
            repo=req.repo,
            halt_on_error=req.halt_on_error,
        )

        engine = AnalysisEngine(params)
        result = engine.compare_to_benchmark()
        return BenchmarkResponse(ok=True, result=result)

    except Exception as exc:
        return BenchmarkResponse(ok=False, error=str(exc))


@router.post("/question", response_model=QuestionResponse)
def analyze_question(req: QuestionRequest) -> QuestionResponse:
    """
    Natural language query about redistricting.

    Translates the question into a structured analysis using only data that
    actually exists in fdp. If the question requires data that is not
    available, returns a missing_data response explaining what is needed.

    Example:
      "What was the minority VAP in the 2024 congressional map compared to 2022?"
    """
    try:
        result = nlq_analyze_question(req.question)
        if result.get("type") == "error":
            return QuestionResponse(ok=False, error=result.get("error"), result=result)
        return QuestionResponse(ok=True, result=result)
    except Exception as exc:
        return QuestionResponse(ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# Standalone app (for `uvicorn fdp.api.main:app`)
# ---------------------------------------------------------------------------

def create_analysis_app() -> FastAPI:
    """Create a standalone FastAPI app for the analysis router."""
    application = FastAPI(
        title="FDP Redistricting Analysis API",
        version="1.0.0",
        description=(
            "Parameterized redistricting analysis for the Fair Districts Data "
            "Platform. All dimensions (census year, election year/type/office, "
            "chamber, minority groups, competitiveness thresholds) are runtime "
            "parameters."
        ),
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(router)
    return application


app = create_analysis_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
