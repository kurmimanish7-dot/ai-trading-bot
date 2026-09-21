import os
import time
import json
import datetime

from google import genai

from telemetry_engine import TelemetryEngine
from state_manager import StateManager
from risk_manager import RiskManager
from broker_interface import BrokerInterface


# ============================================================
# CONFIGURATION
# ============================================================

SMARTAPI_API_KEY = os.getenv("SMARTAPI_API_KEY")
SMARTAPI_CLIENT_CODE = os.getenv("SMARTAPI_CLIENT_CODE")
SMARTAPI_PIN = os.getenv("SMARTAPI_PIN")
SMARTAPI_TOTP_SECRET = os.getenv("SMARTAPI_TOTP_SECRET")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ============================================================
# PAPER TRADING CONFIG
# ============================================================

PAPER_TRADING = True

SYMBOL = "NIFTY26SEPFUT"
TOKEN = "35000"
QTY = 50
EXCHANGE = "NSE"


# ============================================================
# RISK CONFIG
# ============================================================

MAX_DAILY_LOSS = 2000.0
MAX_TRADES_PER_DAY = 5
MAX_POSITION_QUANTITY = 50
MIN_AI_CONFIDENCE = 75.0


# ============================================================
# BASIC VALIDATION
# ============================================================

required_keys = {
    "SMARTAPI_API_KEY": SMARTAPI_API_KEY,
    "SMARTAPI_CLIENT_CODE": SMARTAPI_CLIENT_CODE,
    "SMARTAPI_PIN": SMARTAPI_PIN,
    "SMARTAPI_TOTP_SECRET": SMARTAPI_TOTP_SECRET,
    "GEMINI_API_KEY": GEMINI_API_KEY,
}

missing_keys = [
    key for key, value in required_keys.items()
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
# INITIALIZE COMPONENTS
# ============================================================

telemetry = TelemetryEngine(
    SMARTAPI_API_KEY,
    SMARTAPI_CLIENT_CODE,
    SMARTAPI_PIN,
    SMARTAPI_TOTP_SECRET
)

state = StateManager()

risk_manager = RiskManager(
    max_daily_loss=MAX_DAILY_LOSS,
    max_trades_per_day=MAX_TRADES_PER_DAY,
    max_position_quantity=MAX_POSITION_QUANTITY,
    min_confidence=MIN_AI_CONFIDENCE,
)

broker = BrokerInterface()

ai_client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ============================================================
# AI SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an AI-assisted market analysis engine
for an Indian market PAPER-TRADING system.

Analyse ONLY the market telemetry supplied to you.

Rules:

1. PAPER TRADING ONLY.
2. Never claim certainty about future prices.
3. Never invent market data.
4. If telemetry is insufficient, return NO_TRADE.
5. Avoid overtrading.
6. Risk management has priority over trade frequency.
7. Do not enter a trade without a logical stop loss.
8. Do not enter a trade if the risk/reward structure is poor.
9. For an existing position, consider HOLD, TRAIL_SL,
   TAKE_PARTIAL or EXIT_NOW.
10. Confidence must be between 0 and 100.

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
# AI DECISION
# ============================================================

def call_ai_decision(payload: str) -> dict:

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=payload,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
        },
    )

    if not response or not response.text:
        raise RuntimeError(
            "AI returned an empty response."
        )

    try:
        decision = json.loads(response.text)

    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid AI JSON response: {error}"
        )

    return decision


# ============================================================
# MARKET HOURS
# ============================================================

def is_market_open():

    now = datetime.datetime.now().time()

    market_open = datetime.time(9, 15)
    market_close = datetime.time(15, 15)

    return market_open <= now <= market_close


# ============================================================
# PAPER ORDER
# ============================================================

def execute_paper_order(
    transaction_type: str,
    quantity: int,
    price: float,
    order_type: str = "MARKET",
):

    if not PAPER_TRADING:
        raise RuntimeError(
            "Safety lock: live trading is disabled."
        )

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
# DECISION VALIDATION
# ============================================================

