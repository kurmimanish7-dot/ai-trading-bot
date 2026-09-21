import os
import time
import json
import datetime

from google import genai

from telemetry_engine import TelemetryEngine
from state_manager import StateManager


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

ai_client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ============================================================
# AI SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an AI-assisted market analysis engine
for an Indian market paper-trading system.

Your job is to analyse the supplied market telemetry
and produce a structured trading directive.

IMPORTANT:

1. This system is PAPER TRADING ONLY.
2. Do not claim certainty about future prices.
3. Do not invent market data.
4. Use only the supplied telemetry.
5. If data is insufficient, return NO_TRADE.
6. Avoid overtrading.
7. Risk management has priority over trade frequency.

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

Confidence must be between 0 and 100.
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
            "response_mime_type": "application/json"
        }
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
# PAPER ORDER SIMULATION
# ============================================================

def paper_order(
    transaction_type: str,
    quantity: int,
    price: float
):

    print("")
    print("========== PAPER ORDER ==========")
    print(f"Symbol      : {SYMBOL}")
    print(f"Transaction : {transaction_type}")
    print(f"Quantity    : {quantity}")
    print(f"Price       : ₹{price}")
    print("Mode        : PAPER TRADING")
    print("NO REAL ORDER SENT")
    print("=================================")
    print("")


# ============================================================
# MARKET HOURS
# ============================================================

def is_market_open():

    now = datetime.datetime.now().time()

    market_open = datetime.time(9, 15)
    market_close = datetime.time(15, 15)

    return (
        market_open <= now <= market_close
    )


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
    # 1. GET CURRENT POSITION
    # --------------------------------------------------------

    position = state.get_position(SYMBOL)


    # --------------------------------------------------------
    # 2. GET MARKET TELEMETRY
    # --------------------------------------------------------

    payload = telemetry.build_payload(
        SYMBOL,
        TOKEN,
        position
    )


    # --------------------------------------------------------
    # 3. ASK AI
    # --------------------------------------------------------

    decision = call_ai_decision(payload)


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

    execution_details = decision.get(
        "execution_details",
        {}
    )

    rationale = decision.get(
        "rationale",
        ""
    )


    # --------------------------------------------------------
    # 4. PRINT AI DECISION
    # --------------------------------------------------------

    print("")
    print("========================================")
    print(
        f"Time       : {now.strftime('%H:%M:%S')}"
    )
    print(
        f"Symbol     : {SYMBOL}"
    )
    print(
        f"AI Action  : {action}"
    )
    print(
        f"Confidence : {confidence}%"
    )
    print(
        f"Rationale  : {rationale}"
    )
    print("========================================")
    print("")


    # --------------------------------------------------------
    # 5. PAPER ENTRY
    # --------------------------------------------------------

    if (
        action in [
            "ENTER_LONG",
            "ENTER_SHORT"
        ]
        and not position["has_position"]
        and confidence >= 75
    ):

        transaction_type = (
            "BUY"
            if action == "ENTER_LONG"
            else "SELL"
        )

        suggested_price = float(
            execution_details.get(
                "suggested_price",
                0
            )
        )

        paper_order(
            transaction_type,
            QTY,
            suggested_price
        )

        # Save simulated position

        direction = (
            "LONG"
            if transaction_type == "BUY"
            else "SHORT"
        )

        stop_loss = float(
            execution_details.get(
                "revised_stop_loss",
                0
            )
        )

        target_1 = float(
            execution_details.get(
                "target_1",
                0
            )
        )

        target_2 = float(
            execution_details.get(
                "target_2",
                0
            )
        )

        state.open_position(
            symbol=SYMBOL,
            direction=direction,
            entry_price=suggested_price,
            qty=QTY,
            stop_loss=stop_loss,
            t1=target_1,
            t2=target_2,
            sl_order_id="PAPER_SL"
        )

        print(
            "Paper position created."
        )


    # --------------------------------------------------------
    # 6. PAPER TRAILING SL
    # --------------------------------------------------------

    elif (
        action == "TRAIL_SL"
        and position["has_position"]
    ):

        new_sl = float(
            execution_details.get(
                "revised_stop_loss",
                0
            )
        )

        if new_sl > 0:

            state.update_stop_loss(
                SYMBOL,
                new_sl
            )

            print(
                f"Paper SL updated to ₹{new_sl}"
            )


    # --------------------------------------------------------
    # 7. PAPER EXIT
    # --------------------------------------------------------

    elif (
        action == "EXIT_NOW"
        and position["has_position"]
    ):

        exit_transaction = (
            "SELL"
            if position["direction"] == "LONG"
            else "BUY"
        )

        paper_order(
            exit_transaction,
            position["quantity"],
            execution_details.get(
                "suggested_price",
                0
            )
        )

        state.close_position(
            SYMBOL
        )

        print(
            "Paper position closed."
        )


    # --------------------------------------------------------
    # 8. HOLD / NO TRADE
    # --------------------------------------------------------

    elif position["has_position"]:

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
    print("========================================")
    print("")

    while True:

        try:

            run_trading_cycle()

        except Exception as error:

            print(
                f"Trading cycle error: {error}"
            )

        # Wait before next analysis

        time.sleep(300)
