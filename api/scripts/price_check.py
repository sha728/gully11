"""Which player features explain what franchises really paid at the IPL auctions?

For each past auction (2024, 2025, 2026) every sold player is described using only
what was known before it (``pool._rated(before=year)``), then a price model is fitted
on two auctions and scored on the third, for several sets of features. Prices are in
lakh, scaled to a 120 cr purse so the three years pool; lower error is better.

    uv run python scripts/price_check.py
"""

from __future__ import annotations

import csv
import math
import statistics
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from gully_api.auction.pool import _rated, skills
from gully_api.settings import settings

DATA = Path(__file__).resolve().parent.parent / "src" / "gully_api" / "auction" / "data"
PURSE = {2024: 10000, 2025: 12000, 2026: 12500}      # lakh, what each year's franchises had
RETENTION_AUCTION = {2026: "ipl2026_auction.csv"}


def load_sales() -> list[dict]:
    rows = []
    for r in csv.DictReader((DATA / "ipl_auction_history.csv").open(encoding="utf-8")):
        rows.append({**r, "year": int(r["year"])})
    for r in csv.DictReader((DATA / "ipl2026_auction.csv").open(encoding="utf-8")):
        rows.append({**r, "year": 2026})
    out = []
    for r in rows:
        if not r["player_id"] or not r["base_lakh"] or not r["price_lakh"]:
            continue
        out.append({"year": r["year"], "id": r["player_id"], "price": int(r["price_lakh"]) * 12000 / PURSE[r["year"]],
                    "base": int(r["base_lakh"]), "capped": r["capped"] in ("True", "true"),
                    "country": r["country"] or "India", "role": r["role"]})
    return out


def features(sales: list[dict], conn) -> list[dict]:
    out = []
    for year in sorted({s["year"] for s in sales}):
        mine = [s for s in sales if s["year"] == year]
        pool = _rated(conn, [s["id"] for s in mine], before=str(year), rolling=True)
        by = {p["id"]: (i, p) for i, p in enumerate(pool)}
        vals = [p["value"] for p in pool]
        floor = min(vals)
        for s in mine:
            rank, p = by.get(s["id"], (len(pool), None))
            bat, bowl = skills(p) if p else (0.0, 0.0)
            out.append({**s, "value": p["value"] if p else floor, "rank": rank, "bat": bat, "bowl": bowl,
                        "form_m": (p["m"] or 0) if p else 0, "recent": bool(p and p["last_ipl"] == str(year - 1)),
                        "ipl": p["ipl_career"] if p else 0, "t20i": p["t20i_career"] if p else 0,
                        "known": p is not None, "role": s["role"] or (p["role"] if p else "BAT"),
                        "overseas": s["country"] != "India"})
    return out


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (small systems, no numpy needed)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


def design(rows: list[dict], names: list[str]) -> list[list[float]]:
    cols = {
        "value": lambda r: r["value"],
        "value+": lambda r: max(r["value"], 0.0),          # stars cost more than average ones
        "log rank": lambda r: math.log1p(r["rank"]),
        "capped": lambda r: float(r["capped"]),
        "overseas": lambda r: float(r["overseas"]),
        "bowler": lambda r: float(r["role"] == "BOWL"),
        "keeper": lambda r: float(r["role"] == "WK"),
        "allrounder": lambda r: float(r["role"] == "AR"),
        "bat": lambda r: r["bat"] if r["role"] in ("BAT", "WK", "AR") else 0.0,
        "bowl": lambda r: r["bowl"] if r["role"] in ("BOWL", "AR") else 0.0,
        "log form m": lambda r: math.log1p(r["form_m"]),
        "recent": lambda r: float(r["recent"]),
        "value2": lambda r: r["value"] ** 2,
        "log base": lambda r: math.log(r["base"]),
        "log ipl": lambda r: math.log1p(r["ipl"]),
        "log t20i": lambda r: math.log1p(r["t20i"]),
    }
    return [[1.0] + [cols[n](r) for n in names] for r in rows]


