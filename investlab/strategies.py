"""Strategie di investimento di base.

Ogni strategia riceve la tabella prezzi e restituisce i "pesi obiettivo":
una tabella con le stesse date, una colonna per ETF e valori tra 0 e 1
(quota del capitale da tenere in quell'ETF; il resto resta in contanti).
Le righe vuote (NaN) significano "non fare nulla quel giorno".

Le decisioni usano solo i prezzi di chiusura fino al giorno stesso;
il motore le esegue il giorno di borsa successivo (niente "sbirciate al futuro").
"""

import numpy as np
import pandas as pd


def _empty(prices: pd.DataFrame, columns) -> pd.DataFrame:
    return pd.DataFrame(np.nan, index=prices.index, columns=list(columns))


def _month_ends(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(index.to_period("M")).last().values)


def _position(prices: pd.DataFrame, asset: str, invested: pd.Series, out: str | None) -> pd.DataFrame:
    """Converte un segnale dentro/fuori (True/False/NaN) in pesi, solo nei giorni in cui cambia.

    Quando si è "fuori", il capitale va nell'ETF `out` (liquidità remunerata) se esiste
    già in quella data, altrimenti resta in contanti.
    """
    cols = [asset] + ([out] if out else [])
    w = _empty(prices, cols)
    sig = invested.dropna()
    changes = sig[sig != sig.shift()]
    for date, inside in changes.items():
        row = {c: 0.0 for c in cols}
        if inside:
            row[asset] = 1.0
        elif out and not np.isnan(prices.at[date, out]):
            row[out] = 1.0
        w.loc[date] = row
    return w


def buy_and_hold(prices: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    """Compra il primo giorno disponibile e non tocca più nulla. È il benchmark."""
    w = _empty(prices, weights)
    first = prices[list(weights)].dropna().index[0]
    w.loc[first] = weights
    return w


def periodic_rebalance(prices: pd.DataFrame, weights: dict[str, float], freq: str = "YE") -> pd.DataFrame:
    """Portafoglio fisso (es. 60% azioni / 40% obbligazioni) riportato ai pesi iniziali
    a ogni fine periodo (YE = fine anno, QE = fine trimestre)."""
    w = _empty(prices, weights)
    avail = prices[list(weights)].dropna()
    dates = avail.groupby(avail.index.to_period(freq[0])).tail(1).index
    w.loc[avail.index[0]] = weights
    for d in dates[:-1]:
        w.loc[d] = weights
    return w


def sma_crossover(prices: pd.DataFrame, asset: str, fast: int = 50, slow: int = 200,
                  out: str | None = None) -> pd.DataFrame:
    """Incrocio medie mobili: investiti quando la media a `fast` giorni è sopra quella a `slow`."""
    p = prices[asset]
    sma_fast = p.rolling(fast).mean()
    sma_slow = p.rolling(slow).mean()
    invested = (sma_fast > sma_slow).where(sma_slow.notna())
    return _position(prices, asset, invested, out)


def crash_filter(prices: pd.DataFrame, asset: str, sma: int = 200, band: float = 0.10,
                 out: str | None = None) -> pd.DataFrame:
    """Uscita solo nei crolli: controllo a fine mese; si esce quando il prezzo è più del
    `band` (es. 10%) sotto la media mobile a `sma` giorni, si rientra quando torna sopra
    la media. Pensata per vendere raramente: ogni vendita in guadagno costa il 26%."""
    p = prices[asset]
    avg = p.rolling(sma).mean()
    state = pd.Series(np.nan, index=prices.index)
    inside = True
    for d in _month_ends(prices.index):
        if np.isnan(avg[d]):
            continue
        if inside and p[d] < avg[d] * (1 - band):
            inside = False
        elif not inside and p[d] > avg[d]:
            inside = True
        state[d] = float(inside)
    return _position(prices, asset, state.ffill(), out)


def _total_return(prices: pd.DataFrame, col: str, lookback: int) -> pd.Series:
    return prices[col] / prices[col].shift(lookback) - 1


def time_series_momentum(prices: pd.DataFrame, asset: str, lookback: int = 252,
                         out: str | None = None) -> pd.DataFrame:
    """Momentum: a fine mese, investiti se il rendimento degli ultimi 12 mesi è positivo
    (più precisamente: superiore a quello della liquidità, se disponibile)."""
    r = _total_return(prices, asset, lookback)
    hurdle = _total_return(prices, out, lookback).fillna(0) if out else 0
    invested = (r > hurdle).where(r.notna())
    month_end = invested.index.isin(_month_ends(prices.index))
    invested = invested.where(month_end).ffill()
    return _position(prices, asset, invested, out)


def dual_momentum(prices: pd.DataFrame, risky: list[str], safe: str, cash: str | None = None,
                  lookback: int = 252) -> pd.DataFrame:
    """Dual momentum (Antonacci), controllato a fine mese:
    1. momentum relativo: tra gli azionari scegli quello salito di più negli ultimi 12 mesi;
    2. momentum assoluto: se ha fatto meglio della liquidità tienilo, altrimenti
       passa all'obbligazionario `safe`.
    """
    cols = list(risky) + [safe]
    w = _empty(prices, cols)
    rets = pd.DataFrame({c: _total_return(prices, c, lookback) for c in cols})
    hurdle = _total_return(prices, cash, lookback) if cash else pd.Series(0.0, index=prices.index)
    current = None
    for d in _month_ends(prices.index):
        r = rets.loc[d, risky]
        if r.isna().any() or np.isnan(prices.at[d, safe]):
            continue
        best = r.idxmax()
        h = hurdle.get(d, 0.0)
        choice = best if r[best] > (0.0 if np.isnan(h) else h) else safe
        if choice != current:
            w.loc[d] = {c: float(c == choice) for c in cols}
            current = choice
    return w


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (metodo di Wilder): 0-100, sotto 30 = "ipervenduto"."""
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, min_periods=period).mean()
    return 100 - 100 / (1 + gain / loss)


def rsi_mean_reversion(prices: pd.DataFrame, asset: str, period: int = 14, low: float = 30,
                       high: float = 70, out: str | None = None) -> pd.DataFrame:
    """Mean reversion: compra quando l'RSI scende sotto `low` (prezzo "sceso troppo"),
    vendi quando sale sopra `high`."""
    r = rsi(prices[asset], period)
    state = pd.Series(np.nan, index=prices.index)
    inside = False
    for d, v in r.dropna().items():
        if not inside and v < low:
            inside = True
        elif inside and v > high:
            inside = False
        state[d] = float(inside)
    return _position(prices, asset, state, out)
