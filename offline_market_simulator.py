import pandas as pd
import numpy as np

from telemetry_engine import TelemetryEngine


def create_sample_candles(rows=100):
    """
    Create deterministic sample OHLCV data
    for offline indicator testing.

    IMPORTANT:
    This is TEST DATA only.
    It is NOT real market data.
    """

    timestamps = pd.date_range(
        end=pd.Timestamp.now(),
        periods=rows,
        freq="5min"
    )

    base_price = 25000.0

    prices = (
        base_price
        + np.arange(rows) * 8.0
        + np.sin(np.arange(rows) / 4.0) * 25.0
    )

    close = prices

    open_price = close - 5.0

    high = close + 15.0

    low = close - 15.0

    volume = (
        100000
        + (np.arange(rows) % 10) * 5000
    )

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def main():

    print("")
    print("========================================")
    print(" OFFLINE MARKET SIMULATOR")
    print(" REAL MARKET DATA : NO")
    print(" ANGEL ONE API    : NOT USED")
    print(" REAL ORDERS      : NOT USED")
    print("========================================")
    print("")

    df = create_sample_candles()

    indicators = (
        TelemetryEngine.calculate_indicators(df)
    )

    print("========== OFFLINE TELEMETRY ==========")

    print(
        f"LTP            : ₹{indicators['ltp']}"
    )

    print(
        f"RSI            : {indicators['rsi']}"
    )

    print(
        f"ATR            : {indicators['atr']}"
    )

    print(
        f"EMA 9          : {indicators['ema_9']}"
    )

    print(
        f"EMA 21         : {indicators['ema_21']}"
    )

    print(
        f"EMA 50         : {indicators['ema_50']}"
    )

    print(
        f"ADX            : {indicators['adx']}"
    )

    print(
        f"VWAP           : ₹{indicators['vwap']}"
    )

    print(
        f"Price vs VWAP  : "
        f"{indicators['price_vs_vwap']}"
    )

    print(
        f"EMA Trend      : "
        f"{indicators['ema_trend']}"
    )

    print(
        f"Supertrend     : "
        f"{indicators['supertrend']}"
    )

    print(
        f"Market Regime  : "
        f"{indicators['market_regime']}"
    )

    print("")
    print("Recent candles:")

    for candle in indicators["recent_candles"]:
        print(candle)

    print("")
    print("========================================")
    print(" OFFLINE INDICATOR TEST COMPLETE")
    print(" NO REAL TRADE WAS SENT")
    print("========================================")
    print("")


if __name__ == "__main__":
    main()
