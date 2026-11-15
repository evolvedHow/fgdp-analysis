"""
FDP API server — FastAPI app factory.

The unified server exposes:
  - REST data endpoints under /api/v1 (reads parquet/GeoJSON files)
  - Analysis endpoints under /api/v1/analysis
  - MCP transports under /mcp (SSE + Streamable HTTP)

Start locally:
    uv run --extra api uvicorn fdp.server:app --host 127.0.0.1 --port 8001

Or via the systemd user service:
    systemctl --user start fdp-mcp

Environment variables
---------------------
FDPAPI_SECRET   Secret token for POST /api/v1/query (optional; set to enable)
FDPAPI_ORIGINS  Comma-separated list of allowed CORS origins
                (default: * — open for public non-profit data)
FDP_ROOT        FDP data root directory (for catalog/scan operations)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fdp.api.data import router as data_router
from fdp.api.main import router as analysis_router
from fdp.mcp.server import add_mcp_routes, streamable_http_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the MCP StreamableHTTP lifespan inside the unified app."""
    async with streamable_http_app.router.lifespan_context(streamable_http_app):
        yield


def create_app() -> FastAPI:
    """Create and configure the unified FDP FastAPI application."""
    app = FastAPI(
        title="Fair Districts Data Platform API",
        description=(
            "REST API for Georgia redistricting data — election results, "
            "CVAP demographics, geography at the VTD level, plan analysis, "
            "and MCP tool access."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        redirect_slashes=False,
    )

    app.include_router(data_router, prefix="/api/v1")
    app.include_router(analysis_router)

    # Register MCP routes and StreamableHTTP middleware *before* CORS so
    # CORS wraps the entire app (including the MCP transports).
    add_mcp_routes(app, prefix="/mcp")

    # CORS — permissive by default (public non-profit data).
    # Override FDPAPI_ORIGINS to restrict to specific domains in production.
    raw_origins = os.environ.get("FDPAPI_ORIGINS", "*")
    if raw_origins == "*":
        allow_origins = ["*"]
        allow_credentials = False
    else:
        allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        allow_credentials = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    return app


# Module-level app instance — used by uvicorn/gunicorn:
#   uvicorn fdp.server:app
app = create_app()
