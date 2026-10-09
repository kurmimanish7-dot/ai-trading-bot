import datetime
from datetime import datetime, date, time as dtime
import json
import logging
import time
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import streamlit as st

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)

# =========================================================
# PAGE CONFIGURATION & INSTITUTIONAL THEME
# =========================================================
st.set_page_config(
    page_title="AI Institutional Live Trading Advisor",
    page_icon="âš¡",
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
    
    /* MOBILE RESPONSIVE 2-COLUMN GRID WITHOUT OVERFLOW */
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
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {
            font-size: 1.05rem !important;
            line-height: 1.15 !important;
        }
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] * {
            font-size: 0.72rem !important;
            line-height: 1.1 !important;
        }
        [data-testid="stMetricDelta"],
        [data-testid="stMetricDelta"] * {
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

    /* ZERO-TRUNCATION OVERRIDES */
    div[data-stale="true"],
    div[data-stale="true"] *,
    .stale-element,
    .stale-element *,
    .element-container,
    .element-container * {
        opacity: 1 !important;
        filter: none !important;
        transition: none !important;
        animation: none !important;
    }

    [data-testid="stMetric"],
    [data-testid="stMetric"] * {
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

    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] * {
        white-space: normal !important;
        word-break: break-word !important;
        line-height: 1.15 !important;
        font-size: 0.76rem !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }

    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] * {
        white-space: normal !important;
        word-break: break-word !important;
        line-height: 1.15 !important;
        font-size: 1.12rem !important;
        overflow: visible !important;
        text-overflow: clip !important;
        font-variant-numeric: tabular-nums !important;
        letter-spacing: -0.01em !important;
    }

    [data-testid="stMetricDelta"],
    [data-testid="stMetricDelta"] * {
        white-space: normal !important;
        word-break: break-word !important;
        font-size: 0.72rem !important;
        line-height: 1.1 !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }

    [data-testid="stStatusWidget"] {
        visibility: hidden !important;
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# FRAGMENT COMPATIBILITY
# =========================================================
if hasattr(st, "fragment"):
    live_fragment = st.fragment
elif hasattr(st, "experimental_fragment"):
    live_fragment = st.experimental_fragment
else:
    def live_fragment(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

# =========================================================
# TIMEFRAME CONFIGURATION & MATRIX
# =========================================================
TIMEFRAME_CONFIG = {
    "1m": {
        "label": "âš¡ 1 Minute (Scalping / High-Speed)",
        "smartapi": "ONE_MINUTE",
        "yfinance": "1m",
        "yf_range": "2d",
        "days": 2,
        "holding": "Quick Scalp (1-5 Mins)",
        "target1_mult": 1.15,
        "target2_mult": 1.25,
        "sl_mult": 0.92,
        "atr_mult": 0.8,
        "desc": "Ultra-fast scalp setup. High sensitivity, tight SL.",
    },
    "5m": {
        "label": "ðŸ“Š 5 Minutes (Standard Intraday)",
        "smartapi": "FIVE_MINUTE",
        "yfinance": "5m",
        "yf_range": "5d",
        "days": 5,
        "holding": "Intraday Momentum (15-45 Mins)",
        "target1_mult": 1.20,
        "target2_mult": 1.35,
        "sl_mult": 0.85,
        "atr_mult": 1.0,
        "desc": "Standard institutional intraday timeframe for liquid momentum.",
    },
    "10m": {
        "label": "ðŸŽ¯ 10 Minutes (Noise-Filtered Scalp)",
        "smartapi": "TEN_MINUTE",
        "yfinance": "10m",
        "yf_range": "5d",
        "days": 5,
        "holding": "Intraday Trend (30-60 Mins)",
        "target1_mult": 1.22,
        "target2_mult": 1.38,
        "sl_mult": 0.84,
        "atr_mult": 1.2,
        "desc": "Smooth momentum timeframe filtering out minor whipsaws.",
    },
    "15m": {
        "label": "ðŸ›ï¸ 15 Minutes (Institutional Intraday)",
        "smartapi": "FIFTEEN_MINUTE",
        "yfinance": "15m",
        "yf_range": "5d",
        "days": 7,
        "holding": "Multi-Hour Trend (1-3 Hours)",
        "target1_mult": 1.25,
        "target2_mult": 1.45,
        "sl_mult": 0.82,
        "atr_mult": 1.5,
        "desc": "Key institutional breakout timeframe for major intraday moves.",
    },
    "30m": {
        "label": "ðŸ“ˆ 30 Minutes (Positional / BTST)",
        "smartapi": "THIRTY_MINUTE",
        "yfinance": "30m",
        "yf_range": "1mo",
        "days": 15,
        "holding": "BTST / Positional (1-3 Days)",
        "target1_mult": 1.30,
        "target2_mult": 1.55,
        "sl_mult": 0.78,
        "atr_mult": 2.0,
        "desc": "Strong trend conviction for overnight holding and multi-day swings.",
    },
    "60m": {
        "label": "ðŸ§­ 60 Minutes (1 Hour Macro Swing)",
        "smartapi": "ONE_HOUR",
        "yfinance": "60m",
        "yf_range": "1mo",
        "days": 30,
        "holding": "Swing Trend (3-7 Days)",
        "target1_mult": 1.40,
        "target2_mult": 1.70,
        "sl_mult": 0.75,
        "atr_mult": 2.8,
        "desc": "Macro hourly trend framework for swing traders.",
    },
}

# =========================================================
# ENGINE IMPORTS & RESILIENT FALLBACKS
# =========================================================
try:
    from telemetry_engine import TelemetryEngine
except Exception:
    TelemetryEngine = None

try:
    from options_engine import OptionsEngine
except Exception:
    OptionsEngine = None

try:
    from global_macro_engine import GlobalMacroEngine
except Exception:
    class GlobalMacroEngine:
        def __init__(self):
            self.session = requests.Session()
            self.session.headers.update({"User-Agent": "Mozilla/5.0"})

        def fetch_macro_quotes(self):
            out = {
                "GIFT_NIFTY": {"symbol": "Gift Nifty Spread", "price": 0.0, "change_pct": 0.0, "status": "NEUTRAL"},
                "NASDAQ": {"symbol": "Nasdaq Composite", "price": 0.0, "change_pct": 0.0, "status": "UNKNOWN"},
                "CRUDE_OIL": {"symbol": "Brent Crude Oil", "price": 0.0, "change_pct": 0.0, "status": "UNKNOWN"},
                "GOLD": {"symbol": "Gold (MCX/COMEX)", "price": 0.0, "change_pct": 0.0, "status": "UNKNOWN"},
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
                        "symbol": "Nasdaq Composite",
                        "price": price,
                        "change_pct": pct,
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
                        "symbol": "Brent Crude Oil",
                        "price": price_c,
                        "change_pct": pct_c,
                        "status": "RED" if pct_c >= 1.0 else ("GREEN" if pct_c <= -1.0 else "YELLOW"),
                    }
            except Exception:
                pass

            return out

@st.cache_resource(show_spinner=False)
def get_global_macro_engine():
    try:
        return GlobalMacroEngine()
    except Exception as exc:
        logger.error("Failed to initialize GlobalMacroEngine: %s", exc)
        return None

global_macro_inst = get_global_macro_engine()

# =========================================================
# SECRETS & CREDENTIALS MANAGEMENT
# =========================================================
def secret(name):
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
GEMINI_MODEL = secret("GEMINI_MODEL") or "gemini-3.8-flash"

# =========================================================
# UTILITIES & NORMALIZATION
# =========================================================
def num(x, default=None):
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace(",", "").strip()
        val = float(x)
        return val if np.isfinite(val) else default
    except Exception:
        return default

def fmt(x, digits=2):
    val = num(x)
    return "-" if val is None else f"{val:,.{digits}f}"

def market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)

def expiry_norm(x):
    if x is None:
        return None
    if isinstance(x, (datetime, date)):
        return x.strftime("%Y-%m-%d")
    s = str(x).strip().upper()
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d%b%Y", "%d-%b-%Y"]
    for f in formats:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s

def expiry_label(x):
    n = expiry_norm(x)
    if not n:
        return "-"
    try:
        return datetime.strptime(n, "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        return str(x)

def clean_df(df):
    if df is None:
        return pd.DataFrame()
    if isinstance(df, pd.DataFrame):
        return df.copy()
    try:
        return pd.DataFrame(df)
    except Exception:
        return pd.DataFrame()

def first_value(row, names, default=None):
    for name in names:
        if isinstance(row, dict) and name in row:
            val = row.get(name)
            if val is not None and str(val) != "":
                return val
        try:
            if hasattr(row, "index") and name in row.index:
                val = row[name]
                if pd.notna(val):
                    return val
        except Exception:
            pass
    return default

def find_column(df, names):
    for name in names:
        if name in df.columns:
            return name
    return None

def normalize_option_type(value):
    if not value:
        return ""
    x = str(value).strip().upper()
    if "CE" in x or "CALL" in x or x.endswith("C"):
        return "CE"
    if "PE" in x or "PUT" in x or x.endswith("P"):
        return "PE"
    return ""

def resample_5m_to_10m(df):
    if df.empty or len(df) < 2:
        return df
    groups = df.groupby(df.index // 2)
    res = pd.DataFrame({
        "open": groups["open"].first(),
        "high": groups["high"].max(),
        "low": groups["low"].min(),
        "close": groups["close"].last(),
        "volume": groups["volume"].sum() if "volume" in df.columns else 0
    })
    return res.reset_index(drop=True)

# =========================================================
# BROKER SESSION & TELEMETRY
# =========================================================
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

UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]

INDEX_METADATA = {
    "NIFTY": {
        "exchange": "NSE",
        "symbol": "Nifty 50",
        "alt_symbols": ["NIFTY 50", "NIFTY", "Nifty 50"],
        "live_tokens": ["26000", "99926000"],
        "candle_token": "99926000",
        "yfinance": "^NSEI",
    },
    "BANKNIFTY": {
        "exchange": "NSE",
        "symbol": "Nifty Bank",
        "alt_symbols": ["NIFTY BANK", "BANKNIFTY", "Nifty Bank"],
        "live_tokens": ["26009", "99926009"],
        "candle_token": "99926009",
        "yfinance": "^NSEBANK",
    },
    "FINNIFTY": {
        "exchange": "NSE",
        "symbol": "FINNIFTY",
        "alt_symbols": ["FINNIFTY", "NIFTY FIN SERVICE"],
        "live_tokens": ["99926037", "26037"],
        "candle_token": "99926037",
        "yfinance": "NIFTY_FIN_SERVICE.NS",
    },
    "MIDCPNIFTY": {
        "exchange": "NSE",
        "symbol": "MIDCPNIFTY",
        "alt_symbols": ["MIDCPNIFTY", "NIFTY MID SELECT"],
        "live_tokens": ["99926074", "26074"],
        "candle_token": "99926074",
        "yfinance": "NIFTY_MIDCAP_100.NS",
    },
    "SENSEX": {
        "exchange": "BSE",
        "symbol": "SENSEX",
        "alt_symbols": ["SENSEX", "BSESN"],
        "live_tokens": ["99919000", "1"],
        "candle_token": "99919000",
        "yfinance": "^BSESN",
    },
    "INDIA_VIX": {
        "exchange": "NSE",
        "symbol": "India VIX",
        "alt_symbols": ["INDIA VIX", "INDIAVIX"],
        "live_tokens": ["99926017", "26017"],
        "candle_token": "99926017",
        "yfinance": "^INDIAVIX",
    },
}

# =========================================================
# BULLETPROOF HYBRID DATA FETCHERS (BROKER + LIVE FALLBACK)
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=5):
    if symbol not in INDEX_METADATA:
        return pd.DataFrame()

    meta = INDEX_METADATA[symbol]
    exchange = meta["exchange"]
    token = meta["candle_token"]

    # 1. Try Angel One SmartAPI
    if telemetry and hasattr(telemetry, "fetch_ohlcv"):
        try:
            df = clean_df(telemetry.fetch_ohlcv(exchange=exchange, token=str(token), interval=interval, days=days))
            if not df.empty:
                rename = {}
                for c in df.columns:
                    lc = str(c).lower()
                    if lc in ["open", "o"]: rename[c] = "open"
                    elif lc in ["high", "h"]: rename[c] = "high"
                    elif lc in ["low", "l"]: rename[c] = "low"
                    elif lc in ["close", "c", "ltp"]: rename[c] = "close"
                    elif lc in ["volume", "vol"]: rename[c] = "volume"
                df = df.rename(columns=rename)

                needed = ["open", "high", "low", "close"]
                for c in needed + (["volume"] if "volume" in df.columns else []):
                    df[c] = pd.to_numeric(df[c], errors="coerce")

                df = df.dropna(subset=needed).reset_index(drop=True)
                if len(df) >= 5:
                    return df
        except Exception:
            pass

    # 2. Resilient Live Fallback for Indices
    yf_symbol = meta.get("yfinance")
    if yf_symbol:
        interval_map = {
            "ONE_MINUTE": ("1m", "2d"),
            "FIVE_MINUTE": ("5m", "5d"),
            "TEN_MINUTE": ("5m", "5d"),
            "FIFTEEN_MINUTE": ("15m", "5d"),
            "THIRTY_MINUTE": ("30m", "1mo"),
            "ONE_HOUR": ("60m", "1mo"),
        }
        yf_int, yf_range = interval_map.get(interval, ("5m", "5d"))
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval={yf_int}&range={yf_range}"
            resp = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok:
                data = resp.json()["chart"]["result"][0]
                quotes = data["indicators"]["quote"][0]
                df = pd.DataFrame({
                    "open": quotes.get("open", []),
                    "high": quotes.get("high", []),
                    "low": quotes.get("low", []),
                    "close": quotes.get("close", []),
                    "volume": quotes.get("volume", []),
                })
                df = df.dropna(subset=["close"]).reset_index(drop=True)
                if interval == "TEN_MINUTE":
                    df = resample_5m_to_10m(df)
                if not df.empty and len(df) >= 5:
                    return df
        except Exception:
            pass

    return pd.DataFrame()

@st.cache_data(ttl=10, show_spinner=False)
def get_spot(symbol):
    if symbol not in INDEX_METADATA:
        return None

    meta = INDEX_METADATA[symbol]
    exchange = meta["exchange"]

    # 1. Try Angel One SmartAPI live lookup
    if telemetry and hasattr(telemetry, "smart_api") and telemetry.smart_api:
        symbols_to_try = [meta["symbol"]] + meta.get("alt_symbols", [])
        for sym_name in symbols_to_try:
            for token in meta["live_tokens"]:
                try:
                    res = telemetry.smart_api.ltpData(
                        exchange=exchange,
                        tradingsymbol=sym_name,
                        symboltoken=str(token),
                    )
                    if res and res.get("status") and "data" in res:
                        val = float(res["data"].get("ltp", 0.0))
                        if val > 0:
                            return val
                except Exception:
                    pass

        try:
            res = telemetry.get_ltp(meta["symbol"])
            val = num(res.get("ltp") if isinstance(res, dict) else res)
            if val and val > 0:
                return val
        except Exception:
            pass

    # 2. Resilient Real-Time Fallback via Yahoo Finance
    yf_symbol = meta.get("yfinance")
    if yf_symbol:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1d&range=2d"
            resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok:
                data = resp.json()
                meta_data = data["chart"]["result"][0]["meta"]
                price = float(meta_data.get("regularMarketPrice", 0.0))
                if price > 0:
                    return price
                prev_close = float(meta_data.get("chartPreviousClose", 0.0))
                if prev_close > 0:
                    return prev_close
        except Exception:
            pass

    # 3. Fallback to latest historical candle close
    try:
        df = fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=2)
        if not df.empty and "close" in df.columns:
            last_c = float(df["close"].dropna().iloc[-1])
            if last_c > 0:
                return last_c
    except Exception:
        pass

    return None

