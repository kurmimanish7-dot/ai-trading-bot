import datetime
from typing import Dict, Any


class PaperBroker:
    """
    Simple paper-trading broker.

    No real Angel One order is sent.
    """

    def __init__(self):
        self.orders = {}
        self.order_counter = 0
        self.positions = {}

    def _new_order_id(self) -> str:
        self.order_counter += 1
        return f"PAPER-{self.order_counter:06d}"

    def place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        price: float,
        order_type: str = "MARKET"
    ) -> Dict[str, Any]:

        order_id = self._new_order_id()

        order = {
            "order_id": order_id,
            "symbol": symbol,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "price": price,
            "order_type": order_type,
            "status": "FILLED",
            "timestamp": datetime.datetime.now().isoformat()
        }

        self.orders[order_id] = order

        return order

    def get_order_status(
        self,
        order_id: str
    ) -> Dict[str, Any]:

        return self.orders.get(
            order_id,
            {
                "order_id": order_id,
                "status": "NOT_FOUND"
            }
        )

    def cancel_order(
        self,
        order_id: str
    ) -> Dict[str, Any]:

        if order_id not in self.orders:
            return {
                "order_id": order_id,
                "status": "NOT_FOUND"
            }

        self.orders[order_id]["status"] = "C
