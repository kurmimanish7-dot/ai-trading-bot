import os
import tempfile
import unittest

from paper_broker import PaperBroker
from risk_manager import RiskManager
from State_manager import StateManager


class TestPaperBroker(unittest.TestCase):

    def test_buy_order(self):

        broker = PaperBroker()

        result = broker.place_order(
            symbol="TEST",
            transaction_type="BUY",
            quantity=50,
            price=100.0,
        )

        self.assertEqual(
            result["status"],
            "FILLED"
        )

        self.assertEqual(
            result["quantity"],
            50
        )

        self.assertTrue(
            result["order_id"].startswith("PAPER-")
        )


class TestRiskManager(unittest.TestCase):

    def setUp(self):

        self.risk = RiskManager(
            max_daily_loss=2000,
            max_trades_per_day=5,
            max_position_quantity=50,
            min_confidence=75,
        )

    def valid_decision(self):

        return {
            "action": "ENTER_LONG",

            "execution_details": {
                "quantity_fraction": 1.0
            },

            "algorithmic_confidence": {
                "overall_score": 85
            }
        }

    def test_valid_trade_is_allowed(self):

        decision = self.valid_decision()

        result = self.risk.validate_decision(
            decision=decision,
            position={
                "has_position": False
            },
            daily_pnl=0,
            trades_today=0,
        )

        self.assertTrue(
            result["allowed"]
        )

    def test_low_confidence_is_blocked(self):

        decision = self.valid_decision()

        decision[
            "algorithmic_confidence"
        ]["overall_score"] = 60

        result = self.risk.validate_decision(
            decision=decision,
            position={
                "has_position": False
            },
            daily_pnl=0,
            trades_today=0,
        )

        self.assertFalse(
            result["allowed"]
        )

    def test_daily_loss_is_blocked(self):

        decision = self.valid_decision()

        result = self.risk.validate_decision(
            decision=decision,
            position={
                "has_position": False
            },
            daily_pnl=-2000,
            trades_today=0,
        )

        self.assertFalse(
            result["allowed"]
        )

    def test_trade_limit_is_blocked(self):

        decision = self.valid_decision()

        result = self.risk.validate_decision(
            decision=decision,
            position={
                "has_position": False
            },
            daily_pnl=0,
            trades_today=5,
        )

        self.assertFalse(
            result["allowed"]
        )

    def test_existing_position_blocks_new_entry(self):

        decision = self.valid_decision()

        result = self.risk.validate_decision(
            decision=decision,
            position={
                "has_position": True,
                "direction": "LONG"
            },
            daily_pnl=0,
            trades_today=0,
        )

        self.assertFalse(
            result["allowed"]
        )


class TestStateManager(unittest.TestCase):

    def setUp(self):

        self.temp_file = tempfile.NamedTemporaryFile(
            suffix=".db",
            delete=False
        )

        self.temp_file.close()

        self.state = StateManager(
            self.temp_file.name
        )

    def tearDown(self):

        try:
            os.remove(
                self.temp_file.name
            )
        except FileNotFoundError:
            pass

    def test_open_position(self):

        self.state.open_position(
            symbol="TEST",
            direction="LONG",
            entry_price=100.0,
            qty=50,
            stop_loss=95.0,
            t1=110.0,
            t2=115.0,
            sl_order_id="PAPER-000001",
        )

        position = self.state.get_position(
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

    def test_unrealized_long_pnl(self):

        self.state.open_position(
            symbol="TEST",
            direction="LONG",
            entry_price=100.0,
            qty=50,
            stop_loss=95.0,
            t1=110.0,
            t2=115.0,
            sl_order_id="PAPER-000001",
        )

        pnl = self.state.calculate_unrealized_pnl(
            symbol="TEST",
            current_price=105.0
        )

        self.assertEqual(
            pnl,
            250.0
        )

    def test_unrealized_short_pnl(self):

        self.state.open_position(
            symbol="TEST",
            direction="SHORT",
            entry_price=100.0,
            qty=50,
            stop_loss=105.0,
            t1=90.0,
            t2=85.0,
            sl_order_id="PAPER-000002",
        )

        pnl = self.state.calculate_unrealized_pnl(
            symbol="TEST",
            current_price=95.0
        )

        self.assertEqual(
            pnl,
            250.0
        )

    def test_close_position_records_pnl(self):

        self.state.open_position(
            symbol="TEST",
            direction="LONG",
            entry_price=100.0,
            qty=50,
            stop_loss=95.0,
            t1=110.0,
            t2=115.0,
            sl_order_id="PAPER-000003",
        )

        self.state.close_position(
            symbol="TEST",
            exit_price=110.0,
            reason="TEST EXIT"
        )

        position = self.state.get_position(
            "TEST"
        )

        self.assertFalse(
            position["has_position"]
        )

        stats = self.state.get_daily_stats()

        self.assertEqual(
            stats["trades_today"],
            1
        )

        self.assertEqual(
            stats["daily_pnl"],
            500.0
        )


if __name__ == "__main__":

    unittest.main(
        verbosity=2
    )
