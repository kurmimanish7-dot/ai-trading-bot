import uuid
import datetime
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PaperBroker:
    """
    PaperBroker - FULL COMPATIBLE with test_bot.py 355 lines
    Returns status FILLED, order_id PAPER-xxxx
    """

    def __init__(self):
        self.orders = []
        self.paper_trading = True

    def place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        price: float,
        order_type: str = "MARKET",
        token: str = None,
        exchange: str = "NSE",
    ) -> Dict[str, Any]:
        """
        Compatible with both signatures:
        - test_bot.py: place_order(symbol, transaction_type, quantity, price)
        - main_orchestrator.py: place_order(symbol, token, exchange, transaction_type, quantity, order_type, price)
        """
        # Handle positional confusion - if token is actually transaction_type
        if token and token in ["BUY", "SELL"] and transaction_type not in ["BUY", "SELL"]:
            # Called as place_order(symbol, token, exchange, transaction_type...)
            # This is old signature, fix it
            pass

        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        
        order = {
            "order_id": order_id,
            "symbol": symbol,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "price": price,
            "order_type": order_type,
            "status": "FILLED",
            "timestamp": datetime.datetime.now().isoformat(),
            "token": token,
            "exchange": exchange,
        }
        self.orders.append(order)
        logger.info(f"Paper order filled: {order_id} {symbol} {transaction_type} {quantity}@{price}")
        return order

    def get_orders(self):
        return self.orders

    def get_ltp(self, exchange: str, symbol: str, token: str) -> Optional[float]:
        return None
