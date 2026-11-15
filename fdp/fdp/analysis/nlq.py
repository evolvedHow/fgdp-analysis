"""
Natural Language Query (NLQ) layer for FDP redistricting analysis.

Translates free-form questions into structured AnalysisParameters, then
runs the AnalysisEngine. The LLM only translates — it never sees raw data
and never computes numbers. If required data doesn't exist in fdp, the
LLM reports what's missing instead of hallucinating.

Shared by both the REST API and MCP server.

Context configuration lives in ``fdp/config/nlq/nlq_context.yml`` — edit
that file to tweak available plans, years, columns, defaults, etc.
without changing Python code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from fdp import DataPlatform
from fdp.analysis.engine import AnalysisEngine
from fdp.analysis.parameters import AnalysisParameters, Chamber
from fdp.mcp.providers import get_provider

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------

_FDP_ROOT = Path(os.getenv("FDP_ROOT", Path(__file__).resolve().parent.parent.parent))
NLQ_CONFIG_PATH = _FDP_ROOT / "config" / "nlq" / "nlq_context.yml"


def _load_nlq_config() -> dict[str, Any]:
    """Load NLQ context from YAML config file."""
    if NLQ_CONFIG_PATH.exists():
        with open(NLQ_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


# ---------------------------------------------------------------------------
# Data context discovery
# ---------------------------------------------------------------------------

def discover_data_context() -> dict[str, Any]:
    """
    Discover what data is actually available in fdp, merged with YAML config.

    The YAML config (fdp/config/nlq/nlq_context.yml) provides defaults and
    overrides. Runtime discovery from CDM and boundary files overrides
    anything static.
    """
    config = _load_nlq_config()

    context: dict[str, Any] = {
        "chambers": config.get("chambers", ["congress", "senate", "house"]),
        "plans": {},
        "election_years": config.get("election_years", []),
        "offices": config.get("offices", []),
        "election_types": config.get("election_types", []),
        "boundary_columns": config.get("boundary_columns", []),
        "minority_pct_columns": [],
        "partisan_columns": [],
        "cvap_columns": [],
        "cvap_year_default": config.get("defaults", {}).get("cvap_year", 2024),
        "demographics_chambers": ["congress", "senate", "house"],
        "defaults": config.get("defaults", {}),
        "minority_groups": config.get("minority_groups", []),
    }

    # ── Discover plans from fdp app configs ──────────────────────────
    try:
        platform = DataPlatform(app=None, repo=None)
        fdp_root = Path(
            platform.config.raw().get("platform", {}).get("root", "") or Path.cwd()
        )
        apps_dir = fdp_root / "config" / "apps"
        if apps_dir.exists():
            for app_yml in sorted(apps_dir.glob("*.yml")):
                with open(app_yml) as f:
                    app_cfg = yaml.safe_load(f) or {}
                plans = app_cfg.get("plans", {})
                for ch, plan_list in plans.items():
                    if ch not in context["plans"]:
                        context["plans"][ch] = []
                    for p in plan_list or []:
                        context["plans"][ch].append({
                            "id": p.get("id"),
                            "label": p.get("label"),
                            "file": p.get("file"),
                            "app": app_yml.stem,
                        })
    except Exception:
        pass

    # ── Discover elections from CDM contests ─────────────────────────
    try:
        import pandas as pd

        cdm_dir = DataPlatform(app=None, repo=None).resolve("fdga")
        contests_path = cdm_dir / "contests.parquet"
        if contests_path.exists():
            df = pd.read_parquet(contests_path)
            if "cycle_year" in df.columns:
                context["election_years"] = sorted(
                    int(y) for y in df["cycle_year"].dropna().unique()
                )
            if "office" in df.columns:
                context["offices"] = sorted(
                    str(o) for o in df["office"].dropna().unique()
                )
            if "election_type" in df.columns:
                context["election_types"] = sorted(
                    str(t) for t in df["election_type"].dropna().unique()
                )
    except Exception:
        pass

    # ── Discover columns from a sample boundary GeoJSON ──────────────
    try:
        import geopandas as gpd

        fdp_root = Path(
            DataPlatform(app=None, repo=None).config.raw()
            .get("platform", {}).get("root", "") or Path.cwd()
        )
        sb = config.get("sample_boundary", {})
        sample = fdp_root / "data" / "repos" / "main" / "boundaries" / \
            sb.get("chamber", "congress") / sb.get(
                "file", "congress_enacted_24_2024update.geojson"
            )
        if sample.exists():
            gdf = gpd.read_file(sample)
            all_cols = list(gdf.columns)
            context["boundary_columns"] = all_cols
            context["minority_pct_columns"] = [
                c for c in all_cols
                if any(x in c.lower() for x in ["bvap", "hvap", "avap", "wvap", "bp_", "pct_"])
                and "dem" not in c.lower()
            ]
            context["partisan_columns"] = [
                c for c in all_cols
                if any(x in c.lower() for x in ["partisan", "pct_dem", "_dem"])
            ]
    except Exception:
        pass

    return context


def build_system_prompt(context: dict[str, Any]) -> str:
    """
    Build a strict system prompt that constrains the LLM to only use
    data that actually exists in fdp. Token-efficient.
    """
    # Compact plan listing: chamber -> [plan_id, ...]
    plan_ids = {ch: [p["id"] for p in plist] for ch, plist in context["plans"].items()}
    defaults = context.get("defaults", {})
    minority_groups = context.get("minority_groups", [])

    # Build minority groups JSON for the prompt
    groups_json = json.dumps(minority_groups, indent=2)

    return f"""You translate redistricting questions into AnalysisParameters JSON, or
