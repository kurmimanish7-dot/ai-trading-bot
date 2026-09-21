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

        action = decision.get("action", "NO_TRADE")

        confidence = float(
            decision
            .get("algorithmic_confidence", {})
            .get("overall_score", 0)
        )

        execution = decision.get(
            "execution_details",
            {}
        )

        quantity_fraction = float(
            execution.get(
                "quantity_fraction",
                1.0
            )
        )

        # 1. Validate action
        if action not in self.ALLOWED_ACTIONS:
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": f"Invalid action: {action}",
            }

        # 2. Daily loss protection
        if daily_pnl <= -abs(self.max_daily_loss):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": "Maximum daily loss limit reached.",
            }

        # 3. Maximum trades per day
        if (
            action in {"ENTER_LONG", "ENTER_SHORT"}
            and trades_today >= self.max_trades_per_day
        ):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": "Maximum trades per day reached.",
            }

        # 4. Minimum AI confidence
        if (
            action in {"ENTER_LONG", "ENTER_SHORT"}
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

        # 5. Quantity fraction validation
        if quantity_fraction <= 0 or quantity_fraction > 1:
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": "Invalid quantity fraction.",
            }

        # 6. Existing position protection
        if (
            action in {"ENTER_LONG", "ENTER_SHORT"}
            and position.get("has_position", False)
        ):
            return {
                "allowed": False,
                "action": "NO_TRADE",
                "reason": "Existing position already active.",
            }

        return {
            "allowed": True,
            "action": action,
            "confidence": confidence,
            "quantity_fraction": quantity_fraction,
            "reason": "Risk validation passed.",
        }
