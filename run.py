"""Esegue tutte le strategie, le confronta con il buy & hold e scrive il report in output/.

Uso:  .venv\\Scripts\\python.exe run.py                  (ETF UCITS, dati in cache)
      .venv\\Scripts\\python.exe run.py --universo usa   (storico lungo USA)
      .venv\\Scripts\\python.exe run.py --refresh        (riscarica i prezzi)
"""

import argparse
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

warnings.filterwarnings("ignore", module="yfinance")

from investlab import config as C
from investlab import strategies as S
from investlab.data import check_quality, load_prices
from investlab.engine import run
from investlab.metrics import money_weighted_return, summary

OUT_ROOT = Path(__file__).resolve().parent / "output"


def strategy_set(p: pd.DataFrame, u: C.Universe, with_contributions: bool):
    """(nome, pesi strategia, come investire i versamenti, nome benchmark, pesi benchmark).

    I benchmark investono i versamenti "pro_rata": ogni mese comprano secondo i pesi
    iniziali e non vendono mai.
    """
    main_bh = S.buy_and_hold(p, {u.main: 1.0})
    mix = {u.main: 0.6, u.bonds: 0.4}
    mix_bh = S.buy_and_hold(p, mix)
    lbl = u.main_label
    sets = [
        (f"Medie mobili 50/200 ({lbl})", S.sma_crossover(p, u.main, 50, 200, out=u.cash), "pro_rata",
         f"B&H {lbl}", main_bh),
        (f"Momentum 12 mesi ({lbl})", S.time_series_momentum(p, u.main, 252, out=u.cash), "pro_rata",
         f"B&H {lbl}", main_bh),
        (f"RSI 14 30/70 ({lbl})", S.rsi_mean_reversion(p, u.main, 14, 30, 70, out=u.cash), "pro_rata",
         f"B&H {lbl}", main_bh),
        ("Dual momentum USA/Europa/Bond",
         S.dual_momentum(p, [u.us, u.eu], u.bonds, cash=u.cash, lookback=252), "pro_rata",
         f"B&H {lbl}", main_bh),
        (f"Uscita solo nei crolli ({lbl})", S.crash_filter(p, u.main, 200, 0.10, out=u.cash), "pro_rata",
         f"B&H {lbl}", main_bh),
        ("60/40 ribilanciato annuale", S.periodic_rebalance(p, mix, "YE"), "pro_rata",
         "B&H 60/40 (mai ribilanciato)", mix_bh),
    ]
    if with_contributions:
        # stessi pesi del B&H 60/40, ma i versamenti vanno a ciò che è rimasto indietro
        sets.append(("60/40 ribilanciato coi versamenti", mix_bh, "fill_gaps",
                     "B&H 60/40 (mai ribilanciato)", mix_bh))
    return sets


