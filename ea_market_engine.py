import datetime
import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class EAMarketEngine:
    """
    Expert Advisor Market Engine.

    Purpose:
    - Fetch multi-timeframe OHLCV data from Angel One SmartAPI.
    - Fetch real-time live LTP to eliminate stale historical prices.
    - Calculate technical indicators on live incoming prices.
    - Detect market structure and price action patterns.
    """

    TIMEFRAMES = {
        "1M": "ONE_MINUTE",
        "3M": "THREE_MINUTE",
        "5M": "FIVE_MINUTE",
        "10M": "TEN_MINUTE",
        "15M": "FIFTEEN_MINUTE",
        "30M": "THIRTY_MINUTE",
        "1H": "ONE_HOUR",
        "1D": "ONE_DAY",
    }

    INDEX_TOKEN_MAP = {
        "26000": "99926000",   # Nifty 50 historical candle token
        "26009": "99926009",   # Bank Nifty historical candle token
    }

    def __init__(self, smart_api):
        self.smart_api = smart_api

    # =========================================================
    # SAFE NUMBER FORMATTING
    # =========================================================

    @staticmethod
    def safe_float(value, digits=2):
        try:
            if value is None:
                return None
            value = float(value)
            if not np.isfinite(value):
                return None
            return round(value, digits)
        except Exception:
            return None

    # =========================================================
    # REAL-TIME LIVE LTP FETCHING (PREVENTS MONDAY STALE DATA)
    # =========================================================

    def get_live_ltp(self, exchange: str, symbol: str, token: str) -> Optional[float]:
        """
        Angel One REST API se directly second-by-second live Last Traded Price (LTP) fetch karta hai.
        """
        if not self.smart_api:
            logger.error("SmartAPI instance unavailable in EAMarketEngine.")
            return None

        try:
            # Agar index token 99926000 hai to LTP ke liye 26000 standard hai
            live_token = str(token)
            if live_token == "99926000":
                live_token = "26000"
            elif live_token == "99926009":
                live_token = "26009"

            resp = self.smart_api.ltpData(
                exchange=str(exchange).upper(),
                tradingsymbol=str(symbol).upper(),
                symboltoken=live_token
            )

            if resp and resp.get("status") and resp.get("data"):
                ltp = float(resp["data"].get("ltp", 0.0))
                if ltp > 0:
                    return ltp

            logger.warning("LTP API failed for %s (%s): %s", symbol, token, resp.get("message"))
            return None
        except Exception as e:
            logger.error("Error fetching live LTP for %s: %s", symbol, e)
            return None

    # =========================================================
    # FETCH CANDLES (WITH MAPPING AND TOKEN RECOVERY)
    # =========================================================

    def fetch_candles(
        self,
        exchange: str,
        token: str,
        interval: str,
        days: int = 5,
        live_ltp: Optional[float] = None
    ) -> Dict[str, Any]:

        if not exchange:
            return {"status": False, "error": "Exchange unavailable.", "data": None}

        if not token:
            return {"status": False, "error": "Instrument token unavailable.", "data": None}

        try:
            # Format interval properly (e.g. '5M' -> 'FIVE_MINUTE')
            mapped_interval = self.TIMEFRAMES.get(str(interval).upper(), str(interval).upper())

            # Convert token for Index historical data if needed
            candle_token = self.INDEX_TOKEN_MAP.get(str(token), str(token))

            now = datetime.datetime.now()
            start = now - datetime.timedelta(days=days)

            params = {
                "exchange": str(exchange).upper(),
                "symboltoken": str(candle_token),
                "interval": mapped_interval,
                "fromdate": start.strftime("%Y-%m-%d 09:15"),
                "todate": now.strftime("%Y-%m-%d %H:%M"),
            }

            response = self.smart_api.getCandleData(params)

            if not response or not response.get("status"):
                err_msg = response.get("message", "Angel One candle API error.") if response else "Empty response"
                return {"status": False, "error": str(err_msg), "data": None}

            raw_data = response.get("data")
            if not raw_data:
                return {"status": False, "error": "No candle data received.", "data": None}

            df = pd.DataFrame(
                raw_data,
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            numeric_columns = ["open", "high", "low", "close", "volume"]
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()
            df = df.sort_values("timestamp").reset_index(drop=True)

            if df.empty:
                return {"status": False, "error": "Candle dataframe is empty.", "data": None}

            # Merge live LTP into the latest candle so indicators reflect live tick
            if live_ltp and live_ltp > 0:
                last_idx = df.index[-1]
                df.at[last_idx, "close"] = live_ltp
                if live_ltp > df.at[last_idx, "high"]:
                    df.at[last_idx, "high"] = live_ltp
                if live_ltp < df.at[last_idx, "low"]:
                    df.at[last_idx, "low"] = live_ltp

            return {"status": True, "error": None, "data": df}

        except Exception as exc:
            return {"status": False, "error": str(exc), "data": None}

    # =========================================================
    # TECHNICAL INDICATORS
    # =========================================================

    @staticmethod
    def ema(series, period):
        return series.ewm(span=period, adjust=False, min_periods=period).mean()

    @staticmethod
    def rsi(series, period=14):
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def atr(df, period=14):
        previous_close = df["close"].shift(1)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - previous_close).abs()
        tr3 = (df["low"] - previous_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return true_range.rolling(period).mean()

    @staticmethod
    def macd(close, fast=12, slow=26, signal=9):
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def adx_data(df, period=14):
        high = df["high"]
        low = df["low"]
        close = df["close"]

        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
            index=df.index
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
            index=df.index
        )

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(period).mean()

        plus_di = 100 * plus_dm.rolling(period).mean() / (atr + 1e-9)
        minus_di = 100 * minus_dm.rolling(period).mean() / (atr + 1e-9)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
        adx = dx.rolling(period).mean()

        return adx, plus_di, minus_di

    @staticmethod
    def vwap(df):
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        value = typical_price * df["volume"].fillna(0)
        return value.cumsum() / (df["volume"].fillna(0).cumsum() + 1e-9)

    @staticmethod
    def support_resistance(df, lookback=20):
        recent = df.tail(lookback)
        if recent.empty:
            return {"support": None, "resistance": None}
        return {
            "support": EAMarketEngine.safe_float(recent["low"].min()),
            "resistance": EAMarketEngine.safe_float(recent["high"].max()),
        }

    @staticmethod
    def candle_pattern(df):
        if len(df) < 2:
            return "DATA_UNAVAILABLE"

        previous = df.iloc[-2]
        current = df.iloc[-1]

        o, h, l, c = float(current["open"]), float(current["high"]), float(current["low"]), float(current["close"])
        po, pc = float(previous["open"]), float(previous["close"])

        body = abs(c - o)
        candle_range = max(h - l, 1e-9)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l

        if body <= candle_range * 0.10:
            return "DOJI"
        if lower_wick >= body * 2 and upper_wick <= body:
            return "HAMMER"
        if upper_wick >= body * 2 and lower_wick <= body:
            return "SHOOTING_STAR"
        if pc < po and c > o and o <= pc and c >= po:
            return "BULLISH_ENGULFING"
        if pc > po and c < o and o >= pc and c <= po:
            return "BEARISH_ENGULFING"
        if c > o:
            return "BULLISH_CANDLE"
        if c < o:
            return "BEARISH_CANDLE"
        return "NEUTRAL_CANDLE"

    @staticmethod
    def market_structure(df, lookback=10):
        if len(df) < lookback + 2:
            return {"trend": "DATA_UNAVAILABLE", "structure": "DATA_UNAVAILABLE"}

        recent = df.tail(lookback)
        highs = recent["high"].values
        lows = recent["low"].values

        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            return {"trend": "BULLISH", "structure": "HH_HL"}
        if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            return {"trend": "BEARISH", "structure": "LH_LL"}
        return {"trend": "SIDEWAYS", "structure": "MIXED"}

    @staticmethod
    def volume_analysis(df, period=20):
        if "volume" not in df.columns:
            return {"volume": None, "average_volume": None, "ratio": None, "status": "UNAVAILABLE"}

        current = df["volume"].iloc[-1]
        average = df["volume"].tail(period).mean()

        if pd.isna(current) or pd.isna(average) or average <= 0:
            return {"volume": None, "average_volume": None, "ratio": None, "status": "UNAVAILABLE"}

        ratio = float(current) / float(average)
        status = "HIGH" if ratio >= 1.50 else ("NORMAL" if ratio >= 1.00 else "LOW")

        return {
            "volume": EAMarketEngine.safe_float(current, 0),
            "average_volume": EAMarketEngine.safe_float(average, 0),
            "ratio": EAMarketEngine.safe_float(ratio),
            "status": status,
        }

    # =========================================================
    # COMPLETE SNAPSHOT CALCULATION
    # =========================================================

    @classmethod
    def calculate_snapshot(cls, df, explicit_live_price: Optional[float] = None) -> Dict[str, Any]:
        if df is None or df.empty:
            return {"status": False, "error": "No candle dataframe available."}

        try:
            work = df.copy()
            close = work["close"]

            work["ema9"] = cls.ema(close, 9)
            work["ema20"] = cls.ema(close, 20)
            work["ema50"] = cls.ema(close, 50)
            work["ema200"] = cls.ema(close, 200)
            work["rsi"] = cls.rsi(close, 14)
            work["atr"] = cls.atr(work, 14)

            work["macd"], work["macd_signal"], work["macd_hist"] = cls.macd(close)
            work["adx"], work["plus_di"], work["minus_di"] = cls.adx_data(work)
            work["vwap"] = cls.vwap(work)

            latest = work.iloc[-1]

            # Price priority: Explicit Live LTP > Last candle close
            price = cls.safe_float(explicit_live_price) if explicit_live_price else cls.safe_float(latest["close"])

            ema9 = cls.safe_float(latest["ema9"])
            ema20 = cls.safe_float(latest["ema20"])
            ema50 = cls.safe_float(latest["ema50"])
            ema200 = cls.safe_float(latest["ema200"])
            rsi = cls.safe_float(latest["rsi"])
            atr = cls.safe_float(latest["atr"])

            macd_val = cls.safe_float(latest["macd"])
            macd_sig = cls.safe_float(latest["macd_signal"])
            macd_hist = cls.safe_float(latest["macd_hist"])
            adx = cls.safe_float(latest["adx"])
            plus_di = cls.safe_float(latest["plus_di"])
            minus_di = cls.safe_float(latest["minus_di"])
            vwap_val = cls.safe_float(latest["vwap"])

            # EMA Trend
            if ema9 and ema20 and ema50:
                if ema9 > ema20 > ema50:
                    ema_trend = "BULLISH"
                elif ema9 < ema20 < ema50:
                    ema_trend = "BEARISH"
                else:
                    ema_trend = "MIXED"
            else:
                ema_trend = "UNAVAILABLE"

            # VWAP Position
            if price is not None and vwap_val is not None:
                vwap_pos = "ABOVE" if price > vwap_val else ("BELOW" if price < vwap_val else "AT")
            else:
                vwap_pos = "UNAVAILABLE"

            # MACD Bias
            macd_bias = "BULLISH" if (macd_hist and macd_hist > 0) else ("BEARISH" if (macd_hist and macd_hist < 0) else "NEUTRAL")

            # ADX Regime
            regime = "TRENDING" if (adx and adx >= 25) else "RANGE_OR_WEAK_TREND"

            # DI Bias
            if plus_di is not None and minus_di is not None:
                di_bias = "BULLISH" if plus_di > minus_di else ("BEARISH" if plus_di < minus_di else "NEUTRAL")
            else:
                di_bias = "UNAVAILABLE"

            sr = cls.support_resistance(work, 20)
            volume_meta = cls.volume_analysis(work, 20)
            structure = cls.market_structure(work, 10)
            pattern = cls.candle_pattern(work)

            return {
                "status": True,
                "price": price,
                "timestamp": str(latest["timestamp"]),
                "ema": {
                    "ema9": ema9,
                    "ema20": ema20,
                    "ema50": ema50,
                    "ema200": ema200,
                    "trend": ema_trend,
                },
                "rsi": rsi,
                "atr": atr,
                "macd": {
                    "macd": macd_val,
                    "signal": macd_sig,
                    "hist": macd_hist,
                    "bias": macd_bias,
                },
                "adx": {
                    "adx": adx,
                    "plus_di": plus_di,
                    "minus_di": minus_di,
                    "regime": regime,
                    "bias": di_bias,
                },
                "vwap": {
                    "value": vwap_val,
                    "position": vwap_pos,
                },
                "support_resistance": sr,
                "volume": volume_meta,
                "structure": structure,
                "pattern": pattern,
            }
        except Exception as exc:
            return {"status": False, "error": f"Snapshot calculation failed: {exc}"}
