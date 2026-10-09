# Bot de señales Telegram → Trading

Lee un grupo de Telegram con tu cuenta, detecta señales (LONG/SHORT, entrada, SL, TPs, apalancamiento)
y abre la operación en tu broker. El instrumento lo toma de cada señal: divisas (EURUSD, GBP/JPY),
oro/plata (XAUUSD, "oro"), índices (US30, NAS100, "nasdaq"), petróleo y cripto.

- `BROKER=mt5` (por defecto): **MetaTrader 5**, para forex, metales e índices. Solo Windows con el terminal MT5 abierto.
- `BROKER=ccxt`: exchanges cripto (Binance Futures, etc.).

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

## Instrumentos y alias
`bot/aliases.json` traduce nombres libres ("oro", "nasdaq", "dax") al símbolo estándar; edítalo a tu gusto.
En MT5 el bot busca el símbolo en tu broker automáticamente (admite sufijos como `EURUSDm` o `EURUSD.a`;
si falla, fija `MT5_SYMBOL_SUFFIX`). El lote se calcula con el valor del tick del propio símbolo, así que
el riesgo por operación es correcto para cualquier instrumento. Si hay varios TPs, abre una posición por TP.

## Formatos reconocidos
Un mismo mensaje puede traer varias señales (cada una empieza por `Pair:`); se procesan por separado.
Si la señal dice `Current price`, se opera **a mercado** (ese precio solo sirve para descartarla si el
mercado ya se movió más de `MAX_SLIPPAGE_PCT`). Las señales idénticas repetidas dentro de `DEDUPE_MINUTES`
se ignoran, para no duplicar operaciones cuando el admin reenvía el mismo mensaje.
```
Pair: EUR/USD
Current price: ~ 1.11981
Direction: SELL
Stop Loss: 1.12107
Take Profit: 1.11792
```
```
BUY EUR/USD @ 1.0850
SL 1.0820
TP1 1.0880
TP2 1.0920
```
```
Vender oro ahora      (sin entrada = a mercado)
SL 2360.5
TP 2340
```
También en español (`Entrada`, `Objetivo`, `Compra/Venta`). Si el formato de tu grupo es distinto,
ajusta `bot/parser.py` y los tests en `tests/`.

## Tests
`pytest`