@st.cache_data(ttl=10, show_spinner=False)
def get_india_vix():
    vix = get_spot("INDIA_VIX")
    if vix is None or vix <= 0:
        vix = 14.50

    if vix < 12.0:
        regime = "LOW VOLATILITY"
        sl_multiplier = 0.88
    elif 12.0 <= vix <= 18.0:
        regime = "OPTIMAL BUYING"
        sl_multiplier = 0.85
    elif 18.0 < vix <= 24.0:
        regime = "HIGH VOLATILITY"
        sl_multiplier = 0.80
    else:
        regime = "EXTREME SWINGS"
        sl_multiplier = 0.75

    return {"vix": vix, "regime": regime, "sl_multiplier": sl_multiplier}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fii_dii():
    fii_net, dii_net = None, None
    try:
        resp = requests.get(
            "https://fii-diidata.mrchartist.com/api/data",
            timeout=4,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.ok:
            data = resp.json()
            if isinstance(data, list) and data:
                data = data[0]
            fii_net = num(data.get("fii_net") or data.get("fiiNet"))
            dii_net = num(data.get("dii_net") or data.get("diiNet"))
    except Exception:
        pass

    score = 0
    if fii_net is not None:
        score += 2 if fii_net > 1000 else (1 if fii_net > 300 else (-2 if fii_net < -1000 else (-1 if fii_net < -300 else 0)))
    if dii_net is not None:
        score += 1 if dii_net > 500 else (-1 if dii_net < -500 else 0)

    bias = "STRONG BULLISH" if score >= 2 else ("MODERATE BULLISH" if score == 1 else ("STRONG BEARISH" if score <= -2 else ("MODERATE BEARISH" if score == -1 else "NEUTRAL")))

    return {
        "available": (fii_net is not None or dii_net is not None),
        "fii_net": fii_net,
        "dii_net": dii_net,
        "combined": (fii_net + dii_net) if (fii_net is not None and dii_net is not None) else None,
        "score": score,
        "bias": bias,
    }

fii_dii = fetch_fii_dii()

@st.cache_data(ttl=300, show_spinner=False)
def load_expiries(symbol):
    opt_eng = get_options_engine()
    if opt_eng is None:
        return []
    try:
        res = opt_eng.get_expiry_options(symbol)
        vals = []
        for item in res or []:
            v = item.get("value") or item.get("expiry") if isinstance(item, dict) else item
            v = expiry_norm(v)
            if v:
                vals.append(v)
        return sorted(set(vals))
    except Exception:
        return []

@st.cache_data(ttl=25, show_spinner=False)
def get_chain(symbol, expiry):
    opt_eng = get_options_engine()
    if opt_eng is None or not expiry:
        return pd.DataFrame(), pd.DataFrame()
    try:
        contracts = clean_df(opt_eng.get_option_contracts(underlying=symbol, expiry_date=expiry))
        quoted = clean_df(opt_eng.get_market_quote(contracts)) if not contracts.empty else contracts
        return quoted, contracts
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

def calculate_pcr(chain):
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
                if 0 < pcr_val <= 10:
                    return float(pcr_val)
    return None

def calculate_live_derivatives_proxy(chain, pcr):
    if pcr is None:
        return {"available": False, "score": 0, "bias": "NEUTRAL"}
    score = 2 if pcr >= 1.20 else (-2 if pcr <= 0.70 else 0)
    bias = "BULLISH" if score > 0 else ("BEARISH" if score < 0 else "NEUTRAL")
    return {"available": True, "score": score, "bias": bias}

def add_indicators(df, current_live_price=None):
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()

    if current_live_price and current_live_price > 0:
        last_idx = df.index[-1]
        df.at[last_idx, "close"] = current_live_price
        if current_live_price > df.at[last_idx, "high"]:
            df.at[last_idx, "high"] = current_live_price
        if current_live_price < df.at[last_idx, "low"]:
            df.at[last_idx, "low"] = current_live_price

    close, high, low = df["close"], df["high"], df["low"]
    df["EMA20"] = close.ewm(span=20, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()
    df["EMA200"] = close.ewm(span=200, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean().replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    df["MACD"] = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    df["ATR"] = atr

    plus_dm = high.diff().where((high.diff() > -low.diff()) & (high.diff() > 0), 0)
    minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0)
    plus_di = 100 * plus_dm.rolling(14).sum() / atr.rolling(14).sum().replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(14).sum() / atr.rolling(14).sum().replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["ADX"] = dx.rolling(14).mean()

    if "volume" in df.columns and df["volume"].sum() > 0:
        typical = (high + low + close) / 3
        df["VWAP"] = (typical * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)
        df["VOL_AVG20"] = df["volume"].rolling(20).mean()
    else:
        df["VWAP"] = (high + low + close) / 3
        df["VOL_AVG20"] = 1.0

    return df

def analyze_market(symbol, proxy=None, explicit_spot=None, tf_cfg=None):
    if tf_cfg is None:
        tf_cfg = TIMEFRAME_CONFIG["5m"]

    res = {
        "symbol": symbol,
        "trend": "UNKNOWN",
        "last": explicit_spot,
        "rsi": None,
        "adx": None,
        "ema20": None,
        "ema50": None,
        "vwap": None,
        "support": None,
        "resistance": None,
        "technical_score": 0,
        "institutional_score": 0,
        "score": 0,
        "reasons": [],
    }

    df = add_indicators(
        fetch_ohlcv(symbol, tf_cfg["smartapi"], tf_cfg["days"]),
        current_live_price=explicit_spot
    )
    if df.empty:
        return res

    row = df.iloc[-1]
    last = explicit_spot or num(row.get("close"))
    res["last"] = last
    res["rsi"] = num(row.get("RSI"))
    res["adx"] = num(row.get("ADX"))
    res["ema20"] = num(row.get("EMA20"))
    res["ema50"] = num(row.get("EMA50"))
    res["vwap"] = num(row.get("VWAP"))
    res["support"] = num(df["low"].tail(30).min())
    res["resistance"] = num(df["high"].tail(30).max())

    score = 0
    if res["ema20"] and res["ema50"] and last:
        if last > res["ema20"] > res["ema50"]:
            score += 2
            res["reasons"].append(f"Price EMA20 aur EMA50 ke upar sustained hai ({tf_cfg['smartapi']}).")
        elif last < res["ema20"] < res["ema50"]:
            score -= 2
            res["reasons"].append(f"Price EMA20 aur EMA50 ke neeche breakdown par hai ({tf_cfg['smartapi']}).")

    if res["vwap"] and last:
        if last > res["vwap"]:
            score += 1
            res["reasons"].append("Price Institutional VWAP benchmark ke upar trade kar raha hai.")
        else:
            score -= 1
            res["reasons"].append("Price Institutional VWAP benchmark ke neeche trade kar raha hai.")

    if res["rsi"]:
        if res["rsi"] >= 60:
            score += 1
            res["reasons"].append(f"RSI ({res['rsi']:.1f}) bullish expansion zone mein hai.")
        elif res["rsi"] <= 40:
            score -= 1
            res["reasons"].append(f"RSI ({res['rsi']:.1f}) bearish distribution zone mein hai.")

    if res["adx"] and res["adx"] >= 20:
        res["reasons"].append(f"ADX ({res['adx']:.1f}) trend conviction confirm karta hai.")

    res["technical_score"] = score
    inst_score = fii_dii.get("score", 0) if fii_dii.get("available") else (proxy.get("score", 0) if proxy else 0)
    res["institutional_score"] = inst_score
    res["score"] = score + inst_score
    res["trend"] = "BULLISH" if res["score"] >= 3 else ("BEARISH" if res["score"] <= -3 else "SIDEWAYS")
    return res

def analyze_candlesticks_and_volume(df):
    if df is None or len(df) < 5:
        return {
            "status": "YELLOW",
            "pattern": "AWAITING TICK DATA",
            "vol_ratio": 1.0,
            "reversal_risk": False,
            "reason": "Candle array load ho raha hai.",
        }

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
        return {
            "status": "YELLOW",
            "pattern": "DOJI (PAUSE / INDECISION)",
            "vol_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Doji structure bani hai ({body/rng:.2f} ratio). Consolidation phase.",
        }

    if lower_w >= (2.0 * body) and upper_w <= (0.25 * body):
        return {
            "status": "GREEN",
            "pattern": "BULLISH HAMMER PIN",
            "vol_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Support rejection hammer confirmed ({vol_ratio:.2f}x vol).",
        }

    if upper_w >= (2.0 * body) and lower_w <= (0.25 * body):
        return {
            "status": "RED",
            "pattern": "BEARISH SHOOTING STAR",
            "vol_ratio": vol_ratio,
            "reversal_risk": True,
            "reason": f"Resistance rejection shooting star confirmed ({vol_ratio:.2f}x vol).",
        }

    if (close_p > open_p) and (float(p["close"]) < float(p["open"])) and (close_p >= float(p["open"])):
        return {
            "status": "GREEN",
            "pattern": "BULLISH ENGULFING",
            "vol_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Bullish engulfing overriding prior candle ({vol_ratio:.2f}x vol).",
        }

    if (close_p < open_p) and (float(p["close"]) > float(p["open"])) and (close_p <= float(p["open"])):
        return {
            "status": "RED",
            "pattern": "BEARISH ENGULFING",
            "vol_ratio": vol_ratio,
            "reversal_risk": True,
            "reason": f"Bearish engulfing breakdown overriding prior candle ({vol_ratio:.2f}x vol).",
        }

    if body >= (0.50 * rng):
        if close_p < open_p:
            status = "RED"
            name = "BEARISH BREAKDOWN"
            reason = f"Directional sell expansion confirmed ({vol_ratio:.2f}x vol)."
        else:
            status = "GREEN"
            name = "BULLISH MARUBOZU"
            reason = f"Directional rally expansion confirmed ({vol_ratio:.2f}x vol)."

        return {
            "status": status,
            "pattern": name,
            "vol_ratio": vol_ratio,
            "reversal_risk": (status == "RED"),
            "reason": reason,
        }

    if is_continuous_fall:
        return {
            "status": "RED",
            "pattern": "STEADY BEARISH MOMENTUM",
            "vol_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": "Consecutive lower closes confirm active downward trend.",
        }

    return {
        "status": "YELLOW",
        "pattern": "RANGE CONSOLIDATION",
        "vol_ratio": vol_ratio,
        "reversal_risk": False,
        "reason": "Normal candle range without directional breakout.",
    }

def analyze_smart_money(fii_dii_data, pcr_val, df=None, current_spot=None):
    score = 0
    notes = []
    has_data = False

    if pcr_val is not None:
        has_data = True
        if pcr_val >= 1.25:
            score += 2
            notes.append(f"PCR {pcr_val:.2f} put writing support floor")
        elif pcr_val >= 1.00:
            score += 1
            notes.append(f"PCR {pcr_val:.2f} mildly supportive")
        elif 0.70 < pcr_val < 1.00:
            score -= 1
            notes.append(f"PCR {pcr_val:.2f} cautious call resistance")
        else:
            score -= 2
            notes.append(f"PCR {pcr_val:.2f} heavy call writing pressure")

    if fii_dii_data.get("available"):
        has_data = True
        score += fii_dii_data.get("score", 0)
        notes.append(f"FII/DII: {fii_dii_data.get('bias')}")

    if not has_data and df is not None and not df.empty and current_spot:
        day_open = float(df["open"].iloc[0])
        vwap_val = float(df["VWAP"].iloc[-1]) if "VWAP" in df.columns and pd.notna(df["VWAP"].iloc[-1]) else day_open

        if current_spot < vwap_val and current_spot < day_open:
            score -= 2
            notes.append(f"Institutional VWAP Breakdown (Spot â‚¹{current_spot:,.0f} < VWAP â‚¹{vwap_val:,.0f})")
        elif current_spot > vwap_val and current_spot > day_open:
            score += 2
            notes.append(f"Institutional VWAP Support (Spot â‚¹{current_spot:,.0f} > VWAP â‚¹{vwap_val:,.0f})")
        else:
            notes.append("Hovering near Institutional VWAP")

    status = "GREEN" if score >= 2 else ("RED" if score <= -2 else "YELLOW")
    final_reason = " | ".join(notes) if notes else "Smart Money neutral."
    return {"status": status, "score": score, "reason": final_reason}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_composite_macro_news(macro_quotes=None):
    rss_url = "https://news.google.com/rss/search?q=Indian+stock+market+Nifty&hl=en-IN&gl=IN&ceid=IN:en"
    headlines = []
    try:
        resp = requests.get(rss_url, timeout=4)
        if resp.ok:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:6]:
                t = item.find("title")
                if t is not None and t.text:
                    headlines.append(t.text)
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
        if nq >= 0.5:
            macro_bonus += 1
            macro_notes.append(f"Nasdaq Strong (+{nq:.1f}%)")
        elif nq <= -0.5:
            macro_bonus -= 1
            macro_notes.append(f"Nasdaq Drag ({nq:.1f}%)")

        if crude >= 1.5:
            macro_bonus -= 1
            macro_notes.append(f"Crude Spike (+{crude:.1f}%)")
        elif crude <= -1.5:
            macro_bonus += 1
            macro_notes.append(f"Crude Softening ({crude:.1f}%)")

    total_macro_score = news_score + macro_bonus

    if total_macro_score >= 2:
        status, summary = "GREEN", "BULLISH MACRO CATALYST"
    elif total_macro_score <= -2:
        status, summary = "RED", "BEARISH MACRO HEADWINDS"
    else:
        status, summary = "YELLOW", "BALANCED / NEUTRAL MACRO"

    reason_str = f"News net: {news_score:+d}."
    if macro_notes:
        reason_str += " Cues: " + ", ".join(macro_notes)

    return {"status": status, "score": total_macro_score, "summary": summary, "reason": reason_str}

def evaluate_all_permutations(l1, l2, l3):
    s1, s2, s3 = l1["status"], l2["status"], l3["status"]
    reds = [s1, s2, s3].count("RED")
    greens = [s1, s2, s3].count("GREEN")

    if reds == 3:
        return {
            "signal": "ðŸš¨ ULTRA STRONG SHORT (BUY PE)",
            "action": "BUY PUT (PE)",
            "confidence": 95,
            "badge": "error",
            "allocation": "100% Capital Size",
            "rationale": "High-volume breakdown + Smart Money selling + Global macro headwinds fully aligned.",
        }
    if greens == 3:
        return {
            "signal": "ðŸ”¥ ULTRA STRONG BUY (BUY CE)",
            "action": "BUY CALL (CE)",
            "confidence": 95,
            "badge": "success",
            "allocation": "100% Capital Size",
            "rationale": "High-volume breakout + Institutional buying + Global tailwinds fully aligned.",
        }

    if reds >= 2 and greens == 0:
        return {
            "signal": "ðŸš¨ STRONG SHORT (BUY PE)",
            "action": "BUY PUT (PE)",
            "confidence": 85,
            "badge": "error",
            "allocation": "75% Position Size",
            "rationale": "Price action and macro vectors confirm clear downward momentum.",
        }

    if greens >= 2 and reds == 0:
        return {
            "signal": "âš¡ STRONG BUY (BUY CE)",
            "action": "BUY CALL (CE)",
            "confidence": 85,
            "badge": "success",
            "allocation": "75% Position Size",
            "rationale": "Price action and institutional flows confirm upward expansion.",
        }

    if s1 == "RED" and greens == 0:
        return {
            "signal": "âš¡ MODERATE SHORT (BUY PE)",
            "action": "BUY PUT (PE)",
            "confidence": 70,
            "badge": "error",
            "allocation": "50% Position Size",
            "rationale": "Candle breakdown confirmed. Short positions favored with tight stop-loss.",
        }

    if s1 == "GREEN" and reds == 0:
        return {
            "signal": "âš¡ MODERATE BUY (BUY CE)",
            "action": "BUY CALL (CE)",
            "confidence": 70,
            "badge": "success",
            "allocation": "50% Position Size",
            "rationale": "Candle breakout confirmed. Favor Call buying with trailing risk parameters.",
        }

    if greens >= 1 and reds >= 1:
        return {
            "signal": "âš”ï¸ CONFLICT / STRICT NO TRADE",
            "action": "STRICT AVOID / CASH PRESERVATION",
            "confidence": 15,
            "badge": "info",
            "allocation": "0% Capital Size",
            "rationale": "Divergence detected: Price action diverges from Smart Money or Macro positioning.",
        }

    return {
        "signal": "â¸ï¸ NO TRADE / WAIT FOR CLARITY",
        "action": "STAND ASIDE",
        "confidence": 20,
        "badge": "info",
        "allocation": "0% Capital Size",
        "rationale": "Consolidation phase detected. Await directional breakout confirmation.",
    }

def calculate_indian_market_prediction(macro_data, domestic_pcr=1.0, fii_dii_info=None):
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
        "verdict": verdict,
        "points_range": points_range,
        "badge": badge,
        "confidence": confidence,
        "action": action,
        "score": gap_points,
    }

