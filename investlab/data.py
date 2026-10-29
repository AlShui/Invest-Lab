"""Download e cache dei prezzi giornalieri da Yahoo Finance."""

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from .config import Universe

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _cache_path(ticker: str, adjusted: bool) -> Path:
    return DATA_DIR / f"{ticker.replace('.', '_')}{'_tr' if adjusted else ''}.csv"


def download(ticker: str, refresh: bool = False, adjusted: bool = False) -> pd.Series:
    """Chiusura giornaliera. Usa la cache su disco se presente.

    `adjusted=True` restituisce i prezzi rettificati per i dividendi ("total return"),
    necessari per i fondi a distribuzione.
    """
    path = _cache_path(ticker, adjusted)
    if path.exists() and not refresh:
        s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
    else:
        # Ticker.history invece di yf.download: quest'ultimo a volte si blocca
        df = yf.Ticker(ticker).history(period="max", auto_adjust=adjusted)
        if df.empty:
            raise RuntimeError(f"Nessun dato per {ticker}")
        s = df["Close"]
        s.index = s.index.tz_localize(None).normalize()
        DATA_DIR.mkdir(exist_ok=True)
        s.rename(ticker).to_csv(path)
    s = s.rename(ticker)
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.dropna()


def yield_to_index(annual_yield_pct: pd.Series) -> pd.Series:
    """Trasforma un rendimento annuo (es. T-bill 3 mesi, in %) in un "prezzo" che cresce
    giorno per giorno come un conto remunerato a quel tasso. Parte da 100."""
    y = annual_yield_pct.clip(lower=0) / 100
    days = y.index.to_series().diff().dt.days.fillna(0).to_numpy()
    growth = (1 + y.shift(1).fillna(0).to_numpy()) ** (days / 365)
    return pd.Series(100 * np.cumprod(growth), index=y.index)


def check_quality(s: pd.Series, max_daily_move: float = 0.12, max_flat_days: int = 5) -> list[str]:
    """Segnala problemi tipici dei dati gratuiti: salti giornalieri anomali e prezzi
    fermi per molti giorni di fila (titolo poco scambiato)."""
    issues = []
    ret = s.pct_change().dropna()
    for d, r in ret[ret.abs() > max_daily_move].items():
        issues.append(f"{s.name} {d.date()}: salto {r:+.1%}")
    flat = s.diff().eq(0)
    run_id = (~flat).cumsum()
    runs = flat.groupby(run_id).sum()
    for rid, n in runs[runs >= max_flat_days].items():
        first = flat[run_id == rid].index[1]  # [0] è l'ultimo giorno con prezzo diverso
        issues.append(f"{s.name} dal {first.date()}: prezzo fermo per {n} giorni")
    return issues


def load_prices(u: Universe, refresh: bool = False) -> pd.DataFrame:
    """Tabella prezzi dell'universo `u` (righe = giorni, colonne = ticker).

    I buchi di pochi giorni (festività diverse) sono riempiti con l'ultimo prezzo noto;
    prima dell'inizio quotazione resta NaN.
    """
    series = []
    for t in u.tickers:
        if t == u.cash and u.cash_from_yield:
            s = yield_to_index(download(u.cash_from_yield, refresh))
        else:
            s = download(u.price_source.get(t, t), refresh, u.adjusted)
            s = s[s > 0]
        series.append(s.rename(t))
    prices = pd.concat(series, axis=1).sort_index()
    if u.cash_from_yield:
        # l'indice T-bill esiste da molto prima: lo si tiene solo dove c'è almeno un altro strumento
        prices = prices[prices.drop(columns=u.cash).notna().any(axis=1)]
    return prices.ffill(limit=5)
