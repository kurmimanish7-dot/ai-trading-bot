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
- No real order placement
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

    Stage 1:
        Market data + multi-timeframe analysis

    Stage 2:
        Technical confluence

    Stage 3:
        Options intelligence

    Stage 4:
        Final Expert Advisor decision

    This class never places real orders.
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

        # -----------------------------------------------------
        # STAGE 1
        # -----------------------------------------------------

        self.market_engine = EAMarketEngine(
            smart_api=smart_api
        )

        # -----------------------------------------------------
        # STAGE 2
        # -----------------------------------------------------

        self.technical_engine = TechnicalConfluenceEngine(
            minimum_trade_score=technical_score
        )

        # -----------------------------------------------------
        # STAGE 3
        # -----------------------------------------------------

        self.options_engine = OptionsIntelligenceEngine(
            minimum_option_score=option_score
        )

        # -----------------------------------------------------
        # STAGE 4
        # -----------------------------------------------------
        #
        # IMPORTANT:
        # EADecisionEngine accepts a CONFIG dictionary.
        # It does NOT accept the threshold values directly
        # as keyword arguments.
        #

        decision_config = {
            "minimum_technical_score": technical_score,
            "minimum_option_score": option_score,
            "minimum_final_score": final_score,
            "minimum_rr": minimum_rr,
        }

        self.decision_engine = EADecisionEngine(
            config=decision_config
        )

    # =========================================================
    # SAFE HELPERS
    # =========================================================

    @staticmethod
    def safe_float(value) -> Optional[float]:
        try:
            if value is None:
                return None

            number = float(value)

            if number != number:
                return None

            return number

        except (TypeError, ValueError):
            return None

    @staticmethod
    def is_unavailable(value) -> bool:
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
                "NULL",
                "WAITING",
            )

        return False

    @staticmethod
    def _unwrap_timeframe(value: Any) -> Dict[str, Any]:
        """
        Stage 1 currently returns:

        {
            "status": "...",
            "timeframe": "5M",
            "interval": "...",
            "analysis": {
                "price": ...,
                "ema9": ...,
                ...
            }
        }

        Stage 2 and Stage 4 work more easily with the
        inner analysis dictionary.

        This function supports both formats.
        """

        if not isinstance(value, dict):
            return {}

        analysis = value.get("analysis")

        if isinstance(analysis, dict):
            return analysis

        return value

    # =========================================================
    # NORMALISE MARKET SNAPSHOT
    # =========================================================

    def normalise_market_snapshot(
        self,
        market_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Convert Stage 1 output into a common structure.

        Stage 2 expects:

            mtf = {
                "1M": {...},
                "3M": {...},
                ...
            }

        Stage 4 expects direct timeframe snapshots.

        We also create:

            support_resistance = {
                "support": ...,
                "resistance": ...
            }
        """

        if not isinstance(market_snapshot, dict):
            return {
                "status": "DATA_UNAVAILABLE",
                "mtf": {},
                "multi_timeframe": {},
                "timeframes": {},
            }

        result = dict(market_snapshot)

        # -----------------------------------------------------
        # Extract Stage 1 timeframes
        # -----------------------------------------------------

        raw_timeframes = market_snapshot.get(
            "timeframes",
            {}
        )

        mtf = {}

        if isinstance(raw_timeframes, dict):

            for timeframe, value in raw_timeframes.items():

                snapshot = self._unwrap_timeframe(value)

                if not isinstance(snapshot, dict):
                    snapshot = {}

                mtf[str(timeframe).upper()] = snapshot

        # -----------------------------------------------------
        # Support versions that already contain "mtf"
        # -----------------------------------------------------

        if not mtf:

            existing_mtf = market_snapshot.get("mtf")

            if isinstance(existing_mtf, dict):

                for timeframe, value in existing_mtf.items():

                    snapshot = self._unwrap_timeframe(value)

                    if not isinstance(snapshot, dict):
                        snapshot = {}

                    mtf[str(timeframe).upper()] = snapshot

        # -----------------------------------------------------
        # Support "multi_timeframe"
        # -----------------------------------------------------

        if not mtf:

            existing_mtf = market_snapshot.get(
                "multi_timeframe"
            )

            if isinstance(existing_mtf, dict):

                for timeframe, value in existing_mtf.items():

                    snapshot = self._unwrap_timeframe(value)

                    if not isinstance(snapshot, dict):
                        snapshot = {}

                    mtf[str(timeframe).upper()] = snapshot

        # -----------------------------------------------------
        # Store normalised structures
        # -----------------------------------------------------

        result["mtf"] = mtf
        result["multi_timeframe"] = mtf
        result["timeframes"] = mtf

        # -----------------------------------------------------
        # Build support/resistance wrapper for Stage 4
        # -----------------------------------------------------

        support = None
        resistance = None

        preferred_timeframes = (
            "5M",
            "15M",
            "3M",
            "1M",
            "30M",
            "1H",
        )

        for timeframe in preferred_timeframes:

            snapshot = mtf.get(timeframe)

            if not isinstance(snapshot, dict):
                continue

            if support is None:
                support = self.safe_float(
                    snapshot.get("support")
                )

            if resistance is None:
                resistance = self.safe_float(
                    snapshot.get("resistance")
                )

            if support is not None and resistance is not None:
                break

        # Existing Stage 1 support/resistance object
        existing_sr = market_snapshot.get(
            "support_resistance"
        )

        if isinstance(existing_sr, dict):

            if support is None:
                support = self.safe_float(
                    existing_sr.get("support")
                )

            if resistance is None:
                resistance = self.safe_float(
                    existing_sr.get("resistance")
                )

        result["support_resistance"] = {
            "support": support,
            "resistance": resistance,
        }

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

        NOTE:
        Current EAMarketEngine.build_market_snapshot()
        does not accept symbol.

        Symbol is therefore retained by the pipeline but is
        not passed into Stage 1.
        """

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

        if not isinstance(snapshot, dict):

            return {
                "status": "DATA_UNAVAILABLE",
                "error": "Stage 1 returned invalid data",
                "timeframes": {},
                "mtf": {},
            }

        normalised = self.normalise_market_snapshot(
            snapshot
        )

        # Keep symbol available to downstream stages.
        normalised["symbol"] = symbol
        normalised["exchange"] = exchange
        normalised["token"] = token

        return normalised

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
    # OPTIONS INPUT NORMALISATION
    # =========================================================

    def normalise_options_input(
        self,
        options_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Normalise different possible option-chain wrappers.

        Supported:

            {
                "contracts": [...]
            }

        or:

            {
                "option_chain": [...]
            }

        or:

            {
                "data": [...]
            }
        """

        if not isinstance(options_data, dict):

            return {
                "status": "DATA_UNAVAILABLE",
                "contracts": [],
            }

        result = dict(options_data)

        contracts = result.get("contracts")

        if not isinstance(contracts, list):

            contracts = result.get(
                "option_chain"
            )

        if not isinstance(contracts, list):

            contracts = result.get(
                "data"
            )

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

        No option data = DATA_UNAVAILABLE.

        No synthetic option values are generated.
        """

        data = self.normalise_options_input(
            options_data
        )

        contracts = data.get(
            "contracts",
            []
        )

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

        if underlying_price is None:

            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "preferred_candidate": None,
                "best_ce": None,
                "best_pe": None,
                "setup": None,
                "reason": "Underlying price unavailable",
                "contracts": contracts,
            }

        try:

            result = self.options_engine.analyse(
                contracts=contracts,
                underlying_price=underlying_price,
                technical_direction=technical_direction,
                expiry=expiry,
                days_to_expiry=days_to_expiry,
                pcr=pcr,
            )

        except Exception as exc:

            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "preferred_candidate": None,
                "best_ce": None,
                "best_pe": None,
                "setup": None,
                "reason": f"Stage 3 error: {exc}",
                "contracts": contracts,
            }

        if not isinstance(result, dict):

            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "preferred_candidate": None,
                "best_ce": None,
                "best_pe": None,
                "setup": None,
                "reason": "Stage 3 returned invalid data",
                "contracts": contracts,
            }

        return result

    # =========================================================
    # UNDERLYING PRICE
    # =========================================================

    def get_underlying_price(
        self,
        market_snapshot: Dict[str, Any],
    ) -> Optional[float]:
        """
        Prefer lower execution timeframes first.
        """

        if not isinstance(market_snapshot, dict):
            return None

        timeframes = market_snapshot.get(
            "timeframes",
            {}
        )

        if isinstance(timeframes, dict):

            for timeframe in (
                "5M",
                "15M",
                "3M",
                "1M",
                "30M",
                "1H",
            ):

                snapshot = timeframes.get(
                    timeframe,
                    {}
                )

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

                    if value is not None and value > 0:
                        return value

        # Top-level fallback
        for key in (
            "price",
            "ltp",
            "underlying_price",
        ):

            value = self.safe_float(
                market_snapshot.get(key)
            )

            if value is not None and value > 0:
                return value

        return None

    # =========================================================
    # EXPIRY
    # =========================================================

    @staticmethod
    def calculate_days_to_expiry(
        expiry: Optional[str],
    ) -> Optional[float]:
        """
        Supported formats:

            29SEP2026
            29-SEP-2026
            2026-09-29
            2026/09/29
            29/09/2026
            29-09-2026
        """

        if not expiry:
            return None

        text = str(
            expiry
        ).strip().upper()

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
    ) -> Dict[str, Any]:
        """
        Run final Expert Advisor decision.

        IMPORTANT:
        Actual Stage 4 signature is:

            decide(
                market_snapshot,
                technical_result,
                option_result,
                instrument
            )

        No real order is placed.
        """

        if options_result is None:

            options_result = {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
            }

        try:

            result = self.decision_engine.decide(
                market_snapshot=market_snapshot,
                technical_result=technical_result,
                option_result=options_result,
                instrument=symbol,
            )

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
        Complete Expert Advisor pipeline:

            Stage 1
               ↓
            Stage 2
               ↓
            Stage 3
               ↓
            Stage 4
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

        if market_snapshot.get(
            "status"
        ) == "DATA_UNAVAILABLE":

            return {
                "status": "DATA_UNAVAILABLE",
                "decision": "NO_TRADE",
                "symbol": symbol,
                "exchange": exchange,
                "token": token,
                "market": market_snapshot,
                "technical": {
                    "status": "DATA_UNAVAILABLE",
                    "direction": "NEUTRAL",
                    "score": 0.0,
                },
                "options": {
                    "status": "DATA_UNAVAILABLE",
                },
                "ea_decision": {
                    "decision": "NO_TRADE",
                },
                "paper_trading": True,
                "reason": market_snapshot.get(
                    "error",
                    "Market data unavailable",
                ),
            }

        # -----------------------------------------------------
        # UNDERLYING PRICE
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
            "BUY",
        ):

            technical_direction = "LONG"

        elif technical_direction in (
            "SHORT",
            "BEARISH",
            "SELL",
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
        )

        # -----------------------------------------------------
        # FINAL UNIFIED RESULT
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
    # ALIAS FOR APP
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
# FACTORY
# =============================================================

def build_ea_pipeline(
    smart_api=None,
    technical_score: float = 65.0,
    option_score: float = 65.0,
    final_score: float = 70.0,
    minimum_rr: float = 1.5,
) -> EAPipeline:

    return EAPipeline(
        smart_api=smart_api,
        technical_score=technical_score,
        option_score=option_score,
        final_score=final_score,
        minimum_rr=minimum_rr,
    )