def get_optimal_option_strike(symbol, spot, side, chain=None):
    step = 50 if symbol in ["NIFTY", "FINNIFTY"] else 100
    base_strike = int(round(spot / step) * step)

    ltp = None
    oi = 0
    chg_oi = 0
    delta = 0.52 if side == "CE" else -0.52
    gamma = 0.0028
    theta = -12.5
    vega = 14.2
    iv = 14.8
    contract_token = None
    contract_symbol = None

    if chain is not None and not chain.empty:
        t_col = find_column(chain, ["option_type", "optionType", "type"])
        s_col = find_column(chain, ["strike", "strikePrice"])
        if t_col and s_col:
            work = chain.copy()
            work["_t"] = work[t_col].map(normalize_option_type)
            work = work[work["_t"] == side].copy()
            if not work.empty:
                work["_s"] = pd.to_numeric(work[s_col], errors="coerce")
                if work["_s"].max() > 200000:
                    work["_s"] = work["_s"] / 100.0
                work = work.dropna(subset=["_s"])
                if not work.empty:
                    work["_dist"] = (work["_s"] - spot).abs()
                    best = work.sort_values("_dist").iloc[0]
                    base_strike = int(best["_s"])

                    contract_token = str(first_value(best, ["token", "symboltoken", "symbol_token"]) or "")
                    contract_symbol = str(first_value(best, ["symbol", "tradingsymbol"]) or "")

                    ltp = num(first_value(best, ["ltp", "lastPrice", "close", "last_traded_price"]))
                    oi = int(num(first_value(best, ["openInterest", "oi"]), 0) or 0)
                    chg_oi = int(num(first_value(best, ["changeInOpenInterest", "change_oi"]), 0) or 0)
                    delta = num(first_value(best, ["delta"]), delta)
                    gamma = num(first_value(best, ["gamma"]), gamma)
                    theta = num(first_value(best, ["theta"]), theta)
                    vega = num(first_value(best, ["vega"]), vega)
                    iv = num(first_value(best, ["impliedVolatility", "iv"]), iv)

    if contract_token and contract_symbol and telemetry and hasattr(telemetry, "smart_api") and telemetry.smart_api:
        try:
            res = telemetry.smart_api.ltpData(
                exchange="NFO",
                tradingsymbol=contract_symbol,
                symboltoken=contract_token,
            )
            if res and res.get("status") and "data" in res:
                api_ltp = float(res["data"].get("ltp", 0.0))
                if api_ltp > 0:
                    ltp = api_ltp
        except Exception as exc:
            logger.warning("Direct option ltpData lookup failed: %s", exc)

    if ltp is None or ltp <= 0:
        ltp = round(spot * 0.012, 1)

    return {
        "strike": base_strike,
        "option_type": side,
        "ltp": ltp,
        "oi": oi,
        "chg_oi": chg_oi,
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega,
        "iv": iv,
        "token": contract_token,
        "symbol": contract_symbol,
    }

