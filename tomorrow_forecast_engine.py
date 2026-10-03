from datetime import date, timedelta


class TomorrowForecastEngine:
    """
    Scenario-based next-session market forecast engine.

    This engine does not predict an exact future price.
    It combines currently available market inputs into a
    structured next-session blueprint.
    """

    def __init__(self, market_data=None):
        self.market_data = market_data or {}

    @staticmethod
    def _num(value, default=None):
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _text(value, default="N/A"):
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default

    @staticmethod
    def _next_weekday(value):
        current = value + timedelta(days=1)

        while current.weekday() >= 5:
            current += timedelta(days=1)

        return current

    def _calculate_range(self, spot, atr, support, resistance):
        """
        Creates a reference range using available volatility data.

        ATR is preferred. If ATR is unavailable, the existing
        support/resistance structure is used.
        """
        if spot is None:
            return None, None

        if atr is not None and atr > 0:
            low = max(0.0, spot - (atr * 1.5))
            high = spot + (atr * 1.5)
            return low, high

        if support is not None and resistance is not None:
            return support, resistance

        return None, None

    def _technical_score(self):
        return self._num(
            self.market_data.get("technical_score"),
            0.0,
        )

    def _institutional_score(self):
        return self._num(
            self.market_data.get("institutional_score"),
            0.0,
        )

    def _derivatives_score(self):
        return self._num(
            self.market_data.get("derivatives_score"),
            0.0,
        )

    def _build_bias(self):
        technical = self._technical_score()
        institutional = self._institutional_score()
        derivatives = self._derivatives_score()

        combined = technical + institutional + derivatives

        if combined >= 4:
            bias = "BULLISH"
        elif combined <= -4:
            bias = "BEARISH"
        else:
            bias = "SIDEWAYS"

        return bias, combined

    def _build_scenarios(
        self,
        spot,
        support,
        resistance,
        atr,
        bias,
    ):
        scenarios = []

        if bias == "BULLISH":
            bullish_trigger = resistance
            bearish_trigger = support

            scenarios.append(
                {
                    "scenario": "Bullish",
                    "condition": (
                        f"Price sustains above resistance "
                        f"{resistance:.2f}"
                        if resistance is not None
                        else "Price sustains above the latest resistance zone"
                    ),
                    "view": "Upside continuation can remain active.",
                }
            )

            scenarios.append(
                {
                    "scenario": "Sideways",
                    "condition": (
                        f"Price remains between "
                        f"{support:.2f} and {resistance:.2f}"
                        if support is not None and resistance is not None
                        else "Price remains inside the current range"
                    ),
                    "view": "Range-bound movement is possible.",
                }
            )

            scenarios.append(
                {
                    "scenario": "Bearish",
                    "condition": (
                        f"Price breaks and sustains below support "
                        f"{support:.2f}"
                        if support is not None
                        else "Price breaks and sustains below support"
                    ),
                    "view": "Bullish structure becomes invalid.",
                }
            )

        elif bias == "BEARISH":
            bullish_trigger = resistance
            bearish_trigger = support

            scenarios.append(
                {
                    "scenario": "Bearish",
                    "condition": (
                        f"Price breaks and sustains below support "
                        f"{support:.2f}"
                        if support is not None
                        else "Price breaks and sustains below support"
                    ),
                    "view": "Downside continuation can remain active.",
                }
            )

            scenarios.append(
                {
                    "scenario": "Sideways",
                    "condition": (
                        f"Price remains between "
                        f"{support:.2f} and {resistance:.2f}"
                        if support is not None and resistance is not None
                        else "Price remains inside the current range"
                    ),
                    "view": "Range-bound movement is possible.",
                }
            )

            scenarios.append(
                {
                    "scenario": "Bullish",
                    "condition": (
                        f"Price sustains above resistance "
                        f"{resistance:.2f}"
                        if resistance is not None
                        else "Price sustains above resistance"
                    ),
                    "view": "Bearish structure becomes invalid.",
                }
            )

        else:
            bullish_trigger = resistance
            bearish_trigger = support

            scenarios.append(
                {
                    "scenario": "Bullish",
                    "condition": (
                        f"Breakout above {resistance:.2f} with confirmation"
                        if resistance is not None
                        else "Confirmed breakout above resistance"
                    ),
                    "view": "Upside scenario activates only after confirmation.",
                }
            )

            scenarios.append(
                {
                    "scenario": "Sideways",
                    "condition": (
                        f"Price stays between "
                        f"{support:.2f} and {resistance:.2f}"
                        if support is not None and resistance is not None
                        else "Price remains inside the current range"
                    ),
                    "view": "Range trading remains the primary scenario.",
                }
            )

            scenarios.append(
                {
                    "scenario": "Bearish",
                    "condition": (
                        f"Breakdown below {support:.2f} with confirmation"
                        if support is not None
                        else "Confirmed breakdown below support"
                    ),
                    "view": "Downside scenario activates after confirmation.",
                }
            )

        return scenarios, bullish_trigger, bearish_trigger

    def build(self):
        """
        Build a complete next-session forecast dictionary.
        """

        today = date.today()
        forecast_date = self._next_weekday(today)

        symbol = self._text(
            self.market_data.get("symbol"),
            "MARKET",
        )

        spot = self._num(self.market_data.get("spot"))
        support = self._num(self.market_data.get("support"))
        resistance = self._num(self.market_data.get("resistance"))

        atr = self._num(self.market_data.get("atr"))
        rsi = self._num(self.market_data.get("rsi"))
        adx = self._num(self.market_data.get("adx"))
        ema20 = self._num(self.market_data.get("ema20"))
        ema50 = self._num(self.market_data.get("ema50"))
        vwap = self._num(self.market_data.get("vwap"))

        pcr = self._num(self.market_data.get("pcr"))

        fii_net = self._num(self.market_data.get("fii_net"))
        dii_net = self._num(self.market_data.get("dii_net"))

        technical_score = self._technical_score()
        institutional_score = self._institutional_score()
        derivatives_score = self._derivatives_score()

        bias, combined_score = self._build_bias()

        range_low, range_high = self._calculate_range(
            spot,
            atr,
            support,
            resistance,
        )

        scenarios, bullish_trigger, bearish_trigger = self._build_scenarios(
            spot,
            support,
            resistance,
            atr,
            bias,
        )

        reasons = []

        if ema20 is not None and ema50 is not None:
            if ema20 > ema50:
                reasons.append("EMA20 is above EMA50.")
            elif ema20 < ema50:
                reasons.append("EMA20 is below EMA50.")

        if vwap is not None and spot is not None:
            if spot > vwap:
                reasons.append("Price is above VWAP.")
            elif spot < vwap:
                reasons.append("Price is below VWAP.")

        if rsi is not None:
            if rsi >= 60:
                reasons.append("RSI shows positive momentum.")
            elif rsi <= 40:
                reasons.append("RSI shows negative momentum.")
            else:
                reasons.append("RSI is in a neutral momentum zone.")

        if adx is not None:
            if adx >= 25:
                reasons.append("ADX indicates a relatively strong trend.")
            else:
                reasons.append("ADX indicates limited trend strength.")

        if pcr is not None:
            if pcr > 1:
                reasons.append("PCR is above 1.")
            elif pcr < 1:
                reasons.append("PCR is below 1.")
            else:
                reasons.append("PCR is near 1.")

        if fii_net is not None:
            if fii_net > 0:
                reasons.append("FII net flow is positive.")
            elif fii_net < 0:
                reasons.append("FII net flow is negative.")

        if dii_net is not None:
            if dii_net > 0:
                reasons.append("DII net flow is positive.")
            elif dii_net < 0:
                reasons.append("DII net flow is negative.")

        data_points = 0

        for value in (
            spot,
            support,
            resistance,
            atr,
            rsi,
            adx,
            ema20,
            ema50,
            vwap,
            pcr,
            technical_score,
        ):
            if value is not None:
                data_points += 1

        if fii_net is not None:
            data_points += 1

        if dii_net is not None:
            data_points += 1

        if data_points >= 10:
            data_quality = "HIGH"
        elif data_points >= 6:
            data_quality = "MEDIUM"
        else:
            data_quality = "LOW"

        confidence = 50

        confidence += min(abs(combined_score) * 4, 25)

        if data_quality == "HIGH":
            confidence += 10
        elif data_quality == "MEDIUM":
            confidence += 5

        confidence = max(50, min(confidence, 85))

        if range_low is not None and range_high is not None:
            expected_range = {
                "low": round(range_low, 2),
                "high": round(range_high, 2),
            }
        else:
            expected_range = {
                "low": None,
                "high": None,
            }

        return {
            "symbol": symbol,
            "forecast_date": forecast_date.isoformat(),
            "generated_date": today.isoformat(),

            "bias": bias,
            "combined_score": round(combined_score, 2),
            "technical_score": round(technical_score, 2),
            "institutional_score": round(institutional_score, 2),
            "derivatives_score": round(derivatives_score, 2),

            "confidence": round(confidence, 1),
            "data_quality": data_quality,

            "spot": spot,
            "support": support,
            "resistance": resistance,
            "atr": atr,

            "expected_range": expected_range,

            "bullish_trigger": bullish_trigger,
            "bearish_trigger": bearish_trigger,

            "rsi": rsi,
            "adx": adx,
            "ema20": ema20,
            "ema50": ema50,
            "vwap": vwap,
            "pcr": pcr,

            "fii_net": fii_net,
            "dii_net": dii_net,

            "scenarios": scenarios,
            "reasons": reasons,

            "opening_gap": None,
            "opening_gap_status": "UNAVAILABLE",

            "invalidation": (
                f"Bias invalidation below support {support:.2f}"
                if bias == "BULLISH" and support is not None
                else (
                    f"Bias invalidation above resistance {resistance:.2f}"
                    if bias == "BEARISH" and resistance is not None
                    else "Wait for confirmed breakout or breakdown."
                )
            ),

            "disclaimer": (
                "Scenario-based paper-trading research only. "
                "This is not a guaranteed market prediction."
            ),
        }


def build_tomorrow_forecast(market_data):
    """
    Convenience function used by app.py.
    """

    engine = TomorrowForecastEngine(market_data)
    return engine.build()
