import argparse
import time

from .aggregate import build
from .download import DATASETS, download_dataset, download_register, download_snapshot
from .parse import iter_zip_matches, write_parquet
from .paths import DB_PATH, PARQUET_DIR, RAW_DIR


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="gully-pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="Download a Cricsheet archive and the people register")
    d.add_argument("--dataset", choices=DATASETS, default="all")
    d.add_argument("--source", choices=["cricsheet", "snapshot"], default="cricsheet",
                   help="snapshot: newest data-* GitHub Release of --repo (for CI)")
    d.add_argument("--repo", default="sha728/gully11", help="owner/name for --source snapshot")

    sn = sub.add_parser("snapshot", help="Publish downloaded Cricsheet files as a GitHub Release (for CI)")
    sn.add_argument("--repo", default="sha728/gully11")

    s = sub.add_parser("parse", help="Parse a downloaded archive into Parquet")
    s.add_argument("--dataset", choices=DATASETS, default="all")
    s.add_argument("--gender", default="male", help="male / female / any")

    b = sub.add_parser("build", help="Build player tables in DuckDB from parsed Parquet")
    b.add_argument("--dataset", choices=DATASETS, default="all")

    sub.add_parser("load", help="Load the DuckDB player tables into Postgres")

    sc = sub.add_parser("spotcheck", help="Recount players from raw JSON and compare with tables")
    sc.add_argument("names", nargs="*", help="Cricsheet unique names (default: 10 preset players)")

    sub.add_parser("legends", help="Rebuild reference/legends.csv from Wikipedia infoboxes")
    sub.add_parser("simbase", help="Write the simulator's base_rates.json from parsed data")
    sub.add_parser("names", help="Fetch full names + Wikipedia titles from Wikidata")

    args = p.parse_args(argv)

    if args.cmd == "names":
        from .wikidata import NAMES_CSV, fetch_names
        print(f"{fetch_names():,} players -> {NAMES_CSV}")
        return

    if args.cmd == "simbase":
        from .simbase import OUT_PATH, build_simbase
        t0 = time.perf_counter()
        res = build_simbase(PARQUET_DIR / "all", DB_PATH)
        for name, env in res["envs"].items():
            fi = env["first_innings"]
            print(f"{name:11} first innings n={fi['innings']:5} mean={fi['mean']:6} "
                  f"sd={fi['sd']:5} wkts={fi['mean_wickets']}")
        print(f"-> {OUT_PATH} ({time.perf_counter() - t0:.1f}s)")
        return

    if args.cmd == "legends":
        from .legends import LEGENDS_CSV, build_legends
        rows = build_legends()
        players = {r["name"] for r in rows}
        print(f"{len(players)} players, {len(rows)} player-format rows -> {LEGENDS_CSV}")
        for col in ("role", "batting_hand", "bowling_type", "format_end"):
            missing = sorted({r["name"] for r in rows if r[col] is None})
            if missing:
                print(f"  missing {col}: {missing}")
        return

    if args.cmd == "spotcheck":
        from .spotcheck import DEFAULT_PLAYERS, run
        t0 = time.perf_counter()
        rows = run(RAW_DIR / DATASETS["all"], DB_PATH, args.names or DEFAULT_PLAYERS)
        bad = [r for r in rows if r["table"] != r["raw"]]
        pairs = {(r["player"], r["format"]) for r in rows}
        print(f"{len(pairs)} player-formats, {len(rows)} values checked "
              f"({time.perf_counter() - t0:.0f}s)")
        for r in bad:
            print(f"  MISMATCH {r['player']:16} {r['format']:5} {r['field']:14} "
                  f"table={r['table']} raw={r['raw']}")
        print("OK: all match" if not bad else f"{len(bad)} mismatches")
        raise SystemExit(1 if bad else 0)

    if args.cmd == "load":
        from .load import database_url, load
        if not DB_PATH.exists():
            p.error(f"{DB_PATH} not found; run `build` first")
        t0 = time.perf_counter()
        for table, n in load(DB_PATH, database_url()).items():
            print(f"{table:22} {n:>10,}")
        print(f"-> Postgres ({time.perf_counter() - t0:.1f}s)")
        return

    if args.cmd == "build":
        src = PARQUET_DIR / args.dataset
        if not (src / "deliveries.parquet").exists():
            p.error(f"{src} has no Parquet; run `parse --dataset {args.dataset}` first")
        t0 = time.perf_counter()
        counts = build(src, RAW_DIR / "people.csv", DB_PATH)
        for table, n in counts.items():
            print(f"{table:22} {n:>10,}")
        print(f"-> {DB_PATH} ({time.perf_counter() - t0:.1f}s)")
        return

    if args.cmd == "download" and args.source == "snapshot":
        if args.dataset != "all":
            p.error("snapshots hold the full dataset; use --dataset all")
        tag, paths = download_snapshot(args.repo)
        print(f"Snapshot {tag} from {args.repo}")
        for path in paths:
            print("  ->", path)
    elif args.cmd == "download":
        print("Downloading", DATASETS[args.dataset], "...")
        print("  ->", download_dataset(args.dataset))
        print("  ->", download_register())
    elif args.cmd == "snapshot":
        from .snapshot import publish
        print("Published", publish(args.repo))
    elif args.cmd == "parse":
        zip_path = RAW_DIR / DATASETS[args.dataset]
        if not zip_path.exists():
            p.error(f"{zip_path} not found; run `download --dataset {args.dataset}` first")
        out = PARQUET_DIR / args.dataset
        t0 = time.perf_counter()
        gender = None if args.gender == "any" else args.gender
        n_m, n_d = write_parquet(iter_zip_matches(zip_path), out, gender=gender)
        print(f"{n_m:,} matches, {n_d:,} deliveries -> {out} "
              f"({time.perf_counter() - t0:.1f}s)")


if __name__ == "__main__":
    main()