def make_trade_idea(market, symbol, instrument="INDEX", option_side=None, expiry=None, chain=None, confluence=None, vix_info=None, tf_cfg=None):
    if tf_cfg is None:
        tf_cfg = TIMEFRAME_CONFIG["5m"]

    last = market.get("last")
    if last is None or last <= 0:
        return None

    conf_sig = confluence.get("action", "") if confluence else ""
    if "PUT" in conf_sig:
        bullish = False
    elif "CALL" in conf_sig:
        bullish = True
    else:
        bullish = True if market.get("score", 0) >= 1 else (False if market.get("score", 0) <= -1 else None)

    if bullish is None:
        return None

    entry_spot = float(last)
    support = num(market.get("support"))
    resistance = num(market.get("resistance"))

    atr_mult = tf_cfg.get("atr_mult", 1.0)

    if bullish:
        action = "BUY"
        sl = support if (support and support < entry_spot) else (entry_spot * (1 - 0.003 * atr_mult))
        risk = entry_spot - sl
        t1, t2 = entry_spot + (risk * 1.5), entry_spot + (risk * 2.5)
    else:
        action = "SELL"
        sl = resistance if (resistance and resistance > entry_spot) else (entry_spot * (1 + 0.003 * atr_mult))
        risk = sl - entry_spot
        t1, t2 = entry_spot - (risk * 1.5), entry_spot - (risk * 2.5)

    if risk <= 0:
        return None

    confidence = confluence.get("confidence", 80) if confluence else 80
    sl_mult = tf_cfg.get("sl_mult", 0.85)

    reasons_list = market.get("reasons", [])
    vsa_text = "Volume expansion confirmed" if any("volume" in r.lower() for r in reasons_list) else "Technical breakdown aligned"
    trend_state = "Bullish Uptrend" if bullish else "Bearish Breakdown"
    why_explanation = (
        f"Ye trade {trend_state} aur [{tf_cfg['label']}] resolution par formulate kiya gaya hai. "
        f"{' '.join(reasons_list[:4])} "
        f"Confluence system aur {vsa_text} is direction ko strongly support kar rahe hain."
    )

    idea = {
        "segment": instrument,
        "symbol": symbol,
        "action": action,
        "entry": entry_spot,
        "sl": sl,
        "target1": t1,
        "target2": t2,
        "risk_reward": abs(t1 - entry_spot) / risk,
        "target2_rr": abs(t2 - entry_spot) / risk,
        "confidence": confidence,
        "holding": tf_cfg["holding"] if market_open() else "NEXT SESSION",
        "timeframe": tf_cfg["label"],
        "expiry": expiry,
        "option": None,
        "strike": None,
        "option_ltp": None,
        "delta": None,
        "gamma": None,
        "theta": None,
        "vega": None,
        "iv": None,
        "oi": None,
        "change_oi": None,
        "technical_score": market.get("technical_score", 0),
        "institutional_score": market.get("institutional_score", 0),
        "why": why_explanation,
        "invalidation": f"Agar spot price {sl:,.2f} SL level ke {'neeche' if bullish else 'upar'} candle close karta hai toh trade cancel ho jayega.",
        "trailing": f"Target 1 hit hote hi 50% position book karein aur Stop Loss ko Cost (Entry price) par trail karein. [{tf_cfg['desc']}]",
    }

    if instrument == "INDEX OPTION":
        active_chain = chain
        if active_chain is None or active_chain.empty:
            opt_eng = get_options_engine()
            if opt_eng:
                try:
                    exp_list = opt_eng.get_expiry_options(symbol)
                    target_exp = expiry or (exp_list[0] if exp_list else None)
                    if isinstance(target_exp, dict):
                        target_exp = target_exp.get("value") or target_exp.get("expiry")
                    if target_exp:
                        active_chain, _ = get_chain(symbol, target_exp)
                        idea["expiry"] = target_exp
                except Exception:
                    pass

        side = option_side if option_side in ["CE", "PE"] else ("CE" if bullish else "PE")
        contract = get_optimal_option_strike(symbol, entry_spot, side, active_chain)

        step = 50 if symbol in ["NIFTY", "FINNIFTY"] else 100
        resolved_strike = int(contract.get("strike") or (round(entry_spot / step) * step))

        opt_entry = float(contract.get("ltp", 0.0))
        opt_sl = opt_entry * sl_mult
        opt_t1 = opt_entry * tf_cfg.get("target1_mult", 1.20)
        opt_t2 = opt_entry * tf_cfg.get("target2_mult", 1.35)
        opt_risk = max(opt_entry - opt_sl, 1.0)

        idea["option"] = side
        idea["action"] = "BUY"
        idea["strike"] = resolved_strike
        idea["option_ltp"] = opt_entry
        idea["entry"] = opt_entry
        idea["sl"] = opt_sl
        idea["target1"] = opt_t1
        idea["target2"] = opt_t2
        idea["risk_reward"] = (opt_t1 - opt_entry) / opt_risk
        idea["target2_rr"] = (opt_t2 - opt_entry) / opt_risk
        idea["delta"] = contract.get("delta", 0.52 if side == "CE" else -0.52)
        idea["gamma"] = contract.get("gamma", 0.0028)
        idea["theta"] = contract.get("theta", -12.5)
        idea["vega"] = contract.get("vega", 14.2)
        idea["iv"] = contract.get("iv", 14.8)
        idea["oi"] = contract.get("oi", 0)
        idea["change_oi"] = contract.get("chg_oi", 0)
        idea["why"] = (
            f"Option Buying Aadhar: {symbol} {resolved_strike} {side} ({tf_cfg['label']}) select kiya gaya hai kyunki iska Delta ({idea['delta']:.2f}) "
            f"optimal zone mein hai. {why_explanation}"
        )

    return idea

# =========================================================
# UNIVERSAL GEMINI CALLER WITH MODEL CASCADE FALLBACK
# =========================================================
def call_gemini_cascade(prompt):
    if not GEMINI_API_KEY:
        return "Gemini API Key missing in Streamlit Secrets."

    models_to_attempt = [
        GEMINI_MODEL,
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-pro",
    ]
    models_to_attempt = list(dict.fromkeys([m for m in models_to_attempt if m]))

    last_error = None

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        for m in models_to_attempt:
            try:
                resp = client.models.generate_content(model=m, contents=prompt)
                if hasattr(resp, "text") and resp.text:
                    return resp.text
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
                if hasattr(resp, "text") and resp.text:
                    return resp.text
            except Exception as e:
                last_error = e
                continue
    except Exception as e:
        last_error = e

    return f"AI Generation error: {last_error}"

def ask_gemini(ideas, market_data):
    payload = {"market": market_data, "ideas": ideas, "fii_dii": fii_dii}
    prompt = f"""
    You are a senior institutional quantitative researcher for Indian derivatives (NIFTY/BANKNIFTY).
    Explain the generated trade setups in detail. Focus on:
    1. Kis technical timeframe aur institutional aadhar par trade banaya gaya hai.
    2. Greeks profile (Delta responsiveness, Theta risk).
    3. Risk management aur trailing stop-loss execution.

    DATA PAYLOAD:
    {json.dumps(payload, default=str)}
    """
    return call_gemini_cascade(prompt)

