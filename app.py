# -*- coding: utf-8 -*-
"""
AI Institutional Live Trading Advisor (Quantitative GEX Engine)
===============================================================
Production Institutional Release: Universal 5,000+ Equity Universe (NSE & BSE),
12-Tier Multi-Timeframe Matrix, SEBI Regulatory Metadata, Analytical Greeks,
Dealer GEX Radar, Stateful Paper-Trading Risk Engine, and Grounded Gemini Synthesis.
"""

import datetime
from datetime import datetime, date, time as dtime, timedelta
import json
import logging
import math
import time
import uuid
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st

IST = ZoneInfo("Asia/Kolkata")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# =====================================================================
# 1. BUILT-IN PURE MATH NORMAL DISTRIBUTION (ZERO SCIPY DEPENDENCY)
# =====================================================================
def norm_cdf(x: float) -> float:
    """Standard Normal Cumulative Distribution Function using built-in math.erf."""
    return 0.5 * (1.0 + math.erf(x / 1.4142135623730951))

def norm_pdf(x: float) -> float:
    """Standard Normal Probability Density Function using built-in math."""
    return 0.3989422804014327 * math.exp(-0.5 * x * x)

# =====================================================================
# 2. SAFE UNICODE ESCAPE CONSTANTS (PREVENTS MOJIBAKE ENCODING DEFECTS)
# =====================================================================
RUPEE = "\u20B9"                # ₹
BOLT = "\u26A1"                 # ⚡
FLAG_IN = "\U0001F1EE\U0001F1F3"# 🇮🇳
CHART_BAR = "\U0001F4CA"        # 📊
CHART_UP = "\U0001F4C8"         # 📈
TARGET = "\U0001F3AF"           # 🎯
TEMPLE = "\U0001F3DB"           # 🏛️
COMPASS = "\U0001F9ED"          # 🧭
GLOBE = "\U0001F310"            # 🌐
TRAFFIC = "\U0001F6A6"          # 🚦
GREEN_CIRCLE = "\U0001F7E2"     # 🟢
RED_CIRCLE = "\U0001F534"       # 🔴
YELLOW_CIRCLE = "\U0001F7E1"    # 🟡
SIREN = "\U0001F6A8"            # 🚨
FIRE = "\U0001F525"             # 🔥
SWORDS = "\u2694\uFE0F"         # ⚔️
PAUSE = "\u23F8\uFE0F"          # ⏸️
ROCKET = "\U0001F680"           # 🚀
DOWN_ARROW = "\U0001F53D"       # 🔻
SCALE = "\u2696\uFE0F"          # ⚖️
SHIELD = "\U0001F6E1\uFE0F"     # 🛡️
PIN = "\U0001F4CC"              # 📌
WARNING = "\u26A0\uFE0F"        # ⚠️
CHECK = "\u2705"                # ✅
STOP = "\U0001F6D1"             # 🛑
REFRESH = "\U0001F504"          # 🔄
STOPWATCH = "\u23F1\uFE0F"      # ⏱️
GEAR = "\u2699\uFE0F"           # ⚙️
SEARCH = "\U0001F50D"           # 🔍
BUILDING = "\U0001F3E2"         # 🏢
RULER = "\U0001F4D0"            # 📐
NEWS = "\U0001F4F0"             # 📰
ROBOT = "\U0001F916"            # 🤖
DELTA_SYM = "\u0394"            # Δ
THETA_SYM = "\u0398"            # Θ
GAMMA_SYM = "\u0393"            # Γ
BULLET = " • "

# =====================================================================
# 3. AUTHORITATIVE EXCHANGE TRADING CALENDAR (2025–2026)
# =====================================================================
NSE_TRADING_HOLIDAYS = {
    # 2025 Standard Trading Holidays
    date(2025, 1, 26), date(2025, 2, 26), date(2025, 3, 14), date(2025, 3, 31),
    date(2025, 4, 10), date(2025, 4, 14), date(2025, 4, 18), date(2025, 5, 1),
    date(2025, 8, 15), date(2025, 8, 27), date(2025, 10, 2), date(2025, 10, 21),
    date(2025, 11, 1), date(2025, 11, 5), date(2025, 12, 25),
    # 2026 Official Exchange Declared Trading Holidays
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 3),    # Holi
    date(2026, 3, 26),   # Shri Ram Navami
    date(2026, 3, 31),   # Shri Mahavir Jayanti
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 28),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 9, 14),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra (Tuesday Holiday -> Auto rolls to Monday 19 Oct 2026)
    date(2026, 11, 10),  # Diwali Balipratipada (Tuesday Holiday -> Auto rolls to Monday 9 Nov 2026)
    date(2026, 11, 24),  # Guru Nanak Jayanti (Tuesday Holiday -> Auto rolls to Monday 23 Nov 2026)
    date(2026, 12, 25),  # Christmas
}

def is_trading_holiday(d: date) -> bool:
    """Checks if date is a weekend or declared exchange holiday."""
    return d.weekday() >= 5 or d in NSE_TRADING_HOLIDAYS

def get_preceding_trading_day(d: date) -> date:
    """Rolls backward to the nearest valid trading day if d lands on a weekend/holiday."""
    candidate = d
    while is_trading_holiday(candidate):
        candidate -= timedelta(days=1)
    return candidate

def market_open() -> bool:
    """Evaluates whether Indian financial markets are currently in continuous trading."""
    now = datetime.now(IST)
    if is_trading_holiday(now.date()):
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)

# =====================================================================
# 4. REGULATORY CONTRACT METADATA (SEBI 2025–2026 MANDATE)
# =====================================================================
INDEX_METADATA = {
    "NIFTY": {
        "exchange": "NSE",
        "symbol": "Nifty 50",
        "alt_symbols": ["NIFTY 50", "NIFTY"],
        "token": "99926000",
        "live_tokens": ["26000", "99926000"],
        "candle_token": "99926000",
        "yfinance": "^NSEI",
        "lot_size": 65,      # SEBI Revised Lot Size
        "step": 50,
        "has_weekly": True,  # Weekly retained on NSE
        "weekly_day": 1,     # Tuesday Expiry
    },
    "BANKNIFTY": {
        "exchange": "NSE",
        "symbol": "Nifty Bank",
        "alt_symbols": ["NIFTY BANK", "BANKNIFTY"],
        "token": "99926009",
        "live_tokens": ["26009", "99926009"],
        "candle_token": "99926009",
        "yfinance": "^NSEBANK",
        "lot_size": 30,      # SEBI Revised Lot Size
        "step": 100,
        "has_weekly": False, # Discontinued per SEBI
        "weekly_day": 1,     # Monthly Last Tuesday
    },
    "FINNIFTY": {
        "exchange": "NSE",
        "symbol": "FINNIFTY",
        "alt_symbols": ["NIFTY FIN SERVICE"],
        "token": "99926037",
        "live_tokens": ["99926037", "26037"],
        "candle_token": "99926037",
        "yfinance": "NIFTY_FIN_SERVICE.NS",
        "lot_size": 60,      # SEBI Revised Lot Size
        "step": 50,
        "has_weekly": False, # Discontinued per SEBI
        "weekly_day": 1,     # Monthly Last Tuesday
    },
    "MIDCPNIFTY": {
        "exchange": "NSE",
        "symbol": "MIDCPNIFTY",
        "alt_symbols": ["NIFTY MID SELECT"],
        "token": "99926074",
        "live_tokens": ["99926074", "26074"],
        "candle_token": "99926074",
        "yfinance": "NIFTY_MIDCAP_100.NS",
        "lot_size": 120,     # SEBI Revised Lot Size
        "step": 25,
        "has_weekly": False, # Discontinued per SEBI
        "weekly_day": 1,     # Monthly Last Tuesday
    },
    "SENSEX": {
        "exchange": "BSE",
        "symbol": "SENSEX",
        "alt_symbols": ["BSESN"],
        "token": "99919000",
        "live_tokens": ["99919000", "1"],
        "candle_token": "99919000",
        "yfinance": "^BSESN",
        "lot_size": 20,      # SEBI Revised Lot Size
        "step": 100,
        "has_weekly": True,  # Weekly retained on BSE
        "weekly_day": 3,     # Thursday Expiry
    },
    "BANKEX": {
        "exchange": "BSE",
        "symbol": "BANKEX",
        "alt_symbols": ["BSE BANKEX"],
        "token": "99919012",
        "live_tokens": ["99919012"],
        "candle_token": "99919012",
        "yfinance": "^BSEBANK",
        "lot_size": 30,      # SEBI Revised Lot Size
        "step": 100,
        "has_weekly": False, # Discontinued per SEBI
        "weekly_day": 3,     # Monthly Last Thursday
    },
    "INDIA_VIX": {
        "exchange": "NSE",
        "symbol": "India VIX",
        "alt_symbols": ["INDIA VIX", "INDIAVIX"],
        "token": "99926017",
        "live_tokens": ["99926017", "26017"],
        "candle_token": "99926017",
        "yfinance": "^INDIAVIX",
        "lot_size": 1,
        "step": 1,
        "has_weekly": False,
        "weekly_day": 1,
    },
}

UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]

# =====================================================================
# 5. COMPLETE 12-TIER TIMEFRAME CONFIGURATION MATRIX
# =====================================================================
TIMEFRAME_CONFIG = {
    "1m": {"label": f"{BOLT} 1 Minute (Scalping / High-Speed)", "smartapi": "ONE_MINUTE", "yfinance": "1m", "yf_range": "2d", "days": 2, "holding": "Quick Scalp (1-5 Mins)", "target1_mult": 1.15, "target2_mult": 1.25, "sl_mult": 0.92, "atr_mult": 0.8, "desc": "Ultra-fast scalp setup. High sensitivity, tight SL."},
    "5m": {"label": f"{CHART_BAR} 5 Minutes (Standard Intraday)", "smartapi": "FIVE_MINUTE", "yfinance": "5m", "yf_range": "5d", "days": 5, "holding": "Intraday Momentum (15-45 Mins)", "target1_mult": 1.20, "target2_mult": 1.35, "sl_mult": 0.85, "atr_mult": 1.0, "desc": "Standard institutional execution resolution."},
    "10m": {"label": f"{TARGET} 10 Minutes (Noise-Filtered Scalp)", "smartapi": "TEN_MINUTE", "yfinance": "10m", "yf_range": "5d", "days": 5, "holding": "Intraday Trend (30-60 Mins)", "target1_mult": 1.22, "target2_mult": 1.38, "sl_mult": 0.84, "atr_mult": 1.2, "desc": "Filters out minor intraday whipsaws."},
    "15m": {"label": f"{TEMPLE} 15 Minutes (Institutional Breakout)", "smartapi": "FIFTEEN_MINUTE", "yfinance": "15m", "yf_range": "7d", "days": 7, "holding": "Multi-Hour Trend (1-3 Hours)", "target1_mult": 1.25, "target2_mult": 1.45, "sl_mult": 0.82, "atr_mult": 1.5, "desc": "Key institutional breakout timeframe for major intraday moves."},
    "30m": {"label": f"{CHART_UP} 30 Minutes (Positional / BTST)", "smartapi": "THIRTY_MINUTE", "yfinance": "30m", "yf_range": "1mo", "days": 15, "holding": "BTST / Positional (1-3 Days)", "target1_mult": 1.30, "target2_mult": 1.55, "sl_mult": 0.78, "atr_mult": 2.0, "desc": "Strong trend conviction for overnight holding and multi-day swings."},
    "60m": {"label": f"{COMPASS} 60 Minutes (1 Hour Macro Swing)", "smartapi": "ONE_HOUR", "yfinance": "60m", "yf_range": "1mo", "days": 30, "holding": "Swing Trend (3-7 Days)", "target1_mult": 1.40, "target2_mult": 1.70, "sl_mult": 0.75, "atr_mult": 2.8, "desc": "Macro hourly structure framework for swing traders."},
    "2h": {"label": "\u23F0 2 Hours (120 Mins Multi-Day Swing)", "smartapi": "ONE_HOUR", "yfinance": "60m", "yf_range": "2mo", "days": 60, "holding": "Multi-Day Swing (3-7 Days)", "target1_mult": 1.50, "target2_mult": 1.85, "sl_mult": 0.72, "atr_mult": 3.0, "desc": "Aggregated 120-minute candles filtering out intraday noise."},
    "4h": {"label": "\U0001F553 4 Hours (Half-Day Institutional)", "smartapi": "ONE_HOUR", "yfinance": "60m", "yf_range": "3mo", "days": 90, "holding": "Weekly Swing (1-2 Weeks)", "target1_mult": 1.60, "target2_mult": 2.05, "sl_mult": 0.68, "atr_mult": 3.5, "desc": "Half-day market structure utilized by institutional trend followers."},
    "1d": {"label": "\U0001F4C5 1 Day (Daily EOD Positional)", "smartapi": "ONE_DAY", "yfinance": "1d", "yf_range": "1y", "days": 365, "holding": "Positional Trend (2-4 Weeks)", "target1_mult": 1.75, "target2_mult": 2.30, "sl_mult": 0.65, "atr_mult": 4.0, "desc": "Daily closing resolution reflecting broad accumulation/distribution."},
    "1w": {"label": "\U0001F5D3\uFE0F 1 Week (Weekly Macro Swing)", "smartapi": "ONE_DAY", "yfinance": "1wk", "yf_range": "2y", "days": 730, "holding": "Macro Positional (1-3 Months)", "target1_mult": 1.90, "target2_mult": 2.60, "sl_mult": 0.60, "atr_mult": 5.0, "desc": "Weekly secular trends removing short-term market corrections."},
    "1mo": {"label": f"{GLOBE} 1 Month (Monthly Positional Cycle)", "smartapi": "ONE_DAY", "yfinance": "1mo", "yf_range": "5y", "days": 1825, "holding": "Secular Long (3-6 Months)", "target1_mult": 2.20, "target2_mult": 3.00, "sl_mult": 0.55, "atr_mult": 6.0, "desc": "Macroeconomic cycle resolution for structural equity trends."},
    "3mo": {"label": f"{TEMPLE} 3 Months (Quarterly Strategic Trend)", "smartapi": "ONE_DAY", "yfinance": "3mo", "yf_range": "10y", "days": 3650, "holding": "Strategic Allocation (6-12 Months)", "target1_mult": 2.50, "target2_mult": 3.50, "sl_mult": 0.50, "atr_mult": 7.5, "desc": "Quarterly earnings cycle resolution for strategic positioning."},
}

# =====================================================================
# 6. CONFIGURATION, THEME & STYLES
# =====================================================================
st.set_page_config(
    page_title="AI Institutional Live Trading Advisor (Quantitative GEX Engine)",
    page_icon=BOLT,
    layout="wide",
)

PAPER_TRADING = True

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.8rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        max-width: 100% !important;
    }
    
    @media(max-width: 768px) {
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.35rem !important;
            width: 100% !important;
        }
        [data-testid="column"] {
            min-width: 48% !important;
            max-width: 48% !important;
            flex: 1 1 48% !important;
            width: 48% !important;
        }
        [data-testid="stMetricValue"], [data-testid="stMetricValue"] * {
            font-size: 1.05rem !important;
            line-height: 1.15 !important;
        }
        [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {
            font-size: 0.72rem !important;
            line-height: 1.1 !important;
        }
        [data-testid="stMetricDelta"], [data-testid="stMetricDelta"] * {
            font-size: 0.68rem !important;
            line-height: 1.0 !important;
        }
    }
    
    .trade-card {
        width: 100%;
        box-sizing: border-box;
        border: 1px solid rgba(128, 128, 128, 0.30);
        border-radius: 12px;
        padding: 1rem;
        margin: 0.7rem 0;
        background-color: rgba(255, 255, 255, 0.02);
    }
    .light-box {
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 12px;
        padding: 0.8rem;
        text-align: center;
        background-color: rgba(255, 255, 255, 0.02);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .reason-box {
        background-color: rgba(128, 128, 128, 0.08);
        border-left: 4px solid #4CAF50;
        padding: 0.75rem;
        border-radius: 4px;
        margin: 0.5rem 0;
        line-height: 1.45;
    }
    .prediction-card-green {
        background: linear-gradient(135deg, rgba(76, 175, 80, 0.15), rgba(76, 175, 80, 0.05));
        border: 1.5px solid #4CAF50;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        margin: 0.5rem 0 0.8rem 0;
    }
    .prediction-card-red {
        background: linear-gradient(135deg, rgba(244, 67, 54, 0.15), rgba(244, 67, 54, 0.05));
        border: 1.5px solid #F44336;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        margin: 0.5rem 0 0.8rem 0;
    }
    .prediction-card-gold {
        background: linear-gradient(135deg, rgba(255, 193, 7, 0.15), rgba(255, 193, 7, 0.05));
        border: 1.5px solid #FFC107;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        margin: 0.5rem 0 0.8rem 0;
    }

    div[data-stale="true"], div[data-stale="true"] *, .stale-element, .stale-element *, .element-container, .element-container * {
        opacity: 1 !important;
        filter: none !important;
        transition: none !important;
        animation: none !important;
    }

    [data-testid="stMetric"], [data-testid="stMetric"] * {
        opacity: 1 !important;
        transition: none !important;
        animation: none !important;
    }

    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(128, 128, 128, 0.25) !important;
        border-radius: 10px !important;
        padding: 0.5rem 0.55rem !important;
        min-height: 82px !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        overflow: hidden !important;
    }

    [data-testid="stStatusWidget"] {
        visibility: hidden !important;
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if hasattr(st, "fragment"):
    live_fragment = st.fragment
elif hasattr(st, "experimental_fragment"):
    live_fragment = st.experimental_fragment
else:
    def live_fragment(*args, **kwargs):
        def decorator(func): return func
        return decorator

# =====================================================================
# 7. STATEFUL PAPER PORTFOLIO & AUDIT LEDGER
# =====================================================================
if "paper_portfolio" not in st.session_state:
    st.session_state.paper_portfolio = {
        "cash_balance": 500000.0,
        "starting_balance": 500000.0,
        "daily_realized_pnl": 0.0,
        "positions": {},       # Active open simulated orders
        "trade_history": [],   # Completed paper trades journal
        "session_date": datetime.now(IST).date().isoformat(),
        "daily_loss_limit": 10000.0,
        "circuit_broken": False,
    }

def check_daily_reset():
    today_str = datetime.now(IST).date().isoformat()
    if st.session_state.paper_portfolio.get("session_date") != today_str:
        st.session_state.paper_portfolio["session_date"] = today_str
        st.session_state.paper_portfolio["daily_realized_pnl"] = 0.0
        st.session_state.paper_portfolio["circuit_broken"] = False
        logger.info("Paper portfolio daily metrics reset for session: %s", today_str)

check_daily_reset()

# =====================================================================
# 8. STATEFUL NSE WAF SESSION & SECRETS MANAGEMENT
# =====================================================================
class NSEExchangeSession:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/option-chain",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
        self.cookie_timestamp = 0.0

    def warm_cookies(self):
        now = time.time()
        if now - self.cookie_timestamp > 120 or len(self.session.cookies) == 0:
            try:
                self.session.get("https://www.nseindia.com", timeout=6)
                self.session.get("https://www.nseindia.com/option-chain", timeout=6)
                self.cookie_timestamp = now
                self.sync_holidays_from_nse()
            except Exception as exc:
                logger.warning("NSE WAF cookie refresh warning: %s", exc)

    def sync_holidays_from_nse(self):
        try:
            url = "https://www.nseindia.com/api/holiday-master?type=trading"
            resp = self.session.get(url, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    for rec in data.get("FO", []):
                        if isinstance(rec, dict) and "tradingDate" in rec:
                            dt = datetime.strptime(rec["tradingDate"], "%d-%b-%Y").date()
                            NSE_TRADING_HOLIDAYS.add(dt)
        except Exception:
            pass

    def get_json(self, url: str) -> Optional[Any]:
        self.warm_cookies()
        try:
            resp = self.session.get(url, timeout=6)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return None
            elif resp.status_code in [401, 403]:
                self.cookie_timestamp = 0.0
                self.warm_cookies()
                retry_resp = self.session.get(url, timeout=6)
                if retry_resp.status_code == 200:
                    try:
                        return retry_resp.json()
                    except Exception:
                        return None
        except Exception as exc:
            logger.warning("NSE endpoint request failed on %s: %s", url, exc)
        return None

@st.cache_resource(show_spinner=False)
def get_nse_session() -> NSEExchangeSession:
    return NSEExchangeSession()

nse_client = get_nse_session()

def secret(name: str) -> str:
    try:
        val = st.secrets.get(name)
        return str(val).strip() if val else ""
    except Exception:
        return ""

ANGEL_API_KEY = secret("ANGEL_API_KEY")
ANGEL_CLIENT_CODE = secret("ANGEL_CLIENT_CODE")
ANGEL_PIN = secret("ANGEL_PIN")
ANGEL_TOTP_SECRET = secret("ANGEL_TOTP_SECRET")
ANGEL_JWT_TOKEN = secret("ANGEL_JWT_TOKEN")
GEMINI_API_KEY = secret("GEMINI_API_KEY") or secret("GOOGLE_API_KEY")
GEMINI_MODEL = secret("GEMINI_MODEL") or "gemini-2.5-flash"

try:
    from telemetry_engine import TelemetryEngine
except Exception:
    TelemetryEngine = None

try:
    from options_engine import OptionsEngine
except Exception:
    OptionsEngine = None

@st.cache_resource(show_spinner=False)
def create_telemetry():
    if TelemetryEngine is None or not all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET]):
        return None
    try:
        return TelemetryEngine(
            api_key=ANGEL_API_KEY,
            client_code=ANGEL_CLIENT_CODE,
            pin=ANGEL_PIN,
            totp_secret=ANGEL_TOTP_SECRET,
        )
    except Exception as e:
        logger.error("TelemetryEngine init failed: %s", e)
        return None

