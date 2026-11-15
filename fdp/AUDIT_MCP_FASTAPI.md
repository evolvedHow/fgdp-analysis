# Audit: FDP MCP server & FastAPI layer

## TL;DR — why it does not work

Three independent blockers mean none of the intended entry points actually function:

1. **The data API will not even import.** `fdp.server:app` crashes with `ImportError` because the new `fdp/api/` package shadows the existing `fdp/api.py` module.
2. **Natural-language queries blow up after the LLM responds.** `fdp/analysis/nlq.py` references an undefined variable `defaults` when it builds `AnalysisParameters`.
3. **The MCP servers are protocol stubs.** They expose `/sse` and `/mcp`, but they do not implement the MCP handshake correctly and have no `tools/list` or `tools/call` handlers. They are not wired to the analysis engine or NLQ layer at all.

---

## Critical / blocker findings

### A. Module/package name collision kills `fdp.server:app`

- **File:** `fdp/fdp/server.py:26`
- **Code:** `from fdp.api import router`
- **Problem:** There is now both `fdp/fdp/api.py` (a module containing the data API router) and `fdp/fdp/api/` (a package containing `main.py` and `__init__.py`). Python resolves `fdp.api` as the package, whose `__init__.py` is empty, so `router` is not found.
- **Reproduction:**
  ```bash
  cd fdp
  uv run uvicorn fdp.server:app --host 127.0.0.1 --port 8080
  # ImportError: cannot import name 'router' from 'fdp.api'
  ```
- **Fix:** Move the data API router out of `fdp/api.py` (e.g. into `fdp/api/data.py` or `fdp/api/__init__.py`) and update the import. Delete or rename the colliding `fdp/api.py`.

### B. NLQ `analyze_question` has a runtime NameError

- **File:** `fdp/fdp/analysis/nlq.py:360-377`
- **Code:** uses `defaults.get(...)` but `defaults` is never defined in `analyze_question`.
- **Problem:** Whenever the LLM returns a parseable JSON analysis, building `AnalysisParameters` raises `NameError: name 'defaults' is not defined`.
- **Reproduction:**
  ```python
  from fdp.analysis import nlq
  nlq.get_provider = lambda: FakeProvider('{"type":"analysis","parameters":{"chamber":"congress","plan_id":"congress_enacted_24"}}')
  nlq.analyze_question('What is the minority VAP?')
  # {'type': 'error', 'error': "Failed to build analysis parameters: name 'defaults' is not defined"}
  ```
- **Fix:** Use `context.get("defaults", {})` (already built earlier) or `_load_nlq_config().get("defaults", {})`.

### C. The MCP servers are not MCP servers

- **Files:** `fdp/fdp/mcp/server.py`, `fdp/fdp/mcp/minimal_server.py`, `fdp/fdp/mcp/proper_server.py`, `fdp/fdp/mcp/compat.py`
- **Problems:**
  - `proper_server.py` implements `initialize` but omits the required `protocolVersion` field in the response.
  - No server implements `tools/list` or `tools/call`, so no client can discover or invoke tools.
  - The `/sse` endpoint sends a single `event: endpoint` line and immediately closes. Real MCP clients expect the SSE stream to stay open for server-to-client JSON-RPC messages.
  - `server.py` and `minimal_server.py` return non-JSON-RPC payloads from `/mcp`.
  - `compat.py` references `request.app.state.server._lowlevel_server._generate_session_id()`, which does not exist on these apps, and uses `StreamingResponse` without importing it.
- **Reproduction:**
  ```bash
  uv run uvicorn fdp.mcp.proper_server:app --host 127.0.0.1 --port 8001
  # POST {"jsonrpc":"2.0","id":1,"method":"tools/list"} -> 200 {"result":{"message":"Method processed successfully"}}
  ```
- **Fix:** Either add the official `mcp` Python SDK (`FastMCP`) or write a compliant JSON-RPC handler with session IDs, proper `initialize`, `tools/list`, and `tools/call`. Wire the tool handlers to `AnalysisEngine` and `analyze_question`.

---

## High-severity findings

### D. Analysis API and data API are separate, unrelated apps

- `fdp.api.main:app` runs on port 8000 and exposes `/api/v1/analysis/*`.
- `fdp.server:app` was meant to expose `/api/v1/*` data endpoints.
- `fdp.mcp.*` run on port 8001.
- **Impact:** There is no single deployable FDP API; clients must know three different processes.

