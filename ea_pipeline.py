"""
EA Pipeline
===========

Stage 5 integration layer.

Connects:
    Stage 1 -> EAMarketEngine
    Stage 2 -> TechnicalConfluenceEngine
    Stage 3 -> OptionsIntelligenceEngine
    Stage 4 -> EADecisionEngine

IMPORTANT:
- Paper trading only
- No order placement
- No fake market data
- Missing data remains DATA_UNAVAILABLE
"""

from typing import Dict, Any, Optional
from datetime import datetime, date

from ea_market_engine import EAMarketEngine
from technical_confluence_engine import TechnicalConfluenceEngine
from options_intelligence_engine import OptionsIntelligenceEngine
from ea_decision_engine import EADecisionEngine


class EAPipeline:
    """
    Complete Expert Advisor analysis pipeline.

    This class ONLY analyses market data.

    It does NOT:
    - place orders
    - modify broker positions
    - create fake prices
    - create fake options data
    """

    def __init__(
        self,
        smart_api=None,
        technical_score: float = 65.0,
        option_score: float = 65.0,
        final_score: float = 70.0,
        minimum_rr: float = 1.5,
    ):
        self.smart_api = smart_api

        self.market_engine = EAMarketEngine(
            smart_api=smart_api
        )

        self.technical_engine = TechnicalConfluenceEngine(
            minimum_trade_score=technical_score
        )

        self.options_engine = OptionsIntelligenceEngine(
            minimum_option_score=option_score
        )

        self.decision_engine = EADecisionEngine(
            minimum_technical_score=technical_score,
            minimum_option_score=option_score,
            minimum_final_score=final_score,
            minimum_rr=minimum_rr,
        )

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def safe_float(value):
        try:
            if value is None:
                return None

            value = float(value)

            if value != value:
                return None

            return value

        except (TypeError, ValueError):
            return None

    @staticmethod
    def is_unavailable(value):
        if value is None:
            return True

        if isinstance(value, str):
            return value.strip().upper() in (
                "",
                "UNAVAILABLE",
                "DATA_UNAVAILABLE",
                "N/A",
                "NA",
                "NONE",
            )

        return False

    @staticmethod
    def _unwrap_timeframe(value):
        """
        Stage 1 returns:

            {
                status,
                timeframe,
                interval,
                analysis: {
                    price,
                    ema9,
                    ...
                }
            }

        Stage 2 expects the inner analysis dictionary.

        This function normalises both formats.
        """

        if not isinstance(value, dict):
            return {}

        analysis = value.get("analysis")

        if isinstance(analysis, dict):
            return analysis

        return value

    # =========================================================
    # STAGE 1 -> STAGE 2 NORMALISATION
    # =========================================================

    def normalise_market_snapshot(
        self,
        market_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Convert Stage 1 output into the structure expected by
        Stage 2 and Stage 4.
        """

        if not isinstance(market_snapshot, dict):
            return {
                "status": "DATA_UNAVAILABLE",
                "mtf": {},
                "timeframes": {},
            }

        raw_timeframes = market_snapshot.get(
            "timeframes",
            {}
        )

        mtf = {}
        normalised_timeframes = {}

        if isinstance(raw_timeframes, dict):

            for timeframe, value in raw_timeframes.items():

                snapshot = self._unwrap_timeframe(value)

                if not isinstance(snapshot, dict):
                    snapshot = {}

                mtf[timeframe] = snapshot

                # Keep a consistent direct snapshot for Stage 4.
                normalised_timeframes[timeframe] = snapshot

        # Some future versions may already provide mtf.
        if not mtf:
            existing_mtf = market_snapshot.get("mtf")

            if isinstance(existing_mtf, dict):
                for timeframe, value in existing_mtf.items():
                    mtf[timeframe] = self._unwrap_timeframe(
                        value
                    )

        result = dict(market_snapshot)

        result["mtf"] = mtf
        result["multi_timeframe"] = mtf
        result["timeframes"] = normalised_timeframes

        return result

    # =========================================================
    # STAGE 1
    # =========================================================

    def run_market_analysis(
        self,
        exchange: str,
        token: str,
        symbol: str,
        days: int = 5,
    ) -> Dict[str, Any]:
        """
        Run Stage 1 multi-timeframe market analysis.
        """

        try:
            snapshot = self.market_engine.build_market_snapshot(
                exchange=exchange,
                token=token,
                symbol=symbol,
                days=days,
            )

        except TypeError:
            # Compatibility fallback for versions where symbol
            # is not part of the method signature.
            try:
                snapshot = self.market_engine.build_market_snapshot(
                    exchange=exchange,
                    token=token,
                    days=days,
                )

            except Exception as exc:
                return {
                    "status": "DATA_UNAVAILABLE",
                    "error": f"Stage 1 error: {exc}",
                    "timeframes": {},
                    "mtf": {},
                }

        except Exception as exc:
            return {
                "status": "DATA_UNAVAILABLE",
                "error": f"Stage 1 error: {exc}",
                "timeframes": {},
                "mtf": {},
            }

        if not isinstance(snapshot, dict):
            return {
                "status": "DATA_UNAVAILABLE",
                "error": "Stage 1 returned invalid data",
                "timeframes": {},
                "mtf": {},
            }

        return self.normalise_market_snapshot(
            snapshot
        )

    # =========================================================
    # STAGE 2
    # =========================================================

    def run_technical_analysis(
        self,
        market_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Run deterministic technical confluence.
        """

        normalised = self.normalise_market_snapshot(
            market_snapshot
        )

        try:
            result = self.technical_engine.calculate_confluence(
                normalised
            )

        except Exception as exc:
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "direction": "NEUTRAL",
                "score": 0.0,
                "reason": f"Stage 2 error: {exc}",
            }

        if not isinstance(result, dict):
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "direction": "NEUTRAL",
                "score": 0.0,
                "reason": "Stage 2 returned invalid data",
            }

        return result

    # =========================================================
    # OPTIONS DATA NORMALISATION
    # =========================================================

    def normalise_options_input(
        self,
        options_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Keep Stage 3 input flexible.

        The app may later provide option data in slightly
        different wrappers.
        """

        if not isinstance(options_data, dict):
            return {
                "status": "DATA_UNAVAILABLE",
                "contracts": [],
            }

        result = dict(options_data)

        contracts = result.get("contracts")

        if not isinstance(contracts, list):
            contracts = result.get("option_chain")

        if not isinstance(contracts, list):
            contracts = result.get("data")

        if not isinstance(contracts, list):
            contracts = []

        result["contracts"] = contracts

        return result

    # =========================================================
    # STAGE 3
    # =========================================================

    def run_options_analysis(
        self,
        options_data: Optional[Dict[str, Any]],
        underlying_price: Optional[float],
        technical_direction: Optional[str],
        expiry: Optional[str] = None,
        days_to_expiry: Optional[float] = None,
        pcr: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run Stage 3 options intelligence.

        No option data means DATA_UNAVAILABLE.
        No synthetic option values are generated.
        """

        data = self.normalise_options_input(
            options_data
        )

        contracts = data.get("contracts", [])

        if not contracts:
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "preferred_candidate": None,
                "best_ce": None,
                "best_pe": None,
                "setup": None,
                "reason": "Option-chain data unavailable",
                "contracts": [],
            }

        try:
            # Primary Stage 3 API.
            result = self.options_engine.analyse(
                contracts=contracts,
                underlying_price=underlying_price,
                technical_direction=technical_direction,
                expiry=expiry,
                days_to_expiry=days_to_expiry,
                pcr=pcr,
            )

        except TypeError:
            # Compatibility with alternate Stage 3 signatures.
            try:
                result = self.options_engine.analyse(
                    option_chain=contracts,
                    underlying_price=underlying_price,
                    technical_direction=technical_direction,
                    expiry=expiry,
                    days_to_expiry=days_to_expiry,
                    pcr=pcr,
                )

            except TypeError:
                try:
                    result = self.options_engine.analyse(
                        contracts,
                        underlying_price,
                        technical_direction,
                        expiry,
                        days_to_expiry,
                        pcr,
                    )

                except Exception as exc:
                    return {
                        "status": "DATA_UNAVAILABLE",
                        "decision": "NO_TRADE",
                        "preferred_candidate": None,
                        "reason": f"Stage 3 error: {exc}",
                    }

            except Exception as exc:
                return {
                    "status": "DATA_UNAVAILABLE",
                    "decision": "NO_TRADE",
                    "preferred_candidate": None,
                    "reason": f"Stage 3 error: {exc}",
                }

        except Exception as exc:
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "preferred_candidate": None,
                "reason": f"Stage 3 error: {exc}",
            }

        if not isinstance(result, dict):
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "preferred_candidate": None,
                "reason": "Stage 3 returned invalid data",
            }

        return result

    # =========================================================
    # EXTRACT UNDERLYING PRICE
    # =========================================================

    def get_underlying_price(
        self,
        market_snapshot: Dict[str, Any],
    ) -> Optional[float]:
        """
        Prefer 5M, then 15M, then 3M, then 1M.
        """

        timeframes = market_snapshot.get(
            "timeframes",
            {}
        )

        for timeframe in (
            "5M",
            "15M",
            "3M",
            "1M",
            "30M",
            "1H",
        ):
            snapshot = timeframes.get(timeframe, {})

            if not isinstance(snapshot, dict):
                continue

            for key in (
                "price",
                "ltp",
                "close",
            ):
                value = self.safe_float(
                    snapshot.get(key)
                )

                if value is not None:
                    return value

        # Fallback to top-level fields.
        for key in (
            "price",
            "ltp",
            "underlying_price",
        ):
            value = self.safe_float(
                market_snapshot.get(key)
            )

            if value is not None:
                return value

        return None

    # =========================================================
    # DAYS TO EXPIRY
    # =========================================================

    @staticmethod
    def calculate_days_to_expiry(
        expiry: Optional[str],
    ) -> Optional[float]:
        """
        Supports common formats:

            29SEP2026
            29-SEP-2026
            2026-09-29
            2026/09/29
            29/09/2026
        """

        if not expiry:
            return None

        text = str(expiry).strip().upper()

        formats = (
            "%d%b%Y",
            "%d-%b-%Y",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
        )

        expiry_date = None

        for fmt in formats:
            try:
                expiry_date = datetime.strptime(
                    text,
                    fmt
                ).date()

                break

            except ValueError:
                continue

        if expiry_date is None:
            return None

        today = date.today()

        return float(
            (expiry_date - today).days
        )

    # =========================================================
    # STAGE 4
    # =========================================================

    def run_decision(
        self,
        market_snapshot: Dict[str, Any],
        technical_result: Dict[str, Any],
        options_result: Optional[Dict[str, Any]] = None,
        symbol: Optional[str] = None,
        expiry: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run final Expert Advisor decision.

        Output is a PAPER analysis only.
        """

        if options_result is None:
            options_result = {
                "status": "DATA_UNAVAILABLE"
            }

        try:
            result = self.decision_engine.decide(
                market_snapshot=market_snapshot,
                technical_result=technical_result,
                options_result=options_result,
                symbol=symbol,
                expiry=expiry,
            )

        except TypeError:
            try:
                result = self.decision_engine.decide(
                    market_snapshot,
                    technical_result,
                    options_result,
                    symbol,
                    expiry,
                )

            except Exception as exc:
                return {
                    "status": "DATA_UNAVAILABLE",
                    "decision": "NO_TRADE",
                    "reason": f"Stage 4 error: {exc}",
                    "paper_trading": True,
                }

        except Exception as exc:
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "reason": f"Stage 4 error: {exc}",
                "paper_trading": True,
            }

        if not isinstance(result, dict):
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "reason": "Stage 4 returned invalid data",
                "paper_trading": True,
            }

        result["paper_trading"] = True

        return result

    # =========================================================
    # COMPLETE PIPELINE
    # =========================================================

    def analyse(
        self,
        exchange: str,
        token: str,
        symbol: str,
        expiry: Optional[str] = None,
        options_data: Optional[Dict[str, Any]] = None,
        days: int = 5,
        pcr: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Complete:

            Stage 1
              ↓
            Stage 2
              ↓
            Stage 3
              ↓
            Stage 4

        Returns one unified EA result.
        """

        # -----------------------------------------------------
        # STAGE 1
        # -----------------------------------------------------

        market_snapshot = self.run_market_analysis(
            exchange=exchange,
            token=token,
            symbol=symbol,
            days=days,
        )

        # If market data itself failed, do not manufacture a
        # signal.
        if market_snapshot.get("status") == "DATA_UNAVAILABLE":
            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "symbol": symbol,
                "exchange": exchange,
                "token": token,
                "market": market_snapshot,
                "technical": {
                    "status": "DATA_UNAVAILABLE"
                },
                "options": {
                    "status": "DATA_UNAVAILABLE"
                },
                "ea_decision": {
                    "decision": "NO_TRADE"
                },
                "paper_trading": True,
                "reason": market_snapshot.get(
                    "error",
                    "Market data unavailable",
                ),
            }

        # -----------------------------------------------------
        # UNDERLYING
        # -----------------------------------------------------

        underlying_price = self.get_underlying_price(
            market_snapshot
        )

        # -----------------------------------------------------
        # STAGE 2
        # -----------------------------------------------------

        technical_result = self.run_technical_analysis(
            market_snapshot
        )

        technical_direction = technical_result.get(
            "direction"
        )

        if technical_direction in (
            "LONG",
            "BULLISH",
        ):
            technical_direction = "LONG"

        elif technical_direction in (
            "SHORT",
            "BEARISH",
        ):
            technical_direction = "SHORT"

        else:
            technical_direction = "NEUTRAL"

        # -----------------------------------------------------
        # EXPIRY
        # -----------------------------------------------------

        days_to_expiry = self.calculate_days_to_expiry(
            expiry
        )

        # -----------------------------------------------------
        # STAGE 3
        # -----------------------------------------------------

        options_result = self.run_options_analysis(
            options_data=options_data,
            underlying_price=underlying_price,
            technical_direction=technical_direction,
            expiry=expiry,
            days_to_expiry=days_to_expiry,
            pcr=pcr,
        )

        # -----------------------------------------------------
        # STAGE 4
        # -----------------------------------------------------

        decision_result = self.run_decision(
            market_snapshot=market_snapshot,
            technical_result=technical_result,
            options_result=options_result,
            symbol=symbol,
            expiry=expiry,
        )

        # -----------------------------------------------------
        # UNIFIED RESULT
        # -----------------------------------------------------

        return {
            "status": "OK",
            "timestamp": datetime.now().isoformat(),

            "instrument": {
                "symbol": symbol,
                "exchange": exchange,
                "token": token,
                "underlying_price": underlying_price,
            },

            "expiry": {
                "expiry": expiry,
                "days_to_expiry": days_to_expiry,
            },

            "stage_1_market": market_snapshot,

            "stage_2_technical": technical_result,

            "stage_3_options": options_result,

            "stage_4_decision": decision_result,

            "ea_decision": decision_result,

            "paper_trading": True,

            "safety": {
                "real_orders_allowed": False,
                "paper_only": True,
            },
        }

    # =========================================================
    # ALIAS
    # =========================================================

    def build_ea_analysis(
        self,
        exchange: str,
        token: str,
        symbol: str,
        expiry: Optional[str] = None,
        options_data: Optional[Dict[str, Any]] = None,
        days: int = 5,
        pcr: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Friendly alias for app.py.
        """

        return self.analyse(
            exchange=exchange,
            token=token,
            symbol=symbol,
            expiry=expiry,
            options_data=options_data,
            days=days,
            pcr=pcr,
        )


# =============================================================
# SIMPLE FUNCTION API
# =============================================================

def build_ea_pipeline(
    smart_api=None,
    technical_score: float = 65.0,
    option_score: float = 65.0,
    final_score: float = 70.0,
    minimum_rr: float = 1.5,
) -> EAPipeline:
    """
    Create a ready-to-use EA pipeline.
    """

    return EAPipeline(
        smart_api=smart_api,
        technical_score=technical_score,
        option_score=option_score,
        final_score=final_score,
        minimum_rr=minimum_rr,
    )
