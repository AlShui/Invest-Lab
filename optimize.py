"""Ottimizzazione dei parametri, fatta in modo onesto.

Due verifiche:

A) In-sample / out-of-sample: per ogni strategia si provano tutte le combinazioni di
   parametri sui dati fino al 2018, si sceglie la migliore (CAGR netto) e la si giudica
   SOLO sui dati dal 2019, che durante la scelta non sono mai stati guardati.

B) Walk-forward: come farebbe un investitore reale. A inizio di ogni anno si sceglie la
   combinazione migliore usando solo gli anni precedenti, la si usa per quell'anno, poi
   si ripete. Il risultato è una sola simulazione continua (costi e tasse inclusi) sugli
   anni in cui le scelte non conoscevano il futuro.

Uso:  .venv\\Scripts\\python.exe optimize.py [--universo usa]
"""

import argparse
import sys
import warnings
from itertools import product
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", module="yfinance")

from investlab import config as C
from investlab import strategies as S
from investlab.data import load_prices
from investlab.engine import run
from investlab.metrics import cagr, max_drawdown

OUT_ROOT = Path(__file__).resolve().parent / "output"


def mix(u: C.Universe) -> dict[str, float]:
    return {u.main: 0.6, u.bonds: 0.4}


def search_space(u: C.Universe):
    """Per ogni strategia: (costruttore, griglia di parametri, parametri "da manuale", benchmark)."""
    W, bh = u.main, f"B&H {u.main_label}"
    return {
        f"Medie mobili ({u.main_label})": (
            lambda p, fast, slow: S.sma_crossover(p, W, fast, slow, out=u.cash),
            [dict(fast=f, slow=s) for f, s in product((10, 20, 50, 100), (100, 150, 200, 250)) if f < s],
            dict(fast=50, slow=200), bh),
        f"Momentum ({u.main_label})": (
            lambda p, months: S.time_series_momentum(p, W, months * 21, out=u.cash),
            [dict(months=m) for m in (3, 6, 9, 12)],
            dict(months=12), bh),
        f"RSI ({u.main_label})": (
            lambda p, period, low, high: S.rsi_mean_reversion(p, W, period, low, high, out=u.cash),
            [dict(period=n, low=lo, high=hi) for n, lo, hi in product((2, 5, 14), (20, 25, 30), (60, 70, 80))],
            dict(period=14, low=30, high=70), bh),
        "Dual momentum": (
            lambda p, months: S.dual_momentum(p, [u.us, u.eu], u.bonds, u.cash, months * 21),
            [dict(months=m) for m in (3, 6, 9, 12)],
            dict(months=12), bh),
        "60/40 ribilanciato": (
            lambda p, freq: S.periodic_rebalance(p, mix(u), freq),
            [dict(freq=f) for f in ("ME", "QE", "YE")],
            dict(freq="YE"), "B&H 60/40"),
    }


def benchmarks(p, u: C.Universe):
    return {f"B&H {u.main_label}": S.buy_and_hold(p, {u.main: 1.0}), "B&H 60/40": S.buy_and_hold(p, mix(u))}


def label(params: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in params.items())


def net_cagr(result) -> float:
    years = (result.equity.index[-1] - result.equity.index[0]).days / 365.25
    return cagr(result.final_net, result.initial_capital, years)


def ready_date(targets: pd.DataFrame) -> pd.Timestamp:
    """Primo giorno in cui la strategia ha una posizione (dopo il periodo di "riscaldamento")."""
    return targets.ffill().shift(1).dropna(how="all").index[0]


def best_params(p, candidates, settings, start, end):
    """Combinazione con il miglior CAGR netto nel periodo [start, end]."""
    scores = {i: net_cagr(run(p, tgt, settings, "", start, end)) for i, (_, tgt) in enumerate(candidates)}
    best = max(scores, key=scores.get)
    return best, scores


def stitch(p, candidates, choices: dict[int, int]) -> pd.DataFrame:
    """Unisce i pesi obiettivo: nell'anno Y si usano quelli della combinazione scelta per Y.

    L'ultimo giorno dell'anno precedente si imposta la posizione "in vigore" per la nuova
    combinazione, così il cambio di parametri viene eseguito il primo giorno di Y.
    """
    cols = sorted({c for _, tgt in candidates for c in tgt.columns})
    out = pd.DataFrame(index=p.index, columns=cols, dtype=float)
    for year, idx in sorted(choices.items()):
        tgt = candidates[idx][1].reindex(columns=cols)
        seg = (p.index.year == year)
        prev = p.index[p.index.year < year][-1]
        out.loc[seg] = tgt.loc[seg].values
        out.loc[prev] = tgt.ffill().loc[prev].fillna(0).values
    return out


