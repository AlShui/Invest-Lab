"""Metriche di risultato. Spiegazioni in README.md."""

import numpy as np
import pandas as pd

from .engine import Result


def _years(r: Result) -> float:
    return (r.equity.index[-1] - r.equity.index[0]).days / 365.25


def cagr(final: float, initial: float, years: float) -> float:
    return (final / initial) ** (1 / years) - 1 if years > 0 and final > 0 else np.nan


def xirr(dates: pd.DatetimeIndex, amounts: np.ndarray) -> float:
    """Rendimento annuo dei flussi di denaro (negativi = versamenti, positivi = incasso finale).

    È il tasso che renderebbe equivalente mettere quei soldi in un conto a rendimento fisso.
    Senza versamenti intermedi coincide con il CAGR.
    """
    t = np.asarray((dates - dates[0]).days, dtype=float) / 365.25
    amounts = np.asarray(amounts, dtype=float)

    def npv(rate):
        return float(np.sum(amounts / (1 + rate) ** t))

    lo, hi = -0.99, 1.0
    if npv(lo) * npv(hi) > 0:
        return np.nan
    for _ in range(200):  # bisezione: lenta ma sempre stabile
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def money_weighted_return(r: Result) -> float:
    flows = r.contributions if r.contributions is not None else pd.Series(0.0, index=r.equity.index)
    amounts = -flows.to_numpy().copy()
    amounts[0] -= r.initial_capital
    amounts[-1] += r.final_net
    return xirr(r.equity.index, amounts)


def time_weighted_index(r: Result) -> pd.Series:
    """Andamento del conto "depurato" dai versamenti: misura la strategia, non quanto si è versato."""
    flows = r.contributions if r.contributions is not None else 0.0
    daily = (r.equity - flows) / r.equity.shift(1) - 1
    return (1 + daily.fillna(0)).cumprod()


def max_drawdown(r: Result) -> float:
    idx = time_weighted_index(r)
    return float((idx / idx.cummax() - 1).min())


def summary(r: Result) -> dict:
    daily = time_weighted_index(r).pct_change().dropna()
    vol = daily.std() * np.sqrt(252)
    return {
        "Strategia": r.name,
        "Inizio": r.equity.index[0].date(),
        "Fine": r.equity.index[-1].date(),
        "Rendimento annuo netto": money_weighted_return(r),
        "Volatilità": vol,
        "Max drawdown": max_drawdown(r),
        # Sharpe con tasso privo di rischio = 0 (tassi EUR quasi nulli per gran parte del periodo)
        "Sharpe": daily.mean() * 252 / vol if vol > 0 else np.nan,
        "Ordini": r.orders,
        "Commissioni €": r.commissions + r.spread_cost,
        "Tasse €": r.taxes,  # incluse quelle pagate alla liquidazione finale
        "Bollo €": r.stamp_duty,
        "Minus perse €": r.unused_losses,
        "Versato €": r.total_invested,
        "Finale netto €": r.final_net,
    }
