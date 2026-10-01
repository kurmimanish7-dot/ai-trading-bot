import datetime
import pandas as pd


class TelemetryEngine:
    """
    Angel One SmartAPI market-data engine.

    PAPER TRADING ONLY.
    This class only reads market data.
    It does NOT place orders.
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
    # LIVE / LAST AVAILABLE PRICE
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

                if (
                    ltp is not None
                    and ltp > 0
                ):
                    return {
                        "status": True,
                        "exchange": exchange,
                        "tradingsymbol": tradingsymbol,
                        "symboltoken": str(symboltoken),
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
                        "symboltoken": str(symboltoken),
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
        """
        Fetch historical OHLCV.

        Does NOT require 30 candles.
        This is important for after-market operation.
        """

        if not token:
            return pd.DataFrame()

        try:
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

            from_date = start.strftime(
                "%Y-%m-%d 09:15"
            )

            to_date = now.strftime(
                "%Y-%m-%d %H:%M"
            )

            params = {
                "exchange": str(exchange),
                "symboltoken": str(token),
                "interval": str(interval),
                "fromdate": from_date,
                "todate": to_date,
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
                return df

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
            ).copy()

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
    # LAST HISTORICAL CANDLE
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

            if (
                df is None
                or df.empty
                or "close" not in df.columns
            ):
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

        previous_close = (
            close.shift(1)
        )

        tr1 = (
            high - low
        )

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
    def calculate_vwap(
        df,
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

        volume = pd.to_numeric(
            df.get(
                "volume",
                0,
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

        previous_close = (
            close.shift(1)
        )

        true_range = pd.concat(
            [
                high - low,
                (
                    high
                    - previous_close
                ).abs(),
                (
                    low
                    - previous_close
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

        dx = (
            100
            * (
                plus_di
                - minus_di
            ).abs()
            / (
                plus_di
                + minus_di
            ).replace(
                0,
                pd.NA,
            )
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
    def calculate_macd(
        series,
    ):
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

        macd = (
            ema12 - ema26
        )

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
    # FULL INDICATORS
    # =========================================================

    @staticmethod
    def calculate_indicators(
        df,
    ):
        """
        Static method intentionally.

        This supports both:

            TelemetryEngine.calculate_indicators(df)

        and:

            telemetry.calculate_indicators(df)
        """

        if (
            df is None
            or df.empty
        ):
            return pd.DataFrame()

        work = df.copy()

        required = [
            "open",
            "high",
            "low",
            "close",
        ]

        for column in required:
            if column not in work.columns:
                return pd.DataFrame()

        work["ema9"] = (
            TelemetryEngine.calculate_ema(
                work["close"],
                9,
            )
        )

        work["ema20"] = (
            TelemetryEngine.calculate_ema(
                work["close"],
                20,
            )
        )

        work["ema50"] = (
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
                work,
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

        return work

    # =========================================================
    # MARKET PAYLOAD
    # =========================================================

    @staticmethod
    def build_payload(
        df,
    ):
        if (
            df is None
            or df.empty
        ):
            return {}

        work = (
            TelemetryEngine
            .calculate_indicators(df)
        )

        if work.empty:
            return {}

        last = work.iloc[-1]

        def value(column):
            try:
                result = float(
                    last.get(column)
                )

                if pd.isna(result):
                    return None

                return result

            except Exception:
                return None

        return {
            "timestamp": str(
                last.get(
                    "timestamp",
                    "",
                )
            ),
            "open": value("open"),
            "high": value("high"),
            "low": value("low"),
            "close": value("close"),
            "volume": value("volume"),
            "ema9": value("ema9"),
            "ema20": value("ema20"),
            "ema50": value("ema50"),
            "rsi": value("rsi"),
            "atr": value("atr"),
            "adx": value("adx"),
            "vwap": value("vwap"),
            "macd": value("macd"),
            "macd_signal": value(
                "macd_signal"
            ),
            "macd_hist": value(
                "macd_hist"
            ),
        }

    # =========================================================
    # NUMBER HELPER
    # =========================================================

    @staticmethod
    def _number(
        value,
    ):
        try:
            if value is None:
                return None

            result = float(value)

            if pd.isna(result):
                return None

            return result

        except Exception:
            return None
