from bot.parser import parse_signal


def test_long_english():
    s = parse_signal("#BTCUSDT LONG\nEntry: 60000\nTP1: 61000\nTP2: 62000\nSL: 59000\nLeverage 10x")
    assert s.symbol == "BTC/USDT:USDT" and s.side == "buy"
    assert s.entry == 60000 and s.stop_loss == 59000
    assert s.take_profits == [61000, 62000] and s.leverage == 10


def test_short_spanish():
    s = parse_signal("ETH/USDT VENTA\nEntrada: 3000\nObjetivo 1: 2900\nStop Loss: 3100")
    assert s.side == "sell" and s.symbol == "ETH/USDT:USDT"
    assert s.take_profits == [2900] and s.stop_loss == 3100


def test_inconsistent_sl_rejected():
    assert parse_signal("BTCUSDT LONG entry 60000 sl 61000 tp 62000") is None


def test_not_a_signal():
    assert parse_signal("Buenos dias a todos, hoy mercado lateral") is None
