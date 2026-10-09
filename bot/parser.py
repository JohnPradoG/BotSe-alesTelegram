"""Interpreta mensajes de senales de trading (ES/EN) y los convierte en Signal.

Soporta forex (EURUSD, GBP/JPY), metales (XAUUSD), indices (US30, NAS100),
alias en lenguaje libre (bot/aliases.json) y cripto (#BTCUSDT).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

NUM = r"(\d[\d.,]*)"

CURRENCIES = {
    "EUR", "USD", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "SEK", "NOK", "DKK",
    "MXN", "ZAR", "TRY", "PLN", "HKD", "SGD", "CNH", "XAU", "XAG",
}
INDEXES = {"US30", "US100", "US500", "NAS100", "SPX500", "GER40", "DE40", "UK100",
           "JP225", "USTEC", "DJ30", "USOIL", "UKOIL"}
_ALIASES: dict[str, str] | None = None


def load_aliases() -> dict[str, str]:
    """Carga aliases.json (editable) en minusculas, mas los de usuario en ALIASES_FILE."""
    global _ALIASES
    if _ALIASES is None:
        _ALIASES = {k.lower(): v.upper() for k, v in
                    json.loads((Path(__file__).parent / "aliases.json").read_text("utf-8")).items()}
    return _ALIASES


@dataclass
class Signal:
    symbol: str  # canonico: EURUSD, XAUUSD, NAS100, BTCUSDT ...
    side: str  # "buy" (long) o "sell" (short)
    entry: float | None  # None = entrar a mercado
    stop_loss: float | None
    take_profits: list[float] = field(default_factory=list)
    leverage: int | None = None
    ref_price: float | None = None  # precio "actual" citado en la senal (solo referencia)


def _num(s: str) -> float:
    s = s.strip().rstrip(".,")
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def _find(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.I)
    return m.group(1) if m else None


def detect_symbol(text: str) -> str | None:
    low = text.lower()
    # 1) alias en lenguaje libre (palabra completa)
    for alias, sym in sorted(load_aliases().items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low):
            return sym
    up = text.upper()
    # 2) indices / materias primas
    for m in re.finditer(r"[A-Z0-9]{4,6}", up):
        if m.group(0) in INDEXES:
            return m.group(0)
    # 3) par de divisas EURUSD, EUR/USD, EUR-USD, EUR USD
    for m in re.finditer(r"(?=(?<![A-Z])([A-Z]{3})\s?[/\-_ ]?\s?([A-Z]{3})(?![A-Z]))", up):
        a, b = m.groups()
        if a in CURRENCIES and b in CURRENCIES and a != b:
            return a + b
    # 4) cripto contra USDT / USDC: #BTCUSDT, BTC/USDT
    m = re.search(r"(?<![A-Z0-9])([A-Z0-9]{2,10})\s?[/\-_]?\s?(USDT|USDC)(?![A-Z])", up)
    if m:
        return m.group(1) + m.group(2)
    return None


def parse_signal(text: str) -> Signal | None:
    """Devuelve Signal o None si el texto no parece una senal valida."""
    t = text.replace(" ", " ")

    long_m = re.search(r"\b(long|buy|compra|comprar)\b", t, re.I)
    short_m = re.search(r"\b(short|sell|venta|vender)\b", t, re.I)
    if bool(long_m) == bool(short_m):
        return None  # ninguna o ambiguas
    side = "buy" if long_m else "sell"

    symbol = detect_symbol(t)
    if not symbol:
        return None

    entry = None
    ref_price = None
    cm = re.search(
        rf"(?:current[\s-]*price|precio[\s-]*actual|actual[\s-]*price|now|ahora)[^\d\n]{{0,15}}{NUM}",
        t, re.I,
    )
    if cm:
        ref_price = _num(cm.group(1))
    em = None if cm else re.search(
        rf"(?:entry|entrada|enter|entrar|precio|price|@)[^\d\n]{{0,25}}{NUM}", t, re.I
    )
    if em and not re.search(r"market|mercado", em.group(0), re.I):
        entry = _num(em.group(1))

    sl_raw = _find(rf"(?:stop[\s-]*loss|\bsl\b|stop)[^\d\n]{{0,15}}{NUM}", t)
    sl = _num(sl_raw) if sl_raw else None

    tps: list[float] = []
    for m in re.finditer(
        rf"(?:take[\s-]*profit|\btp|target|objetivo)\s*(?:\d(?![\d.,]))?[^\d\n]{{0,12}}{NUM}",
        t,
        re.I,
    ):
        v = _num(m.group(1))
        if v not in tps:
            tps.append(v)

    lev_raw = _find(r"(?:leverage|apalancamiento|lev)[^\d\n]{0,10}(\d+)\s*x?", t) or _find(
        r"\b(\d{1,3})\s*x\b", t
    )
    leverage = int(lev_raw) if lev_raw else None

    sig = Signal(symbol, side, entry, sl, tps, leverage, ref_price)
    return sig if validate(sig) else None


def parse_signals(text: str) -> list[Signal]:
    """Un mensaje puede traer varias senales (cada una empieza por 'Pair:')."""
    chunks = re.split(r"(?im)^(?=\s*(?:pair|par)\s*:)", text)
    chunks = [c for c in chunks if re.match(r"(?i)\s*(?:pair|par)\s*:", c)]
    if not chunks:
        chunks = [text]
    sigs = [parse_signal(c) for c in chunks]
    return [x for x in sigs if x]


def validate(s: Signal) -> bool:
    """Coherencia basica: SL y TPs del lado correcto respecto a la entrada."""
    ref = s.entry if s.entry is not None else s.ref_price
    if ref is None:
        return True  # se valida contra precio de mercado al ejecutar
    if s.stop_loss is not None:
        if s.side == "buy" and s.stop_loss >= ref:
            return False
        if s.side == "sell" and s.stop_loss <= ref:
            return False
    for tp in s.take_profits:
        if s.side == "buy" and tp <= ref:
            return False
        if s.side == "sell" and tp >= ref:
            return False
    return True
