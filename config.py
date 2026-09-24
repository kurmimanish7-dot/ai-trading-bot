import os


# ============================================================
# ANGEL ONE SMARTAPI
# ============================================================

SMARTAPI_API_KEY = os.getenv("SMARTAPI_API_KEY")
SMARTAPI_CLIENT_CODE = os.getenv("SMARTAPI_CLIENT_CODE")
SMARTAPI_PIN = os.getenv("SMARTAPI_PIN")
SMARTAPI_TOTP_SECRET = os.getenv("SMARTAPI_TOTP_SECRET")


# ============================================================
# GOOGLE GEMINI
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ============================================================
# SAFETY MODE
# ============================================================

# IMPORTANT:
# Keep this TRUE during development and paper testing.
# No real Angel One order should be sent.

PAPER_TRADING = True


# ============================================================
# MARKET / INSTRUMENT
# ============================================================

EXCHANGE = "NSE"

SYMBOL = "NIFTY26SEPFUT"

TOKEN = "35000"

QUANTITY = 50


# ============================================================
# RISK CONTROLS
# ============================================================

MAX_DAILY_LOSS = 2000.0

MAX_TRADES_PER_DAY = 5

MAX_POSITION_QUANTITY = 50

MIN_AI_CONFIDENCE = 75.0


# ============================================================
# MARKET HOURS
# ============================================================

MARKET_OPEN = "09:15"

MARKET_CLOSE = "15:15"


# ============================================================
# AI / ANALYSIS
# ============================================================

AI_MODEL = "gemini-3.6-flash"

CANDLE_INTERVAL = "FIVE_MINUTE"

HISTORICAL_DAYS = 2


# ============================================================
# BOT LOOP
# ============================================================

# 300 seconds = 5 minutes

CYCLE_INTERVAL_SECONDS = 300
