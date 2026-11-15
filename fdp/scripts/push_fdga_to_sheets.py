#!/usr/bin/env python3
"""
push_fdga_to_sheets.py — Publish the FDGA canonical data model to Google Sheets.

Writes the CDM into the *data layer* spreadsheet as static values. Nothing this
script writes contains a formula: the data layer is a published artifact, not a
workbook. That is the property that keeps it from drifting the way the legacy
Excel file did — there is nothing in it a person can accidentally edit into a
hardcoded constant.

Layer model
-----------
    THIS SPREADSHEET (data layer)          <- written here, share as view-only
      facts            county x contest x candidate, no formulas
      contests         one row per race
      chamber_year     one row per cycle x chamber
      statewide        statewide race vote shares
      _manifest        provenance: source, checksum, row counts
      _corrections     documented source fixes and their evidence
      _name_merges     candidate spelling variants that were merged
      _validation      contract-test results

    UI SPREADSHEETS (separate files)       <- built by whoever wants a chart
      =IMPORTRANGE("<this sheet url>", "chamber_year!A:X")
      =IMPORTRANGE("<this sheet url>", "contests!A:V")

Pull the small aggregate tabs into UI sheets, never ``facts``: IMPORTRANGE is
reliable to roughly 50-100k cells per call and ``facts`` is ~390k. Power BI
(native Google Sheets connector) and Tableau (via the Google Drive connector —
its dedicated Sheets connector was retired in mid-2023) read this spreadsheet
directly through the API and are not subject to that limit.

Setup (once)
------------
1. Create a Google Cloud project and enable the Google Sheets API.
2. Create a service account and download its JSON key.
3. Share the target spreadsheet with the service account's email as Editor.
4. Point FDGA_SHEETS_CREDENTIALS at the key file and FDGA_SHEETS_ID at the
   spreadsheet id — the token between '/d/' and '/edit' in its URL.

The Google client libraries live in the project's optional 'sheets' extra;
passing --extra sheets installs them on first run, so there is no separate
install step.

Usage (from fgdp/ root):
    export FDGA_SHEETS_CREDENTIALS=~/.config/fdp/fdga-sheets.json
    export FDGA_SHEETS_ID=1AbC...xyz
    uv run --project fdp --extra sheets python fdp/scripts/push_fdga_to_sheets.py
    uv run --project fdp --extra sheets python fdp/scripts/push_fdga_to_sheets.py --skip facts

    # --dry-run reports what would be sent; it needs neither the extra nor
    # credentials, so it is the quickest way to sanity-check the outputs.
    uv run --project fdp python fdp/scripts/push_fdga_to_sheets.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
_FDGA_DIR = _SCRIPT_DIR.parent / "data" / "repos" / "main" / "fdga"

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

#: Tab name -> source CSV stem. Order controls tab order in the spreadsheet.
TABS: dict[str, str] = {
    "facts": "facts",
    "contests": "contests",
    "chamber_year": "chamber_year",
    "statewide": "statewide",
    "_manifest": "manifest",
    "_corrections": "corrections",
    "_name_merges": "name_merges",
    "_validation": "validation",
    "_reconciliation": "reconciliation",
}

#: Rows per API request. The Sheets API caps a single request at 10 MB; ~20k
#: rows of this width sits comfortably inside that.
_CHUNK_ROWS = 20_000


def _load_client(credentials_path: Path):
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise SystemExit(
            "Google API libraries are not installed. Re-run with the extra:\n"
            "  uv run --project fdp --extra sheets python "
            "fdp/scripts/push_fdga_to_sheets.py"
        )
    creds = Credentials.from_service_account_file(
        str(credentials_path), scopes=_SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _to_values(df: pd.DataFrame) -> list[list]:
    """Header row plus data, with every cell a JSON-safe scalar.

    NaN/NaT become empty strings rather than the string 'nan', and numpy
    scalars are unwrapped so the API's JSON encoder accepts them.
    """
    out: list[list] = [list(df.columns)]
    for record in df.itertuples(index=False, name=None):
        row = []
        for value in record:
            if value is None or (isinstance(value, float) and math.isnan(value)):
                row.append("")
            elif isinstance(value, (bool,)):
                row.append(value)
            elif hasattr(value, "item"):          # numpy scalar
                row.append(value.item())
            elif pd.isna(value):
                row.append("")
            else:
                row.append(value)
        out.append(row)
    return out


def _service_account_email(credentials_path: Path) -> str:
    """Read the service account's address out of its key file."""
    try:
        return json.loads(credentials_path.read_text()).get("client_email", "?")
    except Exception:
        return "?"


