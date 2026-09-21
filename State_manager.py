import sqlite3
from typing import Dict, Any


class StateManager:
    """
    Persistent state manager for the paper-trading system.

    Stores:
    - Active position
    - Trade history
    - Realized P&L
    - Daily trade statistics
    """

    def __init__(self, db_path: str = "trading_state.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:

            # Active position
            conn.execute("""
                CREATE TABLE IF NOT EXISTS active_position (
                    symbol TEXT PRIMARY KEY,
                    direction TEXT,
                    entry_price REAL,
                    quantity INTEGER,
                    stop_loss REAL,
                    target_1 REAL,
                    target_2 REAL,
                    sl_order_id TEXT,
                    bars_held INTEGER,
                    entry_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Trade history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    direction TEXT,
                    transaction_type TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    quantity INTEGER,
                    pnl REAL DEFAULT 0.0,
                    reason TEXT,
                    trade_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    # --------------------------------------------------
    # ACTIVE POSITION
    # --------------------------------------------------

    def get_position(self, symbol: str) -> Dict[str, Any]:

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            row = conn.execute(
                """
                SELECT *
                FROM active_position
                WHERE symbol = ?
                """,
                (symbol,)
            ).fetchone()

            if not row:
                return {
                    "has_position": False,
                    "direction": "NONE",
                    "bars_held": 0,
                    "pnl_pct": "0.0%",
                }

            data = dict(row)
            data["has_position"] = True

            return data

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        qty: int,
        stop_loss: float,
        t1: float,
        t2: float,
        sl_order_id: str
    ):

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO active_position
                (
                    symbol,
                    direction,
                    entry_price,
                    quantity,
                    stop_loss,
                    target_1,
                    target_2,
                    sl_order_id,
                    bars_held
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                symbol,
                direction,
                entry_price,
                qty,
                stop_loss,
                t1,
                t2,
                sl_order_id
            ))

    def update_stop_loss(
        self,
        symbol: str,
        new_sl: float
    ):

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE active_position
                SET stop_loss = ?
                WHERE symbol = ?
                """,
                (new_sl, symbol)
            )

    def increment_bars(self, symbol: str):

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE active_position
                SET bars_held = bars_held + 1
                WHERE symbol = ?
                """,
                (symbol,)
            )

    # --------------------------------------------------
    # TRADE LOG
    # --------------------------------------------------

    def record_trade(
        self,
        symbol: str,
        direction: str,
        transaction_type: str,
        entry_price: float,
        exit_price: float,
        quantity: int,
        pnl: float,
        reason: str = ""
    ):

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO trade_log
                (
                    symbol,
                    direction,
                    transaction_type,
                    entry_price,
                    exit_price,
                    quantity,
                    pnl,
                    reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    direction,
                    transaction_type,
                    entry_price,
                    exit_price,
                    quantity,
                    pnl,
                    reason
                )
            )

    def get_daily_stats(self) -> Dict[str, Any]:

        with sqlite3.connect(self.db_path) as conn:

            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS trades_today,
                    COALESCE(SUM(pnl), 0.0) AS daily_pnl
                FROM trade_log
                WHERE DATE(trade_timestamp) = DATE('now', 'localtime')
                """
            ).fetchone()

            return {
                "trades_today": int(row[0]),
                "daily_pnl": float(row[1]),
            }

    # --------------------------------------------------
    # POSITION P&L
    # --------------------------------------------------

    def calculate_unrealized_pnl(
        self,
        symbol: str,
        current_price: float
    ) -> float:

        position = self.get_position(symbol)

        if not position.get("has_position"):
            return 0.0

        entry_price = float(
            position.get("entry_price", 0.0)
        )

        quantity = int(
            position.get("quantity", 0)
        )

        direction = position.get(
            "direction",
            "NONE"
        )

        if direction == "LONG":
            return (current_price - entry_price) * quantity

        if direction == "SHORT":
            return (entry_price - current_price) * quantity

        return 0.0

    # --------------------------------------------------
    # CLOSE POSITION
    # --------------------------------------------------

    def close_position(
        self,
        symbol: str,
        exit_price: float = 0.0,
        reason: str = ""
    ):

        position = self.get_position(symbol)

        if not position.get("has_position"):
            return

        entry_price = float(
            position.get("entry_price", 0.0)
        )

        quantity = int(
            position.get("quantity", 0)
        )

        direction = position.get(
            "direction",
            "NONE"
        )

        if exit_price > 0:

            if direction == "LONG":
                pnl = (
                    exit_price - entry_price
                ) * quantity

            elif direction == "SHORT":
                pnl = (
                    entry_price - exit_price
                ) * quantity

            else:
                pnl = 0.0

            self.record_trade(
                symbol=symbol,
                direction=direction,
                transaction_type="EXIT",
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                pnl=pnl,
                reason=reason
            )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                DELETE FROM active_position
                WHERE symbol = ?
                """,
                (symbol,)
            )
