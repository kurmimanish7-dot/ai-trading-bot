import pandas as pd
import numpy as np


# ============================================================
# CANDLESTICK PATTERN ANALYSIS
# ============================================================

def detect_candlestick_patterns(df: pd.DataFrame) -> list:
    patterns = []

    if df is None or len(df) < 3:
        return ["INSUFFICIENT_DATA"]

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    open_price = float(latest["open"])
    high = float(latest["high"])
    low = float(latest["low"])
    close = float(latest["close"])

    prev_open = float(previous["open"])
    prev_close = float(previous["close"])

    body = abs(close - open_price)
    candle_range = max(high - low, 1e-9)

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    body_ratio = body / candle_range

    # --------------------------------------------------------
    # DOJI
    # --------------------------------------------------------

    if body_ratio <= 0.10:
        patterns.append("DOJI")

    # --------------------------------------------------------
    # HAMMER
    # --------------------------------------------------------

    if (
        lower_wick >= body * 2
        and upper_wick <= body
        and body_ratio < 0.45
    ):
        patterns.append("HAMMER")

    # --------------------------------------------------------
    # SHOOTING STAR
    # --------------------------------------------------------

    if (
        upper_wick >= body * 2
        and lower_wick <= body
        and body_ratio < 0.45
    ):
        patterns.append("SHOOTING_STAR")

    # --------------------------------------------------------
    # BULLISH ENGULFING
    # --------------------------------------------------------

    if (
        prev_close < prev_open
        and close > open_price
        and open_price <= prev_close
        and close >= prev_open
    ):
        patterns.append("BULLISH_ENGULFING")

    # --------------------------------------------------------
    # BEARISH ENGULFING
    # --------------------------------------------------------

    if (
        prev_close > prev_open
        and close < open_price
        and open_price >= prev_close
        and close <= prev_open
    ):
        patterns.append("BEARISH_ENGULFING")

    # --------------------------------------------------------
    # STRONG BULLISH CANDLE
    # --------------------------------------------------------

    if (
        close > open_price
        and body_ratio >= 0.70
    ):
        patterns.append("STRONG_BULLISH_CANDLE")

    # --------------------------------------------------------
    # STRONG BEARISH CANDLE
    # --------------------------------------------------------

    if (
        close < open_price
        and body_ratio >= 0.70
    ):
        patterns.append("STRONG_BEARISH_CANDLE")

    if not patterns:
        patterns.append("NORMAL_CANDLE")

    return patterns


# ============================================================
# MACD
# ============================================================

def calculate_macd(
    close: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
):
    fast_ema = close.ewm(
        span=fast_period,
        adjust=False
    ).mean()

    slow_ema = close.ewm(
        span=slow_period,
        adjust=False
    ).mean()

    macd = fast_ema - slow_ema

    signal = macd.ewm(
        span=signal_period,
        adjust=False
    ).mean()

    histogram = macd - signal

    return macd, signal, histogram


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def calculate_support_resistance(
    df: pd.DataFrame,
    lookback: int = 20,
):
    if df is None or len(df) < lookback:
        return {
            "support": None,
            "resistance": None,
        }

    recent = df.tail(lookback)

    support = float(
        recent["low"].min()
    )

    resistance = float(
        recent["high"].max()
    )

    return {
        "support": round(support, 2),
        "resistance": round(resistance, 2),
    }


# ============================================================
# VOLUME ANALYSIS
# ============================================================

def analyze_volume(
    df: pd.DataFrame,
    period: int = 20,
):
    if (
        df is None
        or "volume" not in df.columns
        or len(df) < period
    ):
        return {
            "volume": None,
            "average_volume": None,
            "volume_ratio": None,
            "volume_signal": "UNAVAILABLE",
        }

    current_volume = float(
        df["volume"].iloc[-1]
    )

    average_volume = float(
        df["volume"]
        .tail(period)
        .mean()
    )

    if average_volume <= 0:
        ratio = 0.0
    else:
        ratio = (
            current_volume
            / average_volume
        )

    if ratio >= 2.0:
        signal = "VERY_HIGH_VOLUME"

    elif ratio >= 1.5:
        signal = "HIGH_VOLUME"

    elif ratio >= 0.8:
        signal = "NORMAL_VOLUME"

    else:
        signal = "LOW_VOLUME"

    return {
        "volume": round(
            current_volume,
            2
        ),
        "average_volume": round(
            average_volume,
            2
        ),
        "volume_ratio": round(
            ratio,
            2
        ),
        "volume_signal": signal,
    }


# ============================================================
# TREND STRUCTURE
# ============================================================

