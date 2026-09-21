import datetime
from typing import Dict, Any

import pandas as pd
import numpy as np
from SmartApi import SmartConnect


class TelemetryEngine:
    """
    Market telemetry engine.

    Responsibilities:
    - Angel One SmartAPI login
    - Historical OHLCV candle retrieval
    - Technical indicator calculation
    - AI telemetry payload generation

    IMPORTANT:
    This module does NOT generate fake VIX, OI, PCR or news data.
    If those data sources are unavailable, they are marked unavailable.
    """

    def __init__(
        self,
        api_key: str,
        client_code: str,
        pin: str,
        totp_secret: str
    ):
        self.smart_api = SmartConnect(
            api_key=api_key
        )

        totp = __import__("pyotp").TOTP(
            totp_secret
        ).now()

        session = self.smart_api.generateSession(
            client_code,
            pin,
            totp
        )

        if not session or not session.get("status"):
            raise RuntimeError(
                f"Angel One login failed: {session}"
            )

        self.feed_token = self.smart_api.getfeedToken()

    # ========================================================
    # FETCH OHLCV
    # ========================================================

    def fetch_ohlcv(
        self,
        exchange: str,
        token: str,
        interval: str,
        days: int = 5
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV candles from Angel One.
        """

        to_date = datetime.datetime.now()

        from_date = (
            to_date
            - datetime.timedelta(days=days)
        )

        params = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": interval,
            "fromdate": from_date.strftime(
                "%Y-%m-%d 09:15"
            ),
            "todate": to_date.strftime(
                "%Y-%m-%d %H:%M"
            ),
        }

        response = self.smart_api.getCandleData(
            params
        )

        if (
            not response
            or not response.get("status")
            or not response.get("data")
        ):
            raise ValueError(
                f"Failed to fetch candle data: {response}"
            )

        df = pd.DataFrame(
            response["data"],
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
            df["timestamp"]
        )

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        df[numeric_columns] = (
            df[numeric_columns]
            .apply(pd.to_numeric, errors="coerce")
        )

        df = df.dropna(
            subset=numeric_columns
        ).reset_index(drop=True)

        if len(df) < 30:
            raise ValueError(
                "Insufficient candle data for indicators."
            )

        return df

    # ========================================================
    # RSI
    # ========================================================

    @staticmethod
    def calculate_rsi(
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:

        delta = close.diff()

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

    # ========================================================
    # ATR
    # ========================================================

    @staticmethod
    def calculate_atr(
        df: pd.DataFrame,
        period: int = 14
    ) -> pd.Series:

        high_low = (
            df["high"]
            - df["low"]
        )

        high_close = (
            df["high"]
            - df["close"].shift()
        ).abs()

        low_close = (
            df["low"]
            - df["close"].shift()
        ).abs()

        true_range = pd.concat(
            [
                high_low,
                high_close,
                low_close,
            ],
            axis=1,
        ).max(axis=1)

        return true_range.rolling(
            period
        ).mean()

    # ========================================================
    # EMA
    # ========================================================

    @staticmethod
    def calculate_ema(
        close: pd.Series,
        period: int
    ) -> pd.Series:

        return close.ewm(
            span=period,
            adjust=False
        ).mean()

    # ========================================================
    # ADX
    # ========================================================

    @staticmethod
    def calculate_adx(
        df: pd.DataFrame,
        period: int = 14
    ) -> pd.Series:

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
                0.0
            ),
            index=df.index
        )

        minus_dm = pd.Series(
            np.where(
                (down_move > up_move)
                & (down_move > 0),
                down_move,
                0.0
            ),
            index=df.index
        )

        tr1 = high - low

        tr2 = (
            high
            - close.shift()
        ).abs()

        tr3 = (
            low
            - close.shift()
        ).abs()

        tr = pd.concat(
            [tr1, tr2, tr3],
            axis=1
        ).max(axis=1)

        atr = tr.rolling(
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

        return dx.rolling(
            period
        ).mean()

    # ========================================================
    # VWAP
    # ========================================================

    @staticmethod
    def calculate_vwap(
        df: pd.DataFrame
    ) -> pd.Series:

        typical_price = (
            df["high"]
            + df["low"]
            + df["close"]
        ) / 3

        cumulative_value = (
            typical_price
            * df["volume"]
        ).cumsum()

        cumulative_volume = (
            df["volume"]
            .cumsum()
        )

        return cumulative_value / (
            cumulative_volume + 1e-9
        )

    # ========================================================
    # SUPERTREND
    # ========================================================

    @staticmethod
    def calculate_supertrend(
        df: pd.DataFrame,
        period: int = 10,
        multiplier: float = 3.0
    ) -> pd.Series:
        """
        Returns:
            1  = bullish
           -1  = bearish
        """

        atr = TelemetryEngine.calculate_atr(
            df,
            period
        )

        hl2 = (
            df["high"]
            + df["low"]
        ) / 2

        upper_band = (
            hl2
            + multiplier * atr
        )

        lower_band = (
            hl2
            - multiplier * atr
        )

        direction = pd.Series(
            1,
            index=df.index,
            dtype=int
        )

        for i in range(1, len(df)):

            previous_close = df.loc[
                i - 1,
                "close"
            ]

            if previous_close > upper_band.iloc[i - 1]:

                direction.iloc[i] = 1

            elif previous_close < lower_band.iloc[i - 1]:

                direction.iloc[i] = -1

            else:

                direction.iloc[i] = (
                    direction.iloc[i - 1]
                )

        return direction

    # ========================================================
    # INDICATORS
    # ========================================================

    @staticmethod
    def calculate_indicators(
        df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Calculate technical indicators from candles.
        """

        rsi = (
            TelemetryEngine.calculate_rsi(
                df["close"]
            )
        )

        atr = (
            TelemetryEngine.calculate_atr(
                df
            )
        )

        ema_9 = (
            TelemetryEngine.calculate_ema(
                df["close"],
                9
            )
        )

        ema_21 = (
            TelemetryEngine.calculate_ema(
                df["close"],
                21
            )
        )

        ema_50 = (
            TelemetryEngine.calculate_ema(
                df["close"],
                50
            )
        )

        adx = (
            TelemetryEngine.calculate_adx(
                df
            )
        )

        vwap = (
            TelemetryEngine.calculate_vwap(
                df
            )
        )

        supertrend = (
            TelemetryEngine.calculate_supertrend(
                df
            )
        )

        latest = df.iloc[-1]

        close = float(
            latest["close"]
        )

        current_vwap = float(
            vwap.iloc[-1]
        )

        current_supertrend = int(
            supertrend.iloc[-1]
        )

        if close > current_vwap:
            price_relation = "ABOVE"
        elif close < current_vwap:
            price_relation = "BELOW"
        else:
            price_relation = "AT"

        if (
            ema_9.iloc[-1]
            > ema_21.iloc[-1]
            > ema_50.iloc[-1]
        ):
            ema_trend = "BULLISH"

        elif (
            ema_9.iloc[-1]
            < ema_21.iloc[-1]
            < ema_50.iloc[-1]
        ):
            ema_trend = "BEARISH"

        else:
            ema_trend = "MIXED"

        if current_supertrend == 1:
            supertrend_label = "BULLISH"
        else:
            supertrend_label = "BEARISH"

        if (
            not pd.isna(adx.iloc[-1])
            and adx.iloc[-1] >= 25
        ):
            regime = "TRENDING"

        else:
            regime = "RANGE_OR_WEAK_TREND"

        recent_candles = (
            df.tail(5)
            [
                [
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
            ]
            .to_dict(
                orient="records"
            )
        )

        return {
            "ltp": round(close, 2),
            "rsi": round(
                float(rsi.iloc[-1]),
                2
            ),
            "atr": round(
                float(atr.iloc[-1]),
                2
            ),
            "ema_9": round(
                float(ema_9.iloc[-1]),
                2
            ),
            "ema_21": round(
                float(ema_21.iloc[-1]),
                2
            ),
            "ema_50": round(
                float(ema_50.iloc[-1]),
                2
            ),
            "adx": round(
                float(adx.iloc[-1]),
                2
            ),
            "vwap": round(
                current_vwap,
                2
            ),
            "price_vs_vwap": price_relation,
            "ema_trend": ema_trend,
            "supertrend": supertrend_label,
            "market_regime": regime,
            "recent_candles": recent_candles,
        }

    # ========================================================
    # BUILD AI PAYLOAD
    # ========================================================

    def build_payload(
        self,
        symbol: str,
        token: str,
        position_state: dict,
        exchange: str = "NSE",
        interval: str = "FIVE_MINUTE",
        days: int = 2,
    ) -> str:
        """
        Build clean telemetry payload for Gemini.

        No fabricated external data is included.
        """

        df = self.fetch_ohlcv(
            exchange=exchange,
            token=token,
            interval=interval,
            days=days,
        )

        indicators = (
            self.calculate_indicators(df)
        )

        now_str = (
            datetime.datetime.now()
            .strftime("%Y-%m-%d %H:%M:%S IST")
        )

        payload = f"""
Assess the following market telemetry
for {symbol}.

Timestamp:
{now_str}

=== MARKET DATA ===

Exchange:
{exchange}

Instrument Token:
{token}

Candle Interval:
{interval}

Latest Price:
₹{indicators["ltp"]}

=== TECHNICAL INDICATORS ===

RSI (14):
{indicators["rsi"]}

ATR (14):
{indicators["atr"]}

EMA 9:
{indicators["ema_9"]}

EMA 21:
{indicators["ema_21"]}

EMA 50:
{indicators["ema_50"]}

ADX (14):
{indicators["adx"]}

Market Regime:
{indicators["market_regime"]}

VWAP:
₹{indicators["vwap"]}

Price vs VWAP:
{indicators["price_vs_vwap"]}

EMA Trend:
{indicators["ema_trend"]}

Supertrend:
{indicators["supertrend"]}

=== RECENT CANDLES ===

{indicators["recent_candles"]}

=== EXTERNAL DATA ===

India VIX:
UNAVAILABLE

Open Interest:
UNAVAILABLE

Put-Call Ratio:
UNAVAILABLE

Live News:
UNAVAILABLE

Do NOT assume or invent any unavailable
external data.

=== ACTIVE POSITION ===

Has Position:
{position_state.get("has_position", False)}

Direction:
{position_state.get("direction", "NONE")}

Entry Price:
₹{position_state.get("entry_price", 0.0)}

Stop Loss:
₹{position_state.get("stop_loss", 0.0)}

Target 1:
₹{position_state.get("target_1", 0.0)}

Target 2:
₹{position_state.get("target_2", 0.0)}

Bars Held:
{position_state.get("bars_held", 0)}

Return strictly valid JSON according
to the system schema.
"""

        return payload
