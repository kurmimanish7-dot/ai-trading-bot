import os
import tempfile
import unittest

import main_orchestrator as bot
from state_manager import StateManager


class FakeTelemetry:

    def build_payload(
        self,
        symbol,
        token,
        position
    ):
        return "TEST MARKET TELEMETRY"


class FakeAI:

    def __init__(self, decision):
        self.decision = decision

    def get_decision(self, payload):
        return self.decision


class FakeBroker:

    def __init__(self):
        self.orders = []

    def place_order(
        self,
        symbol,
        token,
        exchange,
        transaction_type,
        quantity,
        order_type="MARKET",
        price=0.0,
    ):

        order = {
            "status": "PAPER",
            "order_id": f"TEST-{len(self.orders) + 1}",
            "symbol": symbol,
            "token": token,
            "exchange": exchange,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "price": price,
        }

        self.orders.append(order)

        return order


class TestOrchestratorSafety(unittest.TestCase):

    def setUp(self):

        self.temp_file = tempfile.NamedTemporaryFile(
            suffix=".db",
            delete=False
        )

        self.temp_file.close()

        bot.state = StateManager(
            self.temp_file.name
        )

        bot.PAPER_TRADING = True

        bot.EXCHANGE = "NSE"
        bot.SYMBOL = "TEST"
        bot.TOKEN = "TESTTOKEN"
        bot.QUANTITY = 50
        bot.MAX_POSITION_QUANTITY = 50

    def tearDown(self):

        try:
            os.remove(
                self.temp_file.name
            )
        except FileNotFoundError:
            pass

    def test_paper_mode_is_enabled(self):

        self.assertTrue(
            bot.PAPER_TRADING
        )

    def test_paper_order_does_not_use_live_api(self):

        fake_broker = FakeBroker()

        bot.broker = fake_broker

        result = bot.execute_paper_order(
            transaction_type="BUY",
            quantity=50,
            price=100.0,
        )

        self.assertEqual(
            result["status"],
            "PAPER"
        )

        self.assertEqual(
            len(fake_broker.orders),
            1
        )

        self.assertEqual(
            fake_broker.orders[0][
                "transaction_type"
            ],
            "BUY"
        )

    def test_valid_long_entry_structure(self):

        decision = {
            "action": "ENTER_LONG",

            "execution_details": {
                "suggested_price": 100.0,
                "revised_stop_loss": 95.0,
                "target_1": 110.0,
                "target_2": 115.0,
                "quantity_fraction": 1.0,
            },

            "algorithmic_confidence": {
                "overall_score": 85
            }
        }

        self.assertTrue(
            bot.validate_entry(
                "ENTER_LONG",
                decision["execution_details"]
            )
        )

    def test_invalid_long_stop_loss(self):

        decision = {
            "suggested_price": 100.0,
            "revised_stop_loss": 105.0,
            "target_1": 110.0,
            "target_2": 115.0,
            "quantity_fraction": 1.0,
        }

        self.assertFalse(
            bot.validate_entry(
                "ENTER_LONG",
                decision
            )
        )

    def test_valid_short_entry_structure(self):

        decision = {
            "suggested_price": 100.0,
            "revised_stop_loss": 105.0,
            "target_1": 90.0,
            "target_2": 85.0,
            "quantity_fraction": 1.0,
        }

        self.assertTrue(
            bot.validate_entry(
                "ENTER_SHORT",
                decision
            )
        )

    def test_invalid_short_stop_loss(self):

        decision = {
            "suggested_price": 100.0,
            "revised_stop_loss": 95.0,
            "target_1": 90.0,
            "target_2": 85.0,
            "quantity_fraction": 1.0,
        }

        self.assertFalse(
            bot.validate_entry(
                "ENTER_SHORT",
                decision
            )
        )

    def test_full_long_trade_lifecycle(self):

        fake_broker = FakeBroker()

        bot.broker = fake_broker

        entry = bot.execute_paper_order(
            transaction_type="BUY",
            quantity=50,
            price=100.0,
        )

        bot.state.open_position(
            symbol="TEST",
            direction="LONG",
            entry_price=100.0,
            qty=50,
            stop_loss=95.0,
            t1=110.0,
            t2=115.0,
            sl_order_id=entry["order_id"],
        )

        position = bot.state.get_position(
            "TEST"
        )

        self.assertTrue(
            position["has_position"]
        )

        exit_order = bot.execute_paper_order(
            transaction_type="SELL",
            quantity=50,
            price=110.0,
        )

        self.assertEqual(
            exit_order["transaction_type"],
            "SELL"
        )

        bot.state.close_position(
            symbol="TEST",
            exit_price=110.0,
            reason="TEST TARGET"
        )

        position = bot.state.get_position(
            "TEST"
        )

        self.assertFalse(
            position["has_position"]
        )

        stats = bot.state.get_daily_stats()

        self.assertEqual(
            stats["daily_pnl"],
            500.0
        )

    def test_long_trade_loss(self):

        fake_broker = FakeBroker()

        bot.broker = fake_broker

        entry = bot.execute_paper_order(
            transaction_type="BUY",
            quantity=50,
            price=100.0,
        )

        bot.state.open_position(
            symbol="TEST",
            direction="LONG",
            entry_price=100.0,
            qty=50,
            stop_loss=95.0,
            t1=110.0,
            t2=115.0,
            sl_order_id=entry["order_id"],
        )

        bot.execute_paper_order(
            transaction_type="SELL",
            quantity=50,
            price=95.0,
        )

        bot.state.close_position(
            symbol="TEST",
            exit_price=95.0,
            reason="TEST STOP LOSS"
        )

        stats = bot.state.get_daily_stats()

        self.assertEqual(
            stats["daily_pnl"],
            -250.0
        )


if __name__ == "__main__":

    unittest.main(
        verbosity=2
    )
