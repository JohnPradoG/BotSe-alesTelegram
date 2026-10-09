from bot.mt5_trader import calc_lots


def test_eurusd_risk_100():
    # cuenta 10k, 1% = 100 USD; SL 30 pips (0.0030), tick 0.00001 vale 1 USD/lote
    lots = calc_lots(100, 0.0030, 0.00001, 1.0, 0.01, 100, 0.01)
    assert lots == 0.33  # 100 / (300 ticks * 1) = 0.333 -> 0.33


def test_below_min_rejected():
    assert calc_lots(1, 0.0100, 0.00001, 1.0, 0.01, 100, 0.01) == 0.0
