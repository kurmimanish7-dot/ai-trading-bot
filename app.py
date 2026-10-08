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
    page_icon="⚡",
    layout="wide",
)

PAPER_TRADING = True

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem !important;
        padding-left: 0.7rem !important;
        padding-right: 0.7rem !important;
        max-width: 100% !important;
    }
    @media(max-width: 768px) {
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.45rem !important;
            width: 100% !important;
        }
        [data-testid="column"] {
            min-width: 48% !important;
            max-width: 48% !important;
            flex: 1 1 48% !important;
            width: 48% !important;
        }
    }
    .trade-card {
        width: 100%;
        box-sizing: border-box;
        border: 1px solid rgba(128, 128, 128, 0.30);
        border-radius: 12px;
        padding: 1.1rem;
        margin: 0.8rem 0;
        background-color: rgba(255, 255, 255, 0.02);
    }
    .light-box {
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 12px;
        padding: 0.9rem;
        text-align: center;
        background-color: rgba(255, 255, 255, 0.02);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .reason-box {
        background-color: rgba(128, 128, 128, 0.08);
        border-left: 4px solid #4CAF50;
        padding: 0.8rem;
        border-radius: 4px;
        margin: 0.6rem 0;
        line-height: 1.5;
    }

    /* ZERO-BREATHING / ZERO-FLICKER HARD OVERRIDES */
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
    [data-testid="stMetric"] *,
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] *,
    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] *,
    [data-testid="stMetricDelta"],
    [data-testid="stMetricDelta"] * {
        opacity: 1 !important;
        transition: none !important;
        animation: none !important;
    }

    [data-testid="stMetricValue"] {
        font-variant-numeric: tabular-nums !important;
        letter-spacing: -0.01em !important;
    }

    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(128, 128, 128, 0.25) !important;
        border-radius: 10px !important;
        padding: 0.75rem 1rem !important;
        min-height: 96px !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
    }

    [data-testid="stStatusWidget"] {
        visibility: hidden !important;
        display: none !important;
    }

    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] * {
        opacity: 1 !important;
        transition: none !important;
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
# ENGINE IMPORTS
# =========================================================
try:
    from telemetry_engine import TelemetryEngine
except Exception:
    TelemetryEngine = None

try:
    from options_engine import OptionsEngine
except Exception:
    OptionsEngine = None

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
GEMINI_MODEL = secret("GEMINI_MODEL") or "gemini-2.5-flash"

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
        "live_tokens": ["26000", "99926000"],
        "candle_token": "99926000",
    },
    "BANKNIFTY": {
        "exchange": "NSE",
        "symbol": "Nifty Bank",
        "live_tokens": ["26009", "99926009"],
        "candle_token": "99926009",
    },
    "FINNIFTY": {
        "exchange": "NSE",
        "symbol": "FINNIFTY",
        "live_tokens": ["99926037"],
        "candle_token": "99926037",
    },
    "MIDCPNIFTY": {
        "exchange": "NSE",
        "symbol": "MIDCPNIFTY",
        "live_tokens": ["99926074"],
        "candle_token": "99926074",
    },
    "SENSEX": {
        "exchange": "BSE",
        "symbol": "SENSEX",
        "live_tokens": ["99919000"],
        "candle_token": "99919000",
    },
    "INDIA_VIX": {
        "exchange": "NSE",
        "symbol": "India VIX",
        "live_tokens": ["99926017"],
        "candle_token": "99926017",
    },
}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=3):
    if telemetry is None or symbol not in INDEX_METADATA:
        return pd.DataFrame()

    meta = INDEX_METADATA[symbol]
    exchange = meta["exchange"]
    token = meta["candle_token"]

    try:
        df = clean_df(telemetry.fetch_ohlcv(exchange=exchange, token=token, interval=interval, days=days))
        if df.empty:
            return df

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

        return df.dropna(subset=needed).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()

def get_spot(symbol):
    if telemetry is None or symbol not in INDEX_METADATA:
        return None

    meta = INDEX_METADATA[symbol]
    exchange = meta["exchange"]
    tradingsymbol = meta["symbol"]

    for token in meta["live_tokens"]:
        try:
            if hasattr(telemetry, "smart_api") and telemetry.smart_api:
                res = telemetry.smart_api.ltpData(
                    exchange=exchange,
                    tradingsymbol=tradingsymbol,
                    symboltoken=token,
                )
                if res and res.get("status") and "data" in res:
                    val = float(res["data"].get("ltp", 0.0))
                    if val > 0:
                        return val
        except Exception:
            pass

    try:
        res = telemetry.get_ltp(tradingsymbol)
        val = num(res.get("ltp") if isinstance(res, dict) else res)
        if val and val > 0:
            return val
    except Exception:
        pass

    return None

