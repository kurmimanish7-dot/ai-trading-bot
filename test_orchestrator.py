import os
import tempfile
import unittest
from unittest.mock import patch

import main_orchestrator as bot
from State_manager import StateManager


class FakeTelemetry:

    def build_payload(
        self,
        symbol,
        token,
        position,
        exchange=None,
        interval=None,
        days=None,
    ):
        return "TEST MARKET TELEMETRY"


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


class TestOrchestratorIntegration(unittest.TestCase):

    def setUp(self):

        self.temp_file = tempfile.NamedTemporaryFile(
            suffix=".db",
            delete=False
        )

        self.temp_file.close()

        bot.state = StateManager(
            self.temp_file.name
        )

        bot.risk_manager = bot.RiskManager(
            max_daily_loss=2000.0,
            max_trades_per_day=5,
            max_position_quantity=50,
            min_confidence=75.0,
        )

        bot.broker = FakeBroker()

        bot.telemetry = FakeTelemetry()

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

    def test_long_entry_creates_position(self):

        decision = {
            "action": "ENTER_LONG",
            "execution_details": {
                "order_type": "MARKET",
                "suggested_price": 100.0,
                "revised_stop_loss": 95.0,
                "target_1": 110.0,
                "target_2": 115.0,
                "quantity_fraction": 1.0,
            },
            "algorithmic_confidence": {
                "overall_score": 90
            },
            "rationale": "Test long entry",
        }

        with patch.object(
            bot,
            "call_ai_decision",
            return_value=decision
        ), patch.object(
            bot,
            "is_market_open",
            return_value=True
        ):

            bot.run_trading_cycle()

        position = bot.state.get_position(
            "TEST"
        )

        self.assertTrue(
            position["has_position"]
        )

        self.assertEqual(
            position["direction"],
            "LONG"
        )

        self.assertEqual(
            position["quantity"],
            50
        )

        self.assertEqual(
            len(bot.broker.orders),
            1
        )

        self.assertEqual(
            bot.broker.orders[0]["transaction_type"],
            "BUY"
        )

    def test_short_entry_creates_position(self):

        decision = {
            "action": "ENTER_SHORT",
            "execution_details": {
                "order_type": "MARKET",
                "suggested_price": 100.0,
                "revised_stop_loss": 105.0,
                "target_1": 90.0,
                "target_2": 85.0,
                "quantity_fraction": 1.0,
            },
            "algorithmic_confidence": {
                "overall_score": 90
            },
            "rationale": "Test short entry",
        }

        with patch.object(
            bot,
            "call_ai_decision",
            return_value=decision
        ), patch.object(
            bot,
            "is_market_open",
            return_value=True
        ):

            bot.run_trading_cycle()

        position = bot.state.get_position(
            "TEST"
        )

        self.assertTrue(
            position["has_position"]
        )

        self.assertEqual(
            position["direction"],
            "SHORT"
        )

        self.assertEqual(
            position["quantity"],
            50
        )

        self.assertEqual(
            bot.broker.orders[0]["transaction_type"],
            "SELL"
        )

    def test_existing_position_blocks_new_entry(self):

        bot.state.open_position(
            symbol="TEST",
            direction="LONG",
            entry_price=100.0,
            qty=50,
            stop_loss=95.0,
            t1=110.0,
            t2=115.0,
            sl_order_id="TEST-SL"
        )

        decision = {
            "action": "ENTER_LONG",
            "execution_details": {
                "order_type": "MARKET",
                "suggested_price": 101.0,
                "revised_stop_loss": 96.0,
                "target_1": 111.0,
                "target_2": 116.0,
                "quantity_fraction": 1.0,
            },
            "algorithmic_confidence": {
                "overall_score": 95
            },
        }

        with patch.object(
            bot,
            "call_ai_decision",
            return_value=decision
        ), patch.object(
            bot,
            "is_market_open",
            return_value=True
        ):

            bot.run_trading_cycle()

        self.assertEqual(
            len(bot.broker.orders),
            0
        )

        position = bot.state.get_position(
            "TEST"
        )

        self.assertTrue(
            position["has_position"]
        )

    def test_exit_now_closes_position_and_records_pnl(self):

        bot.state.open_position(
            symbol="TEST",
            direction="LONG",
            entry_price=100.0,
            qty=50,
            stop_loss=95.0,
            t1=110.0,
            t2=115.0,
            sl_order_id="TEST-SL"
        )

        decision = {
            "action": "EXIT_NOW",
            "execution_details": {
                "suggested_price": 110.0,
                "quantity_fraction": 1.0,
            },
            "algorithmic_confidence": {
                "overall_score": 85
            },
            "exit_trigger_condition": "Test target hit",
        }

        with patch.object(
            bot,
            "call_ai_decision",
            return_value=decision
        ), patch.object(
            bot,
            "is_market_open",
            return_value=True
        ):

            bot.run_trading_cycle()

        position = bot.state.get_position(
            "TEST"
        )

        self.assertFalse(
            position["has_position"]
        )

        self.assertEqual(
            len(bot.broker.orders),
            1
        )

        self.assertEqual(
            bot.broker.orders[0]["transaction_type"],
            "SELL"
        )

        stats = bot.state.get_daily_stats()

        self.assertEqual(
            stats["daily_pnl"],
            500.0
        )

    def test_daily_loss_blocks_new_entry(self):

        bot.state.record_trade(
            symbol="TEST",
            direction="LONG",
            transaction_type="EXIT",
            entry_price=100.0,
            exit_price=60.0,
            quantity=50,
            pnl=-2000.0,
            reason="Daily loss test",
        )

        decision = {
            "action": "ENTER_LONG",
            "execution_details": {
                "order_type": "MARKET",
                "suggested_price": 100.0,
                "revised_stop_loss": 95.0,
                "target_1": 110.0,
                "target_2": 115.0,
                "quantity_fraction": 1.0,
            },
            "algorithmic_confidence": {
                "overall_score": 95
            },
        }

        with patch.object(
            bot,
            "call_ai_decision",
            return_value=decision
        ), patch.object(
            bot,
            "is_market_open",
            return_value=True
        ):

            bot.run_trading_cycle()

        self.assertEqual(
            len(bot.broker.orders),
            0
        )

    def test_trailing_stop_updates_position(self):

        bot.state.open_position(
            symbol="TEST",
            direction="LONG",
            entry_price=100.0,
            qty=50,
            stop_loss=95.0,
            t1=110.0,
            t2=115.0,
            sl_order_id="TEST-SL"
        )

        decision = {
            "action": "TRAIL_SL",
            "execution_details": {
                "revised_stop_loss": 103.0,
                "quantity_fraction": 1.0,
            },
            "algorithmic_confidence": {
                "overall_score": 80
            },
        }

        with patch.object(
            bot,
            "call_ai_decision",
            return_value=decision
        ), patch.object(
            bot,
            "is_market_open",
            return_value=True
        ):

            bot.run_trading_cycle()

        position = bot.state.get_position(
            "TEST"
        )

        self.assertTrue(
            position["has_position"]
        )

        self.assertEqual(
            position["stop_loss"],
            103.0
        )

        self.assertEqual(
            len(bot.broker.orders),
            0
        )


if __name__ == "__main__":

    unittest.main(
        verbosity=2
    )
