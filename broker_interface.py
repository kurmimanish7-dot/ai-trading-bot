from typing import Any, Dict


class BrokerInterface:
    """
    Broker abstraction layer.

    This version is intentionally PAPER-TRADING ONLY.
    No real order is sent to Angel One.
    """

    def __init__(self, smart_api=None):
        self.smart_api = smart_api
        self.paper_trading = True

    def place_order(
        self,
        symbol: str,
        token: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0.0,
    ) -> Dict[str, Any]:

        if not self.paper_trading:
            raise RuntimeError(
                "Live trading is disabled."
            )

        return {
            "status": "PAPER",
            "order_id": "PAPER_ORDER",
            "symbol": symbol,
            "token": token,
            "exchange": exchange,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "price": price,
        }

    def modify_order(
        self,
        order_id: str,
        new_trigger_price: float
    ) -> Dict[str, Any]:

        if not self.paper_trading:
            raise RuntimeError(
                "Live trading is disabled."
            )

        return {
            "status": "PAPER",
            "order_id": order_id,
            "new_trigger_price": new_trigger_price,
        }

    def cancel_order(
        self,
        order_id: str
    ) -> Dict[str, Any]:

        if not self.paper_trading:
            raise RuntimeError(
                "Live trading is disabled."
            )

        return {
            "status": "PAPER",
            "order_id": order_id,
            "message": "Paper order cancelled.",
        }

    def get_order_status(
        self,
        order_id: str
    ) -> Dict[str, Any]:

        return {
            "status": "PAPER",
            "order_id": order_id,
            "order_status": "SIMULATED",
        }
