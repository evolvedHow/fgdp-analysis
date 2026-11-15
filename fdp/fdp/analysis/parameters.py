"""
Fully parameterized analysis request models.

Every dimension that could vary between election cycles -- census year,
election year/type/office, chamber, minority group definitions,
competitiveness thresholds -- is a parameter. Nothing is hardcoded.

As long as data exists in fdp (boundaries, elections, demographics, CDM)
for a given cycle, these models accept it without code changes.
"""

from __future__ import annotations

from typing import Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator


class Chamber(str, Enum):
    CONGRESS = "congress"
    SENATE = "senate"
    HOUSE = "house"


class ElectionType(str, Enum):
    GENERAL = "general"
    RUNOFF = "runoff"
    SPECIAL = "special"
    PRIMARY = "primary"

    @classmethod
    def _missing_(cls, value: str) -> "ElectionType":
        """Gracefully handle unknown election type values from CDM data."""
        normalized = value.lower().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == normalized:
                return member
        return cls.GENERAL


class Office(str, Enum):
    PRESIDENT = "president"
    GOVERNOR = "governor"
    SENATE = "senate"
    US_HOUSE = "us-house"
    STATE_REP = "state-rep"
    STATE_HOUSE = "state_house"
    STATE_SENATE = "state_senate"

    @classmethod
    def _missing_(cls, value: str) -> "Office":
        """Gracefully handle unknown office values from CDM data."""
        # Try common normalizations
        normalized = value.lower().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == normalized:
                return member
        # Default to president as a safe fallback
        return cls.PRESIDENT


class CompositeMethod(str, Enum):
    MIN = "min"
    AVERAGE = "average"
    WEIGHTED = "weighted"


class MatchMode(str, Enum):
    NUMBER = "number"
    GEOGRAPHY = "geography"


class MinorityGroupSpec(BaseModel):
    """A single minority/majority group definition for demographic analysis.

    Either ``cvap_col`` (a column name in the CVAP data) or ``formula``
    (a Python expression referencing CVAP columns) must be provided.
    """

    name: str = Field(
        ..., description="Slug: black, white, hispanic, asian, minority_coalition, ..."
    )
    label: str = Field(..., description="Human-readable label for output")
    cvap_col: str | None = Field(
        None,
        description="CVAP column name (e.g. CVAP_BLK24, CVAP_WHT24, CVAP_HSP24)",
    )
    formula: str | None = Field(
        None,
        description="Python expression using CVAP columns (e.g. '1 - CVAP_WHT24 / CVAP_TOT24')",
    )
    majority_threshold: float = Field(
        0.50,
        ge=0.0,
        le=1.0,
        description="Fraction above which a district counts as majority for this group",
    )
    influence_lo: float = Field(
        0.37,
        ge=0.0,
        le=1.0,
        description="Lower bound for 'influence' district classification",
    )
    influence_hi: float = Field(
        0.50,
        ge=0.0,
        le=1.0,
        description="Upper bound for 'influence' district classification",
    )

    @model_validator(mode="after")
    def _check_col_or_formula(self) -> "MinorityGroupSpec":
        if self.cvap_col is None and self.formula is None:
            raise ValueError(
                f"MinorityGroup '{self.name}' must specify cvap_col or formula"
            )
        return self


class ElectionSpec(BaseModel):
    """A single election to include in partisan/competitiveness analysis."""

    year: int = Field(..., ge=1789, description="Election year")
    election_type: ElectionType = ElectionType.GENERAL
    office: Office = Office.PRESIDENT
    candidates: list[str] | None = Field(
        None,
        description="Optional filter to specific candidate codes (e.g. ['WAR', 'LOE'] for a runoff)",
    )
    partisan_score: bool = Field(
        True,
        description="Include in partisan lean scoring",
    )
    competitive: bool = Field(
        True,
        description="Include in competitiveness scoring",
    )