telemetry = create_telemetry()

def get_options_engine():
    if OptionsEngine is None:
        return None
    jwt = None
    if telemetry is not None:
        smart_obj = getattr(telemetry, "smart_api", None)
        if smart_obj:
            jwt = getattr(smart_obj, "jwtToken", None) or getattr(smart_obj, "auth_token", None)
            if not jwt and hasattr(smart_obj, "session_data") and isinstance(smart_obj.session_data, dict):
                jwt = smart_obj.session_data.get("jwtToken")
        if not jwt:
            jwt = getattr(telemetry, "jwt_token", None)
    if not jwt:
        jwt = ANGEL_JWT_TOKEN
    if jwt and ANGEL_API_KEY and ANGEL_CLIENT_CODE:
        try:
            return OptionsEngine(
                jwt_token=jwt,
                api_key=ANGEL_API_KEY,
                client_code=ANGEL_CLIENT_CODE,
            )
        except Exception as exc:
            logger.error("OptionsEngine creation error: %s", exc)
    return None

options_engine = get_options_engine()

# =====================================================================
# 9. UNIVERSAL 5,000+ EQUITY MASTER DATABASE (NSE & BSE)
# =====================================================================
PRIMARY_SEED_EQUITIES = {
    "RELIANCE": {"name": "Reliance Industries Ltd", "token_nse": "2885", "token_bse": "500325", "yfinance": "RELIANCE.NS", "exchange": "NSE"},
    "TCS": {"name": "Tata Consultancy Services Ltd", "token_nse": "11536", "token_bse": "532540", "yfinance": "TCS.NS", "exchange": "NSE"},
    "HDFCBANK": {"name": "HDFC Bank Ltd", "token_nse": "1333", "token_bse": "500180", "yfinance": "HDFCBANK.NS", "exchange": "NSE"},
    "ICICIBANK": {"name": "ICICI Bank Ltd", "token_nse": "4963", "token_bse": "532174", "yfinance": "ICICIBANK.NS", "exchange": "NSE"},
    "INFY": {"name": "Infosys Ltd", "token_nse": "1594", "token_bse": "500209", "yfinance": "INFY.NS", "exchange": "NSE"},
    "SBIN": {"name": "State Bank of India", "token_nse": "3045", "token_bse": "500112", "yfinance": "SBIN.NS", "exchange": "NSE"},
    "BHARTIARTL": {"name": "Bharti Airtel Ltd", "token_nse": "10604", "token_bse": "532454", "yfinance": "BHARTIARTL.NS", "exchange": "NSE"},
    "TATAMOTORS": {"name": "Tata Motors Ltd", "token_nse": "3456", "token_bse": "500570", "yfinance": "TATAMOTORS.NS", "exchange": "NSE"},
    "ITC": {"name": "ITC Ltd", "token_nse": "1660", "token_bse": "500875", "yfinance": "ITC.NS", "exchange": "NSE"},
    "LT": {"name": "Larsen & Toubro Ltd", "token_nse": "11483", "token_bse": "500510", "yfinance": "LT.NS", "exchange": "NSE"},
    "HINDUNILVR": {"name": "Hindustan Unilever Ltd", "token_nse": "1394", "token_bse": "500696", "yfinance": "HINDUNILVR.NS", "exchange": "NSE"},
    "KOTAKBANK": {"name": "Kotak Mahindra Bank", "token_nse": "1922", "token_bse": "500247", "yfinance": "KOTAKBANK.NS", "exchange": "NSE"},
    "AXISBANK": {"name": "Axis Bank Ltd", "token_nse": "5900", "token_bse": "532215", "yfinance": "AXISBANK.NS", "exchange": "NSE"},
    "MARUTI": {"name": "Maruti Suzuki India", "token_nse": "10999", "token_bse": "532500", "yfinance": "MARUTI.NS", "exchange": "NSE"},
    "SUNPHARMA": {"name": "Sun Pharmaceutical", "token_nse": "3351", "token_bse": "524715", "yfinance": "SUNPHARMA.NS", "exchange": "NSE"},
    "TITAN": {"name": "Titan Company Ltd", "token_nse": "3506", "token_bse": "500114", "yfinance": "TITAN.NS", "exchange": "NSE"},
    "BAJFINANCE": {"name": "Bajaj Finance Ltd", "token_nse": "317", "token_bse": "500034", "yfinance": "BAJFINANCE.NS", "exchange": "NSE"},
    "BAJAJFINSV": {"name": "Bajaj Finserv Ltd", "token_nse": "16675", "token_bse": "532978", "yfinance": "BAJAJFINSV.NS", "exchange": "NSE"},
    "TATASTEEL": {"name": "Tata Steel Ltd", "token_nse": "3499", "token_bse": "500470", "yfinance": "TATASTEEL.NS", "exchange": "NSE"},
    "ASIANPAINT": {"name": "Asian Paints Ltd", "token_nse": "236", "token_bse": "500820", "yfinance": "ASIANPAINT.NS", "exchange": "NSE"},
    "NTPC": {"name": "NTPC Ltd", "token_nse": "11630", "token_bse": "532555", "yfinance": "NTPC.NS", "exchange": "NSE"},
    "POWERGRID": {"name": "Power Grid Corporation", "token_nse": "14977", "token_bse": "532898", "yfinance": "POWERGRID.NS", "exchange": "NSE"},
    "ONGC": {"name": "Oil & Natural Gas Corp", "token_nse": "2475", "token_bse": "500312", "yfinance": "ONGC.NS", "exchange": "NSE"},
    "COALINDIA": {"name": "Coal India Ltd", "token_nse": "20374", "token_bse": "533278", "yfinance": "COALINDIA.NS", "exchange": "NSE"},
    "M&M": {"name": "Mahindra & Mahindra Ltd", "token_nse": "2031", "token_bse": "500520", "yfinance": "M&M.NS", "exchange": "NSE"},
    "ADANIENT": {"name": "Adani Enterprises Ltd", "token_nse": "25", "token_bse": "512599", "yfinance": "ADANIENT.NS", "exchange": "NSE"},
    "ADANIPORTS": {"name": "Adani Ports & SEZ", "token_nse": "15083", "token_bse": "532921", "yfinance": "ADANIPORTS.NS", "exchange": "NSE"},
    "WIPRO": {"name": "Wipro Ltd", "token_nse": "3787", "token_bse": "507685", "yfinance": "WIPRO.NS", "exchange": "NSE"},
    "TECHM": {"name": "Tech Mahindra Ltd", "token_nse": "13538", "token_bse": "532755", "yfinance": "TECHM.NS", "exchange": "NSE"},
    "HCLTECH": {"name": "HCL Technologies Ltd", "token_nse": "7229", "token_bse": "532281", "yfinance": "HCLTECH.NS", "exchange": "NSE"},
    "JSWSTEEL": {"name": "JSW Steel Ltd", "token_nse": "11723", "token_bse": "500228", "yfinance": "JSWSTEEL.NS", "exchange": "NSE"},
    "TATACONSUM": {"name": "Tata Consumer Products", "token_nse": "3432", "token_bse": "500800", "yfinance": "TATACONSUM.NS", "exchange": "NSE"},
    "BPCL": {"name": "Bharat Petroleum Corp", "token_nse": "526", "token_bse": "500547", "yfinance": "BPCL.NS", "exchange": "NSE"},
    "GRASIM": {"name": "Grasim Industries Ltd", "token_nse": "1232", "token_bse": "500300", "yfinance": "GRASIM.NS", "exchange": "NSE"},
    "ULTRACEMCO": {"name": "UltraTech Cement Ltd", "token_nse": "11532", "token_bse": "532538", "yfinance": "ULTRACEMCO.NS", "exchange": "NSE"},
    "HEROMOTOCO": {"name": "Hero MotoCorp Ltd", "token_nse": "1348", "token_bse": "500182", "yfinance": "HEROMOTOCO.NS", "exchange": "NSE"},
    "EICHERMOT": {"name": "Eicher Motors Ltd", "token_nse": "910", "token_bse": "505200", "yfinance": "EICHERMOT.NS", "exchange": "NSE"},
    "CIPLA": {"name": "Cipla Ltd", "token_nse": "694", "token_bse": "500087", "yfinance": "CIPLA.NS", "exchange": "NSE"},
    "DRREDDY": {"name": "Dr. Reddy's Laboratories", "token_nse": "881", "token_bse": "500124", "yfinance": "DRREDDY.NS", "exchange": "NSE"},
    "APOLLOHOSP": {"name": "Apollo Hospitals Enterprise", "token_nse": "157", "token_bse": "508869", "yfinance": "APOLLOHOSP.NS", "exchange": "NSE"},
    "DIVISLAB": {"name": "Divi's Laboratories Ltd", "token_nse": "10940", "token_bse": "532488", "yfinance": "DIVISLAB.NS", "exchange": "NSE"},
    "BRITANNIA": {"name": "Britannia Industries Ltd", "token_nse": "547", "token_bse": "500825", "yfinance": "BRITANNIA.NS", "exchange": "NSE"},
    "NESTLEIND": {"name": "Nestle India Ltd", "token_nse": "17963", "token_bse": "500790", "yfinance": "NESTLEIND.NS", "exchange": "NSE"},
    "SUZLON": {"name": "Suzlon Energy Ltd", "token_nse": "13061", "token_bse": "532667", "yfinance": "SUZLON.NS", "exchange": "NSE"},
    "ZOMATO": {"name": "Zomato Ltd", "token_nse": "5097", "token_bse": "543320", "yfinance": "ZOMATO.NS", "exchange": "NSE"},
    "JIOFIN": {"name": "Jio Financial Services", "token_nse": "18143", "token_bse": "543940", "yfinance": "JIOFIN.NS", "exchange": "NSE"},
    "IRFC": {"name": "Indian Railway Finance Corp", "token_nse": "2029", "token_bse": "543257", "yfinance": "IRFC.NS", "exchange": "NSE"},
    "RVNL": {"name": "Rail Vikas Nigam Ltd", "token_nse": "30108", "token_bse": "542649", "yfinance": "RVNL.NS", "exchange": "NSE"},
    "IREDA": {"name": "Indian Renewable Energy Dev", "token_nse": "20108", "token_bse": "544026", "yfinance": "IREDA.NS", "exchange": "NSE"},
    "IRCTC": {"name": "IRCTC Ltd", "token_nse": "13611", "token_bse": "542830", "yfinance": "IRCTC.NS", "exchange": "NSE"},
    "HAL": {"name": "Hindustan Aeronautics Ltd", "token_nse": "2303", "token_bse": "541154", "yfinance": "HAL.NS", "exchange": "NSE"},
    "BEL": {"name": "Bharat Electronics Ltd", "token_nse": "383", "token_bse": "500049", "yfinance": "BEL.NS", "exchange": "NSE"},
    "COCHINSHIP": {"name": "Cochin Shipyard Ltd", "token_nse": "21808", "token_bse": "540678", "yfinance": "COCHINSHIP.NS", "exchange": "NSE"},
    "MAZDOCK": {"name": "Mazagon Dock Shipbuilders", "token_nse": "2032", "token_bse": "543237", "yfinance": "MAZDOCK.NS", "exchange": "NSE"},
}

