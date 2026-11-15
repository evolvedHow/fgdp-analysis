"""Generate the FDP API Colab notebook JSON."""

import json

NOTEBOOK = {
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python"
        },
        "colab": {
            "provenance": [],
            "toc_visible": True
        }
    },
    "nbformat": 4,
    "nbformat_minor": 0,
    "cells": []
}


def md(source):
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def code(source):
    return {"cell_type": "code", "metadata": {}, "source": source, "outputs": [], "execution_count": None}


cells = [
    md("""# FDP API + MCP Exploration Notebook

This notebook exercises every public entry point of the Fair Districts Data Platform (FDP) API and MCP server, then visualises the results with matplotlib and D3.js.

## ⚠️ Important: where is the FDP server?

The default `FDP_BASE_URL` is `http://127.0.0.1:8001`, which only works if this notebook runs **on the same machine as the FDP server** (e.g. your WSL homelab).

- **Running locally in WSL/Jupyter?** Leave `FDP_BASE_URL = "http://127.0.0.1:8001"`.
- **Running in Google Colab?** You must change `FDP_BASE_URL` to a public URL such as:
  - A Cloudflare Tunnel URL (`https://fdp.yourdomain.com`) — see `DEPLOYMENT.md` section 2
  - A Modal + Cloudflare Worker URL — see `DEPLOYMENT.md` sections 4–5

If you see `ConnectionRefusedError`, the notebook cannot reach the FDP server at the URL you configured.

## Fill-in parameters

All user-editable variables live in the **CONFIG** cell below. Change them, then run the cells in order.
"""),
    code("""# -------------------------------------------------
# CONFIG — edit these values, then run all cells
# -------------------------------------------------

# Base URL of the FDP unified API / MCP server.
#
# LOCAL WSL/JUPYTER (notebook and server on same machine):
#   FDP_BASE_URL = "http://127.0.0.1:8001"
#
# GOOGLE COLAB (notebook runs remotely; FDP must be publicly reachable):
#   FDP_BASE_URL = "https://fdp.yourdomain.com"
#
# If you get ConnectionRefusedError, this URL is wrong for where you are running.
FDP_BASE_URL = "http://127.0.0.1:8001"

# Optional secret for authenticated endpoints (POST /api/v1/query).
# Leave empty if you only want to use the MCP tools.
FDPAPI_SECRET = ""

# Which chamber to analyse: "congress", "senate", or "house".
CHAMBER = "house"

# Plan IDs. Pick IDs returned by the "List catalog" cell.
PLAN_ID = "house_enacted_24"
PLAN_A_ID = "house_enacted_24"
PLAN_B_ID = "house_enacted_2123"

# Benchmark config ID (used by benchmark_plan).
BENCHMARK_ID = "ga_house_2026_v1"

# Natural-language question for ask_question.
NLQ_QUESTION = "Which districts in the 2024 enacted house map are competitive?"

# Raw SQL query for /api/v1/query (requires FDPAPI_SECRET).
SQL_QUERY = "SELECT * FROM fdp.election_results LIMIT 5"

# Geo level for analyses.
GEO_LEVEL = "vtd"

print("Config loaded.")
print(f"  FDP URL: {FDP_BASE_URL}")
print(f"  Chamber: {CHAMBER}")
print(f"  Plan:    {PLAN_ID}")
"""),
    md("""## Setup

Install only `requests` (standard on Colab; included for local notebooks).
"""),
    code("""import json
import requests
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import HTML, Javascript, display

# Helper for pretty-printing JSON responses
def pp(data):
    print(json.dumps(data, indent=2, default=str))

# MCP request helper
def mcp_call(method, params=None, req_id=1):
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    url = f"{FDP_BASE_URL}/mcp"
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()

print("Helpers defined.")
"""),
    md("""## 1. Health check

Quick liveness check against the unified API.
"""),
    code("""health_url = f"{FDP_BASE_URL}/api/v1/health"
resp = requests.get(health_url)
print(f"Status: {resp.status_code}")
pp(resp.json())
"""),
    md("""## 2. List catalog

Discover available plans for the selected chamber.
"""),
    code("""catalog = mcp_call("tools/call", {
    "name": "list_catalog",
    "arguments": {"chamber": CHAMBER}
}, req_id=2)
pp(catalog)

# Store plans in a DataFrame for later visualization
catalog_text = json.loads(catalog["result"]["content"][0]["text"])
plans_df = pd.DataFrame(catalog_text["plans"].get(CHAMBER, []))
print("\\nPlans DataFrame:")
display(plans_df)
"""),
    md("""## 3. Analyze a single plan

Run a full demographic/partisan analysis.
"""),
    code("""analyze = mcp_call("tools/call", {
    "name": "analyze_plan",
    "arguments": {
        "plan_id": PLAN_ID,
        "chamber": CHAMBER,
        "geo_level": GEO_LEVEL
    }
}, req_id=3)

analyze_result = json.loads(analyze["result"]["content"][0]["text"])["result"]
summary = analyze_result["summary"]
districts = analyze_result["districts"]

print("Summary:")
pp(summary)
"""),
    md("""## 4. Compare two plans

Side-by-side district comparison.
"""),
    code("""compare = mcp_call("tools/call", {
    "name": "compare_plans",
    "arguments": {
        "plan_a_id": PLAN_A_ID,
        "plan_b_id": PLAN_B_ID,
        "chamber": CHAMBER,
        "geo_level": GEO_LEVEL
    }
}, req_id=4)

compare_result = json.loads(compare["result"]["content"][0]["text"])["result"]
print("Comparison keys:", list(compare_result.keys()))
pp(compare_result.get("summary", compare_result)[:200] if isinstance(compare_result, str) else compare_result.get("summary", compare_result))
"""),
    md("""## 5. Benchmark a plan

Compare a plan against an ensemble benchmark.
"""),
    code("""benchmark = mcp_call("tools/call", {
    "name": "benchmark_plan",
    "arguments": {
        "plan_id": PLAN_ID,
        "benchmark_id": BENCHMARK_ID,
        "chamber": CHAMBER,
        "geo_level": GEO_LEVEL
    }
}, req_id=5)

benchmark_result = json.loads(benchmark["result"]["content"][0]["text"])["result"]
print("Benchmark keys:", list(benchmark_result.keys()))
pp(benchmark_result.get("summary", benchmark_result))
"""),
    md("""## 6. Natural-language question

Let the NLQ layer translate a question into analysis parameters.
"""),
    code("""nlq = mcp_call("tools/call", {
    "name": "ask_question",
    "arguments": {"question": NLQ_QUESTION}
}, req_id=6)

nlq_result = json.loads(nlq["result"]["content"][0]["text"])
print("NLQ result type:", nlq_result.get("type"))
pp(nlq_result)
"""),
    md("""## 7. Raw SQL query

Requires `FDPAPI_SECRET`. Skip this cell if the secret is empty.
"""),
    code("""if not FDPAPI_SECRET:
    print("FDPAPI_SECRET is empty — skipping raw SQL query.")
else:
    query_url = f"{FDP_BASE_URL}/api/v1/query"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FDPAPI_SECRET}"
    }
    resp = requests.post(query_url, json={"sql": SQL_QUERY}, headers=headers)
    resp.raise_for_status()
    query_result = resp.json()
    pp(query_result)
"""),
    md("""## 8. Visualise with matplotlib

Partisan lean and competitiveness of the analysed plan.
"""),
    code("""fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Party breakdown
party_labels = ["Democratic", "Republican"]
party_values = [summary["dem_districts"], summary["rep_districts"]]
axes[0].bar(party_labels, party_values, color=["#1f77b4", "#d62728"])
axes[0].set_title(f"Party Districts — {PLAN_ID}")
axes[0].set_ylabel("Number of districts")

# Minority majority districts
minority = summary.get("minority_districts", {})
minority_labels = list(minority.keys())
majority_counts = [minority[g]["majority"] for g in minority_labels]
axes[1].bar(minority_labels, majority_counts, color="green")
axes[1].set_title(f"Majority-Minority Districts — {PLAN_ID}")
axes[1].set_ylabel("Number of districts")
axes[1].tick_params(axis="x", rotation=45)

plt.tight_layout()
plt.show()
"""),
    md("""## 9. Visualise with D3.js

Interactive bar chart rendered in the notebook output.
"""),
    code("""d3_data = [
    {"label": "Dem", "value": summary["dem_districts"]},
    {"label": "Rep", "value": summary["rep_districts"]},
    {"label": "Competitive", "value": summary["competitive_districts"]["band_46.5_53.5"]},
]

html_template = r'''
<div id="d3-chart"></div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
  const data = __DATA__;
  const margin = {top: 20, right: 20, bottom: 30, left: 40};
  const width = 500 - margin.left - margin.right;
  const height = 300 - margin.top - margin.bottom;

  const svg = d3.select("#d3-chart")
    .append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand()
    .range([0, width])
    .domain(data.map(d => d.label))
    .padding(0.2);

  svg.append("g")
    .attr("transform", `translate(0,${height})`)
    .call(d3.axisBottom(x));

  const y = d3.scaleLinear()
    .domain([0, d3.max(data, d => d.value) * 1.1])
    .range([height, 0]);

  svg.append("g")
    .call(d3.axisLeft(y));

  svg.selectAll("rect")
    .data(data)
    .join("rect")
    .attr("x", d => x(d.label))
    .attr("y", d => y(d.value))
    .attr("width", x.bandwidth())
    .attr("height", d => height - y(d.value))
    .attr("fill", d => d.label === "Dem" ? "#1f77b4" : d.label === "Rep" ? "#d62728" : "#9467bd");
</script>
'''
html = html_template.replace("__DATA__", json.dumps(d3_data))
display(HTML(html))
"""),
    md("""## 10. Export CSV for rawgraphs.io

Generate a CSV you can paste/upload into [rawgraphs.io](https://rawgraphs.io).
"""),
    code("""# Build a district-level CSV from the analyse_plan result
district_rows = []
for did, dinfo in districts.items():
    row = {"district": did}
    row.update(dinfo)
    district_rows.append(row)

districts_df = pd.DataFrame(district_rows)
csv_path = "/tmp/fdp_districts.csv"
districts_df.to_csv(csv_path, index=False)
print(f"CSV saved to {csv_path}")
print(f"Rows: {len(districts_df)}, Columns: {list(districts_df.columns)}")
display(districts_df.head())

# In Colab, offer a download link
from google.colab import files
files.download(csv_path)
""")
]

NOTEBOOK["cells"] = cells

with open("/home/vgana/codebox/fgdp/fdp/notebooks/fdp_api_colab.ipynb", "w") as f:
    json.dump(NOTEBOOK, f, indent=2)

print("Notebook created at /home/vgana/codebox/fgdp/fdp/notebooks/fdp_api_colab.ipynb")
print(f"Total cells: {len(cells)}")
