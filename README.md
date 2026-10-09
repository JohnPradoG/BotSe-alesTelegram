# Bot de señales Telegram → Trading

Lee un grupo de Telegram con tu cuenta, detecta señales (LONG/SHORT, entrada, SL, TPs, apalancamiento)
y abre la operación en el exchange vía [ccxt](https://github.com/ccxt/ccxt) (por defecto Binance Futures).

## Instalación
```bash
pip install -r requirements.txt
cp .env.example .env   # completa tus datos
python -m bot.main
```
La primera vez Telethon pedirá tu teléfono y código de Telegram.

## Seguridad (léelo)
- **Empieza con `DRY_RUN=true`**: solo registra el plan en `trades.jsonl`, no envía órdenes.
- Luego prueba con `SANDBOX=true` (testnet) antes de usar dinero real.
- Crea la API key **sin permiso de retiros**.
- El tamaño se calcula por riesgo (`RISK_PCT` del saldo entre entrada y SL). Señales sin SL se rechazan.
- Define `TG_ALLOWED_SENDERS` para que solo el admin del grupo pueda disparar operaciones.
- Seguir señales de terceros es de alto riesgo; el bot no garantiza ganancias.

## Formatos reconocidos
```
#BTCUSDT LONG
Entry: 60000
TP1: 61000
TP2: 62000
SL: 59000
Leverage 10x
```
También en español (`Entrada`, `Objetivo`, `Compra/Venta`). Si el formato de tu grupo es distinto,
ajusta `bot/parser.py` y los tests en `tests/`.

## Tests
`pytest`
