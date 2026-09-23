import json

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