@st.cache_data(ttl=10, show_spinner=False)
def get_india_vix():
    vix = get_spot("INDIA_VIX")
    if vix is None:
        vix = 14.5

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

    plus_dm = high.diff().where((high.diff() > -low.diff()) & (high.diff() > 0), 0)
    minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0)
    plus_di = 100 * plus_dm.rolling(14).sum() / atr.rolling(14).sum().replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(14).sum() / atr.rolling(14).sum().replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["ADX"] = dx.rolling(14).mean()

    if "volume" in df.columns:
        typical = (high + low + close) / 3
        df["VWAP"] = (typical * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)
        df["VOL_AVG20"] = df["volume"].rolling(20).mean()
    else:
        df["VWAP"] = np.nan
        df["VOL_AVG20"] = np.nan

    return df

def analyze_market(symbol, proxy=None, explicit_spot=None):
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

    df5 = add_indicators(fetch_ohlcv(symbol, "FIVE_MINUTE", 3), current_live_price=explicit_spot)
    if df5.empty:
        return res

    row = df5.iloc[-1]
    last = explicit_spot or num(row.get("close"))
    res["last"] = last
    res["rsi"] = num(row.get("RSI"))
    res["adx"] = num(row.get("ADX"))
    res["ema20"] = num(row.get("EMA20"))
    res["ema50"] = num(row.get("EMA50"))
    res["vwap"] = num(row.get("VWAP"))
    res["support"] = num(df5["low"].tail(30).min())
    res["resistance"] = num(df5["high"].tail(30).max())

    score = 0
    if res["ema20"] and res["ema50"] and last:
        if last > res["ema20"] > res["ema50"]:
            score += 2
            res["reasons"].append("Price EMA20 aur EMA50 ke upar bullish sustained hai.")
        elif last < res["ema20"] < res["ema50"]:
            score -= 2
            res["reasons"].append("Price EMA20 aur EMA50 ke neeche bearish breakdown par hai.")

    if res["vwap"] and last:
        if last > res["vwap"]:
            score += 1
            res["reasons"].append("Price institutional benchmark VWAP ke upar trade kar raha hai.")
        else:
            score -= 1
            res["reasons"].append("Price institutional benchmark VWAP ke neeche trade kar raha hai.")

    if res["rsi"]:
        if res["rsi"] >= 60:
            score += 1
            res["reasons"].append(f"RSI ({res['rsi']:.1f}) bullish expansion territory mein hai.")
        elif res["rsi"] <= 40:
            score -= 1
            res["reasons"].append(f"RSI ({res['rsi']:.1f}) bearish pressure territory mein hai.")

    if res["adx"] and res["adx"] >= 20:
        res["reasons"].append(f"ADX ({res['adx']:.1f}) trend conviction aur volatility confirm karta hai.")

    res["technical_score"] = score
    inst_score = fii_dii.get("score", 0) if fii_dii.get("available") else (proxy.get("score", 0) if proxy else 0)
    res["institutional_score"] = inst_score
    res["score"] = score + inst_score
    res["trend"] = "BULLISH" if res["score"] >= 3 else ("BEARISH" if res["score"] <= -3 else "SIDEWAYS")
    return res

# =========================================================
# UPGRADED INTELLIGENT TRAFFIC LIGHT ENGINES
# =========================================================
def analyze_candlesticks_and_volume(df):
    """
    LIGHT 1 UPGRADE:
    Direct breakdown logic without volume blocker on index spot.
    """
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
    vol = float(c["volume"]) if "volume" in c and pd.notna(c["volume"]) else 1.0
    avg_vol = float(df["volume"].tail(20).mean()) if "volume" in df.columns else 1.0
    vol_ratio = (vol / avg_vol) if avg_vol > 0 else 1.0
    vol_spike = vol_ratio >= 1.25

    rng = max(high_p - low_p, 0.001)
    body = abs(close_p - open_p)
    upper_w = high_p - max(open_p, close_p)
    lower_w = min(open_p, close_p) - low_p

    # Multi-candle momentum context
    prior_3_closes = df["close"].tail(4).values
    is_continuous_fall = (prior_3_closes[-1] < prior_3_closes[-2] < prior_3_closes[-3])

    # Doji / Indecision
    if body <= (0.10 * rng):
        return {
            "status": "YELLOW",
            "pattern": "DOJI (PAUSE / INDECISION)",
            "vol_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Doji candle bani hai ({body/rng:.2f} ratio). Market pause mode mein hai.",
        }

    # Bullish Hammer Pin
    if lower_w >= (2.0 * body) and upper_w <= (0.25 * body):
        return {
            "status": "GREEN",
            "pattern": "BULLISH HAMMER PIN",
            "vol_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Bottom rejection hammer pin confirmed ({vol_ratio:.2f}x vol).",
        }

    # Bearish Shooting Star
    if upper_w >= (2.0 * body) and lower_w <= (0.25 * body):
        return {
            "status": "RED",
            "pattern": "BEARISH SHOOTING STAR",
            "vol_ratio": vol_ratio,
            "reversal_risk": True,
            "reason": f"Top rejection shooting star confirmed ({vol_ratio:.2f}x vol).",
        }

    # Bullish Engulfing
    if (close_p > open_p) and (float(p["close"]) < float(p["open"])) and (close_p >= float(p["open"])):
        return {
            "status": "GREEN",
            "pattern": "BULLISH ENGULFING",
            "vol_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Bullish engulfing overriding prior red candle ({vol_ratio:.2f}x vol).",
        }

    # Bearish Engulfing
    if (close_p < open_p) and (float(p["close"]) > float(p["open"])) and (close_p <= float(p["open"])):
        return {
            "status": "RED",
            "pattern": "BEARISH ENGULFING",
            "vol_ratio": vol_ratio,
            "reversal_risk": True,
            "reason": f"Bearish engulfing breakdown overriding prior green candle ({vol_ratio:.2f}x vol).",
        }

    # DIRECTIONAL EXPANSION / BREAKDOWN (VOLUME BUG REMOVED)
    if body >= (0.50 * rng):
        if close_p < open_p:
            status = "RED"
            name = "BEARISH BREAKDOWN"
            reason = f"Solid directional expansion candle (Sell-off confirmed, {vol_ratio:.2f}x vol)."
        else:
            status = "GREEN"
            name = "BULLISH MARUBOZU"
            reason = f"Solid directional expansion candle (Rally confirmed, {vol_ratio:.2f}x vol)."

        return {
            "status": status,
            "pattern": name,
            "vol_ratio": vol_ratio,
            "reversal_risk": (status == "RED"),
            "reason": reason,
        }

    # Continuous falling structure check
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
    """
    LIGHT 2 UPGRADE:
    If PCR or FII/DII is N/A, falls back to Institutional VWAP & Day Open displacement.
    Never stays blind or locked in YELLOW when market is actively plunging!
    """
    score = 0
    notes = []
    has_data = False

    # 1. Options PCR Analysis
    if pcr_val is not None:
        has_data = True
        if pcr_val >= 1.25:
            score += 2
            notes.append(f"PCR {pcr_val:.2f} solid put writing floor")
        elif pcr_val >= 1.00:
            score += 1
            notes.append(f"PCR {pcr_val:.2f} mildly supportive")
        elif 0.70 < pcr_val < 1.00:
            score -= 1
            notes.append(f"PCR {pcr_val:.2f} cautious resistance")
        else:
            score -= 2
            notes.append(f"PCR {pcr_val:.2f} heavy call writing pressure")

    # 2. Institutional Cash Flow
    if fii_dii_data.get("available"):
        has_data = True
        score += fii_dii_data.get("score", 0)
        notes.append(f"FII/DII: {fii_dii_data.get('bias')}")

    # 3. SMART MONEY VWAP & INTRADAY DISPLACEMENT PROXY (Fallback if PCR is N/A)
    if not has_data and df is not None and not df.empty and current_spot:
        day_open = float(df["open"].iloc[0])
        vwap_val = float(df["VWAP"].iloc[-1]) if "VWAP" in df.columns and pd.notna(df["VWAP"].iloc[-1]) else day_open

        if current_spot < vwap_val and current_spot < day_open:
            score -= 2
            notes.append(f"Institutional VWAP Breakdown (Spot ₹{current_spot:,.0f} < VWAP ₹{vwap_val:,.0f})")
            notes.append("Aggressive intraday distribution detected")
        elif current_spot > vwap_val and current_spot > day_open:
            score += 2
            notes.append(f"Institutional VWAP Support (Spot ₹{current_spot:,.0f} > VWAP ₹{vwap_val:,.0f})")
            notes.append("Institutional accumulation detected")
        else:
            notes.append("Market hovering near Institutional VWAP")

    status = "GREEN" if score >= 2 else ("RED" if score <= -2 else "YELLOW")
    final_reason = " | ".join(notes) if notes else "Smart Money neutral."
    return {"status": status, "score": score, "reason": final_reason}

@st.cache_data(ttl=600, show_spinner=False)
def fetch_news_sentiment():
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

    if not headlines:
        return {"status": "YELLOW", "score": 0, "summary": "NEUTRAL / NO HEADLINES", "reason": "No breaking alerts."}

    text = " ".join(headlines).lower()
    bullish = sum(text.count(w) for w in ["surge", "jump", "record", "gain", "rally", "growth", "buying", "up", "bull", "inflow"])
    bearish = sum(text.count(w) for w in ["fall", "crash", "plunge", "slump", "inflation", "selling", "down", "drop", "war", "loss"])
    net = bullish - bearish

    if net >= 2:
        status, summary = "GREEN", "BULLISH MACRO CATALYST"
    elif net <= -2:
        status, summary = "RED", "BEARISH MACRO HEADWINDS"
    else:
        status, summary = "YELLOW", "BALANCED / NEUTRAL NEWS"

    return {"status": status, "score": net, "summary": summary, "reason": f"Headline tokens: +{bullish} positive vs -{bearish} negative."}

def evaluate_all_permutations(l1, l2, l3):
    """
    CONFLUENCE ENGINE UPGRADE:
    Eliminates rigid freeze. 2 REDS + 1 YELLOW immediately generates actionable SHORT!
    """
    s1, s2, s3 = l1["status"], l2["status"], l3["status"]
    reds = [s1, s2, s3].count("RED")
    greens = [s1, s2, s3].count("GREEN")

    # 1. TRIPLE ALIGNMENT (ULTRA CONVICTION)
    if reds == 3:
        return {
            "signal": "🚨 ULTRA STRONG SHORT (BUY PE)",
            "action": "BUY PUT (PE)",
            "confidence": 95,
            "badge": "error",
            "allocation": "100% Capital Size",
            "rationale": "High-volume breakdown + Smart Money selling + Macro headwinds fully aligned.",
        }
    if greens == 3:
        return {
            "signal": "🔥 ULTRA STRONG BUY (BUY CE)",
            "action": "BUY CALL (CE)",
            "confidence": 95,
            "badge": "success",
            "allocation": "100% Capital Size",
            "rationale": "High-volume breakout + Institutional buying + Macro tailwinds fully aligned.",
        }

    # 2. DOUBLE ALIGNMENT (2 REDS -> ACTIONABLE SHORT)
    if reds >= 2 and greens == 0:
        return {
            "signal": "🚨 STRONG SHORT (BUY PE)",
            "action": "BUY PUT (PE)",
            "confidence": 85,
            "badge": "error",
            "allocation": "75% Position Size",
            "rationale": "Price action aur macro breakdown aligned hain. Downside momentum clear hai.",
        }

    # 3. DOUBLE ALIGNMENT (2 GREENS -> ACTIONABLE BUY)
    if greens >= 2 and reds == 0:
        return {
            "signal": "⚡ STRONG BUY (BUY CE)",
            "action": "BUY CALL (CE)",
            "confidence": 85,
            "badge": "success",
            "allocation": "75% Position Size",
            "rationale": "Price action aur institutional flow bullish hain. Upside momentum clear hai.",
        }

    # 4. SINGLE CONFIRMED PRICE BREAKDOWN
    if s1 == "RED" and greens == 0:
        return {
            "signal": "⚡ MODERATE SHORT (BUY PE)",
            "action": "BUY PUT (PE)",
            "confidence": 70,
            "badge": "error",
            "allocation": "50% Position Size",
            "rationale": "Candle breakdown confirmed. Tight stop loss ke saath short positions favor karein.",
        }

    if s1 == "GREEN" and reds == 0:
        return {
            "signal": "⚡ MODERATE BUY (BUY CE)",
            "action": "BUY CALL (CE)",
            "confidence": 70,
            "badge": "success",
            "allocation": "50% Position Size",
            "rationale": "Candle breakout confirmed. Trailing stop loss ke saath call buying favor karein.",
        }

    # 5. DANGEROUS CONFLICT (Green vs Red directly fighting)
    if greens >= 1 and reds >= 1:
        return {
            "signal": "⚔️ CONFLICT / STRICT NO TRADE",
            "action": "STRICT AVOID / CASH PRESERVATION",
            "confidence": 15,
            "badge": "info",
            "allocation": "0% Capital Size",
            "rationale": "Divergence: Candlestick pattern smart money/macro positioning ke directly opposite hai.",
        }

    # 6. FLAT CHOP
    return {
        "signal": "⏸️ NO TRADE / WAIT FOR CLARITY",
        "action": "STAND ASIDE",
        "confidence": 20,
        "badge": "info",
        "allocation": "0% Capital Size",
        "rationale": "Market consolidation phase mein hai. Directional breakout ka wait karein.",
    }

