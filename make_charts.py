"""Genera le immagini del README in docs/img/.

Uso:  .venv\\Scripts\\python.exe make_charts.py
(i prezzi devono essere già in cache: lanciare prima run.py almeno una volta per universo)
"""

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
from investlab.data import load_prices
from investlab.engine import run
from investlab.metrics import money_weighted_return, time_weighted_index

IMG = Path(__file__).resolve().parent / "docs" / "img"

# Palette di riferimento (validata per daltonismo): slot 1 blu, slot 2 arancio
STRATEGY = "#2a78d6"
BENCH = "#eb6834"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "text.color": INK,
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10.5, "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def pct(v: float) -> str:
    return f"{v:+.1%}".replace(".", ",")


def returns_chart():
    """Rendimento netto vs senza attriti, ETF UCITS, capitale unico."""
    u = C.UCITS
    p = load_prices(u)
    st, free = C.Settings(), C.no_frictions()
    rows = [
        ("Buy & hold SWDA", S.buy_and_hold(p, {u.main: 1.0})),
        ("Uscita solo nei crolli", S.crash_filter(p, u.main, 200, 0.10, out=u.cash)),
        ("Dual momentum", S.dual_momentum(p, [u.us, u.eu], u.bonds, cash=u.cash)),
        ("Momentum 12 mesi", S.time_series_momentum(p, u.main, 252, out=u.cash)),
        ("Medie mobili 50/200", S.sma_crossover(p, u.main, 50, 200, out=u.cash)),
        ("RSI 14 30/70", S.rsi_mean_reversion(p, u.main, 14, 30, 70, out=u.cash)),
    ]
    start = "2011-06-01"  # stesso inizio per tutti (il dual momentum è pronto per ultimo)
    data = [(n, money_weighted_return(run(p, t, st, n, start)), money_weighted_return(run(p, t, free, n, start)))
            for n, t in rows]

    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = range(len(data))[::-1]
    h = 0.36
    for yi, (name, net, ideal) in zip(y, data):
        ax.barh(yi + h / 2, ideal, h - 0.04, color=STRATEGY, alpha=0.35, label="Senza costi e tasse" if yi == y[0] else None)
        ax.barh(yi - h / 2, net, h - 0.04, color=BENCH if name.startswith("Buy") else STRATEGY,
                label="Netto (commissioni Fineco, tasse 26%, bollo)" if yi == y[0] else None)
        ax.text(net + 0.002, yi - h / 2, pct(net), va="center", fontsize=9.5, color=INK)
        ax.text(ideal + 0.002, yi + h / 2, pct(ideal), va="center", fontsize=9, color=INK_2)
    ax.set_yticks(list(y), [d[0] for d in data])
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlim(0, max(d[2] for d in data) * 1.18)
    ax.grid(axis="y", visible=False)
    ax.set_title("Rendimento annuo, ETF UCITS (giugno 2011 - ottobre 2026)")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.text(0.01, 0.01, "Barra chiara: prima di costi e tasse. Barra piena: quanto resta davvero. "
             "Nessuna strategia batte il buy & hold dopo le tasse.", fontsize=8.5, color=INK_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(IMG / "rendimenti_ucits.png", dpi=130)
    plt.close(fig)


def friction_chart():
    """Dove si perde il vantaggio del momentum: USA 1981-2002."""
    u = C.USA_LONG
    p = load_prices(u)
    scen = [
        ("Nessun\nattrito", C.no_frictions()),
        ("+ commissioni\ne spread", C.Settings(taxes=C.Taxes(capital_gain_rate=0, stamp_duty_pct=0))),
        ("+ bollo\n0,2%", C.Settings(taxes=C.Taxes(capital_gain_rate=0))),
        ("+ tasse 26%\n(reale)", C.Settings()),
    ]
    strats = [("Momentum 12 mesi", S.time_series_momentum(p, u.main, 252, out=u.cash), STRATEGY),
              ("Buy & hold S&P 500", S.buy_and_hold(p, {u.main: 1.0}), BENCH)]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    w = 0.36
    for k, (name, tgt, col) in enumerate(strats):
        vals = [money_weighted_return(run(p, tgt, s, name, "1981-01-02", "2002-12-31")) for _, s in scen]
        xs = [i + (k - 0.5) * w for i in range(len(scen))]
        ax.bar(xs, vals, w - 0.04, color=col, label=name)
        for x, v in zip(xs, vals):
            ax.text(x, v + 0.002, pct(v), ha="center", fontsize=9, color=INK)
    ax.set_xticks(range(len(scen)), [s[0] for s in scen])
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_ylim(0, 0.14)
    ax.grid(axis="x", visible=False)
    ax.set_title("Dove sparisce il vantaggio: storico USA 1981-2002")
    ax.legend(loc="upper right", frameon=False)
    fig.text(0.01, 0.01, "Il momentum batteva il buy & hold finché non si pagano le tasse: "
             "chi vende spesso paga il 26% subito, chi tiene lo rinvia alla fine.", fontsize=8.5, color=INK_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(IMG / "tasse_usa.png", dpi=130)
    plt.close(fig)


def curve_chart():
    """Andamento e drawdown: momentum vs buy & hold, USA 1981-oggi."""
    u = C.USA_LONG
    p = load_prices(u)
    st = C.Settings()
    res = [(run(p, S.time_series_momentum(p, u.main, 252, out=u.cash), st, "Momentum 12 mesi", "1981-01-02"), STRATEGY),
           (run(p, S.buy_and_hold(p, {u.main: 1.0}), st, "Buy & hold S&P 500", "1981-01-02"), BENCH)]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True, height_ratios=[3, 1.3])
    for r, col in res:
        ax1.plot(r.equity.index, r.equity, color=col, lw=1.6, label=r.name)
        idx = time_weighted_index(r)
        ax2.plot(idx.index, (idx / idx.cummax() - 1), color=col, lw=1.2)
        ax1.annotate(f"{r.final_net / 1000:,.0f}k netti".replace(",", "."), (r.equity.index[-1], r.equity.iloc[-1]),
                     xytext=(4, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
    ax1.set_yscale("log")
    ax1.yaxis.set_major_formatter(lambda v, _: f"{v / 1000:,.0f}k".replace(",", "."))
    ax1.set_title("10.000 $ investiti nel 1981: meno crolli, ma meno rendimento")
    ax1.legend(loc="upper left", frameon=False)
    ax1.set_ylabel("Valore conto (scala log)")
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax2.set_ylabel("Drawdown")
    ax2.set_ylim(-0.75, 0.05)
    for txt, x in [("crollo 1987", "1987-10-19"), ("2000-03", "2002-10-01"), ("2008", "2009-03-01")]:
        ax2.annotate(txt, (pd.Timestamp(x), -0.72), fontsize=8.5, color=INK_2, ha="center")
    ax2.set_xlim(right=pd.Timestamp("2029-06-01"))
    fig.tight_layout()
    fig.savefig(IMG / "curva_usa.png", dpi=130)
    plt.close(fig)


def pac_chart():
    """Tre modi di tenere un 60/40 con un PAC da 500 €/mese, ETF UCITS."""
    u = C.UCITS
    p = load_prices(u)
    st = C.Settings(monthly_contribution=500)
    mix = {u.main: 0.6, u.bonds: 0.4}
    bh = S.buy_and_hold(p, mix)
    cases = [
        ("Ribilanciato ogni anno\n(vende ciò che è salito)", S.periodic_rebalance(p, mix, "YE"), "pro_rata", STRATEGY),
        ("Ribilanciato coi versamenti\n(compra ciò che è rimasto indietro)", bh, "fill_gaps", STRATEGY),
        ("Mai ribilanciato\n(il peso azionario sale nel tempo)", bh, "pro_rata", BENCH),
    ]
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    for i, (name, tgt, mode, col) in enumerate(cases):
        r = run(p, tgt, st, name, None, None, mode)
        v = money_weighted_return(r)
        idx = time_weighted_index(r)
        dd = (idx / idx.cummax() - 1).min()
        ax.barh(2 - i, v, 0.6, color=col)
        ax.text(v + 0.003, 2 - i, f"{pct(v)}/anno  ·  {r.orders} ordini  ·  perdita max {dd:.0%}",
                va="center", fontsize=9.5, color=INK)
    ax.set_yticks([2, 1, 0], [c[0] for c in cases])
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlim(0, 0.20)
    ax.set_xticks([i / 50 for i in range(11)])
    ax.grid(axis="y", visible=False)
    ax.set_title("60/40 con PAC da 500 €/mese (ETF UCITS, 2009-2026)")
    fig.text(0.01, 0.01, "Per mantenere il 60/40, ribilanciare coi versamenti rende di più con metà degli "
             "ordini: non vende mai, quindi non paga tasse lungo il percorso.", fontsize=8.5, color=INK_2)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(IMG / "pac_60_40.png", dpi=130)
    plt.close(fig)


def terminal_shot():
    """Immagine "da terminale" dell'output di run.py (legge output/ucits/risultati_intero_periodo.csv)."""
    df = pd.read_csv(Path(__file__).resolve().parent / "output" / "ucits" / "risultati_intero_periodo.csv")
    df = df[["Strategia", "Rendimento annuo netto", "Rendimento senza costi/tasse", "Max drawdown",
             "Ordini", "Finale netto €", "Batte il benchmark?"]].fillna("")
    df.columns = ["Strategia", "Netto", "Lordo", "Max DD", "Ordini", "Finale €", "Batte B&H?"]
    for c in ("Netto", "Lordo", "Max DD"):
        df[c] = df[c].map(lambda v: f"{v:+.2%}")
    df["Finale €"] = df["Finale €"].map(lambda v: f"{v:,.0f}".replace(",", "."))
    lines = ["PS> .venv\\Scripts\\python.exe run.py", "Universo: ETF UCITS su Borsa Italiana (2009-oggi)", "",
             "=== Intero periodo ===", *df.to_string(index=False).splitlines(), "",
             "Report scritto in output\\ucits\\report.md"]
    fig = plt.figure(figsize=(7.7, 0.24 * len(lines) + 0.5), facecolor="#1a1a19")
    for i, ln in enumerate(lines):
        color = "#9fd39f" if ln.startswith("PS>") else "#f0efec"
        if "SÌ" in ln or ln.rstrip().endswith(" no"):
            color = "#f0efec"
        if "benchmark" in ln:
            color = "#c3c2b7"
        fig.text(0.015, 1 - (i + 1) / (len(lines) + 1), ln, family="monospace", fontsize=9, color=color, va="center")
    fig.savefig(IMG / "terminale.png", dpi=130, facecolor="#1a1a19")
    plt.close(fig)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    IMG.mkdir(parents=True, exist_ok=True)
    for f in (returns_chart, friction_chart, curve_chart, pac_chart, terminal_shot):
        f()
        print("ok", f.__name__)


if __name__ == "__main__":
    main()
