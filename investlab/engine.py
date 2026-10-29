"""Motore di backtest giornaliero con costi e fiscalità italiana.

Come funziona, in breve:
- la strategia decide a fine giornata (prezzi di chiusura);
- l'ordine viene eseguito alla chiusura del giorno di borsa successivo;
- ogni ordine paga commissione Fineco + metà spread;
- ogni vendita in guadagno paga subito il 26% (regime amministrato), calcolato
  sul costo medio ponderato di carico come fa il broker;
- le vendite in perdita generano minusvalenze che, per gli ETF, non compensano
  le plusvalenze di altri ETF (vedi config.Taxes);
- a fine anno si paga il bollo dello 0,2% sul controvalore dei titoli;
- se previsto un versamento mensile (PAC), il primo giorno di borsa di ogni mese
  arriva nuova liquidità che viene investita secondo i pesi in vigore;
- alla fine del periodo si simula la vendita di tutto ("liquidazione"), così che
  anche il buy & hold paghi le sue tasse e il confronto sia alla pari.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import Settings


@dataclass
class Result:
    name: str
    equity: pd.Series  # valore giornaliero del conto (titoli ai prezzi di mercato + contanti)
    final_net: float  # quanto resta in tasca vendendo tutto all'ultimo giorno, dopo costi e tasse
    initial_capital: float
    orders: int = 0
    commissions: float = 0.0
    spread_cost: float = 0.0
    taxes: float = 0.0
    stamp_duty: float = 0.0
    unused_losses: float = 0.0  # minusvalenze rimaste nello zainetto senza essere usate
    trades: list = field(default_factory=list)
    contributions: pd.Series | None = None  # versamenti giornalieri (0 nei giorni senza versamento)

    @property
    def total_invested(self) -> float:
        """Capitale iniziale + tutti i versamenti successivi."""
        extra = 0.0 if self.contributions is None else float(self.contributions.sum())
        return self.initial_capital + extra


class _Account:
    def __init__(self, settings: Settings):
        self.s = settings
        self.cash = settings.initial_capital
        self.qty: dict[str, float] = {}
        self.avg_cost: dict[str, float] = {}  # costo medio di carico per quota, commissioni incluse
        self.loss_bank: list[list] = []  # [anno di realizzo, importo residuo]
        self.orders = 0
        self.commissions = 0.0
        self.spread_cost = 0.0
        self.taxes = 0.0
        self.stamp_duty = 0.0
        self.trades: list[dict] = []

    def holdings_value(self, px: pd.Series) -> float:
        return sum(q * px[t] for t, q in self.qty.items() if q > 0)

    # --- fiscalità ---------------------------------------------------------
    def _tax_on_gain(self, gain: float, year: int) -> float:
        tx = self.s.taxes
        if gain < 0:
            self.loss_bank.append([year, -gain])
            return 0.0
        taxable = gain
        if tx.etf_losses_offset_gains:
            for lot in self.loss_bank:
                if lot[0] + 4 < year or lot[1] <= 0:
                    continue  # scaduta (vale 4 anni dopo quello di realizzo) o esaurita
                used = min(lot[1], taxable)
                lot[1] -= used
                taxable -= used
        return taxable * tx.capital_gain_rate

    # --- ordini ------------------------------------------------------------
    def sell(self, date, ticker: str, qty: float, price: float):
        half_spread = self.s.costs.spread_pct / 2
        gross = qty * price * (1 - half_spread)
        comm = self.s.costs.commission(gross)
        proceeds = gross - comm
        gain = proceeds - qty * self.avg_cost[ticker]
        tax = self._tax_on_gain(gain, date.year)
        self.cash += proceeds - tax
        self.qty[ticker] -= qty
        if self.qty[ticker] <= 1e-9:
            self.qty[ticker] = 0.0
        self.orders += 1
        self.commissions += comm
        self.spread_cost += qty * price * half_spread
        self.taxes += tax
        self.trades.append(dict(date=date, ticker=ticker, side="VENDI", qty=qty, price=price,
                                value=gross, commission=comm, gain=gain, tax=tax))

    def buy(self, date, ticker: str, budget: float, price: float):
        half_spread = self.s.costs.spread_pct / 2
        comm = self.s.costs.commission(budget)
        invest = budget - comm
        if invest <= 0:
            return
        exec_price = price * (1 + half_spread)
        qty = invest / exec_price
        old_q = self.qty.get(ticker, 0.0)
        old_cost = old_q * self.avg_cost.get(ticker, 0.0)
        self.qty[ticker] = old_q + qty
        self.avg_cost[ticker] = (old_cost + budget) / self.qty[ticker]
        self.cash -= budget
        self.orders += 1
        self.commissions += comm
        self.spread_cost += qty * price * half_spread
        self.trades.append(dict(date=date, ticker=ticker, side="COMPRA", qty=qty, price=price,
                                value=invest, commission=comm, gain=np.nan, tax=0.0))

    def rebalance(self, date, target: pd.Series, px: pd.Series):
        """Porta il portafoglio ai pesi obiettivo. Prima le vendite, poi gli acquisti."""
        min_order = self.s.costs.min_order_eur
        equity = self.cash + self.holdings_value(px)
        tickers = set(target.index) | {t for t, q in self.qty.items() if q > 0}
        diffs = {}
        for t in tickers:
            if np.isnan(px.get(t, np.nan)):
                continue  # ETF non ancora quotato: non si tocca
            w = target.get(t, 0.0)
            w = 0.0 if np.isnan(w) else w
            diffs[t] = w * equity - self.qty.get(t, 0.0) * px[t]

        for t, d in diffs.items():
            held = self.qty.get(t, 0.0)
            if d < 0 and held > 0:
                if target.get(t, 0.0) == 0 or np.isnan(target.get(t, 0.0)):
                    self.sell(date, t, held, px[t])  # uscita completa
                elif -d >= min_order:
                    self.sell(date, t, min(held, -d / px[t]), px[t])

        for t, d in sorted(diffs.items(), key=lambda kv: -kv[1]):
            budget = min(d, self.cash)
            if d > 0 and budget >= max(min_order, 1.0):
                self.buy(date, t, budget, px[t])

    def invest_cash(self, date, target: pd.Series, px: dict, mode: str):
        """Investe la liquidità disponibile (es. un versamento) senza vendere nulla.

        - "pro_rata": divide la liquidità secondo i pesi obiettivo (es. 60% / 40%);
        - "fill_gaps": compra solo ciò che è sotto il peso obiettivo, partendo dal più
          sottopesato. È il "ribilanciamento coi versamenti": riavvicina i pesi senza
          vendere, quindi senza pagare tasse.
        Gli importi sotto l'ordine minimo restano in contanti e si sommano al mese dopo.
        """
        min_order = max(self.s.costs.min_order_eur, 1.0)
        weights = {t: float(w) for t, w in target.items()
                   if not np.isnan(w) and w > 0 and not np.isnan(px.get(t, np.nan))}
        if not weights or self.cash < min_order:
            return
        if mode == "pro_rata":
            total_w = sum(weights.values())
            cash = self.cash
            for t, w in weights.items():
                budget = cash * w / total_w
                if budget >= min_order:
                    self.buy(date, t, budget, px[t])
        elif mode == "fill_gaps":
            equity = self.cash + self.holdings_value(px)
            gaps = {t: w * equity - self.qty.get(t, 0.0) * px[t] for t, w in weights.items()}
            for t, gap in sorted(gaps.items(), key=lambda kv: -kv[1]):
                budget = min(gap, self.cash)
                if budget >= min_order:
                    self.buy(date, t, budget, px[t])
        else:
            raise ValueError(f"modalità di investimento sconosciuta: {mode}")

    def liquidate(self, date, px: pd.Series):
        """Vende tutto: serve a misurare quanto resta davvero in tasca a fine periodo."""
        for t, q in list(self.qty.items()):
            if q > 0:
                self.sell(date, t, q, px[t])


def run(prices: pd.DataFrame, targets: pd.DataFrame, settings: Settings, name: str = "",
        start=None, end=None, contribution_mode: str = "pro_rata") -> Result:
    """Simula la strategia (pesi obiettivo `targets`) tra `start` ed `end`.

    `contribution_mode` dice come investire i versamenti mensili nei giorni in cui la
    strategia non ribilancia (vedi _Account.invest_cash).
    """
    # Decisione a fine giornata t -> esecuzione alla chiusura del giorno t+1.
    exec_targets = targets.shift(1)
    state = exec_targets.ffill()  # posizione "in vigore" in ogni giorno
    px_all = prices.ffill()

    window = px_all.loc[start:end].index
    window = window[state.loc[window].notna().any(axis=1).values]  # parte quando la strategia è pronta
    if len(window) == 0:
        raise ValueError(f"{name}: nessun dato nel periodo richiesto")

    acct = _Account(settings)
    # ultimo giorno di borsa di ogni anno (escluso l'ultimo giorno del periodo): si paga il bollo
    is_year_end = np.append(window.year[1:] != window.year[:-1], False)
    has_action = exec_targets.loc[window].notna().any(axis=1).to_numpy()
    # dizionari al posto delle righe pandas: il ciclo giornaliero è molto più veloce
    px_rows = px_all.loc[window].to_dict("index")
    equity = np.empty(len(window))
    # versamento il primo giorno di borsa di ogni mese (non il primo giorno: lì c'è il capitale iniziale)
    flows = np.zeros(len(window))
    if settings.monthly_contribution > 0:
        new_month = np.append(False, window.month[1:] != window.month[:-1])
        flows[new_month] = settings.monthly_contribution

    for i, d in enumerate(window):
        px = px_rows[d]
        acct.cash += flows[i]
        if i == 0:
            acct.rebalance(d, state.loc[d], px)  # entra con la posizione in vigore all'inizio
        elif has_action[i]:
            acct.rebalance(d, exec_targets.loc[d], px)
        elif flows[i] > 0:
            acct.invest_cash(d, state.loc[d], px, contribution_mode)
        if is_year_end[i]:
            duty = acct.holdings_value(px) * settings.taxes.stamp_duty_pct
            acct.cash -= duty
            acct.stamp_duty += duty
        equity[i] = acct.cash + acct.holdings_value(px)

    equity = pd.Series(equity, index=window)
    orders = acct.orders  # gli ordini di liquidazione finale non contano come operazioni
    acct.liquidate(window[-1], px_rows[window[-1]])
    unused = sum(lot[1] for lot in acct.loss_bank)
    return Result(
        name=name, equity=equity, final_net=acct.cash, initial_capital=settings.initial_capital,
        orders=orders, commissions=acct.commissions, spread_cost=acct.spread_cost,
        taxes=acct.taxes, stamp_duty=acct.stamp_duty, unused_losses=unused, trades=acct.trades,
        contributions=pd.Series(flows, index=window),
    )
