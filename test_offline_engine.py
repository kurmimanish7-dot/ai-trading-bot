import unittest

from risk_manager import RiskManager
from paper_broker import PaperBroker


class TestOfflinePaperEngine(unittest.TestCase):

    def setUp(self):
        self.broker = PaperBroker()

        self.risk_manager = RiskManager(
            max_daily_loss=2000.0,
            max_trades_per_day=5,
            max_position_quantity=50,
            min_confidence=75.0,
        )

    def test_paper_buy_order(self):
        result = self.broker.place_order(
            symbol="NIFTY26SEPFUT",
            token="35000",
            exchange="NSE",
            transaction_type="BUY",
            quantity=50,
            order_type="MARKET",
            price=250.0,
        )

        self.assertTrue(result)
        self.assertEqual(
            result.get("status"),
            "PAPER_FILLED"
        )

    def test_high_confidence_entry_allowed(self):
        decision = {
            "action": "ENTER_LONG",
            "execution_details": {
                "order_type": "MARKET",
                "suggested_price": 250.0,
                "revised_stop_loss": 245.0,
                "target_1": 260.0,
                "target_2": 270.0,
                "quantity_fraction": 1.0,
            },
            "algorithmic_confidence": {
                "overall_score": 85.0
            },
        }

        position = {
            "has_position": False
        }

        result = self.risk_manager.validate_decision(