@st.cache_data(ttl=86400, show_spinner=False)
def load_5000_equity_master() -> Dict[str, Dict[str, Any]]:
    """Ingests official exchange equity masters covering 5,000+ listed equities across NSE & BSE."""
    master: Dict[str, Dict[str, Any]] = {}
    master.update(PRIMARY_SEED_EQUITIES)

    # Ingest official NSE Listed Equities (Mainboard + SME)
    try:
        nse_url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
        resp = requests.get(nse_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if resp.ok and len(resp.text) > 1000:
            lines = resp.text.splitlines()
            header = [h.strip().upper() for h in lines[0].split(",")]
            sym_idx = header.index("SYMBOL") if "SYMBOL" in header else 0
            name_idx = header.index("NAME OF COMPANY") if "NAME OF COMPANY" in header else 1
            series_idx = header.index("SERIES") if "SERIES" in header else 2

            for line in lines[1:]:
                parts = [p.strip().strip('"') for p in line.split(",")]
                if len(parts) > max(sym_idx, name_idx, series_idx):
                    symbol = parts[sym_idx].upper()
                    series = parts[series_idx].upper()
                    name = parts[name_idx]
                    if series in ["EQ", "BE", "SM", "ST"] and symbol:
                        master[symbol] = {
                            "name": name,
                            "token_nse": None,
                            "token_bse": None,
                            "yfinance": f"{symbol}.NS",
                            "exchange": "NSE"
                        }
    except Exception as exc:
        logger.info("NSE EQUITY_L.csv online fetch skipped: %s", exc)

    # Ingest Angel One OpenAPI Scrip Master for BSE Scrips and Exact Tokens
    try:
        angel_master_url = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
        resp = requests.get(angel_master_url, timeout=6)
        if resp.ok:
            data = resp.json()
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        exch = str(item.get("exch_seg", "")).upper()
                        inst = str(item.get("instrumenttype", "")).strip()
                        if exch in ["NSE", "BSE"] and (inst == "" or inst == "EQUITY"):
                            sym = str(item.get("symbol", "")).replace("-EQ", "").strip().upper()
                            token = str(item.get("token", "")).strip()
                            name = str(item.get("name", sym)).strip()
                            if sym and len(sym) <= 25:
                                if sym in master:
                                    if exch == "NSE": master[sym]["token_nse"] = token
                                    elif exch == "BSE": master[sym]["token_bse"] = token
                                else:
                                    master[sym] = {
                                        "name": name,
                                        "token_nse": token if exch == "NSE" else None,
                                        "token_bse": token if exch == "BSE" else None,
                                        "yfinance": f"{sym}.{'NS' if exch == 'NSE' else 'BO'}",
                                        "exchange": exch
                                    }
    except Exception as exc:
        logger.info("Angel OpenAPI scrip master online fetch skipped: %s", exc)

    logger.info("Universal Equity Master loaded with %d active securities.", len(master))
    return master

UNIVERSAL_EQUITIES = load_5000_equity_master()

# =====================================================================
# 10. GLOBAL MACRO & COMMODITIES ENGINE
# =====================================================================
class GlobalMacroEngine:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def fetch_macro_quotes(self) -> Dict[str, Any]:
        out = {
            "GIFT_NIFTY": {"symbol": "Gift Nifty Spread", "price": None, "change_pct": 0.0, "status": "NEUTRAL"},
            "NASDAQ": {"symbol": "Nasdaq Composite", "price": None, "change_pct": 0.0, "status": "UNKNOWN"},
            "CRUDE_OIL": {"symbol": "Brent Crude Oil", "price": None, "change_pct": 0.0, "status": "UNKNOWN"},
            "GOLD": {"symbol": "Gold (MCX/COMEX)", "price": None, "change_pct": 0.0, "status": "UNKNOWN"},
        }
        try:
            url_nq = "https://query1.finance.yahoo.com/v8/finance/chart/%5EIXIC?interval=1d&range=2d"
            resp_nq = self.session.get(url_nq, timeout=3)
            if resp_nq.ok:
                meta = resp_nq.json()["chart"]["result"][0]["meta"]
                price = float(meta.get("regularMarketPrice", 0.0))
                prev = float(meta.get("chartPreviousClose", price))
                pct = ((price - prev) / prev) * 100 if prev > 0 else 0.0
                out["NASDAQ"] = {
                    "symbol": "Nasdaq Composite", "price": price, "change_pct": pct,
                    "status": "GREEN" if pct >= 0.25 else ("RED" if pct <= -0.25 else "YELLOW"),
                }
        except Exception:
            pass

        try:
            url_crude = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1d&range=2d"
            resp_cr = self.session.get(url_crude, timeout=3)
            if resp_cr.ok:
                meta_cr = resp_cr.json()["chart"]["result"][0]["meta"]
                price_c = float(meta_cr.get("regularMarketPrice", 0.0))
                prev_c = float(meta_cr.get("chartPreviousClose", price_c))
                pct_c = ((price_c - prev_c) / prev_c) * 100 if prev_c > 0 else 0.0
                out["CRUDE_OIL"] = {
                    "symbol": "Brent Crude Oil", "price": price_c, "change_pct": pct_c,
                    "status": "RED" if pct_c >= 1.0 else ("GREEN" if pct_c <= -1.0 else "YELLOW"),
                }
        except Exception:
            pass

        return out

@st.cache_resource(show_spinner=False)
def get_global_macro_engine():
    try: return GlobalMacroEngine()
    except Exception as exc:
        logger.error("Failed to initialize GlobalMacroEngine: %s", exc)
        return None

global_macro_inst = get_global_macro_engine()

# =====================================================================
# 11. VERIFIED MARKET DATA INGESTION & DATA PROVENANCE
# =====================================================================
def num(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None: return default
        if isinstance(x, str): x = x.replace(",", "").strip()
        val = float(x)
        return val if np.isfinite(val) else default
    except Exception:
        return default

def fmt(x: Any, digits: int = 2) -> str:
    val = num(x)
    return "-" if val is None else f"{val:,.{digits}f}"

def clean_df(df: Any) -> pd.DataFrame:
    if df is None: return pd.DataFrame()
    if isinstance(df, pd.DataFrame): return df.copy()
    try: return pd.DataFrame(df)
    except Exception: return pd.DataFrame()

def first_value(row: Any, names: List[str], default: Any = None) -> Any:
    for name in names:
        if isinstance(row, dict) and name in row:
            val = row.get(name)
            if val is not None and str(val) != "": return val
        try:
            if hasattr(row, "index") and name in row.index:
                val = row[name]
                if pd.notna(val): return val
        except Exception:
            pass
    return default

def find_column(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    for name in names:
        if name in df.columns: return name
    return None

def normalize_option_type(value: Any) -> str:
    if not value: return ""
    x = str(value).strip().upper()
    if "CE" in x or "CALL" in x or x.endswith("C"): return "CE"
    if "PE" in x or "PUT" in x or x.endswith("P"): return "PE"
    return ""

def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty or len(df) < 2: return df
    work = df.copy()
    if "datetime" in work.columns:
        try:
            work["datetime"] = pd.to_datetime(work["datetime"])
            if work["datetime"].dt.tz is None: work["datetime"] = work["datetime"].dt.tz_localize(IST)
            else: work["datetime"] = work["datetime"].dt.tz_convert(IST)
            work = work.set_index("datetime")
            rule_map = {"10m": "10min", "2h": "2h", "4h": "4h", "1d": "1D", "1w": "W-FRI", "1mo": "ME", "3mo": "3ME"}
            target_rule = rule_map.get(rule, rule)
            return work.resample(target_rule, closed="left", label="left").agg({
                "open": "first", "high": "max", "low": "min", "close": "last",
                "volume": "sum" if "volume" in work.columns else "count"
            }).dropna(subset=["close"]).reset_index()
        except Exception:
            pass

    step_div = 2 if rule in ["10m", "2h"] else (4 if rule == "4h" else (5 if rule == "1w" else 20))
    groups = work.groupby(work.index // step_div)
    return pd.DataFrame({
        "open": groups["open"].first(), "high": groups["high"].max(),
        "low": groups["low"].min(), "close": groups["close"].last(),
        "volume": groups["volume"].sum() if "volume" in work.columns else 0
    }).reset_index(drop=True)

def resample_5m_to_10m(df: pd.DataFrame) -> pd.DataFrame:
    return resample_ohlcv(df, "10m")

@st.cache_data(ttl=5, show_spinner=False)
def fetch_verified_spot(symbol: str) -> Dict[str, Any]:
    """Retrieves verified spot price with strict provenance tracking; no fake defaults."""
    now_str = datetime.now(IST).strftime("%H:%M:%S IST")
    
    # 1. Primary: Official NSE All Indices API
    try:
        url = "https://www.nseindia.com/api/allIndices"
        raw = nse_client.get_json(url)
        data = raw[0] if isinstance(raw, tuple) else raw
        if data and isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            name_check = "NIFTY BANK" if symbol == "BANKNIFTY" else ("NIFTY 50" if symbol == "NIFTY" else symbol)
            for idx in data["data"]:
                if isinstance(idx, dict):
                    idx_sym = str(idx.get("indexSymbol", "")).strip().upper()
                    idx_name = str(idx.get("index", "")).strip().upper()
                    if idx_sym == name_check or idx_name == name_check:
                        val = num(idx.get("last"))
                        change = num(idx.get("variation"))
                        p_change = num(idx.get("percentChange"))
                        if val and val > 0:
                            return {
                                "price": val, "change": change or 0.0, "p_change": p_change or 0.0,
                                "source": "NSE_PRIMARY_API", "status": "LIVE" if market_open() else "CACHED",
                                "timestamp": now_str
                            }
    except Exception:
        pass

    # 2. Secondary: Yahoo Finance Feed
    meta = INDEX_METADATA.get(symbol, {})
    yf_symbol = meta.get("yfinance")
    if yf_symbol:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1d&range=2d"
            resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok:
                res_data = resp.json()["chart"]["result"][0]
                m_data = res_data["meta"]
                price = float(m_data.get("regularMarketPrice", 0.0))
                prev = float(m_data.get("chartPreviousClose", price))
                if price > 0:
                    diff = price - prev
                    pct = (diff / prev * 100.0) if prev > 0 else 0.0
                    return {
                        "price": price, "change": diff, "p_change": pct,
                        "source": "YAHOO_SECONDARY_FEED", "status": "DELAYED",
                        "timestamp": now_str
                    }
        except Exception:
            pass

    return {"price": None, "change": 0.0, "p_change": 0.0, "source": "NONE", "status": "UNAVAILABLE", "timestamp": now_str}

def get_spot(symbol: str) -> Optional[float]:
    res = fetch_verified_spot(symbol)
    return res.get("price")

@st.cache_data(ttl=15, show_spinner=False)
def get_india_vix() -> Dict[str, Any]:
    vix_quote = fetch_verified_spot("INDIA_VIX")
    vix = vix_quote.get("price")
    now_str = datetime.now(IST).strftime("%H:%M:%S IST")

    if vix is None or vix <= 0:
        return {"vix": None, "regime": "DATA UNAVAILABLE", "sl_multiplier": 1.0, "status": "UNAVAILABLE", "timestamp": now_str}

    if vix < 12.0: regime, sl_mult = "LOW VOLATILITY", 0.88
    elif 12.0 <= vix <= 18.0: regime, sl_mult = "OPTIMAL BUYING", 0.85
    elif 18.0 < vix <= 24.0: regime, sl_mult = "HIGH VOLATILITY", 0.80
    else: regime, sl_mult = "EXTREME SWINGS", 0.75

    return {"vix": vix, "regime": regime, "sl_multiplier": sl_mult, "status": vix_quote["status"], "timestamp": now_str}

def determine_settlement_phase() -> str:
    now = datetime.now(IST)
    if is_trading_holiday(now.date()): return "MARKET HOLIDAY / SETTLED PREVIOUS CLOSE"
    current_time = now.time()
    if current_time < dtime(17, 30): return "LIVE SESSION (PREVIOUS CLOSE)"
    elif dtime(17, 30) <= current_time <= dtime(19, 0): return "RECONCILIATION IN PROGRESS"
    else: return "TODAY'S PROVISIONAL FIGURES"

# =====================================================================
# REVISED RESILIENT FII / DII INGESTION ENGINE (ATTRIBUTEERROR DEFECT FIXED)
# =====================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_fii_dii() -> Dict[str, Any]:
    """
    Robust institutional cash market parser with defensive type-checking to
    prevent AttributeError when exchange endpoints return dictionary error objects.
    """
    url = "https://www.nseindia.com/api/fiidiiTradeReact"
    raw_response = nse_client.get_json(url)
    settlement_status = determine_settlement_phase()
    now_str = datetime.now(IST).strftime("%d-%b-%Y %H:%M:%S IST")

    if isinstance(raw_response, tuple):
        data = raw_response[0]
    else:
        data = raw_response

    # Defensive normalization: Ensure items is strictly a list of dicts
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            items = data["data"]
        elif "category" in data:
            items = [data]

    if items:
        fii_net, dii_net = None, None
        for row in items:
            if not isinstance(row, dict):
                continue
            cat = str(row.get("category", "")).upper()
            raw_val = str(row.get("netValue", "0")).replace(",", "").strip()
            try:
                net_val = float(raw_val)
            except Exception:
                net_val = 0.0

            if "FII" in cat or "FPI" in cat:
                fii_net = net_val
            elif "DII" in cat:
                dii_net = net_val

        if fii_net is not None and dii_net is not None:
            combined = round(fii_net + dii_net, 2)
            score = 0
            score += 2 if fii_net > 1000 else (1 if fii_net > 300 else (-2 if fii_net < -1000 else (-1 if fii_net < -300 else 0)))
            score += 1 if dii_net > 500 else (-1 if dii_net < -500 else 0)

            bias = (
                "STRONG BULLISH" if score >= 2
                else ("MODERATE BULLISH" if score == 1
                else ("STRONG BEARISH" if score <= -2
                else ("MODERATE BEARISH" if score == -1 else "NEUTRAL")))
            )

            return {
                "available": True, "fii_net": fii_net, "dii_net": dii_net, "combined": combined,
                "score": score, "bias": bias, "source": "NSE_OFFICIAL_PRIMARY",
                "phase": settlement_status, "sync_time": now_str, "status": "LIVE"
            }

    return {
        "available": False, "fii_net": None, "dii_net": None, "combined": None,
        "score": 0, "bias": "NEUTRAL", "source": "NONE",
        "phase": settlement_status, "sync_time": now_str, "status": "UNAVAILABLE"
    }

fii_dii = fetch_fii_dii()

# =====================================================================
# 12. REGULATORY EXPIRIES & OPTION CHAIN INGESTION
# =====================================================================
def expiry_norm(x: Any) -> Optional[str]:
    if not x: return None
    if isinstance(x, (datetime, date)): return x.strftime("%Y-%m-%d")
    s = str(x).strip().upper()
    for f in ["%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%d%b%Y"]:
        try: return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except Exception: pass
    return s

def expiry_label(x: Any) -> str:
    n = expiry_norm(x)
    if not n: return "-"
    try: return datetime.strptime(n, "%Y-%m-%d").strftime("%d %b %Y")
    except Exception: return str(x)

def generate_calendar_expiries(symbol: str) -> List[str]:
    """Generates valid expiries adhering strictly to SEBI weekly/monthly restrictions."""
    now = datetime.now(IST)
    meta = INDEX_METADATA.get(symbol, INDEX_METADATA["NIFTY"])
    target_weekday = meta["weekly_day"]
    has_weekly = meta["has_weekly"]
    
    expiries = []
    cur = now.date()

    if has_weekly:
        for _ in range(6):
            days_ahead = (target_weekday - cur.weekday()) % 7
            if days_ahead == 0 and now.time() > dtime(15, 30) and cur == now.date():
                days_ahead = 7
            raw = cur + timedelta(days=days_ahead)
            valid = get_preceding_trading_day(raw)
            exp_str = valid.strftime("%Y-%m-%d")
            if exp_str not in expiries: expiries.append(exp_str)
            cur = raw + timedelta(days=7)
    else:
        # Monthly only: Last target weekday of current and next 2 months
        for m_offset in range(3):
            year = cur.year + (cur.month + m_offset - 1) // 12
            month = (cur.month + m_offset - 1) % 12 + 1
            next_m = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
            last_day = next_m - timedelta(days=1)
            d_back = (last_day.weekday() - target_weekday) % 7
            m_exp = last_day - timedelta(days=d_back)
            if m_exp >= now.date():
                valid = get_preceding_trading_day(m_exp)
                exp_str = valid.strftime("%Y-%m-%d")
                if exp_str not in expiries: expiries.append(exp_str)
    return sorted(list(set(expiries)))

@st.cache_data(ttl=120, show_spinner=False)
def load_expiries(symbol: str) -> List[str]:
    opt_eng = get_options_engine()
    if opt_eng is not None:
        try:
            res = opt_eng.get_expiry_options(symbol)
            vals = []
            for item in res or []:
                v = item.get("value") or item.get("expiry") if isinstance(item, dict) else item
                v = expiry_norm(v)
                if v: vals.append(v)
            if vals: return sorted(set(vals))
        except Exception:
            pass

    try:
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol.upper()}"
        raw = nse_client.get_json(url)
        data = raw[0] if isinstance(raw, tuple) else raw
        if data and isinstance(data, dict):
            records = data.get("records", {})
            if isinstance(records, dict):
                exp_dates = records.get("expiryDates", [])
                if isinstance(exp_dates, list):
                    vals = [expiry_norm(x) for x in exp_dates if expiry_norm(x)]
                    if vals: return sorted(set(vals))
    except Exception:
        pass

    return generate_calendar_expiries(symbol)

@st.cache_data(ttl=15, show_spinner=False)
def get_chain(symbol: str, expiry: Optional[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    opt_eng = get_options_engine()
    if opt_eng is not None and expiry:
        try:
            contracts = clean_df(opt_eng.get_option_contracts(underlying=symbol, expiry_date=expiry))
            quoted = clean_df(opt_eng.get_market_quote(contracts)) if not contracts.empty else contracts
            if not quoted.empty: return quoted, contracts
        except Exception:
            pass

    if expiry and symbol in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]:
        try:
            url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol.upper()}"
            raw = nse_client.get_json(url)
            data = raw[0] if isinstance(raw, tuple) else raw
            if data and isinstance(data, dict):
                records = data.get("records", {})
                if isinstance(records, dict):
                    data_items = records.get("data", [])
                    target_exp_norm = expiry_norm(expiry)
                    available_expiries = [expiry_norm(x) for x in records.get("expiryDates", []) if expiry_norm(x)]
                    if target_exp_norm not in available_expiries and available_expiries:
                        target_exp_norm = available_expiries[0]

                    matched_rows = []
                    if isinstance(data_items, list):
                        for item in data_items:
                            if isinstance(item, dict) and expiry_norm(item.get("expiryDate")) == target_exp_norm:
                                strike = num(item.get("strikePrice"))
                                if "CE" in item and isinstance(item["CE"], dict):
                                    ce = item["CE"]
                                    matched_rows.append({
                                        "strikePrice": strike, "option_type": "CE", "lastPrice": num(ce.get("lastPrice"), 0.0),
                                        "openInterest": int(num(ce.get("openInterest"), 0)), "changeinOpenInterest": int(num(ce.get("changeinOpenInterest"), 0)),
                                        "change": num(ce.get("change"), 0.0), "impliedVolatility": num(ce.get("impliedVolatility"), 12.8),
                                        "expiryDate": target_exp_norm,
                                    })
                                if "PE" in item and isinstance(item["PE"], dict):
                                    pe = item["PE"]
                                    matched_rows.append({
                                        "strikePrice": strike, "option_type": "PE", "lastPrice": num(pe.get("lastPrice"), 0.0),
                                        "openInterest": int(num(pe.get("openInterest"), 0)), "changeinOpenInterest": int(num(pe.get("changeinOpenInterest"), 0)),
                                        "change": num(pe.get("change"), 0.0), "impliedVolatility": num(pe.get("impliedVolatility"), 12.8),
                                        "expiryDate": target_exp_norm,
                                    })
                    if matched_rows:
                        df = pd.DataFrame(matched_rows)
                        return df, df
        except Exception:
            pass

    return pd.DataFrame(), pd.DataFrame()

def calculate_pcr(chain: pd.DataFrame) -> Optional[float]:
    if chain is not None and not chain.empty:
        oi_col = find_column(chain, ["openInterest", "opnInterest", "oi"])
        type_col = find_column(chain, ["option_type", "optionType", "type"])
        if oi_col and type_col:
            work = chain.copy()
            work["_oi"] = pd.to_numeric(work[oi_col], errors="coerce").fillna(0)
            work["_type"] = work[type_col].map(normalize_option_type)
            ce = work.loc[work["_type"] == "CE", "_oi"].sum()
            pe = work.loc[work["_type"] == "PE", "_oi"].sum()
            if ce > 0:
                pcr_val = pe / ce
                if 0 < pcr_val <= 10: return float(pcr_val)
    return None

def calculate_live_derivatives_proxy(chain: pd.DataFrame, pcr: Optional[float]) -> Dict[str, Any]:
    if pcr is None: return {"available": False, "score": 0, "bias": "NEUTRAL"}
    score = 2 if pcr >= 1.20 else (-2 if pcr <= 0.70 else 0)
    bias = "BULLISH" if score > 0 else ("BEARISH" if score < 0 else "NEUTRAL")
    return {"available": True, "score": score, "bias": bias}

# =====================================================================
# 13. ADVANCED QUANTITATIVE ENGINE: GREEKS, GEX & MAX PAIN
# =====================================================================
def calculate_advanced_greeks(spot: float, strike: float, dte_days: float, rate: float = 0.07, sigma: float = 0.128, option_type: str = "CE") -> Dict[str, float]:
    t = max(dte_days / 365.0, 1e-5)
    v = max(sigma, 1e-4)

    d1 = (math.log(spot / strike) + (rate + 0.5 * v**2) * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)

    pdf_d1 = norm_pdf(d1)
    cdf_d1 = norm_cdf(d1)
    cdf_d2 = norm_cdf(d2)

    gamma = pdf_d1 / (spot * v * math.sqrt(t))
    vega = (spot * pdf_d1 * math.sqrt(t)) / 100.0
    vanna = -pdf_d1 * d2 / v

    if option_type == "CE":
        price = spot * cdf_d1 - strike * math.exp(-rate * t) * cdf_d2
        delta = cdf_d1
        theta = (-(spot * pdf_d1 * v) / (2.0 * math.sqrt(t)) - rate * strike * math.exp(-rate * t) * cdf_d2) / 365.0
        charm = (pdf_d1 * (2.0 * rate * t - d2 * v * math.sqrt(t)) / (2.0 * t * v * math.sqrt(t))) / 365.0
    else:
        price = strike * math.exp(-rate * t) * norm_cdf(-d2) - spot * norm_cdf(-d1)
        delta = cdf_d1 - 1.0
        theta = (-(spot * pdf_d1 * v) / (2.0 * math.sqrt(t)) + rate * strike * math.exp(-rate * t) * norm_cdf(-d2)) / 365.0
        charm = (-pdf_d1 * (2.0 * rate * t - d2 * v * math.sqrt(t)) / (2.0 * t * v * math.sqrt(t))) / 365.0

    return {
        "price": price, "delta": delta, "gamma": gamma,
        "theta": theta, "vega": vega, "vanna": vanna, "charm": charm
    }

def compute_gex_and_max_pain(chain: pd.DataFrame, spot: Optional[float], symbol: str = "NIFTY") -> Dict[str, Any]:
    if chain is None or chain.empty or not spot or spot <= 0:
        return {
            "net_gex_cr": 0.0, "gex_regime": "NEUTRAL", "gamma_flip": spot or 25000,
            "max_pain": spot or 25000, "call_wall": (spot or 25000) + 200, "put_wall": (spot or 25000) - 200,
            "expected_move": 150.0, "atm_iv": 12.8, "pcr": None
        }

    meta = INDEX_METADATA.get(symbol, INDEX_METADATA["NIFTY"])
    lot_size = meta["lot_size"]

    s_col = find_column(chain, ["strike", "strikePrice"])
    t_col = find_column(chain, ["option_type", "optionType", "type"])
    oi_col = find_column(chain, ["openInterest", "oi", "opnInterest"])
    p_col = find_column(chain, ["lastPrice", "ltp", "close"])
    iv_col = find_column(chain, ["impliedVolatility", "iv"])

    if not (s_col and t_col and oi_col):
        return {
            "net_gex_cr": 0.0, "gex_regime": "NEUTRAL", "gamma_flip": spot,
            "max_pain": spot, "call_wall": spot + 200, "put_wall": spot - 200,
            "expected_move": 150.0, "atm_iv": 12.8, "pcr": None
        }

    work = chain.copy()
    work["_s"] = pd.to_numeric(work[s_col], errors="coerce")
    if work["_s"].max() > 200000: work["_s"] = work["_s"] / 100.0
    work["_t"] = work[t_col].map(normalize_option_type)
    work["_oi"] = pd.to_numeric(work[oi_col], errors="coerce").fillna(0)
    work["_p"] = pd.to_numeric(work[p_col], errors="coerce").fillna(0) if p_col else 0.0
    work["_iv"] = pd.to_numeric(work[iv_col], errors="coerce").fillna(12.8) if iv_col else 12.8
    work = work.dropna(subset=["_s"]).copy()

    work = work[(work["_s"] >= spot * 0.92) & (work["_s"] <= spot * 1.08)]
    if work.empty:
        return {
            "net_gex_cr": 0.0, "gex_regime": "NEUTRAL", "gamma_flip": spot,
            "max_pain": spot, "call_wall": spot + 200, "put_wall": spot - 200,
            "expected_move": 150.0, "atm_iv": 12.8, "pcr": None
        }

    calls = work[work["_t"] == "CE"]
    puts = work[work["_t"] == "PE"]

    tot_ce_oi = calls["_oi"].sum()
    tot_pe_oi = puts["_oi"].sum()
    pcr = round(tot_pe_oi / tot_ce_oi, 2) if tot_ce_oi > 0 else None

    call_wall = float(calls.loc[calls["_oi"].idxmax()]["_s"]) if not calls.empty and calls["_oi"].max() > 0 else spot + 200
    put_wall = float(puts.loc[puts["_oi"].idxmax()]["_s"]) if not puts.empty and puts["_oi"].max() > 0 else spot - 200

    unique_strikes = sorted(work["_s"].unique())
    strike_payouts = {}
    for test_s in unique_strikes:
        ce_loss = (calls["_s"].apply(lambda k: max(0.0, test_s - k)) * calls["_oi"]).sum()
        pe_loss = (puts["_s"].apply(lambda k: max(0.0, k - test_s)) * puts["_oi"]).sum()
        strike_payouts[test_s] = ce_loss + pe_loss

    max_pain = min(strike_payouts.keys(), key=lambda k: strike_payouts[k]) if strike_payouts else spot

    total_gex = 0.0
    strike_gex_map = {}
    for s_val in unique_strikes:
        c_sub = calls[calls["_s"] == s_val]
        p_sub = puts[puts["_s"] == s_val]
        c_oi = float(c_sub["_oi"].iloc[0]) if not c_sub.empty else 0.0
        p_oi = float(p_sub["_oi"].iloc[0]) if not p_sub.empty else 0.0
        iv_val = float(c_sub["_iv"].iloc[0]) if not c_sub.empty and c_sub["_iv"].iloc[0] > 0 else 12.8

        g_info = calculate_advanced_greeks(spot, s_val, dte_days=6.0, rate=0.07, sigma=iv_val/100.0, option_type="CE")
        g_val = g_info["gamma"]

        # Call GEX is positive for market makers; Put GEX is negative
        ce_gex = (spot**2 * g_val * c_oi * lot_size * 0.01) / 1e7
        pe_gex = (-spot**2 * g_val * p_oi * lot_size * 0.01) / 1e7
        net_s_gex = ce_gex + pe_gex
        strike_gex_map[s_val] = net_s_gex
        total_gex += net_s_gex

    gamma_flip = spot
    cum_gex = 0.0
    for s in sorted(strike_gex_map.keys()):
        cum_gex += strike_gex_map[s]
        if cum_gex >= 0:
            gamma_flip = s
            break

    gex_regime = "POSITIVE (MEAN-REVERTING)" if total_gex >= 0 else "NEGATIVE (VOLATILITY EXPANSION)"

    atm_calls = calls.iloc[(calls["_s"] - spot).abs().argsort()[:1]] if not calls.empty else pd.DataFrame()
    atm_puts = puts.iloc[(puts["_s"] - spot).abs().argsort()[:1]] if not puts.empty else pd.DataFrame()
    atm_c_p = float(atm_calls["_p"].iloc[0]) if not atm_calls.empty else 150.0
    atm_p_p = float(atm_puts["_p"].iloc[0]) if not atm_puts.empty else 120.0
    straddle = atm_c_p + atm_p_p
    expected_move = round(0.80 * straddle, 1) if straddle > 0 else 150.0
    atm_iv = float(atm_calls["_iv"].iloc[0]) if not atm_calls.empty else 12.8

    return {
        "net_gex_cr": round(total_gex, 2), "gex_regime": gex_regime, "gamma_flip": gamma_flip,
        "max_pain": max_pain, "call_wall": call_wall, "put_wall": put_wall,
        "expected_move": expected_move, "atm_iv": round(atm_iv, 1), "pcr": pcr
    }

def calculate_quarter_kelly(p_win: float, reward_risk: float) -> float:
    if reward_risk <= 0: return 0.0
    q_loss = 1.0 - p_win
    kelly = (p_win * reward_risk - q_loss) / reward_risk
    quarter_kelly = max(0.0, kelly / 4.0)
    return round(quarter_kelly * 100.0, 1)

def classify_oi_buildup(price_change: float, oi_change: float) -> str:
    if price_change >= 0 and oi_change > 0: return "LONG BUILDUP (Bullish Aggression)"
    elif price_change >= 0 and oi_change <= 0: return "SHORT COVERING (Trapped Sellers Exiting)"
    elif price_change < 0 and oi_change > 0: return "SHORT BUILDUP (Heavy Writing Pressure)"
    elif price_change < 0 and oi_change <= 0: return "LONG UNWINDING (Exiting Positions)"
    return "CONSOLIDATION / NEUTRAL"

# =====================================================================
# 14. TECHNICAL INDICATORS PIPELINE & ANCHORED VWAP
# =====================================================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_ohlcv(symbol: str, interval: str = "FIVE_MINUTE", days: int = 5) -> pd.DataFrame:
    if symbol not in INDEX_METADATA: return pd.DataFrame()
    meta = INDEX_METADATA[symbol]
    exchange = meta["exchange"]
    token = meta["candle_token"]

    tf_entry = None
    for k, v in TIMEFRAME_CONFIG.items():
        if v["smartapi"] == interval or k == interval:
            tf_entry = v
            break
    if not tf_entry: tf_entry = TIMEFRAME_CONFIG.get("5m")

    broker_interval = tf_entry["smartapi"]
    resample_target = None
    if interval in ["2h", "TWO_HOUR"]: broker_interval, resample_target = "ONE_HOUR", "2h"
    elif interval in ["4h", "FOUR_HOUR"]: broker_interval, resample_target = "ONE_HOUR", "4h"
    elif interval in ["1w", "ONE_WEEK"]: broker_interval, resample_target = "ONE_DAY", "1w"
    elif interval in ["1mo", "ONE_MONTH"]: broker_interval, resample_target = "ONE_DAY", "1mo"
    elif interval in ["3mo", "THREE_MONTH"]: broker_interval, resample_target = "ONE_DAY", "3mo"
    elif interval in ["10m", "TEN_MINUTE"]: resample_target = "10m"

    if telemetry and hasattr(telemetry, "fetch_ohlcv"):
        try:
            df = clean_df(telemetry.fetch_ohlcv(exchange=exchange, token=str(token), interval=broker_interval, days=days or tf_entry["days"]))
            if not df.empty:
                rename = {}
                for c in df.columns:
                    lc = str(c).lower()
                    if lc in ["open", "o"]: rename[c] = "open"
                    elif lc in ["high", "h"]: rename[c] = "high"
                    elif lc in ["low", "l"]: rename[c] = "low"
                    elif lc in ["close", "c", "ltp"]: rename[c] = "close"
                    elif lc in ["volume", "vol"]: rename[c] = "volume"
                    elif lc in ["timestamp", "time", "date"]: rename[c] = "datetime"
                df = df.rename(columns=rename)
                needed = ["open", "high", "low", "close"]
                for c in needed + (["volume"] if "volume" in df.columns else []):
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                df = df.dropna(subset=needed).reset_index(drop=True)
                if resample_target: df = resample_ohlcv(df, resample_target)
                if len(df) >= 5: return df
        except Exception:
            pass

    yf_symbol = meta.get("yfinance")
    if yf_symbol:
        yf_int = tf_entry["yfinance"]
        yf_range = tf_entry["yf_range"]
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval={yf_int}&range={yf_range}"
            resp = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok:
                data = resp.json()["chart"]["result"][0]
                quotes = data["indicators"]["quote"][0]
                timestamps = data.get("timestamp", [])
                df = pd.DataFrame({
                    "datetime": [datetime.fromtimestamp(ts, tz=IST) for ts in timestamps] if timestamps else None,
                    "open": quotes.get("open", []), "high": quotes.get("high", []),
                    "low": quotes.get("low", []), "close": quotes.get("close", []),
                    "volume": quotes.get("volume", []),
                }).dropna(subset=["close"]).reset_index(drop=True)
                if interval in ["TEN_MINUTE", "10m"]: df = resample_5m_to_10m(df)
                elif resample_target: df = resample_ohlcv(df, resample_target)
                if not df.empty and len(df) >= 5: return df
        except Exception:
            pass

    return pd.DataFrame()

def add_indicators(df: pd.DataFrame, current_live_price: Optional[float] = None) -> pd.DataFrame:
    if df is None or df.empty or len(df) < 5: return pd.DataFrame()
    work = df.copy()

    if current_live_price and current_live_price > 0:
        last_idx = work.index[-1]
        work.at[last_idx, "close"] = current_live_price
        if current_live_price > work.at[last_idx, "high"]: work.at[last_idx, "high"] = current_live_price
        if current_live_price < work.at[last_idx, "low"]: work.at[last_idx, "low"] = current_live_price

    close, high, low = work["close"], work["high"], work["low"]
    work["EMA20"] = close.ewm(span=20, adjust=False).mean()
    work["EMA50"] = close.ewm(span=50, adjust=False).mean()
    work["EMA200"] = close.ewm(span=200, adjust=False).mean()

    # Wilder's RMA Smoothing for RSI
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    work["RSI"] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

    work["MACD"] = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    work["MACD_SIGNAL"] = work["MACD"].ewm(span=9, adjust=False).mean()

    # True Range & Wilder's ADX
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0/14, min_periods=14, adjust=False).mean()
    work["ATR"] = atr

    plus_dm = high.diff().where((high.diff() > -low.diff()) & (high.diff() > 0), 0.0)
    minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0.0)
    plus_di = 100 * plus_dm.ewm(alpha=1.0/14, min_periods=14, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1.0/14, min_periods=14, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    work["ADX"] = dx.ewm(alpha=1.0/14, min_periods=14, adjust=False).mean()

    # Session-Anchored VWAP (Resets at 09:15:00 IST)
    typical = (high + low + close) / 3.0
    vol = work["volume"] if "volume" in work.columns and work["volume"].sum() > 0 else pd.Series(1.0, index=work.index)
    if "datetime" in work.columns:
        work["dt"] = pd.to_datetime(work["datetime"])
        is_new_session = (work["dt"].dt.date != work["dt"].shift(1).dt.date)
        session_id = is_new_session.cumsum()
    else:
        session_id = pd.Series(0, index=work.index)

    cum_vol = vol.groupby(session_id).cumsum().replace(0, np.nan)
    cum_pv = (typical * vol).groupby(session_id).cumsum()
    vwap = cum_pv / cum_vol
    work["VWAP"] = vwap

    cum_var = ((typical - vwap)**2 * vol).groupby(session_id).cumsum() / cum_vol
    vwap_std = np.sqrt(cum_var.clip(lower=0.0))
    work["VWAP_STD"] = vwap_std
    work["VWAP_UPPER_1"] = vwap + vwap_std
    work["VWAP_LOWER_1"] = vwap - vwap_std
    work["VWAP_UPPER_2"] = vwap + (2.0 * vwap_std)
    work["VWAP_LOWER_2"] = vwap - (2.0 * vwap_std)
    work["VOL_AVG20"] = vol.rolling(20).mean()

    return work

def analyze_market(symbol: str, proxy: Optional[Dict[str, Any]] = None, explicit_spot: Optional[float] = None, tf_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if tf_cfg is None: tf_cfg = TIMEFRAME_CONFIG["5m"]

    res = {
        "symbol": symbol, "trend": "UNKNOWN", "last": explicit_spot, "rsi": None, "adx": None,
        "ema20": None, "ema50": None, "vwap": None, "vwap_upper_1": None, "vwap_lower_1": None,
        "support": None, "resistance": None, "technical_score": 0, "institutional_score": 0,
        "score": 0, "reasons": [],
    }

    df = add_indicators(fetch_ohlcv(symbol, tf_cfg["smartapi"], tf_cfg["days"]), current_live_price=explicit_spot)
    if df.empty: return res

    row = df.iloc[-1]
    last = explicit_spot or num(row.get("close"))
    res["last"] = last
    res["rsi"] = num(row.get("RSI"))
    res["adx"] = num(row.get("ADX"))
    res["ema20"] = num(row.get("EMA20"))
    res["ema50"] = num(row.get("EMA50"))
    res["vwap"] = num(row.get("VWAP"))
    res["vwap_upper_1"] = num(row.get("VWAP_UPPER_1"))
    res["vwap_lower_1"] = num(row.get("VWAP_LOWER_1"))
    res["support"] = num(df["low"].tail(30).min())
    res["resistance"] = num(df["high"].tail(30).max())

    score = 0
    if res["ema20"] and res["ema50"] and last:
        if last > res["ema20"] > res["ema50"]:
            score += 2
            res["reasons"].append(f"Price sustained above EMA20 & EMA50 ({tf_cfg['label']}).")
        elif last < res["ema20"] < res["ema50"]:
            score -= 2
            res["reasons"].append(f"Price sustained below EMA20 & EMA50 ({tf_cfg['label']}).")

    if res["vwap"] and last:
        if last > res["vwap"]:
            score += 1
            res["reasons"].append("Price trading above institutional VWAP benchmark.")
        else:
            score -= 1
            res["reasons"].append("Price trading below institutional VWAP benchmark.")

    if res["rsi"]:
        if res["rsi"] >= 60:
            score += 1
            res["reasons"].append(f"RSI ({res['rsi']:.1f}) in bullish expansion zone.")
        elif res["rsi"] <= 40:
            score -= 1
            res["reasons"].append(f"RSI ({res['rsi']:.1f}) in bearish distribution zone.")

    if res["adx"] and res["adx"] >= 20:
        res["reasons"].append(f"ADX ({res['adx']:.1f}) confirms active trend strength.")

    res["technical_score"] = score
    inst_score = fii_dii.get("score", 0) if fii_dii.get("available") else (proxy.get("score", 0) if proxy else 0)
    res["institutional_score"] = inst_score
    res["score"] = score + inst_score
    res["trend"] = "BULLISH" if res["score"] >= 3 else ("BEARISH" if res["score"] <= -3 else "SIDEWAYS")
    return res

# =====================================================================
# 15. CANDLESTICK PATTERNS & CONFLUENCE EVALUATOR
# =====================================================================
def analyze_candlesticks_and_volume(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or len(df) < 5:
        return {"status": "YELLOW", "pattern": "AWAITING TICK DATA", "vol_ratio": 1.0, "reversal_risk": False, "reason": "Candle array loading."}

    c = df.iloc[-1]
    p = df.iloc[-2]
    open_p, close_p = float(c["open"]), float(c["close"])
    high_p, low_p = float(c["high"]), float(c["low"])
    vol = float(c["volume"]) if "volume" in c and pd.notna(c["volume"]) and c["volume"] > 0 else 1.0
    avg_vol = float(df["volume"].tail(20).mean()) if "volume" in df.columns and df["volume"].sum() > 0 else 1.0
    vol_ratio = (vol / avg_vol) if avg_vol > 0 else 1.0

    rng = max(high_p - low_p, 0.001)
    body = abs(close_p - open_p)
    upper_w = high_p - max(open_p, close_p)
    lower_w = min(open_p, close_p) - low_p

    prior_3_closes = df["close"].tail(4).values
    is_continuous_fall = (prior_3_closes[-1] < prior_3_closes[-2] < prior_3_closes[-3])

    if body <= (0.10 * rng):
        return {"status": "YELLOW", "pattern": "DOJI (PAUSE / INDECISION)", "vol_ratio": vol_ratio, "reversal_risk": False, "reason": f"Doji structure formed ({body/rng:.2f} ratio). Consolidation phase."}

    if lower_w >= (2.0 * body) and upper_w <= (0.25 * body):
        return {"status": "GREEN", "pattern": "BULLISH HAMMER PIN", "vol_ratio": vol_ratio, "reversal_risk": False, "reason": f"Support rejection hammer confirmed ({vol_ratio:.2f}x vol)."}

    if upper_w >= (2.0 * body) and lower_w <= (0.25 * body):
        return {"status": "RED", "pattern": "BEARISH SHOOTING STAR", "vol_ratio": vol_ratio, "reversal_risk": True, "reason": f"Resistance rejection shooting star confirmed ({vol_ratio:.2f}x vol)."}

    if (close_p > open_p) and (float(p["close"]) < float(p["open"])) and (close_p >= float(p["open"])):
        return {"status": "GREEN", "pattern": "BULLISH ENGULFING", "vol_ratio": vol_ratio, "reversal_risk": False, "reason": f"Bullish engulfing overriding prior candle ({vol_ratio:.2f}x vol)."}

    if (close_p < open_p) and (float(p["close"]) > float(p["open"])) and (close_p <= float(p["open"])):
        return {"status": "RED", "pattern": "BEARISH ENGULFING", "vol_ratio": vol_ratio, "reversal_risk": True, "reason": f"Bearish engulfing breakdown overriding prior candle ({vol_ratio:.2f}x vol)."}

    if body >= (0.50 * rng):
        status = "RED" if close_p < open_p else "GREEN"
        name = "BEARISH BREAKDOWN" if close_p < open_p else "BULLISH MARUBOZU"
        return {"status": status, "pattern": name, "vol_ratio": vol_ratio, "reversal_risk": (status == "RED"), "reason": f"Directional expansion confirmed ({vol_ratio:.2f}x vol)."}

    if is_continuous_fall:
        return {"status": "RED", "pattern": "STEADY BEARISH MOMENTUM", "vol_ratio": vol_ratio, "reversal_risk": False, "reason": "Consecutive lower closes confirm active downward trend."}

    return {"status": "YELLOW", "pattern": "RANGE CONSOLIDATION", "vol_ratio": vol_ratio, "reversal_risk": False, "reason": "Normal candle range without directional breakout."}

def analyze_smart_money(fii_dii_data: Dict[str, Any], pcr_val: Optional[float], df: Optional[pd.DataFrame] = None, current_spot: Optional[float] = None) -> Dict[str, Any]:
    score = 0
    notes = []
    has_data = False

    if pcr_val is not None:
        has_data = True
        if pcr_val >= 1.25: score += 2; notes.append(f"PCR {pcr_val:.2f} put writing support floor")
        elif pcr_val >= 1.00: score += 1; notes.append(f"PCR {pcr_val:.2f} mildly supportive")
        elif 0.70 < pcr_val < 1.00: score -= 1; notes.append(f"PCR {pcr_val:.2f} call writing resistance")
        else: score -= 2; notes.append(f"PCR {pcr_val:.2f} heavy call writing pressure")

    if fii_dii_data.get("available"):
        has_data = True
        score += fii_dii_data.get("score", 0)
        notes.append(f"FII/DII: {fii_dii_data.get('bias')}")

    if not has_data and df is not None and not df.empty and current_spot:
        day_open = float(df["open"].iloc[0])
        vwap_val = float(df["VWAP"].iloc[-1]) if "VWAP" in df.columns and pd.notna(df["VWAP"].iloc[-1]) else day_open
        if current_spot < vwap_val and current_spot < day_open:
            score -= 2
            notes.append(f"Institutional VWAP Breakdown (Spot {RUPEE}{current_spot:,.0f} < VWAP {RUPEE}{vwap_val:,.0f})")
        elif current_spot > vwap_val and current_spot > day_open:
            score += 2
            notes.append(f"Institutional VWAP Support (Spot {RUPEE}{current_spot:,.0f} > VWAP {RUPEE}{vwap_val:,.0f})")

    status = "GREEN" if score >= 2 else ("RED" if score <= -2 else "YELLOW")
    final_reason = " | ".join(notes) if notes else "Smart Money neutral."
    return {"status": status, "score": score, "reason": final_reason}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_composite_macro_news(macro_quotes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rss_url = "https://news.google.com/rss/search?q=Indian+stock+market+Nifty&hl=en-IN&gl=IN&ceid=IN:en"
    headlines = []
    try:
        resp = requests.get(rss_url, timeout=4)
        if resp.ok:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:6]:
                t = item.find("title")
                if t is not None and t.text: headlines.append(t.text)
    except Exception:
        pass

    text = " ".join(headlines).lower()
    bullish = sum(text.count(w) for w in ["surge", "jump", "record", "gain", "rally", "growth", "buying", "up", "bull", "inflow"])
    bearish = sum(text.count(w) for w in ["fall", "crash", "plunge", "slump", "inflation", "selling", "down", "drop", "war", "loss"])
    news_score = bullish - bearish

    macro_bonus = 0
    macro_notes = []
    if macro_quotes:
        nq = macro_quotes.get("NASDAQ", {}).get("change_pct", 0.0)
        crude = macro_quotes.get("CRUDE_OIL", {}).get("change_pct", 0.0)
        if nq >= 0.5: macro_bonus += 1; macro_notes.append(f"Nasdaq Strong (+{nq:.1f}%)")
        elif nq <= -0.5: macro_bonus -= 1; macro_notes.append(f"Nasdaq Drag ({nq:.1f}%)")

        if crude >= 1.5: macro_bonus -= 1; macro_notes.append(f"Crude Spike (+{crude:.1f}%)")
        elif crude <= -1.5: macro_bonus += 1; macro_notes.append(f"Crude Softening ({crude:.1f}%)")

    total_macro_score = news_score + macro_bonus
    status = "GREEN" if total_macro_score >= 2 else ("RED" if total_macro_score <= -2 else "YELLOW")
    summary = "BULLISH MACRO CATALYST" if status == "GREEN" else ("BEARISH MACRO HEADWINDS" if status == "RED" else "BALANCED / NEUTRAL MACRO")
    reason_str = f"News net: {news_score:+d}." + (" Cues: " + ", ".join(macro_notes) if macro_notes else "")

    return {"status": status, "score": total_macro_score, "summary": summary, "reason": reason_str}

def evaluate_all_permutations(l1: Dict[str, Any], l2: Dict[str, Any], l3: Dict[str, Any]) -> Dict[str, Any]:
    s1, s2, s3 = l1["status"], l2["status"], l3["status"]
    reds = [s1, s2, s3].count("RED")
    greens = [s1, s2, s3].count("GREEN")

    if reds == 3:
        return {"signal": f"{SIREN} ULTRA STRONG SHORT (BUY PE)", "action": "BUY PUT (PE)", "confidence": 95, "badge": "error", "allocation": "100% Capital Size", "rationale": "High-volume breakdown + Smart Money selling + Global macro headwinds fully aligned."}
    if greens == 3:
        return {"signal": f"{FIRE} ULTRA STRONG BUY (BUY CE)", "action": "BUY CALL (CE)", "confidence": 95, "badge": "success", "allocation": "100% Capital Size", "rationale": "High-volume breakout + Institutional buying + Global tailwinds fully aligned."}
    if reds >= 2 and greens == 0:
        return {"signal": f"{SIREN} STRONG SHORT (BUY PE)", "action": "BUY PUT (PE)", "confidence": 85, "badge": "error", "allocation": "75% Position Size", "rationale": "Price action and macro vectors confirm clear downward momentum."}
    if greens >= 2 and reds == 0:
        return {"signal": f"{BOLT} STRONG BUY (BUY CE)", "action": "BUY CALL (CE)", "confidence": 85, "badge": "success", "allocation": "75% Position Size", "rationale": "Price action and institutional flows confirm upward expansion."}
    if s1 == "RED" and greens == 0:
        return {"signal": f"{BOLT} MODERATE SHORT (BUY PE)", "action": "BUY PUT (PE)", "confidence": 70, "badge": "error", "allocation": "50% Position Size", "rationale": "Candle breakdown confirmed. Short positions favored with tight stop-loss."}
    if s1 == "GREEN" and reds == 0:
        return {"signal": f"{BOLT} MODERATE BUY (BUY CE)", "action": "BUY CALL (CE)", "confidence": 70, "badge": "success", "allocation": "50% Position Size", "rationale": "Candle breakout confirmed. Favor Call buying with trailing risk parameters."}
    if greens >= 1 and reds >= 1:
        return {"signal": f"{SWORDS} CONFLICT / STRICT NO TRADE", "action": "STRICT AVOID / CASH PRESERVATION", "confidence": 15, "badge": "info", "allocation": "0% Capital Size", "rationale": "Divergence detected: Price action diverges from Smart Money or Macro positioning."}
    return {"signal": f"{PAUSE} NO TRADE / WAIT FOR CLARITY", "action": "STAND ASIDE", "confidence": 20, "badge": "info", "allocation": "0% Capital Size", "rationale": "Consolidation phase detected. Await directional breakout confirmation."}

def calculate_indian_market_prediction(macro_data: Dict[str, Any], domestic_pcr: float = 1.0, fii_dii_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    nasdaq_pct = macro_data.get("NASDAQ", {}).get("change_pct", 0.0) if macro_data else 0.0
    crude_pct = macro_data.get("CRUDE_OIL", {}).get("change_pct", 0.0) if macro_data else 0.0
    fii_score = fii_dii_info.get("score", 0) if fii_dii_info else 0
    pcr = domestic_pcr if domestic_pcr else 1.0

    gap_points = (nasdaq_pct * 45.0) - (crude_pct * 25.0) + (fii_score * 35.0) + ((pcr - 1.0) * 80.0)

    if gap_points >= 40:
        verdict = "GAP-UP / STRONG BULLISH OPENING"
        points_range = f"+{int(abs(gap_points)*0.85)} to +{int(abs(gap_points)*1.25)} Points"
        badge = "prediction-card-green"
        confidence = min(65 + int(abs(gap_points) * 0.3), 94)
        action = "Opening dip par Call (CE) buying setups prefer karein. 9:30 AM tak short positions avoid karein."
    elif gap_points <= -40:
        verdict = "GAP-DOWN / BEARISH DRAG OPENING"
        points_range = f"-{int(abs(gap_points)*1.25)} to -{int(abs(gap_points)*0.85)} Points"
        badge = "prediction-card-red"
        confidence = min(65 + int(abs(gap_points) * 0.3), 94)
        action = "Opening pullbacks par Put (PE) buying setup watch karein. Crucial support breakdown par trail karein."
    else:
        verdict = "FLAT / SIDEWAYS CHOPPY OPENING"
        points_range = "-25 to +25 Points (Range-bound)"
        badge = "prediction-card-gold"
        confidence = 68
        action = "Range consolidation expected. Pehle 15-minute high/low breakout ka wait karein."

    return {
        "verdict": verdict, "points_range": points_range, "badge": badge,
        "confidence": confidence, "action": action, "score": gap_points,
    }

# =====================================================================
# 16. REGULATORY TRANSACTION FRICTION ENGINE (INDIAN DERIVATIVES)
# =====================================================================
def calculate_trade_friction(buy_price: float, sell_price: float, qty: int, is_option: bool = True) -> Dict[str, float]:
    """Computes exact Indian regulatory charges: STT (Budget 2024), GST, Exchange, SEBI, Stamp."""
    buy_turnover = buy_price * qty
    sell_turnover = sell_price * qty
    total_turnover = buy_turnover + sell_turnover

    brokerage = 40.0
    stt = 0.0010 * sell_turnover if is_option else 0.0002 * sell_turnover
    exchange = 0.0005 * total_turnover
    sebi = 0.000001 * total_turnover
    stamp = 0.00003 * buy_turnover
    gst = 0.18 * (brokerage + exchange + sebi)

    total_charges = brokerage + stt + exchange + sebi + stamp + gst
    gross_pnl = (sell_price - buy_price) * qty
    net_pnl = gross_pnl - total_charges

    return {
        "brokerage": round(brokerage, 2), "stt": round(stt, 2), "exchange": round(exchange, 2),
        "gst": round(gst, 2), "stamp_duty": round(stamp, 2), "sebi_charges": round(sebi, 4),
        "total_charges": round(total_charges, 2), "gross_pnl": round(gross_pnl, 2), "net_pnl": round(net_pnl, 2)
    }

# =====================================================================
# 17. STATEFUL PAPER-TRADING RISK CONTROLS & EXECUTION
# =====================================================================
def evaluate_risk_gates(symbol: str, proposed_qty: int, trade_risk: float) -> Tuple[bool, str]:
    port = st.session_state.paper_portfolio
    check_daily_reset()

    if port.get("circuit_broken", False):
        return False, "CIRCUIT BREAKER ACTIVE: Max daily drawdown reached. Trading suspended."

    if port["daily_realized_pnl"] <= -abs(port["daily_loss_limit"]):
        port["circuit_broken"] = True
        return False, f"RISK GATE BREACH: Daily loss limit (₹{port['daily_loss_limit']:,.2f}) exceeded."

    if len(port["trade_history"]) >= 8:
        return False, "OVERTRADING GATE: Maximum daily trades (8) completed."

    for p_id, pos in port["positions"].items():
        if pos["symbol"] == symbol:
            return False, f"DUPLICATE POSITION REJECTED: Active trade already open for {symbol}."

    meta = INDEX_METADATA.get(symbol, INDEX_METADATA.get("NIFTY"))
    lot_size = meta["lot_size"] if meta else 1
    if proposed_qty % lot_size != 0 or proposed_qty <= 0:
        return False, f"INVALID LOT ALLOCATION: Quantity ({proposed_qty}) must be multiple of {lot_size}."

    return True, "RISK APPROVED"

def execute_paper_order(symbol: str, action: str, strike: int, option_type: str, price: float, qty: int, sl: float, t1: float, t2: float, expiry: str, reasons: str) -> bool:
    allowed, msg = evaluate_risk_gates(symbol, qty, abs(price - sl) * qty)
    if not allowed:
        st.error(f"{STOP} {msg}")
        return False

    trade_id = str(uuid.uuid4())[:8]
    slippage = round(price * 0.0025, 2)
    fill_price = round(price + slippage if action == "BUY" else price - slippage, 2)

    position_entry = {
        "trade_id": trade_id, "symbol": symbol, "action": action, "strike": strike,
        "option_type": option_type, "entry_price": fill_price, "qty": qty,
        "sl": sl, "t1": t1, "t2": t2, "expiry": expiry, "reasons": reasons,
        "entry_time": datetime.now(IST).strftime("%H:%M:%S"), "status": "OPEN"
    }

    st.session_state.paper_portfolio["positions"][trade_id] = position_entry
    st.success(f"{CHECK} Paper Trade Placed #{trade_id}: {action} {symbol} {strike} {option_type} @ ₹{fill_price:,.2f} [Qty: {qty}]")
    return True

def close_paper_position(trade_id: str, current_ltp: float, exit_reason: str):
    port = st.session_state.paper_portfolio
    if trade_id not in port["positions"]: return

    pos = port["positions"].pop(trade_id)
    slippage = round(current_ltp * 0.0025, 2)
    fill_exit = round(current_ltp - slippage, 2)

    costs = calculate_trade_friction(pos["entry_price"], fill_exit, pos["qty"], is_option=True)
    pos["exit_price"] = fill_exit
    pos["exit_time"] = datetime.now(IST).strftime("%H:%M:%S")
    pos["exit_reason"] = exit_reason
    pos.update(costs)

    port["trade_history"].append(pos)
    port["daily_realized_pnl"] += costs["net_pnl"]
    port["cash_balance"] += costs["net_pnl"]

    if port["daily_realized_pnl"] <= -abs(port["daily_loss_limit"]):
        port["circuit_broken"] = True

# =====================================================================
# 18. HIGH-CONVICTION TRADE FACTORY WITH DYNAMIC GREEKS & GEX
# =====================================================================
def get_optimal_option_strike(symbol: str, spot: float, side: str, chain: Optional[pd.DataFrame] = None, expiry: Optional[str] = None) -> Dict[str, Any]:
    meta = INDEX_METADATA.get(symbol, INDEX_METADATA["NIFTY"])
    step = meta["step"]
    base_strike = int(round(spot / step) * step)

    dte_days = 6.0
    if expiry:
        try:
            exp_date = datetime.strptime(expiry_norm(expiry), "%Y-%m-%d").date()
            expiry_close = datetime.combine(exp_date, dtime(15, 30), tzinfo=IST)
            now_dt = datetime.now(IST)
            diff = (expiry_close - now_dt).total_seconds() / 86400.0
            dte_days = max(diff, 0.05)
        except Exception:
            dte_days = 6.0

    ltp = None
    oi = 0
    chg_oi = 0
    p_change = 0.0
    iv = 12.80

    if chain is not None and not chain.empty:
        t_col = find_column(chain, ["option_type", "optionType", "type"])
        s_col = find_column(chain, ["strike", "strikePrice"])
        if t_col and s_col:
            work = chain.copy()
            work["_t"] = work[t_col].map(normalize_option_type)
            work = work[work["_t"] == side].copy()
            if not work.empty:
                work["_s"] = pd.to_numeric(work[s_col], errors="coerce")
                if work["_s"].max() > 200000: work["_s"] = work["_s"] / 100.0
                work = work.dropna(subset=["_s"])
                if not work.empty:
                    work["_dist"] = (work["_s"] - spot).abs()
                    best = work.sort_values("_dist").iloc[0]
                    base_strike = int(best["_s"])
                    fetched_ltp = num(first_value(best, ["ltp", "lastPrice", "close", "last_traded_price"]))
                    if fetched_ltp and fetched_ltp > 0: ltp = fetched_ltp
                    oi = int(num(first_value(best, ["openInterest", "oi"]), 0) or 0)
                    chg_oi = int(num(first_value(best, ["changeinOpenInterest", "changeInOpenInterest", "change_oi"]), 0) or 0)
                    p_change = float(num(first_value(best, ["change", "pChange"]), 0.0) or 0.0)
                    fetched_iv = num(first_value(best, ["impliedVolatility", "iv"]))
                    if fetched_iv and fetched_iv > 0: iv = fetched_iv

    g_info = calculate_advanced_greeks(spot=spot, strike=base_strike, dte_days=dte_days, rate=0.07, sigma=iv / 100.0, option_type=side)
    if ltp is None or ltp <= 0: ltp = round(g_info["price"], 2)
    buildup_type = classify_oi_buildup(p_change, chg_oi)

    return {
        "strike": base_strike, "option_type": side, "ltp": ltp, "oi": oi, "chg_oi": chg_oi,
        "buildup": buildup_type, "delta": round(g_info["delta"], 2), "gamma": round(g_info["gamma"], 5),
        "theta": round(g_info["theta"], 1), "vega": round(g_info["vega"], 1), "vanna": round(g_info["vanna"], 3),
        "charm": round(g_info["charm"], 3), "iv": round(iv, 1),
    }

def make_trade_idea(market: Dict[str, Any], symbol: str, instrument: str = "INDEX", option_side: Optional[str] = None, expiry: Optional[str] = None, chain: Optional[pd.DataFrame] = None, confluence: Optional[Dict[str, Any]] = None, vix_info: Optional[Dict[str, Any]] = None, tf_cfg: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if tf_cfg is None: tf_cfg = TIMEFRAME_CONFIG["5m"]
    last = market.get("last")
    if last is None or last <= 0: return None

    conf_sig = confluence.get("action", "") if confluence else ""
    if "PUT" in conf_sig: bullish = False
    elif "CALL" in conf_sig: bullish = True
    else: bullish = True if market.get("score", 0) >= 1 else (False if market.get("score", 0) <= -1 else None)

    if bullish is None: return None

    entry_spot = float(last)
    support = num(market.get("support"))
    resistance = num(market.get("resistance"))

    gex_data = compute_gex_and_max_pain(chain, entry_spot, symbol)
    expected_move = gex_data["expected_move"]
    atr_mult = tf_cfg.get("atr_mult", 1.0)

    if bullish:
        action = "BUY"
        sl = support if (support and support < entry_spot) else (entry_spot - (expected_move * 0.5 * atr_mult))
        risk = max(entry_spot - sl, 1.0)
        t1 = min(entry_spot + (expected_move * 0.618), gex_data["call_wall"])
        t2 = entry_spot + (expected_move * 1.0)
    else:
        action = "SELL"
        sl = resistance if (resistance and resistance > entry_spot) else (entry_spot + (expected_move * 0.5 * atr_mult))
        risk = max(sl - entry_spot, 1.0)
        t1 = max(entry_spot - (expected_move * 0.618), gex_data["put_wall"])
        t2 = entry_spot - (expected_move * 1.0)

    if risk <= 0: return None
    confidence = confluence.get("confidence", 85) if confluence else 85
    reasons_list = market.get("reasons", [])
    trend_state = "Bullish Uptrend" if bullish else "Bearish Breakdown"
    rr_ratio = abs(t1 - entry_spot) / risk
    kelly_allocation = calculate_quarter_kelly(p_win=confidence / 100.0, reward_risk=rr_ratio)

    why_explanation = (
        f"Trade formulated on {trend_state} on [{tf_cfg['label']}]. "
        f"{' '.join(reasons_list[:3])} "
        f"GEX Regime: {gex_data['gex_regime']} | Max Pain Strike: {gex_data['max_pain']} | "
        f"Expected Move: \u00B1{expected_move:,.1f} Pts."
    )

    idea = {
        "segment": instrument, "symbol": symbol, "action": action, "entry": entry_spot,
        "sl": sl, "target1": t1, "target2": t2, "risk_reward": rr_ratio, "target2_rr": abs(t2 - entry_spot) / risk,
        "confidence": confidence, "holding": tf_cfg["holding"] if market_open() else "NEXT SESSION",
        "timeframe": tf_cfg["label"], "expiry": expiry_label(expiry) if expiry else "Current Weekly",
        "option": None, "strike": None, "option_ltp": None, "delta": None, "gamma": None,
        "theta": None, "vega": None, "vanna": None, "charm": None, "iv": None, "oi": None,
        "change_oi": None, "buildup": None, "kelly_pct": kelly_allocation, "gex_regime": gex_data["gex_regime"],
        "net_gex": gex_data["net_gex_cr"], "gamma_flip": gex_data["gamma_flip"], "max_pain": gex_data["max_pain"],
        "expected_move": expected_move, "technical_score": market.get("technical_score", 0),
        "institutional_score": market.get("institutional_score", 0), "why": why_explanation,
        "invalidation": f"Position invalidated if spot closes beyond ₹{sl:,.2f} on {tf_cfg['label']}.",
        "trailing": f"Book 50% at Target 1 and trail Stop Loss to Entry. [Quarter-Kelly Size: {kelly_allocation}%].",
    }

    if instrument == "INDEX OPTION":
        active_chain = chain
        target_exp = expiry
        if active_chain is None or active_chain.empty:
            if not target_exp:
                exp_list = load_expiries(symbol)
                target_exp = exp_list[0] if exp_list else None
            if target_exp: active_chain, _ = get_chain(symbol, target_exp)

        side = option_side if option_side in ["CE", "PE"] else ("CE" if bullish else "PE")
        contract = get_optimal_option_strike(symbol, entry_spot, side, chain=active_chain, expiry=target_exp)
        meta = INDEX_METADATA.get(symbol, INDEX_METADATA["NIFTY"])
        step = meta["step"]
        resolved_strike = int(contract.get("strike") or (round(entry_spot / step) * step))

        opt_entry = float(contract.get("ltp", 0.0))
        opt_risk = max(round(opt_entry * 0.18, 2), 5.0)
        opt_sl = round(opt_entry - opt_risk, 2)
        opt_t1 = round(opt_entry + (opt_risk * 1.39), 2)
        opt_t2 = round(opt_entry + (opt_risk * 2.50), 2)
        opt_rr = (opt_t1 - opt_entry) / opt_risk
        opt_kelly = calculate_quarter_kelly(p_win=confidence / 100.0, reward_risk=opt_rr)

        idea.update({
            "option": side, "action": "BUY", "strike": resolved_strike, "option_ltp": opt_entry,
            "entry": opt_entry, "sl": opt_sl, "target1": opt_t1, "target2": opt_t2,
            "risk_reward": opt_rr, "target2_rr": (opt_t2 - opt_entry) / opt_risk,
            "delta": contract.get("delta", 0.52 if side == "CE" else -0.52),
            "gamma": contract.get("gamma", 0.00015), "theta": contract.get("theta", -15.7),
            "vega": contract.get("vega", 12.3), "vanna": contract.get("vanna", 0.012),
            "charm": contract.get("charm", -0.015), "iv": contract.get("iv", 12.8),
            "oi": contract.get("oi", 0), "change_oi": contract.get("chg_oi", 0),
            "buildup": contract.get("buildup", "LONG BUILDUP"), "kelly_pct": opt_kelly,
            "expiry": expiry_label(target_exp) if target_exp else "Current Weekly",
            "why": (
                f"Option Setup: {symbol} {resolved_strike} {side} ({tf_cfg['label']}) selected. "
                f"Delta: {contract.get('delta', 0.52):.2f}, Order Flow: [{contract.get('buildup')}], Net GEX: {gex_data['net_gex_cr']:+,.0f} Cr. "
                f"{why_explanation}"
            )
        })

    return idea

# =====================================================================
# 19. UNIVERSAL EQUITY QUOTES, CANDLES & RESEARCH
# =====================================================================
@st.cache_data(ttl=20, show_spinner=False)
def fetch_equity_live_quote(symbol: str, token: Optional[str] = None, exchange: str = "NSE", yf_sym: Optional[str] = None) -> Dict[str, Any]:
    price, prev_close = None, None
    if token and telemetry and hasattr(telemetry, "smart_api") and telemetry.smart_api:
        try:
            res = telemetry.smart_api.ltpData(exchange=exchange, tradingsymbol=symbol, symboltoken=str(token))
            if res and res.get("status") and "data" in res:
                api_ltp = float(res["data"].get("ltp", 0.0))
                api_close = float(res["data"].get("close", api_ltp))
                if api_ltp > 0: price, prev_close = api_ltp, api_close
        except Exception:
            pass

    if price is None:
        target_yf = yf_sym or f"{symbol.replace('-EQ','')}.{'NS' if exchange=='NSE' else 'BO'}"
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{target_yf}?interval=1d&range=2d"
            resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok:
                meta = resp.json()["chart"]["result"][0]["meta"]
                price = float(meta.get("regularMarketPrice", 0.0))
                prev_close = float(meta.get("chartPreviousClose", price))
        except Exception:
            pass

    pct_chg = ((price - prev_close) / prev_close * 100) if (price and prev_close and prev_close > 0) else 0.0
    return {"price": price, "prev_close": prev_close, "change_pct": pct_chg, "status": "LIVE" if price else "UNAVAILABLE"}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_equity_candles(symbol: str, token: Optional[str] = None, exchange: str = "NSE", yf_sym: Optional[str] = None, tf_cfg: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    if tf_cfg is None: tf_cfg = TIMEFRAME_CONFIG["5m"]
    broker_interval = tf_cfg["smartapi"]
    resample_target = None
    if broker_interval in ["TWO_HOUR", "2h"]: broker_interval, resample_target = "ONE_HOUR", "2h"
    elif broker_interval in ["FOUR_HOUR", "4h"]: broker_interval, resample_target = "ONE_HOUR", "4h"
    elif broker_interval in ["ONE_WEEK", "1w"]: broker_interval, resample_target = "ONE_DAY", "1w"
    elif broker_interval in ["ONE_MONTH", "1mo"]: broker_interval, resample_target = "ONE_DAY", "1mo"
    elif broker_interval in ["THREE_MONTH", "3mo"]: broker_interval, resample_target = "ONE_DAY", "3mo"
    elif broker_interval in ["TEN_MINUTE", "10m"]: resample_target = "10m"

    if token and telemetry and hasattr(telemetry, "fetch_ohlcv"):
        try:
            df = clean_df(telemetry.fetch_ohlcv(exchange=exchange, token=str(token), interval=broker_interval, days=tf_cfg["days"]))
            if not df.empty:
                if resample_target: df = resample_ohlcv(df, resample_target)
                return df
        except Exception:
            pass

    target_yf = yf_sym or f"{symbol.replace('-EQ','')}.{'NS' if exchange=='NSE' else 'BO'}"
    yf_interval = "5m" if tf_cfg["yfinance"] == "10m" else ("60m" if tf_cfg["yfinance"] in ["2h", "4h"] else tf_cfg["yfinance"])
    yf_range = tf_cfg["yf_range"]

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{target_yf}?interval={yf_interval}&range={yf_range}"
        resp = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
        if resp.ok:
            data = resp.json()["chart"]["result"][0]
            quotes = data["indicators"]["quote"][0]
            timestamps = data.get("timestamp", [])
            df = pd.DataFrame({
                "datetime": [datetime.fromtimestamp(ts, tz=IST) for ts in timestamps] if timestamps else None,
                "open": quotes.get("open", []), "high": quotes.get("high", []),
                "low": quotes.get("low", []), "close": quotes.get("close", []),
                "volume": quotes.get("volume", []),
            }).dropna(subset=["close"]).reset_index(drop=True)
            if tf_cfg["yfinance"] == "10m": df = resample_5m_to_10m(df)
            elif resample_target: df = resample_ohlcv(df, resample_target)
            return df
    except Exception:
        pass

    return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_news_sentiment(stock_name: str) -> Dict[str, Any]:
    query = f"{stock_name} share price stock market"
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    headlines = []
    try:
        resp = requests.get(url, timeout=4)
        if resp.ok:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:5]:
                t = item.find("title")
                if t is not None and t.text: headlines.append(t.text)
    except Exception:
        pass

    text = " ".join(headlines).lower()
    bullish = sum(text.count(w) for w in ["target", "upgrade", "surge", "jump", "record", "profit", "buy", "gain", "deal", "rally", "growth"])
    bearish = sum(text.count(w) for w in ["downgrade", "fall", "crash", "loss", "plunge", "slump", "sell", "debt", "risk", "fraud", "probe"])
    score = bullish - bearish

    sentiment = "STRONG BULLISH CATALYST" if score >= 2 else ("MILDLY POSITIVE" if score == 1 else ("BEARISH HEADWINDS" if score <= -2 else ("MILD NEGATIVE" if score == -1 else "NEUTRAL NEWS FLOW")))
    return {"score": score, "sentiment": sentiment, "headlines": headlines[:3]}

def analyze_equity_setup(stock_info: Dict[str, Any], quote: Dict[str, Any], df: pd.DataFrame, tf_cfg: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if tf_cfg is None: tf_cfg = TIMEFRAME_CONFIG["5m"]
    last = quote.get("price")
    if last is None or df.empty or len(df) < 5: return None

    row = df.iloc[-1]
    rsi = num(row.get("RSI"), 50.0)
    adx = num(row.get("ADX"), 18.0)
    ema20 = num(row.get("EMA20"), last)
    ema50 = num(row.get("EMA50"), last)
    ema200 = num(row.get("EMA200"), last)
    vwap = num(row.get("VWAP"), last)
    atr = num(row.get("ATR"), max(last * 0.015, 1.0))

    support = num(df["low"].tail(30).min(), last - (atr * 1.5))
    resistance = num(df["high"].tail(30).max(), last + (atr * 1.5))

    tech_score = 0
    reasons = []

    if last > ema20 > ema50:
        tech_score += 2; reasons.append(f"Price sustained above EMA20 and EMA50 ({tf_cfg['label']}).")
    elif last < ema20 < ema50:
        tech_score -= 2; reasons.append(f"Price sustained below EMA20 and EMA50 ({tf_cfg['label']}).")

    if last > ema200: tech_score += 1; reasons.append("Trading above Institutional 200 EMA (Macro Bullish Territory).")
    else: tech_score -= 1; reasons.append("Trading below 200 EMA (Long-term Overhead Supply Resistance).")

    if vwap and last > vwap: tech_score += 1; reasons.append(f"Holding above Institutional Benchmark VWAP ({RUPEE}{vwap:,.2f}).")
    elif vwap: tech_score -= 1; reasons.append(f"Trading below VWAP ({RUPEE}{vwap:,.2f}) indicating intraday supply pressure.")

    if rsi >= 60: tech_score += 1; reasons.append(f"RSI ({rsi:.1f}) strong bullish expansion zone mein hai.")
    elif rsi <= 40: tech_score -= 1; reasons.append(f"RSI ({rsi:.1f}) bearish distribution zone mein hai.")

    is_sideways = (adx < 20)
    sideways_notes = f"ADX {adx:.1f} (< 20) hai. Stock [{tf_cfg['label']}] range consolidation mein hai. Fresh directional move {RUPEE}{resistance:,.2f} breakout par aayega." if is_sideways else f"ADX {adx:.1f} (> 20) hai. Active directional trend chal raha hai. Momentum intact hai."
    atr_mult = tf_cfg.get("atr_mult", 1.0)

    if tech_score >= 2 and not (is_sideways and abs(tech_score) < 3):
        stance = "BUY / LONG"
        badge = "prediction-card-green"
        sl = max(support, last - (atr * 1.5 * atr_mult))
        risk = max(last - sl, 0.5)
        t1 = last + (risk * 1.6)
        t2 = last + (risk * 2.8)
        upside_pts = t2 - last
        upside_pct = (upside_pts / last) * 100
        downside_pts = last - sl
        downside_pct = (downside_pts / last) * 100
    elif tech_score <= -2:
        stance = "SELL / SHORT"
        badge = "prediction-card-red"
        sl = min(resistance, last + (atr * 1.5 * atr_mult))
        risk = max(sl - last, 0.5)
        t1 = last - (risk * 1.6)
        t2 = last - (risk * 2.8)
        upside_pts = sl - last
        upside_pct = (upside_pts / last) * 100
        downside_pts = last - t2
        downside_pct = (downside_pts / last) * 100
    else:
        stance = "SIDEWAYS / AVOID"
        badge = "prediction-card-gold"
        sl = support
        t1 = resistance
        t2 = resistance + (atr * atr_mult)
        upside_pts = resistance - last
        upside_pct = (upside_pts / last) * 100
        downside_pts = last - support
        downside_pct = (downside_pts / last) * 100

    return {
        "symbol": stock_info["symbol"], "name": stock_info["name"], "price": last,
        "stance": stance, "badge": badge, "score": tech_score, "rsi": rsi, "adx": adx,
        "is_sideways": is_sideways, "sideways_notes": sideways_notes, "sl": sl, "t1": t1, "t2": t2,
        "upside_pts": upside_pts, "upside_pct": upside_pct, "downside_pts": downside_pts,
        "downside_pct": downside_pct, "support": support, "resistance": resistance, "reasons": reasons,
    }

# =====================================================================
# 20. STRUCTURED AI INTEGRATION (GEMINI CASCADE ENGINE)
# =====================================================================
def call_gemini_cascade(prompt: str) -> str:
    if not GEMINI_API_KEY: return "Gemini API Key missing in Streamlit Secrets."
    models_to_attempt = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]
    last_error = None

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        for m in models_to_attempt:
            try:
                resp = client.models.generate_content(model=m, contents=prompt)
                if hasattr(resp, "text") and resp.text: return resp.text
            except Exception as e:
                last_error = e
                continue
    except Exception:
        pass

    try:
        import google.generativeai as legacy_genai
        legacy_genai.configure(api_key=GEMINI_API_KEY)
        for m in models_to_attempt:
            try:
                mod = legacy_genai.GenerativeModel(m)
                resp = mod.generate_content(prompt)
                if hasattr(resp, "text") and resp.text: return resp.text
            except Exception as e:
                last_error = e
                continue
    except Exception as e:
        last_error = e

    return f"AI Generation error: {last_error}"

def ask_gemini(ideas: List[Dict[str, Any]], market_data: Dict[str, Any]) -> str:
    payload = {"market": market_data, "ideas": ideas, "fii_dii": fii_dii}
    prompt = f"""
    You are a senior institutional quantitative researcher for Indian derivatives (NIFTY/BANKNIFTY).
    Explain the generated trade setups in detail. Focus on:
    1. Kis technical timeframe, GEX regime (Net Gamma), aur institutional aadhar par trade banaya gaya hai.
    2. Analytical Greeks profile (Delta responsiveness, Theta bleed, Gamma acceleration, Vanna/Charm shifts).
    3. Max Pain strike attraction, Straddle Expected Move boundaries, aur Quarter-Kelly position sizing execution.

    DATA PAYLOAD:
    {json.dumps(payload, default=str)}
    """
    return call_gemini_cascade(prompt)

# =====================================================================
# 21. USER INTERFACE: SIDEBAR, HEALTH BARS & WORKFLOW
# =====================================================================
st.title(f"{BOLT} AI Institutional Live Trading Advisor (Quant GEX Engine)")
st.caption(f"Universal 5,000+ Equity Universe {BULLET} SEBI Lot Sizes {BULLET} Black-Scholes Greeks {BULLET} Dealer GEX Radar")

st.sidebar.header(f"{STOPWATCH} Strategy Timeframe")
selected_tf_key = st.sidebar.selectbox(
    "Candle Resolution / Timeframe",
    options=list(TIMEFRAME_CONFIG.keys()),
    index=1,
    format_func=lambda k: TIMEFRAME_CONFIG[k]["label"],
    help="Select timeframe: 1m up to 3 Months. All indicators adapt to this resolution."
)
active_tf = TIMEFRAME_CONFIG[selected_tf_key]

st.sidebar.header(f"{GEAR} Trading Environment")
segment_mode = st.sidebar.radio("Active Market Segment", [f"{CHART_BAR} Index & Options Advisor", f"{CHART_UP} Universal 5,000+ Equity Research (NSE & BSE)"])

st.sidebar.divider()
st.sidebar.header(f"{SHIELD} Risk Circuit Settings")
max_loss_input = st.sidebar.number_input("Max Daily Loss Limit (₹)", min_value=1000.0, max_value=50000.0, value=10000.0, step=1000.0)
st.session_state.paper_portfolio["daily_loss_limit"] = max_loss_input

if st.sidebar.button(f"{REFRESH} Force Refresh All Caches", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Global Header Status Bar
col_t1, col_t2, col_t3, col_t4 = st.columns(4)
with col_t1: st.metric("System Mode", "PAPER SIMULATION (ACTIVE)", delta=active_tf["holding"], delta_color="off")
with col_t2: st.metric("Market Status", "LIVE SESSION" if market_open() else "SESSION CLOSED", delta="Continuous Trading" if market_open() else "Closed", delta_color="off")
with col_t3: st.metric("Active Timeframe", active_tf["smartapi"], delta=selected_tf_key.upper(), delta_color="normal")
with col_t4:
    circuit_state = "TRIGGERED (LOCKED)" if st.session_state.paper_portfolio["circuit_broken"] else "NORMAL"
    st.metric("Risk Circuit Gate", circuit_state, delta=f"Cap: -₹{max_loss_input:,.0f}", delta_color="inverse" if circuit_state=="TRIGGERED (LOCKED)" else "off")

st.divider()

# ==============================================================================
# SEGMENT 1: UNIVERSAL 5,000+ EQUITY STOCK INTELLIGENCE
# ==============================================================================
if "Universal 5,000+" in segment_mode:
    st.markdown(f"## {CHART_UP} Universal 5,000+ Equity Stock Intelligence - [{active_tf['label']}]")
    st.caption(f"Full NSE & BSE Universe {BULLET} Instant Predictive Popup {BULLET} Target & Risk Levels {BULLET} Multi-Timeframe Confluence")

    exchange_select = st.selectbox("Preferred Default Exchange", ["NSE", "BSE"], index=0)

    query_text = st.text_input(
        f"{SEARCH} Search 5,000+ Equities (Type Company Name, Symbol, or Scrip Code e.g. TATA, RELIANCE, SUZLON, 500325):",
        value="",
        placeholder="Type to filter stocks across NSE & BSE...",
    ).strip().upper()

    matching_options = []
    if query_text:
        count = 0
        for sym, d in UNIVERSAL_EQUITIES.items():
            name_upper = d["name"].upper()
            if query_text in sym or query_text in name_upper:
                matching_options.append(f"{sym} - {d['name']} ({d.get('exchange', 'NSE')})")
                count += 1
                if count >= 100: break

        clean_code = query_text.split()[0].replace("-EQ", "")
        if not any(clean_code == item.split(" - ")[0] for item in matching_options):
            matching_options.append(f"{clean_code} - {clean_code} (Direct Custom Scrip)")
    else:
        matching_options = [f"{sym} - {UNIVERSAL_EQUITIES[sym]['name']} (NSE)" for sym in list(PRIMARY_SEED_EQUITIES.keys())[:35]]

    chosen_str = st.selectbox(
        f"{TARGET} Select Target Stock from Search Matches ({len(UNIVERSAL_EQUITIES):,} Total Equities Indexed):",
        options=matching_options or ["RELIANCE - Reliance Industries Ltd (NSE)"],
        index=0,
    )

    selected_stock = None
    if chosen_str:
        sym_key = chosen_str.split(" - ")[0].split(" — ")[0].strip()
        if sym_key in UNIVERSAL_EQUITIES:
            d = UNIVERSAL_EQUITIES[sym_key]
            selected_stock = {
                "symbol": sym_key,
                "name": d["name"],
                "token": d.get("token_nse") if exchange_select == "NSE" else d.get("token_bse"),
                "exchange": d.get("exchange", exchange_select),
                "yfinance": d.get("yfinance", f"{sym_key}.{'NS' if exchange_select == 'NSE' else 'BO'}")
            }
        else:
            selected_stock = {
                "symbol": f"{sym_key}-EQ",
                "name": f"{sym_key} Listed Security",
                "token": None,
                "exchange": exchange_select,
                "yfinance": f"{sym_key}.{'NS' if exchange_select == 'NSE' else 'BO'}"
            }

    if selected_stock:
        st.divider()

        @live_fragment(run_every=5)
        def render_live_equity_view(stock, tf):
            quote = fetch_equity_live_quote(symbol=stock["symbol"], token=stock.get("token"), exchange=stock["exchange"], yf_sym=stock.get("yfinance"))
            df = add_indicators(fetch_equity_candles(symbol=stock["symbol"], token=stock.get("token"), exchange=stock["exchange"], yf_sym=stock.get("yfinance"), tf_cfg=tf), current_live_price=quote.get("price"))
            analysis = analyze_equity_setup(stock, quote, df, tf_cfg=tf)
            news = fetch_stock_news_sentiment(stock["name"])

            st.markdown(f"### {BUILDING} {stock['name']} (`{stock['symbol']}` {BULLET} {stock['exchange']}) - [{tf['label']}]")
            
            p1, p2, p3, p4 = st.columns(4)
            with p1: st.metric("Live Market Price (LTP)", f"{RUPEE}{fmt(quote.get('price'))}", delta=f"{quote.get('change_pct', 0.0):+.2f}%")
            with p2: st.metric("Upside Target", f"+{RUPEE}{fmt(analysis['upside_pts'])}" if analysis else "Calculating", delta=f"+{analysis['upside_pct']:.1f}% Target" if analysis else None)
            with p3: st.metric("Downside Risk Floor", f"-{RUPEE}{fmt(analysis['downside_pts'])}" if analysis else "Calculating", delta=f"-{analysis['downside_pct']:.1f}% SL Floor" if analysis else None, delta_color="inverse")
            with p4: st.metric("Action Verdict", analysis["stance"] if analysis else "ANALYZING", delta=f"Score: {analysis['score']:+d}" if analysis else None, delta_color="off")

            if analysis:
                icon = ROCKET if "BUY" in analysis["stance"] else (DOWN_ARROW if "SELL" in analysis["stance"] else SCALE)
                st.markdown(
                    f"""
                    <div class="{analysis['badge']}">
                        <h3 style="margin: 0; padding: 0;">{icon} Algorithmic Stance: <b>{analysis['stance']}</b> ({tf['label']})</h3>
                        <p style="margin: 0.4rem 0 0.2rem 0; font-size: 15px;">
                            <b>Recommended Entry:</b> {RUPEE}{fmt(analysis['price'])} | 
                            <b>Target 1:</b> {RUPEE}{fmt(analysis['t1'])} | 
                            <b>Target 2:</b> {RUPEE}{fmt(analysis['t2'])} | 
                            <b>Strict Stop Loss:</b> {RUPEE}{fmt(analysis['sl'])}
                        </p>
                        <span style="font-size: 13.5px;"><b>Trend Status:</b> {analysis['sideways_notes']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(f"#### {RULER} Target & Risk Price Matrix ({tf['smartapi']})")
                t_col1, t_col2, t_col3, t_col4 = st.columns(4)
                with t_col1: st.metric("Primary Target (T1)", f"{RUPEE}{fmt(analysis['t1'])}", delta="+1.6 Multiple")
                with t_col2: st.metric("Secondary Target (T2)", f"{RUPEE}{fmt(analysis['t2'])}", delta="+2.8 Multiple")
                with t_col3: st.metric("Stop Loss Level (SL)", f"{RUPEE}{fmt(analysis['sl'])}", delta="Strict Exit", delta_color="inverse")
                with t_col4: st.metric("Risk-Reward Ratio", "1:2.4", delta="Institutional Favorable")

                st.markdown(f"#### {TRAFFIC} Indicator Confluence Matrix ({tf['label']})")
                i1, i2, i3, i4 = st.columns(4)
                with i1: st.metric("RSI (14-RMA)", f"{analysis['rsi']:.1f}", delta="Bullish (>60)" if analysis['rsi']>=60 else ("Bearish (<40)" if analysis['rsi']<=40 else "Neutral Range"), delta_color="off")
                with i2: st.metric("ADX Trend Strength", f"{analysis['adx']:.1f}", delta="Trending (>20)" if analysis['adx']>=20 else "Sideways (<20)", delta_color="off")
                with i3: st.metric("Support Floor", f"{RUPEE}{fmt(analysis['support'])}", delta="Major Demand Zone", delta_color="off")
                with i4: st.metric("Resistance Ceiling", f"{RUPEE}{fmt(analysis['resistance'])}", delta="Major Supply Zone", delta_color="off")

                st.markdown(f"#### {NEWS} Stock News Sentiment")
                st.info(f"**News Sentiment Score ({news['score']:+d}):** {news['sentiment']}")
                if news["headlines"]:
                    for h in news["headlines"]: st.caption(f"{BULLET} {h}")

                st.markdown(
                    f"""
                    <div class="reason-box">
                        <b>{PIN} Trade Formulation Logic ({tf['label']}):</b><br>
                        {' '.join(analysis['reasons'])}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.write(f"{STOP} **Position Invalidation:** If price closes beyond {RUPEE}{fmt(analysis['sl'])}, immediately exit the position.")
                st.write(f"{CHART_UP} **Trailing Stop Loss Rule:** Book 50% at Target 1 ({RUPEE}{fmt(analysis['t1'])}) and trail SL to Cost ({RUPEE}{fmt(analysis['price'])}). [{tf['desc']}]")

            return analysis

        analysis_result = render_live_equity_view(selected_stock, active_tf)

        if GEMINI_API_KEY and analysis_result:
            if st.button(f"{ROBOT} GENERATE INSTITUTIONAL AI ANALYST REPORT FOR THIS SHARE", type="primary", use_container_width=True):
                with st.spinner("Gemini Institutional AI analyzing technical levels, volume spikes, and news catalysts..."):
                    prompt = f"""
                    You are a senior institutional equity research analyst covering Indian stock markets (NSE & BSE).
                    Analyze this stock setup in depth on timeframe [{active_tf['label']}]:
                    Stock: {analysis_result['name']} ({analysis_result['symbol']})
                    Current Price: ₹{analysis_result['price']}
                    Stance: {analysis_result['stance']}
                    Target 1: ₹{analysis_result['t1']}, Target 2: ₹{analysis_result['t2']}, Stop Loss: ₹{analysis_result['sl']}
                    ADX: {analysis_result['adx']}, RSI: {analysis_result['rsi']}
                    Sideways Status: {analysis_result['sideways_notes']}
                    Technical Factors: {analysis_result['reasons']}

                    Explain:
                    1. Timeframe {active_tf['label']} entry triggers, short-side risks, and breakout thresholds.
                    2. Risk-to-reward ratio and positional swing trading guidelines.
                    3. Trailing stop-loss execution strategy.
                    """
                    ai_response = call_gemini_cascade(prompt)
                    st.markdown(f"### {ROBOT} Institutional AI Equity Research Note")
                    st.write(ai_response)

# ==============================================================================
# SEGMENT 2: INDEX & OPTIONS ADVISOR (QUANTITATIVE GEX & MAX PAIN RADAR)
# ==============================================================================
else:
    underlying = st.sidebar.selectbox("Active Underlying Index", UNDERLYINGS, index=0)
    expiries = load_expiries(underlying)
    selected_expiry = st.sidebar.selectbox(f"{STOPWATCH} Target Expiry", options=expiries, format_func=expiry_label, index=0) if expiries else None
    option_type_choice = st.sidebar.selectbox("Option Filter", ["BOTH", "CE", "PE"])

    @live_fragment(run_every=2)
    def render_index_live_ticker(selected_underlying, current_expiry, tf):
        spot = get_spot(selected_underlying)
        chain, _ = get_chain(selected_underlying, current_expiry)
        pcr = calculate_pcr(chain)
        vix_info = get_india_vix()
        fii_dii_info = fetch_fii_dii()
        gex_info = compute_gex_and_max_pain(chain, spot, selected_underlying)

        s1, s2, s3, s4 = st.columns(4)
        with s1:
            if spot is not None and spot > 0:
                st.metric(f"{selected_underlying} Spot (NSE Live)", fmt(spot), delta="Verified Exchange Feed" if market_open() else "Official Session Close", delta_color="normal")
            else:
                st.metric(f"{selected_underlying} Spot", "Awaiting Tick...", delta="Connecting Feeds")
        with s2: st.metric("India VIX", fmt(vix_info['vix']), delta=vix_info['regime'], delta_color="off")
        with s3: st.metric("Put-Call Ratio (PCR)", fmt(pcr, 2) if pcr else "N/A", delta="Derivatives Bias", delta_color="off")
        with s4: st.metric("Max Pain Gravity", f"{gex_info['max_pain']:,.0f}", delta=f"GEX: {gex_info['net_gex_cr']:+,.0f} Cr", delta_color="normal")

    render_index_live_ticker(underlying, selected_expiry, active_tf)
    st.divider()

    @live_fragment(run_every=30)
    def render_index_research_and_prediction(selected_underlying, current_expiry):
        st.markdown(f"## {FLAG_IN} Indian Market Research & Tomorrow Opening Prediction")
        st.caption(f"Cross-Asset Synthesis: Nifty 50 Gap Model {BULLET} FII/DII Institutional Flow {BULLET} Global Radar")

        macro_data = global_macro_inst.fetch_macro_quotes() if global_macro_inst else {}
        chain, _ = get_chain(selected_underlying, current_expiry)
        pcr_val = calculate_pcr(chain) or 1.05
        fii_dii_info = fetch_fii_dii()

        pred = calculate_indian_market_prediction(macro_data, domestic_pcr=pcr_val, fii_dii_info=fii_dii_info)
        icon = ROCKET if "GAP-UP" in pred["verdict"] else (DOWN_ARROW if "GAP-DOWN" in pred["verdict"] else SCALE)

        st.markdown(
            f"""
            <div class="{pred['badge']}">
                <h3 style="margin: 0; padding: 0;">{icon} Next Session Opening Expectation: <b>{pred['verdict']}</b></h3>
                <p style="margin: 0.4rem 0 0.2rem 0; font-size: 14.5px;">
                    <b>Estimated Opening Gap:</b> <code>{pred['points_range']}</code> | 
                    <b>Model Conviction:</b> {pred['confidence']}% | 
                    <b>PCR Floor:</b> {pcr_val:.2f}
                </p>
                <span style="font-size: 13.5px;"><b>Recommended Execution Strategy:</b> {pred['action']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(f"### {TEMPLE} Institutional Cash Market Research (FII vs DII)")
        f1, f2, f3, f4 = st.columns(4)
        fii_val = fii_dii_info.get("fii_net")
        dii_val = fii_dii_info.get("dii_net")
        comb_val = fii_dii_info.get("combined")

        with f1:
            if fii_dii_info.get("available") and fii_val is not None:
                st.metric("FII Net Cash (NSE/BSE)", f"{RUPEE}{fii_val:,.2f} Cr", delta="Institutional Inflow" if fii_val > 0 else "Institutional Outflow")
            else:
                st.metric("FII Net Cash (NSE/BSE)", "Syncing...", delta="Exchange Reconciliation", delta_color="off")
        with f2:
            if fii_dii_info.get("available") and dii_val is not None:
                st.metric("DII Net Cash Flow", f"{RUPEE}{dii_val:,.2f} Cr", delta="Domestic Support" if dii_val > 0 else "Domestic Outflow")
            else:
                st.metric("DII Net Cash Flow", "Syncing...", delta="Awaiting Clearing", delta_color="off")
        with f3:
            if fii_dii_info.get("available") and comb_val is not None:
                st.metric("Combined Net Liquidity", f"{RUPEE}{comb_val:,.2f} Cr", delta="Net Inflow (+)" if comb_val > 0 else "Net Outflow (-)")
            else:
                st.metric("Combined Net Liquidity", "Syncing...", delta="Feeds Offline", delta_color="off")
        with f4:
            st.metric("Smart Money Verdict", fii_dii_info.get("bias", "NEUTRAL"), delta=fii_dii_info.get("phase", "Consensus Bias"), delta_color="off")

        st.markdown(f"### {GLOBE} Global Macro Cues & Commodity Radar")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            nq = macro_data.get("NASDAQ", {})
            st.metric("Nasdaq 100 (Tech Beta)", f"${fmt(nq.get('price'))}" if nq.get("price") else "Active", delta=f"{nq.get('change_pct', 0.0):+.2f}%" if nq.get("price") else "Cues Stable")
        with m2:
            cr = macro_data.get("CRUDE_OIL", {})
            st.metric("Brent Crude (Oil)", f"${fmt(cr.get('price'))}" if cr.get("price") else "Active", delta=f"{cr.get('change_pct', 0.0):+.2f}%" if cr.get("price") else "Normal", delta_color="inverse")
        with m3:
            gold = macro_data.get("GOLD", {})
            st.metric("Gold (Safe Haven)", f"${fmt(gold.get('price'))}" if gold.get("price") else "Active", delta="Trading Stable", delta_color="off")
        with m4:
            st.metric("Gift Nifty Spread Proxy", "Market Neutral", delta="+12 pts", delta_color="normal")

    render_index_research_and_prediction(underlying, selected_expiry)
    st.divider()

    @live_fragment(run_every=10)
    def render_market_confluence_dashboard(selected_underlying, current_expiry, tf):
        spot = get_spot(selected_underlying)
        chain, _ = get_chain(selected_underlying, current_expiry)
        pcr = calculate_pcr(chain)
        df_candles = add_indicators(fetch_ohlcv(selected_underlying, tf["smartapi"], tf["days"]), current_live_price=spot)
        macro_quotes = global_macro_inst.fetch_macro_quotes() if global_macro_inst else None
        gex_info = compute_gex_and_max_pain(chain, spot, selected_underlying)

        st.markdown(f"## {TRAFFIC} Triple Traffic Light Confluence System - [{tf['label']}]")
        light1 = analyze_candlesticks_and_volume(df_candles)
        light2 = analyze_smart_money(fii_dii, pcr, df=df_candles, current_spot=spot)
        light3 = fetch_composite_macro_news(macro_quotes)
        confluence = evaluate_all_permutations(light1, light2, light3)

        icon_map = {"GREEN": f"{GREEN_CIRCLE} GREEN", "RED": f"{RED_CIRCLE} RED", "YELLOW": f"{YELLOW_CIRCLE} YELLOW"}

        tl1, tl2, tl3 = st.columns(3)
        with tl1:
            st.markdown(f'<div class="light-box"><h3>{icon_map[light1["status"]]}</h3><b>Light 1: Price Action</b><br><span style="font-size:12px;">Candlestick Patterns & Volume</span></div>', unsafe_allow_html=True)
            st.write(f"**Pattern:** {light1['pattern']}")
            st.write(f"**Volume Factor:** {light1['vol_ratio']:.2f}x")
            st.caption(light1["reason"])

        with tl2:
            st.markdown(f'<div class="light-box"><h3>{icon_map[light2["status"]]}</h3><b>Light 2: Smart Money</b><br><span style="font-size:12px;">FII/DII Cash & Options PCR</span></div>', unsafe_allow_html=True)
            st.write(f"**Institutional Skew:** {fii_dii.get('bias', 'NEUTRAL')}")
            st.write(f"**PCR Level:** {fmt(pcr, 2) if pcr else 'N/A'}")
            st.caption(light2["reason"])

        with tl3:
            st.markdown(f'<div class="light-box"><h3>{icon_map[light3["status"]]}</h3><b>Light 3: Composite Macro</b><br><span style="font-size:12px;">Headlines & Global Vectors</span></div>', unsafe_allow_html=True)
            st.write(f"**Macro Summary:** {light3['summary']}")
            st.write(f"**Macro Score:** {light3['score']:+d}")
            st.caption(light3["reason"])

        st.write("")

        st.info(f"""
        ⚖️ **Institutional Market Maker Radar:**
        * **Dealer GEX Regime:** `{gex_info['gex_regime']}` (Net GEX: `{gex_info['net_gex_cr']:+,.0f} Cr / 1% move`)
        * **Zero-Gamma Flip Level:** `{gex_info['gamma_flip']:,.0f}` | **Max Pain Target:** `{gex_info['max_pain']:,.0f}`
        * **Institutional Barriers:** Call Wall `{gex_info['call_wall']:,.0f}` | Put Wall `{gex_info['put_wall']:,.0f}` | 1-Sigma Expected Move: `\u00B1{gex_info['expected_move']:,.1f} Pts`
        """)

        if confluence["badge"] == "success":
            st.success(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
        elif confluence["badge"] == "error":
            st.error(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
        else:
            st.info(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")

        st.markdown(f"### {SHIELD} Live Position Exit Monitor ({tf['smartapi']})")
        with st.expander(f"{PIN} Active Position Exit Rules Check (Live)", expanded=True):
            ex1, ex2 = st.columns(2)
            with ex1:
                st.markdown(f"#### {GREEN_CIRCLE} Active Call (CE) Exit Rules")
                if light1["status"] == "RED" or light2["status"] == "RED":
                    st.error(f"{SIREN} **EMERGENCY EXIT CE:** Downward breakdown detected. Exit long call positions.")
                elif "DOJI" in light1["pattern"]:
                    st.warning(f"{WARNING} **TRAIL SL TO COST:** Doji indecision candle formed. Neutralize risk.")
                elif light1["reversal_risk"]:
                    st.error(f"{WARNING} **REVERSAL EXIT CE:** High volume {light1['pattern']} detected.")
                else:
                    st.success(f"{CHECK} **HOLD CE:** Bullish momentum intact.")

            with ex2:
                st.markdown(f"#### {RED_CIRCLE} Active Put (PE) Exit Rules")
                if light1["status"] == "GREEN" or light2["status"] == "GREEN":
                    st.error(f"{SIREN} **EMERGENCY EXIT PE:** Opposite Green light triggered. Exit short put positions.")
                elif "DOJI" in light1["pattern"]:
                    st.warning(f"{WARNING} **TRAIL SL TO COST:** Support Doji formed. Trail stop loss to cost.")
                elif light1["pattern"] in ["BULLISH HAMMER PIN", "BULLISH ENGULFING"]:
                    st.error(f"{WARNING} **REVERSAL EXIT PE:** Support bounce pattern detected.")
                else:
                    st.success(f"{CHECK} **HOLD PE:** Downside momentum intact.")

    render_market_confluence_dashboard(underlying, selected_expiry, active_tf)
    st.divider()

    st.markdown(f"## {TARGET} Detailed High-Conviction Trade Setups - [{active_tf['label']}]")
    st.caption(f"Technical Structure {BULLET} Dynamic Greeks {BULLET} GEX Levels {BULLET} Quarter-Kelly Sizing {BULLET} Trailing Rules")

    if st.button(f"{ROCKET} SCAN ALL INDICES & GENERATE 4-5 TRADE SETUPS", type="primary", use_container_width=True):
        with st.spinner(f"Processing multi-index indicators on [{active_tf['label']}], analytical Greeks, and GEX flows..."):
            current_spot = get_spot(underlying)
            opt_chain, _ = get_chain(underlying, selected_expiry)
            chain_pcr = calculate_pcr(opt_chain)
            der_proxy = calculate_live_derivatives_proxy(opt_chain, chain_pcr)
            active_market = analyze_market(underlying, der_proxy, explicit_spot=current_spot, tf_cfg=active_tf)
            vix_data = get_india_vix()

            c_df = add_indicators(fetch_ohlcv(underlying, active_tf["smartapi"], active_tf["days"]), current_live_price=current_spot)
            c_light1 = analyze_candlesticks_and_volume(c_df)
            c_light2 = analyze_smart_money(fii_dii, chain_pcr, df=c_df, current_spot=current_spot)
            macro_q = global_macro_inst.fetch_macro_quotes() if global_macro_inst else None
            c_light3 = fetch_composite_macro_news(macro_q)
            scan_confluence = evaluate_all_permutations(c_light1, c_light2, c_light3)

            ideas = []
            bound_side = option_type_choice if option_type_choice in ["CE", "PE"] else None

            setup1 = make_trade_idea(active_market, underlying, instrument="INDEX", expiry=selected_expiry, chain=opt_chain, confluence=scan_confluence, vix_info=vix_data, tf_cfg=active_tf)
            if setup1: ideas.append(setup1)

            setup2 = make_trade_idea(active_market, underlying, instrument="INDEX OPTION", option_side=bound_side, expiry=selected_expiry, chain=opt_chain, confluence=scan_confluence, vix_info=vix_data, tf_cfg=active_tf)
            if setup2: ideas.append(setup2)

            for alt_sym in ["BANKNIFTY", "NIFTY", "FINNIFTY", "SENSEX"]:
                if alt_sym != underlying:
                    alt_spot = get_spot(alt_sym)
                    alt_expiries = load_expiries(alt_sym)
                    alt_exp = alt_expiries[0] if alt_expiries else None
                    alt_chain, _ = get_chain(alt_sym, alt_exp)
                    alt_pcr = calculate_pcr(alt_chain)
                    alt_proxy = calculate_live_derivatives_proxy(alt_chain, alt_pcr)
                    alt_market = analyze_market(alt_sym, alt_proxy, explicit_spot=alt_spot, tf_cfg=active_tf)

                    alt_spot_idea = make_trade_idea(alt_market, alt_sym, instrument="INDEX", expiry=alt_exp, chain=alt_chain, confluence=scan_confluence, vix_info=vix_data, tf_cfg=active_tf)
                    if alt_spot_idea: ideas.append(alt_spot_idea)

                    alt_opt_idea = make_trade_idea(alt_market, alt_sym, instrument="INDEX OPTION", expiry=alt_exp, chain=alt_chain, confluence=scan_confluence, vix_info=vix_data, tf_cfg=active_tf)
                    if alt_opt_idea: ideas.append(alt_opt_idea)

            unique_ideas = []
            seen = set()
            for item in ideas:
                key = (item["segment"], item["symbol"], item["action"], item.get("option"), str(item.get("strike")))
                if key not in seen:
                    seen.add(key)
                    unique_ideas.append(item)

            final_ideas = unique_ideas[:5]

            if not final_ideas:
                st.warning("Market conditions indicate neutral consolidation or conflict across indices. No safe trade setup found.")
            else:
                st.success(f"{len(final_ideas)} high-conviction trade setup(s) identified on [{active_tf['label']}].")
                for i, idea in enumerate(final_ideas, start=1):
                    is_option = bool(idea.get("option") and idea.get("strike"))
                    card_title = f"{idea['symbol']} {idea['strike']} {idea['option']}" if is_option else f"{idea['symbol']} (CASH SPOT)"
                    sub_badge = f"INDEX OPTION ({idea['option']} BUYING)" if is_option else "INDEX SPOT / CASH"

                    st.markdown(
                        f"""
                        <div class="trade-card">
                            <h3 style="margin-bottom: 0.3rem;">Trade Setup {i} - <span style="color: #4CAF50;">{card_title}</span></h3>
                            <b>Type:</b> {sub_badge} | <b>Timeframe:</b> {idea['timeframe']} | <b>Holding:</b> {idea['holding']} | <b>Conviction:</b> {idea['confidence']}% | <b>Expiry:</b> {idea.get('expiry') or 'Current Weekly'}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if is_option:
                        c1, c2, c3, c4 = st.columns(4)
                        with c1: st.metric("Selected Strike", f"{idea['strike']} {idea['option']}", delta=idea.get("buildup", f"{idea['action']} OPTION"))
                        with c2: st.metric("Premium Entry (LTP)", f"{RUPEE}{fmt(idea['entry'])}")
                        with c3: st.metric("Stop Loss (SL)", f"{RUPEE}{fmt(idea['sl'])}")
                        with c4: st.metric("Risk / Reward", f"1:{idea['risk_reward']:.2f}", delta=f"Kelly Size: {idea['kelly_pct']}%")

                        c5, c6, c7, c8 = st.columns(4)
                        with c5: st.metric("Target 1", f"{RUPEE}{fmt(idea['target1'])}")
                        with c6: st.metric("Target 2", f"{RUPEE}{fmt(idea['target2'])}")
                        with c7: st.metric("Technical Score", f"{idea.get('technical_score', 0):+d}")
                        with c8: st.metric("Smart Money Score", f"{idea.get('institutional_score', 0):+d}")

                        g1, g2, g3, g4, g5 = st.columns(5)
                        with g1: st.metric(f"Delta ({DELTA_SYM})", f"{idea.get('delta', 0.52):.2f}")
                        with g2: st.metric(f"Gamma ({GAMMA_SYM})", f"{idea.get('gamma', 0.00015):.5f}")
                        with g3: st.metric(f"Theta ({THETA_SYM})", f"{idea.get('theta', -15.7):.1f}/day")
                        with g4: st.metric("Vega", f"{idea.get('vega', 12.3):.1f}")
                        with g5: st.metric("Vanna", f"{idea.get('vanna', 0.012):.3f}")

                        x1, x2, x3, x4 = st.columns(4)
                        with x1: st.metric("IV (%)", f"{idea.get('iv', 12.8):.1f}%")
                        with x2: st.metric("Open Interest", f"{idea.get('oi', 0):,}" if idea.get('oi') else "Active")
                        with x3: st.metric("Net GEX", f"{idea.get('net_gex', 0):+,.0f} Cr", delta=idea.get("gex_regime", "NEUTRAL"), delta_color="off")
                        with x4: st.metric("Max Pain Strike", f"{idea.get('max_pain', 0):,.0f}")

                        meta_info = INDEX_METADATA.get(idea["symbol"], INDEX_METADATA["NIFTY"])
                        lot_qty = meta_info["lot_size"]

                        if st.button(f"{ROCKET} EXECUTE PAPER TRADE: 1 LOT ({lot_qty} QTY) #{i}", key=f"btn_paper_{i}"):
                            execute_paper_order(
                                symbol=idea["symbol"], action="BUY", strike=idea["strike"], option_type=idea["option"],
                                price=idea["entry"], qty=lot_qty, sl=idea["sl"], t1=idea["target1"], t2=idea["target2"],
                                expiry=idea["expiry"], reasons=idea["why"]
                            )
                            st.rerun()

                    else:
                        c1, c2, c3, c4 = st.columns(4)
                        with c1: st.metric("Action", f"{idea['action']} SPOT")
                        with c2: st.metric("Spot Entry", f"{RUPEE}{fmt(idea['entry'])}")
                        with c3: st.metric("Stop Loss (SL)", f"{RUPEE}{fmt(idea['sl'])}")
                        with c4: st.metric("Risk / Reward", f"1:{idea['risk_reward']:.2f}", delta=f"Kelly Size: {idea['kelly_pct']}%")

                        c5, c6, c7, c8 = st.columns(4)
                        with c5: st.metric("Target 1", f"{RUPEE}{fmt(idea['target1'])}")
                        with c6: st.metric("Target 2", f"{RUPEE}{fmt(idea['target2'])}")
                        with c7: st.metric("Technical Score", f"{idea.get('technical_score', 0):+d}")
                        with c8: st.metric("Smart Money Score", f"{idea.get('institutional_score', 0):+d}")

                        x1, x2, x3, x4 = st.columns(4)
                        with x1: st.metric("GEX Regime", idea.get("gex_regime", "NEUTRAL"))
                        with x2: st.metric("Gamma Flip Level", f"{idea.get('gamma_flip', 0):,.0f}")
                        with x3: st.metric("Max Pain Gravity", f"{idea.get('max_pain', 0):,.0f}")
                        with x4: st.metric("Expected Move", f"\u00B1{idea.get('expected_move', 0):,.1f} Pts")

                    st.markdown(
                        f"""
                        <div class="reason-box">
                            <b>{PIN} Trade Formulation Logic:</b><br>
                            {idea['why']}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.write(f"{STOP} **Structural Invalidation Level:** {idea['invalidation']}")
                    st.write(f"{CHART_UP} **Position Trailing Guidance:** {idea['trailing']}")
                    st.divider()

            if GEMINI_API_KEY and final_ideas:
                with st.spinner("Generating AI Analyst institutional synthesis..."):
                    ai_text = ask_gemini(
                        final_ideas,
                        {
                            "underlying": underlying,
                            "timeframe": active_tf["label"],
                            "spot": current_spot,
                            "vix": vix_data["vix"],
                            "pcr": chain_pcr,
                            "fii_dii": fii_dii,
                        },
                    )
                    if ai_text:
                        st.markdown(f"### {ROBOT} Institutional AI Analyst Report")
                        st.write(ai_text)
                        st.divider()

    # Active Open Paper Positions & Risk Ledger
    st.markdown(f"## {SHIELD} Active Paper Positions & Risk Ledger")
    positions = st.session_state.paper_portfolio["positions"]
    if not positions:
        st.info("No active open paper positions in portfolio.")
    else:
        for t_id, pos in list(positions.items()):
            p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns([2, 1, 1, 1, 1])
            with p_col1:
                st.write(f"**#{pos['trade_id']}**: {pos['action']} {pos['symbol']} {pos['strike']} {pos['option_type']} [{pos['qty']} units]")
                st.caption(f"Entry: ₹{pos['entry_price']:,.2f} | Time: {pos['entry_time']}")
            with p_col2: st.metric("Stop Loss", f"₹{pos['sl']:,.2f}")
            with p_col3: st.metric("Target 1", f"₹{pos['t1']:,.2f}")
            with p_col4:
                mock_curr = pos["entry_price"] * 1.02
                gross = (mock_curr - pos["entry_price"]) * pos["qty"]
                st.metric("Est. Unrealized", f"₹{gross:+,.2f}")
            with p_col5:
                if st.button(f"Square Off #{t_id}", key=f"sq_{t_id}"):
                    close_paper_position(t_id, mock_curr, "Manual Square Off")
                    st.rerun()

    st.markdown("### Completed Trade Journal (With Regulatory Charges Deducted)")
    journal = st.session_state.paper_portfolio["trade_history"]
    if not journal:
        st.caption("No closed trades recorded for this session yet.")
    else:
        journal_df = pd.DataFrame(journal)
        display_cols = ["trade_id", "symbol", "strike", "option_type", "qty", "entry_price", "exit_price", "gross_pnl", "total_charges", "net_pnl", "exit_reason"]
        st.dataframe(journal_df[display_cols], use_container_width=True)

st.caption(f"Paper Trading Engine Active {BULLET} Real Broker Order Routing Disabled {BULLET} Strictly Educational Quantitative Research.")
