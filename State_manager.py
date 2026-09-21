import sqlite3
from typing import Dict


class StateManager:
    def __init__(self, db_path: str = "trading_state.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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

    def get_position(self, symbol: str) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            row = conn.execute(
                "SELECT * FROM active_position WHERE symbol = ?",
                (symbol,)
            ).fetchone()

            if not row:
                return {
                    "has_position": False,
                    "direction": "NONE",
                    "bars_held": 0
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

    def close_position(self, symbol: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                DELETE FROM active_position
                WHERE symbol = ?
                """,
                (symbol,)
            )
