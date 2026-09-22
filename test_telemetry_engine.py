import unittest

import numpy as np
import pandas as pd

from telemetry_engine import TelemetryEngine


class TestTelemetryEngine(unittest.TestCase):

    def setUp(self):

        self.engine = TelemetryEngine.__new__(
            TelemetryEngine
        )

        timestamps = pd.date_range(
            "2026-09-22 09:15",
            periods=80,
            freq="5min"
        )

        base_price = np.linspace(
            100,
            120,
            80
        )

        self.df = pd.DataFrame({
            "timestamp": timestamps,
            "open": base_price - 0.5,
            "high": base_price + 1.0,
            "low": base_price - 1.0,
            "close": base_price,
            "volume": np.full(80, 1000),
        })

    def test_rsi_calculation(self):

        rsi = self.engine.calculate_rsi(
            self.df["close"]
        )

        self.assertEqual(
            len(rsi),
            len(self.df)
        )

        self.assertFalse(
            pd.isna(rsi.iloc[-1])
        )

        self.assertGreaterEqual(
            rsi.iloc[-1],
            0
        )

        self.assertLessEqual(
            rsi.iloc[-1],
            100
        )

    def test_atr_calculation(self):

        atr = self.engine.calculate_atr(
            self.df
        )

        self.assertEqual(
            len(atr),
            len(self.df)
        )

        self.assertFalse(
            pd.isna(atr.iloc[-1])
        )

        self.assertGreater(
            atr.iloc[-1],
            0
        )

    def test_ema_calculation(self):

        ema = self.engine.calculate_ema(
            self.df["close"],
            21
        )

        self.assertEqual(
            len(ema),
            len(self.df)
        )

        self.assertFalse(
            pd.isna(ema.iloc[-1])
        )

    def test_adx_calculation(self):

        adx = self.engine.calculate_adx(
            self.df
        )

        self.assertEqual(
            len(adx),
            len(self.df)
        )

        self.assertFalse(
            pd.isna(adx.iloc[-1])
        )

        self.assertGreaterEqual(
            adx.iloc[-1],
            0
        )

    def test_vwap_calculation(self):

        vwap = self.engine.calculate_vwap(
            self.df
        )

        self.assertEqual(
            len(vwap),
            len(self.df)
        )

        self.assertFalse(
            pd.isna(vwap.iloc[-1])
        )

        self.assertGreater(
            vwap.iloc[-1],
            0
        )

    def test_supertrend_calculation(self):

        supertrend = (
            self.engine.calculate_supertrend(
                self.df
            )
        )

        self.assertEqual(
            len(supertrend),
            len(self.df)
        )

        self.assertIn(
            int(supertrend.iloc[-1]),
            [-1, 1]
        )

    def test_all_indicators(self):

        indicators = (
            self.engine.calculate_indicators(
                self.df
            )
        )

        required_fields = [
            "ltp",
            "rsi",
            "atr",
            "ema_9",
            "ema_21",
            "ema_50",
            "adx",
            "vwap",
            "price_vs_vwap",
            "ema_trend",
            "supertrend",
            "market_regime",
            "recent_candles",
        ]

        for field in required_fields:

            self.assertIn(
                field,
                indicators
            )

        self.assertEqual(
            indicators["ltp"],
            120.0
        )

        self.assertIn(
            indicators["price_vs_vwap"],
            [
                "ABOVE",
                "BELOW",
                "AT"
            ]
        )

        self.assertIn(
            indicators["ema_trend"],
            [
                "BULLISH",
                "BEARISH",
                "MIXED"
            ]
        )

        self.assertIn(
            indicators["supertrend"],
            [
                "BULLISH",
                "BEARISH"
            ]
        )

        self.assertIn(
            indicators["market_regime"],
            [
                "TRENDING",
                "RANGE_OR_WEAK_TREND"
            ]
        )

        self.assertEqual(
            len(
                indicators["recent_candles"]
            ),
            5
        )


if __name__ == "__main__":

    unittest.main(
        verbosity=2
    )
