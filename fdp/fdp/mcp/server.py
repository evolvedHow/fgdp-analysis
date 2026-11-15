"""
FDP MCP server.

Implements the Model Context Protocol on top of the existing analysis engine
and NLQ layer.  Tools are exposed via Server-Sent Events (SSE) transport at:

    GET  /mcp/sse
    POST /mcp/messages?session_id=<uuid>

The MCP router can be mounted into any FastAPI app with
``add_mcp_routes(app, prefix="/mcp")``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import anyio
import mcp_types as types
import yaml
from fastapi import FastAPI, Request, Response
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from pydantic import BaseModel, Field
from starlette.types import ASGIApp, Receive, Scope, Send

from fdp import DataPlatform
from fdp.analysis.engine import AnalysisEngine
from fdp.analysis.nlq import analyze_question as nlq_analyze_question
from fdp.analysis.parameters import (
    AnalysisParameters,
    Chamber,
)

# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------

async def _list_tools(_ctx, _params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def _call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    name = params.name
    arguments = dict(params.arguments or {})
    try:
        payload = await anyio.to_thread.run_sync(_run_sync_tool, name, arguments)
        text = json.dumps(payload, indent=2, default=str)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            is_error=False,
        )
    except Exception as exc:  # noqa: BLE001
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps({"error": str(exc)}))],
            is_error=True,
        )


# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp_server = Server(
    "fdp-analysis",
    version="1.0.0",
    title="FDP Redistricting Analysis",
    description=(
        "MCP server for the Fair Districts Data Platform. "
        "Provides plan analysis, comparison, benchmark scoring, and natural-language queries."
    ),
    on_list_tools=_list_tools,
    on_call_tool=_call_tool,
)

# Streamable HTTP transport for clients that do not support SSE (ChatGPT,
# Gemini, Claude, LibreChat, llama.cpp UI, etc. may each pick a different
# transport). Stateless mode avoids requiring clients to manage a session ID.
streamable_http_app = mcp_server.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
)


# ---------------------------------------------------------------------------
# Tool input schemas (Pydantic -> JSON Schema)
# ---------------------------------------------------------------------------

ChamberName = Literal["congress", "senate", "house"]
GeoLevelName = Literal["vtd", "precinct", "county", "block"]


class AnalyzePlanInput(BaseModel):
    plan_id: str = Field(..., description="Logical plan ID (e.g. congress_enacted_24)")
    chamber: ChamberName = Field("congress", description="Georgia legislative chamber: congress, senate, or house")
    census_year: int = Field(2020, description="Census vintage year")
    geo_level: GeoLevelName = Field("vtd", description="Geographic level: vtd, precinct, county, or block")
    cvap_year: int = Field(2024, description="CVAP ACS vintage year")
    election_years: list[int] | None = Field(None, description="Filter elections to these years, e.g. [2018, 2020, 2022, 2024]")
    election_types: list[str] | None = Field(None, description="Filter elections to these types, e.g. ['general', 'primary']")
    offices: list[str] | None = Field(None, description="Filter elections to these offices, e.g. ['Senate', 'House']")
    majority_threshold: float = Field(0.50, ge=0.0, le=1.0)
    competitive_lo: float = Field(0.465, ge=0.0, le=1.0)
    competitive_hi: float = Field(0.535, ge=0.0, le=1.0)
    repo: str | None = Field(None, description="Optional fdp repo/workspace name")


class ComparePlansInput(BaseModel):
    plan_a_id: str = Field(..., description="First plan ID")
    plan_b_id: str = Field(..., description="Second plan ID")
    chamber: ChamberName = Field("congress", description="Georgia legislative chamber: congress, senate, or house")
    census_year: int = Field(2020, description="Census vintage year")
    geo_level: GeoLevelName = Field("vtd", description="Geographic level: vtd, precinct, county, or block")
    cvap_year: int = Field(2024, description="CVAP ACS vintage year")
    election_years: list[int] | None = Field(None, description="Filter elections to these years, e.g. [2018, 2020, 2022, 2024]")
    election_types: list[str] | None = Field(None, description="Filter elections to these types, e.g. ['general', 'primary']")
    offices: list[str] | None = Field(None, description="Filter elections to these offices, e.g. ['Senate', 'House']")
    majority_threshold: float = Field(0.50)
    competitive_lo: float = Field(0.465)
    competitive_hi: float = Field(0.535)
    repo: str | None = Field(None)


class BenchmarkPlanInput(BaseModel):
    plan_id: str = Field(..., description="Plan ID to evaluate")
    benchmark_id: str = Field(..., description="Benchmark config ID")
    chamber: ChamberName = Field("congress", description="Georgia legislative chamber: congress, senate, or house")
    census_year: int = Field(2020)
    geo_level: GeoLevelName = Field("vtd")
    cvap_year: int = Field(2024)
    majority_threshold: float = Field(0.50)
    competitive_lo: float = Field(0.465)
    competitive_hi: float = Field(0.535)
    repo: str | None = Field(None)


class AskQuestionInput(BaseModel):
    question: str = Field(..., description="Natural-language redistricting question")


class ListCatalogInput(BaseModel):
    chamber: ChamberName | None = Field(None, description="Optional chamber filter: congress, senate, or house")


# ---------------------------------------------------------------------------
# Tool catalog
# ---------------------------------------------------------------------------

TOOLS: list[types.Tool] = [
    types.Tool(
        name="analyze_plan",
        title="Analyze a redistricting plan",
        description="Run a full demographic/partisan analysis of a single plan.",
        input_schema=AnalyzePlanInput.model_json_schema(),
    ),
    types.Tool(
        name="compare_plans",
        title="Compare two redistricting plans",
        description="Compare two plans district-by-district.",
        input_schema=ComparePlansInput.model_json_schema(),
    ),
    types.Tool(
        name="benchmark_plan",
        title="Benchmark a plan",
        description="Compare a plan against a simulated benchmark distribution.",
        input_schema=BenchmarkPlanInput.model_json_schema(),
    ),
    types.Tool(
        name="ask_question",
        title="Ask a redistricting question",
        description="Ask a natural-language question; it will be translated into analysis parameters and executed.",
        input_schema=AskQuestionInput.model_json_schema(),
    ),
    types.Tool(
        name="list_catalog",
        title="List available plans",
        description="List the redistricting plans available for analysis.",
        input_schema=ListCatalogInput.model_json_schema(),
    ),
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _params_from_analyze(args: dict[str, Any]) -> AnalysisParameters:
    return AnalysisParameters(
        chamber=Chamber(args.get("chamber", "congress")),
        census_year=args.get("census_year", 2020),
        geo_level=args.get("geo_level", "vtd"),
        plan_id=args["plan_id"],
        plan_file=None,
        plan_a_id=None,
        plan_b_id=None,
        elections=[],
        election_years=args.get("election_years"),
        election_types=args.get("election_types"),
        offices=args.get("offices"),
        cvap_year=args.get("cvap_year", 2024),
        minority_groups=[],
        majority_threshold=args.get("majority_threshold", 0.50),
        competitiveness_thresholds=[0.035, 0.05],
        competitive_lo=args.get("competitive_lo", 0.465),
        competitive_hi=args.get("competitive_hi", 0.535),
        repo=args.get("repo"),
        halt_on_error=False,
    )


def _params_from_compare(args: dict[str, Any]) -> AnalysisParameters:
    plan_a = args["plan_a_id"]
    plan_b = args["plan_b_id"]
    return AnalysisParameters(
        chamber=Chamber(args.get("chamber", "congress")),
        census_year=args.get("census_year", 2020),
        geo_level=args.get("geo_level", "vtd"),
        plan_id=plan_a,
        plan_file=None,
        plan_a_id=plan_a,
        plan_b_id=plan_b,
        elections=[],
        election_years=args.get("election_years"),
        election_types=args.get("election_types"),
        offices=args.get("offices"),
        cvap_year=args.get("cvap_year", 2024),
        minority_groups=[],
        majority_threshold=args.get("majority_threshold", 0.50),
        competitiveness_thresholds=[0.035, 0.05],
        competitive_lo=args.get("competitive_lo", 0.465),
        competitive_hi=args.get("competitive_hi", 0.535),
        repo=args.get("repo"),
        halt_on_error=False,
    )


def _params_from_benchmark(args: dict[str, Any]) -> AnalysisParameters:
    return AnalysisParameters(
        chamber=Chamber(args.get("chamber", "congress")),
        census_year=args.get("census_year", 2020),
        geo_level=args.get("geo_level", "vtd"),
        plan_id=args["plan_id"],
        plan_file=None,
        plan_a_id=None,
        plan_b_id=None,
        elections=[],
        cvap_year=args.get("cvap_year", 2024),
        minority_groups=[],
        majority_threshold=args.get("majority_threshold", 0.50),
        competitiveness_thresholds=[0.035, 0.05],
        competitive_lo=args.get("competitive_lo", 0.465),
        competitive_hi=args.get("competitive_hi", 0.535),
        benchmark_id=args["benchmark_id"],
        composite_method="min",
        repo=args.get("repo"),
        halt_on_error=False,
    )


def _build_catalog(chamber: str | None) -> dict[str, Any]:
    """Synchronous catalog builder for the MCP tool."""
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
                if chamber and ch != chamber:
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


def _run_sync_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool synchronously (runs in a worker thread)."""
    if name == "analyze_plan":
        params = _params_from_analyze(arguments)
        result = AnalysisEngine(params).analyze_plan()
        return {"result": result.model_dump()}

    if name == "compare_plans":
        params = _params_from_compare(arguments)
        result = AnalysisEngine(params).compare_plans()
        return {"result": result.model_dump()}

    if name == "benchmark_plan":
        params = _params_from_benchmark(arguments)
        result = AnalysisEngine(params).compare_to_benchmark()
        return {"result": result.model_dump()}

    if name == "ask_question":
        return nlq_analyze_question(arguments["question"])

    if name == "list_catalog":
        return _build_catalog(arguments.get("chamber"))

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# FastAPI integration
# ---------------------------------------------------------------------------