def fit(rows, names, ridge=1.0):
    X, y = design(rows, names), [math.log(r["price"]) for r in rows]
    k = len(X[0])
    xtx = [[sum(x[i] * x[j] for x in X) + (ridge if i == j and i > 0 else 0.0) for j in range(k)] for i in range(k)]
    xty = [sum(x[i] * t for x, t in zip(X, y)) for i in range(k)]
    return solve(xtx, xty)


def main() -> None:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        rows = features(load_sales(), conn)
    years = sorted({r["year"] for r in rows})
    print(f"{len(rows)} sales: " + ", ".join(f"{y}: {sum(r['year'] == y for r in rows)}" for y in years)
          + f"; {sum(not r['known'] for r in rows)} without IPL form in the 3 seasons before")
    sets = {
        "nothing (flat)": [],
        "rank only": ["log rank"],
        "value": ["value", "value+"],
        "value + status": ["value", "value+", "capped", "overseas", "bowler", "keeper", "allrounder"],
        "+ base price": ["value", "value+", "capped", "overseas", "bowler", "keeper", "allrounder", "log base"],
        "+ career caps": ["value", "value+", "capped", "overseas", "bowler", "keeper", "allrounder", "log base",
                          "log ipl", "log t20i"],
        "skills + status": ["bat", "bowl", "log form m", "recent", "log ipl", "log t20i", "capped", "overseas",
                            "bowler", "keeper", "allrounder"],
        "value + more": ["value", "value+", "value2", "log form m", "recent", "log ipl", "log t20i", "capped",
                         "overseas", "bowler", "keeper", "allrounder"],
        "status + base only": ["capped", "overseas", "bowler", "keeper", "allrounder", "log base"],
    }
    print(f"\n{'features':22}" + "".join(f"{'test ' + str(y):>12}" for y in years) + f"{'all':>10}   (log-price RMSE; MAE in crore)")
    for label, names in sets.items():
        errs, maes, allp = [], [], []
        for y in years:
            tr, te = [r for r in rows if r["year"] != y], [r for r in rows if r["year"] == y]
            w = fit(tr, names)
            pred = [sum(a * b for a, b in zip(x, w)) for x in design(te, names)]
            truth = [math.log(r["price"]) for r in te]
            errs.append(math.sqrt(statistics.mean((p - t) ** 2 for p, t in zip(pred, truth))))
            maes.append(statistics.mean(abs(math.exp(p) - math.exp(t)) for p, t in zip(pred, truth)) / 100)
            allp += list(zip(pred, truth))
        r2 = 1 - sum((p - t) ** 2 for p, t in allp) / sum((t - statistics.mean(t for _, t in allp)) ** 2 for _, t in allp)
        print(f"{label:22}" + "".join(f"{e:6.2f}/{m:4.1f}cr" for e, m in zip(errs, maes)) + f"{r2:10.2f}")




def show(year: int = 2025, n: int = 14) -> None:
    """Fitted-on-the-other-years predictions against the real prices of the year's top lots."""
    names = ["value", "value+", "capped", "overseas", "bowler", "keeper", "allrounder"]
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        rows = features(load_sales(), conn)
    w = fit([r for r in rows if r["year"] != year], names)
    te = sorted((r for r in rows if r["year"] == year), key=lambda r: -r["price"])
    pred = [math.exp(sum(a * b for a, b in zip(x, w))) for x in design(te, names)]
    for r, p in list(zip(te, pred))[:n]:
        print(f"  {r['id'][:6]} {r['role']:5} val {r['value']:5.2f}  real {r['price'] / 100:5.1f} cr  model {p / 100:5.1f} cr")
    tot_r, tot_p = sum(r["price"] for r in te), sum(pred)
    print(f"  total real {tot_r / 100:.0f} cr, model {tot_p / 100:.0f} cr; top-10 real {sum(r['price'] for r in te[:10]) / 100:.0f}, "
          f"model {sum(sorted(pred)[-10:]) / 100:.0f}")


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    for r, i in enumerate(order):
        out[i] = r
    return out