def pct(v: float) -> str:
    return f"{v:+.2%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universo", choices=list(C.UNIVERSES), default="ucits")
    u = C.UNIVERSES[ap.parse_args().universo]
    sys.stdout.reconfigure(encoding="utf-8")
    settings = C.Settings()
    p = load_prices(u)
    bench = benchmarks(p, u)
    split = pd.Timestamp(u.split_date)
    first_wf_year = u.first_wf_year  # il walk-forward ha bisogno di qualche anno di storia prima di decidere
    print(f"Universo: {u.description}")
    is_end = split - pd.Timedelta(days=1)
    last_year = p.index[-1].year

    rows_a, rows_b, wf_choices = [], [], []
    for name, (build, grid, textbook, bench_name) in search_space(u).items():
        candidates = [(params, build(p, **params)) for params in grid]
        # tutte le combinazioni partono lo stesso giorno, quando anche la più "lenta" è pronta
        start = max(ready_date(t) for _, t in candidates)
        textbook_tgt = build(p, **textbook)
        print(f"{name}: {len(grid)} combinazioni, dati da {start.date()}")

        # --- A) in-sample -> out-of-sample ------------------------------------
        best, is_scores = best_params(p, candidates, settings, start, is_end)
        oos_scores = {i: net_cagr(run(p, t, settings, "", split)) for i, (_, t) in enumerate(candidates)}
        rank = sorted(oos_scores.values(), reverse=True).index(oos_scores[best]) + 1
        bench_oos = net_cagr(run(p, bench[bench_name], settings, "", split))
        rows_a.append({
            "Strategia": name,
            "Migliore in-sample": label(candidates[best][0]),
            "CAGR in-sample": pct(is_scores[best]),
            "CAGR out-of-sample": pct(oos_scores[best]),
            "Posizione out-of-sample": f"{rank}ª su {len(grid)}",
            "OOS parametri da manuale": pct(net_cagr(run(p, textbook_tgt, settings, "", split))),
            "OOS migliore in assoluto": pct(max(oos_scores.values())),
            f"OOS benchmark": f"{pct(bench_oos)} ({bench_name})",
        })

        # --- B) walk-forward ---------------------------------------------------
        # almeno 3 anni interi di dati prima della prima scelta
        wf_first = max(first_wf_year, start.year + 4)
        choices = {}
        for year in range(wf_first, last_year + 1):
            train_end = pd.Timestamp(f"{year}-01-01") - pd.Timedelta(days=1)
            choices[year], _ = best_params(p, candidates, settings, start, train_end)
            wf_choices.append({"Strategia": name, "Anno": year, "Parametri scelti": label(candidates[choices[year]][0])})
        wf_start = pd.Timestamp(f"{wf_first}-01-01")
        wf = run(p, stitch(p, candidates, choices), settings, name, wf_start)
        fixed = run(p, textbook_tgt, settings, name, wf_start)
        b = run(p, bench[bench_name], settings, bench_name, wf_start)
        rows_b.append({
            "Strategia": name,
            "Dal": wf_first,
            "CAGR walk-forward": pct(net_cagr(wf)),
            "Max DD walk-forward": pct(max_drawdown(wf)),
            "Ordini": wf.orders,
            "CAGR parametri da manuale": pct(net_cagr(fixed)),
            "CAGR benchmark": f"{pct(net_cagr(b))} ({bench_name})",
            "Max DD benchmark": pct(max_drawdown(b)),
            "Batte il benchmark?": "SÌ" if wf.final_net > b.final_net else "no",
        })

    a, b, ch = pd.DataFrame(rows_a), pd.DataFrame(rows_b), pd.DataFrame(wf_choices)
    changes = ch.pivot(index="Anno", columns="Strategia", values="Parametri scelti")
    wf_period = f"dal {first_wf_year} (o più tardi, vedi colonna Dal) al {p.index[-1].date()}"

    print(f"\n=== A) Ottimizzato fino al {is_end.date()}, verificato dal {split.date()} ===")
    print(a.to_string(index=False))
    print(f"\n=== B) Walk-forward ({wf_period}) ===")
    print(b.to_string(index=False))
    print("\nParametri scelti anno per anno:")
    print(changes.to_string())

    out = OUT_ROOT / u.key
    out.mkdir(parents=True, exist_ok=True)
    (out / "ottimizzazione.md").write_text("\n".join([
        f"# Ottimizzazione dei parametri — {u.description}\n",
        "Criterio di scelta: CAGR netto (dopo commissioni, tasse e bollo).\n",
        f"## A) Ottimizzato fino al {is_end.date()}, verificato dal {split.date()}\n",
        a.to_markdown(index=False),
        f"\n## B) Walk-forward ({wf_period})\n",
        "Ogni anno si scelgono i parametri migliori sugli anni precedenti e si usano per l'anno successivo.\n",
        b.to_markdown(index=False),
        "\n### Parametri scelti anno per anno\n",
        changes.to_markdown(),
    ]), encoding="utf-8")
    print(f"\nReport scritto in {out / 'ottimizzazione.md'}")


if __name__ == "__main__":
    main()
