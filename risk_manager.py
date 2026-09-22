from typing import Dict, Any


class RiskManager:
    """
    Risk and safety validation layer.

    Paper-trading safe.
    This module does NOT place orders.
    It only validates AI trading decisions.
    """

    ALLOWED_ACTIONS = {
        "ENTER_LONG",
        "ENTER_SHORT",
        "HOLD",
        "TRAIL_SL",
        "TAKE_PARTIAL",
        "EXIT_NOW",
        "NO_TRADE",
    }

    ENTRY_ACTIONS = {
        "ENTER_LONG",
        "ENTER_SHORT",
    }

    POSITION_MANAGEMENT_ACTIONS = {
        "HOLD",
        "TRAIL_SL",
        "TAKE_PARTIAL",
        "EXIT_NOW",
    }

    def __init__(
        self,
        max_daily_loss: float = 2000.0,
        max_trades_per_day: int = 5,
        max_position_quantity: int = 50,
        min_confidence: float = 75.0,
    ):
        self.max_daily_loss = max_daily_loss
        self.max_trades_per_day = max_trades_per_day
        self.max_position_quantity = max_position_quantity
        self.min_confidence = min_confidence

    def validate_decision(
        self,
        decision: Dict[str, Any],
        position: Dict[str, Any],
        daily_pnl: float = 0.0,
        trades_today: int = 0,
    ) -> Dict[str, Any]:

        if not isinstance(decision, dict):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": "Invalid decision format.",
            }

        action = decision.get(
            "action",
            "NO_TRADE"
        )

        # --------------------------------------------------
        # 1. Validate action
        # --------------------------------------------------

        if action not in self.ALLOWED_ACTIONS:
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": f"Invalid action: {action}",
            }

        # --------------------------------------------------
        # 2. Safely read confidence
        # --------------------------------------------------

        confidence_data = decision.get(
            "algorithmic_confidence",
            {}
        )

        if not isinstance(
            confidence_data,
            dict
        ):
            confidence_data = {}

        try:
            confidence = float(
                confidence_data.get(
                    "overall_score",
                    0
                )
            )
        except (TypeError, ValueError):
            confidence = 0.0

        confidence = max(
            0.0,
            min(
                100.0,
                confidence
            )
        )

        # --------------------------------------------------
        # 3. Safely read execution details
        # --------------------------------------------------

        execution = decision.get(
            "execution_details",
            {}
        )

        if not isinstance(
            execution,
            dict
        ):
            execution = {}

        try:
            quantity_fraction = float(
                execution.get(
                    "quantity_fraction",
                    1.0
                )
            )
        except (TypeError, ValueError):
            quantity_fraction = 0.0

        # --------------------------------------------------
        # 4. Quantity fraction validation
        # --------------------------------------------------

        if (
            quantity_fraction <= 0
            or quantity_fraction > 1
        ):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": "Invalid quantity fraction.",
            }

        # --------------------------------------------------
        # 5. DAILY LOSS PROTECTION
        #
        # Daily loss limit blocks NEW entries only.
        # Existing positions must remain manageable.
        # --------------------------------------------------

        if (
            action in self.ENTRY_ACTIONS
            and daily_pnl <= -abs(
                self.max_daily_loss
            )
        ):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": (
                    "Maximum daily loss limit reached."
                ),
            }

        # --------------------------------------------------
        # 6. MAXIMUM TRADES PER DAY
        #
        # Only new entries count toward this limit.
        # --------------------------------------------------

        if (
            action in self.ENTRY_ACTIONS
            and trades_today >= self.max_trades_per_day
        ):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": (
                    "Maximum trades per day reached."
                ),
            }

        # --------------------------------------------------
        # 7. MINIMUM AI CONFIDENCE
        #
        # Confidence is required for new entries.
        # Position-management actions can still execute.
        # --------------------------------------------------

        if (
            action in self.ENTRY_ACTIONS
            and confidence < self.min_confidence
        ):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": (
                    f"AI confidence {confidence}% "
                    f"is below minimum "
                    f"{self.min_confidence}%."
                ),
            }

        # --------------------------------------------------
        # 8. EXISTING POSITION PROTECTION
        #
        # Do not allow a second entry while a position
        # is already active.
        # --------------------------------------------------

        if (
            action in self.ENTRY_ACTIONS
            and position.get(
                "has_position",
                False
            )
        ):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": (
                    "Existing position already active."
                ),
            }

        # --------------------------------------------------
        # 9. POSITION MANAGEMENT VALIDATION
        #
        # Management actions require an active position.
        # --------------------------------------------------

        if (
            action in self.POSITION_MANAGEMENT_ACTIONS
            and not position.get(
                "has_position",
                False
            )
        ):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": (
                    "No active position to manage."
                ),
            }

        # --------------------------------------------------
        # 10. SUCCESS
        # --------------------------------------------------

        return {
            "allowed": True,
            "action": action,
            "confidence": confidence,
            "quantity_fraction": quantity_fraction,
            "reason": "Risk validation passed.",
        }
