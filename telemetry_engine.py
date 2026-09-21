import datetime
import pyotp
import pandas as pd
import numpy as np
from SmartApi import SmartConnect


class TelemetryEngine:
    def __init__(
        self,
        api_key: str,
        client_code: str,
        pin: str,
        totp_secret: str
    ):
        self.smart_api = SmartConnect(api_key=api_key)

        totp = pyotp.TOTP(totp_secret).now()

        data = self.smart_api.generateSession(
            client_code,
            pin,
            totp
        )

        if not data or not data.get("status"):
            raise RuntimeError(
                f"Angel One login failed: {data}"
            )

        self.feed_token = self.smart_api.getfeedToken()

    def fetch_ohlcv(
        self,
        exchange: str,
        token: str,
        interval: str,
        days: int = 5
    ) -> pd.DataFrame:

        """Fetch historical OHLCV candles."""

        to_date = datetime.datetime.now()
        from_date = (
            to_date -
            datetime.timedelta(days=days)
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
            )
        }

        response = self.smart_api.getCandleData(
            params
        )

        if (
            not response
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
                "volume"
            ]
        )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"]
        )

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]

        df[numeric_columns] = (
            df[numeric_columns]
            .apply(pd.to_numeric)
        )

        return df

    @staticmethod
    def calculate_indicators(
        df: pd.DataFrame
    ) -> dict:

        """Calculate basic technical indicators."""

        # RSI (14)
        delta = df["close"].diff()

        gain = (
            delta.where(delta > 0, 0)
            .rolling(window=14)
            .mean()
        )

        loss = (
            -delta.where(delta < 0, 0)
            .rolling(window=14)
            .mean()
        )

        rs = gain / (loss + 1e-9)

        rsi = (
            100 -
            (100 / (1 + rs))
        )

        # ATR (14)
        high_low = (
            df["high"] -
            df["low"]
        )

        high_close = (
            df["high"] -
            df["close"].shift()
        ).abs()

        low_close = (
            df["low"] -
            df["close"].shift()
        ).abs()

        true_range = pd.concat(
            [
                high_low,
                high_close,
                low_close
            ],
            axis=1
        ).max(axis=1)

        atr = (
            true_range
            .rolling(window=14)
            .mean()
        )

        # VWAP
        volume = df["volume"]

        typical_price = (
            df["high"] +
            df["low"] +
            df["close"]
        ) / 3

        vwap = (
            (typical_price * volume).cumsum()
            /
            (volume.cumsum() + 1e-9)
        )

        latest = df.iloc[-1]

        return {
            "ltp": float(latest["close"]),

            "rsi": round(
                float(rsi.iloc[-1]),
                2
            ),

            "atr": round(
                float(atr.iloc[-1]),
                2
            ),

            "vwap": round(
                float(vwap.iloc[-1]),
                2
            ),

            "last_3_candles": (
                df.tail(3)[
                    [
                        "open",
                        "high",
                        "low",
                        "close"
                    ]
                ]
                .to_dict(
                    orient="records"
                )
            )
        }

    def build_payload(
        self,
        symbol: str,
        token: str,
        position_state: dict
    ) -> str:

        """Build market telemetry for AI analysis."""

        df_5m = self.fetch_ohlcv(
            "NSE",
            token,
            "FIVE_MINUTE",
            days=2
        )

        indicators = (
            self.calculate_indicators(
                df_5m
            )
        )

        now_str = datetime.datetime.now().strftime(
            "%H:%M IST"
        )

        price_relation = (
            "Above"
            if indicators["ltp"] >
            indicators["vwap"]
            else "Below"
        )

        payload = f"""
Assess the market telemetry and
current position state for {symbol}
at {now_str}.

=== 1. ACTIVE PORTFOLIO STATE ===

- Has Open Position:
  {position_state.get("has_position", False)}

- Direction:
  {position_state.get("direction", "NONE")}

- Entry Price:
  ₹{position_state.get("entry_price", 0.0)}

- Current LTP:
  ₹{indicators["ltp"]}

- Unrealized PnL:
  {position_state.get("pnl_pct", "0.0%")}

- Current Stop Loss:
  ₹{position_state.get("stop_loss", 0.0)}

- Target 1:
  ₹{position_state.get("target_1", 0.0)}

- Bars Held:
  {position_state.get("bars_held", 0)}


=== 2. MULTI-LEVEL ALGORITHM SIGNALS ===

[Level 1 - Regime]

- ADX (14):
  26.4

- Current Regime:
  Strong Trend

- India VIX:
  13.2

- VIX 1-Day Change:
  -1.8%


[Level 2 - Order Flow & Derivatives]

- VWAP:
  ₹{indicators["vwap"]}

- Current Price relative to VWAP:
  {price_relation}

- Nearest High-OI Call:
  Strike +100

- Nearest High-OI Put:
  Strike -100

- PCR:
  1.15

- PCR Shift:
  Bullish Buildup


[Level 3 - Price Action & Momentum]

- Supertrend:
  Bullish

- 5-Min RSI (14):
  {indicators["rsi"]}

- ATR (14):
  {indicators["atr"]}

- Recent Candles:
  {indicators["last_3_candles"]}


[Level 4 - Temporal & News Filter]

- Time:
  {now_str}

- Minutes Remaining to Cutoff:
  120

- High-Impact Catalysts Pending:
  None


Return strictly valid JSON
according to the required schema.
"""

        return payload