def validate_ai_decision(decision: dict) -> dict:

    if not isinstance(decision, dict):
        return {
            "action": "NO_TRADE",
            "execution_details": {},
            "algorithmic_confidence": {
                "overall_score": 0
            },
            "rationale": "AI response is not a valid object.",
        }

    action = decision.get(
        "action",
        "NO_TRADE"
    )

    confidence = float(
        decision.get(
            "algorithmic_confidence",
            {}
        ).get(
            "overall_score",
            0
        )
    )

    execution = decision.get(
        "execution_details",
        {}
    )

    if not isinstance(execution, dict):
        execution = {}

    confidence = max(
        0.0,
        min(100.0, confidence)
    )

    decision["action"] = action
    decision["execution_details"] = execution
    decision["algorithmic_confidence"] = {
        "overall_score": confidence
    }

    return decision


# ============================================================
# MAIN TRADING CYCLE
# ============================================================

def run_trading_cycle():

    now = datetime.datetime.now()

    if not is_market_open():

        print(
            f"[{now.strftime('%H:%M:%S')}] "
            "Outside market hours."
        )

        return

    # --------------------------------------------------------
    # 1. CURRENT POSITION
    # --------------------------------------------------------

    position = state.get_position(SYMBOL)

    # --------------------------------------------------------
    # 2. DAILY RISK STATISTICS
    # --------------------------------------------------------

    daily_stats = state.get_daily_stats()

    daily_pnl = daily_stats.get(
        "daily_pnl",
        0.0
    )

    trades_today = daily_stats.get(
        "trades_today",
        0
    )

    print("")
    print("========== DAILY STATUS ==========")
    print(f"Daily P&L    : ₹{daily_pnl:.2f}")
    print(f"Trades Today : {trades_today}")
    print(f"Position     : {position.get('has_position')}")
    print("==================================")
    print("")

    # --------------------------------------------------------
    # 3. MARKET TELEMETRY
    # --------------------------------------------------------

    payload = telemetry.build_payload(
        SYMBOL,
        TOKEN,
        position
    )

    # --------------------------------------------------------
    # 4. GEMINI ANALYSIS
    # --------------------------------------------------------

    decision = call_ai_decision(payload)

    decision = validate_ai_decision(
        decision
    )

    action = decision.get(
        "action",
        "NO_TRADE"
    )

    confidence = decision.get(
        "algorithmic_confidence",
        {}
    ).get(
        "overall_score",
        0
    )

    execution = decision.get(
        "execution_details",
        {}
    )

    rationale = decision.get(
        "rationale",
        ""
    )

    # --------------------------------------------------------
    # 5. DISPLAY AI DECISION
    # --------------------------------------------------------

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
    # 6. RISK MANAGER
    # --------------------------------------------------------

    risk_result = risk_manager.validate_decision(
        decision=decision,
        position=position,
        daily_pnl=daily_pnl,
        trades_today=trades_today,
    )

    if not risk_result.get("allowed", False):

        print(
            "RISK BLOCKED:",
            risk_result.get("reason")
        )

        return

    # --------------------------------------------------------
    # 7. ENTRY
    # --------------------------------------------------------

    if action in {
        "ENTER_LONG",
        "ENTER_SHORT"
    }:

        suggested_price = float(
            execution.get(
                "suggested_price",
                0
            )
        )

        stop_loss = float(
            execution.get(
                "revised_stop_loss",
                0
            )
        )

        target_1 = float(
            execution.get(
                "target_1",
                0
            )
        )

        target_2 = float(
            execution.get(
                "target_2",
                0
            )
        )

        quantity_fraction = float(
            execution.get(
                "quantity_fraction",
                1.0
            )
        )

        quantity = int(
            QTY * quantity_fraction
        )

        quantity = min(
            quantity,
            MAX_POSITION_QUANTITY
        )

        if (
            suggested_price <= 0
            or stop_loss <= 0
            or target_1 <= 0
            or quantity <= 0
        ):
            print(
                "ENTRY BLOCKED: "
                "Invalid price, SL, target or quantity."
            )

            return

        transaction_type = (
            "BUY"
            if action == "ENTER_LONG"
            else "SELL"
        )

        direction = (
            "LONG"
            if action == "ENTER_LONG"
            else "SHORT"
        )

        order_result = execute_paper_order(
            transaction_type=transaction_type,
            quantity=quantity,
            price=suggested_price,
            order_type=execution.get(
                "order_type",
                "MARKET"
            ),
        )

        state.open_position(
            symbol=SYMBOL,
            direction=direction,
            entry_price=suggested_price,
            qty=quantity,
            stop_loss=stop_loss,
            t1=target_1,
            t2=target_2,
            sl_order_id=order_result.get(
                "order_id",
                "PAPER_SL"
            ),
        )

        print(
            f"Paper {direction} position created."
        )

        return

    # --------------------------------------------------------
    # 8. TRAILING STOP LOSS
    # --------------------------------------------------------

    if (
        action == "TRAIL_SL"
        and position.get("has_position", False)
    ):

        new_sl = float(
            execution.get(
                "revised_stop_loss",
                0
            )
        )

        if new_sl <= 0:

            print(
                "Trailing SL rejected: "
                "Invalid stop-loss."
            )

            return

        state.update_stop_loss(
            SYMBOL,
            new_sl
        )

        print(
            f"Paper SL updated to ₹{new_sl}"
        )

        return

    # --------------------------------------------------------
    # 9. PARTIAL EXIT
    # --------------------------------------------------------

    if (
        action == "TAKE_PARTIAL"
        and position.get("has_position", False)
    ):

        fraction = float(
            execution.get(
                "quantity_fraction",
                0.5
            )
        )

        fraction = max(
            0.1,
            min(1.0, fraction)
        )

        current_quantity = int(
            position.get(
                "quantity",
                0
            )
        )

        partial_quantity = int(
            current_quantity * fraction
        )

        exit_price = float(
            execution.get(
                "suggested_price",
                0
            )
        )

        if (
            partial_quantity <= 0
            or exit_price <= 0
        ):

            print(
                "Partial exit rejected: "
                "Invalid quantity or price."
            )

            return

        exit_transaction = (
            "SELL"
            if position.get("direction") == "LONG"
            else "BUY"
        )

        execute_paper_order(
            transaction_type=exit_transaction,
            quantity=partial_quantity,
            price=exit_price,
        )

        entry_price = float(
            position.get(
                "entry_price",
                0
            )
        )

        direction = position.get(
            "direction"
        )

        if direction == "LONG":
            pnl = (
                exit_price - entry_price
            ) * partial_quantity
        else:
            pnl = (
                entry_price - exit_price
            ) * partial_quantity

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

        remaining_quantity = (
            current_quantity
            - partial_quantity
        )

        if remaining_quantity <= 0:

            state.close_position(
                SYMBOL
            )

        else:

            # Re-create remaining position.
            state.open_position(
                symbol=SYMBOL,
                direction=direction,
                entry_price=entry_price,
                qty=remaining_quantity,
                stop_loss=float(
                    position.get(
                        "stop_loss",
                        0
                    )
                ),
                t1=float(
                    position.get(
                        "target_1",
                        0
                    )
                ),
                t2=float(
                    position.get(
                        "target_2",
                        0
                    )
                ),
                sl_order_id=position.get(
                    "sl_order_id",
                    "PAPER_SL"
                ),
            )

        print(
            f"Partial exit executed. "
            f"Quantity: {partial_quantity}"
        )

        return

    # --------------------------------------------------------
    # 10. FULL EXIT
    # --------------------------------------------------------

    if (
        action == "EXIT_NOW"
        and position.get("has_position", False)
    ):

        exit_price = float(
            execution.get(
                "suggested_price",
                0
            )
        )

        if exit_price <= 0:

            print(
                "Exit rejected: invalid exit price."
            )

            return

        exit_transaction = (
            "SELL"
            if position.get("direction") == "LONG"
            else "BUY"
        )

        execute_paper_order(
            transaction_type=exit_transaction,
            quantity=int(
                position.get(
                    "quantity",
                    0
                )
            ),
            price=exit_price,
        )

        state.close_position(
            symbol=SYMBOL,
            exit_price=exit_price,
            reason=decision.get(
                "exit_trigger_condition",
                "AI EXIT_NOW"
            ),
        )

        print(
            "Paper position closed."
        )

        return

    # --------------------------------------------------------
    # 11. HOLD / NO TRADE
    # --------------------------------------------------------

    if position.get("has_position", False):

        state.increment_bars(
            SYMBOL
        )

        print(
            "Existing paper position maintained."
        )

    else:

        print(
            "No trade taken."
        )


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":

    print("")
    print("========================================")
    print(" AI TRADING BOT")
    print(" PAPER TRADING MODE")
    print(" REAL ORDERS DISABLED")
    print("========================================")
    print("")

    while True:

        try:

            run_trading_cycle()

        except Exception as error:

            print(
                f"Trading cycle error: {error}"
            )

        time.sleep(300)
