import time
import json
import datetime

from google import genai

from telemetry_engine import TelemetryEngine
from State_manager import StateManager
from risk_manager import RiskManager
from broker_interface import BrokerInterface

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

telemetry = None
ai_client = None


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

    Unit tests can import this module without credentials.
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

        print(
            "Missing environment variables:"
        )

        for key in missing_keys:
            print(
                f"- {key}"
            )

        raise RuntimeError(
            "Required API credentials are not configured."
        )


# ============================================================
# INITIALIZE LIVE DATA COMPONENTS
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

    ai_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    print("")
    print("========================================")
    print(" Runtime components initialized")
    print(" Angel One telemetry : READY")
    print(" Gemini AI           : READY")
    print(" Paper trading       : ENABLED")
    print(" Real orders         : DISABLED")
    print("========================================")
    print("")


# ============================================================
# AI DECISION
# ============================================================

def call_ai_decision(
    payload: str
) -> dict:

    if ai_client is None:

        raise RuntimeError(
            "AI client is not initialized."
        )

    response = ai_client.models.generate_content(
        model=AI_MODEL,
        contents=payload,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
        },
    )

    if (
        not response
        or not response.text
    ):

        raise RuntimeError(
            "AI returned an empty response."
        )

    try:

        decision = json.loads(
            response.text
        )

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

    market_open = datetime.datetime.strptime(
        MARKET_OPEN,
        "%H:%M"
    ).time()

    market_close = datetime.datetime.strptime(
        MARKET_CLOSE,
        "%H:%M"
    ).time()

    return (
        market_open
        <= now
        <= market_close
    )


# ============================================================
# AI DECISION VALIDATION
# ============================================================

def validate_ai_decision(
    decision: dict
) -> dict:

    if not isinstance(
        decision,
        dict
    ):

        return {
            "action": "NO_TRADE",
            "execution_details": {},
            "algorithmic_confidence": {
                "overall_score": 0
            },
            "rationale": (
                "Invalid AI response."
            ),
        }

    action = decision.get(
        "action",
        "NO_TRADE"
    )

    confidence = float(
        decision
        .get(
            "algorithmic_confidence",
            {}
        )
        .get(
            "overall_score",
            0
        )
    )

    execution = decision.get(
        "execution_details",
        {}
    )

    if not isinstance(
        execution,
        dict
    ):

        execution = {}

    confidence = max(
        0.0,
        min(
            100.0,
            confidence
        )
    )

    decision["action"] = action

    decision["execution_details"] = execution

    decision["algorithmic_confidence"] = {
        "overall_score": confidence
    }

    return decision


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
    print(
        f"Transaction : "
        f"{transaction_type}"
    )
    print(
        f"Quantity    : "
        f"{quantity}"
    )
    print(
        f"Order Type  : "
        f"{order_type}"
    )
    print(
        f"Price       : "
        f"₹{price}"
    )
    print(
        f"Order ID    : "
        f"{result.get('order_id')}"
    )
    print("Mode        : PAPER TRADING")
    print("NO REAL ORDER SENT")
    print("=================================")
    print("")

    return result


# ============================================================
# ENTRY VALIDATION
# ============================================================

def validate_entry(
    action: str,
    execution: dict
) -> bool:

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

    quantity_fraction = float(
        execution.get(
            "quantity_fraction",
            1.0
        )
    )

    if suggested_price <= 0:
        return False

    if stop_loss <= 0:
        return False

    if target_1 <= 0:
        return False

    if (
        quantity_fraction <= 0
        or quantity_fraction > 1
    ):
        return False

    if action == "ENTER_LONG":

        if stop_loss >= suggested_price:
            return False

        if target_1 <= suggested_price:
            return False

    elif action == "ENTER_SHORT":

        if stop_loss <= suggested_price:
            return False

        if target_1 >= suggested_price:
            return False

    else:

        return False

    return True


# ============================================================
# MAIN TRADING CYCLE
# ============================================================