report missing_data if required data is unavailable. Never hallucinate.

STRICT RULE — USE ONLY DATA LISTED BELOW:
─────────────────────────────────────────

CHAMBERS: {context['chambers']}

PLAN IDs (by chamber):
{json.dumps(plan_ids)}

ELECTION YEARS: {context['election_years']}
OFFICES: {context['offices']}
ELECTION TYPES: {context['election_types']}

MINORITY PCT COLUMNS: {context['minority_pct_columns']}
PARTISAN COLUMNS: {context['partisan_columns'][:8]}
CVAP COLUMNS: {context['cvap_columns']} (empty — not yet loaded into GeoJSON)
DEFAULT CVAP YEAR: {context['cvap_year_default']}

DEFAULT MINORITY GROUPS:
{groups_json}

DEFAULT PARAMETERS:
{json.dumps(defaults, indent=2)}

─────────────────────────────────────────

OUTPUT — JSON only, no markdown:

{{
  "type": "analysis" | "missing_data",

  "parameters": {{  // only if type=analysis
    "chamber": "congress",  // one of: congress, senate, house
    "census_year": 2020,
    "geo_level": "vtd",
    "plan_id": "congress_enacted_24",  // MUST be one of the plan IDs listed above
    "cvap_year": 2024,
    "minority_groups": [
      {{"name": "black", "label": "Black VAP", "cvap_col": "pct_bvap_al", "majority_threshold": 0.50}}
    ],
    "majority_threshold": 0.50,
    "competitiveness_thresholds": [0.035, 0.05],
    "competitive_lo": 0.465,
    "competitive_hi": 0.535,
    "election_years": [<from available years>],
    "repo": null
  }},

  "missing": {{  // only if type=missing_data
    "what": "<what data is missing>",
    "why": "<why question cannot be answered>",
    "required": ["<item needed>"]
  }}
}}

RULES:
1. Plan/chamber/year/office/column NOT in lists above → missing_data.
2. 2026+ elections but max year is 2024 → missing_data (not loaded).
3. CVAP columns requested but cvap_columns is empty → missing_data.
4. Otherwise → analysis with parameters using ONLY listed values.
5. "This vs prior" → most recent year vs previous available year.
6. Never invent IDs, years, offices, or columns.