def _explain_api_error(exc, sheet_id: str, credentials: Path) -> str:
    """Turn a Google API error into something a person can act on.

    The two failures everyone hits during setup are 'the sheet was never shared
    with the service account' and 'the Sheets API is not enabled', and both
    arrive as an opaque 403.
    """
    status = getattr(getattr(exc, "resp", None), "status", None)
    body = ""
    try:
        body = exc.content.decode() if isinstance(exc.content, bytes) else str(exc.content)
    except Exception:
        body = str(exc)
    email = _service_account_email(credentials)
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    if status == 403 and "has not been used in project" in body:
        return (
            "The Google Sheets API is not enabled for this project.\n"
            "  Open the URL printed in the error above and click Enable, then\n"
            "  wait a minute for it to propagate and re-run."
        )
    if status == 403:
        try:
            reason = json.loads(body)["error"].get("message", body)
        except Exception:
            reason = body[:400]
        return (
            f"The service account cannot write to this spreadsheet.\n\n"
            f"  Google's reason: {reason}\n\n"
            f"  Service account: {email}\n"
            f"  Spreadsheet:     {url}\n\n"
            f"  Checklist:\n"
            f"   1. Open the spreadsheet, click Share, and confirm the address\n"
            f"      above is listed with the role Editor (not Viewer).\n"
            f"   2. If the file lives in a Shared Drive, add the service account\n"
            f"      as a member of the *drive* — file-level sharing is not enough.\n"
            f"   3. If your Workspace restricts sharing outside the organization,\n"
            f"      an admin must allow it, or move the sheet to a personal\n"
            f"      Google account that has no such restriction.\n"
            f"   4. Confirm the id above is the sheet you actually shared."
        )
    if status == 404:
        return (
            f"No spreadsheet with id {sheet_id!r}.\n"
            f"  FDGA_SHEETS_ID is the token between '/d/' and '/edit' in the\n"
            f"  spreadsheet URL — not the whole URL, and not the '#gid=' number."
        )
    if status == 400 and "exceeds the maximum" in body:
        return (
            "The spreadsheet hit a Google Sheets size limit.\n"
            "  Re-run with --skip facts to publish only the aggregate tabs."
        )
    return f"Google Sheets API error {status}:\n{body[:800]}"


def diagnose(sheet_id: str, credentials: Path) -> int:
    """Probe read and write separately so the failing capability is obvious."""
    from googleapiclient.errors import HttpError

    email = _service_account_email(credentials)
    print(f"Service account : {email}")
    print(f"Spreadsheet id  : {sheet_id}\n")

    service = _load_client(credentials)

    print("[1/2] READ  — spreadsheets().get()")
    try:
        meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        title = meta["properties"]["title"]
        tabs = [s["properties"]["title"] for s in meta["sheets"]]
        print(f"      OK — title {title!r}")
        print(f"      existing tabs: {tabs}")
    except HttpError as exc:
        print("      FAILED")
        print(_explain_api_error(exc, sheet_id, credentials))
        return 1

    print("\n[2/2] WRITE — values().update() on one scratch cell")
    try:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{tabs[0]}!A1",
            valueInputOption="RAW",
            body={"values": [[""]]},
        ).execute()
        print("      OK — the account can write\n")
        print("Both checks passed. Re-run the push; if it still fails the "
              "problem is elsewhere and worth reporting.")
        return 0
    except HttpError as exc:
        print("      FAILED\n")
        print("Read works but write does not — the account has Viewer access, "
              "not Editor.\n")
        print(_explain_api_error(exc, sheet_id, credentials))
        return 1


def _ensure_tabs(service, sheet_id: str,
                 shapes: dict[str, tuple[int, int]]) -> None:
    """Create any missing tabs and size every grid to fit its table.

    A new tab defaults to a 1000 x 26 grid, and ``values().update()`` will not
    grow it — writing outside the grid fails with 'exceeds grid limits'. Two
    tables here need more than the default: ``facts`` is 32k rows and
    ``contests`` is 27 columns wide. So the grid is set explicitly, both on
    creation and on every later push (a table gains rows each election).
    """
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = {
        s["properties"]["title"]: s["properties"] for s in meta["sheets"]
    }

    missing = [n for n in shapes if n not in existing]
    if missing:
        print(f"  creating {len(missing)} tab(s): {', '.join(missing)}")
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "addSheet": {"properties": {
                    "title": name,
                    "gridProperties": {
                        "rowCount": shapes[name][0],
                        "columnCount": shapes[name][1],
                    },
                }},
            } for name in missing]},
        ).execute()
        meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        existing = {
            s["properties"]["title"]: s["properties"] for s in meta["sheets"]
        }

    # Grow any existing tab that is now too small for its table.
    resizes = []
    for name, (rows, cols) in shapes.items():
        props = existing.get(name)
        if not props:
            continue
        grid = props.get("gridProperties", {})
        if grid.get("rowCount", 0) < rows or grid.get("columnCount", 0) < cols:
            resizes.append({"updateSheetProperties": {
                "properties": {
                    "sheetId": props["sheetId"],
                    "gridProperties": {
                        "rowCount": max(rows, grid.get("rowCount", 0)),
                        "columnCount": max(cols, grid.get("columnCount", 0)),
                    },
                },
                "fields": "gridProperties.rowCount,gridProperties.columnCount",
            }})
    if resizes:
        print(f"  resizing {len(resizes)} grid(s) to fit")
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id, body={"requests": resizes},
        ).execute()