def add_mcp_routes(app: FastAPI, prefix: str = "/mcp") -> None:
    """Mount the MCP SSE transport on ``app`` at ``prefix``."""
    # The trailing slash on the message endpoint avoids Starlette Mount's
    # 307 redirect when the ASGI sub-app is mounted.
    message_path = f"{prefix}/messages/"
    sse = SseServerTransport(message_path)

    @app.get(f"{prefix}/sse")
    async def mcp_sse(request: Request) -> Response:
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )
        return Response()

    # The message endpoint is a raw ASGI app and must be mounted directly;
    # wrapping it in a FastAPI path operation would send a second response.
    app.mount(message_path, sse.handle_post_message)

    # Streamable HTTP transport — supports clients that POST to the MCP root
    # URL instead of using SSE. Added as middleware so both /mcp and /mcp/
    # work without relying on trailing-slash redirects.
    app.add_middleware(StreamableHTTPMiddleware, prefix=prefix)


class StreamableHTTPMiddleware:
    """ASGI middleware that dispatches MCP StreamableHTTP requests."""

    def __init__(self, app: ASGIApp, prefix: str = "/mcp") -> None:
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") in (
            self.prefix,
            f"{self.prefix}/",
        ):
            # Present the request to the SDK app as if it were mounted at
            # <prefix>/ with a root path of <prefix>/.
            child_scope = {
                **scope,
                "root_path": scope.get("root_path", "") + self.prefix + "/",
                "path": "/",
            }
            await streamable_http_app(child_scope, receive, send)
            return
        await self.app(scope, receive, send)

