from bot.parser import parse_signal


def test_long_english():
    s = parse_signal("#BTCUSDT LONG\nEntry: 60000\nTP1: 61000\nTP2: 62000\nSL: 59000\nLeverage 10x")
    assert s.symbol == "BTCUSDT" and s.side == "buy"
    assert s.entry == 60000 and s.stop_loss == 59000
    assert s.take_profits == [61000, 62000] and s.leverage == 10


def test_short_spanish():
    s = parse_signal("ETH/USDT VENTA\nEntrada: 3000\nObjetivo 1: 2900\nStop Loss: 3100")
    assert s.side == "sell" and s.symbol == "ETHUSDT"
    assert s.take_profits == [2900] and s.stop_loss == 3100


def test_inconsistent_sl_rejected():
    assert parse_signal("BTCUSDT LONG entry 60000 sl 61000 tp 62000") is None


def test_not_a_signal():
    assert parse_signal("Buenos dias a todos, hoy mercado lateral") is None


def test_forex_pair_slash():
    s = parse_signal("BUY EUR/USD @ 1.0850\nSL 1.0820\nTP1 1.0880\nTP2 1.0920")
    assert s.symbol == "EURUSD" and s.side == "buy" and s.entry == 1.085
    assert s.stop_loss == 1.082 and s.take_profits == [1.088, 1.092]


def test_gold_alias_market():
    s = parse_signal("Vender oro ahora\nSL 2360.5\nTP 2340")
    assert s.symbol == "XAUUSD" and s.side == "sell" and s.entry is None
    assert s.stop_loss == 2360.5


def test_index():
    s = parse_signal("SELL NAS100 entry 18500 sl 18560 tp 18400")
    assert s.symbol == "NAS100" and s.side == "sell"


def test_entry_range_uses_first():
    s = parse_signal("GBPJPY BUY entry: 190.50-190.70 SL 190.00 TP 191.50")
    assert s.symbol == "GBPJPY" and s.entry == 190.5


BATCH = """Atención, amigos! Empezamos la sesión sobre señales. Preparaos!
Pair: NZD/USD

Current price: ~ 0.55979

Direction: SELL

Stop Loss: 0.56049

Take Profit: 0.55874

Pair: GBP/USD

Current price: ~ 1.32141

Direction: BUY

Stop Loss: 1.32040

Take Profit: 1.32209

Pair: EUR/USD

Current price: ~ 1.11981

Direction: SELL

Stop Loss: 1.12107

Take Profit: 1.11792
Se las voy a pasar independientes"""


def test_real_batch_message():
    from bot.parser import parse_signals
    sigs = parse_signals(BATCH)
    assert [(s.symbol, s.side) for s in sigs] == [
        ("NZDUSD", "sell"), ("GBPUSD", "buy"), ("EURUSD", "sell")]
    nzd = sigs[0]
    assert nzd.entry is None and nzd.ref_price == 0.55979  # a mercado
    assert nzd.stop_loss == 0.56049 and nzd.take_profits == [0.55874]
    assert sigs[1].stop_loss == 1.3204 and sigs[1].take_profits == [1.32209]


def test_single_message_and_intro():
    from bot.parser import parse_signals
    assert parse_signals("Atención, amigos! Empezamos la sesión sobre señales. Preparaos!") == []
    s = parse_signals("Pair: EUR/USD\nCurrent price: ~ 1.11981\nDirection: SELL\nStop Loss: 1.12107\nTake Profit: 1.11792")
    assert len(s) == 1 and s[0].symbol == "EURUSD"