def push(fdga_dir: Path, sheet_id: str, credentials: Path,
         skip: set[str], dry_run: bool) -> int:
    frames: dict[str, pd.DataFrame] = {}
    for tab, stem in TABS.items():
        if tab in skip:
            print(f"  {tab:16s} skipped")
            continue
        path = fdga_dir / f"{stem}.csv"
        if not path.exists():
            print(f"  {tab:16s} MISSING {path.name} — run build_fdga_cdm.py first")
            continue
        frames[tab] = pd.read_csv(path)

    if not frames:
        raise SystemExit("Nothing to push.")

    total_cells = sum((len(d) + 1) * len(d.columns) for d in frames.values())
    print(f"\n{len(frames)} tab(s), {total_cells:,} cells total")
    # IMPORTRANGE is reliable to roughly 50-100k cells per call, less when the
    # cells are text-heavy. Anything above that must be pulled as a column
    # subset, or read directly by a BI tool (which bypasses IMPORTRANGE).
    for tab, df in frames.items():
        cells = (len(df) + 1) * len(df.columns)
        if cells > 100_000:
            note = "  <- too big for IMPORTRANGE; use a BI tool"
        elif cells > 50_000:
            note = "  <- near the IMPORTRANGE limit; pull a column subset"
        else:
            note = ""
        print(f"  {tab:16s} {len(df):7,d} rows x {len(df.columns):2d} cols "
              f"= {cells:8,d} cells{note}")

    if dry_run:
        print("\n(--dry-run: nothing sent)")
        return 0

    from googleapiclient.errors import HttpError

    print(f"\nAuthenticating as {_service_account_email(credentials)}")
    print("  (this address must have Editor access to the spreadsheet)")
    service = _load_client(credentials)

    # Header row plus data, and at least Google's minimum of one column.
    shapes = {
        tab: (len(df) + 1, max(len(df.columns), 1)) for tab, df in frames.items()
    }
    try:
        _ensure_tabs(service, sheet_id, shapes)

        print()
        for tab, df in frames.items():
            service.spreadsheets().values().clear(
                spreadsheetId=sheet_id, range=tab, body={}
            ).execute()
            values = _to_values(df)
            # Header goes with the first chunk; later chunks append below it.
            written = 0
            for start in range(0, len(values), _CHUNK_ROWS):
                chunk = values[start:start + _CHUNK_ROWS]
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=f"{tab}!A{start + 1}",
                    valueInputOption="RAW",
                    body={"values": chunk},
                ).execute()
                written += len(chunk)
            print(f"  {tab:16s} wrote {written - 1:,} rows")
    except HttpError as exc:
        print("\n" + "-" * 70, file=sys.stderr)
        print(_explain_api_error(exc, sheet_id, credentials), file=sys.stderr)
        print("-" * 70, file=sys.stderr)
        return 1

    print(f"\nhttps://docs.google.com/spreadsheets/d/{sheet_id}/edit")
    print("Reminder: share this spreadsheet view-only. It is a published "
          "artifact — every refresh overwrites it.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fdga-dir", type=Path, default=_FDGA_DIR)
    p.add_argument("--sheet-id", default=os.environ.get("FDGA_SHEETS_ID"))
    p.add_argument("--credentials", type=Path,
                   default=os.environ.get("FDGA_SHEETS_CREDENTIALS"))
    p.add_argument("--skip", action="append", default=[],
                   help="tab to skip (repeatable); e.g. --skip facts")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would be sent without calling the API")
    p.add_argument("--diagnose", action="store_true",
                   help="probe read and write access separately and stop")
    args = p.parse_args()

    if not args.dry_run:
        if not args.sheet_id:
            raise SystemExit("Set FDGA_SHEETS_ID or pass --sheet-id.")
        if not args.credentials:
            raise SystemExit(
                "Set FDGA_SHEETS_CREDENTIALS or pass --credentials."
            )
        if not Path(args.credentials).exists():
            raise SystemExit(f"Credentials file not found: {args.credentials}")

    if args.diagnose:
        return diagnose(args.sheet_id, Path(args.credentials))

    return push(
        args.fdga_dir, args.sheet_id or "",
        Path(args.credentials) if args.credentials else Path(),
        set(args.skip), args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
