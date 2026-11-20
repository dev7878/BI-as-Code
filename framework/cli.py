"""Command line for builders and agents.

    rbc-bi validate [files...]     validate config, semantic layer and dashboards (exit 1 on errors)
    rbc-bi run [--port 8050]       start the app with live reload on YAML changes
    rbc-bi data                    build data/warehouse.duckdb from data/raw
    rbc-bi datasets [name]         describe the semantic layer (datasets, fields, types)
    rbc-bi sql <dataset>           print the SQL behind a dataset
    rbc-bi query "<sql>"           run a read-only query against the warehouse
    rbc-bi schema                  export the dashboard JSON Schema for IDE autocomplete
    rbc-bi snapshot <id>           render a dashboard to snapshots/<id>.png and .pdf (deck team)

Also available as `python -m rbc_bi <command>`.
"""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

from rbc_bi import paths


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass


def cmd_validate(args) -> int:
    from rbc_bi.spec.validator import load_project

    only = [Path(p).resolve() for p in args.files] if args.files else None
    proj = load_project(check_sql=not args.no_sql, only=only)
    for e in proj.errors:
        print(f"ERROR {e}")
    n = len(proj.dashboards)
    if proj.errors:
        print(f"\n{len(proj.errors)} error(s). {n} dashboard(s) valid, {len(proj.invalid_dashboard_files)} invalid.")
        return 1
    print(f"OK: config, semantic layer ({len(proj.semantic.datasets)} datasets) and {n} dashboard(s) are valid.")
    return 0


def cmd_run(args) -> int:
    from rbc_bi.app import run

    run(port=args.port, reload=not args.no_reload)
    return 0


def cmd_data(args) -> int:
    runpy.run_path(str(paths.DATA_DIR / "build_warehouse.py"), run_name="__main__")
    return 0


def cmd_datasets(args) -> int:
    from rbc_bi.spec.validator import load_project

    proj = load_project()
    if proj.semantic is None:
        print("\n".join(map(str, proj.errors)))
        return 1
    for name, ds in proj.semantic.datasets.items():
        if args.name and name != args.name:
            continue
        print(f"\n## {name}  (connector: {ds.connector}, refresh: {ds.refresh}, grain: {', '.join(ds.grain)})")
        print(f"   {ds.description.strip()}")
        for fname, f in ds.fields.items():
            kind = "measure  " if f.is_numeric else "dimension"
            agg = f"agg={f.default_agg()}" + (f"({f.ratio[0]}/{f.ratio[1]})" if f.ratio else "") if f.is_numeric else ""
            desc = f" - {f.description}" if f.description else ""
            print(f"   {fname:<16} {f.type:<9} {kind} {agg:<26} {f.label}{desc}")
    used = {}
    for s in proj.dashboards:
        for _, comp in s.components():
            used.setdefault(comp.body.dataset, set()).add(s.id)
    print("\nUsed by dashboards: " + "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in used.items()))
    return 0


def cmd_sql(args) -> int:
    from rbc_bi.spec.validator import load_project

    proj = load_project()
    ds = proj.semantic.datasets.get(args.dataset)
    if ds is None:
        print(f"No dataset '{args.dataset}'. Datasets: {', '.join(proj.semantic.datasets)}")
        return 1
    print(f"-- dataset {args.dataset} (connector: {ds.connector})\n{ds.sql}")
    return 0


def cmd_query(args) -> int:
    import pandas as pd

    from rbc_bi.semantic.connectors import get_connector

    sql = args.sql.strip().rstrip(";")
    if not sql.lower().startswith(("select", "with", "describe", "show", "summarize")):
        print("Only read-only queries (select/with/describe/show/summarize) are allowed.")
        return 1
    df = get_connector(args.connector).query(sql)
    with pd.option_context("display.max_rows", args.limit, "display.max_columns", 50, "display.width", 200):
        print(df.head(args.limit).to_string(index=False))
        if len(df) > args.limit:
            print(f"... {len(df) - args.limit} more rows")
    return 0


def cmd_schema(args) -> int:
    from rbc_bi.spec.models import DashboardSpec

    schema = DashboardSpec.model_json_schema()
    schema["title"] = "Dashboard spec"
    paths.SCHEMA_PATH.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {paths.rel(paths.SCHEMA_PATH)}")
    return 0


def cmd_snapshot(args) -> int:
    from rbc_bi.modules.snapshot import snapshot

    for f in snapshot(args.id, port=args.port, pdf=not args.no_pdf):
        print(f"Wrote {paths.rel(f)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8()
    p = argparse.ArgumentParser(prog="rbc-bi", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate specs")
    v.add_argument("files", nargs="*")
    v.add_argument("--no-sql", action="store_true", help="skip running dataset SQL with LIMIT 0")
    v.set_defaults(fn=cmd_validate)

    r = sub.add_parser("run", help="start the app")
    r.add_argument("--port", type=int, default=8050)
    r.add_argument("--no-reload", action="store_true")
    r.set_defaults(fn=cmd_run)

    sub.add_parser("data", help="build the local warehouse").set_defaults(fn=cmd_data)

    d = sub.add_parser("datasets", help="describe the semantic layer")
    d.add_argument("name", nargs="?")
    d.set_defaults(fn=cmd_datasets)

    s = sub.add_parser("sql", help="print a dataset's SQL")
    s.add_argument("dataset")
    s.set_defaults(fn=cmd_sql)

    q = sub.add_parser("query", help="run a read-only query")
    q.add_argument("sql")
    q.add_argument("--connector", default="warehouse")
    q.add_argument("--limit", type=int, default=50)
    q.set_defaults(fn=cmd_query)

    sub.add_parser("schema", help="export JSON Schema").set_defaults(fn=cmd_schema)

    sn = sub.add_parser("snapshot", help="render a dashboard to PNG/PDF")
    sn.add_argument("id")
    sn.add_argument("--port", type=int, default=8050)
    sn.add_argument("--no-pdf", action="store_true")
    sn.set_defaults(fn=cmd_snapshot)

    args = p.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