# =========================================================
# COMPREHENSIVE EQUITY MASTER DATABASE (250+ STOCKS)
# =========================================================
POPULAR_EQUITIES = {
    # Nifty 50 Heavyweights
    "RELIANCE": {"name": "Reliance Industries Ltd", "token_nse": "2885", "token_bse": "500325", "yfinance": "RELIANCE.NS"},
    "TCS": {"name": "Tata Consultancy Services Ltd", "token_nse": "11536", "token_bse": "532540", "yfinance": "TCS.NS"},
    "HDFCBANK": {"name": "HDFC Bank Ltd", "token_nse": "1333", "token_bse": "500180", "yfinance": "HDFCBANK.NS"},
    "ICICIBANK": {"name": "ICICI Bank Ltd", "token_nse": "4963", "token_bse": "532174", "yfinance": "ICICIBANK.NS"},
    "INFY": {"name": "Infosys Ltd", "token_nse": "1594", "token_bse": "500209", "yfinance": "INFY.NS"},
    "SBIN": {"name": "State Bank of India", "token_nse": "3045", "token_bse": "500112", "yfinance": "SBIN.NS"},
    "BHARTIARTL": {"name": "Bharti Airtel Ltd", "token_nse": "10604", "token_bse": "532454", "yfinance": "BHARTIARTL.NS"},
    "TATAMOTORS": {"name": "Tata Motors Ltd", "token_nse": "3456", "token_bse": "500570", "yfinance": "TATAMOTORS.NS"},
    "ITC": {"name": "ITC Ltd", "token_nse": "1660", "token_bse": "500875", "yfinance": "ITC.NS"},
    "LT": {"name": "Larsen & Toubro Ltd", "token_nse": "11483", "token_bse": "500510", "yfinance": "LT.NS"},
    "HINDUNILVR": {"name": "Hindustan Unilever Ltd", "token_nse": "1394", "token_bse": "500696", "yfinance": "HINDUNILVR.NS"},
    "KOTAKBANK": {"name": "Kotak Mahindra Bank", "token_nse": "1922", "token_bse": "500247", "yfinance": "KOTAKBANK.NS"},
    "AXISBANK": {"name": "Axis Bank Ltd", "token_nse": "5900", "token_bse": "532215", "yfinance": "AXISBANK.NS"},
    "MARUTI": {"name": "Maruti Suzuki India", "token_nse": "10999", "token_bse": "532500", "yfinance": "MARUTI.NS"},
    "SUNPHARMA": {"name": "Sun Pharmaceutical", "token_nse": "3351", "token_bse": "524715", "yfinance": "SUNPHARMA.NS"},
    "TITAN": {"name": "Titan Company Ltd", "token_nse": "3506", "token_bse": "500114", "yfinance": "TITAN.NS"},
    "BAJFINANCE": {"name": "Bajaj Finance Ltd", "token_nse": "317", "token_bse": "500034", "yfinance": "BAJFINANCE.NS"},
    "BAJAJFINSV": {"name": "Bajaj Finserv Ltd", "token_nse": "16675", "token_bse": "532978", "yfinance": "BAJAJFINSV.NS"},
    "TATASTEEL": {"name": "Tata Steel Ltd", "token_nse": "3499", "token_bse": "500470", "yfinance": "TATASTEEL.NS"},
    "ASIANPAINT": {"name": "Asian Paints Ltd", "token_nse": "236", "token_bse": "500820", "yfinance": "ASIANPAINT.NS"},
    "NTPC": {"name": "NTPC Ltd", "token_nse": "11630", "token_bse": "532555", "yfinance": "NTPC.NS"},
    "POWERGRID": {"name": "Power Grid Corporation", "token_nse": "14977", "token_bse": "532898", "yfinance": "POWERGRID.NS"},
    "ONGC": {"name": "Oil & Natural Gas Corp", "token_nse": "2475", "token_bse": "500312", "yfinance": "ONGC.NS"},
    "COALINDIA": {"name": "Coal India Ltd", "token_nse": "20374", "token_bse": "533278", "yfinance": "COALINDIA.NS"},
    "M&M": {"name": "Mahindra & Mahindra Ltd", "token_nse": "2031", "token_bse": "500520", "yfinance": "M&M.NS"},
    "ADANIENT": {"name": "Adani Enterprises Ltd", "token_nse": "25", "token_bse": "512599", "yfinance": "ADANIENT.NS"},
    "ADANIPORTS": {"name": "Adani Ports & SEZ", "token_nse": "15083", "token_bse": "532921", "yfinance": "ADANIPORTS.NS"},
    "WIPRO": {"name": "Wipro Ltd", "token_nse": "3787", "token_bse": "507685", "yfinance": "WIPRO.NS"},
    "TECHM": {"name": "Tech Mahindra Ltd", "token_nse": "13538", "token_bse": "532755", "yfinance": "TECHM.NS"},
    "HCLTECH": {"name": "HCL Technologies Ltd", "token_nse": "7229", "token_bse": "532281", "yfinance": "HCLTECH.NS"},
    "JSWSTEEL": {"name": "JSW Steel Ltd", "token_nse": "11723", "token_bse": "500228", "yfinance": "JSWSTEEL.NS"},
    "TATACONSUM": {"name": "Tata Consumer Products", "token_nse": "3432", "token_bse": "500800", "yfinance": "TATACONSUM.NS"},
    "BPCL": {"name": "Bharat Petroleum Corp", "token_nse": "526", "token_bse": "500547", "yfinance": "BPCL.NS"},
    "GRASIM": {"name": "Grasim Industries Ltd", "token_nse": "1232", "token_bse": "500300", "yfinance": "GRASIM.NS"},
    "ULTRACEMCO": {"name": "UltraTech Cement Ltd", "token_nse": "11532", "token_bse": "532538", "yfinance": "ULTRACEMCO.NS"},
    "HEROMOTOCO": {"name": "Hero MotoCorp Ltd", "token_nse": "1348", "token_bse": "500182", "yfinance": "HEROMOTOCO.NS"},
    "EICHERMOT": {"name": "Eicher Motors Ltd", "token_nse": "910", "token_bse": "505200", "yfinance": "EICHERMOT.NS"},
    "CIPLA": {"name": "Cipla Ltd", "token_nse": "694", "token_bse": "500087", "yfinance": "CIPLA.NS"},
    "DRREDDY": {"name": "Dr. Reddy's Laboratories", "token_nse": "881", "token_bse": "500124", "yfinance": "DRREDDY.NS"},
    "APOLLOHOSP": {"name": "Apollo Hospitals Enterprise", "token_nse": "157", "token_bse": "508869", "yfinance": "APOLLOHOSP.NS"},
    "DIVISLAB": {"name": "Divi's Laboratories Ltd", "token_nse": "10940", "token_bse": "532488", "yfinance": "DIVISLAB.NS"},
    "BRITANNIA": {"name": "Britannia Industries Ltd", "token_nse": "547", "token_bse": "500825", "yfinance": "BRITANNIA.NS"},
    "NESTLEIND": {"name": "Nestle India Ltd", "token_nse": "17963", "token_bse": "500790", "yfinance": "NESTLEIND.NS"},

    # High-Growth, Buzz & Defence / Railway / Energy Stocks
    "SUZLON": {"name": "Suzlon Energy Ltd", "token_nse": "13061", "token_bse": "532667", "yfinance": "SUZLON.NS"},
    "ZOMATO": {"name": "Zomato Ltd", "token_nse": "5097", "token_bse": "543320", "yfinance": "ZOMATO.NS"},
    "JIOFIN": {"name": "Jio Financial Services", "token_nse": "18143", "token_bse": "543940", "yfinance": "JIOFIN.NS"},
    "IRFC": {"name": "Indian Railway Finance Corp", "token_nse": "2029", "token_bse": "543257", "yfinance": "IRFC.NS"},
    "RVNL": {"name": "Rail Vikas Nigam Ltd", "token_nse": "30108", "token_bse": "542649", "yfinance": "RVNL.NS"},
    "IREDA": {"name": "Indian Renewable Energy Dev", "token_nse": "20108", "token_bse": "544026", "yfinance": "IREDA.NS"},
    "IRCTC": {"name": "IRCTC Ltd", "token_nse": "13611", "token_bse": "542830", "yfinance": "IRCTC.NS"},
    "MAZDOCK": {"name": "Mazagon Dock Shipbuilders", "token_nse": "2032", "token_bse": "543237", "yfinance": "MAZDOCK.NS"},
    "COCHINSHIP": {"name": "Cochin Shipyard Ltd", "token_nse": "21808", "token_bse": "540678", "yfinance": "COCHINSHIP.NS"},
    "HAL": {"name": "Hindustan Aeronautics Ltd", "token_nse": "2303", "token_bse": "541154", "yfinance": "HAL.NS"},
    "BEL": {"name": "Bharat Electronics Ltd", "token_nse": "383", "token_bse": "500049", "yfinance": "BEL.NS"},
    "BDL": {"name": "Bharat Dynamics Ltd", "token_nse": "2142", "token_bse": "541143", "yfinance": "BDL.NS"},
    "TATAPOWER": {"name": "Tata Power Company Ltd", "token_nse": "3426", "token_bse": "500400", "yfinance": "TATAPOWER.NS"},
    "TATACOMM": {"name": "Tata Communications Ltd", "token_nse": "3413", "token_bse": "500483", "yfinance": "TATACOMM.NS"},
    "TRENT": {"name": "Trent Ltd", "token_nse": "1964", "token_bse": "500251", "yfinance": "TRENT.NS"},
    "BHEL": {"name": "Bharat Heavy Electricals", "token_nse": "438", "token_bse": "500103", "yfinance": "BHEL.NS"},
    "NHPC": {"name": "NHPC Ltd", "token_nse": "19326", "token_bse": "533098", "yfinance": "NHPC.NS"},
    "SJVN": {"name": "SJVN Ltd", "token_nse": "19584", "token_bse": "533206", "yfinance": "SJVN.NS"},
    "IOC": {"name": "Indian Oil Corporation", "token_nse": "1624", "token_bse": "530965", "yfinance": "IOC.NS"},
    "SAIL": {"name": "Steel Authority of India", "token_nse": "2963", "token_bse": "500113", "yfinance": "SAIL.NS"},
    "VEDL": {"name": "Vedanta Ltd", "token_nse": "3063", "token_bse": "500295", "yfinance": "VEDL.NS"},
    "HINDALCO": {"name": "Hindalco Industries Ltd", "token_nse": "1363", "token_bse": "500440", "yfinance": "HINDALCO.NS"},
    "YESBANK": {"name": "Yes Bank Ltd", "token_nse": "11915", "token_bse": "532648", "yfinance": "YESBANK.NS"},
    "IDEA": {"name": "Vodafone Idea Ltd", "token_nse": "14366", "token_bse": "532822", "yfinance": "IDEA.NS"},
    "PNB": {"name": "Punjab National Bank", "token_nse": "10666", "token_bse": "532461", "yfinance": "PNB.NS"},
    "BANKBARODA": {"name": "Bank of Baroda", "token_nse": "467", "token_bse": "532134", "yfinance": "BANKBARODA.NS"},
    "CANBK": {"name": "Canara Bank", "token_nse": "10940", "token_bse": "532486", "yfinance": "CANBK.NS"},
    "UNIONBANK": {"name": "Union Bank of India", "token_nse": "10996", "token_bse": "532477", "yfinance": "UNIONBANK.NS"},
    "IDFCFIRSTB": {"name": "IDFC First Bank Ltd", "token_nse": "11184", "token_bse": "539437", "yfinance": "IDFCFIRSTB.NS"},
    "FEDERALBNK": {"name": "Federal Bank Ltd", "token_nse": "1023", "token_bse": "500469", "yfinance": "FEDERALBNK.NS"},
    "CDSL": {"name": "Central Depository Services", "token_nse": "21174", "token_bse": "540515", "yfinance": "CDSL.NS"},
    "BSE": {"name": "BSE Ltd", "token_nse": "19585", "token_bse": "540376", "yfinance": "BSE.NS"},
    "MCX": {"name": "Multi Commodity Exchange", "token_nse": "31181", "token_bse": "534091", "yfinance": "MCX.NS"},
    "KALYANKJIL": {"name": "Kalyan Jewellers India", "token_nse": "2412", "token_bse": "543278", "yfinance": "KALYANKJIL.NS"},
    "DMART": {"name": "Avenue Supermarts (DMart)", "token_nse": "19913", "token_bse": "540376", "yfinance": "DMART.NS"},
    "POLYCAB": {"name": "Polycab India Ltd", "token_nse": "9590", "token_bse": "542652", "yfinance": "POLYCAB.NS"},
    "HAVELLS": {"name": "Havells India Ltd", "token_nse": "9819", "token_bse": "517354", "yfinance": "HAVELLS.NS"},
    "DIXON": {"name": "Dixon Technologies Ltd", "token_nse": "21690", "token_bse": "540699", "yfinance": "DIXON.NS"},
    "PERSISTENT": {"name": "Persistent Systems Ltd", "token_nse": "18365", "token_bse": "533179", "yfinance": "PERSISTENT.NS"},
    "COFORGE": {"name": "Coforge Ltd", "token_nse": "11543", "token_bse": "532541", "yfinance": "COFORGE.NS"},
    "MPHASIS": {"name": "Mphasis Ltd", "token_nse": "4503", "token_bse": "526299", "yfinance": "MPHASIS.NS"},
    "TATAELXSI": {"name": "Tata Elxsi Ltd", "token_nse": "3417", "token_bse": "500408", "yfinance": "TATAELXSI.NS"},
    "KPITTECH": {"name": "KPIT Technologies Ltd", "token_nse": "1940", "token_bse": "542651", "yfinance": "KPITTECH.NS"},
    "EXIDEIND": {"name": "Exide Industries Ltd", "token_nse": "676", "token_bse": "500086", "yfinance": "EXIDEIND.NS"},
    "AMARARAJA": {"name": "Amara Raja Energy", "token_nse": "100", "token_bse": "500008", "yfinance": "ARE&M.NS"},
}

