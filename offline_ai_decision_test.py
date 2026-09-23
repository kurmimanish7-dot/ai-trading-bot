from risk_manager import RiskManager


SYSTEM_SCHEMA_ACTIONS = {
    "ENTER_LONG",
    "ENTER_SHORT",
    "HOLD",
    "TRAIL_SL",
    "TAKE_PARTIAL",
    "EXIT_NOW",
    "NO_TRADE",
}


def validate_ai_decision(decision: dict) -> dict:

    if not isinstance(decision, dict):
        return {
            "action": "NO_TRADE",
            "algorithmic_confidence": {
                "overall_score": 0
            },
        }

    action = decision.get(
        "action",
        "NO_TRADE"
    )

    if action not in SYSTEM_SCHEMA_ACTIONS:
        action = "NO_TRADE"

    confidence = float(
        decision.get(
            "algorithmic_confidence",
            {}
        ).get(
            "overall_score",
            0
        )
    )

    confidence = max(
        0.0,
        min(100.0, confidence)
    )

    decision["action"] = action

    decision["algorithmic_confidence"] = {
        "overall_score": confidence
    }

    return decision


def main():

    print("")
    print("========================================")
    print(" OFFLINE AI DECISION TEST")
    print(" REAL GEMINI API : NO")
    print(" REAL MARKET     : NO")
    print(" REAL ORDERS     : NO")
    print("========================================")
    print("")

    # --------------------------------------------------------
    # SIMULATED AI DECISION
    # --------------------------------------------------------

    decision = {
        "action": "ENTER_LONG",

        "execution_details": {
            "order_type": "MARKET",
            "suggested_price": 25000.0,
            "revised_stop_loss": 24950.0,
            "target_1": 25100.0,
            "target_2": 25200.0,
            "quantity_fraction": 1.0,
        },

        "algorithmic_confidence": {
            "overall_score": 85.0
        },

        "rationale": (
            "Offline simulated bullish setup."
        ),
    }

    print("1. Raw AI decision:")
    print(decision)

    # --------------------------------------------------------
    # VALIDATE AI DECISION
    # --------------------------------------------------------

    validated = validate_ai_decision(
        decision
    )

    print("")
    print("2. Validated AI decision:")
    print(validated)

    # --------------------------------------------------------
    # BASIC VALIDATION
    # --------------------------------------------------------

    assert validated["action"] in SYSTEM_SCHEMA_ACTIONS

    confidence = validated[
        "algorithmic_confidence"
    ]["overall_score"]

    assert 0 <= confidence <= 100

    assert (
        validated["execution_details"]
        ["suggested_price"] > 0
    )

    assert (
        validated["execution_details"]
        ["revised_stop_loss"]
        < validated["execution_details"]
        ["suggested_price"]
    )

    assert (
        validated["execution_details"]
        ["target_1"]
        > validated["execution_details"]
        ["suggested_price"]
    )

    # --------------------------------------------------------
    # RISK MANAGER
    # --------------------------------------------------------

    risk_manager = RiskManager(
        max_daily_loss=2000.0,
        max_trades_per_day=5,
        max_position_quantity=50,
        min_confidence=75.0,
    )

    position = {
        "has_position": False,
        "direction": "NONE",
        "quantity": 0,
    }

    risk_result = risk_manager.validate_decision(
        decision=validated,
        position=position,
        daily_pnl=0.0,
        trades_today=0,
    )

    print("")
    print("3. Risk validation:")
    print(risk_result)

    assert risk_result["allowed"] is True

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    print("")
    print("========================================")
    print(" OFFLINE AI DECISION TEST PASSED")
    print("========================================")
    print("AI schema validation : PASS")
    print("Confidence check     : PASS")
    print("Entry structure      : PASS")
    print("Risk validation      : PASS")
    print("----------------------------------------")
    print("NO REAL GEMINI CALL")
    print("NO ANGEL ONE CALL")
    print("NO REAL ORDER")
    print("NO REAL MONEY")
    print("========================================")
    print("")


if __name__ == "__main__":
    main()
