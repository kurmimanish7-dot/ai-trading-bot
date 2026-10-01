import datetime
import pandas as pd


class TelemetryEngine:
    """
    Angel One SmartAPI telemetry engine.

    PAPER TRADING ONLY.
    Market data / indicators only.
    No real orders.
    """

    # =========================================================
    # INIT
    # =========================================================

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
    # NUMBER HELPER
    # =========================================================

    @staticmethod
    def _number(value):
        try:
            if value is None:
                return None

            value = float(value)

            if pd.isna(value):
                return None

            return value

        except Exception:
            return None

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

                if (
                    ltp is not None
                    and ltp > 0
                ):
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

        if "volume" in df.columns:
            volume = pd.to_numeric(
                df["volume"],
                errors="coerce",
            ).fillna(0)
        else:
            volume = pd.Series(
                0,
                index=df.index,
            )

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
    # INDICATORS
    # =========================================================

    @staticmethod
    def calculate_indicators(
        df,
    ):
        """
        Compatible with existing offline_market_simulator.py.

        The simulator expects:
            indicators["ltp"]

        Therefore this method explicitly creates
        the ltp column from the latest close.
        """

        if (
            df is None
            or df.empty
        ):
            return pd.DataFrame()

        work = df.copy()

        # -----------------------------------------------------
        # Normalize column names
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
                rename[column] = (
                    "timestamp"
                )

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
        # If LTP exists but close doesn't,
        # use LTP as close.
        # -----------------------------------------------------

        if (
            "close" not in work.columns
            and "ltp" in work.columns
        ):
            work["close"] = (
                work["ltp"]
            )

        required = [
            "open",
            "high",
            "low",
            "close",
        ]

        for column in required:

            if column not in work.columns:

                # Graceful fallback for
                # simple close/ltp datasets.
                if (
                    column == "open"
                    and "close" in work.columns
                ):
                    work["open"] = (
                        work["close"]
                    )

                elif (
                    column == "high"
                    and "close" in work.columns
                ):
                    work["high"] = (
                        work["close"]
                    )

                elif (
                    column == "low"
                    and "close" in work.columns
                ):
                    work["low"] = (
                        work["close"]
                    )

                else:
                    return pd.DataFrame()

        # -----------------------------------------------------
        # Numeric conversion
        # -----------------------------------------------------

        for column in [
            "open",
            "high",
            "low",
            "close",
            "ltp",
            "volume",
        ]:

            if column in work.columns:
                work[column] = pd.to_numeric(
                    work[column],
                    errors="coerce",
                )

        # -----------------------------------------------------
        # LTP compatibility
        # -----------------------------------------------------

        if "ltp" not in work.columns:

            work["ltp"] = (
                work["close"]
            )

        else:

            work["ltp"] = (
                work["ltp"]
                .fillna(
                    work["close"]
                )
            )

        # -----------------------------------------------------
        # Volume
        # -----------------------------------------------------

        if "volume" not in work.columns:
            work["volume"] = 0

        work["volume"] = (
            work["volume"]
            .fillna(0)
        )

        # -----------------------------------------------------
        # EMA
        # -----------------------------------------------------

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

        # -----------------------------------------------------
        # RSI
        # -----------------------------------------------------

        work["rsi"] = (
            TelemetryEngine.calculate_rsi(
                work["close"],
                14,
            )
        )

        # -----------------------------------------------------
        # ATR
        # -----------------------------------------------------

        work["atr"] = (
            TelemetryEngine.calculate_atr(
                work,
                14,
            )
        )

        # -----------------------------------------------------
        # ADX
        # -----------------------------------------------------

        work["adx"] = (
            TelemetryEngine.calculate_adx(
                work,
                14,
            )
        )

        # -----------------------------------------------------
        # VWAP
        # -----------------------------------------------------

        work["vwap"] = (
            TelemetryEngine.calculate_vwap(
                work
            )
        )

        # -----------------------------------------------------
        # MACD
        # -----------------------------------------------------

        macd, signal, histogram = (
            TelemetryEngine.calculate_macd(
                work["close"]
            )
        )

        work["macd"] = macd

        work["macd_signal"] = (
            signal
        )

        work["macd_hist"] = (
            histogram
        )

        return work

    # =========================================================
    # BUILD PAYLOAD
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

        indicators = (
            TelemetryEngine
            .calculate_indicators(
                df
            )
        )

        if indicators.empty:
            return {}

        last = indicators.iloc[-1]

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
            "ltp": value("ltp"),
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