class AnalysisParameters(BaseModel):
    """Complete parameter set for any redistricting analysis.

    All fields are optional with sensible defaults, but every dimension
    that varies by cycle can be overridden.
    """

    # ── Geography ──────────────────────────────────────────────────────
    chamber: Chamber = Field(
        Chamber.CONGRESS,
        description="Chamber to analyze: congress, senate, house",
    )
    census_year: int = Field(
        2020,
        ge=1790,
        le=2100,
        description="Census vintage year for boundaries and demographics",
    )
    geo_level: str = Field(
        "vtd",
        description="Geographic level: vtd, precinct, block, county",
    )

    # ── Plan selection ─────────────────────────────────────────────────
    plan_id: str | None = Field(
        None,
        description="Logical plan ID from the app config (e.g. congress_enacted_24)",
    )
    plan_file: str | None = Field(
        None,
        description="Override: explicit path to a plan GeoJSON (workspace-relative)",
    )
    plan_a_id: str | None = Field(
        None,
        description="For comparisons: first plan ID",
    )
    plan_b_id: str | None = Field(
        None,
        description="For comparisons: second plan ID",
    )

    @model_validator(mode="after")
    def _check_plan_selection(self) -> "AnalysisParameters":
        """Ensure at least one plan identifier is provided."""
        if not self.plan_id and not self.plan_a_id and not self.plan_b_id:
            raise ValueError(
                "At least one of plan_id, plan_a_id, or plan_b_id is required"
            )
        return self

    # ── Elections (partisan + competitiveness) ─────────────────────────
    elections: list[ElectionSpec] = Field(
        default_factory=list,
        description="Elections to include. If empty, all elections in the CDM for the chamber are used.",
    )
    election_years: list[int] | None = Field(
        None,
        description="Shorthand: include all elections from these years",
    )
    election_types: list[ElectionType] | None = Field(
        None,
        description="Filter elections by type",
    )
    offices: list[Office] | None = Field(
        None,
        description="Filter elections by office",
    )

    # ── Demographics (minority/majority) ───────────────────────────────
    cvap_year: int = Field(
        2024,
        ge=2000,
        le=2100,
        description="CVAP ACS vintage year",
    )
    minority_groups: list[MinorityGroupSpec] = Field(
        default_factory=list,
        description="Minority/majority groups to analyze. If empty, defaults to black/white/hispanic/minority_coalition.",
    )
    majority_threshold: float = Field(
        0.50,
        ge=0.0,
        le=1.0,
        description="Default majority threshold for groups that don't override it",
    )

    # ── Competitiveness ────────────────────────────────────────────────
    competitiveness_thresholds: list[float] = Field(
        default_factory=lambda: [0.035, 0.05],
        description="Margin thresholds for competitiveness (e.g. [0.035, 0.05] = +/-3.5pp, +/-5pp)",
    )
    competitive_lo: float = Field(
        0.465,
        ge=0.0,
        le=0.5,
        description="Lower bound of the competitive Dem-vote-share band",
    )
    competitive_hi: float = Field(
        0.535,
        ge=0.5,
        le=1.0,
        description="Upper bound of the competitive Dem-vote-share band",
    )

    # ── Spatial / community analysis ───────────────────────────────────
    reference_layer: str = Field(
        "county",
        description="Reference geography for split analysis: county, places, etc.",
    )
    match_mode: MatchMode = Field(
        MatchMode.NUMBER,
        description="How to pair districts between two plans: by number or by centroid proximity",
    )
    match_threshold_km: float = Field(
        20.0,
        ge=0.0,
        description="Max centroid distance (km) for geography-based matching",
    )

    # ── Benchmark comparison ───────────────────────────────────────────
    benchmark_id: str | None = Field(
        None,
        description="Benchmark config ID to compare against (from fdp/configs/benchmarks/)",
    )
    composite_method: CompositeMethod = Field(
        CompositeMethod.MIN,
        description="How to combine metric grades: min (worst), average, weighted",
    )

    # ── Runtime ────────────────────────────────────────────────────────
    repo: str | None = Field(
        None,
        description="fdp repo/workspace name (default: main or app config)",
    )
    halt_on_error: bool = Field(
        False,
        description="If True, data quality errors raise instead of warning",
    )

    @field_validator("competitiveness_thresholds")
    @classmethod
    def _validate_thresholds(cls, v: list[float]) -> list[float]:
        for t in v:
            if not 0.0 < t < 0.5:
                raise ValueError(f"Competitiveness threshold {t} must be between 0 and 0.5")
        return sorted(v)

    @field_validator("competitive_hi")
    @classmethod
    def _validate_competitive_band(cls, v: float, info) -> float:
        lo = info.data.get("competitive_lo", 0.465)
        if v <= lo:
            raise ValueError("competitive_hi must be greater than competitive_lo")
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DistrictMetric(BaseModel):
    """Per-district result for any analysis."""

    district_id: str
    total_pop: int | None = None
    vap: int | None = None
    dem_votes: float | None = None
    rep_votes: float | None = None
    partisan_lean: float | None = Field(
        None,
        description="Dem share 0-100",
    )
    minority_pcts: dict[str, float] = Field(
        default_factory=dict,
        description="Group name -> percentage of VAP",
    )
    is_majority_minority: dict[str, bool] = Field(
        default_factory=dict,
        description="Group name -> whether district is majority for that group",
    )
    is_influence: dict[str, bool] = Field(
        default_factory=dict,
        description="Group name -> whether district is influence for that group",
    )
    is_competitive: dict[str, bool] = Field(
        default_factory=dict,
        description="Threshold label -> whether district is competitive at that threshold",
    )


class PlanAnalysisResult(BaseModel):
    """Top-level result for a single plan analysis."""

    plan_id: str
    chamber: str
    census_year: int
    cvap_year: int
    n_districts: int
    total_population: int
    elections_used: list[dict[str, Any]]
    minority_groups_used: list[dict[str, Any]]
    competitiveness_thresholds: list[float]
    districts: list[DistrictMetric]
    summary: dict[str, Any]


class PlanComparisonResult(BaseModel):
    """Result for comparing two plans."""

    plan_a_id: str
    plan_b_id: str
    chamber: str
    match_mode: str
    district_deltas: list[dict[str, Any]]
    summary: dict[str, Any]


class BenchmarkComparisonResult(BaseModel):
    """Result comparing a plan against simulated benchmarks."""

    plan_id: str
    benchmark_id: str
    chamber: str
    partisan_grade: str
    competitiveness_grade: str
    demographics_grade: str
    overall_grade: str
    pass_fail: str
    details: dict[str, Any]


class AnalysisError(BaseModel):
    error: str
    detail: str | None = None
