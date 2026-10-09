"""Escucha un grupo de Telegram, detecta senales y las ejecuta."""
import asyncio
import logging
import os
import time

from dotenv import load_dotenv
from telethon import TelegramClient, events

from .parser import parse_signals
from .mt5_trader import MT5Config, MT5Trader
from .trader import Config, Trader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("bot")


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "si")


def load_config() -> Config:
    return Config(
        exchange=os.getenv("EXCHANGE", "binanceusdm"),
        api_key=os.getenv("API_KEY", ""),
        api_secret=os.getenv("API_SECRET", ""),
        sandbox=_bool("SANDBOX", "true"),
        dry_run=_bool("DRY_RUN", "true"),
        risk_pct=float(os.getenv("RISK_PCT", "1")),
        max_leverage=int(os.getenv("MAX_LEVERAGE", "10")),
        max_open_trades=int(os.getenv("MAX_OPEN_TRADES", "3")),
        max_slippage_pct=float(os.getenv("MAX_SLIPPAGE_PCT", "0.5")),
        default_sl_pct=float(os.getenv("DEFAULT_SL_PCT", "0")),
    )


def build_trader():
    broker = os.getenv("BROKER", "mt5").lower()
    if broker == "mt5":
        return MT5Trader(MT5Config(
            login=int(os.getenv("MT5_LOGIN") or 0) or None,
            password=os.getenv("MT5_PASSWORD", ""),
            server=os.getenv("MT5_SERVER", ""),
            terminal_path=os.getenv("MT5_PATH", ""),
            symbol_suffix=os.getenv("MT5_SYMBOL_SUFFIX", ""),
            dry_run=_bool("DRY_RUN", "true"),
            risk_pct=float(os.getenv("RISK_PCT", "1")),
            max_open_trades=int(os.getenv("MAX_OPEN_TRADES", "3")),
            max_slippage_pct=float(os.getenv("MAX_SLIPPAGE_PCT", "0.5")),
            default_sl_pct=float(os.getenv("DEFAULT_SL_PCT", "0")),
        )), _bool("DRY_RUN", "true"), False
    cfg = load_config()
    return Trader(cfg), cfg.dry_run, cfg.sandbox


def main() -> None:
    load_dotenv()
    trader, dry_run, sandbox = build_trader()
    chat = os.environ["TG_CHAT"]
    chat = int(chat) if chat.lstrip("-").isdigit() else chat
    allowed = {int(x) for x in os.getenv("TG_ALLOWED_SENDERS", "").split(",") if x.strip()}

    dedupe_secs = int(os.getenv("DEDUPE_MINUTES", "30")) * 60
    seen: dict[tuple, float] = {}

    max_age = int(os.getenv("MAX_SIGNAL_AGE_SECONDS", "120"))
    client = TelegramClient(
        "session", int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"],
        connection_retries=-1, retry_delay=5, auto_reconnect=True,  # reconectar siempre
    )

    async def notify(msg: str) -> None:
        """Aviso a tus 'Mensajes guardados' de Telegram."""
        try:
            await client.send_message("me", f"🤖 {msg}")
        except Exception:
            log.exception("No se pudo enviar el aviso")

    @client.on(events.NewMessage(chats=chat))
    async def handler(event):
        if allowed and event.sender_id not in allowed:
            return
        now = time.time()
        # tras una caida de red Telegram entrega mensajes atrasados: no operar senales viejas
        if now - event.date.timestamp() > max_age:
            log.warning("Mensaje antiguo ignorado (%ss)", int(now - event.date.timestamp()))
            return
        for sig in parse_signals(event.raw_text or ""):
            # el mismo mensaje se suele reenviar (junto y luego por separado): no operar dos veces
            key = (sig.symbol, sig.side, sig.stop_loss, tuple(sig.take_profits))
            if now - seen.get(key, 0) < dedupe_secs:
                log.info("Senal duplicada ignorada: %s %s", sig.symbol, sig.side)
                continue
            seen[key] = now
            log.info("Senal detectada: %s", sig)
            try:
                plan = await asyncio.to_thread(trader.execute, sig)
                if plan:
                    tag = "SIMULADA" if plan.get("dry_run") else "ABIERTA"
                    await notify(f"Operacion {tag}: {sig.side.upper()} {sig.symbol} SL {sig.stop_loss} TP {sig.take_profits}")
                else:
                    await notify(f"Senal NO operada: {sig.side.upper()} {sig.symbol} (revisa el log)")
            except Exception as e:
                log.exception("Error ejecutando la senal")
                await notify(f"ERROR operando {sig.symbol}: {e}")

    log.info("Bot iniciado (dry_run=%s, sandbox=%s)", dry_run, sandbox)
    with client:
        client.loop.run_until_complete(notify(f"Bot iniciado (dry_run={dry_run}). Escuchando senales."))
        client.run_until_disconnected()


if __name__ == "__main__":
    main()