def fmt(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ["Rendimento annuo netto", "Rendimento senza costi/tasse", "Volatilità", "Max drawdown"]:
        if c in df:
            df[c] = df[c].map(lambda v: f"{v:+.2%}" if c != "Volatilità" else f"{v:.2%}")
    df["Sharpe"] = df["Sharpe"].map(lambda v: f"{v:.2f}")
    for c in [c for c in df.columns if c.endswith("€")]:
        df[c] = df[c].map(lambda v: f"{v:,.0f}".replace(",", "."))
    return df


def evaluate(p, strategy_targets, mode, bench_targets, name, bench_name, settings, start=None, end=None):
    strat = run(p, strategy_targets, settings, name, start, end, mode)
    # Il benchmark parte lo stesso giorno della strategia: confronto alla pari
    bench = run(p, bench_targets, settings, bench_name, strat.equity.index[0], end)
    return strat, bench


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="riscarica i prezzi da Yahoo")
    ap.add_argument("--universo", choices=list(C.UNIVERSES), default="ucits")
    ap.add_argument("--mensile", type=float, default=0.0, help="versamento mensile (PAC), es. 500")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # la console Windows non è UTF-8 di default

    settings = C.Settings(monthly_contribution=args.mensile)
    frictionless = C.no_frictions(args.mensile)
    u = C.UNIVERSES[args.universo]
    prices = load_prices(u, refresh=args.refresh)
    out = OUT_ROOT / (u.key + (f"_pac{args.mensile:.0f}" if args.mensile else ""))
    out.mkdir(parents=True, exist_ok=True)

    # liquidità esclusa: con tassi ~0 il prezzo fermo è normale, non un errore
    warnings_ = [w for t in prices if t != u.cash for w in check_quality(prices[t].dropna())]
    print(f"Universo: {u.description}")
    print(f"Problemi nei dati ({len(warnings_)}):", *(warnings_[:10] or ["nessuno"]), sep="\n  ")
    split = pd.Timestamp(u.split_date)
    periods = [
        ("Intero periodo", None, None),
        (f"In-sample (fino al {split.date()})", None, split - pd.Timedelta(days=1)),
        (f"Out-of-sample (dal {split.date()})", split, None),
    ]

    lines = [f"# Report backtest — {u.description}\n",
             f"Capitale iniziale: {settings.initial_capital:,.0f} €"
             + (f" + versamento di {args.mensile:,.0f} € al mese" if args.mensile else "")
             + ". Commissioni Fineco, spread "
             f"{settings.costs.spread_pct:.2%}, tasse 26% (minusvalenze ETF non compensabili), bollo 0,2%.\n",
             "Ultimi prezzi: " + ", ".join(f"{t} {prices[t].last_valid_index().date()}" for t in prices) + "\n"]
    if warnings_:
        lines.append("**Problemi nei dati:** " + "; ".join(warnings_) + "\n")

    for period_name, start, end in periods:
        rows = []
        for name, tgt, mode, bench_name, bench_tgt in strategy_set(prices, u, args.mensile > 0):
            strat, bench = evaluate(prices, tgt, mode, bench_tgt, name, bench_name, settings, start, end)
            ideal = run(prices, tgt, frictionless, name, strat.equity.index[0], end, mode)
            for r in (strat, bench):
                row = summary(r)
                ideal_r = ideal if r is strat else run(prices, bench_tgt, frictionless, bench_name,
                                                       strat.equity.index[0], end)
                row["Rendimento senza costi/tasse"] = money_weighted_return(ideal_r)
                rows.append(row)
            rows[-1]["Strategia"] = f"  ↳ benchmark: {bench_name}"
            rows[-2]["Batte il benchmark?"] = "SÌ" if strat.final_net > bench.final_net else "no"
            rows[-1]["Batte il benchmark?"] = ""

            if start is None and end is None:
                pd.DataFrame(strat.trades).to_csv(out / f"ordini_{_slug(name)}.csv", index=False)
                _plot(strat, bench, out)

        df = pd.DataFrame(rows)
        cols = ["Strategia", "Inizio", "Fine", "Rendimento annuo netto", "Rendimento senza costi/tasse",
                "Volatilità", "Max drawdown", "Sharpe", "Ordini", "Commissioni €", "Tasse €", "Bollo €",
                "Minus perse €", "Versato €", "Finale netto €", "Batte il benchmark?"]
        df[cols].to_csv(out / f"risultati_{_slug(period_name)}.csv", index=False)  # numeri grezzi, per i grafici
        table = fmt(df[cols])
        print(f"\n=== {period_name} ===")
        print(table.to_string(index=False))
        lines += [f"\n## {period_name}\n", table.to_markdown(index=False), ""]

    lines.append(f"\nGrafici: `output/{out.name}/curva_*.png`. Ordini eseguiti: `output/{out.name}/ordini_*.csv`.")
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport scritto in {out / 'report.md'}")


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")


def _plot(strat, bench, out: Path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, height_ratios=[3, 1])
    for r in (strat, bench):
        ax1.plot(r.equity.index, r.equity, label=r.name)
        ax2.plot(r.equity.index, (r.equity / r.equity.cummax() - 1) * 100, label=r.name)
    ax1.set_ylabel("Valore conto")
    ax1.set_yscale("log")  # scala logaritmica: su decenni le variazioni % restano confrontabili
    ax1.set_title(f"{strat.name} vs {bench.name} (dopo costi; tasse finali escluse dalla curva)")
    ax1.legend()
    ax1.grid(alpha=0.3)
    ax2.set_ylabel("Drawdown %")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / f"curva_{_slug(strat.name)}.png", dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    main()
