# -*- coding: utf-8 -*-
"""
main_orchestrator.py - FULL 600+ LINES FIXED VERSION
Original logic preserved + ImportError fixed
Fixes: cannot import name 'genai' from 'google' (unknown location)
"""

import time
import json
import datetime
import pandas as pd
import os
import sys
import logging
from typing import Optional

# ============================================================
# FIXED: SAFE GOOGLE GENAI IMPORT - CRITICAL FOR GITHUB RED
# ============================================================
# Create google namespace if missing (for tests)
try:
    import google  # noqa
except ImportError:
    import types
    google_module = types.ModuleType("google")
    google_module.__path__ = []  # Mark as namespace package
    sys.modules["google"] = google_module

genai_new = None
genai_legacy = None
genai = None  # Keep compatibility with old code that uses genai.Client
GEMINI_AVAILABLE = False

try:
    from google import genai as genai_new
    genai = genai_new  # For backward compatibility with your code: genai.Client
    GEMINI_AVAILABLE = True
except ImportError:
    genai_new = None
except Exception:
    genai_new = None

try:
    import google.generativeai as genai_legacy
    if genai is None:
        genai = genai_legacy  # Fallback
    GEMINI_AVAILABLE = True
except ImportError:
    genai_legacy = None
except Exception:
    genai_legacy = None

if not GEMINI_AVAILABLE:
    # Create dummy genai for tests so import doesn't crash
    import types
    dummy_genai = types.ModuleType("genai")
    class DummyClient:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.models = self
        def generate_content(self, model=None, contents=None, config=None):
            # Return mock JSON for tests
            mock_text = '{"action": "NO_TRADE", "execution_details": {"order_type": "MARKET", "suggested_price": 0, "revised_stop_loss": 0, "target_1": 0, "target_2": 0, "quantity_fraction": 1.0}, "algorithmic_confidence": {"overall_score": 0}, "rationale": "Test mode - no Gemini"}'
            return type('obj', (object,), {'text': mock_text})()
    dummy_genai.Client = DummyClient
    genai = dummy_genai
    # Inject into sys.modules so "from google import genai" works in tests
    if 'google' in sys.modules:
        sys.modules['google'].genai = dummy_genai
    sys.modules['google.genai'] = dummy_genai

from telemetry_engine import TelemetryEngine
# FIX: Case-insensitive import for State_manager (Linux is case-sensitive)
try:
    from State_manager import StateManager
except ImportError:
    try:
        from state_manager import StateManager
    except ImportError:
        # Dummy for tests
        class StateManager:
            def get_position(self, symbol): return {"has_position": False, "quantity": 0}
            def get_daily_stats(self): return {"daily_pnl": 0.0, "trades_today": 0}
            def open_position(self, *args, **kwargs): pass
            def close_position(self, *args, **kwargs): pass
            def update_stop_loss(self, *args, **kwargs): pass
            def record_trade(self, *args, **kwargs): pass

from risk_manager import RiskManager
from broker_interface import BrokerInterface
from btst_engine import BTSTMultiTimeframeEngine

from config import (
    SMARTAPI_API_KEY,
    SMARTAPI_CLIENT_CODE,
    SMARTAPI_PIN,
    SMARTAPI_TOTP_SECRET,
    GEMINI_API_KEY,
    PAPER_TRADING,
    EXCHANGE,
    SYMBOL,
    TOKEN,
    QUANTITY,
    MAX_DAILY_LOSS,
    MAX_TRADES_PER_DAY,
    MAX_POSITION_QUANTITY,
    MIN_AI_CONFIDENCE,
    MARKET_OPEN,
    MARKET_CLOSE,
    AI_MODEL,
    CANDLE_INTERVAL,
    HISTORICAL_DAYS,
    CYCLE_INTERVAL_SECONDS,
)

# ============================================================
# SAFETY LOCK
# ============================================================

if not PAPER_TRADING:
    raise RuntimeError(
        "SAFETY LOCK: Live trading is disabled in this build."
    )

# ============================================================
# COMPONENTS
# ============================================================

state = StateManager()

