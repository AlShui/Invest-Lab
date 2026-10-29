"""Parametri del test. Tutto ciò che si può voler cambiare sta qui."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Universe:
    """Un insieme di strumenti su cui fare il test, con il "ruolo" di ciascuno."""

    key: str
    description: str
    tickers: dict[str, str]  # ticker -> descrizione
    main: str  # azionario principale: strategie su un solo strumento e benchmark
    main_label: str
    us: str  # azionario USA e Europa: per il dual momentum
    eu: str
    bonds: str
    cash: str  # "parcheggio" quando una strategia esce dal mercato
    split_date: str  # fine in-sample / inizio out-of-sample
    first_wf_year: int  # primo anno di verifica nel walk-forward
    price_source: dict[str, str] = field(default_factory=dict)  # ticker -> da dove leggere i prezzi
    adjusted: bool = False  # True = prezzi rettificati per i dividendi (fondi a distribuzione)
    cash_from_yield: str | None = None  # costruisce `cash` dal rendimento di un titolo di Stato


# --- ETF UCITS su Borsa Italiana, ad accumulazione: quelli che si possono comprare davvero.
# Ad accumulazione: i dividendi sono reinvestiti nel prezzo, quindi il prezzo di
# chiusura è già un "total return" e non ci sono cedole da tassare a parte.
UCITS = Universe(
    key="ucits",
    description="ETF UCITS su Borsa Italiana (2009-oggi)",
    tickers={
        "SWDA.MI": "iShares Core MSCI World (azionario globale)",
        "CSSPX.MI": "iShares Core S&P 500 (azionario USA)",
        "SMEA.MI": "iShares Core MSCI Europe (azionario Europa)",
        "XGLE.MI": "Xtrackers Eurozone Government Bond (obbligazionario)",
        "XEON.MI": "Xtrackers EUR Overnight Rate Swap (liquidità remunerata)",
    },
    main="SWDA.MI", main_label="SWDA", us="CSSPX.MI", eu="SMEA.MI", bonds="XGLE.MI", cash="XEON.MI",
    split_date="2019-01-01", first_wf_year=2016,
    # Alcuni ETF a Milano nei primi anni erano poco scambiati (es. SWDA.MI nel 2011-2012:
    # prezzo fermo in ~metà dei giorni), quindi per lo storico usiamo la quotazione più
    # liquida dello STESSO fondo (stesso ISIN, sempre in EUR).
    price_source={
        "SWDA.MI": "EUNL.DE",  # Xetra, IE00B4L5Y983
        "SMEA.MI": "IMAE.AS",  # Euronext Amsterdam, IE00B4K48X80
    },
)

# --- Storico lungo USA (1980-oggi), solo per studio: fondi indicizzati Vanguard, in USD.
# Non acquistabili da un investitore italiano, ma coprono crolli che lo storico UCITS
# non ha (1987, 2000-2003, 2008). Costi e tasse restano quelli italiani, come se
# esistessero ETF equivalenti; gli importi sono in USD.
USA_LONG = Universe(
    key="usa",
    description="Fondi indicizzati USA, storico lungo (1980-oggi, solo studio)",
    tickers={
        "VFINX": "Vanguard 500 Index (S&P 500)",
        "VEURX": "Vanguard European Stock Index (azionario Europa)",
        "VBMFX": "Vanguard Total Bond Market Index (obbligazionario USA)",
        "TBILL": "Titoli di Stato USA a 3 mesi (indice costruito dal rendimento ^IRX)",
    },
    main="VFINX", main_label="S&P 500", us="VFINX", eu="VEURX", bonds="VBMFX", cash="TBILL",
    split_date="2003-01-01", first_wf_year=1990,
    adjusted=True, cash_from_yield="^IRX",
)

UNIVERSES = {u.key: u for u in (UCITS, USA_LONG)}


@dataclass
class Costs:
    """Commissioni Fineco (mercato italiano): 0,19% dell'ordine, min 2,95 €, max 19 €."""

    commission_pct: float = 0.0019
    commission_min: float = 2.95
    commission_max: float = 19.0
    spread_pct: float = 0.001  # differenza denaro/lettera: paghi metà in acquisto e metà in vendita
    min_order_eur: float = 200.0  # sotto questa cifra l'ordine non viene eseguito (non conviene)

    def commission(self, order_value: float) -> float:
        if order_value <= 0:
            return 0.0
        return min(max(order_value * self.commission_pct, self.commission_min), self.commission_max)


@dataclass
class Taxes:
    """Fiscalità italiana, regime amministrato.

    - Plusvalenze da ETF armonizzati: 26%, trattenute dal broker alla vendita
      (sono "redditi di capitale").
    - Minusvalenze da ETF: sono "redditi diversi" e NON compensano plusvalenze da ETF.
      Finiscono nello "zainetto fiscale" (4 anni) e servono solo contro plusvalenze
      di azioni/ETC/certificati. Con un portafoglio di soli ETF vanno di fatto perse.
    - Imposta di bollo: 0,2% annuo sul controvalore del deposito titoli.
    Semplificazione: gli ETF obbligazionari su titoli di Stato avrebbero una quota
    tassata al 12,5%; qui applichiamo il 26% a tutto (scelta prudente).
    """

    capital_gain_rate: float = 0.26
    etf_losses_offset_gains: bool = False  # True = scenario ipotetico (non realistico per ETF)
    stamp_duty_pct: float = 0.002


@dataclass
class Settings:
    initial_capital: float = 10_000.0
    monthly_contribution: float = 0.0  # versamento mensile (PAC); 0 = solo capitale iniziale
    costs: Costs = field(default_factory=Costs)
    taxes: Taxes = field(default_factory=Taxes)


def no_frictions(monthly_contribution: float = 0.0) -> Settings:
    """Stesso test ma senza commissioni, spread, tasse e bollo: serve a vedere quanto costano."""
    return Settings(
        monthly_contribution=monthly_contribution,
        costs=Costs(commission_pct=0, commission_min=0, commission_max=0, spread_pct=0, min_order_eur=0),
        taxes=Taxes(capital_gain_rate=0, stamp_duty_pct=0),
    )