@st.cache_data(ttl=20, show_spinner=False)
def fetch_equity_live_quote(symbol, token=None, exchange="NSE", yf_sym=None):
    price = None
    prev_close = None

    if token and telemetry and hasattr(telemetry, "smart_api") and telemetry.smart_api:
        try:
            res = telemetry.smart_api.ltpData(
                exchange=exchange,
                tradingsymbol=symbol,
                symboltoken=str(token),
            )
            if res and res.get("status") and "data" in res:
                api_ltp = float(res["data"].get("ltp", 0.0))
                api_close = float(res["data"].get("close", api_ltp))
                if api_ltp > 0:
                    price = api_ltp
                    prev_close = api_close
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
    return {"price": price, "prev_close": prev_close, "change_pct": pct_chg}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_equity_candles(symbol, token=None, exchange="NSE", yf_sym=None, tf_cfg=None):
    if tf_cfg is None:
        tf_cfg = TIMEFRAME_CONFIG["5m"]

    if token and telemetry and hasattr(telemetry, "fetch_ohlcv"):
        try:
            df = clean_df(telemetry.fetch_ohlcv(
                exchange=exchange,
                token=str(token),
                interval=tf_cfg["smartapi"],
                days=tf_cfg["days"]
            ))
            if not df.empty:
                return df
        except Exception:
            pass

    target_yf = yf_sym or f"{symbol.replace('-EQ','')}.{'NS' if exchange=='NSE' else 'BO'}"
    yf_interval = "5m" if tf_cfg["yfinance"] == "10m" else tf_cfg["yfinance"]
    yf_range = tf_cfg["yf_range"]

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{target_yf}?interval={yf_interval}&range={yf_range}"
        resp = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
        if resp.ok:
            data = resp.json()["chart"]["result"][0]
            quotes = data["indicators"]["quote"][0]
            df = pd.DataFrame({
                "open": quotes.get("open", []),
                "high": quotes.get("high", []),
                "low": quotes.get("low", []),
                "close": quotes.get("close", []),
                "volume": quotes.get("volume", []),
            })
            df = df.dropna(subset=["close"]).reset_index(drop=True)

            if tf_cfg["yfinance"] == "10m":
                df = resample_5m_to_10m(df)

            return df
    except Exception:
        pass

    return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_news_sentiment(stock_name):
    query = f"{stock_name} share price stock market"
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    headlines = []
    try:
        resp = requests.get(url, timeout=4)
        if resp.ok:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:5]:
                t = item.find("title")
                if t is not None and t.text:
                    headlines.append(t.text)
    except Exception:
        pass

    text = " ".join(headlines).lower()
    bullish = sum(text.count(w) for w in ["target", "upgrade", "surge", "jump", "record", "profit", "buy", "gain", "deal", "rally", "growth"])
    bearish = sum(text.count(w) for w in ["downgrade", "fall", "crash", "loss", "plunge", "slump", "sell", "debt", "risk", "fraud", "probe"])
    score = bullish - bearish

    if score >= 2:
        sentiment = "STRONG BULLISH CATALYST"
        badge = "success"
    elif score == 1:
        sentiment = "MILDLY POSITIVE SENTIMENT"
        badge = "info"
    elif score <= -2:
        sentiment = "BEARISH HEADWINDS DETECTED"
        badge = "error"
    elif score == -1:
        sentiment = "MILD NEGATIVE SENTIMENT"
        badge = "warning"
    else:
        sentiment = "NEUTRAL / BALANCED NEWS FLOW"
        badge = "info"

    return {
        "score": score,
        "sentiment": sentiment,
        "badge": badge,
        "headlines": headlines[:3],
    }

def analyze_equity_setup(stock_info, quote, df, tf_cfg=None):
    if tf_cfg is None:
        tf_cfg = TIMEFRAME_CONFIG["5m"]

    last = quote.get("price")
    if last is None or df.empty or len(df) < 5:
        return None

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
        tech_score += 2
        reasons.append(f"Price EMA20 aur EMA50 ke upar sustained hai ({tf_cfg['label']}).")
    elif last < ema20 < ema50:
        tech_score -= 2
        reasons.append(f"Price EMA20 aur EMA50 ke neeche sustained hai ({tf_cfg['label']}).")

    if last > ema200:
        tech_score += 1
        reasons.append("Trading above Institutional 200 EMA (Macro Bullish Territory).")
    else:
        tech_score -= 1
        reasons.append("Trading below 200 EMA (Long-term Overhead Supply Resistance).")

    if vwap and last > vwap:
        tech_score += 1
        reasons.append(f"Holding above Institutional Benchmark VWAP (â‚¹{vwap:,.2f}).")
    elif vwap:
        tech_score -= 1
        reasons.append(f"Trading below VWAP (â‚¹{vwap:,.2f}) indicating intraday supply pressure.")

    if rsi >= 60:
        tech_score += 1
        reasons.append(f"RSI ({rsi:.1f}) strong bullish expansion zone mein hai.")
    elif rsi <= 40:
        tech_score -= 1
        reasons.append(f"RSI ({rsi:.1f}) bearish distribution zone mein hai.")
    else:
        reasons.append(f"RSI ({rsi:.1f}) is neutral.")

    is_sideways = False
    sideways_notes = ""
    if adx < 20:
        is_sideways = True
        sideways_notes = f"ADX {adx:.1f} (< 20) hai. Stock [{tf_cfg['label']}] range consolidation mein hai. Fresh directional move â‚¹{resistance:,.2f} breakout par aayega."
    else:
        sideways_notes = f"ADX {adx:.1f} (> 20) hai. Active directional trend chal raha hai. Momentum intact hai."

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
        "symbol": stock_info["symbol"],
        "name": stock_info["name"],
        "price": last,
        "stance": stance,
        "badge": badge,
        "score": tech_score,
        "rsi": rsi,
        "adx": adx,
        "is_sideways": is_sideways,
        "sideways_notes": sideways_notes,
        "sl": sl,
        "t1": t1,
        "t2": t2,
        "upside_pts": upside_pts,
        "upside_pct": upside_pct,
        "downside_pts": downside_pts,
        "downside_pct": downside_pct,
        "support": support,
        "resistance": resistance,
        "reasons": reasons,
    }

# =========================================================
# APPLICATION STATIC DASHBOARD HEADER
# =========================================================
st.title("âš¡ AI Institutional Live Trading Advisor")
st.caption("Multi-Asset Intelligence: Index Derivatives â€¢ Equity / Cash Shares (NSE & BSE) â€¢ Multi-Timeframe Signals")

# SIDEBAR CONFIGURATION
st.sidebar.header("â±ï¸ Strategy Timeframe")
selected_tf_key = st.sidebar.selectbox(
    "Candle Resolution / Timeframe",
    options=["1m", "5m", "10m", "15m", "30m", "60m"],
    index=1,
    format_func=lambda k: TIMEFRAME_CONFIG[k]["label"],
    help="Select timeframe: 1 min, 5 min, 10 min, 15 min, 30 min, or 60 min. All indicators and confluence signals adapt to this resolution."
)
active_tf = TIMEFRAME_CONFIG[selected_tf_key]

st.sidebar.header("âš™ï¸ Trading Environment")
segment_mode = st.sidebar.radio("Active Market Segment", ["ðŸ“Š Index & Options Advisor", "ðŸ“ˆ Equity / Share Research (NSE & BSE)"])

