"""Genera le immagini del README: italiano in docs/img/, inglese in docs/img/en/.

Uso:  .venv\\Scripts\\python.exe make_charts.py
(i prezzi devono essere già in cache e output/ucits/ deve esistere: lanciare prima
run.py e run.py --universo usa)
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

ROOT = Path(__file__).resolve().parent
OUT_DIRS = {"it": ROOT / "docs" / "img", "en": ROOT / "docs" / "img" / "en"}

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

# Tutti i testi dei grafici, per lingua
TEXT = {
    "it": {
        "bh_swda": "Buy & hold SWDA", "crash": "Uscita solo nei crolli", "dual": "Dual momentum",
        "mom": "Momentum 12 mesi", "sma": "Medie mobili 50/200", "rsi": "RSI 14 30/70",
        "bh_sp": "Buy & hold S&P 500",
        "gross": "Senza costi e tasse", "net": "Netto (commissioni Fineco, tasse 26%, bollo)",
        "ret_title": "Rendimento annuo, ETF UCITS (giugno 2011 - ottobre 2026)",
        "ret_note": "Barra chiara: prima di costi e tasse. Barra piena: quanto resta davvero. "
                    "Nessuna strategia batte il buy & hold dopo le tasse.",
        "fr_scen": ["Nessun\nattrito", "+ commissioni\ne spread", "+ bollo\n0,2%", "+ tasse 26%\n(reale)"],
        "fr_title": "Dove sparisce il vantaggio: storico USA 1981-2002",
        "fr_note": "Il momentum batteva il buy & hold finché non si pagano le tasse: "
                   "chi vende spesso paga il 26% subito, chi tiene lo rinvia alla fine.",
        "cv_title": "10.000 $ investiti nel 1981: meno crolli, ma meno rendimento",
        "cv_net": "netti", "cv_y": "Valore conto (scala log)", "cv_dd": "Drawdown",
        "cv_events": [("crollo 1987", "1987-10-19"), ("2000-03", "2002-10-01"), ("2008", "2009-03-01")],
        "pac_cases": ["Ribilanciato ogni anno\n(vende ciò che è salito)",
                      "Ribilanciato coi versamenti\n(compra ciò che è rimasto indietro)",
                      "Mai ribilanciato\n(il peso azionario sale nel tempo)"],
        "pac_label": "{ret}/anno  ·  {orders} ordini  ·  perdita max {dd}",
        "pac_title": "60/40 con PAC da 500 €/mese (ETF UCITS, 2009-2026)",
        "pac_note": "Per mantenere il 60/40, ribilanciare coi versamenti rende di più con metà degli "
                    "ordini: non vende mai, quindi non paga tasse lungo il percorso.",
        "term_universe": "Universo: ETF UCITS su Borsa Italiana (2009-oggi)",
        "term_period": "=== Intero periodo ===",
        "term_cols": ["Strategia", "Netto", "Lordo", "Max DD", "Ordini", "Finale €", "Batte B&H?"],
        "term_report": "Report scritto in output\\ucits\\report.md",
        "term_names": {}, "term_yes": "SÌ", "term_no": "no",
    },
    "en": {
        "bh_swda": "Buy & hold SWDA", "crash": "Exit only on crashes", "dual": "Dual momentum",
        "mom": "12-month momentum", "sma": "Moving averages 50/200", "rsi": "RSI 14 30/70",
        "bh_sp": "Buy & hold S&P 500",
        "gross": "Before costs and taxes", "net": "Net (broker fees, 26% tax, stamp duty)",
        "ret_title": "Annual return, UCITS ETFs (June 2011 - October 2026)",
        "ret_note": "Light bar: before costs and taxes. Solid bar: what you actually keep. "
                    "No strategy beats buy & hold after taxes.",
        "fr_scen": ["No\nfrictions", "+ fees\nand spread", "+ stamp duty\n0.2%", "+ 26% tax\n(real)"],
        "fr_title": "Where the edge disappears: US history 1981-2002",
        "fr_note": "Momentum beat buy & hold until taxes were paid: frequent sellers pay 26% right away, "
                   "holders defer it to the end.",
        "cv_title": "$10,000 invested in 1981: smaller crashes, but lower returns",
        "cv_net": "net", "cv_y": "Account value (log scale)", "cv_dd": "Drawdown",
        "cv_events": [("1987 crash", "1987-10-19"), ("2000-03", "2002-10-01"), ("2008", "2009-03-01")],
        "pac_cases": ["Rebalanced yearly\n(sells what went up)",
                      "Rebalanced with contributions\n(buys what fell behind)",
                      "Never rebalanced\n(stock weight drifts up)"],
        "pac_label": "{ret}/yr  ·  {orders} orders  ·  max drawdown {dd}",
        "pac_title": "60/40 with a 500 €/month savings plan (UCITS ETFs, 2009-2026)",
        "pac_note": "To keep a 60/40 mix, rebalancing with new contributions returns more with half the "
                    "orders: it never sells, so it pays no tax along the way.",
        "term_universe": "Universe: UCITS ETFs on Borsa Italiana (2009-today)",
        "term_period": "=== Full period ===",
        "term_cols": ["Strategy", "Net", "Gross", "Max DD", "Orders", "Final €", "Beats B&H?"],
        "term_report": "Report written to output\\ucits\\report.md",
        "term_names": {
            "Medie mobili 50/200 (SWDA)": "Moving averages 50/200 (SWDA)",
            "Momentum 12 mesi (SWDA)": "12-month momentum (SWDA)",
            "RSI 14 30/70 (SWDA)": "RSI 14 30/70 (SWDA)",
            "Dual momentum USA/Europa/Bond": "Dual momentum US/Europe/Bonds",
            "Uscita solo nei crolli (SWDA)": "Exit only on crashes (SWDA)",
            "60/40 ribilanciato annuale": "60/40 rebalanced yearly",
            "  ↳ benchmark: B&H SWDA": "  ↳ benchmark: B&H SWDA",
            "  ↳ benchmark: B&H 60/40 (mai ribilanciato)": "  ↳ benchmark: B&H 60/40 (never rebalanced)",
        },
        "term_yes": "YES", "term_no": "no",
    },
}


def pct(v: float, lang: str, decimals: int = 1) -> str:
    s = f"{v:+.{decimals}%}"
    return s.replace(".", ",") if lang == "it" else s


def thousands(v: float, lang: str) -> str:
    s = f"{v:,.0f}"
    return s.replace(",", ".") if lang == "it" else s


def save(fig, lang: str, name: str, **kw):
    OUT_DIRS[lang].mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIRS[lang] / name, dpi=130, **kw)
    plt.close(fig)


def returns_chart():
    """Rendimento netto vs senza attriti, ETF UCITS, capitale unico."""
    u = C.UCITS
    p = load_prices(u)
    st, free = C.Settings(), C.no_frictions()
    rows = [
        ("bh_swda", S.buy_and_hold(p, {u.main: 1.0})),
        ("crash", S.crash_filter(p, u.main, 200, 0.10, out=u.cash)),
        ("dual", S.dual_momentum(p, [u.us, u.eu], u.bonds, cash=u.cash)),
        ("mom", S.time_series_momentum(p, u.main, 252, out=u.cash)),
        ("sma", S.sma_crossover(p, u.main, 50, 200, out=u.cash)),
        ("rsi", S.rsi_mean_reversion(p, u.main, 14, 30, 70, out=u.cash)),
    ]
    start = "2011-06-01"  # stesso inizio per tutti (il dual momentum è pronto per ultimo)
    data = [(k, money_weighted_return(run(p, t, st, k, start)), money_weighted_return(run(p, t, free, k, start)))
            for k, t in rows]

    for lang, T in TEXT.items():
        fig, ax = plt.subplots(figsize=(9, 4.6))
        y = range(len(data))[::-1]
        h = 0.36
        for yi, (key, net, ideal) in zip(y, data):
            ax.barh(yi + h / 2, ideal, h - 0.04, color=STRATEGY, alpha=0.35, label=T["gross"] if yi == y[0] else None)
            ax.barh(yi - h / 2, net, h - 0.04, color=BENCH if key == "bh_swda" else STRATEGY,
                    label=T["net"] if yi == y[0] else None)
            ax.text(net + 0.002, yi - h / 2, pct(net, lang), va="center", fontsize=9.5, color=INK)
            ax.text(ideal + 0.002, yi + h / 2, pct(ideal, lang), va="center", fontsize=9, color=INK_2)
        ax.set_yticks(list(y), [T[d[0]] for d in data])
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.set_xlim(0, max(d[2] for d in data) * 1.18)
        ax.grid(axis="y", visible=False)
        ax.set_title(T["ret_title"])
        ax.legend(loc="lower right", frameon=False, fontsize=9)
        fig.text(0.01, 0.01, T["ret_note"], fontsize=8.5, color=INK_2)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        save(fig, lang, "rendimenti_ucits.png")


def friction_chart():
    """Dove si perde il vantaggio del momentum: USA 1981-2002."""
    u = C.USA_LONG
    p = load_prices(u)
    scen = [
        C.no_frictions(),
        C.Settings(taxes=C.Taxes(capital_gain_rate=0, stamp_duty_pct=0)),
        C.Settings(taxes=C.Taxes(capital_gain_rate=0)),
        C.Settings(),
    ]
    strats = [("mom", S.time_series_momentum(p, u.main, 252, out=u.cash), STRATEGY),
              ("bh_sp", S.buy_and_hold(p, {u.main: 1.0}), BENCH)]
    vals = {k: [money_weighted_return(run(p, tgt, s, k, "1981-01-02", "2002-12-31")) for s in scen]
            for k, tgt, _ in strats}

    for lang, T in TEXT.items():
        fig, ax = plt.subplots(figsize=(9, 4.4))
        w = 0.36
        for i, (key, _, col) in enumerate(strats):
            xs = [j + (i - 0.5) * w for j in range(len(scen))]
            ax.bar(xs, vals[key], w - 0.04, color=col, label=T[key])
            for x, v in zip(xs, vals[key]):
                ax.text(x, v + 0.002, pct(v, lang), ha="center", fontsize=9, color=INK)
        ax.set_xticks(range(len(scen)), T["fr_scen"])
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.set_ylim(0, 0.14)
        ax.grid(axis="x", visible=False)
        ax.set_title(T["fr_title"])
        ax.legend(loc="upper right", frameon=False)
        fig.text(0.01, 0.01, T["fr_note"], fontsize=8.5, color=INK_2)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        save(fig, lang, "tasse_usa.png")


def curve_chart():
    """Andamento e drawdown: momentum vs buy & hold, USA 1981-oggi."""
    u = C.USA_LONG
    p = load_prices(u)
    st = C.Settings()
    res = [("mom", run(p, S.time_series_momentum(p, u.main, 252, out=u.cash), st, "mom", "1981-01-02"), STRATEGY),
           ("bh_sp", run(p, S.buy_and_hold(p, {u.main: 1.0}), st, "bh_sp", "1981-01-02"), BENCH)]

    for lang, T in TEXT.items():
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True, height_ratios=[3, 1.3])
        for key, r, col in res:
            ax1.plot(r.equity.index, r.equity, color=col, lw=1.6, label=T[key])
            idx = time_weighted_index(r)
            ax2.plot(idx.index, (idx / idx.cummax() - 1), color=col, lw=1.2)
            ax1.annotate(f"{thousands(r.final_net / 1000, lang)}k {T['cv_net']}", (r.equity.index[-1], r.equity.iloc[-1]),
                         xytext=(4, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
        ax1.set_yscale("log")
        ax1.yaxis.set_major_formatter(lambda v, _, lang=lang: f"{thousands(v / 1000, lang)}k")
        ax1.set_title(T["cv_title"])
        ax1.legend(loc="upper left", frameon=False)
        ax1.set_ylabel(T["cv_y"])
        ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax2.set_ylabel(T["cv_dd"])
        ax2.set_ylim(-0.75, 0.05)
        for txt, x in T["cv_events"]:
            ax2.annotate(txt, (pd.Timestamp(x), -0.72), fontsize=8.5, color=INK_2, ha="center")
        ax2.set_xlim(right=pd.Timestamp("2029-06-01"))
        fig.tight_layout()
        save(fig, lang, "curva_usa.png")


def pac_chart():
    """Tre modi di tenere un 60/40 con un PAC da 500 €/mese, ETF UCITS."""
    u = C.UCITS
    p = load_prices(u)
    st = C.Settings(monthly_contribution=500)
    mix = {u.main: 0.6, u.bonds: 0.4}
    bh = S.buy_and_hold(p, mix)
    cases = [(S.periodic_rebalance(p, mix, "YE"), "pro_rata", STRATEGY),
             (bh, "fill_gaps", STRATEGY),
             (bh, "pro_rata", BENCH)]
    stats = []
    for tgt, mode, col in cases:
        r = run(p, tgt, st, "", None, None, mode)
        idx = time_weighted_index(r)
        stats.append((money_weighted_return(r), r.orders, (idx / idx.cummax() - 1).min(), col))

    for lang, T in TEXT.items():
        fig, ax = plt.subplots(figsize=(9.5, 4.2))
        for i, (v, orders, dd, col) in enumerate(stats):
            ax.barh(2 - i, v, 0.6, color=col)
            label = T["pac_label"].format(ret=pct(v, lang), orders=orders, dd=f"{dd:.0%}")
            ax.text(v + 0.003, 2 - i, label, va="center", fontsize=9.5, color=INK)
        ax.set_yticks([2, 1, 0], T["pac_cases"])
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.set_xlim(0, 0.20)
        ax.set_xticks([i / 50 for i in range(11)])
        ax.grid(axis="y", visible=False)
        ax.set_title(T["pac_title"])
        fig.text(0.01, 0.01, T["pac_note"], fontsize=8.5, color=INK_2)
        fig.tight_layout(rect=(0, 0.05, 1, 1))
        save(fig, lang, "pac_60_40.png")


def terminal_shot():
    """Immagine "da terminale" dell'output di run.py (legge output/ucits/risultati_intero_periodo.csv)."""
    raw = pd.read_csv(ROOT / "output" / "ucits" / "risultati_intero_periodo.csv")
    raw = raw[["Strategia", "Rendimento annuo netto", "Rendimento senza costi/tasse", "Max drawdown",
               "Ordini", "Finale netto €", "Batte il benchmark?"]].fillna("")

    for lang, T in TEXT.items():
        df = raw.copy()
        df.columns = T["term_cols"]
        name_col, beats_col, final_col = T["term_cols"][0], T["term_cols"][6], T["term_cols"][5]
        df[name_col] = df[name_col].map(lambda s: T["term_names"].get(s, s))
        df[beats_col] = df[beats_col].map({"SÌ": T["term_yes"], "no": T["term_no"], "": ""})
        for c in T["term_cols"][1:4]:
            df[c] = df[c].map(lambda v: f"{v:+.2%}")
        df[final_col] = df[final_col].map(lambda v: thousands(v, lang))
        lines = ["PS> .venv\\Scripts\\python.exe run.py", T["term_universe"], "",
                 T["term_period"], *df.to_string(index=False).splitlines(), "", T["term_report"]]
        fig = plt.figure(figsize=(7.9, 0.24 * len(lines) + 0.5), facecolor="#1a1a19")
        for i, ln in enumerate(lines):
            color = "#9fd39f" if ln.startswith("PS>") else "#c3c2b7" if "benchmark" in ln else "#f0efec"
            fig.text(0.015, 1 - (i + 1) / (len(lines) + 1), ln, family="monospace", fontsize=9, color=color, va="center")
        save(fig, lang, "terminale.png", facecolor="#1a1a19")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for f in (returns_chart, friction_chart, curve_chart, pac_chart, terminal_shot):
        f()
        print("ok", f.__name__)


if __name__ == "__main__":
    main()
