"""Ejecucion de ordenes con ccxt, dimensionando por riesgo."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import ccxt

from .parser import Signal

log = logging.getLogger("trader")


@dataclass
class Config:
    exchange: str
    api_key: str
    api_secret: str
    sandbox: bool
    dry_run: bool
    risk_pct: float
    max_leverage: int
    max_open_trades: int
    max_slippage_pct: float
    default_sl_pct: float


class Trader:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        ex_class = getattr(ccxt, cfg.exchange)
        self.ex = ex_class(
            {
                "apiKey": cfg.api_key,
                "secret": cfg.api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "swap"},
            }
        )
        if cfg.sandbox:
            self.ex.set_sandbox_mode(True)
        self.ex.load_markets()

    # ---------- helpers ----------
    def _balance(self) -> float:
        return float(self.ex.fetch_balance()["USDT"]["free"])

    def _open_positions(self) -> int:
        return len([p for p in self.ex.fetch_positions() if float(p.get("contracts") or 0) > 0])

    def _record(self, data: dict) -> None:
        data["ts"] = int(time.time())
        with open("trades.jsonl", "a") as f:
            f.write(json.dumps(data) + "\n")

    # ---------- ejecucion ----------
    def execute(self, s: Signal) -> dict | None:
        c = self.cfg
        quote = "USDT" if s.symbol.endswith("USDT") else "USDC" if s.symbol.endswith("USDC") else None
        if not quote:
            log.warning("%s no es un par cripto; usa BROKER=mt5 para forex/indices", s.symbol)
            return None
        s.symbol = f"{s.symbol[:-len(quote)]}/{quote}:{quote}"
        if s.symbol not in self.ex.markets:
            log.warning("Simbolo no disponible en el exchange: %s", s.symbol)
            return None

        price = float(self.ex.fetch_ticker(s.symbol)["last"])
        entry = s.entry or price
        if s.entry and abs(price - s.entry) / s.entry * 100 > c.max_slippage_pct:
            log.warning("Precio %.6f muy lejos de entrada %.6f; senal descartada", price, s.entry)
            return None

        sl = s.stop_loss
        if sl is None:
            if c.default_sl_pct <= 0:
                log.warning("Senal sin Stop Loss; rechazada por seguridad")
                return None
            d = entry * c.default_sl_pct / 100
            sl = entry - d if s.side == "buy" else entry + d
        if (s.side == "buy" and sl >= entry) or (s.side == "sell" and sl <= entry):
            log.warning("Stop Loss incoherente con la direccion; rechazada")
            return None

        if not c.dry_run and self._open_positions() >= c.max_open_trades:
            log.warning("Maximo de operaciones abiertas alcanzado")
            return None

        balance = 1000.0 if c.dry_run else self._balance()
        risk_amount = balance * c.risk_pct / 100
        qty = risk_amount / abs(entry - sl)
        lev = min(s.leverage or c.max_leverage, c.max_leverage)
        # no exceder el margen disponible con el apalancamiento elegido
        qty = min(qty, balance * lev / entry)
        qty = float(self.ex.amount_to_precision(s.symbol, qty))
        if qty <= 0:
            log.warning("Cantidad calculada = 0; rechazada")
            return None

        plan = {
            "symbol": s.symbol, "side": s.side, "qty": qty, "entry": entry,
            "sl": sl, "tps": s.take_profits, "leverage": lev, "dry_run": c.dry_run,
        }
        log.info("Plan: %s", plan)
        if c.dry_run:
            self._record(plan)
            return plan

        close = "sell" if s.side == "buy" else "buy"
        try:
            self.ex.set_leverage(lev, s.symbol)
        except Exception as e:  # algunos exchanges ya lo tienen fijado
            log.warning("No se pudo fijar apalancamiento: %s", e)

        if s.entry and abs(price - s.entry) / s.entry * 100 > 0.05:
            order = self.ex.create_order(s.symbol, "limit", s.side, qty, s.entry)
        else:
            order = self.ex.create_order(s.symbol, "market", s.side, qty)

        # Stop Loss (reduceOnly) siempre
        self.ex.create_order(
            s.symbol, "STOP_MARKET", close, qty, None,
            {"stopPrice": float(self.ex.price_to_precision(s.symbol, sl)), "reduceOnly": True},
        )

        # Take profits repartidos en partes iguales
        if s.take_profits:
            n = len(s.take_profits)
            part = float(self.ex.amount_to_precision(s.symbol, qty / n))
            for tp in s.take_profits:
                self.ex.create_order(
                    s.symbol, "limit", close, part,
                    float(self.ex.price_to_precision(s.symbol, tp)), {"reduceOnly": True},
                )
        plan["order_id"] = order.get("id")
        self._record(plan)
        return plan
