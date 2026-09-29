from typing import Any, Dict, List, Optional
import math


class EADecisionEngine:
    """
    Stage 4 - Expert Advisor Decision Engine.

    Combines:
        Stage 1 -> Multi-timeframe market snapshot
        Stage 2 -> Technical confluence
        Stage 3 -> Options intelligence

    Produces:
        TRADE_CANDIDATE
        WAIT
        NO_TRADE

    IMPORTANT:
        - Paper trading only.
        - No order placement.
        - No fake market values.
        - Missing data never becomes a BUY/SELL signal.
        - Confluence score is NOT probability of profit.
    """

    # ---------------------------------------------------------
    # DEFAULT SETTINGS
    # ---------------------------------------------------------

    DEFAULT_CONFIG = {
        "minimum_technical_score": 65.0,
        "minimum_option_score": 65.0,
        "minimum_final_score": 70.0,

        "minimum_rr": 1.50,

        # ATR based risk
        "atr_sl_multiplier": 1.20,
        "atr_target_1": 1.50,
        "atr_target_2": 2.50,

        # Option price sanity
        "minimum_option_ltp": 0.05,

        # Maximum distance allowed between
        # current price and proposed structural SL.
        "maximum_sl_percent": 3.0,
    }

    # ---------------------------------------------------------
    # INITIALIZE
    # ---------------------------------------------------------

    def __init__(
        self,
        technical_engine=None,
        options_engine=None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.technical_engine = technical_engine
        self.options_engine = options_engine

        self.config = dict(self.DEFAULT_CONFIG)

        if config:
            self.config.update(config)

    # ---------------------------------------------------------
    # SAFE HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def safe_float(value) -> Optional[float]:
        try:
            if value is None:
                return None

            value = float(value)

            if not math.isfinite(value):
                return None

            return value

        except Exception:
            return None

    @staticmethod
    def safe_text(value) -> str:
        if value is None:
            return ""

        return str(value).strip().upper()

    @staticmethod
    def clamp(
        value: float,
        low: float = 0.0,
        high: float = 100.0,
    ) -> float:

        value = float(value)

        return max(
            low,
            min(high, value),
        )

    @staticmethod
    def first_value(
        data: Dict[str, Any],
        keys: List[str],
        default=None,
    ):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]

        return default

    # ---------------------------------------------------------
    # DATA STATUS
    # ---------------------------------------------------------

    @staticmethod
    def is_unavailable(value) -> bool:

        if value is None:
            return True

        if isinstance(value, str):

            text = value.strip().upper()

            return text in (
                "",
                "N/A",
                "NA",
                "NONE",
                "NULL",
                "UNAVAILABLE",
                "DATA_UNAVAILABLE",
                "WAITING",
            )

        return False

    # ---------------------------------------------------------
    # EXTRACT PRICE
    # ---------------------------------------------------------

    def get_underlying_price(
        self,
        market_snapshot: Dict[str, Any],
    ) -> Optional[float]:

        if not isinstance(market_snapshot, dict):
            return None

        # Common direct locations
        candidates = [
            market_snapshot.get("price"),
            market_snapshot.get("ltp"),
            market_snapshot.get("underlying_price"),
        ]

        # Nested snapshot
        snapshot = market_snapshot.get(
            "snapshot"
        )

        if isinstance(snapshot, dict):

            candidates.extend(
                [
                    snapshot.get("price"),
                    snapshot.get("ltp"),
                    snapshot.get("underlying_price"),
                ]
            )

        # Latest timeframe
        timeframes = market_snapshot.get(
            "timeframes"
        )

        if isinstance(timeframes, dict):

            for tf in (
                "1M",
                "3M",
                "5M",
                "15M",
            ):

                item = timeframes.get(tf)

                if not isinstance(item, dict):
                    continue

                candidates.extend(
                    [
                        item.get("price"),
                        item.get("ltp"),
                    ]
                )

                indicators = item.get(
                    "indicators"
                )

                if isinstance(indicators, dict):

                    candidates.extend(
                        [
                            indicators.get("price"),
                            indicators.get("ltp"),
                        ]
                    )

        for value in candidates:

            number = self.safe_float(value)

            if number is not None and number > 0:
                return number

        return None

    # ---------------------------------------------------------
    # EXTRACT ATR
    # ---------------------------------------------------------

    def get_atr(
        self,
        market_snapshot: Dict[str, Any],
        preferred_timeframes=None,
    ) -> Optional[float]:

        if preferred_timeframes is None:
            preferred_timeframes = [
                "5M",
                "3M",
                "15M",
                "1M",
            ]

        timeframes = {}

        if isinstance(market_snapshot, dict):

            timeframes = market_snapshot.get(
                "timeframes",
                {}
            )

        if not isinstance(timeframes, dict):
            return None

        for tf in preferred_timeframes:

            item = timeframes.get(tf)

            if not isinstance(item, dict):
                continue

            indicators = item.get(
                "indicators",
                item,
            )

            if not isinstance(indicators, dict):
                continue

            atr = self.first_value(
                indicators,
                [
                    "atr",
                    "ATR",
                    "atr14",
                ],
            )

            atr = self.safe_float(atr)

            if atr is not None and atr > 0:
                return atr

        return None

    # ---------------------------------------------------------
    # EXTRACT TECHNICAL RESULT
    # ---------------------------------------------------------

    def get_technical_result(
        self,
        technical_result: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not isinstance(
            technical_result,
            dict,
        ):
            return {
                "status": "DATA_UNAVAILABLE",
                "direction": "NEUTRAL",
                "score": 0.0,
            }

        status = self.safe_text(
            technical_result.get(
                "status"
            )
        )

        if status in (
            "DATA_UNAVAILABLE",
            "ERROR",
        ):
            return {
                "status": status,
                "direction": "NEUTRAL",
                "score": 0.0,
            }

        direction = self.first_value(
            technical_result,
            [
                "direction",
                "bias",
                "final_direction",
                "signal",
            ],
            "NEUTRAL",
        )

        direction = self.safe_text(
            direction
        )

        if direction in (
            "BULLISH",
            "LONG",
            "BUY",
        ):
            direction = "LONG"

        elif direction in (
            "BEARISH",
            "SHORT",
            "SELL",
        ):
            direction = "SHORT"

        else:
            direction = "NEUTRAL"

        score = self.first_value(
            technical_result,
            [
                "score",
                "confluence_score",
                "final_score",
                "technical_score",
            ],
            0,
        )

        score = self.safe_float(score)

        if score is None:
            score = 0.0

        return {
            "status": status or "OK",
            "direction": direction,
            "score": self.clamp(score),
            "raw": technical_result,
        }

    # ---------------------------------------------------------
    # DETERMINE MARKET DIRECTION
    # ---------------------------------------------------------

    def determine_direction(
        self,
        technical_result: Dict[str, Any],
    ) -> Dict[str, Any]:

        result = self.get_technical_result(
            technical_result
        )

        direction = result["direction"]
        score = result["score"]

        if direction == "NEUTRAL":

            return {
                "direction": "NEUTRAL",
                "score": score,
                "status": "WAIT",
                "reason": (
                    "Technical engine has no confirmed "
                    "direction."
                ),
            }

        if score < self.config[
            "minimum_technical_score"
        ]:

            return {
                "direction": direction,
                "score": score,
                "status": "WAIT",
                "reason": (
                    "Technical confluence is below "
                    "entry threshold."
                ),
            }

        return {
            "direction": direction,
            "score": score,
            "status": "OK",
            "reason": (
                "Technical direction passed "
                "the confluence threshold."
            ),
        }

    # ---------------------------------------------------------
    # OPTION SETUP
    # ---------------------------------------------------------

    def get_option_setup(
        self,
        option_result: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not isinstance(
            option_result,
            dict,
        ):
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
            }

        status = self.safe_text(
            option_result.get(
                "status"
            )
        )

        if status in (
            "DATA_UNAVAILABLE",
            "ERROR",
        ):
            return {
                "status": status,
                "decision": "NO_TRADE",
                "reason": (
                    option_result.get(
                        "reason",
                        "Option data unavailable.",
                    )
                ),
            }

        setup = option_result.get(
            "setup"
        )

        if not isinstance(
            setup,
            dict,
        ):
            setup = {}

        candidate = option_result.get(
            "preferred_candidate"
        )

        if not isinstance(
            candidate,
            dict,
        ):
            candidate = {}

        option_type = self.first_value(
            setup,
            [
                "option_type",
                "type",
            ],
        )

        if option_type is None:
            option_type = candidate.get(
                "option_type"
            )

        strike = self.first_value(
            setup,
            [
                "strike",
            ],
        )

        if strike is None:
            strike = candidate.get(
                "strike"
            )

        expiry = self.first_value(
            setup,
            [
                "expiry",
            ],
        )

        if expiry is None:
            expiry = candidate.get(
                "expiry"
            )

        entry = self.first_value(
            setup,
            [
                "entry_reference",
                "entry",
                "ltp",
            ],
        )

        if entry is None:
            entry = candidate.get(
                "ltp"
            )

        score = self.first_value(
            option_result,
            [
                "option_score",
                "score",
            ],
            0,
        )

        score = self.safe_float(
            score
        )

        if score is None:
            score = 0.0

        return {
            "status": "OK",
            "decision": self.safe_text(
                option_result.get(
                    "decision",
                    setup.get(
                        "decision",
                        "WAIT",
                    ),
                )
            ),
            "option_type": self.safe_text(
                option_type
            ),
            "strike": self.safe_float(
                strike
            ),
            "expiry": expiry,
            "entry_reference": self.safe_float(
                entry
            ),
            "score": self.clamp(score),
            "candidate": candidate,
            "raw": option_result,
        }

    # ---------------------------------------------------------
    # STRUCTURAL SUPPORT / RESISTANCE
    # ---------------------------------------------------------

    def get_support_resistance(
        self,
        market_snapshot: Dict[str, Any],
    ) -> Dict[str, Optional[float]]:

        result = {
            "support": None,
            "resistance": None,
        }

        timeframes = {}

        if isinstance(
            market_snapshot,
            dict,
        ):
            timeframes = market_snapshot.get(
                "timeframes",
                {},
            )

        if not isinstance(
            timeframes,
            dict,
        ):
            return result

        # Prefer 5M because option entries
        # are normally based on lower-TF structure.
        for tf in (
            "5M",
            "3M",
            "15M",
            "1M",
            "30M",
            "1H",
        ):

            item = timeframes.get(tf)

            if not isinstance(item, dict):
                continue

            sr = item.get(
                "support_resistance"
            )

            if not isinstance(
                sr,
                dict,
            ):
                sr = item.get(
                    "supportResistance"
                )

            if not isinstance(
                sr,
                dict,
            ):
                sr = item.get(
                    "sr"
                )

            if isinstance(sr, dict):

                support = self.first_value(
                    sr,
                    [
                        "support",
                        "Support",
                    ],
                )

                resistance = self.first_value(
                    sr,
                    [
                        "resistance",
                        "Resistance",
                    ],
                )

                support = self.safe_float(
                    support
                )

                resistance = self.safe_float(
                    resistance
                )

                if support is not None:
                    result["support"] = support

                if resistance is not None:
                    result["resistance"] = resistance

                if (
                    result["support"] is not None
                    or result["resistance"] is not None
                ):
                    return result

        return result

    # ---------------------------------------------------------
    # CALCULATE UNDERLYING RISK LEVELS
    # ---------------------------------------------------------

    def calculate_underlying_levels(
        self,
        direction: str,
        price: float,
        atr: Optional[float],
        support: Optional[float],
        resistance: Optional[float],
    ) -> Dict[str, Any]:

        direction = self.safe_text(
            direction
        )

        price = self.safe_float(price)
        atr = self.safe_float(atr)
        support = self.safe_float(support)
        resistance = self.safe_float(resistance)

        if price is None or price <= 0:

            return {
                "status": "DATA_UNAVAILABLE",
                "reason": "Underlying price unavailable.",
            }

        if atr is None or atr <= 0:

            return {
                "status": "DATA_UNAVAILABLE",
                "reason": (
                    "ATR unavailable. Risk levels "
                    "cannot be calculated safely."
                ),
            }

        sl_distance = (
            atr
            * self.config[
                "atr_sl_multiplier"
            ]
        )

        target_1_distance = (
            atr
            * self.config[
                "atr_target_1"
            ]
        )

        target_2_distance = (
            atr
            * self.config[
                "atr_target_2"
            ]
        )

        if direction == "LONG":

            atr_sl = price - sl_distance

            atr_t1 = price + target_1_distance
            atr_t2 = price + target_2_distance

            # Use support only if it is below entry.
            structural_sl = None

            if (
                support is not None
                and support < price
            ):
                structural_sl = support

            if structural_sl is not None:

                # Keep the SL below price but avoid
                # an excessively distant stop.
                if structural_sl > atr_sl:
                    stop_loss = structural_sl
                else:
                    stop_loss = atr_sl

            else:
                stop_loss = atr_sl

            target_1 = atr_t1
            target_2 = atr_t2

        elif direction == "SHORT":

            atr_sl = price + sl_distance

            atr_t1 = price - target_1_distance
            atr_t2 = price - target_2_distance

            structural_sl = None

            if (
                resistance is not None
                and resistance > price
            ):
                structural_sl = resistance

            if structural_sl is not None:

                if structural_sl < atr_sl:
                    stop_loss = structural_sl
                else:
                    stop_loss = atr_sl

            else:
                stop_loss = atr_sl

            target_1 = atr_t1
            target_2 = atr_t2

        else:

            return {
                "status": "WAIT",
                "reason": (
                    "No directional setup."
                ),
            }

        stop_loss = self.safe_float(
            stop_loss
        )

        target_1 = self.safe_float(
            target_1
        )

        target_2 = self.safe_float(
            target_2
        )

        if (
            stop_loss is None
            or target_1 is None
            or target_2 is None
        ):

            return {
                "status": "DATA_UNAVAILABLE",
                "reason": (
                    "Unable to calculate complete "
                    "risk levels."
                ),
            }

        if direction == "LONG":

            risk = price - stop_loss
            reward_1 = target_1 - price
            reward_2 = target_2 - price

        else:

            risk = stop_loss - price
            reward_1 = price - target_1
            reward_2 = price - target_2

        if risk <= 0:

            return {
                "status": "NO_TRADE",
                "reason": (
                    "Calculated stop-loss is invalid "
                    "for the selected direction."
                ),
            }

        rr_1 = reward_1 / risk
        rr_2 = reward_2 / risk

        sl_percent = (
            abs(price - stop_loss)
            / price
            * 100
        )

        if (
            sl_percent
            > self.config[
                "maximum_sl_percent"
            ]
        ):

            return {
                "status": "NO_TRADE",
                "reason": (
                    "Stop-loss distance is too wide."
                ),
                "sl_percent": round(
                    sl_percent,
                    3,
                ),
            }

        if (
            rr_2
            < self.config[
                "minimum_rr"
            ]
        ):

            return {
                "status": "WAIT",
                "reason": (
                    "Risk/reward does not meet "
                    "minimum requirement."
                ),
                "rr_t1": round(rr_1, 2),
                "rr_t2": round(rr_2, 2),
            }

        return {
            "status": "OK",
            "entry": round(price, 2),
            "stop_loss": round(
                stop_loss,
                2,
            ),
            "target_1": round(
                target_1,
                2,
            ),
            "target_2": round(
                target_2,
                2,
            ),
            "risk_points": round(
                risk,
                2,
            ),
            "reward_t1": round(
                reward_1,
                2,
            ),
            "reward_t2": round(
                reward_2,
                2,
            ),
            "rr_t1": round(
                rr_1,
                2,
            ),
            "rr_t2": round(
                rr_2,
                2,
            ),
            "sl_percent": round(
                sl_percent,
                3,
            ),
            "atr": round(
                atr,
                2,
            ),
            "support": support,
            "resistance": resistance,
        }

    # ---------------------------------------------------------
    # OPTION RISK LEVELS
    # ---------------------------------------------------------

    def calculate_option_levels(
        self,
        direction: str,
        option_entry: float,
        underlying_risk: Dict[str, Any],
        option_candidate: Dict[str, Any],
    ) -> Dict[str, Any]:

        option_entry = self.safe_float(
            option_entry
        )

        if (
            option_entry is None
            or option_entry
            < self.config[
                "minimum_option_ltp"
            ]
        ):

            return {
                "status": "DATA_UNAVAILABLE",
                "reason": (
                    "Option entry price unavailable."
                ),
            }

        # The Stage 3 engine intentionally does not
        # fabricate option targets.
        #
        # For the first EA decision layer we use
        # controlled percentage risk on the real
        # option premium. This is a planning reference,
        # not an execution order.

        option_sl_percent = 25.0
        option_t1_percent = 35.0
        option_t2_percent = 60.0

        if direction == "LONG":

            stop_loss = option_entry * (
                1
                - option_sl_percent / 100
            )

            target_1 = option_entry * (
                1
                + option_t1_percent / 100
            )

            target_2 = option_entry * (
                1
                + option_t2_percent / 100
            )

        elif direction == "SHORT":

            # For a PE purchase the option itself
            # is still LONG premium exposure.
            stop_loss = option_entry * (
                1
                - option_sl_percent / 100
            )

            target_1 = option_entry * (
                1
                + option_t1_percent / 100
            )

            target_2 = option_entry * (
                1
                + option_t2_percent / 100
            )

        else:

            return {
                "status": "WAIT",
                "reason": "No option direction.",
            }

        risk = (
            option_entry
            - stop_loss
        )

        reward_1 = (
            target_1
            - option_entry
        )

        reward_2 = (
            target_2
            - option_entry
        )

        rr_1 = reward_1 / risk
        rr_2 = reward_2 / risk

        return {
            "status": "OK",
            "entry": round(
                option_entry,
                2,
            ),
            "stop_loss": round(
                stop_loss,
                2,
            ),
            "target_1": round(
                target_1,
                2,
            ),
            "target_2": round(
                target_2,
                2,
            ),
            "risk_points": round(
                risk,
                2,
            ),
            "reward_t1": round(
                reward_1,
                2,
            ),
            "reward_t2": round(
                reward_2,
                2,
            ),
            "rr_t1": round(
                rr_1,
                2,
            ),
            "rr_t2": round(
                rr_2,
                2,
            ),
            "method": (
                "Controlled option-premium planning "
                "reference; not a guaranteed target."
            ),
        }

    # ---------------------------------------------------------
    # EXPIRY RISK CHECK
    # ---------------------------------------------------------

    def check_expiry_risk(
        self,
        option_candidate: Dict[str, Any],
    ) -> Dict[str, Any]:

        expiry_analysis = option_candidate.get(
            "expiry_analysis",
            {},
        )

        if not isinstance(
            expiry_analysis,
            dict,
        ):
            expiry_analysis = {}

        risk = self.safe_text(
            expiry_analysis.get(
                "risk"
            )
        )

        days = self.safe_float(
            option_candidate.get(
                "days_to_expiry"
            )
        )

        if days is not None:

            if days <= 0:

                return {
                    "status": "BLOCK",
                    "risk": "EXPIRED",
                    "reason": (
                        "Option expiry is expired/invalid."
                    ),
                }

            if days <= 1:

                return {
                    "status": "WARNING",
                    "risk": "VERY_HIGH",
                    "reason": (
                        "Very high expiry risk."
                    ),
                }

            if days <= 2:

                return {
                    "status": "WARNING",
                    "risk": "HIGH",
                    "reason": (
                        "High expiry risk."
                    ),
                }

        if risk in (
            "VERY_HIGH",
            "EXPIRED",
        ):

            return {
                "status": (
                    "BLOCK"
                    if risk == "EXPIRED"
                    else "WARNING"
                ),
                "risk": risk,
                "reason": (
                    "Expiry risk requires caution."
                ),
            }

        return {
            "status": "OK",
            "risk": risk or "UNKNOWN",
            "reason": (
                "No expiry block triggered."
            ),
        }

    # ---------------------------------------------------------
    # LIQUIDITY CHECK
    # ---------------------------------------------------------

    def check_liquidity(
        self,
        option_candidate: Dict[str, Any],
    ) -> Dict[str, Any]:

        liquidity = option_candidate.get(
            "liquidity",
            {},
        )

        if not isinstance(
            liquidity,
            dict,
        ):
            liquidity = {}

        spread = self.safe_float(
            liquidity.get(
                "spread_percent"
            )
        )

        volume = self.safe_float(
            liquidity.get(
                "volume"
            )
        )

        if (
            spread is not None
            and spread > 2.5
        ):

            return {
                "status": "BLOCK",
                "reason": (
                    "Option bid/ask spread is too wide."
                ),
                "spread_percent": round(
                    spread,
                    3,
                ),
            }

        if (
            volume is not None
            and volume <= 0
        ):

            return {
                "status": "WARNING",
                "reason": (
                    "Option volume is unavailable/zero."
                ),
                "volume": volume,
            }

        return {
            "status": "OK",
            "spread_percent": spread,
            "volume": volume,
        }

    # ---------------------------------------------------------
    # FINAL SCORE
    # ---------------------------------------------------------

    def calculate_final_score(
        self,
        technical_score: float,
        option_score: float,
        rr: float,
        direction: str,
        expiry_status: str,
        liquidity_status: str,
    ) -> float:

        technical_score = self.clamp(
            self.safe_float(
                technical_score
            ) or 0
        )

        option_score = self.clamp(
            self.safe_float(
                option_score
            ) or 0
        )

        rr = self.safe_float(
            rr
        ) or 0.0

        # Technical = 50%
        # Options = 35%
        # Risk/reward = 15%
        final = (
            technical_score * 0.50
            + option_score * 0.35
        )

        rr_score = self.clamp(
            rr / 3.0 * 100
        )

        final += (
            rr_score * 0.15
        )

        # Direction is mandatory.
        if direction == "NEUTRAL":
            final -= 20

        # Safety penalties.
        if expiry_status == "WARNING":
            final -= 5

        if liquidity_status == "WARNING":
            final -= 5

        return round(
            self.clamp(final),
            2,
        )

    # ---------------------------------------------------------
    # BUILD REASONS
    # ---------------------------------------------------------

    def build_reasons(
        self,
        direction_result: Dict[str, Any],
        option_setup: Dict[str, Any],
        risk_levels: Dict[str, Any],
        expiry_check: Dict[str, Any],
        liquidity_check: Dict[str, Any],
    ) -> List[str]:

        reasons = []

        technical_score = direction_result.get(
            "score",
            0,
        )

        direction = direction_result.get(
            "direction",
            "NEUTRAL",
        )

        if direction == "LONG":
            reasons.append(
                "Technical engine shows bullish confluence."
            )

        elif direction == "SHORT":
            reasons.append(
                "Technical engine shows bearish confluence."
            )

        else:
            reasons.append(
                "Technical direction is not confirmed."
            )

        reasons.append(
            f"Technical confluence score: "
            f"{round(float(technical_score), 1)}/100."
        )

        option_type = option_setup.get(
            "option_type"
        )

        strike = option_setup.get(
            "strike"
        )

        if option_type and strike is not None:

            reasons.append(
                f"Selected option side: "
                f"{option_type} {strike:g}."
            )

        option_score = option_setup.get(
            "score",
            0,
        )

        reasons.append(
            f"Option intelligence score: "
            f"{round(float(option_score), 1)}/100."
        )

        if risk_levels.get(
            "status"
        ) == "OK":

            reasons.append(
                f"Risk/reward T1: "
                f"{risk_levels.get('rr_t1')}."
            )

            reasons.append(
                f"Risk/reward T2: "
                f"{risk_levels.get('rr_t2')}."
            )

        expiry_reason = expiry_check.get(
            "reason"
        )

        if expiry_reason:
            reasons.append(
                expiry_reason
            )

        if liquidity_check.get(
            "status"
        ) == "OK":

            reasons.append(
                "Option liquidity check passed."
            )

        elif liquidity_check.get(
            "status"
        ) == "WARNING":

            reasons.append(
                "Option liquidity warning present."
            )

        return reasons[:20]

    # ---------------------------------------------------------
    # MAIN DECISION
    # ---------------------------------------------------------

    def decide(
        self,
        market_snapshot: Dict[str, Any],
        technical_result: Dict[str, Any],
        option_result: Dict[str, Any],
        instrument: Optional[str] = None,
    ) -> Dict[str, Any]:

        # =====================================================
        # BASIC DATA VALIDATION
        # =====================================================

        if not isinstance(
            market_snapshot,
            dict,
        ):

            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "reason": (
                    "Market snapshot unavailable."
                ),
            }

        # =====================================================
        # TECHNICAL DIRECTION
        # =====================================================

        direction_result = (
            self.determine_direction(
                technical_result
            )
        )

        direction = direction_result[
            "direction"
        ]

        technical_score = direction_result[
            "score"
        ]

        if direction == "NEUTRAL":

            return {
                "status": "OK",
                "decision": "WAIT",
                "direction": "NEUTRAL",
                "technical_score": technical_score,
                "option_score": 0.0,
                "final_score": 0.0,
                "reasons": [
                    direction_result[
                        "reason"
                    ]
                ],
            }

        if (
            technical_score
            < self.config[
                "minimum_technical_score"
            ]
        ):

            return {
                "status": "OK",
                "decision": "WAIT",
                "direction": direction,
                "technical_score": technical_score,
                "option_score": 0.0,
                "final_score": technical_score,
                "reasons": [
                    direction_result[
                        "reason"
                    ]
                ],
            }

        # =====================================================
        # UNDERLYING PRICE
        # =====================================================

        underlying_price = (
            self.get_underlying_price(
                market_snapshot
            )
        )

        if (
            underlying_price is None
            or underlying_price <= 0
        ):

            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "direction": direction,
                "technical_score": technical_score,
                "reason": (
                    "Live underlying price unavailable."
                ),
            }

        # =====================================================
        # OPTION SETUP
        # =====================================================

        option_setup = self.get_option_setup(
            option_result
        )

        option_score = option_setup.get(
            "score",
            0.0,
        )

        option_score = self.safe_float(
            option_score
        ) or 0.0

        if (
            option_setup.get(
                "status"
            )
            != "OK"
        ):

            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "direction": direction,
                "underlying_price": underlying_price,
                "technical_score": technical_score,
                "option_score": option_score,
                "reason": (
                    "Options data unavailable."
                ),
            }

        option_decision = self.safe_text(
            option_setup.get(
                "decision"
            )
        )

        if option_decision not in (
            "OPTION_CANDIDATE",
            "CANDIDATE",
        ):

            return {
                "status": "OK",
                "decision": "WAIT",
                "direction": direction,
                "underlying_price": underlying_price,
                "technical_score": technical_score,
                "option_score": option_score,
                "option": option_setup,
                "reasons": [
                    "Option engine has not confirmed "
                    "a valid candidate."
                ],
            }

        if (
            option_score
            < self.config[
                "minimum_option_score"
            ]
        ):

            return {
                "status": "OK",
                "decision": "WAIT",
                "direction": direction,
                "underlying_price": underlying_price,
                "technical_score": technical_score,
                "option_score": option_score,
                "option": option_setup,
                "reasons": [
                    "Option confluence is below "
                    "entry threshold."
                ],
            }

        # =====================================================
        # CANDIDATE VALIDATION
        # =====================================================

        candidate = option_setup.get(
            "candidate",
            {}
        )

        if not isinstance(
            candidate,
            dict,
        ):
            candidate = {}

        # Expiry
        expiry_check = (
            self.check_expiry_risk(
                candidate
            )
        )

        if expiry_check.get(
            "status"
        ) == "BLOCK":

            return {
                "status": "OK",
                "decision": "NO_TRADE",
                "direction": direction,
                "underlying_price": underlying_price,
                "technical_score": technical_score,
                "option_score": option_score,
                "option": option_setup,
                "expiry": expiry_check,
                "reasons": [
                    expiry_check[
                        "reason"
                    ]
                ],
            }

        # Liquidity
        liquidity_check = (
            self.check_liquidity(
                candidate
            )
        )

        if liquidity_check.get(
            "status"
        ) == "BLOCK":

            return {
                "status": "OK",
                "decision": "NO_TRADE",
                "direction": direction,
                "underlying_price": underlying_price,
                "technical_score": technical_score,
                "option_score": option_score,
                "option": option_setup,
                "liquidity": liquidity_check,
                "reasons": [
                    liquidity_check[
                        "reason"
                    ]
                ],
            }

        # =====================================================
        # ATR / STRUCTURE
        # =====================================================

        atr = self.get_atr(
            market_snapshot
        )

        sr = self.get_support_resistance(
            market_snapshot
        )

        underlying_levels = (
            self.calculate_underlying_levels(
                direction=direction,
                price=underlying_price,
                atr=atr,
                support=sr.get(
                    "support"
                ),
                resistance=sr.get(
                    "resistance"
                ),
            )
        )

        if underlying_levels.get(
            "status"
        ) != "OK":

            return {
                "status": "OK",
                "decision": "WAIT",
                "direction": direction,
                "underlying_price": underlying_price,
                "technical_score": technical_score,
                "option_score": option_score,
                "option": option_setup,
                "risk": underlying_levels,
                "reasons": [
                    underlying_levels.get(
                        "reason",
                        "Risk levels unavailable."
                    )
                ],
            }

        # =====================================================
        # OPTION ENTRY / TARGETS
        # =====================================================

        option_entry = option_setup.get(
            "entry_reference"
        )

        option_levels = (
            self.calculate_option_levels(
                direction=direction,
                option_entry=option_entry,
                underlying_risk=underlying_levels,
                option_candidate=candidate,
            )
        )

        if option_levels.get(
            "status"
        ) != "OK":

            return {
                "status": "OK",
                "decision": "WAIT",
                "direction": direction,
                "underlying_price": underlying_price,
                "technical_score": technical_score,
                "option_score": option_score,
                "option": option_setup,
                "risk": underlying_levels,
                "option_risk": option_levels,
                "reasons": [
                    option_levels.get(
                        "reason",
                        "Option risk levels unavailable."
                    )
                ],
            }

        # =====================================================
        # FINAL SCORE
        # =====================================================

        final_score = (
            self.calculate_final_score(
                technical_score=technical_score,
                option_score=option_score,
                rr=underlying_levels.get(
                    "rr_t2",
                    0,
                ),
                direction=direction,
                expiry_status=expiry_check.get(
                    "status",
                    "OK",
                ),
                liquidity_status=liquidity_check.get(
                    "status",
                    "OK",
                ),
            )
        )

        # =====================================================
        # FINAL DECISION
        # =====================================================

        if final_score >= self.config[
            "minimum_final_score"
        ]:

            decision = "TRADE_CANDIDATE"

        elif final_score >= 55:

            decision = "WAIT"

        else:

            decision = "NO_TRADE"

        # =====================================================
        # REASONS
        # =====================================================

        reasons = self.build_reasons(
            direction_result=direction_result,
            option_setup=option_setup,
            risk_levels=underlying_levels,
            expiry_check=expiry_check,
            liquidity_check=liquidity_check,
        )

        # =====================================================
        # TRAILING STOP REFERENCE
        # =====================================================

        if direction == "LONG":

            trailing_sl_reference = (
                underlying_levels[
                    "entry"
                ]
                + (
                    underlying_levels[
                        "entry"
                    ]
                    - underlying_levels[
                        "stop_loss"
                    ]
                )
            )

        else:

            trailing_sl_reference = (
                underlying_levels[
                    "entry"
                ]
                - (
                    underlying_levels[
                        "stop_loss"
                    ]
                    - underlying_levels[
                        "entry"
                    ]
                )
            )

        trailing_sl_reference = round(
            trailing_sl_reference,
            2,
        )

        # =====================================================
        # FINAL STRUCTURED OUTPUT
        # =====================================================

        return {
            "status": "OK",
            "decision": decision,

            "instrument": instrument,

            "direction": direction,

            "underlying": {
                "price": round(
                    underlying_price,
                    2,
                ),
                "atr": underlying_levels.get(
                    "atr"
                ),
                "support": underlying_levels.get(
                    "support"
                ),
                "resistance": underlying_levels.get(
                    "resistance"
                ),
            },

            "technical": {
                "direction": direction,
                "score": technical_score,
            },

            "option": {
                "type": option_setup.get(
                    "option_type"
                ),
                "strike": option_setup.get(
                    "strike"
                ),
                "expiry": option_setup.get(
                    "expiry"
                ),
                "score": option_score,
                "entry_reference": option_setup.get(
                    "entry_reference"
                ),
            },

            "risk": {
                "underlying": underlying_levels,

                "option": option_levels,

                "trailing_sl_reference": (
                    trailing_sl_reference
                ),
            },

            "scores": {
                "technical": round(
                    technical_score,
                    2,
                ),
                "options": round(
                    option_score,
                    2,
                ),
                "final_confluence": final_score,
            },

            "expiry": expiry_check,

            "liquidity": liquidity_check,

            "reasons": reasons,

            "safety": {
                "paper_trading_only": True,
                "real_order_placement": False,
                "score_is_probability": False,
            },

            "note": (
                "This is a paper-trading Expert Advisor "
                "analysis result. Confluence score is not "
                "a guaranteed probability of profit."
            ),
        }

    # ---------------------------------------------------------
    # SIMPLE API
    # ---------------------------------------------------------

    def analyse(
        self,
        market_snapshot: Dict[str, Any],
        technical_result: Dict[str, Any],
        option_result: Dict[str, Any],
        instrument: Optional[str] = None,
    ) -> Dict[str, Any]:

        return self.decide(
            market_snapshot=market_snapshot,
            technical_result=technical_result,
            option_result=option_result,
            instrument=instrument,
        )


# =============================================================
# CONVENIENCE FUNCTION
# =============================================================

def build_ea_decision(
    market_snapshot: Dict[str, Any],
    technical_result: Dict[str, Any],
    option_result: Dict[str, Any],
    instrument: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    engine = EADecisionEngine(
        config=config
    )

    return engine.decide(
        market_snapshot=market_snapshot,
        technical_result=technical_result,
        option_result=option_result,
        instrument=instrument,
    )