Respond with ONLY the JSON object."""


# ---------------------------------------------------------------------------
# LLM translation call
# ---------------------------------------------------------------------------

def call_llm_translate(system_prompt: str, user_prompt: str) -> str:
    """
    Call the configured AI provider to translate a question into AnalysisParameters.

    Reads AI_PROVIDER, AI_API_KEY, AI_MODEL (or LLAMA_* for llama.cpp) from env.
    Raises RuntimeError if no provider is configured or the call fails.
    """
    provider = get_provider()
    return provider.translate(system_prompt, user_prompt)


# ---------------------------------------------------------------------------
# Main NLQ entry point
# ---------------------------------------------------------------------------

def analyze_question(question: str) -> dict[str, Any]:
    """
    Process a natural-language redistricting question.

    Returns a dict with one of these types:
      - {"type": "missing_data", "missing": {...}, ...}
      - {"type": "analysis_result", "result_type": ..., "parameters_used": ..., "result": ...}
      - {"type": "error", "error": ...}
    """
    # ── Step 1: Discover available data ──────────────────────────────
    context = discover_data_context()

    # ── Step 2: Build prompt and call LLM ────────────────────────────
    system_prompt = build_system_prompt(context)
    context_summary = json.dumps(context, indent=2)

    user_prompt = (
        f"Question: {question}\n\n"
        f"Available data context:\n{context_summary}\n\n"
        "Respond with ONLY the JSON object per the instructions above."
    )

    try:
        llm_response = call_llm_translate(system_prompt, user_prompt)
    except RuntimeError as exc:
        return {
            "type": "error",
            "error": str(exc),
            "hint": "Set AI_PROVIDER and AI_API_KEY (or LLAMA_* for llama.cpp) environment variables.",
        }

    # ── Step 3: Parse LLM response ───────────────────────────────────
    try:
        cleaned = llm_response.strip()
        cleaned = cleaned.removeprefix("```json")
        cleaned = cleaned.removeprefix("```")
        cleaned = cleaned.removesuffix("```")
        cleaned = cleaned.strip()
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "type": "error",
            "error": f"LLM returned invalid JSON: {exc}",
            "raw_response": llm_response[:500],
        }

    # ── Step 4: Handle missing_data ──────────────────────────────────
    if parsed.get("type") == "missing_data":
        missing = parsed.get("missing", {})
        return {
            "type": "missing_data",
            "question": question,
            "missing": missing,
            "available_plans": context["plans"],
            "available_years": context["election_years"],
            "available_columns": context["minority_pct_columns"] + context["partisan_columns"],
        }

    # ── Step 5: Validate type ────────────────────────────────────────
    if parsed.get("type") != "analysis":
        return {
            "type": "error",
            "error": f"LLM returned unknown type: {parsed.get('type')}",
        }

    params_raw = parsed.get("parameters", {})
    defaults = context.get("defaults", {})

    # Validate chamber
    chamber_str = params_raw.get("chamber", "congress")
    if " | " in chamber_str:
        chamber_str = chamber_str.split(" | ")[0].strip()
    chamber_str = chamber_str.strip().strip('"').strip("'")
    try:
        chamber = Chamber(chamber_str)
    except ValueError:
        return {
            "type": "error",
            "error": f"Invalid chamber '{chamber_str}'. Must be one of: congress, senate, house",
        }

    # Validate plan_id exists
    plan_id = params_raw.get("plan_id", "")
    available_plan_ids = []
    for plans in context["plans"].values():
        for p in plans:
            available_plan_ids.append(p["id"])

    if plan_id and plan_id not in available_plan_ids:
        return {
            "type": "missing_data",
            "question": question,
            "missing": {
                "what": f"Plan '{plan_id}'",
                "why": f"Plan '{plan_id}' is not in the available plans list.",
                "required": [f"Use one of: {available_plan_ids[:10]}..."],
            },
            "available_plan_ids": available_plan_ids,
        }

    # Build AnalysisParameters
    try:
        params = AnalysisParameters(
            chamber=chamber,
            census_year=int(params_raw.get("census_year", defaults.get("census_year", 2020))),
            geo_level=params_raw.get("geo_level", defaults.get("geo_level", "vtd")),
            plan_id=plan_id or None,
            plan_file=params_raw.get("plan_file"),
            plan_a_id=params_raw.get("plan_a_id"),
            plan_b_id=params_raw.get("plan_b_id"),
            elections=[],
            election_years=params_raw.get("election_years"),
            election_types=params_raw.get("election_types"),
            offices=params_raw.get("offices"),
            cvap_year=int(params_raw.get("cvap_year", defaults.get("cvap_year", 2024))),
            minority_groups=params_raw.get("minority_groups") or [],
            majority_threshold=float(params_raw.get("majority_threshold", defaults.get("majority_threshold", 0.50))),
            competitiveness_thresholds=params_raw.get("competitiveness_thresholds") or defaults.get("competitiveness_thresholds", [0.035, 0.05]),
            competitive_lo=float(params_raw.get("competitive_lo", defaults.get("competitive_lo", 0.465))),
            competitive_hi=float(params_raw.get("competitive_hi", defaults.get("competitive_hi", 0.535))),
            repo=params_raw.get("repo"),
            halt_on_error=False,
        )
    except Exception as exc:
        return {
            "type": "error",
            "error": f"Failed to build analysis parameters: {exc}",
        }

    # ── Step 6: Run engine ───────────────────────────────────────────
    try:
        engine = AnalysisEngine(params)
        if params.plan_a_id and params.plan_b_id:
            result = engine.compare_plans()
            result_type = "comparison"
        else:
            result = engine.analyze_plan()
            result_type = "single_plan"

        return {
            "type": "analysis_result",
            "question": question,
            "result_type": result_type,
            "parameters_used": params.model_dump(),
            "result": result.model_dump(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "type": "error",
            "error": f"Analysis engine failed: {exc}",
            "parameters_used": params.model_dump(),
        }
