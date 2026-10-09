"""Ejecucion de ordenes en MetaTrader 5 (forex, metales, indices, etc.).

Requiere Windows con el terminal MT5 instalado y la sesion iniciada (o credenciales).
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass

from .parser import Signal

log = logging.getLogger("mt5")


@dataclass
class MT5Config:
    login: int | None
    password: str
    server: str
    terminal_path: str
    symbol_suffix: str
    dry_run: bool
    risk_pct: float
    max_open_trades: int
    max_slippage_pct: float
    default_sl_pct: float
    deviation: int = 20
    magic: int = 424242


def calc_lots(risk_amount: float, sl_dist: float, tick_size: float, tick_value: float,
              vol_min: float, vol_max: float, vol_step: float) -> float:
    """Lotes para que perder sl_dist (en precio) cueste ~risk_amount. 0 si no alcanza el minimo."""
    if sl_dist <= 0 or tick_size <= 0 or tick_value <= 0:
        return 0.0
    loss_per_lot = sl_dist / tick_size * tick_value
    lots = risk_amount / loss_per_lot
    lots = math.floor(lots / vol_step + 1e-9) * vol_step  # nunca redondear hacia arriba
    lots = min(lots, vol_max)
    if lots < vol_min:
        return 0.0
    return round(lots, 8)


class MT5Trader:
    def __init__(self, cfg: MT5Config):
        import MetaTrader5 as mt5  # solo disponible en Windows

        self.mt5 = mt5
        self.cfg = cfg
        self._connect()

    def _connect(self) -> None:
        mt5, cfg = self.mt5, self.cfg
        kwargs = {}
        if cfg.terminal_path:
            kwargs["path"] = cfg.terminal_path
        if cfg.login:
            kwargs.update(login=cfg.login, password=cfg.password, server=cfg.server)
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"No se pudo iniciar MT5: {mt5.last_error()}")
        log.info("Conectado a MT5: %s", mt5.account_info().server)

    # ---------- helpers ----------
    def _ensure_connected(self) -> None:
        """El terminal puede cerrarse o perder conexion con el broker durante el dia."""
        ti = self.mt5.terminal_info()
        if ti is None or not ti.connected:
            log.warning("MT5 desconectado; reconectando")
            self.mt5.shutdown()
            self._connect()

    def resolve_symbol(self, name: str) -> str | None:
        """Busca el simbolo del broker: exacto, con sufijo configurado o que empiece por el nombre."""
        names = [s.name for s in (self.mt5.symbols_get() or [])]
        for cand in (name, name + self.cfg.symbol_suffix):
            if cand in names:
                return cand
        starts = sorted((n for n in names if n.upper().startswith(name.upper())), key=len)
        return starts[0] if starts else None

    def _record(self, data: dict) -> None:
        data["ts"] = int(time.time())
        with open("trades.jsonl", "a") as f:
            f.write(json.dumps(data) + "\n")

    def _open_count(self) -> int:
        m = self.mt5
        return len(m.positions_get() or []) + len(m.orders_get() or [])

    # ---------- ejecucion ----------
    def execute(self, s: Signal) -> dict | None:
        self._ensure_connected()
        mt5, c = self.mt5, self.cfg
        sym = self.resolve_symbol(s.symbol)
        if not sym:
            log.warning("Simbolo %s no encontrado en el broker", s.symbol)
            return None
        mt5.symbol_select(sym, True)
        info, tick = mt5.symbol_info(sym), mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            log.warning("Sin datos de mercado para %s", sym)
            return None

        price = tick.ask if s.side == "buy" else tick.bid
        entry = s.entry or price
        quoted = s.entry or s.ref_price
        if quoted and abs(price - quoted) / quoted * 100 > c.max_slippage_pct:
            log.warning("Precio %s lejos del precio de la senal %s; descartada", price, quoted)
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
        tps = [tp for tp in s.take_profits
               if (tp > entry if s.side == "buy" else tp < entry)]

        if not c.dry_run and self._open_count() >= c.max_open_trades:
            log.warning("Maximo de operaciones abiertas alcanzado")
            return None

        risk_amount = mt5.account_info().balance * c.risk_pct / 100
        lots = calc_lots(risk_amount, abs(entry - sl), info.trade_tick_size,
                         info.trade_tick_value, info.volume_min, info.volume_max, info.volume_step)
        if lots <= 0:
            log.warning("Lote calculado por debajo del minimo del broker; rechazada")
            return None

        # Reparte en una posicion por TP si cada parte alcanza el lote minimo
        n = len(tps)
        if n > 1 and lots / n >= info.volume_min:
            part = math.floor(lots / n / info.volume_step + 1e-9) * info.volume_step
            parts = [(round(part, 8), tp) for tp in tps]
        else:
            parts = [(lots, tps[0] if tps else None)]

        digits = info.digits
        plan = {"symbol": sym, "side": s.side, "entry": entry, "sl": round(sl, digits),
                "parts": [(v, tp and round(tp, digits)) for v, tp in parts],
                "pending": bool(s.entry and abs(price - s.entry) / s.entry * 100 > 0.02),
                "dry_run": c.dry_run}
        log.info("Plan: %s", plan)
        if c.dry_run:
            self._record(plan)
            return plan

        results = []
        for vol, tp in parts:
            res = self._send(sym, s, vol, round(sl, digits), tp and round(tp, digits),
                             s.entry if plan["pending"] else None, price)
            results.append(res)
        plan["results"] = results
        self._record(plan)
        return plan

    def _send(self, sym, s: Signal, vol, sl, tp, pending_price, price):
        mt5 = self.mt5
        buy = s.side == "buy"
        req = {"symbol": sym, "volume": vol, "sl": sl, "tp": tp or 0.0,
               "deviation": self.cfg.deviation, "magic": self.cfg.magic,
               "comment": "tg-signal", "type_time": mt5.ORDER_TIME_GTC}
        if pending_price:
            # limit si el precio objetivo esta "mejor" que el actual; stop en caso contrario
            if buy:
                otype = mt5.ORDER_TYPE_BUY_LIMIT if pending_price < price else mt5.ORDER_TYPE_BUY_STOP
            else:
                otype = mt5.ORDER_TYPE_SELL_LIMIT if pending_price > price else mt5.ORDER_TYPE_SELL_STOP
            req.update(action=mt5.TRADE_ACTION_PENDING, type=otype, price=pending_price)
        else:
            req.update(action=mt5.TRADE_ACTION_DEAL,
                       type=mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL, price=price)
        # Los brokers aceptan distintos modos de llenado; probamos los habituales
        res = None
        for fill in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
            req["type_filling"] = fill
            res = mt5.order_send(req)
            if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                return {"retcode": res.retcode, "order": res.order, "volume": vol}
            if res is not None and res.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
                break
        log.error("Orden rechazada: %s", res)
        return {"retcode": getattr(res, "retcode", None), "comment": getattr(res, "comment", "")}
