"""
Options Intelligence Engine
===========================

Stage 3 of the Expert Advisor architecture.

Purpose:
- Analyse real option-chain data
- Compare CE and PE
- Evaluate OI / Change OI / PCR / IV / Greeks
- Evaluate liquidity
- Evaluate expiry risk
- Select candidate strikes
- Produce deterministic option scores

IMPORTANT:
- Paper trading only
- No order placement
- No fake market data
- Missing data is marked DATA_UNAVAILABLE
- Score is NOT a profit probability
"""

from typing import Dict, Any, List, Optional
import math


class OptionsIntelligenceEngine:
    """
    Deterministic options analysis engine.

    This engine does not call the broker itself.
    It expects already-fetched real option-chain data.

    Expected option contract fields can include:

        symbol
        tradingsymbol
        strike
        option_type
        ltp
        bid
        ask
        volume
        oi
        change_oi
        iv
        delta
        gamma
        theta
        vega

    Field aliases are supported where practical.
    """

    def __init__(
        self,
        minimum_option_score: float = 65.0,
        max_spread_percent: float = 2.5,
    ):
        self.minimum_option_score = float(minimum_option_score)
        self.max_spread_percent = float(max_spread_percent)

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def safe_float(value) -> Optional[float]:
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
    def text(value) -> str:
        if value is None:
            return ""

        return str(value).strip().upper()

    @staticmethod
    def clamp(
        value: float,
        low: float = 0.0,
        high: float = 100.0,
    ) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def first_value(
        data: Dict[str, Any],
        keys: List[str],
    ):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]

        return None

    # =========================================================
    # NORMALISE CONTRACT
    # =========================================================

    def normalise_contract(
        self,
        contract: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not isinstance(contract, dict):
            return {
                "valid": False,
                "reason": "Invalid contract",
            }

        option_type = self.text(
            self.first_value(
                contract,
                [
                    "option_type",
                    "optionType",
                    "type",
                    "instrument_type",
                ],
            )
        )

        # Support common SmartAPI naming.
        symbol = self.first_value(
            contract,
            [
                "tradingsymbol",
                "trading_symbol",
                "symbol",
                "name",
            ],
        )

        strike = self.safe_float(
            self.first_value(
                contract,
                [
                    "strike",
                    "strike_price",
                    "strikePrice",
                ],
            )
        )

        ltp = self.safe_float(
            self.first_value(
                contract,
                [
                    "ltp",
                    "LTP",
                    "last_traded_price",
                    "lastTradedPrice",
                ],
            )
        )

        bid = self.safe_float(
            self.first_value(
                contract,
                [
                    "bid",
                    "best_bid",
                    "buy_price",
                ],
            )
        )

        ask = self.safe_float(
            self.first_value(
                contract,
                [
                    "ask",
                    "best_ask",
                    "sell_price",
                ],
            )
        )

        volume = self.safe_float(
            self.first_value(
                contract,
                [
                    "volume",
                    "tradeVolume",
                    "trade_volume",
                ],
            )
        )

        oi = self.safe_float(
            self.first_value(
                contract,
                [
                    "oi",
                    "open_interest",
                    "opnInterest",
                    "openInterest",
                ],
            )
        )

        change_oi = self.safe_float(
            self.first_value(
                contract,
                [
                    "change_oi",
                    "changeOI",
                    "change_in_oi",
                    "net_change_oi",
                ],
            )
        )

        iv = self.safe_float(
            self.first_value(
                contract,
                [
                    "iv",
                    "implied_volatility",
                    "impliedVolatility",
                ],
            )
        )

        delta = self.safe_float(
            self.first_value(
                contract,
                [
                    "delta",
                ],
            )
        )

        gamma = self.safe_float(
            self.first_value(
                contract,
                [
                    "gamma",
                ],
            )
        )

        theta = self.safe_float(
            self.first_value(
                contract,
                [
                    "theta",
                ],
            )
        )

        vega = self.safe_float(
            self.first_value(
                contract,
                [
                    "vega",
                ],
            )
        )

        return {
            "valid": True,
            "symbol": symbol,
            "option_type": option_type,
            "strike": strike,
            "ltp": ltp,
            "bid": bid,
            "ask": ask,
            "volume": volume,
            "oi": oi,
            "change_oi": change_oi,
            "iv": iv,
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "raw": contract,
        }

    # =========================================================
    # EXPIRY ANALYSIS
    # =========================================================

    def analyse_expiry(
        self,
        expiry: Optional[str],
        days_to_expiry: Optional[float] = None,
    ) -> Dict[str, Any]:

        days = self.safe_float(days_to_expiry)

        if days is None:
            return {
                "status": "PARTIAL",
                "risk": "UNKNOWN",
                "score_adjustment": 0.0,
                "reason": "Days to expiry unavailable",
            }

        if days <= 0:
            return {
                "status": "OK",
                "risk": "EXPIRED_OR_EXPIRING",
                "score_adjustment": -20.0,
                "reason": "Expiry is at or past current session",
            }

        if days <= 1:
            return {
                "status": "OK",
                "risk": "VERY_HIGH",
                "score_adjustment": -12.0,
                "reason": "Very close to expiry; gamma/theta risk is high",
            }

        if days <= 2:
            return {
                "status": "OK",
                "risk": "HIGH",
                "score_adjustment": -8.0,
                "reason": "Near expiry; option decay and gamma risk elevated",
            }

        if days <= 5:
            return {
                "status": "OK",
                "risk": "MODERATE",
                "score_adjustment": -3.0,
                "reason": "Short-dated expiry",
            }

        return {
            "status": "OK",
            "risk": "NORMAL",
            "score_adjustment": 0.0,
            "reason": "Expiry distance is relatively normal",
        }

    # =========================================================
    # LIQUIDITY
    # =========================================================

    def analyse_liquidity(
        self,
        contract: Dict[str, Any],
    ) -> Dict[str, Any]:

        ltp = contract.get("ltp")
        bid = contract.get("bid")
        ask = contract.get("ask")
        volume = contract.get("volume")

        reasons = []

        spread_percent = None

        if (
            ltp is not None
            and bid is not None
            and ask is not None
            and ltp > 0
        ):
            spread = max(0.0, ask - bid)
            spread_percent = (spread / ltp) * 100

        score = 0.0

        if spread_percent is not None:

            if spread_percent <= 0.50:
                score += 10
                reasons.append(
                    f"Tight spread ({spread_percent:.2f}%)"
                )

            elif spread_percent <= 1.0:
                score += 7
                reasons.append(
                    f"Acceptable spread ({spread_percent:.2f}%)"
                )

            elif spread_percent <= self.max_spread_percent:
                score += 2
                reasons.append(
                    f"Wide spread ({spread_percent:.2f}%)"
                )

            else:
                score -= 10
                reasons.append(
                    f"Very wide spread ({spread_percent:.2f}%)"
                )

        if volume is not None:

            if volume >= 100000:
                score += 8
                reasons.append("High option volume")

            elif volume >= 25000:
                score += 5
                reasons.append("Good option volume")

            elif volume >= 5000:
                score += 2
                reasons.append("Moderate option volume")

            else:
                score -= 4
                reasons.append("Low option volume")

        if spread_percent is None and volume is None:
            return {
                "status": "DATA_UNAVAILABLE",
                "score": 0.0,
                "spread_percent": None,
                "reasons": [],
            }

        return {
            "status": "OK",
            "score": self.clamp(score, -10, 18),
            "spread_percent": spread_percent,
            "reasons": reasons,
        }

    # =========================================================
    # GREEKS
    # =========================================================

    def analyse_greeks(
        self,
        contract: Dict[str, Any],
        option_type: str,
    ) -> Dict[str, Any]:

        delta = contract.get("delta")
        gamma = contract.get("gamma")
        theta = contract.get("theta")
        vega = contract.get("vega")

        available = sum(
            x is not None
            for x in (
                delta,
                gamma,
                theta,
                vega,
            )
        )

        if available == 0:
            return {
                "status": "DATA_UNAVAILABLE",
                "score": 0.0,
                "delta": None,
                "gamma": None,
                "theta": None,
                "vega": None,
                "reasons": [],
            }

        score = 0.0
        reasons = []

        # For buying options, absolute delta around 0.40-0.60
        # generally gives better directional sensitivity than
        # extremely low-delta contracts.
        if delta is not None:

            abs_delta = abs(delta)

            if 0.40 <= abs_delta <= 0.65:
                score += 8
                reasons.append(
                    f"Useful delta ({delta:.2f})"
                )

            elif 0.25 <= abs_delta < 0.40:
                score += 3
                reasons.append(
                    f"Lower directional delta ({delta:.2f})"
                )

            elif abs_delta < 0.25:
                score -= 5
                reasons.append(
                    f"Very low delta ({delta:.2f})"
                )

        # Gamma
        if gamma is not None and gamma > 0:
            score += 3
            reasons.append(
                f"Gamma available ({gamma:.4f})"
            )

        # Theta
        if theta is not None:

            if theta < 0:
                # Negative theta is a cost for long options.
                score -= 4
                reasons.append(
                    f"Negative theta ({theta:.4f})"
                )

            else:
                reasons.append(
                    f"Theta ({theta:.4f})"
                )

        # Vega is informational here.
        if vega is not None:
            reasons.append(
                f"Vega ({vega:.4f})"
            )

        return {
            "status": "OK",
            "score": score,
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "reasons": reasons,
        }

    # =========================================================
    # OI ANALYSIS
    # =========================================================

    def analyse_oi(
        self,
        contract: Dict[str, Any],
        option_type: str,
    ) -> Dict[str, Any]:

        oi = contract.get("oi")
        change_oi = contract.get("change_oi")
        ltp = contract.get("ltp")

        if oi is None and change_oi is None:
            return {
                "status": "DATA_UNAVAILABLE",
                "bias": "UNKNOWN",
                "score": 0.0,
                "reasons": [],
            }

        score = 0.0
        reasons = []

        # OI itself confirms liquidity/participation,
        # while change in OI + price gives a basic buildup label.
        if oi is not None:

            if oi >= 500000:
                score += 5
                reasons.append("High open interest")

            elif oi >= 100000:
                score += 3
                reasons.append("Good open interest")

            elif oi < 10000:
                score -= 3
                reasons.append("Low open interest")

        buildup = "UNKNOWN"

        if change_oi is not None and ltp is not None:

            if change_oi > 0 and ltp > 0:
                # Rising OI with rising option price.
                buildup = "LONG_BUILDUP"
                score += 5
                reasons.append(
                    "OI rising with option price"
                )

            elif change_oi > 0 and ltp <= 0:
                buildup = "SHORT_BUILDUP"
                score -= 2
                reasons.append(
                    "OI rising while option price is weak"
                )

            elif change_oi < 0 and ltp > 0:
                buildup = "SHORT_COVERING"
                score += 2
                reasons.append(
                    "OI falling with option price strength"
                )

            elif change_oi < 0 and ltp <= 0:
                buildup = "LONG_UNWINDING"
                score -= 2
                reasons.append(
                    "OI falling with option price weakness"
                )

        return {
            "status": "OK",
            "bias": buildup,
            "score": score,
            "oi": oi,
            "change_oi": change_oi,
            "reasons": reasons,
        }

    # =========================================================
    # IV ANALYSIS
    # =========================================================

    def analyse_iv(
        self,
        contract: Dict[str, Any],
    ) -> Dict[str, Any]:

        iv = contract.get("iv")

        if iv is None:
            return {
                "status": "DATA_UNAVAILABLE",
                "score": 0.0,
                "iv": None,
                "reason": "IV unavailable",
            }

        # IV cannot be judged as expensive/cheap in isolation.
        # This module therefore only records extremes.
        if iv >= 40:
            score = -4.0
            label = "VERY_HIGH_IV"

        elif iv >= 25:
            score = -1.0
            label = "HIGH_IV"

        elif iv >= 12:
            score = 2.0
            label = "NORMAL_IV"

        else:
            score = 0.0
            label = "LOW_IV"

        return {
            "status": "OK",
            "score": score,
            "iv": iv,
            "label": label,
            "reason": f"IV regime: {label}",
        }

    # =========================================================
    # CONTRACT SCORE
    # =========================================================

    def score_contract(
        self,
        contract: Dict[str, Any],
        option_type: Optional[str] = None,
        underlying_price: Optional[float] = None,
        expiry: Optional[str] = None,
        days_to_expiry: Optional[float] = None,
        technical_direction: Optional[str] = None,
    ) -> Dict[str, Any]:

        c = self.normalise_contract(contract)

        if not c.get("valid"):
            return {
                "status": "DATA_UNAVAILABLE",
                "score": 0.0,
                "decision": "REJECT",
                "reason": c.get("reason", "Invalid contract"),
            }

        if option_type:
            c["option_type"] = self.text(option_type)

        option_type = c["option_type"]

        if option_type not in ("CE", "PE", "CALL", "PUT"):
            return {
                "status": "DATA_UNAVAILABLE",
                "score": 0.0,
                "decision": "REJECT",
                "reason": "Unknown option type",
            }

        if option_type == "CALL":
            option_type = "CE"

        if option_type == "PUT":
            option_type = "PE"

        c["option_type"] = option_type

        # Required core data.
        if c["strike"] is None or c["ltp"] is None:
            return {
                "status": "DATA_UNAVAILABLE",
                "score": 0.0,
                "decision": "REJECT",
                "reason": "Strike or option LTP unavailable",
                "contract": c,
            }

        score = 50.0
        reasons = []

        # -----------------------------------------------------
        # Direction
        # -----------------------------------------------------

        direction = self.text(technical_direction)

        if direction in ("LONG", "BULLISH"):

            if option_type == "CE":
                score += 12
                reasons.append(
                    "CE aligned with bullish technical direction"
                )
            else:
                score -= 12
                reasons.append(
                    "PE conflicts with bullish technical direction"
                )

        elif direction in ("SHORT", "BEARISH"):

            if option_type == "PE":
                score += 12
                reasons.append(
                    "PE aligned with bearish technical direction"
                )
            else:
                score -= 12
                reasons.append(
                    "CE conflicts with bearish technical direction"
                )

        # -----------------------------------------------------
        # Greeks
        # -----------------------------------------------------

        greek = self.analyse_greeks(
            c,
            option_type,
        )

        score += greek["score"]
        reasons.extend(greek["reasons"])

        # -----------------------------------------------------
        # OI
        # -----------------------------------------------------

        oi = self.analyse_oi(
            c,
            option_type,
        )

        score += oi["score"]
        reasons.extend(oi["reasons"])

        # -----------------------------------------------------
        # IV
        # -----------------------------------------------------

        iv = self.analyse_iv(c)

        score += iv["score"]

        if iv.get("reason"):
            reasons.append(iv["reason"])

        # -----------------------------------------------------
        # Liquidity
        # -----------------------------------------------------

        liquidity = self.analyse_liquidity(c)

        # Reject extremely poor liquidity rather than hiding it.
        spread = liquidity.get("spread_percent")

        if (
            spread is not None
            and spread > self.max_spread_percent
        ):
            score -= 12
            reasons.append(
                "Liquidity warning: spread too wide"
            )
        else:
            score += liquidity["score"]
            reasons.extend(
                liquidity["reasons"]
            )

        # -----------------------------------------------------
        # Strike distance
        # -----------------------------------------------------

        distance_percent = None

        if (
            underlying_price is not None
            and underlying_price > 0
        ):

            distance_percent = (
                abs(c["strike"] - underlying_price)
                / underlying_price
                * 100
            )

            if distance_percent <= 0.50:
                score += 6
                reasons.append("Near ATM strike")

            elif distance_percent <= 1.00:
                score += 4
                reasons.append("Moderately near ATM")

            elif distance_percent <= 2.00:
                score += 0
                reasons.append("OTM/ITM distance acceptable")

            else:
                score -= 8
                reasons.append("Strike too far from underlying")

        # -----------------------------------------------------
        # Expiry
        # -----------------------------------------------------

        expiry_result = self.analyse_expiry(
            expiry,
            days_to_expiry,
        )

        score += expiry_result["score_adjustment"]

        reasons.append(
            expiry_result["reason"]
        )

        score = round(
            self.clamp(score),
            2,
        )

        # -----------------------------------------------------
        # Decision
        # -----------------------------------------------------

        if score >= self.minimum_option_score:
            decision = "CANDIDATE"

        elif score >= 50:
            decision = "WATCH"

        else:
            decision = "REJECT"

        return {
            "status": "OK",
            "decision": decision,
            "score": score,
            "option_type": option_type,
            "strike": c["strike"],
            "ltp": c["ltp"],
            "expiry": expiry,
            "days_to_expiry": days_to_expiry,
            "distance_from_underlying_percent": (
                round(distance_percent, 3)
                if distance_percent is not None
                else None
            ),
            "contract": c,
            "greeks": greek,
            "oi_analysis": oi,
            "iv_analysis": iv,
            "liquidity": liquidity,
            "expiry_analysis": expiry_result,
            "reasons": reasons[:30],
        }

    # =========================================================
    # ATM / STRIKE CANDIDATES
    # =========================================================

    def select_candidate_strikes(
        self,
        contracts: List[Dict[str, Any]],
        underlying_price: float,
        technical_direction: str,
        expiry: Optional[str] = None,
        days_to_expiry: Optional[float] = None,
    ) -> Dict[str, Any]:

        if not contracts:
            return {
                "status": "DATA_UNAVAILABLE",
                "reason": "No option contracts received",
                "candidates": [],
            }

        spot = self.safe_float(underlying_price)

        if spot is None or spot <= 0:
            return {
                "status": "DATA_UNAVAILABLE",
                "reason": "Underlying price unavailable",
                "candidates": [],
            }

        results = []

        for raw_contract in contracts:

            result = self.score_contract(
                raw_contract,
                underlying_price=spot,
                expiry=expiry,
                days_to_expiry=days_to_expiry,
                technical_direction=technical_direction,
            )

            if result.get("status") == "OK":
                results.append(result)

        if not results:
            return {
                "status": "DATA_UNAVAILABLE",
                "reason": "No valid option contracts",
                "candidates": [],
            }

        # Highest score first.
        results.sort(
            key=lambda x: (
                x.get("score", 0),
                -(
                    x.get(
                        "distance_from_underlying_percent"
                    )
                    or 999
                ),
            ),
            reverse=True,
        )

        candidates = [
            x
            for x in results
            if x.get("decision") == "CANDIDATE"
        ]

        return {
            "status": "OK",
            "underlying_price": spot,
            "technical_direction": technical_direction,
            "total_contracts_analysed": len(results),
            "candidate_count": len(candidates),
            "candidates": candidates[:10],
            "all_ranked": results[:20],
        }

    # =========================================================
    # CALL / PUT SIDE COMPARISON
    # =========================================================

    def compare_ce_pe(
        self,
        contracts: List[Dict[str, Any]],
        underlying_price: float,
        technical_direction: str,
        expiry: Optional[str] = None,
        days_to_expiry: Optional[float] = None,
    ) -> Dict[str, Any]:

        analysis = self.select_candidate_strikes(
            contracts=contracts,
            underlying_price=underlying_price,
            technical_direction=technical_direction,
            expiry=expiry,
            days_to_expiry=days_to_expiry,
        )

        if analysis["status"] != "OK":
            return analysis

        ranked = analysis["all_ranked"]

        ce = [
            x for x in ranked
            if x.get("option_type") == "CE"
        ]

        pe = [
            x for x in ranked
            if x.get("option_type") == "PE"
        ]

        best_ce = ce[0] if ce else None
        best_pe = pe[0] if pe else None

        if best_ce is None and best_pe is None:
            return {
                **analysis,
                "side_comparison": "NO_VALID_SIDE",
                "best_ce": None,
                "best_pe": None,
            }

        # Direction determines preferred side.
        preferred = None

        direction = self.text(technical_direction)

        if direction in ("LONG", "BULLISH"):
            preferred = best_ce

        elif direction in ("SHORT", "BEARISH"):
            preferred = best_pe

        # If technical direction is neutral/mixed,
        # do not manufacture a directional option trade.
        if direction not in (
            "LONG",
            "SHORT",
            "BULLISH",
            "BEARISH",
        ):
            preferred = None

        return {
            **analysis,
            "best_ce": best_ce,
            "best_pe": best_pe,
            "preferred_candidate": preferred,
            "technical_direction": technical_direction,
        }

    # =========================================================
    # OPTION SETUP
    # =========================================================

    def build_option_setup(
        self,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not isinstance(analysis, dict):
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
            }

        candidate = analysis.get(
            "preferred_candidate"
        )

        if not candidate:
            return {
                "status": "OK",
                "decision": "WAIT",
                "reason": (
                    "No option candidate is aligned "
                    "with the technical direction."
                ),
            }

        if candidate.get("decision") != "CANDIDATE":
            return {
                "status": "OK",
                "decision": "WAIT",
                "reason": "Option score below entry threshold",
                "candidate": candidate,
            }

        option_type = candidate.get("option_type")
        strike = candidate.get("strike")
        ltp = self.safe_float(
            candidate.get("ltp")
        )

        if ltp is None or ltp <= 0:
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "reason": "Option entry price unavailable",
            }

        # Do NOT create fake market targets here.
        # Risk levels will be calculated by the later
        # execution/risk layer using real price + ATR.
        return {
            "status": "OK",
            "decision": "OPTION_CANDIDATE",
            "option_type": option_type,
            "strike": strike,
            "expiry": candidate.get("expiry"),
            "entry_reference": ltp,
            "score": candidate.get("score", 0),
            "risk_flags": {
                "expiry_risk": candidate.get(
                    "expiry_analysis",
                    {},
                ).get("risk"),
                "liquidity": candidate.get(
                    "liquidity",
                    {},
                ),
                "iv": candidate.get(
                    "iv_analysis",
                    {},
                ),
                "greeks": candidate.get(
                    "greeks",
                    {},
                ),
            },
            "reasons": candidate.get(
                "reasons",
                [],
            ),
            "note": (
                "Entry/SL/targets must be calculated by "
                "the risk/execution layer from real market data."
            ),
        }

    # =========================================================
    # COMPLETE ANALYSIS
    # =========================================================

    def analyse(
        self,
        contracts: List[Dict[str, Any]],
        underlying_price: float,
        technical_direction: str,
        expiry: Optional[str] = None,
        days_to_expiry: Optional[float] = None,
        pcr: Optional[float] = None,
    ) -> Dict[str, Any]:

        comparison = self.compare_ce_pe(
            contracts=contracts,
            underlying_price=underlying_price,
            technical_direction=technical_direction,
            expiry=expiry,
            days_to_expiry=days_to_expiry,
        )

        if comparison.get("status") != "OK":
            return comparison

        # -----------------------------------------------------
        # PCR
        # -----------------------------------------------------

        pcr_value = self.safe_float(pcr)
        pcr_label = "UNAVAILABLE"
        pcr_score = 0.0

        if pcr_value is not None:

            if pcr_value >= 1.30:
                pcr_label = "BULLISH_BIAS"
                pcr_score = 5.0

            elif pcr_value >= 1.00:
                pcr_label = "MILD_BULLISH_BIAS"
                pcr_score = 2.0

            elif pcr_value >= 0.70:
                pcr_label = "MILD_BEARISH_BIAS"
                pcr_score = -2.0

            else:
                pcr_label = "BEARISH_BIAS"
                pcr_score = -5.0

        preferred = comparison.get(
            "preferred_candidate"
        )

        final_score = 0.0

        if preferred:
            final_score = float(
                preferred.get("score", 0.0)
            )

            # PCR is confirmation only.
            # Do not allow PCR to override technical direction.
            if (
                technical_direction in (
                    "LONG",
                    "BULLISH",
                )
                and pcr_value is not None
                and pcr_score > 0
            ):
                final_score += pcr_score

            elif (
                technical_direction in (
                    "SHORT",
                    "BEARISH",
                )
                and pcr_value is not None
                and pcr_score < 0
            ):
                final_score += abs(pcr_score)

        final_score = round(
            self.clamp(final_score),
            2,
        )

        if preferred and final_score >= self.minimum_option_score:
            decision = "OPTION_CANDIDATE"
        elif preferred:
            decision = "WAIT"
        else:
            decision = "NO_TRADE"

        setup = self.build_option_setup(
            {
                **comparison,
                "preferred_candidate": preferred,
            }
        )

        return {
            "status": "OK",
            "decision": decision,
            "technical_direction": technical_direction,
            "underlying_price": underlying_price,
            "expiry": expiry,
            "days_to_expiry": days_to_expiry,
            "pcr": pcr_value,
            "pcr_label": pcr_label,
            "pcr_score": pcr_score,
            "option_score": final_score,
            "best_ce": comparison.get("best_ce"),
            "best_pe": comparison.get("best_pe"),
            "preferred_candidate": preferred,
            "setup": setup,
            "candidate_count": comparison.get(
                "candidate_count",
                0,
            ),
            "risk_note": (
                "Option score is a deterministic confluence "
                "score, not a probability of profit."
            ),
        }


# =============================================================
# SIMPLE FUNCTION API
# =============================================================

def analyse_options(
    contracts: List[Dict[str, Any]],
    underlying_price: float,
    technical_direction: str,
    expiry: Optional[str] = None,
    days_to_expiry: Optional[float] = None,
    pcr: Optional[float] = None,
    minimum_option_score: float = 65.0,
) -> Dict[str, Any]:

    engine = OptionsIntelligenceEngine(
        minimum_option_score=minimum_option_score
    )

    return engine.analyse(
        contracts=contracts,
        underlying_price=underlying_price,
        technical_direction=technical_direction,
        expiry=expiry,
        days_to_expiry=days_to_expiry,
        pcr=pcr,
    )
