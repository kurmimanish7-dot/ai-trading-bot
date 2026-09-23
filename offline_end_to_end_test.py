from risk_manager import RiskManager
from paper_broker import PaperBroker


def main():

    print("======================================")
    print("OFFLINE END-TO-END PAPER TEST")
    print("======================================")

    # --------------------------------------------------
    # 1. Simulated AI decision
    # --------------------------------------------------

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

    print("\n1. AI decision:")
    print(decision)

    # --------------------------------------------------
    # 2. Risk validation
    # --------------------------------------------------

    risk_manager = RiskManager(
        max_daily_loss=2000.0,
        max_trades_per_day=5,
        max_position_quantity=50,
        min_confidence=75.0,
    )

    position = {
        "has_position": False
    }

    risk_result = risk_manager.validate_decision(
        decision=decision,
        position=position,
        daily_pnl=0.0,
        trades_today=0,
    )

    print("\n2. Risk validation:")
    print(risk_result)

    if not risk_result.get("allowed"):
        raise RuntimeError(
            "Risk validation unexpectedly blocked the trade."
        )

    # --------------------------------------------------
    # 3. Paper BUY
    # --------------------------------------------------

    broker = PaperBroker()

    buy_price = 25000.0
    quantity = 50

    buy_order = broker.place_order(
        symbol="NIFTY26SEPFUT",
        transaction_type="BUY",
        quantity=quantity,
        price=buy_price,
        order_type="MARKET",
    )

    print("\n3. Paper BUY:")
    print(buy_order)

    if buy_order.get("status") != "FILLED":
        raise RuntimeError(
            "Paper BUY was not filled."
        )

    # --------------------------------------------------
    # 4. Simulated position
    # --------------------------------------------------

    position = {
        "has_position": True,
        "direction": "LONG",
        "entry_price": buy_price,
        "quantity": quantity,
    }

    print("\n4. Simulated position:")
    print(position)

    # --------------------------------------------------
    # 5. Paper SELL
    # --------------------------------------------------

    sell_price = 25100.0

    sell_order = broker.place_order(
        symbol="NIFTY26SEPFUT",
        transaction_type="SELL",
        quantity=quantity,
        price=sell_price,
        order_type="MARKET",
    )

    print("\n5. Paper SELL:")
    print(sell_order)

    if sell_order.get("status") != "FILLED":
        raise RuntimeError(
            "Paper SELL was not filled."
        )

    # --------------------------------------------------
    # 6. Calculate P&L
    # --------------------------------------------------

    pnl = (
        sell_price - buy_price
    ) * quantity

    print("\n6. Simulated P&L:")
    print(f"₹{pnl:.2f}")

    expected_pnl = 5000.0

    if pnl != expected_pnl:
        raise RuntimeError(
            f"Unexpected P&L: {pnl}"
        )

    # --------------------------------------------------
    # 7. Final result
    # --------------------------------------------------

    print("\n======================================")
    print("OFFLINE END-TO-END TEST PASSED")
    print("======================================")
    print("AI decision        : PASS")
    print("Risk validation    : PASS")
    print("Paper BUY          : PASS")
    print("Position simulation: PASS")
    print("Paper SELL         : PASS")
    print("P&L calculation    : PASS")
    print("--------------------------------------")
    print("NO GEMINI API USED")
    print("NO ANGEL ONE ORDER USED")
    print("NO REAL MONEY USED")
    print("======================================")


if __name__ == "__main__":
    main()