def run_trading_cycle():

    if telemetry is None:
        raise RuntimeError(
            "Telemetry is not initialized."
        )

    now = datetime.datetime.now()

    # --------------------------------------------------------
    # MARKET HOURS
    # --------------------------------------------------------

    if not is_market_open():

        print(
            f"[{now.strftime('%H:%M:%S')}] "
            "Outside market hours."
        )

        return

    # --------------------------------------------------------
    # CURRENT POSITION
    # --------------------------------------------------------

    position = state.get_position(
        SYMBOL
    )

    # --------------------------------------------------------
    # DAILY STATISTICS
    # --------------------------------------------------------

    daily_stats = state.get_daily_stats()

    daily_pnl = float(
        daily_stats.get(
            "daily_pnl",
            0.0
        )
    )

    trades_today = int(
        daily_stats.get(
            "trades_today",
            0
        )
    )

    print("")
    print("========== DAILY STATUS ==========")
    print(
        f"Daily P&L    : "
        f"₹{daily_pnl:.2f}"
    )
    print(
        f"Trades Today : "
        f"{trades_today}"
    )
    print(
        f"Position     : "
        f"{position.get('has_position', False)}"
    )
    print("==================================")
    print("")

    # --------------------------------------------------------
    # MARKET TELEMETRY
    # --------------------------------------------------------

    payload = telemetry.build_payload(
        SYMBOL,
        TOKEN,
        position,
        exchange=EXCHANGE,
        interval=CANDLE_INTERVAL,
        days=HISTORICAL_DAYS,
    )

    # --------------------------------------------------------
    # AI ANALYSIS
    # --------------------------------------------------------

    decision = call_ai_decision(
        payload
    )

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
    # DISPLAY AI DECISION
    # --------------------------------------------------------

    print("")
    print("========================================")
    print(
        f"Time       : "
        f"{now.strftime('%H:%M:%S')}"
    )
    print(
        f"Symbol     : "
        f"{SYMBOL}"
    )
    print(
        f"AI Action  : "
        f"{action}"
    )
    print(
        f"Confidence : "
        f"{confidence}%"
    )
    print(
        f"Rationale  : "
        f"{rationale}"
    )
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

    if not risk_result.get(
        "allowed",
        False
    ):

        print(
            "RISK BLOCKED:",
            risk_result.get(
                "reason",
                "Unknown risk reason."
            )
        )

        return

    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------

    if action in {
        "ENTER_LONG",
        "ENTER_SHORT"
    }:

        if not validate_entry(
            action,
            execution
        ):

            print(
                "ENTRY BLOCKED: "
                "Invalid entry/SL/target structure."
            )

            return

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
            QUANTITY
            * quantity_fraction
        )

        quantity = min(
            quantity,
            MAX_POSITION_QUANTITY
        )

        if quantity <= 0:

            print(
                "ENTRY BLOCKED: "
                "Invalid quantity."
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

        order_type = execution.get(
            "order_type",
            "MARKET"
        )

        if order_type not in {
            "MARKET",
            "LIMIT"
        }:

            print(
                "ENTRY BLOCKED: "
                "Invalid order type."
            )

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
            sl_order_id=order_result.get(
                "order_id",
                "PAPER_SL"
            ),
        )

        print(
            f"Paper {direction} "
            f"position created."
        )

        return

    # --------------------------------------------------------
    # TRAILING STOP LOSS
    # --------------------------------------------------------

    if (
        action == "TRAIL_SL"
        and position.get(
            "has_position",
            False
        )
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
            f"Paper SL updated "
            f"to ₹{new_sl}"
        )

        return

    # --------------------------------------------------------
    # PARTIAL EXIT
    # --------------------------------------------------------

    if (
        action == "TAKE_PARTIAL"
        and position.get(
            "has_position",
            False
        )
    ):

        fraction = float(
            execution.get(
                "quantity_fraction",
                0.5
            )
        )

        fraction = max(
            0.1,
            min(
                1.0,
                fraction
            )
        )

        current_quantity = int(
            position.get(
                "quantity",
                0
            )
        )

        partial_quantity = int(
            current_quantity
            * fraction
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
            if position.get(
                "direction"
            ) == "LONG"
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
                exit_price
                - entry_price
            ) * partial_quantity

        else:

            pnl = (
                entry_price
                - exit_price
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
            "Partial exit executed."
        )

        return

    # --------------------------------------------------------
    # FULL EXIT
    # --------------------------------------------------------

    if (
        action == "EXIT_NOW"
        and position.get(
            "has_position",
            False
        )
    ):

        exit_price = float(
            execution.get(
                "suggested_price",
                0
            )
        )

        if exit_price <= 0:

            print(
                "Exit rejected: "
                "Invalid exit price."
            )

            return

        exit_transaction = (
            "SELL"
            if position.get(
                "direction"
            ) == "LONG"
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
    # HOLD / NO TRADE
    # --------------------------------------------------------

    if position.get(
        "has_position",
        False
    ):

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

    initialize_runtime()

    while True:

        try:

            run_trading_cycle()

        except Exception as error:

            print(
                f"Trading cycle error: {error}"
            )

        time.sleep(
            CYCLE_INTERVAL_SECONDS
        )
