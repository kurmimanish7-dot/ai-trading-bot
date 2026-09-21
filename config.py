import os

# Angel One SmartAPI
SMARTAPI_API_KEY = os.getenv("SMARTAPI_API_KEY")
SMARTAPI_CLIENT_CODE = os.getenv("SMARTAPI_CLIENT_CODE")
SMARTAPI_PIN = os.getenv("SMARTAPI_PIN")
SMARTAPI_TOTP_SECRET = os.getenv("SMARTAPI_TOTP_SECRET")

# Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Trading configuration
PAPER_TRADING = True

EXCHANGE = "NSE"

# Instrument details will be configured later
SYMBOL = ""
TOKEN = ""

QUANTITY = 0

# Risk controls
MAX_DAILY_LOSS = 0
MAX_TRADES_PER_DAY = 0

# Trading session
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:15"
