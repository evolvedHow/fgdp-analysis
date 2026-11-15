"""
Modal deployment for the FDP unified API + MCP server.

Usage
-----
Deploy or update:
    cd ~/codebox/fgdp/fdp
    uv run --extra modal modal deploy modal_app.py

The data directory (~2.7 GB) is stored on a Modal Volume mounted at /fdp-data.
To upload/sync local data to the volume:
    uv run --extra modal modal volume put fdp-data data /fdp-data --force

Environment secrets (set in Modal dashboard or via CLI):
    FDPAPI_SECRET     Token protecting POST /api/v1/query
    FDPAPI_ORIGINS    Optional comma-separated CORS origins
"""

from __future__ import annotations

import os
from pathlib import Path

import modal

# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("uv")
    # Add package metadata, lock file, and application source.
    .add_local_file("pyproject.toml", "/app/pyproject.toml")
    .add_local_file("uv.lock", "/app/uv.lock")
    .add_local_file("README.md", "/app/README.md")
    .add_local_dir("fdp", "/app/fdp")
    # Install the package and its [api] extras inside the image.
    .run_commands(
        "cd /app && uv pip install --system --no-cache '.[api]'",
    )
)

# ---------------------------------------------------------------------------
# Volume for the ~2.7 GB data directory.
# ---------------------------------------------------------------------------

volume = modal.Volume.from_name("fdp-data", create_if_missing=True)

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

secrets = [
    modal.Secret.from_name("fdp-api"),
]

# ---------------------------------------------------------------------------
# Modal app
# ---------------------------------------------------------------------------

app = modal.App("fdp-api", image=image, secrets=secrets)


@app.function(volumes={"/fdp-data": volume})
@modal.asgi_app()
def fastapi_app():
    """Return the unified FDP FastAPI application.

    The ASGI app is imported inside the function so package paths and the
    data volume are resolved at container runtime.
    """
    os.environ.setdefault("FDP_ROOT", "/fdp-data")

    from fdp.server import app as fdp_fastapi_app

    return fdp_fastapi_app


# ---------------------------------------------------------------------------
# Optional: one-shot helper to seed the volume from local data.
# ---------------------------------------------------------------------------

@app.function(volumes={"/fdp-data": volume})
def sync_data(local_root: str = "/fdp-data") -> dict[str, str]:
    """Verify the volume mount and report the data root contents."""
    root = Path(local_root)
    return {
        "root": str(root),
        "exists": str(root.exists()),
        "top_level": ", ".join(
            p.name for p in sorted(root.iterdir()) if root.exists()
        )[:200],
    }