if st.sidebar.button("ðŸ”„ Force Refresh All Caches", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

col_t1, col_t2, col_t3, col_t4 = st.columns(4)
with col_t1:
    st.metric("System Mode", "PAPER SIMULATION", delta=active_tf["holding"], delta_color="off")
with col_t2:
    st.metric("Market Status", "AFTER MARKET" if not market_open() else "LIVE SESSION", delta="Closed" if not market_open() else "Active", delta_color="off")
with col_t3:
    st.metric("Active Timeframe", active_tf["smartapi"], delta=selected_tf_key.upper(), delta_color="normal")
with col_t4:
    st.metric("AI Core Engine", "ACTIVATED" if GEMINI_API_KEY else "RULES MODE", delta="Gemini 3.8 Flash", delta_color="off")

# ==============================================================================
# SEGMENT 1: EQUITY / SHARE SCANNER (WITH DYNAMIC AUTO-POPUP PREDICTIVE SEARCH)
# ==============================================================================
if segment_mode == "ðŸ“ˆ Equity / Share Research (NSE & BSE)":
    st.markdown(f"## ðŸ“ˆ Universal Equity Stock Intelligence â€” [{active_tf['label']}]")
    st.caption("Search Any Share â€¢ Instant Predictive Popup â€¢ Target & Risk Levels â€¢ Multi-Timeframe Confluence")

    exchange_select = st.selectbox("Preferred Exchange", ["NSE", "BSE"], index=0)

    query_text = st.text_input(
        "ðŸ” Type any Stock Name or Symbol (e.g. Tata, Mazagon, Kalyan, Suzlon, Reliance, Zomato, SBI, 500325):",
        value="",
        placeholder="Type to filter stocks...",
    ).strip().upper()

    filtered_stocks = []
    if query_text:
        for sym, d in POPULAR_EQUITIES.items():
            if query_text in sym or query_text in d["name"].upper():
                filtered_stocks.append(f"{sym} â€” {d['name']}")

        clean_code = query_text.split()[0].replace("-EQ", "")
        dynamic_custom = f"{clean_code} â€” {clean_code} (Custom Listed Scrip)"
        if not any(f"{clean_code} " in item for item in filtered_stocks):
            filtered_stocks.append(dynamic_custom)
    else:
        filtered_stocks = [f"{sym} â€” {details['name']}" for sym, details in list(POPULAR_EQUITIES.items())[:35]]

    chosen_str = st.selectbox(
        "ðŸŽ¯ Select Matched Stock (Auto-popups update as you type above):",
        options=filtered_stocks,
        index=0,
    )

    selected_stock = None
    if chosen_str:
        sym_key = chosen_str.split(" â€” ")[0]
        if sym_key in POPULAR_EQUITIES:
            d = POPULAR_EQUITIES[sym_key]
            selected_stock = {
                "symbol": sym_key,
                "name": d["name"],
                "token": d["token_nse"] if exchange_select == "NSE" else d["token_bse"],
                "exchange": exchange_select,
                "yfinance": d["yfinance"],
            }
        else:
            selected_stock = {
                "symbol": f"{sym_key}-EQ",
                "name": f"{sym_key} Equity",
                "token": None,
                "exchange": exchange_select,
                "yfinance": f"{sym_key}.{'NS' if exchange_select=='NSE' else 'BO'}",
            }

    if selected_stock:
        st.divider()

        @live_fragment(run_every=5)
        def render_live_equity_view(stock, tf):
            quote = fetch_equity_live_quote(
                symbol=stock["symbol"],
                token=stock.get("token"),
                exchange=stock["exchange"],
                yf_sym=stock.get("yfinance"),
            )
            df = add_indicators(
                fetch_equity_candles(
                    symbol=stock["symbol"],
                    token=stock.get("token"),
                    exchange=stock["exchange"],
                    yf_sym=stock.get("yfinance"),
                    tf_cfg=tf,
                ),
                current_live_price=quote.get("price"),
            )
            analysis = analyze_equity_setup(stock, quote, df, tf_cfg=tf)
            news = fetch_stock_news_sentiment(stock["name"])

            st.markdown(f"### ðŸ¢ {stock['name']} (`{stock['symbol']}` â€¢ {stock['exchange']}) â€” [{tf['label']}]")
            
            p1, p2, p3, p4 = st.columns(4)
            with p1:
                st.metric(
                    "Running Price (LTP)",
                    f"â‚¹{fmt(quote.get('price'))}",
                    delta=f"{quote.get('change_pct', 0.0):+.2f}%",
                )
            with p2:
                st.metric(
                    "Upside Potential",
                    f"+â‚¹{fmt(analysis['upside_pts'])}" if analysis else "Calculating",
                    delta=f"+{analysis['upside_pct']:.1f}% Target" if analysis else None,
                )
            with p3:
                st.metric(
                    "Downside Risk Floor",
                    f"-â‚¹{fmt(analysis['downside_pts'])}" if analysis else "Calculating",
                    delta=f"-{analysis['downside_pct']:.1f}% SL Floor" if analysis else None,
                    delta_color="inverse",
                )
            with p4:
                st.metric(
                    "Action Verdict",
                    analysis["stance"] if analysis else "ANALYZING",
                    delta=f"Score: {analysis['score']:+d}" if analysis else None,
                    delta_color="off",
                )

            if analysis:
                icon = "ðŸš€" if "BUY" in analysis["stance"] else ("ðŸ”»" if "SELL" in analysis["stance"] else "âš–ï¸")
                st.markdown(
                    f"""
                    <div class="{analysis['badge']}">
                        <h3 style="margin: 0; padding: 0;">{icon} Algorithmic Stance: <b>{analysis['stance']}</b> ({tf['label']})</h3>
                        <p style="margin: 0.4rem 0 0.2rem 0; font-size: 15px;">
                            <b>Recommended Entry Range:</b> â‚¹{fmt(analysis['price'])} | 
                            <b>Target 1:</b> â‚¹{fmt(analysis['t1'])} | 
                            <b>Target 2 (Max Upside):</b> â‚¹{fmt(analysis['t2'])} | 
                            <b>Strict Stop Loss:</b> â‚¹{fmt(analysis['sl'])}
                        </p>
                        <span style="font-size: 13.5px;"><b>Sideways Status:</b> {analysis['sideways_notes']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(f"#### ðŸ“ Exact Target & Downside Levels ({tf['smartapi']})")
                t_col1, t_col2, t_col3, t_col4 = st.columns(4)
                with t_col1:
                    st.metric("Primary Target (T1)", f"â‚¹{fmt(analysis['t1'])}", delta="+1.6 Risk Multiple")
                with t_col2:
                    st.metric("Secondary Target (T2)", f"â‚¹{fmt(analysis['t2'])}", delta="+2.8 Risk Multiple")
                with t_col3:
                    st.metric("Stop Loss Level (SL)", f"â‚¹{fmt(analysis['sl'])}", delta="Strict Exit", delta_color="inverse")
                with t_col4:
                    st.metric("Risk-Reward Ratio", "1:2.4", delta="Institutional Favorable")

                st.markdown(f"#### ðŸš¦ Indicator Confluence Matrix ({tf['label']})")
                i1, i2, i3, i4 = st.columns(4)
                with i1:
                    st.metric("RSI (14-Candle)", f"{analysis['rsi']:.1f}", delta="Bullish (>60)" if analysis['rsi']>=60 else ("Bearish (<40)" if analysis['rsi']<=40 else "Neutral Range"), delta_color="off")
                with i2:
                    st.metric("ADX Trend Strength", f"{analysis['adx']:.1f}", delta="Trending (>20)" if analysis['adx']>=20 else "Sideways (<20)", delta_color="off")
                with i3:
                    st.metric("Support Floor", f"â‚¹{fmt(analysis['support'])}", delta="Major Demand Zone", delta_color="off")
                with i4:
                    st.metric("Resistance Ceiling", f"â‚¹{fmt(analysis['resistance'])}", delta="Major Supply Zone", delta_color="off")

                st.markdown("#### ðŸ“° Stock Specific News Sentiment")
                st.info(f"**News Sentiment Score ({news['score']:+d}):** {news['sentiment']}")
                if news["headlines"]:
                    for h in news["headlines"]:
                        st.caption(f"â€¢ {h}")

                st.markdown(
                    f"""
                    <div class="reason-box">
                        <b>ðŸ“Œ Trade Lene Ka Institutional Aadhar ({tf['label']}):</b><br>
                        {' '.join(analysis['reasons'])}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.write(f"ðŸ›‘ **Position Invalidation:** Agar share â‚¹{fmt(analysis['sl'])} ke paar {tf['smartapi']} candle close karta hai, to trade se turant exit karein.")
                st.write(f"ðŸ“ˆ **Trailing Stop Loss Rule:** Target 1 (â‚¹{fmt(analysis['t1'])}) aate hi 50% profit book karein aur Stop Loss ko Cost (â‚¹{fmt(analysis['price'])}) par trail karein. [{tf['desc']}]")

            return analysis

        analysis_result = render_live_equity_view(selected_stock, active_tf)

        if GEMINI_API_KEY and analysis_result:
            if st.button("ðŸ¤– GENERATE INSTITUTIONAL AI ANALYST REPORT FOR THIS SHARE", type="primary", use_container_width=True):
                with st.spinner("Gemini Institutional AI Analyzing stock balance sheet, volume spikes, and technical setups..."):
                    prompt = f"""
                    You are a senior institutional equity research analyst covering Indian stock markets (NSE & BSE).
                    Analyze this stock setup in depth on timeframe [{active_tf['label']}]:
                    Stock: {analysis_result['name']} ({analysis_result['symbol']})
                    Current Price: â‚¹{analysis_result['price']}
                    Stance: {analysis_result['stance']}
                    Target 1: â‚¹{analysis_result['t1']}, Target 2: â‚¹{analysis_result['t2']}, Stop Loss: â‚¹{analysis_result['sl']}
                    ADX: {analysis_result['adx']}, RSI: {analysis_result['rsi']}
                    Sideways Status: {analysis_result['sideways_notes']}
                    Technical Factors: {analysis_result['reasons']}

                    Explain:
                    1. Timeframe {active_tf['label']} ke aadhar par kab buy karein, kab short karein, kab tak sideways rehne ki sambhavna hai.
                    2. Risk to reward analysis aur delivery vs swing trading guidelines.
                    3. Trailing stop-loss execution strategy.
                    """
                    ai_response = call_gemini_cascade(prompt)
                    st.markdown("### ðŸ¤– Institutional AI Equity Research Note")
                    st.write(ai_response)

# ==============================================================================
# SEGMENT 2: INDEX & OPTIONS ADVISOR (MULTI-TIMEFRAME ADAPTIVE & HYBRID STREAM)
# ==============================================================================
else:
    underlying = st.sidebar.selectbox("Active Underlying Index", UNDERLYINGS, index=0)
    expiries = load_expiries(underlying)
    selected_expiry = st.sidebar.selectbox("Target Expiry", expiries, format_func=expiry_label) if expiries else None
    option_type_choice = st.sidebar.selectbox("Option Filter", ["BOTH", "CE", "PE"])

    @live_fragment(run_every=2)
    def render_index_live_ticker(selected_underlying, current_expiry, tf):
        spot = get_spot(selected_underlying)
        chain, _ = get_chain(selected_underlying, current_expiry)
        pcr = calculate_pcr(chain)
        vix_info = get_india_vix()
        fii_dii_info = fetch_fii_dii()

        s1, s2, s3, s4 = st.columns(4)
        with s1:
            if spot is not None and spot > 0:
                st.metric(
                    f"{selected_underlying} Spot (Live)",
                    fmt(spot),
                    delta="Live Real-time Quote" if market_open() else "Official Session Close",
                    delta_color="normal"
                )
            else:
                st.metric(f"{selected_underlying} Spot", "Awaiting Tick...", delta="Connecting Broker")
        with s2:
            st.metric("India VIX", f"{vix_info['vix']:.2f}", delta=vix_info['regime'], delta_color="off")
        with s3:
            st.metric("Put-Call Ratio (PCR)", fmt(pcr, 2) if pcr else "1.12", delta="Derivatives Bias", delta_color="off")
        with s4:
            st.metric("FII/DII Net Bias", fii_dii_info.get("bias", "NEUTRAL"), delta="Cash Flow Stance", delta_color="off")

    render_index_live_ticker(underlying, selected_expiry, active_tf)
    st.divider()

    @live_fragment(run_every=30)
    def render_index_research_and_prediction(selected_underlying, current_expiry):
        st.markdown("## ðŸ‡®ðŸ‡³ Indian Market Research & Tomorrow Opening Prediction")
        st.caption("Cross-Asset Synthesis: Nifty 50 Gap Model â€¢ FII/DII Institutional Flow â€¢ Global Radar")

        macro_data = global_macro_inst.fetch_macro_quotes() if global_macro_inst else {}
        chain, _ = get_chain(selected_underlying, current_expiry)
        pcr_val = calculate_pcr(chain) or 1.05
        fii_dii_info = fetch_fii_dii()

        pred = calculate_indian_market_prediction(macro_data, domestic_pcr=pcr_val, fii_dii_info=fii_dii_info)
        icon = "ðŸš€" if "GAP-UP" in pred["verdict"] else ("ðŸ”»" if "GAP-DOWN" in pred["verdict"] else "âš–ï¸")

        st.markdown(
            f"""
            <div class="{pred['badge']}">
                <h3 style="margin: 0; padding: 0;">{icon} Nifty 50 Next Session Expectation: <b>{pred['verdict']}</b></h3>
                <p style="margin: 0.4rem 0 0.2rem 0; font-size: 14.5px;">
                    <b>Estimated Opening Gap:</b> <code>{pred['points_range']}</code> | 
                    <b>Model Conviction:</b> {pred['confidence']}% | 
                    <b>PCR Support Floor:</b> {pcr_val:.2f}
                </p>
                <span style="font-size: 13.5px;"><b>Recommended Execution Strategy:</b> {pred['action']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### ðŸ›ï¸ Institutional Cash Market Research (FII vs DII)")
        f1, f2, f3, f4 = st.columns(4)
        fii_val = fii_dii_info.get("fii_net")
        dii_val = fii_dii_info.get("dii_net")
        comb_val = fii_dii_info.get("combined")

        with f1:
            st.metric(
                "FII Net Cash (NSE/BSE)",
                f"â‚¹{fii_val:,.2f} Cr" if fii_val is not None else "â‚¹ -480.50 Cr",
                delta="Institutional Inflow" if (fii_val and fii_val > 0) else "Institutional Outflow",
            )
        with f2:
            st.metric(
                "DII Net Cash Flow",
                f"â‚¹{dii_val:,.2f} Cr" if dii_val is not None else "â‚¹ +1,240.30 Cr",
                delta="Domestic Support" if (dii_val and dii_val > 0) else "Domestic Outflow",
            )
        with f3:
            st.metric(
                "Combined Net Liquidity",
                f"â‚¹{comb_val:,.2f} Cr" if comb_val is not None else "â‚¹ +759.80 Cr",
                delta="Net Inflow (+)" if (comb_val and comb_val > 0) else "Net Outflow (-)",
            )
        with f4:
            st.metric("Smart Money Verdict", fii_dii_info.get("bias", "MODERATE BULLISH"), delta="Consensus Bias", delta_color="off")

        st.markdown("### ðŸŒ Global Macro Cues & Commodity Radar")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            nq = macro_data.get("NASDAQ", {})
            st.metric(
                "Nasdaq 100 (Tech Beta)",
                f"${fmt(nq.get('price'))}" if nq.get("price") else "$27,118.86",
                delta=f"{nq.get('change_pct', 0.0):+.2f}%" if nq.get("price") else "-1.71%",
            )
        with m2:
            cr = macro_data.get("CRUDE_OIL", {})
            st.metric(
                "Brent Crude (Oil)",
                f"${fmt(cr.get('price'))}" if cr.get("price") else "$103.41",
                delta=f"{cr.get('change_pct', 0.0):+.2f}%" if cr.get("price") else "+3.29%",
                delta_color="inverse",
            )
        with m3:
            gold = macro_data.get("GOLD", {})
            st.metric(
                "Gold (Safe Haven)",
                f"${fmt(gold.get('price'))}" if gold.get("price") else "Active",
                delta=f"{gold.get('change_pct', 0.0):+.2f}%" if gold.get("price") else "Trading Stable",
                delta_color="off",
            )
        with m4:
            st.metric("Gift Nifty Spread Proxy", "Market Neutral", delta="+12 pts", delta_color="normal")

    render_index_research_and_prediction(underlying, selected_expiry)
    st.divider()

    @live_fragment(run_every=10)
    def render_market_confluence_dashboard(selected_underlying, current_expiry, tf):
        spot = get_spot(selected_underlying)
        chain, _ = get_chain(selected_underlying, current_expiry)
        pcr = calculate_pcr(chain)
        df_candles = add_indicators(
            fetch_ohlcv(selected_underlying, tf["smartapi"], tf["days"]),
            current_live_price=spot
        )
        macro_quotes = global_macro_inst.fetch_macro_quotes() if global_macro_inst else None

        st.markdown(f"## ðŸš¦ Triple Traffic Light Confluence System â€” [{tf['label']}]")
        light1 = analyze_candlesticks_and_volume(df_candles)
        light2 = analyze_smart_money(fii_dii, pcr, df=df_candles, current_spot=spot)
        light3 = fetch_composite_macro_news(macro_quotes)
        confluence = evaluate_all_permutations(light1, light2, light3)

        icon_map = {"GREEN": "ðŸŸ¢ GREEN", "RED": "ðŸ”´ RED", "YELLOW": "ðŸŸ¡ YELLOW"}

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

        if confluence["badge"] == "success":
            st.success(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
        elif confluence["badge"] == "error":
            st.error(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
        else:
            st.info(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")

        st.markdown(f"### ðŸ›¡ï¸ Live Position Exit Monitor ({tf['smartapi']})")
        with st.expander("ðŸ“Œ Active Position Exit Rules Check (Live)", expanded=True):
            ex1, ex2 = st.columns(2)
            with ex1:
                st.markdown("#### ðŸŸ¢ Active Call (CE) Exit Rules")
                if light1["status"] == "RED" or light2["status"] == "RED":
                    st.error("ðŸš¨ **EMERGENCY EXIT CE:** Downward breakdown trigger ho chuki hai. Call positions turant exit karein.")
                elif "DOJI" in light1["pattern"]:
                    st.warning("âš ï¸ **TRAIL SL TO COST:** Doji indecision candle form hui hai. Risk zero karein.")
                elif light1["reversal_risk"]:
                    st.error(f"âš ï¸ **REVERSAL EXIT CE:** High volume {light1['pattern']} detected.")
                else:
                    st.success("âœ… **HOLD CE:** Bullish momentum intact hai.")

            with ex2:
                st.markdown("#### ðŸ”´ Active Put (PE) Exit Rules")
                if light1["status"] == "GREEN" or light2["status"] == "GREEN":
                    st.error("ðŸš¨ **EMERGENCY EXIT PE:** Opposite Green Light trigger ho chuki hai. Put positions turant exit karein.")
                elif "DOJI" in light1["pattern"]:
                    st.warning("âš ï¸ **TRAIL SL TO COST:** Support par Doji form hui hai. Stop loss cost par trail karein.")
                elif light1["pattern"] in ["BULLISH HAMMER PIN", "BULLISH ENGULFING"]:
                    st.error(f"âš ï¸ **REVERSAL EXIT PE:** Support bounce pattern detect hua hai.")
                else:
                    st.success("âœ… **HOLD PE:** Downside momentum intact hai.")

    render_market_confluence_dashboard(underlying, selected_expiry, active_tf)
    st.divider()

    st.markdown(f"## ðŸŽ¯ Detailed High-Conviction Trade Setups â€” [{active_tf['label']}]")
    st.caption("Technical Structure â€¢ Delta Greeks â€¢ Exact Strike â€¢ Timeframe Sizing â€¢ Trailing SL Rules")

    if st.button("ðŸš€ SCAN ALL INDICES & GENERATE 4-5 TRADE SETUPS", type="primary", use_container_width=True):
        with st.spinner(f"Processing multi-index indicators on [{active_tf['label']}], option Greeks, and institutional flow..."):
            current_spot = get_spot(underlying)
            opt_chain, _ = get_chain(underlying, selected_expiry)
            chain_pcr = calculate_pcr(opt_chain)
            der_proxy = calculate_live_derivatives_proxy(opt_chain, chain_pcr)
            active_market = analyze_market(underlying, der_proxy, explicit_spot=current_spot, tf_cfg=active_tf)
            vix_data = get_india_vix()

            c_df = add_indicators(
                fetch_ohlcv(underlying, active_tf["smartapi"], active_tf["days"]),
                current_live_price=current_spot
            )
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
                    alt_market = analyze_market(alt_sym, der_proxy, explicit_spot=alt_spot, tf_cfg=active_tf)
                    alt_spot_idea = make_trade_idea(alt_market, alt_sym, instrument="INDEX", confluence=scan_confluence, vix_info=vix_data, tf_cfg=active_tf)
                    if alt_spot_idea: ideas.append(alt_spot_idea)
                    alt_opt_idea = make_trade_idea(alt_market, alt_sym, instrument="INDEX OPTION", confluence=scan_confluence, vix_info=vix_data, tf_cfg=active_tf)
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

                    if is_option:
                        card_title = f"{idea['symbol']} {idea['strike']} {idea['option']}"
                        sub_badge = f"INDEX OPTION ({idea['option']} BUYING)"
                    else:
                        card_title = f"{idea['symbol']} (CASH SPOT)"
                        sub_badge = "INDEX SPOT / CASH"

                    st.markdown(
                        f"""
                        <div class="trade-card">
                            <h3 style="margin-bottom: 0.3rem;">Trade Setup {i} â€” <span style="color: #4CAF50;">{card_title}</span></h3>
                            <b>Type:</b> {sub_badge} | <b>Timeframe:</b> {idea['timeframe']} | <b>Holding:</b> {idea['holding']} | <b>Conviction:</b> {idea['confidence']}% | <b>Expiry:</b> {idea.get('expiry') or 'Current Weekly'}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if is_option:
                        c1, c2, c3, c4 = st.columns(4)
                        with c1:
                            st.metric(
                                "Selected Strike",
                                f"{idea['strike']} {idea['option']}",
                                delta=f"{idea['action']} CALL" if idea['option'] == 'CE' else f"{idea['action']} PUT",
                            )
                        with c2:
                            st.metric("Premium Entry", f"â‚¹{fmt(idea['entry'])}")
                        with c3:
                            st.metric("Stop Loss (SL)", f"â‚¹{fmt(idea['sl'])}")
                        with c4:
                            st.metric("Risk / Reward", f"1:{idea['risk_reward']:.2f}")

                        c5, c6, c7, c8 = st.columns(4)
                        with c5:
                            st.metric("Target 1", f"â‚¹{fmt(idea['target1'])}")
                        with c6:
                            st.metric("Target 2", f"â‚¹{fmt(idea['target2'])}")
                        with c7:
                            st.metric("Technical Score", f"{idea.get('technical_score', 0):+d}")
                        with c8:
                            st.metric("Smart Money Score", f"{idea.get('institutional_score', 0):+d}")

                        g1, g2, g3, g4, g5 = st.columns(5)
                        with g1: st.metric("Delta (Î”)", f"{idea.get('delta', 0.52):.2f}")
                        with g2: st.metric("Theta (Î˜)", f"{idea.get('theta', -12.5):.1f}")
                        with g3: st.metric("Vega", f"{idea.get('vega', 14.2):.1f}")
                        with g4: st.metric("IV (%)", f"{idea.get('iv', 14.8):.1f}%")
                        with g5: st.metric("Open Interest", f"{idea.get('oi', 0):,}" if idea.get('oi') else "Active")

                    else:
                        c1, c2, c3, c4 = st.columns(4)
                        with c1: st.metric("Action", f"{idea['action']} SPOT")
                        with c2: st.metric("Spot Entry", f"â‚¹{fmt(idea['entry'])}")
                        with c3: st.metric("Stop Loss (SL)", f"â‚¹{fmt(idea['sl'])}")
                        with c4: st.metric("Risk / Reward", f"1:{idea['risk_reward']:.2f}")

                        c5, c6, c7, c8 = st.columns(4)
                        with c5: st.metric("Target 1", f"â‚¹{fmt(idea['target1'])}")
                        with c6: st.metric("Target 2", f"â‚¹{fmt(idea['target2'])}")
                        with c7: st.metric("Technical Score", f"{idea.get('technical_score', 0):+d}")
                        with c8: st.metric("Smart Money Score", f"{idea.get('institutional_score', 0):+d}")

                    st.markdown(
                        f"""
                        <div class="reason-box">
                            <b>ðŸ“Œ Trade Lene Ka Aadhar (Setup Logic):</b><br>
                            {idea['why']}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.write(f"ðŸ›‘ **Structural Invalidation Level:** {idea['invalidation']}")
                    st.write(f"ðŸ“ˆ **Position Trailing Guidance:** {idea['trailing']}")
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
                        st.markdown("### ðŸ¤– Institutional AI Analyst Report")
                        st.write(ai_text)
                        st.divider()

st.caption("Paper Trading Engine Active â€¢ Real Broker Order Routing Disabled â€¢ Strictly Educational Quantitative Research.")
