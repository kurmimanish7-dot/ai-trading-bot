from typing import Dict, Any


class RiskManager:
    """
    Risk and safety validation layer.

    This module does NOT place orders.
    It only decides whether an AI directive
    is allowed to proceed.
    """

    def __init__(
        self,
        max_daily_loss: float = 0.0,
        max_trades_per_day: int = 0,
        max_position_quantity: int = 0,
    ):
        self.max_daily_loss = max_daily_loss
        self.max_trades_per_day = max_trades_per_day
        self.max_position_quantity = max_position_quantity

    def validate_decision(
        self,
        decision: Dict[str, Any],
        position: Dict[str, Any],
        daily_pnl: float = 0.0,
        trades_today: int = 0,
    ) -> Dict[str, Any]:

        action = decision.get(
            "action",
            "NO_TRADE"
        )

        confidence = (
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

        # --------------------------------------------------
        # Basic validation
        # --------------------------------------------------

        allowed_actions = {
            "ENTER_LONG",
            "ENTER_SHORT",
            "HOLD",
            "TRAIL_SL",
            "TAKE_PARTIAL",
            "EXIT_NOW",
            "NO_TRADE",
        }

        if action not in allowed_actions:
