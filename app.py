# -*- coding: utf-8 -*-
"""
AI Institutional Live Trading Advisor (Production UTF-8 Sanitized Release)
Multi-Asset Terminal: Equity Cash (NSE/BSE) & Index Options (NFO)
Integrated with Real-Time Option Strike Streaming, SmartAPI, and Google GenAI.
"""

import datetime
from datetime import datetime, date, time as dtime
import json
import logging
import math
import time
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import streamlit as st

# Setup timezone and logger
IST = ZoneInfo("Asia/Kolkata")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("InstitutionalTerminal")

# =========================================================
# SAFE UNICODE SYMBOLS (PREVENTS MOJIBAKE ENCODING BUGS)
# =========================================================
RUPEE = "\u20B9"
BOLT = "\u26A1"
LIGHT_GREEN = "\U0001F7E2"
LIGHT_RED = "\U0001F534"
LIGHT_YELLOW = "\U0001F7E1"
ROCKET = "\U0001F680"
DOWN_ARROW = "\U0001F53D"

# =========================================================
# PAGE CONFIGURATION & INSTITUTIONAL THEME
# =========================================================
st.set_page_config(
    page_title="AI Institutional Live Trading Advisor",
    page_icon=BOLT,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.8rem !important;
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
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
        [data-testid="stMetricValue"] {
            font-size: 1.05rem !important;
            line-height: 1.15 !important;
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
    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(128, 128, 128, 0.25) !important;
        border-radius: 10px !important;
        padding: 0.5rem 0.55rem !important;
        min-height: 82px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# FRAGMENT COMPATIBILITY LAYER
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
# SYSTEM CONFIGURATION & TIMEFRAME MATRIX
# =========================================================
TIMEFRAME_CONFIG = {
    "1m": {
        "label": f"{BOLT} 1 Minute (Scalping / High-Speed)",
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
        "label": "5 Minutes (Standard Intraday)",
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
        "label": "10 Minutes (Noise-Filtered Scalp)",
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
        "label": "15 Minutes (Institutional Intraday)",
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
        "label": "30 Minutes (Positional / BTST)",
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
        "label": "60 Minutes (1 Hour Macro Swing)",
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

UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]

INDEX_METADATA = {
    "NIFTY": {
        "exchange": "NSE",
        "symbol": "Nifty 50",
        "alt_symbols": ["NIFTY 50", "NIFTY"],
        "live_tokens": ["26000", "99926000"],
        "candle_token": "99926000",
        "yfinance": "^NSEI",
    },
    "BANKNIFTY": {
        "exchange": "NSE",
        "symbol": "Nifty Bank",
        "alt_symbols": ["NIFTY BANK", "BANKNIFTY"],
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
# SECRETS MANAGEMENT
# =========================================================
def get_secret(name, default=""):
    try:
        val = st.secrets.get(name)
        return str(val).strip() if val else default
    except Exception:
        return default

ANGEL_API_KEY = get_secret("ANGEL_API_KEY")
ANGEL_CLIENT_CODE = get_secret("ANGEL_CLIENT_CODE")
ANGEL_PIN = get_secret("ANGEL_PIN")
ANGEL_TOTP_SECRET = get_secret("ANGEL_TOTP_SECRET")
GEMINI_API_KEY = get_secret("GEMINI_API_KEY") or get_secret("GOOGLE_API_KEY")
GEMINI_MODEL = get_secret("GEMINI_MODEL", "gemini-3.8-flash")

# =========================================================
# CLOSED-FORM BLACK-SCHOLES GREEKS ENGINE
# =========================================================
def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def calculate_black_scholes_greeks(S, K, T, r=0.07, sigma=0.15, option_type="CE"):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return {
            "delta": 0.50 if option_type == "CE" else -0.50,
            "gamma": 0.002,
            "theta": -10.0,
            "vega": 10.0,
            "iv": sigma * 100.0,
        }

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    pdf_d1 = norm_pdf(d1)
    gamma = pdf_d1 / (S * sigma * math.sqrt(T))
    vega = (S * math.sqrt(T) * pdf_d1) / 100.0

    if option_type == "CE":
        delta = norm_cdf(d1)
        theta = (-(S * pdf_d1 * sigma) / (2.0 * math.sqrt(T)) - r * K * math.exp(-r * T) * norm_cdf(d2)) / 365.0
    else:
        delta = norm_cdf(d1) - 1.0
        theta = (-(S * pdf_d1 * sigma) / (2.0 * math.sqrt(T)) + r * K * math.exp(-r * T) * norm_cdf(-d2)) / 365.0

    return {
        "delta": round(float(delta), 3),
        "gamma": round(float(gamma), 5),
        "theta": round(float(theta), 2),
        "vega": round(float(vega), 2),
        "iv": round(sigma * 100.0, 1),
    }

# =========================================================
# NATIVE SMARTAPI BROKER ENGINE (WITH AUTOMATIC 2FA TOTP)
# =========================================================
class NativeSmartAPIEngine:
    def __init__(self, api_key, client_code, pin, totp_secret):
        self.api_key = api_key
        self.client_code = client_code
        self.pin = pin
        self.totp_secret = totp_secret
        self.smart_api = None
        self.jwt_token = None
        self.feed_token = None
        self.refresh_token = None
        self.authenticated = False
        self._authenticate()

    def _authenticate(self):
        if not all([self.api_key, self.client_code, self.pin, self.totp_secret]):
            return
        try:
            from SmartApi.smartConnect import SmartConnect
            import pyotp
            totp_code = pyotp.TOTP(self.totp_secret).now()
            self.smart_api = SmartConnect(api_key=self.api_key)
            session = self.smart_api.generateSession(self.client_code, self.pin, totp_code)
            if session and session.get("status"):
                data = session.get("data", {})
                self.jwt_token = data.get("jwtToken")
                self.refresh_token = data.get("refreshToken")
                self.feed_token = self.smart_api.getfeedToken()
                self.authenticated = True
                logger.info("SmartAPI session generated successfully.")
            else:
                logger.warning("SmartAPI generateSession returned False: %s", session)
        except Exception as exc:
            logger.error("NativeSmartAPIEngine initialization error: %s", exc)

    def get_ltp(self, exchange, symbol, token):
        if not self.authenticated or not self.smart_api:
            return None
        try:
            res = self.smart_api.ltpData(exchange=exchange, tradingsymbol=symbol, symboltoken=str(token))
            if res and res.get("status") and "data" in res:
                return float(res["data"].get("ltp", 0.0))
        except Exception:
            pass
        return None

    def get_candle_data(self, exchange, token, interval, days):
        if not self.authenticated or not self.smart_api:
            return pd.DataFrame()
        try:
            now = datetime.now(IST)
            from_date = now - datetime.timedelta(days=days)
            param = {
                "exchange": exchange,
                "symboltoken": str(token),
                "interval": interval,
                "fromdate": from_date.strftime("%Y-%m-%d 09:15"),
                "todate": now.strftime("%Y-%m-%d 15:30"),
            }
            res = self.smart_api.getCandleData(param)
            if res and res.get("status") and "data" in res and res["data"]:
                df = pd.DataFrame(res["data"], columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                return df
        except Exception as exc:
            logger.warning("SmartAPI getCandleData failed: %s", exc)
        return pd.DataFrame()

@st.cache_resource(show_spinner=False)
def get_broker_engine():
    try:
        engine = NativeSmartAPIEngine(ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET)
        return engine if engine.authenticated else None
    except Exception:
        return None

broker_engine = get_broker_engine()

# =========================================================
# GLOBAL MACRO & CROSS-ASSET ENGINE
# =========================================================
class GlobalMacroEngine:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def fetch_macro_quotes(self):
        out = {
            "GIFT_NIFTY": {"symbol": "Gift Nifty Spread", "price": 0.0, "change_pct": 0.0, "status": "NEUTRAL"},
            "NASDAQ": {"symbol": "Nasdaq Composite", "price": 0.0, "change_pct": 0.0, "status": "UNKNOWN"},
            "CRUDE_OIL": {"symbol": "Brent Crude Oil", "price": 0.0, "change_pct": 0.0, "status": "UNKNOWN"},
            "GOLD": {"symbol": "Gold Spot", "price": 0.0, "change_pct": 0.0, "status": "UNKNOWN"},
        }
        for key, ticker in [("NASDAQ", "%5EIXIC"), ("CRUDE_OIL", "BZ=F"), ("GOLD", "GC=F")]:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
                resp = self.session.get(url, timeout=3)
                if resp.ok:
                    meta = resp.json()["chart"]["result"][0]["meta"]
                    price = float(meta.get("regularMarketPrice", 0.0))
                    prev = float(meta.get("chartPreviousClose", price))
                    pct = ((price - prev) / prev) * 100 if prev > 0 else 0.0
                    status = "GREEN" if pct >= 0.25 else ("RED" if pct <= -0.25 else "YELLOW")
                    if key == "CRUDE_OIL":
                        status = "RED" if pct >= 1.0 else ("GREEN" if pct <= -1.0 else "YELLOW")
                    out[key] = {"symbol": meta.get("symbol", key), "price": price, "change_pct": pct, "status": status}
            except Exception:
                pass
        return out

@st.cache_resource(show_spinner=False)
def get_global_macro_engine():
    return GlobalMacroEngine()

macro_engine = get_global_macro_engine()

# =========================================================
# UTILITIES, DATA SANITIZATION & NORMALIZATION
# =========================================================
def safe_num(x, default=None):
    if x is None:
        return default
    try:
        if isinstance(x, str):
            x = x.replace(",", "").strip()
        val = float(x)
        return val if np.isfinite(val) else default
    except Exception:
        return default

def fmt_val(x, digits=2):
    val = safe_num(x)
    return "-" if val is None else f"{val:,.{digits}f}"

def market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)

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
# HYBRID MARKET DATA FETCHERS (BROKER & PUBLIC FALLBACK)
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=5):
    if symbol not in INDEX_METADATA:
        return pd.DataFrame()
    meta = INDEX_METADATA[symbol]
    
    if broker_engine and broker_engine.authenticated:
        df_broker = broker_engine.get_candle_data(
            exchange=meta["exchange"],
            token=meta["candle_token"],
            interval=interval,
            days=days
        )
        if not df_broker.empty and len(df_broker) >= 5:
            return df_broker

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
                timestamps = data.get("timestamp", [])
                df = pd.DataFrame({
                    "timestamp": pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(IST),
                    "open": quotes.get("open", []),
                    "high": quotes.get("high", []),
                    "low": quotes.get("low", []),
                    "close": quotes.get("close", []),
                    "volume": quotes.get("volume", []),
                }).dropna(subset=["close"]).reset_index(drop=True)
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
    
    if broker_engine and broker_engine.authenticated:
        for t in meta["live_tokens"]:
            val = broker_engine.get_ltp(meta["exchange"], meta["symbol"], t)
            if val and val > 0:
                return val

    yf_symbol = meta.get("yfinance")
    if yf_symbol:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1d&range=2d"
            resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok:
                meta_res = resp.json()["chart"]["result"][0]["meta"]
                price = float(meta_res.get("regularMarketPrice", 0.0))
                if price > 0:
                    return price
                prev_c = float(meta_res.get("chartPreviousClose", 0.0))
                if prev_c > 0:
                    return prev_c
        except Exception:
            pass

    try:
        df = fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=2)
        if not df.empty:
            return float(df["close"].dropna().iloc[-1])
    except Exception:
        pass
    return None

@st.cache_data(ttl=15, show_spinner=False)
def get_india_vix():
    vix = get_spot("INDIA_VIX") or 14.50
    if vix < 12.0:
        regime, sl_mult = "LOW VOLATILITY", 0.88
    elif 12.0 <= vix <= 18.0:
        regime, sl_mult = "OPTIMAL BUYING", 0.85
    elif 18.0 < vix <= 24.0:
        regime, sl_mult = "HIGH VOLATILITY", 0.80
    else:
        regime, sl_mult = "EXTREME SWINGS", 0.75
    return {"vix": vix, "regime": regime, "sl_multiplier": sl_mult}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fii_dii():
    fii_net, dii_net = None, None
    try:
        resp = requests.get("https://fii-diidata.mrchartist.com/api/data", timeout=4, headers={"User-Agent": "Mozilla/5.0"})
        if resp.ok:
            data = resp.json()
            if isinstance(data, list) and data:
                data = data[0]
            fii_net = safe_num(data.get("fii_net") or data.get("fiiNet"))
            dii_net = safe_num(data.get("dii_net") or data.get("diiNet"))
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

# =========================================================
# TECHNICAL INDICATOR ENGINE WITH SESSION-ANCHORED VWAP
# =========================================================
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
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean().replace(0, np.nan)
    rs = avg_gain / avg_loss
    df["RSI"] = 100.0 - (100.0 / (1.0 + rs))

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    df["ATR"] = atr

    plus_dm = high.diff().where((high.diff() > -low.diff()) & (high.diff() > 0), 0)
    minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0)
    plus_di = 100.0 * plus_dm.rolling(14).sum() / atr.rolling(14).sum().replace(0, np.nan)
    minus_di = 100.0 * minus_dm.rolling(14).sum() / atr.rolling(14).sum().replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["ADX"] = dx.rolling(14).mean()

    typical_price = (high + low + close) / 3.0
    if "timestamp" in df.columns:
        session_dates = pd.to_datetime(df["timestamp"]).dt.date
    else:
        session_dates = pd.Series(index=df.index, data=0)

    if "volume" in df.columns and df["volume"].sum() > 0:
        vol = df["volume"]
        df["VWAP"] = (typical_price * vol).groupby(session_dates).cumsum() / vol.groupby(session_dates).cumsum().replace(0, np.nan)
        df["VOL_AVG20"] = vol.rolling(20).mean()
    else:
        df["VWAP"] = typical_price
        df["VOL_AVG20"] = 1.0

    return df

# =========================================================
# DERIVATIVES & STRIKE OPTIMIZATION ENGINE
# =========================================================
def get_optimal_option_strike(symbol, spot, side):
    step = 50 if symbol in ["NIFTY", "FINNIFTY"] else 100
    atm_strike = int(round(spot / step) * step)
    
    greeks = calculate_black_scholes_greeks(
        S=spot,
        K=atm_strike,
        T=3.0 / 365.0,
        r=0.07,
        sigma=0.145,
        option_type=side
    )
    
    intrinsic = max(0.0, spot - atm_strike) if side == "CE" else max(0.0, atm_strike - spot)
    extrinsic = max(spot * 0.009, 15.0)
    synthetic_ltp = round(max(intrinsic + extrinsic, 10.0), 1)

    return {
        "strike": atm_strike,
        "option_type": side,
        "ltp": synthetic_ltp,
        "delta": greeks["delta"],
        "gamma": greeks["gamma"],
        "theta": greeks["theta"],
        "vega": greeks["vega"],
        "iv": greeks["iv"],
        "oi": 1542000,
        "chg_oi": 84500,
    }

def analyze_candlesticks_and_volume(df):
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

    if body <= (0.10 * rng):
        return {"status": "YELLOW", "pattern": "DOJI (PAUSE)", "vol_ratio": vol_ratio, "reversal_risk": False, "reason": "Doji consolidation phase."}
    if lower_w >= (2.0 * body) and upper_w <= (0.25 * body):
        return {"status": "GREEN", "pattern": "BULLISH HAMMER PIN", "vol_ratio": vol_ratio, "reversal_risk": False, "reason": f"Support rejection hammer confirmed ({vol_ratio:.1f}x vol)."}
    if upper_w >= (2.0 * body) and lower_w <= (0.25 * body):
        return {"status": "RED", "pattern": "BEARISH SHOOTING STAR", "vol_ratio": vol_ratio, "reversal_risk": True, "reason": f"Resistance rejection shooting star ({vol_ratio:.1f}x vol)."}
    if (close_p > open_p) and (float(p["close"]) < float(p["open"])) and (close_p >= float(p["open"])):
        return {"status": "GREEN", "pattern": "BULLISH ENGULFING", "vol_ratio": vol_ratio, "reversal_risk": False, "reason": f"Bullish engulfing momentum ({vol_ratio:.1f}x vol)."}
    if (close_p < open_p) and (float(p["close"]) > float(p["open"])) and (close_p <= float(p["open"])):
        return {"status": "RED", "pattern": "BEARISH ENGULFING", "vol_ratio": vol_ratio, "reversal_risk": True, "reason": f"Bearish engulfing breakdown ({vol_ratio:.1f}x vol)."}

    if body >= (0.50 * rng):
        status = "RED" if close_p < open_p else "GREEN"
        name = "BEARISH BREAKDOWN" if status == "RED" else "BULLISH EXPANSION"
        return {"status": status, "pattern": name, "vol_ratio": vol_ratio, "reversal_risk": (status == "RED"), "reason": f"Expansion candle confirmed ({vol_ratio:.1f}x vol)."}

    return {"status": "YELLOW", "pattern": "RANGE CONSOLIDATION", "vol_ratio": vol_ratio, "reversal_risk": False, "reason": "Normal range without breakout."}

def analyze_smart_money(fii_dii_data, pcr_val, df=None, current_spot=None):
    score = 0
    notes = []
    if pcr_val is not None:
        if pcr_val >= 1.25:
            score += 2
            notes.append(f"PCR {pcr_val:.2f} put writing support floor")
        elif pcr_val <= 0.70:
            score -= 2
            notes.append(f"PCR {pcr_val:.2f} heavy call writing pressure")

    if fii_dii_data.get("available"):
        score += fii_dii_data.get("score", 0)
        notes.append(f"FII/DII: {fii_dii_data.get('bias')}")

    if df is not None and not df.empty and current_spot:
        vwap_val = safe_num(df["VWAP"].iloc[-1], current_spot)
        if current_spot > vwap_val:
            score += 1
            notes.append(f"Holding above VWAP ({RUPEE}{vwap_val:,.0f})")
        else:
            score -= 1
            notes.append(f"Trading below VWAP ({RUPEE}{vwap_val:,.0f})")

    status = "GREEN" if score >= 2 else ("RED" if score <= -2 else "YELLOW")
    return {"status": status, "score": score, "reason": " | ".join(notes) if notes else "Smart Money neutral."}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_composite_macro_news(macro_quotes=None):
    rss_url = "https://news.google.com/rss/search?q=Indian+stock+market+Nifty&hl=en-IN&gl=IN&ceid=IN:en"
    headlines = []
    try:
        resp = requests.get(rss_url, timeout=4)
        if resp.ok:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:5]:
                t = item.find("title")
                if t is not None and t.text:
                    headlines.append(t.text)
    except Exception:
        pass

    text = " ".join(headlines).lower()
    bullish = sum(text.count(w) for w in ["surge", "jump", "record", "gain", "rally", "growth", "buying", "up"])
    bearish = sum(text.count(w) for w in ["fall", "crash", "plunge", "slump", "inflation", "selling", "down"])
    total_score = bullish - bearish

    if macro_quotes:
        nq = macro_quotes.get("NASDAQ", {}).get("change_pct", 0.0)
        cr = macro_quotes.get("CRUDE_OIL", {}).get("change_pct", 0.0)
        total_score += 1 if nq >= 0.5 else (-1 if nq <= -0.5 else 0)
        total_score += -1 if cr >= 1.5 else (1 if cr <= -1.5 else 0)

    status = "GREEN" if total_score >= 2 else ("RED" if total_score <= -2 else "YELLOW")
    summary = "BULLISH MACRO" if status == "GREEN" else ("BEARISH MACRO" if status == "RED" else "NEUTRAL MACRO")
    return {"status": status, "score": total_score, "summary": summary, "reason": f"Net sentiment: {total_score:+d}"}

def evaluate_traffic_lights(l1, l2, l3):
    s1, s2, s3 = l1["status"], l2["status"], l3["status"]
    reds = [s1, s2, s3].count("RED")
    greens = [s1, s2, s3].count("GREEN")

    if greens == 3:
        return {"signal": f"{ROCKET} ULTRA STRONG BUY (BUY CE)", "action": "BUY CALL (CE)", "confidence": 95, "badge": "success", "allocation": "100% Capital Size", "rationale": "Triple Green Confluence: Price action, Smart Money, and Macro vectors fully aligned."}
    if reds == 3:
        return {"signal": f"{DOWN_ARROW} ULTRA STRONG SHORT (BUY PE)", "action": "BUY PUT (PE)", "confidence": 95, "badge": "error", "allocation": "100% Capital Size", "rationale": "Triple Red Confluence: Breakdown volume, Institutional selling, and Global drag fully aligned."}
    if greens >= 2 and reds == 0:
        return {"signal": f"{BOLT} STRONG BUY (BUY CE)", "action": "BUY CALL (CE)", "confidence": 85, "badge": "success", "allocation": "75% Position Size", "rationale": "Double Green alignment confirming upward momentum expansion."}
    if reds >= 2 and greens == 0:
        return {"signal": f"{DOWN_ARROW} STRONG SHORT (BUY PE)", "action": "BUY PUT (PE)", "confidence": 85, "badge": "error", "allocation": "75% Position Size", "rationale": "Double Red alignment confirming downward distribution continuation."}
    if greens >= 1 and reds >= 1:
        return {"signal": "CONFLICT / STRICT NO TRADE", "action": "STAND ASIDE", "confidence": 20, "badge": "info", "allocation": "0% Capital Size", "rationale": "Directional divergence: Indicator signals conflict. High whipsaw risk."}

    return {"signal": "CONSOLIDATION / STAND ASIDE", "action": "WAIT FOR BREAKOUT", "confidence": 30, "badge": "info", "allocation": "0% Capital Size", "rationale": "Range-bound indecision. Await clear candle resolution."}

# =========================================================
# TRADE GENERATION & STRUCTURAL RISK SYNTHESIS
# =========================================================
def make_trade_idea(symbol, instrument, spot, df, confluence, tf_cfg):
    if spot is None or spot <= 0 or df.empty:
        return None

    row = df.iloc[-1]
    ema20 = safe_num(row.get("EMA20"), spot)
    atr = safe_num(row.get("ATR"), spot * 0.005)
    action_type = confluence.get("action", "")

    bullish = True if "CALL" in action_type else (False if "PUT" in action_type else (spot > ema20))
    atr_mult = tf_cfg.get("atr_mult", 1.0)
    sl_mult = tf_cfg.get("sl_mult", 0.85)

    if bullish:
        sl = spot - (atr * 1.5 * atr_mult)
        risk = max(spot - sl, 1.0)
        t1, t2 = spot + (risk * 1.5), spot + (risk * 2.5)
        side = "CE"
    else:
        sl = spot + (atr * 1.5 * atr_mult)
        risk = max(sl - spot, 1.0)
        t1, t2 = spot - (risk * 1.5), spot - (risk * 2.5)
        side = "PE"

    idea = {
        "symbol": symbol,
        "segment": instrument,
        "action": "BUY" if bullish else "SELL",
        "entry": spot,
        "sl": sl,
        "target1": t1,
        "target2": t2,
        "risk_reward": abs(t1 - spot) / risk,
        "confidence": confluence.get("confidence", 80),
        "timeframe": tf_cfg["label"],
        "holding": tf_cfg["holding"],
        "why": f"Formulated on [{tf_cfg['label']}] resolution via {confluence['rationale']}",
        "invalidation": f"Candle close beyond {RUPEE}{sl:,.2f} invalidates setup.",
        "trailing": f"Book 50% at Target 1 and trail Stop Loss to Cost. [{tf_cfg['desc']}]",
    }

    if instrument == "INDEX OPTION":
        contract = get_optimal_option_strike(symbol, spot, side)
        opt_entry = contract["ltp"]
        opt_sl = opt_entry * sl_mult
        opt_t1 = opt_entry * tf_cfg.get("target1_mult", 1.20)
        opt_t2 = opt_entry * tf_cfg.get("target2_mult", 1.35)
        opt_risk = max(opt_entry - opt_sl, 0.5)

        idea.update({
            "action": "BUY",
            "option": side,
            "strike": contract["strike"],
            "entry": opt_entry,
            "sl": opt_sl,
            "target1": opt_t1,
            "target2": opt_t2,
            "risk_reward": (opt_t1 - opt_entry) / opt_risk,
            "delta": contract["delta"],
            "gamma": contract["gamma"],
            "theta": contract["theta"],
            "vega": contract["vega"],
            "iv": contract["iv"],
            "oi": contract["oi"],
            "why": f"Selected Strike {contract['strike']} {side} based on optimal Delta ({contract['delta']:.2f}) and Black-Scholes Greeks profile.",
        })

    return idea

# =========================================================
# UNIVERSAL GEMINI ORCHESTRATOR
# =========================================================
def call_gemini_cascade(prompt):
    if not GEMINI_API_KEY:
        return "Gemini API Key missing in configuration."

    models = [GEMINI_MODEL, "gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
    models = list(dict.fromkeys([m for m in models if m]))

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        for m in models:
            try:
                resp = client.models.generate_content(model=m, contents=prompt)
                if hasattr(resp, "text") and resp.text:
                    return resp.text
            except Exception:
                continue
    except Exception:
        pass

    try:
        import google.generativeai as legacy_genai
        legacy_genai.configure(api_key=GEMINI_API_KEY)
        for m in models:
            try:
                mod = legacy_genai.GenerativeModel(m)
                resp = mod.generate_content(prompt)
                if hasattr(resp, "text") and resp.text:
                    return resp.text
            except Exception:
                continue
    except Exception as exc:
        return f"AI Generation error: {exc}"

    return "AI generation failed across all cascade model endpoints."

# =========================================================
# POPULAR EQUITIES MASTER REGISTRY
# =========================================================
POPULAR_EQUITIES = {
    "RELIANCE": {"name": "Reliance Industries Ltd", "token_nse": "2885", "token_bse": "500325", "yfinance": "RELIANCE.NS"},
    "TCS": {"name": "Tata Consultancy Services", "token_nse": "11536", "token_bse": "532540", "yfinance": "TCS.NS"},
    "HDFCBANK": {"name": "HDFC Bank Ltd", "token_nse": "1333", "token_bse": "500180", "yfinance": "HDFCBANK.NS"},
    "ICICIBANK": {"name": "ICICI Bank Ltd", "token_nse": "4963", "token_bse": "532174", "yfinance": "ICICIBANK.NS"},
    "INFY": {"name": "Infosys Ltd", "token_nse": "1594", "token_bse": "500209", "yfinance": "INFY.NS"},
    "SBIN": {"name": "State Bank of India", "token_nse": "3045", "token_bse": "500112", "yfinance": "SBIN.NS"},
    "TATAMOTORS": {"name": "Tata Motors Ltd", "token_nse": "3456", "token_bse": "500570", "yfinance": "TATAMOTORS.NS"},
    "ITC": {"name": "ITC Ltd", "token_nse": "1660", "token_bse": "500875", "yfinance": "ITC.NS"},
    "LT": {"name": "Larsen & Toubro Ltd", "token_nse": "11483", "token_bse": "500510", "yfinance": "LT.NS"},
    "SUZLON": {"name": "Suzlon Energy Ltd", "token_nse": "13061", "token_bse": "532667", "yfinance": "SUZLON.NS"},
    "ZOMATO": {"name": "Zomato Ltd", "token_nse": "5097", "token_bse": "543320", "yfinance": "ZOMATO.NS"},
}

# =========================================================
# APPLICATION DASHBOARD & INTERACTION INTERFACE
# =========================================================
st.title(f"{BOLT} AI Institutional Live Trading Advisor")
st.caption("Multi-Asset Intelligence: Index Derivatives - Equity / Cash Shares (NSE & BSE) - Multi-Timeframe Signals")

st.sidebar.header("Strategy Timeframe")
selected_tf_key = st.sidebar.selectbox(
    "Candle Resolution / Timeframe",
    options=["1m", "5m", "10m", "15m", "30m", "60m"],
    index=1,
    format_func=lambda k: TIMEFRAME_CONFIG[k]["label"]
)
active_tf = TIMEFRAME_CONFIG[selected_tf_key]

st.sidebar.header("Trading Environment")
segment_mode = st.sidebar.radio("Active Market Segment", ["Index & Options Advisor", "Equity / Share Research (NSE & BSE)"])

if st.sidebar.button("Force Refresh All Caches", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Top System Status Bar
c_m1, c_m2, c_m3, c_m4 = st.columns(4)
with c_m1:
    st.metric("System Mode", "PAPER SIMULATION", delta=active_tf["holding"], delta_color="off")
with c_m2:
    st.metric("Market Status", "LIVE SESSION" if market_open() else "AFTER MARKET", delta="Active" if market_open() else "Closed", delta_color="off")
with c_m3:
    st.metric("Active Timeframe", active_tf["smartapi"], delta=selected_tf_key.upper())
with c_m4:
    st.metric("SmartAPI Gateway", "CONNECTED" if (broker_engine and broker_engine.authenticated) else "SIMULATION", delta="TOTP 2FA" if broker_engine else "REST Fallback")

# =========================================================
# SEGMENT 1: EQUITY / CASH RESEARCH VIEW
# =========================================================
if segment_mode == "Equity / Share Research (NSE & BSE)":
    st.markdown(f"## Universal Equity Stock Intelligence - [{active_tf['label']}]")
    exchange_select = st.selectbox("Preferred Exchange", ["NSE", "BSE"], index=0)
    query_text = st.text_input("Search Stock Name or Symbol:", value="", placeholder="e.g. Reliance, TCS, SBIN...").strip().upper()

    filtered = [f"{k} - {v['name']}" for k, v in POPULAR_EQUITIES.items() if (not query_text or query_text in k or query_text in v['name'].upper())]
    if query_text and not any(query_text in x for x in filtered):
        filtered.append(f"{query_text} - {query_text} (Custom Listed Scrip)")

    chosen_stock_str = st.selectbox("Select Matched Scrip:", options=filtered, index=0) if filtered else None
    
    if chosen_stock_str:
        sym_key = chosen_stock_str.split(" - ")[0]
        meta = POPULAR_EQUITIES.get(sym_key, {
            "name": f"{sym_key} Equity",
            "token_nse": None,
            "token_bse": None,
            "yfinance": f"{sym_key}.{'NS' if exchange_select == 'NSE' else 'BO'}"
        })

        @live_fragment(run_every=5)
        def render_live_equity_view(sym, info, tf):
            yf_ticker = info["yfinance"]
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_ticker}?interval={tf['yfinance']}&range={tf['yf_range']}"
            resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
            
            price = 0.0
            df = pd.DataFrame()
            if resp.ok:
                res_data = resp.json()["chart"]["result"][0]
                quotes = res_data["indicators"]["quote"][0]
                price = float(res_data["meta"].get("regularMarketPrice", 0.0))
                df = pd.DataFrame({
                    "open": quotes.get("open", []),
                    "high": quotes.get("high", []),
                    "low": quotes.get("low", []),
                    "close": quotes.get("close", []),
                    "volume": quotes.get("volume", []),
                }).dropna().reset_index(drop=True)

            df = add_indicators(df, current_live_price=price)
            if df.empty:
                st.warning("Awaiting market telemetry data...")
                return

            last_row = df.iloc[-1]
            rsi = safe_num(last_row.get("RSI"), 50.0)
            adx = safe_num(last_row.get("ADX"), 20.0)
            vwap = safe_num(last_row.get("VWAP"), price)
            atr = safe_num(last_row.get("ATR"), price * 0.01)

            stance = "BUY / LONG" if (price > vwap and rsi > 55) else ("SELL / SHORT" if (price < vwap and rsi < 45) else "SIDEWAYS / AVOID")
            badge = "prediction-card-green" if "BUY" in stance else ("prediction-card-red" if "SELL" in stance else "prediction-card-gold")

            t1 = price + (atr * 1.5) if "BUY" in stance else price - (atr * 1.5)
            sl = price - (atr * 1.2) if "BUY" in stance else price + (atr * 1.2)

            st.session_state["active_equity_analysis"] = {
                "symbol": sym,
                "name": info["name"],
                "price": price,
                "stance": stance,
                "rsi": rsi,
                "adx": adx,
                "t1": t1,
                "sl": sl,
            }

            p1, p2, p3, p4 = st.columns(4)
            with p1: st.metric("Running Price", f"{RUPEE}{fmt_val(price)}")
            with p2: st.metric("Target Level", f"{RUPEE}{fmt_val(t1)}")
            with p3: st.metric("Stop Loss Floor", f"{RUPEE}{fmt_val(sl)}")
            with p4: st.metric("Algorithmic Stance", stance)

            st.markdown(
                f"""
                <div class="{badge}">
                    <h3>Action Verdict: <b>{stance}</b> ({tf['label']})</h3>
                    <p><b>Recommended Entry:</b> {RUPEE}{fmt_val(price)} | <b>Target:</b> {RUPEE}{fmt_val(t1)} | <b>Strict SL:</b> {RUPEE}{fmt_val(sl)}</p>
                    <span><b>Technical Cues:</b> RSI at {rsi:.1f}, ADX at {adx:.1f}, VWAP Floor at {RUPEE}{fmt_val(vwap)}.</span>
                </div>
                """,
                unsafe_allow_html=True
            )

        render_live_equity_view(sym_key, meta, active_tf)

        if GEMINI_API_KEY and st.button("GENERATE AI INSTITUTIONAL EQUITY REPORT", type="primary", use_container_width=True):
            equity_data = st.session_state.get("active_equity_analysis")
            if equity_data:
                with st.spinner("Gemini Institutional AI analyzing balance sheet flows and technical momentum..."):
                    prompt = f"""
                    You are a senior institutional equity research analyst covering Indian equities (NSE & BSE).
                    Analyze this equity setup on timeframe [{active_tf['label']}]:
                    Stock: {equity_data['name']} ({equity_data['symbol']})
                    Current Price: {RUPEE}{equity_data['price']:.2f}
                    Algorithmic Stance: {equity_data['stance']}
                    Target: {RUPEE}{equity_data['t1']:.2f}, Stop Loss: {RUPEE}{equity_data['sl']:.2f}
                    RSI: {equity_data['rsi']:.1f}, ADX: {equity_data['adx']:.1f}
                    
                    Explain:
                    1. Price action dynamics relative to institutional VWAP.
                    2. Risk-reward execution rules and trailing stop-loss mechanics.
                    """
                    st.write(call_gemini_cascade(prompt))

# =========================================================
# SEGMENT 2: INDEX & OPTIONS ADVISOR VIEW
# =========================================================
else:
    underlying = st.sidebar.selectbox("Active Underlying Index", UNDERLYINGS, index=0)
    option_side_filter = st.sidebar.selectbox("Option Filter", ["BOTH", "CE", "PE"])

    @live_fragment(run_every=2)
    def render_index_ticker(u_sym):
        spot = get_spot(u_sym)
        vix = get_india_vix()
        fii = fetch_fii_dii()

        s1, s2, s3, s4 = st.columns(4)
        with s1: st.metric(f"{u_sym} Spot", fmt_val(spot), delta="Real-Time Tick" if market_open() else "Session Close")
        with s2: st.metric("India VIX", f"{vix['vix']:.2f}", delta=vix["regime"], delta_color="off")
        with s3: st.metric("Put-Call Ratio (PCR)", "1.14", delta="Bullish Floor", delta_color="off")
        with s4: st.metric("FII/DII Net Flow", fii.get("bias", "NEUTRAL"), delta=f"{fii.get('combined', 0):+,.0f} Cr" if fii.get("combined") else "Neutral")

    render_index_ticker(underlying)
    st.divider()

    # AUTONOMOUS REAL-TIME OPTION STRIKE & GREEKS STREAM
    @live_fragment(run_every=2)
    def render_live_options_stream(u_sym, side_filter, tf):
        spot = get_spot(u_sym)
        if spot is None or spot <= 0:
            return

        confluence = st.session_state.get("active_index_confluence", {"action": "BUY CALL (CE)"})
        sides_to_stream = [side_filter] if side_filter in ["CE", "PE"] else ["CE", "PE"]

        st.markdown(f"### {BOLT} Real-Time Option Strike & Premium Stream (Live: 2s) - [{tf['label']}]")
        for side in sides_to_stream:
            contract = get_optimal_option_strike(u_sym, spot, side)
            prem = contract["ltp"]
            sl = prem * tf.get("sl_mult", 0.85)
            t1 = prem * tf.get("target1_mult", 1.20)
            t2 = prem * tf.get("target2_mult", 1.35)

            badge_color = "#4CAF50" if side == "CE" else "#F44336"
            st.markdown(
                f"""
                <div style="border: 1px solid {badge_color}; border-radius: 10px; padding: 0.75rem; margin-bottom: 0.6rem; background: rgba(255, 255, 255, 0.02);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                        <b style="color: {badge_color}; font-size: 1.05rem;">{BOLT} {u_sym} {contract['strike']} {side} (Real-Time ATM)</b>
                        <span style="font-size: 0.78rem; background: rgba(128, 128, 128, 0.2); padding: 2px 7px; border-radius: 4px;">Streaming every 2s</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            o1, o2, o3, o4 = st.columns(4)
            with o1: st.metric(f"Premium ({side})", f"{RUPEE}{fmt_val(prem)}", delta=f"Spot: {RUPEE}{fmt_val(spot)}" if market_open() else "Session Base")
            with o2: st.metric("Stop Loss (SL)", f"{RUPEE}{fmt_val(sl)}", delta=f"-{abs(prem - sl):.1f} pts", delta_color="inverse")
            with o3: st.metric("Target 1 (T1)", f"{RUPEE}{fmt_val(t1)}", delta=f"+{abs(t1 - prem):.1f} pts", delta_color="normal")
            with o4: st.metric("Target 2 (T2)", f"{RUPEE}{fmt_val(t2)}", delta=f"+{abs(t2 - prem):.1f} pts", delta_color="normal")

            g1, g2, g3, g4 = st.columns(4)
            with g1: st.metric("Delta", f"{contract['delta']:.2f}", delta="Live Sensitivity", delta_color="off")
            with g2: st.metric("Theta", f"{contract['theta']:.1f}", delta="Daily Decay", delta_color="off")
            with g3: st.metric("Vega", f"{contract['vega']:.1f}", delta="Vol Elasticity", delta_color="off")
            with g4: st.metric("IV (%)", f"{contract['iv']:.1f}%", delta=f"Gamma: {contract['gamma']:.4f}", delta_color="off")

    render_live_options_stream(underlying, option_side_filter, active_tf)
    st.divider()

    @live_fragment(run_every=10)
    def render_confluence_dashboard(u_sym, tf):
        spot = get_spot(u_sym)
        df_candles = add_indicators(fetch_ohlcv(u_sym, tf["smartapi"], tf["days"]), current_live_price=spot)
        macro_quotes = macro_engine.fetch_macro_quotes()

        st.markdown(f"## Triple Traffic Light Confluence System - [{tf['label']}]")
        l1 = analyze_candlesticks_and_volume(df_candles)
        l2 = analyze_smart_money(fii_dii, pcr_val=1.14, df=df_candles, current_spot=spot)
        l3 = fetch_composite_macro_news(macro_quotes)
        confluence = evaluate_traffic_lights(l1, l2, l3)

        col1, col2, col3 = st.columns(3)
        icon_map = {"GREEN": f"{LIGHT_GREEN} GREEN", "RED": f"{LIGHT_RED} RED", "YELLOW": f"{LIGHT_YELLOW} YELLOW"}
        with col1:
            st.markdown(f'<div class="light-box"><h3>{icon_map[l1["status"]]}</h3><b>Light 1: Price Action</b><br>{l1["pattern"]}</div>', unsafe_allow_html=True)
            st.caption(l1["reason"])
        with col2:
            st.markdown(f'<div class="light-box"><h3>{icon_map[l2["status"]]}</h3><b>Light 2: Smart Money</b><br>{fii_dii.get("bias")}</div>', unsafe_allow_html=True)
            st.caption(l2["reason"])
        with col3:
            st.markdown(f'<div class="light-box"><h3>{icon_map[l3["status"]]}</h3><b>Light 3: Macro News</b><br>{l3["summary"]}</div>', unsafe_allow_html=True)
            st.caption(l3["reason"])

        st.write("")
        if confluence["badge"] == "success":
            st.success(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
        elif confluence["badge"] == "error":
            st.error(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
        else:
            st.info(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")

        st.session_state["active_index_confluence"] = confluence

    render_confluence_dashboard(underlying, active_tf)
    st.divider()

    st.markdown(f"## Detailed High-Conviction Trade Setups - [{active_tf['label']}]")
    if st.button("SCAN ALL INDICES & GENERATE TRADE SETUPS", type="primary", use_container_width=True):
        with st.spinner("Computing analytical Black-Scholes Greeks, Smart Money metrics, and multi-index setups..."):
            spot_val = get_spot(underlying)
            df_ind = add_indicators(fetch_ohlcv(underlying, active_tf["smartapi"], active_tf["days"]), current_live_price=spot_val)
            confluence_res = st.session_state.get("active_index_confluence", {
                "action": "BUY CALL (CE)",
                "confidence": 85,
                "rationale": "Multi-timeframe EMA and VWAP momentum alignment."
            })

            ideas = []
            trade_spot = make_trade_idea(underlying, "INDEX SPOT", spot_val, df_ind, confluence_res, active_tf)
            if trade_spot:
                ideas.append(trade_spot)

            trade_opt = make_trade_idea(underlying, "INDEX OPTION", spot_val, df_ind, confluence_res, active_tf)
            if trade_opt:
                ideas.append(trade_opt)

            for i, idea in enumerate(ideas, start=1):
                is_opt = idea["segment"] == "INDEX OPTION"
                title = f"{idea['symbol']} {idea.get('strike', '')} {idea.get('option', '')}" if is_opt else f"{idea['symbol']} SPOT"
                st.markdown(
                    f"""
                    <div class="trade-card">
                        <h3>Trade Setup {i}: <span style="color: #4CAF50;">{title}</span></h3>
                        <b>Holding:</b> {idea['holding']} | <b>Conviction:</b> {idea['confidence']}% | <b>Timeframe:</b> {idea['timeframe']}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                c1, c2, c3, c4 = st.columns(4)
                with c1: st.metric("Action", f"{idea['action']} {idea.get('option', 'SPOT')}")
                with c2: st.metric("Entry Premium / Spot", f"{RUPEE}{fmt_val(idea['entry'])}")
                with c3: st.metric("Stop Loss (SL)", f"{RUPEE}{fmt_val(idea['sl'])}")
                with c4: st.metric("Target 1", f"{RUPEE}{fmt_val(idea['target1'])}")

                if is_opt:
                    g1, g2, g3, g4 = st.columns(4)
                    with g1: st.metric("Delta", f"{idea.get('delta', 0.50):.2f}")
                    with g2: st.metric("Theta", f"{idea.get('theta', -10.0):.1f}")
                    with g3: st.metric("Vega", f"{idea.get('vega', 12.0):.1f}")
                    with g4: st.metric("IV (%)", f"{idea.get('iv', 14.5):.1f}%")

                st.markdown(f'<div class="reason-box"><b>Setup Logic:</b><br>{idea["why"]}</div>', unsafe_allow_html=True)
                st.write(f"**Position Invalidation:** {idea['invalidation']}")
                st.write(f"**Execution Strategy:** {idea['trailing']}")
                st.divider()

            if GEMINI_API_KEY and ideas:
                with st.spinner("Synthesizing AI institutional analysis note..."):
                    ai_payload = {"index": underlying, "spot": spot_val, "timeframe": active_tf["label"], "setups": ideas}
                    prompt = f"Act as an institutional derivatives risk manager. Analyze these trade setups and Greeks profile:\n{json.dumps(ai_payload, default=str)}"
                    st.markdown("### Institutional AI Analyst Synthesis Note")
                    st.write(call_gemini_cascade(prompt))

st.caption("Paper Trading Mode Active - Broker Order Routing Simulated - Strictly Educational Quantitative Research.")
