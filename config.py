
import os
import streamlit as st

def get_secret(name: str) -> str:
    """Unified secrets loader: st.secrets > os.getenv"""
    try:
        if hasattr(st, 'secrets') and name in st.secrets:
            val = st.secrets.get(name)
            if val:
                return str(val).strip()
    except Exception:
        pass
    val = os.getenv(name, "")
    return str(val).strip() if val else ""

# ANGEL ONE SMARTAPI - Unified
SMARTAPI_API_KEY = get_secret("ANGEL_API_KEY") or get_secret("SMARTAPI_API_KEY")
SMARTAPI_CLIENT_CODE = get_secret("ANGEL_CLIENT_CODE") or get_secret("SMARTAPI_CLIENT_CODE")
SMARTAPI_PIN = get_secret("ANGEL_PIN") or get_secret("SMARTAPI_PIN")
SMARTAPI_TOTP_SECRET = get_secret("ANGEL_TOTP_SECRET") or get_secret("SMARTAPI_TOTP_SECRET")

# GEMINI
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")

# SAFETY
PAPER_TRADING = True

# MARKET - FIXED TOKENS (Spot tokens, not historical)
EXCHANGE = "NSE"
SYMBOL = "NIFTY"
TOKEN = "26000"
TOKEN_NIFTY_SPOT = "26000"
TOKEN_BANKNIFTY_SPOT = "26009"
TOKEN_FINNIFTY_SPOT = "26037"
TOKEN_SENSEX_SPOT = "1"

QUANTITY = 50

# RISK
MAX_DAILY_LOSS = 2000.0
MAX_TRADES_PER_DAY = 5
MAX_POSITION_QUANTITY = 50
MIN_AI_CONFIDENCE = 75.0

# MARKET HOURS
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:15"

# AI
AI_MODEL = "gemini-1.5-flash"
CANDLE_INTERVAL = "FIVE_MINUTE"
HISTORICAL_DAYS = 2

# BOT LOOP
CYCLE_INTERVAL_SECONDS = 300

def validate_config():
    missing = []
    if not SMARTAPI_API_KEY: missing.append("ANGEL_API_KEY")
    if not SMARTAPI_CLIENT_CODE: missing.append("ANGEL_CLIENT_CODE")
    if not SMARTAPI_PIN: missing.append("ANGEL_PIN")
    if not SMARTAPI_TOTP_SECRET: missing.append("ANGEL_TOTP_SECRET")
    if missing:
        raise ValueError(f"Missing secrets: {', '.join(missing)}. Add them in Streamlit Secrets")
    return True
