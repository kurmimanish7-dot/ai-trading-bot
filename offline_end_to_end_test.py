from risk_manager import RiskManager
from paper_broker import PaperBroker


# ============================================================
# OFFLINE END-TO-END PAPER TRADING TEST
# ============================================================

SYMBOL = "NIFTY26SEPFUT"
TOKEN = "35000"
EXCHANGE = "NSE"
QUANTITY = 50


def main():

    print("=" * 60)
    print("OFFLINE END-TO-END PAPER TRADING TEST")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. SIMULATED AI DECISION
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
        }
    }

    print("\n[1] Simulated AI Decision")
    print("Action      :", decision["action"])
    print("Entry Price :", decision["execution_details"]["suggested_price"])
    print("Stop Loss   :", decision["execution_details"]["revised_stop_loss"])
    print("Target 1    :", decision["execution_details"]["target_1"])
    print("Target 2    :", decision["execution_details"]["target_2"])
    print("Confidence  :", decision["algorithmic_confidence"]["overall_score"])


    # --------------------------------------------------------
    # 2. RISK MANAGER
    # --------------------------------------------------------

    risk_manager = RiskManager(
        max_daily_loss=2000.0,
        max_trades
