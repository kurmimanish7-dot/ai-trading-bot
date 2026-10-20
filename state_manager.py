import sqlite3
import os
import datetime
import json
from typing import Dict, Any, Optional

class StateManager:
    """
    StateManager - FULL 355-line test compatible
    Case-insensitive file: State_manager.py (capital S)
    Handles open_position, get_position, close_position, calculate_unrealized_pnl, get_daily_stats
    """

    def __init__(self, db_path: str = "state.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                direction TEXT,
                entry_price REAL,
                quantity INTEGER,
                stop_loss REAL,
                target_1 REAL,
                target_2 REAL,
                sl_order_id TEXT,
                has_position INTEGER DEFAULT 0,
                entry_time TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                direction TEXT,
                transaction_type TEXT,
                entry_price REAL,
                exit_price REAL,
                quantity INTEGER,
                pnl REAL,
                reason TEXT,
                timestamp TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                daily_pnl REAL DEFAULT 0,
                trades_today INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def open_position(self, symbol: str, direction: str, entry_price: float, qty: int, stop_loss: float, t1: float, t2: float, sl_order_id: str = ""):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO positions 
            (symbol, direction, entry_price, quantity, stop_loss, target_1, target_2, sl_order_id, has_position, entry_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (symbol, direction, entry_price, qty, stop_loss, t1, t2, sl_order_id, datetime.datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_position(self, symbol: str) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return {"has_position": False, "symbol": symbol, "quantity": 0}
        
        # row: symbol, direction, entry_price, quantity, stop_loss, target_1, target_2, sl_order_id, has_position, entry_time
        return {
            "has_position": bool(row[8]),
            "symbol": row[0],
            "direction": row[1],
            "entry_price": row[2],
            "quantity": row[3],
            "stop_loss": row[4],
            "target_1": row[5],
            "target_2": row[6],
            "sl_order_id": row[7],
            "entry_time": row[9],
        }

    def calculate_unrealized_pnl(self, symbol: str, current_price: float) -> float:
        pos = self.get_position(symbol)
        if not pos.get("has_position"):
            return 0.0
        
        entry = float(pos.get("entry_price", 0))
        qty = int(pos.get("quantity", 0))
        direction = pos.get("direction", "LONG")
        
        if direction == "LONG":
            return (current_price - entry) * qty
        else:
            return (entry - current_price) * qty

    def close_position(self, symbol: str, exit_price: float = 0, reason: str = ""):
        pos = self.get_position(symbol)
        if not pos.get("has_position"):
            return
        
        entry_price = float(pos.get("entry_price", 0))
        qty = int(pos.get("quantity", 0))
        direction = pos.get("direction", "LONG")
        
        if direction == "LONG":
            pnl = (exit_price - entry_price) * qty
        else:
            pnl = (entry_price - exit_price) * qty
        
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        # Record trade
        cur.execute("""
            INSERT INTO trades (symbol, direction, transaction_type, entry_price, exit_price, quantity, pnl, reason, timestamp)
            VALUES (?, ?, 'FULL_EXIT', ?, ?, ?, ?, ?, ?)
        """, (symbol, direction, entry_price, exit_price, qty, pnl, reason, datetime.datetime.now().isoformat()))
        
        # Update daily stats
        today = datetime.date.today().isoformat()
        cur.execute("SELECT daily_pnl, trades_today FROM daily_stats WHERE date = ?", (today,))
        row = cur.fetchone()
        if row:
            new_pnl = row[0] + pnl
            new_trades = row[1] + 1
            cur.execute("UPDATE daily_stats SET daily_pnl = ?, trades_today = ? WHERE date = ?", (new_pnl, new_trades, today))
        else:
            cur.execute("INSERT INTO daily_stats (date, daily_pnl, trades_today) VALUES (?, ?, 1)", (today, pnl))
        
        # Remove position
        cur.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        conn.commit()
        conn.close()
        return pnl

    def get_daily_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        today = datetime.date.today().isoformat()
        cur.execute("SELECT daily_pnl, trades_today FROM daily_stats WHERE date = ?", (today,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {"daily_pnl": row[0], "trades_today": row[1], "date": today}
        return {"daily_pnl": 0.0, "trades_today": 0, "date": today}

    # Extra methods for compatibility with other code
    def record_trade(self, symbol: str, direction: str, transaction_type: str, entry_price: float, exit_price: float, quantity: int, pnl: float, reason: str = ""):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO trades (symbol, direction, transaction_type, entry_price, exit_price, quantity, pnl, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, direction, transaction_type, entry_price, exit_price, quantity, pnl, reason, datetime.datetime.now().isoformat()))
        
        today = datetime.date.today().isoformat()
        cur.execute("SELECT daily_pnl, trades_today FROM daily_stats WHERE date = ?", (today,))
        row = cur.fetchone()
        if row:
            new_pnl = row[0] + pnl
            new_trades = row[1] + 1
            cur.execute("UPDATE daily_stats SET daily_pnl = ?, trades_today = ? WHERE date = ?", (new_pnl, new_trades, today))
        else:
            cur.execute("INSERT INTO daily_stats (date, daily_pnl, trades_today) VALUES (?, ?, 1)", (today, pnl))
        conn.commit()
        conn.close()

    def update_stop_loss(self, symbol: str, new_sl: float):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("UPDATE positions SET stop_loss = ? WHERE symbol = ?", (new_sl, symbol))
        conn.commit()
        conn.close()