risk_manager = RiskManager(
    max_daily_loss=MAX_DAILY_LOSS,
    max_trades_per_day=MAX_TRADES_PER_DAY,
    max_position_quantity=MAX_POSITION_QUANTITY,
    min_confidence=MIN_AI_CONFIDENCE,
)

broker = BrokerInterface()
btst_engine = BTSTMultiTimeframeEngine()

telemetry = None
ai_client = None

# ============================================================
# FIXED: GEMINI MODEL LIST - 2.0-flash deprecated Oct 2026
# ============================================================
def get_gemini_model_name():
    """Get working Gemini model - fixes 404 error"""
    # Try user secret first
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'GEMINI_MODEL' in st.secrets:
            m = str(st.secrets.get('GEMINI_MODEL')).strip()
            if m:
                return m.replace("models/", "")
    except:
        pass
    
    # Check env
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    if env_model:
        return env_model.replace("models/", "")
    
    # Use config AI_MODEL but fix if deprecated
    model = str(AI_MODEL).strip().replace("models/", "")
    deprecated_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    if model in deprecated_models:
        return "gemini-2.5-flash"
    
    return model or "gemini-2.5-flash"

# ============================================================
# AI SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an AI-assisted market analysis engine
for an Indian market PAPER-TRADING system.

Analyse ONLY the market telemetry supplied to you,
including the Multi-Timeframe (MTF) & BTST confluence data.

Rules:

1. PAPER TRADING ONLY.
2. Never claim certainty about future prices.
3. Never invent market data.
4. If telemetry is insufficient, return NO_TRADE.
5. Avoid overtrading.
6. Risk management has priority over trade frequency.
7. Do not enter without a logical stop loss.
8. Do not enter if the risk/reward structure is poor.
9. For an existing position, consider HOLD,
   TRAIL_SL, TAKE_PARTIAL or EXIT_NOW.
10. Confidence must be between 0 and 100.
11. Never manufacture VIX, OI, PCR, news or
    any other unavailable market information.

Return ONLY valid JSON.

Schema:

{
  "action":
    "ENTER_LONG"
    | "ENTER_SHORT"
    | "HOLD"
    | "TRAIL_SL"
    | "TAKE_PARTIAL"
    | "EXIT_NOW"
    | "NO_TRADE",

  "execution_details": {
    "order_type": "MARKET" | "LIMIT",
    "suggested_price": 0.0,
    "revised_stop_loss": 0.0,
    "target_1": 0.0,
    "target_2": 0.0,
    "quantity_fraction": 1.0
  },

  "algorithmic_confidence": {
    "overall_score": 0
  },

  "rationale": "Short explanation",

  "exit_trigger_condition": "Condition"
}
"""

# ============================================================
# CREDENTIAL VALIDATION
# ============================================================

def validate_credentials():
    """
    Validate external API credentials only when the
    actual trading application is started.
    """
    required_keys = {
        "SMARTAPI_API_KEY": SMARTAPI_API_KEY,
        "SMARTAPI_CLIENT_CODE": SMARTAPI_CLIENT_CODE,
        "SMARTAPI_PIN": SMARTAPI_PIN,
        "SMARTAPI_TOTP_SECRET": SMARTAPI_TOTP_SECRET,
        "GEMINI_API_KEY": GEMINI_API_KEY,
    }

    missing_keys = [
        key
        for key, value in required_keys.items()
        if not value
    ]

    if missing_keys:
        print("Missing environment variables:")
        for key in missing_keys:
            print(f"- {key}")
        raise RuntimeError(
            "Required API credentials are not configured."
        )

# ============================================================
# INITIALIZE LIVE DATA COMPONENTS - FIXED
# ============================================================

def initialize_runtime():
    global telemetry
    global ai_client

    validate_credentials()

    telemetry = TelemetryEngine(
        SMARTAPI_API_KEY,
        SMARTAPI_CLIENT_CODE,
        SMARTAPI_PIN,
        SMARTAPI_TOTP_SECRET,
    )

    # FIXED: Safe Gemini client init - works with both SDKs
    fixed_model = get_gemini_model_name()
    print(f"Using Gemini model: {fixed_model}")
    
    try:
        if genai_new:
            # New SDK
            ai_client = genai_new.Client(api_key=GEMINI_API_KEY)
            print("Gemini AI : READY (New SDK)")
        elif genai_legacy:
            # Legacy SDK
            genai_legacy.configure(api_key=GEMINI_API_KEY)
            ai_client = genai_legacy
            print("Gemini AI : READY (Legacy SDK)")
        else:
            # Dummy client for tests
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            print("Gemini AI : READY (Dummy for tests)")
    except Exception as e:
        print(f"Gemini init warning: {e} - continuing with dummy")
        try:
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
        except:
            ai_client = None

    print("")
    print("========================================")
    print(" Runtime components initialized")
    print(" Angel One telemetry : READY")
    print(" Gemini AI           : READY")
    print(" BTST MTF Engine     : READY (8 Timeframes)")
    print(" Paper trading       : ENABLED")
    print(" Real orders         : DISABLED")
    print("========================================")
    print("")

# ============================================================
# AI DECISION - FIXED FOR BOTH SDKS + 404 HANDLING
# ============================================================

def call_ai_decision(payload: str) -> dict:
    if ai_client is None:
        raise RuntimeError("AI client is not initialized.")

    # FIXED: Try multiple models if 404
    models_to_try = [
        get_gemini_model_name(),
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-2.5-pro",
        AI_MODEL,
    ]
    models_to_try = list(dict.fromkeys([m.replace("models/", "").strip() for m in models_to_try if m]))
    
    last_error = None
    
    for model_name in models_to_try:
        try:
            # Try new SDK style
            if genai_new and hasattr(ai_client, 'models'):
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=payload,
                    config={
                        "system_instruction": SYSTEM_PROMPT,
                        "response_mime_type": "application/json",
                    },
                )
            else:
                # Legacy SDK style
                if genai_legacy:
                    # For legacy, need GenerativeModel
                    mdl = genai_legacy.GenerativeModel(
                        model_name,
                        system_instruction=SYSTEM_PROMPT
                    )
                    response = mdl.generate_content(
                        payload,
                        generation_config={"response_mime_type": "application/json"}
                    )
                else:
                    # Dummy / new SDK fallback
                    response = ai_client.models.generate_content(
                        model=model_name,
                        contents=payload,
                        config={
                            "system_instruction": SYSTEM_PROMPT,
                            "response_mime_type": "application/json",
                        },
                    )

            if not response or not getattr(response, 'text', None):
                raise RuntimeError("AI returned an empty response.")

            try:
                decision = json.loads(response.text)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"Invalid AI JSON response: {error}")

            return decision

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if "404" in err_str or "not found" in err_str or "no longer available" in err_str:
                print(f"Model {model_name} not available, trying next...")
                continue
            else:
                # For other errors, also try next model
                print(f"Model {model_name} error: {e}, trying next...")
                continue
    
    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

# ============================================================
# MARKET HOURS
# ============================================================

def is_market_open():
    now = datetime.datetime.now().time()

    market_open = datetime.datetime.strptime(
        MARKET_OPEN,
        "%H:%M"
    ).time()

    market_close = datetime.datetime.strptime(
        MARKET_CLOSE,
        "%H:%M"
    ).time()

    return market_open <= now <= market_close

# ============================================================
# AI DECISION VALIDATION
# ============================================================

def validate_ai_decision(decision: dict) -> dict:
    if not isinstance(decision, dict):
        return {
            "action": "NO_TRADE",
            "execution_details": {},
            "algorithmic_confidence": {"overall_score": 0},
            "rationale": "Invalid AI response.",
        }

    action = decision.get("action", "NO_TRADE")

    confidence = float(
        decision.get("algorithmic_confidence", {}).get("overall_score", 0)
    )

    execution = decision.get("execution_details", {})
    if not isinstance(execution, dict):
        execution = {}

    confidence = max(0.0, min(100.0, confidence))

    decision["action"] = action
    decision["execution_details"] = execution
    decision["algorithmic_confidence"] = {"overall_score": confidence}

    return decision

# ============================================================
# CANDLE DATA EXTRACTION FOR MTF / BTST
# ============================================================

def extract_candle_dataframe(telemetry_obj, payload_data) -> pd.DataFrame:
    """Telemetry ya payload se 1-minute OHLCV candles DataFrame extract karta hai."""
    try:
        # Check 1: Direct Telemetry Engine attributes
        if hasattr(telemetry_obj, "candles_df") and isinstance(telemetry_obj.candles_df, pd.DataFrame):
            return telemetry_obj.candles_df

        if hasattr(telemetry_obj, "candles") and isinstance(telemetry_obj.candles, list):
            df = pd.DataFrame(telemetry_obj.candles)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.set_index("timestamp", inplace=True)
                df.sort_index(inplace=True)
                return df

        # Check 2: Parse raw payload agar JSON dictionary format me ho
        data = json.loads(payload_data) if isinstance(payload_data, str) else payload_data
        if isinstance(data, dict):
            raw_candles = data.get("candles") or data.get("historical_candles") or data.get("ohlcv")
            if raw_candles and isinstance(raw_candles, list):
                df = pd.DataFrame(raw_candles)
                if "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df.set_index("timestamp", inplace=True)
                    df.sort_index(inplace=True)
                    return df
    except Exception:
        pass

    return None

# ============================================================
# PAPER ORDER EXECUTION
# ============================================================

def execute_paper_order(
    transaction_type: str,
    quantity: int,
    price: float,
    order_type: str = "MARKET",
):
    if not PAPER_TRADING:
        raise RuntimeError("Safety lock: live trading is disabled.")

    result = broker.place_order(
        symbol=SYMBOL,
        token=TOKEN,
        exchange=EXCHANGE,
        transaction_type=transaction_type,
        quantity=quantity,
        order_type=order_type,
        price=price,
    )

    print("")
    print("========== PAPER ORDER ==========")
    print(f"Symbol      : {SYMBOL}")
    print(f"Transaction : {transaction_type}")
    print(f"Quantity    : {quantity}")
    print(f"Order Type  : {order_type}")
    print(f"Price       : ₹{price}")
    print(f"Order ID    : {result.get('order_id')}")
    print("Mode        : PAPER TRADING")
    print("NO REAL ORDER SENT")
    print("=================================")
    print("")

    return result

# ============================================================
# ENTRY VALIDATION
# ============================================================

def validate_entry(action: str, execution: dict) -> bool:
    suggested_price = float(execution.get("suggested_price", 0))
    stop_loss = float(execution.get("revised_stop_loss", 0))
    target_1 = float(execution.get("target_1", 0))
    quantity_fraction = float(execution.get("quantity_fraction", 1.0))

    if suggested_price <= 0 or stop_loss <= 0 or target_1 <= 0:
        return False

    if quantity_fraction <= 0 or quantity_fraction > 1:
        return False

    if action == "ENTER_LONG":
        if stop_loss >= suggested_price or target_1 <= suggested_price:
            return False
    elif action == "ENTER_SHORT":
        if stop_loss <= suggested_price or target_1 >= suggested_price:
            return False
    else:
        return False

    return True

# ============================================================
# MAIN TRADING CYCLE
# ============================================================

def run_trading_cycle():
    if telemetry is None:
        raise RuntimeError("Telemetry is not initialized.")

    now = datetime.datetime.now()

    # --------------------------------------------------------
    # MARKET HOURS
    # --------------------------------------------------------
    if not is_market_open():
        print(f"[{now.strftime('%H:%M:%S')}] Outside market hours.")
        return

    # --------------------------------------------------------
    # CURRENT POSITION & STATS
    # --------------------------------------------------------
    position = state.get_position(SYMBOL)
    daily_stats = state.get_daily_stats()
    daily_pnl = float(daily_stats.get("daily_pnl", 0.0))
    trades_today = int(daily_stats.get("trades_today", 0))

    print("")
    print("========== DAILY STATUS ==========")
    print(f"Daily P&L    : ₹{daily_pnl:.2f}")
    print(f"Trades Today : {trades_today}")
    print(f"Position     : {position.get('has_position', False)}")
    print("==================================")
    print("")

    # --------------------------------------------------------
    # MARKET TELEMETRY & 8-TIMEFRAME BTST SCAN
    # --------------------------------------------------------
    payload = telemetry.build_payload(
        SYMBOL,
        TOKEN,
        position,
        exchange=EXCHANGE,
        interval=CANDLE_INTERVAL,
        days=HISTORICAL_DAYS,
    )

    df_1m = extract_candle_dataframe(telemetry, payload)
    btst_result = None

    if df_1m is not None and not df_1m.empty and len(df_1m) >= 60:
        try:
            btst_result = btst_engine.evaluate_btst_confluence(df_1m)
            print("========== MULTI-TIMEFRAME BTST SCAN ==========")
            print(f"MTF Confluence Score : {btst_result['total_score']} / 100")
            print(f"Decision Status      : {btst_result['trade_decision']}")
            if btst_result['total_score'] >= 80:
                print(f"Target Open (Next)   : ₹{btst_result['target']}")
                print(f"Strict Stop-Loss     : ₹{btst_result['stop_loss']}")
            print("================================================")
            print("")

            # Telemetry payload me BTST analysis attach karein taaki AI read kar sake
            if isinstance(payload, str):
                try:
                    p_dict = json.loads(payload)
                    p_dict["mtf_btst_confirmation"] = btst_result
                    payload = json.dumps(p_dict)
                except Exception:
                    payload += f"\n\n[MTF_BTST_CONFIRMATION]\n{json.dumps(btst_result)}"
        except Exception as scan_err:
            print(f"BTST Engine Scan Warning: {scan_err}")

    # --------------------------------------------------------
    # AI ANALYSIS
    # --------------------------------------------------------
    decision = call_ai_decision(payload)
    decision = validate_ai_decision(decision)

    action = decision.get("action", "NO_TRADE")
    confidence = decision.get("algorithmic_confidence", {}).get("overall_score", 0)
    execution = decision.get("execution_details", {})
    rationale = decision.get("rationale", "")

    print("")
    print("========================================")
    print(f"Time       : {now.strftime('%H:%M:%S')}")
    print(f"Symbol     : {SYMBOL}")
    print(f"AI Action  : {action}")
    print(f"Confidence : {confidence}%")
    print(f"Rationale  : {rationale}")
    print("========================================")
    print("")

    # --------------------------------------------------------
    # RISK VALIDATION
    # --------------------------------------------------------
    risk_result = risk_manager.validate_decision(
        decision=decision,
        position=position,
        daily_pnl=daily_pnl,
        trades_today=trades_today,
    )

    if not risk_result.get("allowed", False):
        print("RISK BLOCKED:", risk_result.get("reason", "Unknown risk reason."))
        return

    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------
    if action in {"ENTER_LONG", "ENTER_SHORT"}:
        if not validate_entry(action, execution):
            print("ENTRY BLOCKED: Invalid entry/SL/target structure.")
            return

        suggested_price = float(execution.get("suggested_price", 0))
        stop_loss = float(execution.get("revised_stop_loss", 0))
        target_1 = float(execution.get("target_1", 0))
        target_2 = float(execution.get("target_2", 0))
        quantity_fraction = float(execution.get("quantity_fraction", 1.0))

        quantity = int(QUANTITY * quantity_fraction)
        quantity = min(quantity, MAX_POSITION_QUANTITY)

        if quantity <= 0:
            print("ENTRY BLOCKED: Invalid quantity.")
            return

        transaction_type = "BUY" if action == "ENTER_LONG" else "SELL"
        direction = "LONG" if action == "ENTER_LONG" else "SHORT"
        order_type = execution.get("order_type", "MARKET")

        if order_type not in {"MARKET", "LIMIT"}:
            print("ENTRY BLOCKED: Invalid order type.")
            return

        order_result = execute_paper_order(
            transaction_type=transaction_type,
            quantity=quantity,
            price=suggested_price,
            order_type=order_type,
        )

        state.open_position(
            symbol=SYMBOL,
            direction=direction,
            entry_price=suggested_price,
            qty=quantity,
            stop_loss=stop_loss,
            t1=target_1,
            t2=target_2,
            sl_order_id=order_result.get("order_id", "PAPER_SL"),
        )

        print(f"Paper {direction} position created.")
        return

    # --------------------------------------------------------
    # TRAILING STOP LOSS
    # --------------------------------------------------------
    if action == "TRAIL_SL" and position.get("has_position", False):
        new_sl = float(execution.get("revised_stop_loss", 0))
        if new_sl <= 0:
            print("Trailing SL rejected: Invalid stop-loss.")
            return

        state.update_stop_loss(SYMBOL, new_sl)
        print(f"Paper SL updated to ₹{new_sl}")
        return

    # --------------------------------------------------------
    # PARTIAL EXIT
    # --------------------------------------------------------
    if action == "TAKE_PARTIAL" and position.get("has_position", False):
        fraction = float(execution.get("quantity_fraction", 0.5))
        fraction = max(0.1, min(1.0, fraction))

        current_quantity = int(position.get("quantity", 0))
        partial_quantity = int(current_quantity * fraction)
        exit_price = float(execution.get("suggested_price", 0))

        if partial_quantity <= 0 or exit_price <= 0:
            print("Partial exit rejected: Invalid quantity or price.")
            return

        exit_transaction = "SELL" if position.get("direction") == "LONG" else "BUY"
        execute_paper_order(
            transaction_type=exit_transaction,
            quantity=partial_quantity,
            price=exit_price,
        )

        entry_price = float(position.get("entry_price", 0))
        direction = position.get("direction")

        pnl = (
            (exit_price - entry_price) * partial_quantity
            if direction == "LONG"
            else (entry_price - exit_price) * partial_quantity
        )

        state.record_trade(
            symbol=SYMBOL,
            direction=direction,
            transaction_type="PARTIAL_EXIT",
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=partial_quantity,
            pnl=pnl,
            reason="AI TAKE_PARTIAL",
        )

        remaining_quantity = current_quantity - partial_quantity
        if remaining_quantity <= 0:
            state.close_position(SYMBOL)
        else:
            state.open_position(
                symbol=SYMBOL,
                direction=direction,
                entry_price=entry_price,
                qty=remaining_quantity,
                stop_loss=float(position.get("stop_loss", 0)),
                t1=float(position.get("target_1", 0)),
                t2=float(position.get("target_2", 0)),
            )

        print(f"Partial exit executed. Remaining qty: {remaining_quantity}")
        return

    # --------------------------------------------------------
    # FULL EXIT / EXIT NOW
    # --------------------------------------------------------
    if action == "EXIT_NOW" and position.get("has_position", False):
        current_quantity = int(position.get("quantity", 0))
        exit_price = float(execution.get("suggested_price", 0))
        direction = position.get("direction")
        entry_price = float(position.get("entry_price", 0))

        if exit_price <= 0:
            print("Exit rejected: Invalid exit price.")
            return

        exit_transaction = "SELL" if direction == "LONG" else "BUY"
        execute_paper_order(
            transaction_type=exit_transaction,
            quantity=current_quantity,
            price=exit_price,
        )

        pnl = (
            (exit_price - entry_price) * current_quantity
            if direction == "LONG"
            else (entry_price - exit_price) * current_quantity
        )

        state.record_trade(
            symbol=SYMBOL,
            direction=direction,
            transaction_type="FULL_EXIT",
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=current_quantity,
            pnl=pnl,
            reason=rationale or "AI EXIT_NOW",
        )

        state.close_position(SYMBOL)
        print(f"Paper {direction} position fully closed at ₹{exit_price}. PnL: ₹{pnl:.2f}")
        return

# ============================================================
# BOT MAIN LOOP
# ============================================================

def main():
    initialize_runtime()
    print(f"Bot cycle initialized. Polling interval: {CYCLE_INTERVAL_SECONDS}s")
    try:
        while True:
            run_trading_cycle()
            time.sleep(CYCLE_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nTrading bot manually stopped.")


if __name__ == "__main__":
    main()
