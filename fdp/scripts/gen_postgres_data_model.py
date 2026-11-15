"""Regenerate the reference half of fdp/cdm/postgres_data_model.md.

The narrative above the marker is hand-written and preserved. Everything below
it — every table, view, constraint, index and column — is read out of the live
PostgreSQL catalog, so the document cannot drift from the deployed schema.

Run after any change to postgres_ddl.sql or postgres_comments.sql:

    export FDGA_DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/fdga
    uv run --project fdp python fdp/scripts/gen_postgres_data_model.py
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "fdp" / "cdm" / "postgres_data_model.md"
SCHEMA = "fdga"
MARKER = "<!-- BEGIN GENERATED REFERENCE"


def _esc(text: str | None) -> str:
    """Make a comment safe inside a markdown table cell."""
    return (text or "").replace("|", r"\|").replace("\n", " ").strip()


def _fetch(cur, sql: str, *params):
    cur.execute(sql, params)
    return cur.fetchall()


def build_reference(cur) -> str:
    rels = _fetch(cur, """
        SELECT c.relname, c.relkind, obj_description(c.oid),
               pg_size_pretty(pg_total_relation_size(c.oid))
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind IN ('r', 'v')
        ORDER BY c.relkind DESC, c.relname;""", SCHEMA)

    cols: dict[str, list] = {}
    for rel, *rest in _fetch(cur, """
        SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
               NOT a.attnotnull, col_description(c.oid, a.attnum)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0
                           AND NOT a.attisdropped
        WHERE n.nspname = %s AND c.relkind IN ('r', 'v')
        ORDER BY c.relname, a.attnum;""", SCHEMA):
        cols.setdefault(rel, []).append(rest)

    cons: dict[str, list] = {}
    for rel, name, definition in _fetch(cur, """
        SELECT rel.relname, con.conname, pg_get_constraintdef(con.oid)
        FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        WHERE n.nspname = %s ORDER BY rel.relname, con.conname;""", SCHEMA):
        cons.setdefault(rel, []).append((name, definition))

    idx: dict[str, list] = {}
    for rel, name, definition in _fetch(cur, """
        SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname = %s ORDER BY tablename, indexname;""", SCHEMA):
        idx.setdefault(rel, []).append((name, definition))

    viewdefs = dict(_fetch(cur, """
        SELECT viewname,
               pg_get_viewdef((quote_ident(schemaname) || '.'
                               || quote_ident(viewname))::regclass, true)
        FROM pg_views WHERE schemaname = %s;""", SCHEMA))

    counts = {}
    for name, kind, _, _ in rels:
        if kind == "r":
            cur.execute(f'SELECT count(*) FROM {SCHEMA}."{name}";')
            counts[name] = cur.fetchone()[0]

    known = {name for name, _, _, _ in rels}
    out: list[str] = []

    for kind, heading in (("r", "Table reference"), ("v", "View reference")):
        out.append(f"\n---\n\n# {heading}\n")
        for name, relkind, desc, size in rels:
            if relkind != kind:
                continue
            out.append(f"\n## `{SCHEMA}.{name}`\n")
            if desc:
                out.append(f"\n{_esc(desc)}\n")

            meta = []
            if kind == "r":
                meta.append(f"**Rows:** {counts[name]:,}")
                meta.append(f"**Size:** {size}")
            meta.append(f"**Columns:** {len(cols.get(name, []))}")
            if kind == "v":
                deps = sorted({
                    m for m in re.findall(rf"{SCHEMA}\.(\w+)", viewdefs.get(name, ""))
                    if m in known and m != name})
                if deps:
                    meta.append("**Reads:** " + ", ".join(f"`{d}`" for d in deps))
            out.append("\n" + " · ".join(meta) + "\n")

            if kind == "r" and name in cons:
                out.append("\n**Constraints**\n")
                for cname, cdef in cons[name]:
                    out.append(f"\n- `{cname}` — `{_esc(cdef)}`")
                out.append("\n")

            if kind == "r" and name in idx:
                # A unique/primary constraint already prints above; do not repeat
                # the index it is backed by.
                extra = [i for i in idx[name]
                         if not any(i[0] == c[0] for c in cons.get(name, []))]
                if extra:
                    out.append("\n**Indexes**\n")
                    for iname, idef in extra:
                        out.append(f"\n- `{iname}` — `{idef.split('USING ')[-1]}`")
                    out.append("\n")

            out.append("\n| Column | Type | Null | Description |\n|---|---|---|---|\n")
            for cname, ctype, nullable, cdesc in cols.get(name, []):
                out.append(f"| `{cname}` | {ctype} | "
                           f"{'yes' if nullable else 'no'} | {_esc(cdesc)} |\n")

    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database-url",
                    default=os.environ.get("FDGA_DATABASE_URL")
                            or os.environ.get("DATABASE_URL"))
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the document is out of date; write nothing")
    args = ap.parse_args()

    if not args.database_url:
        print("Set FDGA_DATABASE_URL (or DATABASE_URL), or pass --database-url.",
              file=sys.stderr)
        return 2

    text = DOC.read_text()
    if MARKER not in text:
        print(f"Marker {MARKER!r} not found in {DOC}.", file=sys.stderr)
        return 2
    head, _, tail = text.partition(MARKER)
    preserved = MARKER + tail.split("-->", 1)[0] + "-->\n"

    try:
        import psycopg
    except ModuleNotFoundError:
        print("psycopg is required:\n  uv add --project fdp 'psycopg[binary]'",
              file=sys.stderr)
        return 2

    with psycopg.connect(args.database_url) as conn, conn.cursor() as cur:
        reference = build_reference(cur)

    updated = head + preserved + reference

    if args.check:
        if updated != text:
            print(f"{DOC.name} is out of date — re-run without --check.",
                  file=sys.stderr)
            return 1
        print(f"{DOC.name} is up to date.")
        return 0

    DOC.write_text(updated)
    print(f"Wrote {DOC.relative_to(Path.cwd()) if DOC.is_relative_to(Path.cwd()) else DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
