import datetime
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd


class EAMarketEngine:
    """
    Expert Advisor Market Engine.

    Purpose:
    - Fetch multi-timeframe OHLCV data from an existing Angel One API object.
    - Calculate technical indicators.
    - Detect market structure and price action.
    - Prepare clean data for the EA decision engine.

    IMPORTANT:
    - No fake market values.
    - No fake VIX/OI/PCR.
    - Missing data is explicitly marked unavailable.
    - This engine does NOT place orders.
    - Paper-trading safety remains outside this module.
    """

    TIMEFRAMES = {
        "1M": "ONE_MINUTE",
        "3M": "THREE_MINUTE",
        "5M": "FIVE_MINUTE",
        "15M": "FIFTEEN_MINUTE",
        "30M": "THIRTY_MINUTE",
        "1H": "ONE_HOUR",
    }

    def __init__(self, smart_api):
        self.smart_api = smart_api

    # =========================================================
    # SAFE NUMBER
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
    # FETCH CANDLES
    # =========================================================

    def fetch_candles(
        self,
        exchange: str,
        token: str,
        interval: str,
        days: int = 5,
    ) -> Dict[str, Any]:

        if not exchange:
            return {
                "status": False,
                "error": "Exchange unavailable.",
                "data": None,
            }

        if not token:
            return {
                "status": False,
                "error": "Instrument token unavailable.",
                "data": None,
            }

        try:
            now = datetime.datetime.now()

            start = now - datetime.timedelta(days=days)

            params = {
                "exchange": str(exchange),
                "symboltoken": str(token),
                "interval": str(interval),
                "fromdate": start.strftime(
                    "%Y-%m-%d 09:15"
                ),
                "todate": now.strftime(
                    "%Y-%m-%d %H:%M"
                ),
            }

            response = self.smart_api.getCandleData(
                params
            )

            if not response:
                return {
                    "status": False,
                    "error": "Empty response from Angel One.",
                    "data": None,
                }

            if not response.get("status"):
                return {
                    "status": False,
                    "error": str(
                        response.get(
                            "message",
                            "Angel One candle API error."
                        )
                    ),
                    "data": None,
                }

            raw_data = response.get("data")

            if not raw_data:
                return {
                    "status": False,
                    "error": "No candle data received.",
                    "data": None,
                }

            df = pd.DataFrame(
                raw_data,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ],
            )

            df["timestamp"] = pd.to_datetime(
                df["timestamp"],
                errors="coerce",
            )

            numeric_columns = [
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]

            for column in numeric_columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

            df = df.dropna(
                subset=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                ]
            ).copy()

            df = df.sort_values(
                "timestamp"
            ).reset_index(drop=True)

            if df.empty:
                return {
                    "status": False,
                    "error": "Candle dataframe is empty.",
                    "data": None,
                }

            return {
                "status": True,
                "error": None,
                "data": df,
            }

        except Exception as exc:
            return {
                "status": False,
                "error": str(exc),
                "data": None,
            }

    # =========================================================
    # EMA
    # =========================================================

    @staticmethod
    def ema(series, period):
        return series.ewm(
            span=period,
            adjust=False,
            min_periods=period,
        ).mean()

    # =========================================================
    # RSI
    # =========================================================

    @staticmethod
    def rsi(series, period=14):

        delta = series.diff()

        gain = delta.clip(
            lower=0
        )

        loss = -delta.clip(
            upper=0
        )

        avg_gain = gain.rolling(
            period
        ).mean()

        avg_loss = loss.rolling(
            period
        ).mean()

        rs = avg_gain / (
            avg_loss + 1e-9
        )

        return 100 - (
            100 / (1 + rs)
        )

    # =========================================================
    # ATR
    # =========================================================

    @staticmethod
    def atr(df, period=14):

        previous_close = df[
            "close"
        ].shift(1)

        tr1 = (
            df["high"]
            - df["low"]
        )

        tr2 = (
            df["high"]
            - previous_close
        ).abs()

        tr3 = (
            df["low"]
            - previous_close
        ).abs()

        true_range = pd.concat(
            [
                tr1,
                tr2,
                tr3,
            ],
            axis=1,
        ).max(axis=1)

        return true_range.rolling(
            period
        ).mean()

    # =========================================================
    # MACD
    # =========================================================

    @staticmethod
    def macd(
        close,
        fast=12,
        slow=26,
        signal=9,
    ):

        ema_fast = close.ewm(
            span=fast,
            adjust=False,
        ).mean()

        ema_slow = close.ewm(
            span=slow,
            adjust=False,
        ).mean()

        macd_line = (
            ema_fast
            - ema_slow
        )

        signal_line = macd_line.ewm(
            span=signal,
            adjust=False,
        ).mean()

        histogram = (
            macd_line
            - signal_line
        )

        return (
            macd_line,
            signal_line,
            histogram,
        )

    # =========================================================
    # ADX + DI
    # =========================================================

    @staticmethod
    def adx_data(
        df,
        period=14,
    ):

        high = df["high"]
        low = df["low"]
        close = df["close"]

        up_move = high.diff()

        down_move = -low.diff()

        plus_dm = pd.Series(
            np.where(
                (up_move > down_move)
                & (up_move > 0),
                up_move,
                0.0,
            ),
            index=df.index,
        )

        minus_dm = pd.Series(
            np.where(
                (down_move > up_move)
                & (down_move > 0),
                down_move,
                0.0,
            ),
            index=df.index,
        )

        tr1 = high - low

        tr2 = (
            high
            - close.shift(1)
        ).abs()

        tr3 = (
            low
            - close.shift(1)
        ).abs()

        true_range = pd.concat(
            [
                tr1,
                tr2,
                tr3,
            ],
            axis=1,
        ).max(axis=1)

        atr = true_range.rolling(
            period
        ).mean()

        plus_di = (
            100
            * plus_dm.rolling(period).mean()
            / (atr + 1e-9)
        )

        minus_di = (
            100
            * minus_dm.rolling(period).mean()
            / (atr + 1e-9)
        )

        dx = (
            100
            * (plus_di - minus_di).abs()
            / (
                plus_di
                + minus_di
                + 1e-9
            )
        )

        adx = dx.rolling(
            period
        ).mean()

        return (
            adx,
            plus_di,
            minus_di,
        )

    # =========================================================
    # VWAP
    # =========================================================

    @staticmethod
    def vwap(df):

        typical_price = (
            df["high"]
            + df["low"]
            + df["close"]
        ) / 3.0

        value = (
            typical_price
            * df["volume"].fillna(0)
        )

        return (
            value.cumsum()
            / (
                df["volume"]
                .fillna(0)
                .cumsum()
                + 1e-9
            )
        )

    # =========================================================
    # SUPPORT / RESISTANCE
    # =========================================================

    @staticmethod
    def support_resistance(
        df,
        lookback=20,
    ):

        recent = df.tail(
            lookback
        )

        if recent.empty:
            return {
                "support": None,
                "resistance": None,
            }

        support = recent[
            "low"
        ].min()

        resistance = recent[
            "high"
        ].max()

        return {
            "support": EAMarketEngine.safe_float(
                support
            ),
            "resistance": EAMarketEngine.safe_float(
                resistance
            ),
        }

    # =========================================================
    # CANDLE PATTERN
    # =========================================================

    @staticmethod
    def candle_pattern(df):

        if len(df) < 2:
            return "DATA_UNAVAILABLE"

        previous = df.iloc[-2]
        current = df.iloc[-1]

        o = float(current["open"])
        h = float(current["high"])
        l = float(current["low"])
        c = float(current["close"])

        po = float(previous["open"])
        pc = float(previous["close"])

        body = abs(c - o)

        candle_range = max(
            h - l,
            1e-9,
        )

        upper_wick = h - max(
            o,
            c,
        )

        lower_wick = min(
            o,
            c
        ) - l

        # Doji
        if body <= candle_range * 0.10:
            return "DOJI"

        # Hammer
        if (
            lower_wick >= body * 2
            and upper_wick <= body
        ):
            return "HAMMER"

        # Shooting star
        if (
            upper_wick >= body * 2
            and lower_wick <= body
        ):
            return "SHOOTING_STAR"

        # Bullish engulfing
        if (
            pc < po
            and c > o
            and o <= pc
            and c >= po
        ):
            return "BULLISH_ENGULFING"

        # Bearish engulfing
        if (
            pc > po
            and c < o
            and o >= pc
            and c <= po
        ):
            return "BEARISH_ENGULFING"

        if c > o:
            return "BULLISH_CANDLE"

        if c < o:
            return "BEARISH_CANDLE"

        return "NEUTRAL_CANDLE"

    # =========================================================
    # MARKET STRUCTURE
    # =========================================================

    @staticmethod
    def market_structure(
        df,
        lookback=10,
    ):

        if len(df) < lookback + 2:
            return {
                "trend": "DATA_UNAVAILABLE",
                "structure": "DATA_UNAVAILABLE",
            }

        recent = df.tail(
            lookback
        )

        highs = recent[
            "high"
        ].values

        lows = recent[
            "low"
        ].values

        last_high = highs[-1]
        previous_high = highs[-2]

        last_low = lows[-1]
        previous_low = lows[-2]

        if (
            last_high > previous_high
            and last_low > previous_low
        ):
            return {
                "trend": "BULLISH",
                "structure": "HH_HL",
            }

        if (
            last_high < previous_high
            and last_low < previous_low
        ):
            return {
                "trend": "BEARISH",
                "structure": "LH_LL",
            }

        return {
            "trend": "SIDEWAYS",
            "structure": "MIXED",
        }

    # =========================================================
    # VOLUME
    # =========================================================

    @staticmethod
    def volume_analysis(
        df,
        period=20,
    ):

        if "volume" not in df.columns:
            return {
                "volume": None,
                "average_volume": None,
                "ratio": None,
                "status": "UNAVAILABLE",
            }

        current = df["volume"].iloc[-1]

        average = (
            df["volume"]
            .tail(period)
            .mean()
        )

        if (
            pd.isna(current)
            or pd.isna(average)
            or average <= 0
        ):
            return {
                "volume": None,
                "average_volume": None,
                "ratio": None,
                "status": "UNAVAILABLE",
            }

        ratio = (
            float(current)
            / float(average)
        )

        if ratio >= 1.50:
            status = "HIGH"

        elif ratio >= 1.00:
            status = "NORMAL"

        else:
            status = "LOW"

        return {
            "volume": EAMarketEngine.safe_float(
                current,
                0,
            ),
            "average_volume": EAMarketEngine.safe_float(
                average,
                0,
            ),
            "ratio": EAMarketEngine.safe_float(
                ratio,
            ),
            "status": status,
        }

    # =========================================================
    # FULL INDICATOR SNAPSHOT
    # =========================================================

    @classmethod
    def calculate_snapshot(
        cls,
        df,
    ):

        if df is None or df.empty:
            return {
                "status": False,
                "error": "No candle dataframe.",
            }

        try:
            work = df.copy()

            close = work["close"]

            work["ema9"] = cls.ema(
                close,
                9,
            )

            work["ema20"] = cls.ema(
                close,
                20,
            )

            work["ema50"] = cls.ema(
                close,
                50,
            )

            work["ema200"] = cls.ema(
                close,
                200,
            )

            work["rsi"] = cls.rsi(
                close,
                14,
            )

            work["atr"] = cls.atr(
                work,
                14,
            )

            (
                work["macd"],
                work["macd_signal"],
                work["macd_hist"],
            ) = cls.macd(
                close
            )

            (
                work["adx"],
                work["plus_di"],
                work["minus_di"],
            ) = cls.adx_data(
                work
            )

            work["vwap"] = cls.vwap(
                work
            )

            latest = work.iloc[-1]

            price = cls.safe_float(
                latest["close"]
            )

            ema9 = cls.safe_float(
                latest["ema9"]
            )

            ema20 = cls.safe_float(
                latest["ema20"]
            )

            ema50 = cls.safe_float(
                latest["ema50"]
            )

            ema200 = cls.safe_float(
                latest["ema200"]
            )

            rsi = cls.safe_float(
                latest["rsi"]
            )

            atr = cls.safe_float(
                latest["atr"]
            )

            macd_value = cls.safe_float(
                latest["macd"]
            )

            macd_signal = cls.safe_float(
                latest["macd_signal"]
            )

            macd_hist = cls.safe_float(
                latest["macd_hist"]
            )

            adx = cls.safe_float(
                latest["adx"]
            )

            plus_di = cls.safe_float(
                latest["plus_di"]
            )

            minus_di = cls.safe_float(
                latest["minus_di"]
            )

            vwap_value = cls.safe_float(
                latest["vwap"]
            )

            # EMA trend
            if (
                ema9 is not None
                and ema20 is not None
                and ema50 is not None
                and ema9 > ema20 > ema50
            ):
                ema_trend = "BULLISH"

            elif (
                ema9 is not None
                and ema20 is not None
                and ema50 is not None
                and ema9 < ema20 < ema50
            ):
                ema_trend = "BEARISH"

            else:
                ema_trend = "MIXED"

            # Price / VWAP
            if (
                price is not None
                and vwap_value is not None
            ):
                if price > vwap_value:
                    vwap_position = "ABOVE"

                elif price < vwap_value:
                    vwap_position = "BELOW"

                else:
                    vwap_position = "AT"

            else:
                vwap_position = "UNAVAILABLE"

            # MACD
            if macd_hist is None:
                macd_bias = "UNAVAILABLE"

            elif macd_hist > 0:
                macd_bias = "BULLISH"

            elif macd_hist < 0:
                macd_bias = "BEARISH"

            else:
                macd_bias = "NEUTRAL"

            # ADX regime
            if adx is None:
                regime = "UNAVAILABLE"

            elif adx >= 25:
                regime = "TRENDING"

            else:
                regime = "RANGE_OR_WEAK_TREND"

            # DI bias
            if (
                plus_di is not None
                and minus_di is not None
            ):
                if plus_di > minus_di:
                    di_bias = "BULLISH"

                elif plus_di < minus_di:
                    di_bias = "BEARISH"

                else:
                    di_bias = "NEUTRAL"

            else:
                di_bias = "UNAVAILABLE"

            sr = cls.support_resistance(
                work,
                20,
            )

            volume = cls.volume_analysis(
                work,
                20,
            )

            structure = cls.market_structure(
                work,
                10,
            )

            pattern = cls.candle_pattern(
                work
            )

            return {
                "status": True,

                "candles": len(work),

                "price": price,

                "ema9": ema9,
                "ema20": ema20,
                "ema50": ema50,
                "ema200": ema200,

                "ema_trend": ema_trend,

                "rsi": rsi,

                "atr": atr,

                "macd": macd_value,
                "macd_signal": macd_signal,
                "macd_histogram": macd_hist,
                "macd_bias": macd_bias,

                "adx": adx,
                "plus_di": plus_di,
                "minus_di": minus_di,
                "di_bias": di_bias,

                "vwap": vwap_value,
                "price_vs_vwap": vwap_position,

                "market_regime": regime,

                "support": sr[
                    "support"
                ],

                "resistance": sr[
                    "resistance"
                ],

                "volume": volume,

                "market_structure": structure,

                "candle_pattern": pattern,

                "last_candle": {
                    "timestamp": str(
                        latest["timestamp"]
                    ),
                    "open": cls.safe_float(
                        latest["open"]
                    ),
                    "high": cls.safe_float(
                        latest["high"]
                    ),
                    "low": cls.safe_float(
                        latest["low"]
                    ),
                    "close": cls.safe_float(
                        latest["close"]
                    ),
                    "volume": cls.safe_float(
                        latest["volume"],
                        0,
                    ),
                },
            }

        except Exception as exc:

            return {
                "status": False,
                "error": str(exc),
            }

    # =========================================================
    # ONE TIMEFRAME
    # =========================================================

    def analyze_timeframe(
        self,
        exchange: str,
        token: str,
        timeframe: str,
        days: int = 5,
    ):

        interval = self.TIMEFRAMES.get(
            timeframe
        )

        if not interval:
            return {
                "status": False,
                "timeframe": timeframe,
                "error": (
                    "Unsupported timeframe."
                ),
            }

        result = self.fetch_candles(
            exchange=exchange,
            token=token,
            interval=interval,
            days=days,
        )

        if not result["status"]:
            return {
                "status": False,
                "timeframe": timeframe,
                "interval": interval,
                "error": result["error"],
            }

        snapshot = self.calculate_snapshot(
            result["data"]
        )

        return {
            "status": snapshot.get(
                "status",
                False,
            ),
            "timeframe": timeframe,
            "interval": interval,
            "error": snapshot.get(
                "error"
            ),
            "analysis": snapshot,
        }

    # =========================================================
    # MULTI TIMEFRAME
    # =========================================================

    def analyze_all_timeframes(
        self,
        exchange: str,
        token: str,
        days: int = 5,
    ):

        result = {
            "status": True,
            "exchange": exchange,
            "token": str(token),
            "timeframes": {},
        }

        for timeframe in self.TIMEFRAMES:

            analysis = self.analyze_timeframe(
                exchange=exchange,
                token=token,
                timeframe=timeframe,
                days=days,
            )

            result[
                "timeframes"
            ][timeframe] = analysis

        successful = sum(
            1
            for value in result[
                "timeframes"
            ].values()
            if value.get("status")
        )

        result[
            "available_timeframes"
        ] = successful

        if successful == 0:
            result["status"] = False
            result["error"] = (
                "No timeframe data available."
            )

        return result

    # =========================================================
    # MTF DIRECTION
    # =========================================================

    @staticmethod
    def multi_timeframe_direction(
        timeframe_data,
    ):

        weights = {
            "1M": 1,
            "3M": 1,
            "5M": 2,
            "15M": 3,
            "30M": 3,
            "1H": 4,
        }

        score = 0
        total_weight = 0

        details = []

        for timeframe, weight in weights.items():

            item = timeframe_data.get(
                timeframe,
                {},
            )

            if not item.get("status"):
                continue

            analysis = item.get(
                "analysis",
                {},
            )

            trend = analysis.get(
                "ema_trend"
            )

            macd = analysis.get(
                "macd_bias"
            )

            di = analysis.get(
                "di_bias"
            )

            local_score = 0

            if trend == "BULLISH":
                local_score += 1

            elif trend == "BEARISH":
                local_score -= 1

            if macd == "BULLISH":
                local_score += 1

            elif macd == "BEARISH":
                local_score -= 1

            if di == "BULLISH":
                local_score += 1

            elif di == "BEARISH":
                local_score -= 1

            score += (
                local_score
                * weight
            )

            total_weight += (
                weight * 3
            )

            details.append(
                {
                    "timeframe": timeframe,
                    "trend": trend,
                    "macd": macd,
                    "di": di,
                    "score": local_score,
                }
            )

        if total_weight == 0:
            direction = "UNAVAILABLE"
            normalized = None

        else:
            normalized = (
                score
                / total_weight
                * 100
            )

            if normalized >= 25:
                direction = "BULLISH"

            elif normalized <= -25:
                direction = "BEARISH"

            else:
                direction = "MIXED"

        return {
            "direction": direction,
            "score": EAMarketEngine.safe_float(
                normalized
            ),
            "details": details,
        }

    # =========================================================
    # FINAL MARKET SNAPSHOT
    # =========================================================

    def build_market_snapshot(
        self,
        exchange: str,
        token: str,
        days: int = 5,
    ):

        mtf = self.analyze_all_timeframes(
            exchange=exchange,
            token=token,
            days=days,
        )

        if not mtf.get("status"):
            return {
                "status": False,
                "error": mtf.get(
                    "error",
                    "Market data unavailable.",
                ),
                "exchange": exchange,
                "token": str(token),
                "timeframes": {},
            }

        direction = (
            self.multi_timeframe_direction(
                mtf["timeframes"]
            )
        )

        return {
            "status": True,
            "timestamp": datetime.datetime.now().isoformat(),
            "exchange": exchange,
            "token": str(token),
            "available_timeframes": mtf[
                "available_timeframes"
            ],
            "multi_timeframe_direction": direction,
            "timeframes": mtf[
                "timeframes"
            ],

            # Deliberately unavailable here.
            # These will come from the Options/Market
            # Intelligence layer only when real data exists.
            "india_vix": {
                "status": "UNAVAILABLE"
            },

            "market_breadth": {
                "status": "UNAVAILABLE"
            },

            "news_sentiment": {
                "status": "UNAVAILABLE"
            },

            "options_data": {
                "status": "UNAVAILABLE"
            },
        }