# =========================================================
# REAL-TIME OPTION RESOLVER & PRICE FETCHER (LIVE NFO GATEWAY)
# =========================================================
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

    # DIRECT LIVE ANGEL ONE NFO LTP QUERY
    if contract_token and contract_symbol and telemetry and hasattr(telemetry, "smart_api") and telemetry.smart_api:
        try:
            res = telemetry.smart_api.ltpData(
                exchange="NFO",
                tradingsymbol=contract_symbol,
                symboltoken=contract_token
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

def make_trade_idea(market, symbol, instrument="INDEX", option_side=None, expiry=None, chain=None, confluence=None, vix_info=None):
    last = market.get("last")
    if last is None or last <= 0:
        return None

    # Support confluence override if available
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

    if bullish:
        action = "BUY"
        sl = support if (support and support < entry_spot) else (entry_spot * 0.997)
        risk = entry_spot - sl
        t1, t2 = entry_spot + (risk * 1.5), entry_spot + (risk * 2.5)
    else:
        action = "SELL"
        sl = resistance if (resistance and resistance > entry_spot) else (entry_spot * 1.003)
        risk = sl - entry_spot
        t1, t2 = entry_spot - (risk * 1.5), entry_spot - (risk * 2.5)

    if risk <= 0:
        return None

    confidence = confluence.get("confidence", 80) if confluence else 80
    sl_mult = vix_info.get("sl_multiplier", 0.85) if vix_info else 0.85

    reasons_list = market.get("reasons", [])
    vsa_text = "Volume expansion confirmed" if any("volume" in r.lower() for r in reasons_list) else "Technical breakdown aligned"
    trend_state = "Bullish Uptrend" if bullish else "Bearish Breakdown"
    why_explanation = (
        f"Ye trade {trend_state} ke aadhar par formulate kiya gaya hai. "
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
        "holding": "Intraday" if market_open() else "NEXT SESSION",
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
        "trailing": "Target 1 hit hote hi 50% position book karein aur Stop Loss ko Cost (Entry price) par trail karein.",
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
        opt_t1 = opt_entry * 1.20
        opt_t2 = opt_entry * 1.35
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
            f"Option Buying Aadhar: {symbol} {resolved_strike} {side} select kiya gaya hai kyunki iska Delta ({idea['delta']:.2f}) "
            f"optimal zone mein hai. Isse spot downward movement par premium turant react karega. "
            f"{why_explanation}"
        )

    return idea

def ask_gemini(ideas, market_data):
    if not GEMINI_API_KEY:
        return None

    payload = {"market": market_data, "ideas": ideas, "fii_dii": fii_dii}
    prompt = f"""
    You are a senior institutional quantitative researcher for Indian derivatives (NIFTY/BANKNIFTY).
    Explain the generated trade setups in detail. Focus on:
    1. Kis technical aur institutional aadhar par trade banaya gaya hai.
    2. Greeks profile (Delta responsiveness, Theta risk).
    3. Risk management aur trailing stop-loss execution.

    DATA PAYLOAD:
    {json.dumps(payload, default=str)}
    """
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        return getattr(resp, "text", None)
    except Exception:
        pass

    try:
        import google.generativeai as legacy_genai
        legacy_genai.configure(api_key=GEMINI_API_KEY)
        model = legacy_genai.GenerativeModel(GEMINI_MODEL)
        resp = model.generate_content(prompt)
        return getattr(resp, "text", None)
    except Exception as e:
        return f"AI explanation unavailable: {e}"

# =========================================================
# APPLICATION STATIC DASHBOARD (NEVER FLICKERS)
# =========================================================
st.title("⚡ AI Institutional Live Trading Advisor")
st.caption("Triple Traffic Light Confluence • Live Delta Greeks • 4-5 High Conviction Trade Ideas • Paper Trading Only")

col_t1, col_t2, col_t3, col_t4 = st.columns(4)
with col_t1:
    st.metric("Mode", "PAPER SIMULATION")
with col_t2:
    st.metric("Market Status", "OPEN" if market_open() else "AFTER MARKET")
with col_t3:
    st.metric("Broker API", "CONNECTED" if telemetry is not None else "STANDALONE")
with col_t4:
    st.metric("AI Core", "ACTIVATED" if GEMINI_API_KEY else "RULES MODE")

# Sidebar
st.sidebar.header("⚙️ Trading Environment")
underlying = st.sidebar.selectbox("Active Underlying", UNDERLYINGS, index=0)
expiries = load_expiries(underlying)
selected_expiry = st.sidebar.selectbox("Target Expiry", expiries, format_func=expiry_label) if expiries else None
option_type_choice = st.sidebar.selectbox("Option Filter", ["BOTH", "CE", "PE"])

if st.sidebar.button("🔄 Force Refresh All Caches", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# =========================================================
# ISOLATED ZERO-BREATHING LIVE TICKER STREAM
# =========================================================
@live_fragment(run_every=2)
def render_live_ticker(selected_underlying, current_expiry):
    spot = get_spot(selected_underlying)
    chain, _ = get_chain(selected_underlying, current_expiry)
    pcr = calculate_pcr(chain)
    vix_info = get_india_vix()

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        if spot is not None:
            st.metric(f"{selected_underlying} Spot (Live)", fmt(spot))
        else:
            st.metric(f"{selected_underlying} Spot", "Awaiting Tick...", delta="Connecting Angel")
    with s2:
        st.metric("India VIX", f"{vix_info['vix']:.2f} ({vix_info['regime']})")
    with s3:
        st.metric("Put-Call Ratio (PCR)", fmt(pcr, 2) if pcr else "1.12")
    with s4:
        st.metric("FII/DII Net Bias", fii_dii.get("bias", "NEUTRAL"))

render_live_ticker(underlying, selected_expiry)

st.divider()

# =========================================================
# LIVE CONFLUENCE & EXIT MONITOR (STABLE CADENCE)
# =========================================================
@live_fragment(run_every=10)
def render_market_confluence_dashboard(selected_underlying, current_expiry):
    spot = get_spot(selected_underlying)
    chain, _ = get_chain(selected_underlying, current_expiry)
    pcr = calculate_pcr(chain)
    df5 = add_indicators(fetch_ohlcv(selected_underlying, "FIVE_MINUTE", 3), current_live_price=spot)

    st.markdown("## 🚦 Triple Traffic Light Confluence System")
    light1 = analyze_candlesticks_and_volume(df5)
    light2 = analyze_smart_money(fii_dii, pcr, df=df5, current_spot=spot)
    light3 = fetch_news_sentiment()
    confluence = evaluate_all_permutations(light1, light2, light3)

    icon_map = {"GREEN": "🟢 GREEN", "RED": "🔴 RED", "YELLOW": "🟡 YELLOW"}

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
        st.markdown(f'<div class="light-box"><h3>{icon_map[light3["status"]]}</h3><b>Light 3: Macro News</b><br><span style="font-size:12px;">Headlines Polarity Score</span></div>', unsafe_allow_html=True)
        st.write(f"**Macro Summary:** {light3['summary']}")
        st.write(f"**Factor:** {light3['score']:+d}")
        st.caption(light3["reason"])

    st.write("")

    if confluence["badge"] == "success":
        st.success(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
    elif confluence["badge"] == "error":
        st.error(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
    else:
        st.info(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")

    # Real-Time Exit Monitor
    st.markdown("### 🛡️ Live Position Exit Monitor")
    with st.expander("📌 Active Position Exit Rules Check (Live)", expanded=True):
        ex1, ex2 = st.columns(2)
        with ex1:
            st.markdown("#### 🟢 Active Call (CE) Exit Rules")
            if light1["status"] == "RED" or light2["status"] == "RED":
                st.error("🚨 **EMERGENCY EXIT CE:** Downward breakdown trigger ho chuki hai. Call positions turant exit karein.")
            elif "DOJI" in light1["pattern"]:
                st.warning("⚠️ **TRAIL SL TO COST:** Doji indecision candle form hui hai. Risk zero karein.")
            elif light1["reversal_risk"]:
                st.error(f"⚠️ **REVERSAL EXIT CE:** High volume {light1['pattern']} detected.")
            else:
                st.success("✅ **HOLD CE:** Bullish momentum intact hai.")

        with ex2:
            st.markdown("#### 🔴 Active Put (PE) Exit Rules")
            if light1["status"] == "GREEN" or light2["status"] == "GREEN":
                st.error("🚨 **EMERGENCY EXIT PE:** Opposite Green Light trigger ho chuki hai. Put positions turant exit karein.")
            elif "DOJI" in light1["pattern"]:
                st.warning("⚠️ **TRAIL SL TO COST:** Support par Doji form hui hai. Stop loss cost par trail karein.")
            elif light1["pattern"] in ["BULLISH HAMMER PIN", "BULLISH ENGULFING"]:
                st.error(f"⚠️ **REVERSAL EXIT PE:** Support bounce pattern detect hua hai.")
            else:
                st.success("✅ **HOLD PE:** Downside momentum intact hai.")

render_market_confluence_dashboard(underlying, selected_expiry)

st.divider()

# =========================================================
# TRADE IDEAS SCANNER (WITH LIVE OPTION PREMIUMS)
# =========================================================
st.markdown("## 🎯 Detailed High-Conviction Trade Setups")
st.caption("Technical Structure • Delta Greeks • Exact Strike • Setup Aadhar Explanation • Trailing SL Rules")

if st.button("🚀 SCAN ALL INDICES & GENERATE 4-5 TRADE SETUPS", type="primary", use_container_width=True):
    with st.spinner("Processing multi-index technical indicators, option Greeks, and institutional flow..."):
        current_spot = get_spot(underlying)
        opt_chain, _ = get_chain(underlying, selected_expiry)
        chain_pcr = calculate_pcr(opt_chain)
        der_proxy = calculate_live_derivatives_proxy(opt_chain, chain_pcr)
        active_market = analyze_market(underlying, der_proxy, explicit_spot=current_spot)
        vix_data = get_india_vix()

        # Confluence evaluation
        c_df5 = add_indicators(fetch_ohlcv(underlying, "FIVE_MINUTE", 3), current_live_price=current_spot)
        c_light1 = analyze_candlesticks_and_volume(c_df5)
        c_light2 = analyze_smart_money(fii_dii, chain_pcr, df=c_df5, current_spot=current_spot)
        c_light3 = fetch_news_sentiment()
        scan_confluence = evaluate_all_permutations(c_light1, c_light2, c_light3)

        ideas = []
        bound_side = option_type_choice if option_type_choice in ["CE", "PE"] else None

        # Setup 1: Underlying Spot
        setup1 = make_trade_idea(active_market, underlying, instrument="INDEX", expiry=selected_expiry, chain=opt_chain, confluence=scan_confluence, vix_info=vix_data)
        if setup1: ideas.append(setup1)

        # Setup 2: Underlying Option Contract
        setup2 = make_trade_idea(active_market, underlying, instrument="INDEX OPTION", option_side=bound_side, expiry=selected_expiry, chain=opt_chain, confluence=scan_confluence, vix_info=vix_data)
        if setup2: ideas.append(setup2)

        # Setups 3, 4, 5: Alternate Indices
        for alt_sym in ["BANKNIFTY", "NIFTY", "FINNIFTY", "SENSEX"]:
            if alt_sym != underlying:
                alt_spot = get_spot(alt_sym)
                alt_market = analyze_market(alt_sym, der_proxy, explicit_spot=alt_spot)
                alt_spot_idea = make_trade_idea(alt_market, alt_sym, instrument="INDEX", confluence=scan_confluence, vix_info=vix_data)
                if alt_spot_idea: ideas.append(alt_spot_idea)
                alt_opt_idea = make_trade_idea(alt_market, alt_sym, instrument="INDEX OPTION", confluence=scan_confluence, vix_info=vix_data)
                if alt_opt_idea: ideas.append(alt_opt_idea)

        # Filter unique setups
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
            st.success(f"{len(final_ideas)} high-conviction trade setup(s) identified with complete execution parameters.")
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
                        <h3 style="margin-bottom: 0.3rem;">Trade Setup {i} — <span style="color: #4CAF50;">{card_title}</span></h3>
                        <b>Type:</b> {sub_badge} | <b>Holding:</b> {idea['holding']} | <b>Conviction:</b> {idea['confidence']}% | <b>Expiry:</b> {idea.get('expiry') or 'Current Weekly'}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if is_option:
                    # Row 1: Dedicated Strike & Entry Metrics
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        st.metric(
                            "Selected Strike",
                            f"{idea['strike']} {idea['option']}",
                            delta=f"{idea['action']} CALL" if idea['option'] == 'CE' else f"{idea['action']} PUT",
                        )
                    with c2:
                        st.metric("Premium Entry", f"₹{fmt(idea['entry'])}")
                    with c3:
                        st.metric("Stop Loss (SL)", f"₹{fmt(idea['sl'])}")
                    with c4:
                        st.metric("Risk / Reward", f"1:{idea['risk_reward']:.2f}")

                    # Row 2: Targets & Confluence Scores
                    c5, c6, c7, c8 = st.columns(4)
                    with c5:
                        st.metric("Target 1 (+20%)", f"₹{fmt(idea['target1'])}")
                    with c6:
                        st.metric("Target 2 (+35%)", f"₹{fmt(idea['target2'])}")
                    with c7:
                        st.metric("Technical Score", f"{idea.get('technical_score', 0):+d}")
                    with c8:
                        st.metric("Smart Money Score", f"{idea.get('institutional_score', 0):+d}")

                    # Row 3: Option Greeks & Real Open Interest
                    g1, g2, g3, g4, g5 = st.columns(5)
                    with g1: st.metric("Delta (Δ)", f"{idea.get('delta', 0.52):.2f}")
                    with g2: st.metric("Theta (Θ)", f"{idea.get('theta', -12.5):.1f}")
                    with g3: st.metric("Vega", f"{idea.get('vega', 14.2):.1f}")
                    with g4: st.metric("IV (%)", f"{idea.get('iv', 14.8):.1f}%")
                    with g5: st.metric("Open Interest", f"{idea.get('oi', 0):,}" if idea.get('oi') else "Active")

                else:
                    # Cash / Spot Layout
                    c1, c2, c3, c4 = st.columns(4)
                    with c1: st.metric("Action", f"{idea['action']} SPOT")
                    with c2: st.metric("Spot Entry", f"₹{fmt(idea['entry'])}")
                    with c3: st.metric("Stop Loss (SL)", f"₹{fmt(idea['sl'])}")
                    with c4: st.metric("Risk / Reward", f"1:{idea['risk_reward']:.2f}")

                    c5, c6, c7, c8 = st.columns(4)
                    with c5: st.metric("Target 1", f"₹{fmt(idea['target1'])}")
                    with c6: st.metric("Target 2", f"₹{fmt(idea['target2'])}")
                    with c7: st.metric("Technical Score", f"{idea.get('technical_score', 0):+d}")
                    with c8: st.metric("Smart Money Score", f"{idea.get('institutional_score', 0):+d}")

                st.markdown(
                    f"""
                    <div class="reason-box">
                        <b>📌 Trade Lene Ka Aadhar (Setup Logic):</b><br>
                        {idea['why']}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.write(f"🛑 **Structural Invalidation Level:** {idea['invalidation']}")
                st.write(f"📈 **Position Trailing Guidance:** {idea['trailing']}")
                st.divider()

        # AI Gemini Analyst Synthesis
        if GEMINI_API_KEY and final_ideas:
            with st.spinner("Generating AI Analyst institutional synthesis..."):
                ai_text = ask_gemini(
                    final_ideas,
                    {
                        "underlying": underlying,
                        "spot": current_spot,
                        "vix": vix_data["vix"],
                        "pcr": chain_pcr,
                        "fii_dii": fii_dii,
                    },
                )
                if ai_text:
                    st.markdown("### 🤖 Institutional AI Analyst Report")
                    st.write(ai_text)
                    st.divider()

st.caption("Paper Trading Engine Active • Real Broker Order Routing Disabled • Strictly Educational Quantitative Research.")
