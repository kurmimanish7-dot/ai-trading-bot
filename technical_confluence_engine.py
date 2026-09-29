"""
Technical Confluence Engine
Stage 2 of the Expert Advisor architecture.

Purpose:
- Combine multi-timeframe technical data
- Score trend, momentum, price action, VWAP, S/R and volume
- Produce a deterministic confluence score
- NEVER invent market data
- This module does NOT place orders
- This module does NOT select option strikes yet

Expected input:
market_snapshot = {
    "symbol": "...",
    "mtf": {
        "1M": {...},
        "3M": {...},
        "5M": {...},
        "15M": {...},
        "30M": {...},
        "1H": {...}
    },
    "multi_timeframe_direction": {...}
}
"""


from typing import Dict, Any, List
import math


class TechnicalConfluenceEngine:
    """
    Deterministic technical scoring engine.

    It converts technical observations into:
        BULLISH
        BEARISH
        NEUTRAL
        MIXED

    and a 0-100 confluence score.

    IMPORTANT:
    This is NOT an AI prediction and NOT a probability.
    """

    # Higher timeframes get greater importance.
    TIMEFRAME_WEIGHTS = {
        "1M": 1.0,
        "3M": 1.0,
        "5M": 2.0,
        "15M": 3.0,
        "30M": 3.0,
        "1H": 4.0,
    }

    def __init__(self, minimum_trade_score: float = 70.0):
        self.minimum_trade_score = float(minimum_trade_score)

    # ---------------------------------------------------------
    # BASIC HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def _safe_float(value):
        try:
            if value is None:
                return None

            number = float(value)

            if not math.isfinite(number):
                return None

            return number

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalise_text(value) -> str:
        if value is None:
            return ""

        return str(value).strip().upper()

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
        return max(low, min(high, float(value)))

    # ---------------------------------------------------------
    # TREND SCORING
    # ---------------------------------------------------------

    def score_trend(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        score = 0.0
        reasons: List[str] = []

        price = self._safe_float(snapshot.get("price"))
        ema9 = self._safe_float(snapshot.get("ema9"))
        ema20 = self._safe_float(snapshot.get("ema20"))
        ema50 = self._safe_float(snapshot.get("ema50"))
        ema200 = self._safe_float(snapshot.get("ema200"))

        trend = self._normalise_text(snapshot.get("ema_trend"))
        supertrend = self._normalise_text(snapshot.get("supertrend"))

        available = 0
        bullish = 0
        bearish = 0

        # EMA9 vs EMA20
        if ema9 is not None and ema20 is not None:
            available += 1

            if ema9 > ema20:
                score += 15
                bullish += 1
                reasons.append("EMA9 above EMA20")
            elif ema9 < ema20:
                score -= 15
                bearish += 1
                reasons.append("EMA9 below EMA20")

        # EMA20 vs EMA50
        if ema20 is not None and ema50 is not None:
            available += 1

            if ema20 > ema50:
                score += 15
                bullish += 1
                reasons.append("EMA20 above EMA50")
            elif ema20 < ema50:
                score -= 15
                bearish += 1
                reasons.append("EMA20 below EMA50")

        # Price vs EMA50
        if price is not None and ema50 is not None:
            available += 1

            if price > ema50:
                score += 10
                bullish += 1
                reasons.append("Price above EMA50")
            elif price < ema50:
                score -= 10
                bearish += 1
                reasons.append("Price below EMA50")

        # Price vs EMA200
        if price is not None and ema200 is not None:
            available += 1

            if price > ema200:
                score += 15
                bullish += 1
                reasons.append("Price above EMA200")
            elif price < ema200:
                score -= 15
                bearish += 1
                reasons.append("Price below EMA200")

        # Existing trend label
        if trend:
            available += 1

            if "BULL" in trend or "UP" in trend:
                score += 10
                bullish += 1
                reasons.append(f"EMA trend: {trend}")

            elif "BEAR" in trend or "DOWN" in trend:
                score -= 10
                bearish += 1
                reasons.append(f"EMA trend: {trend}")

        # Supertrend
        if supertrend:
            available += 1

            if (
                supertrend in ("1", "BULLISH", "UP", "LONG")
                or "BULL" in supertrend
            ):
                score += 10
                bullish += 1
                reasons.append("Supertrend bullish")

            elif (
                supertrend in ("-1", "BEARISH", "DOWN", "SHORT")
                or "BEAR" in supertrend
            ):
                score -= 10
                bearish += 1
                reasons.append("Supertrend bearish")

        if available == 0:
            direction = "UNAVAILABLE"
        elif bullish > bearish:
            direction = "BULLISH"
        elif bearish > bullish:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        return {
            "direction": direction,
            "raw_score": score,
            "available_factors": available,
            "bullish_factors": bullish,
            "bearish_factors": bearish,
            "reasons": reasons,
        }

    # ---------------------------------------------------------
    # MOMENTUM SCORING
    # ---------------------------------------------------------

    def score_momentum(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        score = 0.0
        reasons: List[str] = []

        available = 0
        bullish = 0
        bearish = 0

        rsi = self._safe_float(snapshot.get("rsi"))
        macd = self._safe_float(snapshot.get("macd"))
        macd_signal = self._safe_float(snapshot.get("macd_signal"))
        adx = self._safe_float(snapshot.get("adx"))
        plus_di = self._safe_float(snapshot.get("plus_di"))
        minus_di = self._safe_float(snapshot.get("minus_di"))

        # RSI
        if rsi is not None:
            available += 1

            if 50 <= rsi < 70:
                score += 15
                bullish += 1
                reasons.append(f"RSI bullish ({rsi:.1f})")

            elif 30 < rsi < 50:
                score -= 10
                bearish += 1
                reasons.append(f"RSI weak ({rsi:.1f})")

            elif rsi >= 70:
                # Overbought is not automatically bearish.
                score += 3
                bullish += 1
                reasons.append(f"RSI strong/overbought ({rsi:.1f})")

            elif rsi <= 30:
                # Oversold is not automatically bullish.
                score -= 3
                bearish += 1
                reasons.append(f"RSI weak/oversold ({rsi:.1f})")

        # MACD
        if macd is not None and macd_signal is not None:
            available += 1

            if macd > macd_signal:
                score += 15
                bullish += 1
                reasons.append("MACD above signal")

            elif macd < macd_signal:
                score -= 15
                bearish += 1
                reasons.append("MACD below signal")

        # ADX strength
        if adx is not None:
            available += 1

            if adx >= 25:
                score += 5
                reasons.append(f"ADX confirms trend strength ({adx:.1f})")

            elif adx < 15:
                reasons.append(f"ADX indicates weak trend ({adx:.1f})")

        # Directional indicators
        if plus_di is not None and minus_di is not None:
            available += 1

            if plus_di > minus_di:
                score += 15
                bullish += 1
                reasons.append("+DI above -DI")

            elif plus_di < minus_di:
                score -= 15
                bearish += 1
                reasons.append("-DI above +DI")

        if available == 0:
            direction = "UNAVAILABLE"
        elif bullish > bearish:
            direction = "BULLISH"
        elif bearish > bullish:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        return {
            "direction": direction,
            "raw_score": score,
            "available_factors": available,
            "bullish_factors": bullish,
            "bearish_factors": bearish,
            "reasons": reasons,
        }

    # ---------------------------------------------------------
    # VWAP SCORING
    # ---------------------------------------------------------

    def score_vwap(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        price = self._safe_float(snapshot.get("price"))
        vwap = self._safe_float(snapshot.get("vwap"))

        if price is None or vwap is None:
            return {
                "direction": "UNAVAILABLE",
                "raw_score": 0.0,
                "reasons": [],
            }

        if price > vwap:
            return {
                "direction": "BULLISH",
                "raw_score": 10.0,
                "reasons": ["Price above VWAP"],
            }

        if price < vwap:
            return {
                "direction": "BEARISH",
                "raw_score": -10.0,
                "reasons": ["Price below VWAP"],
            }

        return {
            "direction": "NEUTRAL",
            "raw_score": 0.0,
            "reasons": ["Price at VWAP"],
        }

    # ---------------------------------------------------------
    # PRICE ACTION
    # ---------------------------------------------------------

    def score_price_action(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        score = 0.0
        reasons: List[str] = []

        candle = self._normalise_text(
            snapshot.get("candle_pattern")
            or snapshot.get("pattern")
        )

        structure = self._normalise_text(
            snapshot.get("market_structure")
            or snapshot.get("structure")
        )

        breakout = self._normalise_text(snapshot.get("breakout"))

        bullish = 0
        bearish = 0
        available = 0

        # Candle patterns
        if candle:
            available += 1

            bullish_patterns = (
                "BULLISH",
                "HAMMER",
                "ENGULFING_BULL",
                "BULLISH_ENGULFING",
                "STRONG_BULLISH",
                "PIN_BAR_BULL",
            )

            bearish_patterns = (
                "BEARISH",
                "SHOOTING_STAR",
                "ENGULFING_BEAR",
                "BEARISH_ENGULFING",
                "STRONG_BEARISH",
                "PIN_BAR_BEAR",
            )

            if any(x in candle for x in bullish_patterns):
                score += 15
                bullish += 1
                reasons.append(f"Bullish candle: {candle}")

            elif any(x in candle for x in bearish_patterns):
                score -= 15
                bearish += 1
                reasons.append(f"Bearish candle: {candle}")

        # Market structure
        if structure:
            available += 1

            if (
                "HH" in structure
                or "HL" in structure
                or "BULL" in structure
                or "UPTREND" in structure
            ):
                score += 15
                bullish += 1
                reasons.append(f"Bullish structure: {structure}")

            elif (
                "LH" in structure
                or "LL" in structure
                or "BEAR" in structure
                or "DOWNTREND" in structure
            ):
                score -= 15
                bearish += 1
                reasons.append(f"Bearish structure: {structure}")

        # Breakout
        if breakout:
            available += 1

            if "UP" in breakout or "BULL" in breakout:
                score += 10
                bullish += 1
                reasons.append("Upside breakout")

            elif "DOWN" in breakout or "BEAR" in breakout:
                score -= 10
                bearish += 1
                reasons.append("Downside breakdown")

        if available == 0:
            direction = "UNAVAILABLE"
        elif bullish > bearish:
            direction = "BULLISH"
        elif bearish > bullish:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        return {
            "direction": direction,
            "raw_score": score,
            "available_factors": available,
            "reasons": reasons,
        }

    # ---------------------------------------------------------
    # SUPPORT / RESISTANCE
    # ---------------------------------------------------------

    def score_support_resistance(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        price = self._safe_float(snapshot.get("price"))
        support = self._safe_float(
            snapshot.get("support")
            or snapshot.get("support_1")
        )
        resistance = self._safe_float(
            snapshot.get("resistance")
            or snapshot.get("resistance_1")
        )

        if price is None:
            return {
                "direction": "UNAVAILABLE",
                "raw_score": 0.0,
                "reasons": [],
            }

        reasons = []

        # If neither level is available, there is nothing reliable to score.
        if support is None and resistance is None:
            return {
                "direction": "UNAVAILABLE",
                "raw_score": 0.0,
                "reasons": [],
            }

        score = 0.0
        direction = "NEUTRAL"

        # Near support = potentially bullish reaction area.
        if support is not None and support > 0:
            distance = abs(price - support) / support * 100

            if distance <= 0.30 and price >= support:
                score += 8
                direction = "BULLISH"
                reasons.append("Price reacting near support")

        # Near resistance = potentially bearish reaction area.
        if resistance is not None and resistance > 0:
            distance = abs(resistance - price) / resistance * 100

            if distance <= 0.30 and price <= resistance:
                score -= 8
                direction = "BEARISH"
                reasons.append("Price near resistance")

        return {
            "direction": direction,
            "raw_score": score,
            "reasons": reasons,
            "support": support,
            "resistance": resistance,
        }

    # ---------------------------------------------------------
    # VOLUME
    # ---------------------------------------------------------

    def score_volume(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        volume_ratio = self._safe_float(
            snapshot.get("volume_ratio")
            or snapshot.get("volume_multiple")
        )

        volume_label = self._normalise_text(
            snapshot.get("volume_signal")
            or snapshot.get("volume_status")
        )

        if volume_ratio is None and not volume_label:
            return {
                "direction": "UNAVAILABLE",
                "raw_score": 0.0,
                "reasons": [],
            }

        reasons = []

        if volume_ratio is not None:
            if volume_ratio >= 1.5:
                reasons.append(
                    f"High volume confirmation ({volume_ratio:.2f}x)"
                )

                return {
                    "direction": "CONFIRMING",
                    "raw_score": 8.0,
                    "reasons": reasons,
                }

            if volume_ratio < 0.7:
                reasons.append(
                    f"Low volume ({volume_ratio:.2f}x)"
                )

                return {
                    "direction": "WEAK",
                    "raw_score": -4.0,
                    "reasons": reasons,
                }

        if volume_label:
            if "HIGH" in volume_label or "STRONG" in volume_label:
                return {
                    "direction": "CONFIRMING",
                    "raw_score": 8.0,
                    "reasons": [f"Volume: {volume_label}"],
                }

            if "LOW" in volume_label or "WEAK" in volume_label:
                return {
                    "direction": "WEAK",
                    "raw_score": -4.0,
                    "reasons": [f"Volume: {volume_label}"],
                }

        return {
            "direction": "NEUTRAL",
            "raw_score": 0.0,
            "reasons": ["Volume neutral"],
        }

    # ---------------------------------------------------------
    # SINGLE TIMEFRAME SCORE
    # ---------------------------------------------------------

    def score_timeframe(self, timeframe: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(snapshot, dict):
            return {
                "timeframe": timeframe,
                "direction": "UNAVAILABLE",
                "score": 0.0,
                "reasons": ["Timeframe data unavailable"],
            }

        trend = self.score_trend(snapshot)
        momentum = self.score_momentum(snapshot)
        vwap = self.score_vwap(snapshot)
        price_action = self.score_price_action(snapshot)
        sr = self.score_support_resistance(snapshot)
        volume = self.score_volume(snapshot)

        components = {
            "trend": trend,
            "momentum": momentum,
            "vwap": vwap,
            "price_action": price_action,
            "support_resistance": sr,
            "volume": volume,
        }

        raw_score = (
            trend["raw_score"]
            + momentum["raw_score"]
            + vwap["raw_score"]
            + price_action["raw_score"]
            + sr["raw_score"]
            + volume["raw_score"]
        )

        reasons = []

        for component in components.values():
            reasons.extend(component.get("reasons", []))

        if raw_score >= 15:
            direction = "BULLISH"

        elif raw_score <= -15:
            direction = "BEARISH"

        else:
            direction = "NEUTRAL"

        return {
            "timeframe": timeframe,
            "direction": direction,
            "raw_score": round(raw_score, 2),
            "score": round(
                self._clamp(50.0 + raw_score / 2.0),
                2,
            ),
            "components": components,
            "reasons": reasons[:20],
        }

    # ---------------------------------------------------------
    # MULTI-TIMEFRAME CONFLUENCE
    # ---------------------------------------------------------

    def calculate_mtf_confluence(
        self,
        mtf_data: Dict[str, Any],
    ) -> Dict[str, Any]:

        weighted_score = 0.0
        total_weight = 0.0

        bullish_weight = 0.0
        bearish_weight = 0.0

        timeframe_results = {}
        reasons = []

        for timeframe, weight in self.TIMEFRAME_WEIGHTS.items():

            snapshot = mtf_data.get(timeframe)

            if not isinstance(snapshot, dict):
                timeframe_results[timeframe] = {
                    "timeframe": timeframe,
                    "direction": "UNAVAILABLE",
                    "score": 0.0,
                    "raw_score": 0.0,
                    "reasons": ["No data"],
                }
                continue

            result = self.score_timeframe(timeframe, snapshot)

            timeframe_results[timeframe] = result

            direction = result["direction"]

            if direction == "UNAVAILABLE":
                continue

            total_weight += weight

            # Convert timeframe score around 50 into a directional value.
            directional_score = result["score"] - 50.0

            weighted_score += directional_score * weight

            if direction == "BULLISH":
                bullish_weight += weight

            elif direction == "BEARISH":
                bearish_weight += weight

            reasons.extend(
                [
                    f"{timeframe}: {reason}"
                    for reason in result.get("reasons", [])[:5]
                ]
            )

        if total_weight <= 0:
            return {
                "direction": "DATA_UNAVAILABLE",
                "score": 0.0,
                "weighted_directional_score": 0.0,
                "bullish_weight": 0.0,
                "bearish_weight": 0.0,
                "timeframes": timeframe_results,
                "reasons": ["No usable timeframe data"],
            }

        normalised_directional = weighted_score / total_weight

        final_score = self._clamp(
            50.0 + normalised_directional
        )

        if bullish_weight > bearish_weight and final_score >= 60:
            direction = "BULLISH"

        elif bearish_weight > bullish_weight and final_score <= 40:
            direction = "BEARISH"

        elif abs(bullish_weight - bearish_weight) < 1e-9:
            direction = "NEUTRAL"

        else:
            direction = "MIXED"

        return {
            "direction": direction,
            "score": round(final_score, 2),
            "weighted_directional_score": round(
                normalised_directional,
                2,
            ),
            "bullish_weight": round(bullish_weight, 2),
            "bearish_weight": round(bearish_weight, 2),
            "timeframes": timeframe_results,
            "reasons": reasons[:40],
        }

    # ---------------------------------------------------------
    # FINAL CONFLUENCE
    # ---------------------------------------------------------

    def calculate_confluence(
        self,
        market_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not isinstance(market_snapshot, dict):
            return {
                "status": "DATA_UNAVAILABLE",
                "direction": "NO_TRADE",
                "score": 0.0,
                "reason": "Invalid market snapshot",
            }

        mtf_data = market_snapshot.get("mtf")

        if not isinstance(mtf_data, dict):
            # Support alternate naming from future versions.
            mtf_data = market_snapshot.get(
                "multi_timeframe",
                {},
            )

        mtf_result = self.calculate_mtf_confluence(mtf_data)

        if mtf_result["direction"] == "DATA_UNAVAILABLE":
            return {
                "status": "DATA_UNAVAILABLE",
                "direction": "NO_TRADE",
                "score": 0.0,
                "trade_candidate": False,
                "reason": "Technical timeframe data unavailable",
                "multi_timeframe": mtf_result,
            }

        # -----------------------------------------------------
        # Final score
        # -----------------------------------------------------
        final_score = float(mtf_result["score"])

        # Higher timeframe alignment bonus/penalty.
        high_tf = []

        for tf in ("1H", "30M", "15M"):
            result = mtf_result["timeframes"].get(tf, {})
            direction = result.get("direction")

            if direction in ("BULLISH", "BEARISH"):
                high_tf.append(direction)

        if len(high_tf) >= 2:
            if all(x == "BULLISH" for x in high_tf):
                final_score += 5

            elif all(x == "BEARISH" for x in high_tf):
                final_score += 5

            else:
                final_score -= 5

        # Lower timeframe disagreement penalty.
        low_tf = []

        for tf in ("1M", "3M", "5M"):
            result = mtf_result["timeframes"].get(tf, {})
            direction = result.get("direction")

            if direction in ("BULLISH", "BEARISH"):
                low_tf.append(direction)

        if mtf_result["direction"] == "BULLISH":
            bearish_low = low_tf.count("BEARISH")

            if bearish_low >= 2:
                final_score -= 8

        elif mtf_result["direction"] == "BEARISH":
            bullish_low = low_tf.count("BULLISH")

            if bullish_low >= 2:
                final_score -= 8

        final_score = round(
            self._clamp(final_score),
            2,
        )

        # -----------------------------------------------------
        # Final decision
        # -----------------------------------------------------
        if final_score >= self.minimum_trade_score:
            if mtf_result["direction"] == "BULLISH":
                direction = "LONG"
                decision = "TRADE_CANDIDATE"

            elif mtf_result["direction"] == "BEARISH":
                direction = "SHORT"
                decision = "TRADE_CANDIDATE"

            else:
                direction = "NEUTRAL"
                decision = "WAIT"

        elif final_score >= 50:
            direction = (
                "LONG"
                if mtf_result["direction"] == "BULLISH"
                else "SHORT"
                if mtf_result["direction"] == "BEARISH"
                else "NEUTRAL"
            )

            decision = "WAIT"

        else:
            direction = (
                "LONG"
                if mtf_result["direction"] == "BULLISH"
                else "SHORT"
                if mtf_result["direction"] == "BEARISH"
                else "NEUTRAL"
            )

            decision = "NO_TRADE"

        # -----------------------------------------------------
        # Human-readable reason
        # -----------------------------------------------------
        if decision == "TRADE_CANDIDATE":
            reason = (
                "Multi-timeframe technical confluence supports "
                f"{direction} setup."
            )

        elif decision == "WAIT":
            reason = (
                "Technical bias exists, but confluence is not "
                "strong enough for an entry."
            )

        else:
            reason = (
                "Technical confluence is insufficient or conflicting."
            )

        return {
            "status": "OK",
            "decision": decision,
            "direction": direction,
            "score": final_score,
            "minimum_trade_score": self.minimum_trade_score,
            "trade_candidate": decision == "TRADE_CANDIDATE",
            "reason": reason,
            "multi_timeframe": mtf_result,
        }

    # ---------------------------------------------------------
    # SUMMARY FOR APP / AI
    # ---------------------------------------------------------

    def build_summary(
        self,
        market_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:

        result = self.calculate_confluence(market_snapshot)

        summary = {
            "status": result.get("status"),
            "decision": result.get("decision", "NO_TRADE"),
            "direction": result.get("direction", "NEUTRAL"),
            "confluence_score": result.get("score", 0.0),
            "reason": result.get("reason", ""),
        }

        mtf = result.get("multi_timeframe", {})

        summary["timeframe_bias"] = {}

        for timeframe in self.TIMEFRAME_WEIGHTS:
            tf_data = mtf.get("timeframes", {}).get(
                timeframe,
                {},
            )

            summary["timeframe_bias"][timeframe] = {
                "direction": tf_data.get(
                    "direction",
                    "UNAVAILABLE",
                ),
                "score": tf_data.get(
                    "score",
                    0.0,
                ),
            }

        return summary


# -------------------------------------------------------------
# SIMPLE FUNCTION API
# -------------------------------------------------------------

def calculate_technical_confluence(
    market_snapshot: Dict[str, Any],
    minimum_trade_score: float = 70.0,
) -> Dict[str, Any]:
    """
    Convenience function for app.py / orchestrator.

    Example:

        result = calculate_technical_confluence(snapshot)

        print(result["decision"])
        print(result["direction"])
        print(result["score"])
    """

    engine = TechnicalConfluenceEngine(
        minimum_trade_score=minimum_trade_score
    )

    return engine.calculate_confluence(
        market_snapshot
    )


def build_technical_summary(
    market_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Convenience summary function.
    """

    engine = TechnicalConfluenceEngine()

    return engine.build_summary(
        market_snapshot
    )
