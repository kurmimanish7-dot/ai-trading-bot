import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BrokerInterface:
    """
    Broker abstraction layer.
    - Orders: PAPER-TRADING ONLY (simulated).
    - Market Data: LIVE market data via Angel One SmartAPI.
    """

    def __init__(self, smart_api=None):
        self.smart_api = smart_api
        self.paper_trading = True

    # ==========================================
    # LIVE MARKET DATA METHODS
    # ==========================================

    def get_ltp(self, exchange: str, symbol: str, token: str) -> Optional[float]:
        """
        Angel One REST API se fresh live LTP fetch karta hai.
        Exchange: "NSE" ya "NFO"
        Symbol: e.g. "NIFTY", "RELIANCE-EQ"
        Token: e.g. "26000", "2885"
        """
        if not self.smart_api:
            logger.error("SmartAPI instance not provided to BrokerInterface.")
            return None

        try:
            # Angel One live ltpData endpoint
            response = self.smart_api.ltpData(
                exchange=exchange.upper(),
                tradingsymbol=symbol.upper(),
                symboltoken=str(token)
            )

            if response and response.get("status") and "data" in response:
                data = response["data"]
                ltp = float(data.get("ltp", 0.0))
                if ltp > 0:
                    return ltp

            logger.warning(
                "LTP response invalid for %s (%s): %s",
                symbol,
                token,
                response.get("message", "No data")
            )
            return None

        except Exception as e:
            logger.error("Error fetching live LTP for %s: %s", symbol, e)
            return None

    def get_market_data(self, exchange: str, symbol: str, token: str) -> Dict[str, Any]:
        """
        Detailed live quote data (LTP, Open, High, Low, Close) fetch karta hai.
        """
        ltp = self.get_ltp(exchange, symbol, token)
        return {
            "symbol": symbol,
            "token": token,
            "exchange": exchange,
            "ltp": ltp,
            "is_live": ltp is not None
        }

    # ==========================================
    # ORDER EXECUTION (PAPER TRADING ONLY)
    # ==========================================

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
            raise RuntimeError("Live trading is disabled.")

        # Real market price attach karein taaki paper trade live rates par ho
        executed_price = price
        if executed_price == 0.0:
            live_price = self.get_ltp(exchange, symbol, token)
            executed_price = live_price if live_price else price

        return {
            "status": "PAPER",
            "order_id": "PAPER_ORDER",
            "symbol": symbol,
            "token": token,
            "exchange": exchange,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "price": executed_price,
        }

    def modify_order(
        self,
        order_id: str,
        new_trigger_price: float
    ) -> Dict[str, Any]:

        if not self.paper_trading:
            raise RuntimeError("Live trading is disabled.")

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
            raise RuntimeError("Live trading is disabled.")

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
