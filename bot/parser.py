"""Interpreta mensajes de senales de trading (ES/EN) y los convierte en Signal."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NUM = r"(\d[\d.,]*)"


@dataclass
class Signal:
    symbol: str  # formato ccxt, ej: BTC/USDT:USDT
    side: str  # "buy" (long) o "sell" (short)
    entry: float | None  # None = entrar a mercado
    stop_loss: float | None
    take_profits: list[float] = field(default_factory=list)
    leverage: int | None = None


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


def parse_signal(text: str, quote: str = "USDT") -> Signal | None:
    """Devuelve Signal o None si el texto no parece una senal valida."""
    t = text.replace(" ", " ")

    # Direccion
    long_m = re.search(r"\b(long|buy|compra|comprar)\b", t, re.I)
    short_m = re.search(r"\b(short|sell|venta|vender)\b", t, re.I)
    if bool(long_m) == bool(short_m):
        return None  # ninguna o ambiguas
    side = "buy" if long_m else "sell"

    # Simbolo: #BTCUSDT, BTC/USDT, BTC-USDT, $BTC
    sym = None
    m = re.search(rf"[#$]?\b([A-Z0-9]{{2,10}})\s*[/\-_]?\s*{quote}\b", t, re.I)
    if m:
        sym = m.group(1).upper()
    else:
        m = re.search(r"[#$]([A-Z][A-Z0-9]{1,9})\b", t)
        if m:
            sym = m.group(1).upper()
    if not sym or sym in {"LONG", "SHORT", "BUY", "SELL"}:
        return None
    symbol = f"{sym}/{quote}:{quote}"

    entry = None
    em = re.search(
        rf"(?:entry|entrada|enter|entrar|precio)[^\d\n]{{0,25}}{NUM}", t, re.I
    )
    if em and not re.search(r"market|mercado", em.group(0), re.I):
        entry = _num(em.group(1))

    sl_raw = _find(rf"(?:stop[\s-]*loss|\bsl\b|stop)[^\d\n]{{0,15}}{NUM}", t)
    sl = _num(sl_raw) if sl_raw else None

    tps: list[float] = []
    for m in re.finditer(
        rf"(?:take[\s-]*profit|\btp\s*\d*|target|objetivo)\s*\d*[^\d\n]{{0,12}}{NUM}",
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

    sig = Signal(symbol, side, entry, sl, tps, leverage)
    return sig if validate(sig) else None


def validate(s: Signal) -> bool:
    """Coherencia basica: SL y TPs del lado correcto respecto a la entrada."""
    ref = s.entry
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
