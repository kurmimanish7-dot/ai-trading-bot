import datetime
import pandas as pd


class TelemetryEngine:
    """
    Angel One SmartAPI telemetry engine.

    PAPER TRADING ONLY.
    Market data / indicators only.
    No real orders.
    """

    def __init__(
        self,
        api_key,
        client_code,
        pin,
        totp_secret,
    ):
        from SmartApi import SmartConnect
        import pyotp

        self.smart_api = SmartConnect(
            api_key=api_key
        )

        totp = pyotp.TOTP(
            totp_secret
        ).now()

        session = self.smart_api.generateSession(
            client_code,
            pin,
            totp,
        )

        if not session:
            raise RuntimeError(
                "Angel One login returned no response."
            )

        if not session.get("status"):
            raise RuntimeError(
                f"Angel One login failed: {session}"
            )

        try:
            self.feed_token = (
                self.smart_api.getfeedToken()
            )
        except Exception:
            self.feed_token = None

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _number(value, default=None):
        try:
            if value is None:
                return default

            if isinstance(value, pd.Series):
                if value.empty:
                    return default
                value = value.iloc[-1]

            if isinstance(value, pd.DataFrame):
                if value.empty:
                    return default
                value = value.iloc[-1, -1]

            value = float(value)

            if pd.isna(value):
                return default

            return value

        except Exception:
            return default

    @staticmethod
    def _last_value(series, default=None):
        try:
            if series is None:
                return default

            s = pd.to_numeric(
                series,
                errors="coerce"
            )

            if s.empty:
                return default

            value = s.iloc[-1]

            if pd.isna(value):
                return default

            return float(value)

        except Exception:
            return default

    # =========================================================
    # LIVE LTP
    # =========================================================

    def get_live_ltp(
        self,
        exchange,
        tradingsymbol,
        symboltoken,
    ):
        try:
            response = self.smart_api.ltpData(
                exchange,
                tradingsymbol,
                str(symboltoken),
            )

            if not response:
                return {
                    "status": False,
                    "error": "Empty LTP response.",
                }

            data = response.get("data")

            if isinstance(data, dict):

                ltp = self._number(
                    data.get("ltp")
                )

                open_price = self._number(
                    data.get("open")
                )

                high_price = self._number(
                    data.get("high")
                )

                low_price = self._number(
                    data.get("low")
                )

                close_price = self._number(
                    data.get("close")
                )

                if ltp is not None and ltp > 0:
                    return {
                        "status": True,
                        "exchange": exchange,
                        "tradingsymbol": tradingsymbol,
                        "symboltoken": str(
                            symboltoken
                        ),
                        "ltp": ltp,
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "source": "ANGEL_LTP",
                    }

                if (
                    close_price is not None
                    and close_price > 0
                ):
                    return {
                        "status": True,
                        "exchange": exchange,
                        "tradingsymbol": tradingsymbol,
                        "symboltoken": str(
                            symboltoken
                        ),
                        "ltp": close_price,
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "source": "ANGEL_CLOSE",
                    }

            return {
                "status": False,
                "error": str(
                    response.get(
                        "message",
                        "LTP unavailable.",
                    )
                ),
            }

        except Exception as exc:
            return {
                "status": False,
                "error": str(exc),
            }

    # =========================================================
    # HISTORICAL OHLCV
    # =========================================================

    def fetch_ohlcv(
        self,
        exchange,
        token,
        interval="FIVE_MINUTE",
        days=5,
    ):
        try:
            if not token:
                return pd.DataFrame()

            now = datetime.datetime.now()

            days = max(
                int(days or 1),
                1,
            )

            start = (
                now
                - datetime.timedelta(
                    days=days
                )
            )

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

            response = (
                self.smart_api.getCandleData(
                    params
                )
            )

            if not response:
                return pd.DataFrame()

            if not response.get("status"):
                return pd.DataFrame()

            rows = response.get("data")

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)

            if df.empty:
                return pd.DataFrame()

            if len(df.columns) < 6:
                return pd.DataFrame()

            df = df.iloc[:, :6].copy()

            df.columns = [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]

            df["timestamp"] = pd.to_datetime(
                df["timestamp"],
                errors="coerce",
            )

            for column in [
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]:
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
            )

            if df.empty:
                return pd.DataFrame()

            df["volume"] = (
                df["volume"]
                .fillna(0)
            )

            df = (
                df.drop_duplicates(
                    subset=["timestamp"],
                    keep="last",
                )
                .sort_values(
                    "timestamp"
                )
                .reset_index(
                    drop=True
                )
            )

            return df

        except Exception:
            return pd.DataFrame()

    # =========================================================
    # LAST CANDLE
    # =========================================================

    def get_last_candle(
        self,
        exchange,
        token,
        interval="ONE_DAY",
        days=15,
    ):
        try:
            df = self.fetch_ohlcv(
                exchange=exchange,
                token=token,
                interval=interval,
                days=days,
            )

            if df is None or df.empty:
                return None

            row = df.iloc[-1]

            close_price = self._number(
                row.get("close")
            )

            if (
                close_price is None
                or close_price <= 0
            ):
                return None

            return {
                "timestamp": row.get(
                    "timestamp"
                ),
                "open": self._number(
                    row.get("open")
                ),
                "high": self._number(
                    row.get("high")
                ),
                "low": self._number(
                    row.get("low")
                ),
                "close": close_price,
                "volume": self._number(
                    row.get("volume")
                ) or 0,
                "source": "HISTORICAL_CANDLE",
            }

        except Exception:
            return None

    # =========================================================
    # RSI
    # =========================================================

    @staticmethod
    def calculate_rsi(
        series,
        period=14,
    ):
        series = pd.to_numeric(
            series,
            errors="coerce",
        )

        delta = series.diff()

        gain = delta.clip(
            lower=0
        )

        loss = -delta.clip(
            upper=0
        )

        avg_gain = gain.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

        avg_loss = loss.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

        rs = (
            avg_gain
            / avg_loss.replace(
                0,
                pd.NA,
            )
        )

        return 100 - (
            100 / (1 + rs)
        )

    # =========================================================
    # EMA
    # =========================================================

    @staticmethod
    def calculate_ema(
        series,
        period,
    ):
        return (
            pd.to_numeric(
                series,
                errors="coerce",
            )
            .ewm(
                span=period,
                adjust=False,
            )
            .mean()
        )

    # =========================================================
    # ATR
    # =========================================================

    @staticmethod
    def calculate_atr(
        df,
        period=14,
    ):
        high = pd.to_numeric(
            df["high"],
            errors="coerce",
        )

        low = pd.to_numeric(
            df["low"],
            errors="coerce",
        )

        close = pd.to_numeric(
            df["close"],
            errors="coerce",
        )

        previous_close = close.shift(1)

        tr1 = high - low

        tr2 = (
            high - previous_close
        ).abs()

        tr3 = (
            low - previous_close
        ).abs()

        true_range = pd.concat(
            [
                tr1,
                tr2,
                tr3,
            ],
            axis=1,
        ).max(axis=1)

        return true_range.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

    # =========================================================
    # VWAP
    # =========================================================

    @staticmethod
    def calculate_vwap(df):

        high = pd.to_numeric(
            df["high"],
            errors="coerce",
        )

        low = pd.to_numeric(
            df["low"],
            errors="coerce",
        )

        close = pd.to_numeric(
            df["close"],
            errors="coerce",
        )

        volume = pd.to_numeric(
            df.get(
                "volume",
                pd.Series(
                    0,
                    index=df.index,
                )
            ),
            errors="coerce",
        ).fillna(0)

        typical_price = (
            high + low + close
        ) / 3

        cumulative_volume = (
            volume.cumsum()
        )

        cumulative_value = (
            typical_price * volume
        ).cumsum()

        return (
            cumulative_value
            / cumulative_volume.replace(
                0,
                pd.NA,
            )
        )

    # =========================================================
    # ADX
    # =========================================================

    @staticmethod
    def calculate_adx(
        df,
        period=14,
    ):
        high = pd.to_numeric(
            df["high"],
            errors="coerce",
        )

        low = pd.to_numeric(
            df["low"],
            errors="coerce",
        )

        close = pd.to_numeric(
            df["close"],
            errors="coerce",
        )

        up_move = high.diff()

        down_move = -low.diff()

        plus_dm = pd.Series(
            0.0,
            index=df.index,
        )

        minus_dm = pd.Series(
            0.0,
            index=df.index,
        )

        plus_dm[
            (up_move > down_move)
            & (up_move > 0)
        ] = up_move

        minus_dm[
            (down_move > up_move)
            & (down_move > 0)
        ] = down_move

        previous_close = close.shift(1)

        true_range = pd.concat(
            [
                high - low,
                (
                    high - previous_close
                ).abs(),
                (
                    low - previous_close
                ).abs(),
            ],
            axis=1,
        ).max(axis=1)

        atr = true_range.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

        plus_di = (
            100
            * plus_dm.ewm(
                alpha=1 / period,
                adjust=False,
                min_periods=period,
            ).mean()
            / atr.replace(
                0,
                pd.NA,
            )
        )

        minus_di = (
            100
            * minus_dm.ewm(
                alpha=1 / period,
                adjust=False,
                min_periods=period,
            ).mean()
            / atr.replace(
                0,
                pd.NA,
            )
        )

        denominator = (
            plus_di + minus_di
        ).replace(
            0,
            pd.NA,
        )

        dx = (
            100
            * (
                plus_di - minus_di
            ).abs()
            / denominator
        )

        return dx.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

    # =========================================================
    # MACD
    # =========================================================

    @staticmethod
    def calculate_macd(series):

        close = pd.to_numeric(
            series,
            errors="coerce",
        )

        ema12 = close.ewm(
            span=12,
            adjust=False,
        ).mean()

        ema26 = close.ewm(
            span=26,
            adjust=False,
        ).mean()

        macd = ema12 - ema26

        signal = macd.ewm(
            span=9,
            adjust=False,
        ).mean()

        histogram = (
            macd - signal
        )

        return (
            macd,
            signal,
            histogram,
        )

    # =========================================================
    # INDICATOR ENGINE
    #
    # IMPORTANT:
    # Existing offline_market_simulator.py expects
    # a DICTIONARY of latest indicator values.
    # =========================================================

    @staticmethod
    def calculate_indicators(df):

        if (
            df is None
            or not isinstance(
                df,
                pd.DataFrame
            )
            or df.empty
        ):
            return {}

        work = df.copy()

        # -----------------------------------------------------
        # Normalize names
        # -----------------------------------------------------

        rename = {}

        for column in work.columns:

            name = str(
                column
            ).strip().lower()

            if name in [
                "timestamp",
                "time",
                "datetime",
                "date",
            ]:
                rename[column] = "timestamp"

            elif name in [
                "open",
                "o",
            ]:
                rename[column] = "open"

            elif name in [
                "high",
                "h",
            ]:
                rename[column] = "high"

            elif name in [
                "low",
                "l",
            ]:
                rename[column] = "low"

            elif name in [
                "close",
                "c",
            ]:
                rename[column] = "close"

            elif name in [
                "ltp",
                "lastprice",
                "last_price",
            ]:
                rename[column] = "ltp"

            elif name in [
                "volume",
                "vol",
            ]:
                rename[column] = "volume"

        work = work.rename(
            columns=rename
        )

        # -----------------------------------------------------
        # Close / LTP compatibility
        # -----------------------------------------------------

        if (
            "close" not in work.columns
            and "ltp" in work.columns
        ):
            work["close"] = work["ltp"]

        if "close" not in work.columns:
            return {}

        # -----------------------------------------------------
        # OHLC fallback
        # -----------------------------------------------------

        if "open" not in work.columns:
            work["open"] = work["close"]

        if "high" not in work.columns:
            work["high"] = work["close"]

        if "low" not in work.columns:
            work["low"] = work["close"]

        if "volume" not in work.columns:
            work["volume"] = 0

        # -----------------------------------------------------
        # Numeric conversion
        # -----------------------------------------------------

        for column in [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]:
            work[column] = pd.to_numeric(
                work[column],
                errors="coerce",
            )

        work = work.dropna(
            subset=[
                "open",
                "high",
                "low",
                "close",
            ]
        ).reset_index(
            drop=True
        )

        if work.empty:
            return {}

        # -----------------------------------------------------
        # LTP
        # -----------------------------------------------------

        work["ltp"] = work["close"]

        # If actual LTP column existed, use it
        # where valid.
        if "ltp" in df.columns:
            original_ltp = pd.to_numeric(
                df["ltp"],
                errors="coerce"
            )

            if len(original_ltp) == len(work):
                original_ltp = (
                    original_ltp
                    .reset_index(drop=True)
                )

                work["ltp"] = (
                    original_ltp
                    .fillna(work["close"])
                )

        # -----------------------------------------------------
        # Indicators
        # -----------------------------------------------------

        work["ema_9"] = (
            TelemetryEngine.calculate_ema(
                work["close"],
                9,
            )
        )

        work["ema_21"] = (
            TelemetryEngine.calculate_ema(
                work["close"],
                21,
            )
        )

        work["ema_50"] = (
            TelemetryEngine.calculate_ema(
                work["close"],
                50,
            )
        )

        work["rsi"] = (
            TelemetryEngine.calculate_rsi(
                work["close"],
                14,
            )
        )

        work["atr"] = (
            TelemetryEngine.calculate_atr(
                work,
                14,
            )
        )

        work["adx"] = (
            TelemetryEngine.calculate_adx(
                work,
                14,
            )
        )

        work["vwap"] = (
            TelemetryEngine.calculate_vwap(
                work
            )
        )

        macd, signal, histogram = (
            TelemetryEngine.calculate_macd(
                work["close"]
            )
        )

        work["macd"] = macd
        work["macd_signal"] = signal
        work["macd_hist"] = histogram

        # -----------------------------------------------------
        # Latest values
        # -----------------------------------------------------

        latest = work.iloc[-1]

        ltp = TelemetryEngine._number(
            latest.get("ltp")
        )

        close = TelemetryEngine._number(
            latest.get("close")
        )

        ema_9 = TelemetryEngine._number(
            latest.get("ema_9")
        )

        ema_21 = TelemetryEngine._number(
            latest.get("ema_21")
        )

        ema_50 = TelemetryEngine._number(
            latest.get("ema_50")
        )

        rsi = TelemetryEngine._number(
            latest.get("rsi")
        )

        atr = TelemetryEngine._number(
            latest.get("atr")
        )

        adx = TelemetryEngine._number(
            latest.get("adx")
        )

        vwap = TelemetryEngine._number(
            latest.get("vwap")
        )

        macd = TelemetryEngine._number(
            latest.get("macd")
        )

        macd_signal = TelemetryEngine._number(
            latest.get("macd_signal")
        )

        macd_hist = TelemetryEngine._number(
            latest.get("macd_hist")
        )

        # -----------------------------------------------------
        # Price vs VWAP
        # -----------------------------------------------------

        if (
            close is not None
            and vwap is not None
        ):
            if close > vwap:
                price_vs_vwap = "ABOVE"
            elif close < vwap:
                price_vs_vwap = "BELOW"
            else:
                price_vs_vwap = "AT VWAP"
        else:
            price_vs_vwap = "UNKNOWN"

        # -----------------------------------------------------
        # EMA trend
        # -----------------------------------------------------

        if (
            ema_9 is not None
            and ema_21 is not None
            and ema_50 is not None
        ):
            if (
                ema_9 > ema_21
                and ema_21 > ema_50
            ):
                ema_trend = "BULLISH"

            elif (
                ema_9 < ema_21
                and ema_21 < ema_50
            ):
                ema_trend = "BEARISH"

            else:
                ema_trend = "MIXED"
        else:
            ema_trend = "UNKNOWN"

        # -----------------------------------------------------
        # Supertrend-style directional state
        #
        # This is a lightweight offline compatibility value.
        # -----------------------------------------------------

        if (
            close is not None
            and atr is not None
        ):
            upper = close + (
                2.0 * atr
            )

            lower = close - (
                2.0 * atr
            )

            if close > lower:
                supertrend = "BULLISH"
            elif close < upper:
                supertrend = "BEARISH"
            else:
                supertrend = "NEUTRAL"
        else:
            supertrend = "UNKNOWN"

        # -----------------------------------------------------
        # Market regime
        # -----------------------------------------------------

        if (
            ema_trend == "BULLISH"
            and rsi is not None
            and rsi >= 55
            and adx is not None
            and adx >= 20
        ):
            market_regime = "TRENDING BULLISH"

        elif (
            ema_trend == "BEARISH"
            and rsi is not None
            and rsi <= 45
            and adx is not None
            and adx >= 20
        ):
            market_regime = "TRENDING BEARISH"

        elif (
            adx is not None
            and adx < 20
        ):
            market_regime = "RANGE / WEAK TREND"

        else:
            market_regime = "MIXED"

        # -----------------------------------------------------
        # Recent candles
        # -----------------------------------------------------

        recent_candles = []

        recent = work.tail(5)

        for _, row in recent.iterrows():

            recent_candles.append({
                "timestamp": str(
                    row.get(
                        "timestamp",
                        ""
                    )
                ),
                "open": TelemetryEngine._number(
                    row.get("open")
                ),
                "high": TelemetryEngine._number(
                    row.get("high")
                ),
                "low": TelemetryEngine._number(
                    row.get("low")
                ),
                "close": TelemetryEngine._number(
                    row.get("close")
                ),
                "volume": TelemetryEngine._number(
                    row.get("volume"),
                    0
                ),
            })

        # -----------------------------------------------------
        # Return DICTIONARY
        #
        # These names are required by the existing
        # offline_market_simulator.py.
        # -----------------------------------------------------

        return {
            "ltp": ltp,
            "close": close,

            "rsi": rsi,
            "atr": atr,

            "ema_9": ema_9,
            "ema_21": ema_21,
            "ema_50": ema_50,

            "adx": adx,
            "vwap": vwap,

            "macd": macd,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,

            "price_vs_vwap": price_vs_vwap,
            "ema_trend": ema_trend,
            "supertrend": supertrend,
            "market_regime": market_regime,

            "recent_candles": recent_candles,
        }

    # =========================================================
    # BUILD PAYLOAD
    # =========================================================

    @staticmethod
    def build_payload(df):

        indicators = (
            TelemetryEngine.calculate_indicators(
                df
            )
        )

        if not indicators:
            return {}

        return {
            "timestamp": (
                str(
                    df.iloc[-1].get(
                        "timestamp",
                        ""
                    )
                )
                if isinstance(
                    df,
                    pd.DataFrame
                )
                and not df.empty
                else ""
            ),

            "ltp": indicators.get(
                "ltp"
            ),

            "open": (
                TelemetryEngine._number(
                    df.iloc[-1].get("open")
                )
                if not df.empty
                else None
            ),

            "high": (
                TelemetryEngine._number(
                    df.iloc[-1].get("high")
                )
                if not df.empty
                else None
            ),

            "low": (
                TelemetryEngine._number(
                    df.iloc[-1].get("low")
                )
                if not df.empty
                else None
            ),

            "close": indicators.get(
                "close"
            ),

            "volume": (
                TelemetryEngine._number(
                    df.iloc[-1].get(
                        "volume"
                    ),
                    0
                )
                if not df.empty
                else 0
            ),

            "ema9": indicators.get(
                "ema_9"
            ),

            "ema20": indicators.get(
                "ema_21"
            ),

            "ema50": indicators.get(
                "ema_50"
            ),

            "rsi": indicators.get(
                "rsi"
            ),

            "atr": indicators.get(
                "atr"
            ),

            "adx": indicators.get(
                "adx"
            ),

            "vwap": indicators.get(
                "vwap"
            ),

            "macd": indicators.get(
                "macd"
            ),

            "macd_signal": indicators.get(
                "macd_signal"
            ),

            "macd_hist": indicators.get(
                "macd_hist"
            ),

            "price_vs_vwap": indicators.get(
                "price_vs_vwap"
            ),

            "ema_trend": indicators.get(
                "ema_trend"
            ),

            "supertrend": indicators.get(
                "supertrend"
            ),

            "market_regime": indicators.get(
                "market_regime"
            ),
        }