### E. Blocking sync code inside async routes

- `fdp/api/main.py` endpoints are `async` but call:
  - `AnalysisEngine(...)` which does GeoJSON/parquet/duckdb work synchronously.
  - `nlq_analyze_question(...)` which can block for up to 120 s waiting on llama.cpp.
- **Impact:** Under any real load the event loop is blocked; concurrent requests stall.
- **Fix:** Use `fastapi.concurrency.run_in_threadpool` for sync work, or make the routes synchronous.

### F. CORS misconfiguration

- `fdp/api/main.py:60-66`, `fdp/mcp/*.py`: `allow_origins=["*"]` combined with `allow_credentials=True`. Browsers reject wildcard credentials, and it is a security anti-pattern.
- **Fix:** Set `allow_credentials=False` for wildcard origins, or explicitly list origins and then allow credentials.

### G. `/query` SQL passthrough is weakly guarded

- **File:** `fdp/fdp/api.py:654-660`
- **Problem:** Only the first token is checked (`SELECT`, `WITH`, `EXPLAIN`). Comments, semicolons, or multi-statement strings may bypass the guard.
- **Fix:** Use a strict allow-list parser (e.g. `sqlparse` + statement count check) or run under a read-only DB role.

### H. No tests for the new layers

- `fdp/tests/test_cdm.py` passes (76 tests) but covers none of the API/MCP/NLQ code.
- There are no smoke tests for the FastAPI apps or MCP JSON-RPC flow.

---

## Medium / low findings

- **Lint:** `ruff` reports 43 issues across the new files (unused imports, blind `except: pass`, undefined names, import ordering, nested `with` statements).
- **`fdp/api/main.py` self-hosts:** it calls `uvicorn.run(app, ...)` in `main()`, which is fine for local dev but duplicates the app when imported by uvicorn.
- **`compat.py` is dead code:** it cannot work with the current apps and is not imported anywhere.
- **No `mcp` dependency:** `fdp/pyproject.toml` does not include `mcp` or any JSON-RPC library.
- **Dockerfile deploys the broken data API:** `fdp/Dockerfile` uses `uvicorn fdp.server:app`, which currently fails to import.

---

> **Post-audit status:** All critical blockers and the full rebuild have been applied. `fdp.server:app` now starts, the analysis API is mounted under the same app, and the MCP server uses the official `mcp` SDK with working tools.

## Applied fixes

1. **Resolved `fdp.api` collision** — moved the data API router from `fdp/api.py` to `fdp/api/data.py` and updated `fdp/server.py`.
2. **Fixed NLQ `defaults` NameError** — `fdp/analysis/nlq.py` now uses `context.get("defaults", {})`.
3. **Unified FastAPI app** — `fdp.server:app` now includes:
   - Data API at `/api/v1/*`
   - Analysis API at `/api/v1/analysis/*`
   - OpenAPI docs at `/docs`
   - MCP SSE at `/mcp/sse` and messages at `/mcp/messages/`
4. **Real MCP implementation** — replaced the stubs in `fdp/mcp/server.py` with the official `mcp` SDK (`Server` + `SseServerTransport`). Exposed tools:
   - `analyze_plan`
   - `compare_plans`
   - `benchmark_plan`
   - `ask_question`
   - `list_catalog`
5. **Removed dead MCP files** — `minimal_server.py`, `proper_server.py`, and `compat.py` deleted.
6. **Offloaded blocking work** — analysis API endpoints changed from `async def` to sync `def` so FastAPI runs them in a threadpool; MCP tool handlers use `anyio.to_thread.run_sync`.
7. **Added smoke tests** — `fdp/tests/test_api_mcp.py` covers health, catalog, docs, route mounting, and the NLQ defaults fix.

## Verification

```bash
cd fdp
uv run pytest tests/ -q          # 82 passed
uv run uvicorn fdp.server:app    # imports and starts
```

Manual MCP handshake confirmed:
- `initialize` returns `protocolVersion: 2024-11-05`
- `tools/list` returns the five tools above
- `tools/call` for `list_catalog` returns a non-error result

## Remaining known issues

- **CORS:** still wildcard origins by default. Set `FDPAPI_ORIGINS` in production.
- **SQL passthrough:** still only checks the first token. Use a read-only DB role for defense in depth.
- **Lint:** a handful of intentional broad `except Exception` blocks remain in the API/NLQ layers (ruff `BLE001`).