def analyze_market_structure(
    df: pd.DataFrame
):
    if df is None or len(df) < 10:
        return {
            "structure": "INSUFFICIENT_DATA",
            "trend": "UNKNOWN",
            "momentum": "UNKNOWN",
        }

    recent = df.tail(10)

    highs = recent["high"].to_numpy()
    lows = recent["low"].to_numpy()
    closes = recent["close"].to_numpy()

    higher_highs = (
        highs[-1] > highs[-3]
        and highs[-3] > highs[-5]
    )

    higher_lows = (
        lows[-1] > lows[-3]
        and lows[-3] > lows[-5]
    )

    lower_highs = (
        highs[-1] < highs[-3]
        and highs[-3] < highs[-5]
    )

    lower_lows = (
        lows[-1] < lows[-3]
        and lows[-3] < lows[-5]
    )

    if higher_highs and higher_lows:
        structure = "HIGHER_HIGH_HIGHER_LOW"
        trend = "BULLISH"

    elif lower_highs and lower_lows:
        structure = "LOWER_HIGH_LOWER_LOW"
        trend = "BEARISH"

    else:
        structure = "MIXED"
        trend = "SIDEWAYS"

    short_move = (
        closes[-1] - closes[-4]
    )

    if short_move > 0:
        momentum = "POSITIVE"

    elif short_move < 0:
        momentum = "NEGATIVE"

    else:
        momentum = "FLAT"

    return {
        "structure": structure,
        "trend": trend,
        "momentum": momentum,
    }


# ============================================================
# EMA 200
# ============================================================

def calculate_ema_200(
    close: pd.Series
) -> float:

    ema_200 = close.ewm(
        span=200,
        adjust=False
    ).mean()

    return round(
        float(ema_200.iloc[-1]),
        2
    )


# ============================================================
# COMPLETE ADVANCED ANALYSIS
# ============================================================

def build_advanced_analysis(
    df: pd.DataFrame
):
    if df is None or df.empty:
        return {
            "status": "NO_DATA"
        }

    df = df.copy()

    df["close"] = pd.to_numeric(
        df["close"],
        errors="coerce"
    )

    df["open"] = pd.to_numeric(
        df["open"],
        errors="coerce"
    )

    df["high"] = pd.to_numeric(
        df["high"],
        errors="coerce"
    )

    df["low"] = pd.to_numeric(
        df["low"],
        errors="coerce"
    )

    df["volume"] = pd.to_numeric(
        df["volume"],
        errors="coerce"
    )

    df = df.dropna(
        subset=[
            "open",
            "high",
            "low",
            "close",
        ]
    )

    if len(df) < 30:
        return {
            "status": "INSUFFICIENT_DATA"
        }

    close = df["close"]

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    macd, macd_signal, macd_histogram = (
        calculate_macd(close)
    )

    latest_macd = float(
        macd.iloc[-1]
    )

    latest_signal = float(
        macd_signal.iloc[-1]
    )

    latest_histogram = float(
        macd_histogram.iloc[-1]
    )

    if (
        latest_macd > latest_signal
        and latest_histogram > 0
    ):
        macd_bias = "BULLISH"

    elif (
        latest_macd < latest_signal
        and latest_histogram < 0
    ):
        macd_bias = "BEARISH"

    else:
        macd_bias = "NEUTRAL"

    # --------------------------------------------------------
    # EMA 200
    # --------------------------------------------------------

    ema_200 = calculate_ema_200(
        close
    )

    current_price = float(
        close.iloc[-1]
    )

    if current_price > ema_200:
        ema_200_position = "ABOVE"

    elif current_price < ema_200:
        ema_200_position = "BELOW"

    else:
        ema_200_position = "AT"

    # --------------------------------------------------------
    # CANDLE PATTERNS
    # --------------------------------------------------------

    patterns = detect_candlestick_patterns(
        df
    )

    # --------------------------------------------------------
    # SUPPORT / RESISTANCE
    # --------------------------------------------------------

    levels = calculate_support_resistance(
        df
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    volume = analyze_volume(
        df
    )

    # --------------------------------------------------------
    # MARKET STRUCTURE
    # --------------------------------------------------------

    structure = analyze_market_structure(
        df
    )

    return {
        "status": "OK",

        "candlestick_patterns": patterns,

        "macd": {
            "value": round(
                latest_macd,
                4
            ),
            "signal": round(
                latest_signal,
                4
            ),
            "histogram": round(
                latest_histogram,
                4
            ),
            "bias": macd_bias,
        },

        "ema_200": {
            "value": ema_200,
            "position": ema_200_position,
        },

        "support_resistance": levels,

        "volume": volume,

        "market_structure": structure,

        "current_price": round(
            current_price,
            2
        ),
    }
