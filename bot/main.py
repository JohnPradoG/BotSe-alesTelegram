"""Escucha un grupo de Telegram, detecta senales y las ejecuta."""
import asyncio
import logging
import os

from dotenv import load_dotenv
from telethon import TelegramClient, events

from .parser import parse_signal
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

    client = TelegramClient("session", int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])

    @client.on(events.NewMessage(chats=chat))
    async def handler(event):
        if allowed and event.sender_id not in allowed:
            return
        sig = parse_signal(event.raw_text or "")
        if not sig:
            return
        log.info("Senal detectada: %s", sig)
        try:
            await asyncio.to_thread(trader.execute, sig)
        except Exception:
            log.exception("Error ejecutando la senal")

    log.info("Bot iniciado (dry_run=%s, sandbox=%s)", dry_run, sandbox)
    with client:
        client.run_until_disconnected()


if __name__ == "__main__":
    main()