def ordering() -> None:
    """How well does each score order the players of a held-out auction by the price they fetched?
    Spearman correlation, and how many of the real 15 dearest the score puts in its own top 15."""
    sets = {"value (current)": None,
            "value + status": ["value", "value+", "capped", "overseas", "bowler", "keeper", "allrounder"],
            "skills + status": ["bat", "bowl", "log form m", "recent", "log ipl", "log t20i", "capped", "overseas",
                                "bowler", "keeper", "allrounder"],
            "status + caps": ["log ipl", "log t20i", "capped", "overseas", "bowler", "keeper", "allrounder"]}
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        rows = features(load_sales(), conn)
    print(f"{'score':18}" + "".join(f"{y:>16}" for y in (2024, 2025, 2026)) + "     (Spearman / top-15 overlap)")
    for label, names in sets.items():
        cells = []
        for y in (2024, 2025, 2026):
            te = [r for r in rows if r["year"] == y]
            if names is None:
                score = [r["value"] for r in te]
            else:
                w = fit([r for r in rows if r["year"] != y], names)
                score = [sum(a * b for a, b in zip(x, w)) for x in design(te, names)]
            price = [r["price"] for r in te]
            rho = statistics.correlation(ranks(score), ranks(price))
            top = lambda xs: set(sorted(range(len(xs)), key=lambda i: -xs[i])[:15])  # noqa: E731
            cells.append(f"{rho:7.2f} / {len(top(score) & top(price)):2}")
        print(f"{label:18}" + "".join(f"{c:>16}" for c in cells))


def curve_check() -> None:
    """How does the game's fair-price curve (by value rank) compare with what rank bought in real auctions?"""
    from gully_api.auction.pool import FLOOR_PRICE, TOP_PRICE, decay_for, price_curve
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        rows = features(load_sales(), conn)
    tau0 = decay_for(10, 12000)
    print(f"current curve: top {TOP_PRICE / 100:.0f} cr, tau {tau0:.1f} ranks; "
          f"fair at rank 0/10/30/60/120/200: " + ", ".join(f"{price_curve(k, tau0) / 100:.1f}" for k in (0, 10, 30, 60, 120, 200)))
    bands = [(0, 10), (10, 30), (30, 60), (60, 120), (120, 400)]
    print(f"{'value rank':12}" + "".join(f"{f'{a}-{b}':>14}" for a, b in bands) + "      (real mean price in cr, n)")
    for y in (2024, 2025, 2026):
        cells = []
        for a, b in bands:
            xs = [r["price"] for r in rows if r["year"] == y and a <= r["rank"] < b]
            cells.append(f"{statistics.mean(xs) / 100:6.1f} ({len(xs):2})" if xs else "     -")
        print(f"{y:<12}" + "".join(f"{c:>14}" for c in cells))
    cur = [statistics.mean(price_curve(k, tau0) for k in range(a, b)) / 100 for a, b in bands]
    print(f"{'curve':12}" + "".join(f"{c:14.1f}" for c in cur))
    # Refit the curve on the real (rank, price) pairs: least squares over top and tau.
    pairs = [(r["rank"], r["price"]) for r in rows]
    best = None
    for top in range(800, 3200, 100):
        for tau in range(10, 300, 5):
            err = sum((FLOOR_PRICE + (top - FLOOR_PRICE) * math.exp(-k / tau) - pr) ** 2 for k, pr in pairs)
            if best is None or err < best[0]:
                best = (err, top, tau)
    cur_err = sum((price_curve(k, tau0) - pr) ** 2 for k, pr in pairs)
    print(f"best fit to all sales: top {best[1] / 100:.0f} cr, tau {best[2]}, rms {math.sqrt(best[0] / len(pairs)) / 100:.2f} cr "
          f"(current curve rms {math.sqrt(cur_err / len(pairs)) / 100:.2f} cr)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "curve":
        curve_check()
    elif len(sys.argv) > 1 and sys.argv[1] == "order":
        ordering()
    elif len(sys.argv) > 1 and sys.argv[1] == "show":
        show(int(sys.argv[2]) if len(sys.argv) > 2 else 2025)
    else:
        sys.exit(main())
