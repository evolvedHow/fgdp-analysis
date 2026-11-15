"""
FDP Parameterized Redistricting Analysis.

Provides a fully parameterized analysis engine that works for any census
year, election cycle, chamber, minority group definition, or competitiveness
threshold. As long as data exists in fdp for a given cycle, the same code
runs without modification.

Usage:
    from fdp.analysis.engine import AnalysisEngine
    from fdp.analysis.parameters import AnalysisParameters, Chamber

    params = AnalysisParameters(
        chamber=Chamber.CONGRESS,
        census_year=2020,
        cvap_year=2024,
        plan_id="congress_enacted_24",
        competitiveness_thresholds=[0.035, 0.05],
    )
    engine = AnalysisEngine(params)
    result = engine.analyze_plan()
"""

from fdp.analysis.engine import AnalysisEngine
from fdp.analysis.parameters import (
    AnalysisParameters,
    BenchmarkComparisonResult,
    Chamber,
    DistrictMetric,
    ElectionSpec,
    ElectionType,
    MatchMode,
    MinorityGroupSpec,
    Office,
    PlanAnalysisResult,
    PlanComparisonResult,
)

__all__ = [
    "AnalysisEngine",
    "AnalysisParameters",
    "BenchmarkComparisonResult",
    "Chamber",
    "DistrictMetric",
    "ElectionSpec",
    "ElectionType",
    "MatchMode",
    "MinorityGroupSpec",
    "Office",
    "PlanAnalysisResult",
    "PlanComparisonResult",
]
