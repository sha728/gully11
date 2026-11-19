import argparse
import time

from .download import DATASETS, download_dataset, download_register
from .parse import iter_zip_matches, write_parquet
from .paths import PARQUET_DIR, RAW_DIR


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="gully-pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="Download a Cricsheet archive and the people register")
    d.add_argument("--dataset", choices=DATASETS, default="all")

    s = sub.add_parser("parse", help="Parse a downloaded archive into Parquet")
    s.add_argument("--dataset", choices=DATASETS, default="all")
    s.add_argument("--gender", default="male", help="male / female / any")

    args = p.parse_args(argv)

    if args.cmd == "download":
        print("Downloading", DATASETS[args.dataset], "...")
        print("  ->", download_dataset(args.dataset))
        print("  ->", download_register())
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
