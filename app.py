import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dtime
import json
import requests
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# =========================================================
# PAGE CONFIGURATION & STYLES
# =========================================================

st.set_page_config(
    page_title="AI Trading Advisor & Traffic Lights",
    page_icon="🚦",
    layout="wide",
)

PAPER_TRADING = True

st.markdown("""
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
    padding: 1rem;
    margin: 0.5rem 0;
}

.light-box {
    border: 1px solid rgba(128, 128, 128, 0.25);
    border-radius: 12px;
    padding: 0.9rem;
    text-align: center;
    background-color: rgba(255, 255, 255, 0.02);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# OPTIONAL ENGINE IMPORTS WITH FAIL-SAFE FALLBACKS
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
    from tomorrow_forecast_engine import build_tomorrow_forecast
except Exception:
    build_tomorrow_forecast = None

# =========================================================
# UTILITY FUNCTIONS & DATA COERCION
# =========================================================

def secret(name):
    try:
        val = st.secrets.get(name)
        return str(val).strip() if val else ""
    except Exception:
        return ""

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

def safe_text(x):
    return str(x) if x is not None else ""

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
# CREDENTIALS CONFIGURATION
# =========================================================

ANGEL_API_KEY = secret("ANGEL_API_KEY")
ANGEL_CLIENT_CODE = secret("ANGEL_CLIENT_CODE")
ANGEL_PIN = secret("ANGEL_PIN")
ANGEL_TOTP_SECRET = secret("ANGEL_TOTP_SECRET")
ANGEL_JWT_TOKEN = secret("ANGEL_JWT_TOKEN")

GEMINI_API_KEY = secret("GEMINI_API_KEY") or secret("GOOGLE_API_KEY") or secret("GEMINI_KEY")
GEMINI_MODEL = secret("GEMINI_MODEL") or "gemini-2.5-flash"

# =========================================================
# INSTITUTIONAL FLOW ENGINE (FII / DII)
# =========================================================

FII_DII_API = "https://fii-diidata.mrchartist.com/api/data"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fii_dii():
    empty = {
        "available": False,
        "source": "Unavailable",
        "date": None,
        "fii_net": None,
        "dii_net": None,
        "combined_net": None,
        "institutional_score": 0,
        "bias": "UNAVAILABLE",
    }
    try:
        resp = requests.get(FII_DII_API, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if resp.ok:
            data = resp.json()
            if isinstance(data, list) and data:
                data = data[0]
            f_net = num(data.get("fii_net") or data.get("fiiNet"))
            d_net = num(data.get("dii_net") or data.get("diiNet"))
            score = 0
            if f_net is not None:
                score += 1 if f_net > 500 else (-1 if f_net < -500 else 0)
            if d_net is not None:
                score += 1 if d_net > 500 else (-1 if d_net < -500 else 0)

            bias = "BULLISH" if score > 0 else ("BEARISH" if score < 0 else "NEUTRAL")
            return {
                "available": True,
                "source": "NSE FII/DII API",
                "date": data.get("date"),
                "fii_net": f_net,
                "dii_net": d_net,
                "combined_net": (f_net + d_net) if (f_net is not None and d_net is not None) else None,
                "institutional_score": score,
                "bias": bias,
            }
    except Exception:
        pass
    return empty

fii_dii = fetch_fii_dii()

# =========================================================
# BROKER SESSION & TELEMETRY SETUP
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
            totp_secret=ANGEL_TOTP_SECRET
        )
    except Exception:
        return None

@st.cache_resource(show_spinner=False)
def create_options():
    if OptionsEngine is None:
        return None
    try:
        if ANGEL_JWT_TOKEN:
            return OptionsEngine(
                jwt_token=ANGEL_JWT_TOKEN,
                api_key=ANGEL_API_KEY,
                client_code=ANGEL_CLIENT_CODE
            )
    except Exception:
        pass
    return None

telemetry = create_telemetry()
options = create_options()

UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]
SPOT_TOKENS = {
    "NIFTY": ("NSE", "99926000"),
    "BANKNIFTY": ("NSE", "99926009"),
    "FINNIFTY": ("NSE", "99926037"),
    "MIDCPNIFTY": ("NSE", "99926074"),
    "SENSEX": ("BSE", "99919000"),
}

@st.cache_data(ttl=120, show_spinner=False)
def fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=5):
    if telemetry is None or symbol not in SPOT_TOKENS:
        return pd.DataFrame()
    exchange, token = SPOT_TOKENS[symbol]
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
    if telemetry is not None:
        try:
            res = telemetry.get_ltp(symbol)
            if isinstance(res, dict):
                for k in ["ltp", "lastTradedPrice", "close"]:
                    if k in res and num(res[k]) is not None:
                        return num(res[k])
            v = num(res)
            if v and v > 0:
                return v
        except Exception:
            pass
    try:
        df = fetch_ohlcv(symbol, "FIVE_MINUTE", 1)
        if not df.empty:
            return float(df["close"].iloc[-1])
    except Exception:
        pass
    return None

@st.cache_data(ttl=300, show_spinner=False)
def load_expiries(symbol):
    if options is None:
        return []
    try:
        res = options.get_expiry_options(symbol)
        vals = []
        for item in res or []:
            v = item.get("value") or item.get("expiry") if isinstance(item, dict) else item
            v = expiry_norm(v)
            if v: vals.append(v)
        return sorted(set(vals))
    except Exception:
        return []

def get_chain(symbol, expiry, spot):
    if options is None or not expiry:
        return pd.DataFrame(), pd.DataFrame()
    try:
        contracts = clean_df(options.get_option_contracts(underlying=symbol, expiry_date=expiry))
        quoted = clean_df(options.get_market_quote(contracts)) if not contracts.empty else contracts
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

# =========================================================
# INDICATORS & MULTI-TIMEFRAME ANALYSIS
# =========================================================

def add_indicators(df):
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
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

    if "volume" in df.columns:
        typical = (high + low + close) / 3
        df["VWAP"] = (typical * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)
        df["VOL_AVG20"] = df["volume"].rolling(20).mean()
    else:
        df["VWAP"] = np.nan
        df["VOL_AVG20"] = np.nan

    return df

def analyze_market(symbol, proxy=None):
    res = {
        "symbol": symbol,
        "trend": "UNKNOWN",
        "last": None,
        "rsi": None,
        "ema20": None,
        "ema50": None,
        "vwap": None,
        "support": None,
        "resistance": None,
        "technical_score": 0,
        "institutional_score": 0,
        "score": 0,
        "reasons": []
    }
    df5 = add_indicators(fetch_ohlcv(symbol, "FIVE_MINUTE", 5))
    if df5.empty:
        return res

    row = df5.iloc[-1]
    last = num(row.get("close"))
    res["last"] = last
    res["rsi"] = num(row.get("RSI"))
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
            res["reasons"].append("Price VWAP ke upar trade kar raha hai.")
        else:
            score -= 1
            res["reasons"].append("Price VWAP ke neeche trade kar raha hai.")

    if res["rsi"]:
        if res["rsi"] >= 60: score += 1
        elif res["rsi"] <= 40: score -= 1

    res["technical_score"] = score
    inst_score = fii_dii.get("institutional_score", 0) if fii_dii.get("available") else (proxy.get("score", 0) if proxy else 0)
    res["institutional_score"] = inst_score
    res["score"] = score + inst_score
    res["trend"] = "BULLISH" if res["score"] >= 3 else ("BEARISH" if res["score"] <= -3 else "SIDEWAYS")
    return res

# =========================================================
# 🚦 TRIPLE TRAFFIC LIGHT CONFLUENCE ENGINES
# =========================================================

def analyze_candlestick_and_volume(df):
    """LIGHT 1: Candlestick Pattern Recognition & Volume Spread Analysis"""
    if df is None or len(df) < 5:
        return {
            "status": "YELLOW",
            "pattern": "AWAITING TICK DATA",
            "volume_spike": False,
            "volume_ratio": 1.0,
            "reversal_risk": False,
            "reason": "Candle array load ho raha hai."
        }

    c = df.iloc[-1]
    p = df.iloc[-2]
    open_p, close_p = float(c["open"]), float(c["close"])
    high_p, low_p = float(c["high"]), float(c["low"])
    vol = float(c["volume"]) if "volume" in c and pd.notna(c["volume"]) else 1.0

    avg_vol = float(df["volume"].tail(20).mean()) if "volume" in df.columns else 1.0
    vol_ratio = (vol / avg_vol) if avg_vol > 0 else 1.0
    vol_spike = vol_ratio >= 1.30

    total_range = max(high_p - low_p, 0.001)
    body = abs(close_p - open_p)
    upper_shadow = high_p - max(open_p, close_p)
    lower_shadow = min(open_p, close_p) - low_p

    # Doji / Equilibrium
    if body <= (0.12 * total_range):
        return {
            "status": "YELLOW",
            "pattern": "DOJI (INDECISION / PAUSE)",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Doji balance candle bani hai ({body/total_range:.2f} body ratio). Market indecision mode mein hai."
        }

    # Bullish Hammer
    if lower_shadow >= (2.0 * body) and upper_shadow <= (0.25 * body):
        return {
            "status": "GREEN" if vol_spike else "YELLOW",
            "pattern": "BULLISH HAMMER",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Support par bottom rejection hammer bana hai with {vol_ratio:.2f}x volume confirmation."
        }

    # Bearish Shooting Star
    if upper_shadow >= (2.0 * body) and lower_shadow <= (0.25 * body):
        return {
            "status": "RED" if vol_spike else "YELLOW",
            "pattern": "BEARISH SHOOTING STAR",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": True,
            "reason": f"Resistance par rejection shooting star bana hai with {vol_ratio:.2f}x volume rejection."
        }

    # Bullish Engulfing
    if (close_p > open_p) and (float(p["close"]) < float(p["open"])) and (close_p >= float(p["open"])) and (open_p <= float(p["close"])):
        return {
            "status": "GREEN" if vol_spike else "YELLOW",
            "pattern": "BULLISH ENGULFING",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Bullish body overrides previous red candle with {vol_ratio:.2f}x volume."
        }

    # Bearish Engulfing
    if (close_p < open_p) and (float(p["close"]) > float(p["open"])) and (close_p <= float(p["open"])) and (open_p >= float(p["close"])):
        return {
            "status": "RED" if vol_spike else "YELLOW",
            "pattern": "BEARISH ENGULFING",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": True,
            "reason": f"Bearish engulfing overrides buyers with {vol_ratio:.2f}x volume breakdown."
        }

    # Marubozu / Solid Expansion
    if body >= (0.65 * total_range):
        if close_p > open_p:
            return {
                "status": "GREEN" if vol_spike else "YELLOW",
                "pattern": "BULLISH EXPANSION CANDLE",
                "volume_spike": vol_spike,
                "volume_ratio": vol_ratio,
                "reversal_risk": False,
                "reason": f"Strong green expansion candle with {vol_ratio:.2f}x volume."
            }
        else:
            return {
                "status": "RED" if vol_spike else "YELLOW",
                "pattern": "BEARISH BREAKDOWN CANDLE",
                "volume_spike": vol_spike,
                "volume_ratio": vol_ratio,
                "reversal_risk": True,
                "reason": f"Aggressive red selling candle with {vol_ratio:.2f}x volume."
            }

    return {
        "status": "YELLOW",
        "pattern": "RANGE CONSOLIDATION",
        "volume_spike": vol_spike,
        "volume_ratio": vol_ratio,
        "reversal_risk": False,
        "reason": "Normal candle range; koi decisive breakout ya reversal trigger nahi hai."
    }

def analyze_smart_money(fii_dii, pcr):
    """LIGHT 2: Institutional FII/DII Cash Flow & Options Put-Call Ratio"""
    score = 0
    notes = []

    if pcr is not None:
        if pcr >= 1.25:
            score += 2
            notes.append(f"PCR {pcr:.2f} shows strong put writing floor.")
        elif pcr >= 1.00:
            score += 1
            notes.append(f"PCR {pcr:.2f} mildly supportive hai.")
        elif 0.70 < pcr < 1.00:
            score -= 1
            notes.append(f"PCR {pcr:.2f} cautious resistance indicate karta hai.")
        else:
            score -= 2
            notes.append(f"PCR {pcr:.2f} heavy call writing pressure me hai.")
    else:
        notes.append("PCR unavailable.")

    if fii_dii.get("available"):
        score += fii_dii.get("institutional_score", 0)
        notes.append(f"FII/DII Bias: {fii_dii.get('bias')}.")
    else:
        notes.append("Cash flow neutral/pending.")

    status = "GREEN" if score >= 2 else ("RED" if score <= -2 else "YELLOW")
    return {"status": status, "score": score, "reason": " | ".join(notes)}

@st.cache_data(ttl=600, show_spinner=False)
def fetch_news_sentiment():
    """LIGHT 3: Live Macro News Feed & Sentiment Polarity"""
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
    """27 Permutations and Combinations Decision Matrix"""
    s1, s2, s3 = l1["status"], l2["status"], l3["status"]
    greens = [s1, s2, s3].count("GREEN")
    reds = [s1, s2, s3].count("RED")

    # Triple Green
    if greens == 3:
        return {
            "state": "TRIPLE GREEN CONFLUENCE",
            "signal": "🔥 STRONG BUY (BUY CE)",
            "action": "BUY CALL (CE)",
            "confidence": 95,
            "badge": "success",
            "allocation": "100% Capital Size",
            "rationale": "High-volume bullish candle, positive institutional PCR/Flow, aur supportive macro news teeno aligned hain.",
            "rule": "Aggressive Call Entry. Target 1 (+20%), Target 2 (+35%)."
        }

    # Triple Red
    if reds == 3:
        return {
            "state": "TRIPLE RED CONFLUENCE",
            "signal": "🚨 STRONG SHORT (BUY PE)",
            "action": "BUY PUT (PE)",
            "confidence": 95,
            "badge": "error",
            "allocation": "100% Capital Size",
            "rationale": "High-volume breakdown candle, institutional call resistance, aur negative macro news teeno aligned hain.",
            "rule": "Aggressive Put Entry. Target 1 (+20%), Target 2 (+35%)."
        }

    # Moderate Setups (2 Green or 2 Red with Yellow)
    if s1 == "GREEN" and s2 == "GREEN" and s3 == "YELLOW":
        return {
            "state": "TECHNICAL + SMART MONEY ALIGNMENT",
            "signal": "⚡ MODERATE BUY (CE)",
            "action": "BUY CALL (CE)",
            "confidence": 80,
            "badge": "success",
            "allocation": "60% Position Size",
            "rationale": "Price action aur Smart Money bullish hain; macro news quiet hai.",
            "rule": "Standard Call entry with half risk."
        }

    if s1 == "RED" and s2 == "RED" and s3 == "YELLOW":
        return {
            "state": "TECHNICAL + SMART MONEY BREAKDOWN",
            "signal": "⚡ MODERATE SHORT (PE)",
            "action": "BUY PUT (PE)",
            "confidence": 80,
            "badge": "error",
            "allocation": "60% Position Size",
            "rationale": "Price action aur institutional flows bearish hain; macro news quiet hai.",
            "rule": "Standard Put entry with half risk."
        }

    # Divergence / Trap Zones
    if (s1 == "GREEN" and s2 == "RED") or (s1 == "RED" and s2 == "GREEN"):
        return {
            "state": "DIVERGENCE TRAP ZONE",
            "signal": "⚔️ CONFLICT / STRICT NO TRADE",
            "action": "STRICT AVOID / CASH PRESERVATION",
            "confidence": 15,
            "badge": "info",
            "allocation": "0% Capital Size",
            "rationale": "Candlestick price action institutional smart money ke directly opposite hai.",
            "rule": "Koi fresh trade na lein; fake breakout trap risk high hai."
        }

    # Default Chop
    return {
        "state": "EQUILIBRIUM & CHOP ZONE",
        "signal": "⏸️ NO TRADE / WAIT FOR CLARITY",
        "action": "STAND ASIDE",
        "confidence": 20,
        "badge": "info",
        "allocation": "0% Capital Size",
        "rationale": "Market consolidation ya Doji candle phase mein hai. Directional edge absent hai.",
        "rule": "Kam se kam 2 synchronized lights ka wait karein."
    }

# =========================================================
# SYSTEMATIC TRADE IDEA GENERATOR
# =========================================================

def nearest_option(chain, spot, side):
    if chain.empty or spot is None:
        return None
    type_col = find_column(chain, ["option_type", "optionType", "type"])
    strike_col = find_column(chain, ["strike", "strikePrice", "strike_price"])
    if not type_col or not strike_col:
        return None
    work = chain.copy()
    work["_type"] = work[type_col].map(normalize_option_type)
    work = work[work["_type"] == side].copy()
    if work.empty:
        return None
    work["_strike"] = pd.to_numeric(work[strike_col], errors="coerce")
    work = work.dropna(subset=["_strike"])
    if work.empty:
        return None
    work["_dist"] = (work["_strike"] - spot).abs()
    return work.sort_values("_dist").iloc[0]

def make_trade_idea(market, symbol, instrument="INDEX", option_side=None, expiry=None, chain=None, confluence=None):
    last = market.get("last")
    if last is None or last <= 0:
        return None

    bullish = True if market.get("score", 0) >= 2 else (False if market.get("score", 0) <= -2 else None)
    if bullish is None:
        return None

    direction = "BUY" if bullish else "SELL"
    entry_spot = float(last)
    support = num(market.get("support"))
    resistance = num(market.get("resistance"))

    if bullish:
        sl = support if (support and support < entry_spot) else (entry_spot * 0.997)
        risk = entry_spot - sl
        t1, t2 = entry_spot + (risk * 1.5), entry_spot + (risk * 2.5)
    else:
        sl = resistance if (resistance and resistance > entry_spot) else (entry_spot * 1.003)
        risk = sl - entry_spot
        t1, t2 = entry_spot - (risk * 1.5), entry_spot - (risk * 2.5)

    if risk <= 0:
        return None

    conf_score = confluence.get("confidence", 75) if confluence else 75

    idea = {
        "segment": instrument,
        "symbol": symbol,
        "action": direction,
        "entry": entry_spot,
        "sl": sl,
        "target1": t1,
        "target2": t2,
        "risk_reward": abs(t1 - entry_spot) / risk,
        "confidence": conf_score,
        "holding": "Intraday" if market_open() else "NEXT SESSION",
        "expiry": expiry,
        "option": None,
        "strike": None,
        "option_ltp": None,
        "why": " ".join(market.get("reasons", [])[:6]),
        "invalidation": f"Price {'below' if bullish else 'above'} SL sustain kare.",
    }

    if instrument == "INDEX OPTION" and chain is not None and not chain.empty:
        opt_type = option_side if option_side in ["CE", "PE"] else ("CE" if bullish else "PE")
        selected = nearest_option(chain, entry_spot, opt_type)
        if selected is not None:
            stk = first_value(selected, ["strike", "strikePrice"])
            opt_price = num(first_value(selected, ["ltp", "lastPrice", "lastTradedPrice"]))
            idea["option"] = opt_type
            idea["strike"] = stk
            idea["option_ltp"] = opt_price
            if opt_price and opt_price > 0:
                opt_entry = float(opt_price)
                idea["entry"] = opt_entry
                idea["sl"] = opt_entry * 0.85
                idea["target1"] = opt_entry * 1.20
                idea["target2"] = opt_entry * 1.35
                idea["risk_reward"] = 1.33

    return idea

# =========================================================
# AI GEMINI SYNTHESIS ENGINE
# =========================================================

def ask_gemini(ideas, market_data):
    if not GEMINI_API_KEY:
        return None
    payload = {"market": market_data, "ideas": ideas, "fii_dii": fii_dii}
    prompt = f"""
You are a quantitative Indian market analyst for a PAPER TRADING advisor.
Rely STRICTLY on this data payload. Evaluate technical setups, institutional flows, and invalidations.
PAYLOAD: {json.dumps(payload, default=str)}
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
# APPLICATION DASHBOARD RENDERING
# =========================================================

st.title("📊 AI Trading Advisor & Traffic Lights")
st.caption("Triple Traffic Light Confluence • Multi-Timeframe • Options • Sentiments • Paper Trading Only")

h1, h2, h3, h4 = st.columns(4)
with h1: st.metric("Mode", "PAPER ONLY")
with h2: st.metric("Market", "OPEN" if market_open() else "AFTER MARKET")
with h3: st.metric("Broker API", "CONNECTED" if telemetry is not None else "STANDALONE")
with h4: st.metric("AI Engine", "READY" if GEMINI_API_KEY else "RULES MODE")

# Sidebar
st.sidebar.header("⚙️ Trading Parameters")
underlying = st.sidebar.selectbox("Underlying Index", UNDERLYINGS, index=0)
expiries = load_expiries(underlying)
selected_expiry = st.sidebar.selectbox("Expiry", expiries, format_func=expiry_label) if expiries else None
option_type_choice = st.sidebar.selectbox("Option Filter", ["BOTH", "CE", "PE"])

if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

spot = get_spot(underlying)
chain, _ = get_chain(underlying, selected_expiry, spot)
pcr = calculate_pcr(chain)
proxy = calculate_live_derivatives_proxy(chain, pcr)
df5 = fetch_ohlcv(underlying, "FIVE_MINUTE", 5)
market = analyze_market(underlying, proxy)

# Summary Row
st.subheader("📌 Current Market")
m1, m2, m3, m4 = st.columns(4)
with m1: st.metric("Underlying", underlying)
with m2: st.metric("Spot LTP", fmt(spot))
with m3: st.metric("Live PCR", fmt(pcr, 2) if pcr else "-")
with m4: st.metric("Expiry", expiry_label(selected_expiry) if selected_expiry else "-")

st.divider()

# =========================================================
# 🚦 TRAFFIC LIGHTS SECTION (LIVE & PROMINENT)
# =========================================================

st.markdown("## 🚦 Triple Traffic Light Confluence System")

light1 = analyze_candlestick_and_volume(df5)
light2 = analyze_smart_money(fii_dii, pcr)
light3 = fetch_news_sentiment()
confluence = evaluate_all_permutations(light1, light2, light3)

icon_map = {"GREEN": "🟢 GREEN", "RED": "🔴 RED", "YELLOW": "🟡 YELLOW"}

tl1, tl2, tl3 = st.columns(3)

with tl1:
    st.markdown(f"""
    <div class="light-box">
        <h3>{icon_map[light1['status']]}</h3>
        <b>Light 1: Price Action</b><br>
        <span style="font-size:13px;">Candlestick Patterns & Volume</span>
    </div>
    """, unsafe_allow_html=True)
    st.write(f"**Pattern:** {light1['pattern']}")
    st.write(f"**Volume Factor:** {light1['volume_ratio']:.2f}x")
    st.caption(light1["reason"])

with tl2:
    st.markdown(f"""
    <div class="light-box">
        <h3>{icon_map[light2['status']]}</h3>
        <b>Light 2: Smart Money</b><br>
        <span style="font-size:13px;">FII/DII Cash & Options PCR</span>
    </div>
    """, unsafe_allow_html=True)
    st.write(f"**Institutional Skew:** {fii_dii.get('bias', 'NEUTRAL')}")
    st.write(f"**PCR Level:** {fmt(pcr, 2) if pcr else 'N/A'}")
    st.caption(light2["reason"])

with tl3:
    st.markdown(f"""
    <div class="light-box">
        <h3>{icon_map[light3['status']]}</h3>
        <b>Light 3: Macro Catalyst</b><br>
        <span style="font-size:13px;">News Headlines & Polarity</span>
    </div>
    """, unsafe_allow_html=True)
    st.write(f"**Macro Summary:** {light3['summary']}")
    st.write(f"**Catalyst Factor:** {light3['score']:+d}")
    st.caption(light3["reason"])

st.write("")

# Action Alert
if confluence["badge"] == "success":
    st.success(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
elif confluence["badge"] == "error":
    st.error(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
elif confluence["badge"] == "warning":
    st.warning(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")
else:
    st.info(f"### {confluence['signal']}\n**Action:** {confluence['action']} | **Confidence:** {confluence['confidence']}%\n\n{confluence['rationale']}")

# Dynamic Exit Monitor
st.markdown("### 🛡️ Active Position Exit Monitor")
with st.expander("📌 Active Position Exit Rules Check (Live)", expanded=True):
    ex1, ex2 = st.columns(2)
    with ex1:
        st.markdown("**🟢 Agar aap Call (CE) Hold kar rahe hain:**")
        if light1["status"] == "RED" or light2["status"] == "RED":
            st.error("🚨 **EXIT LONG (CE) NOW:** Opposite Red Lights trigger ho gayi hain. Technical rejection ya selling volume detect hua hai.")
        elif light1["reversal_risk"] and light1["volume_spike"]:
            st.error(f"⚠️ **TECHNICAL EXIT (CE):** Reversal pattern ({light1['pattern']}) bana hai. Profit book karein.")
        elif "DOJI" in light1["pattern"]:
            st.warning("⚠️ **TRAIL SL TO COST:** Doji equilibrium bani hai. Stop loss tight karein.")
        else:
            st.success("✅ **HOLD CE POSITION:** Parameters bullish hain. Target 1 (+20%) / Target 2 (+35%) ke liye hold karein.")

    with ex2:
        st.markdown("**🔴 Agar aap Put (PE) Hold kar rahe hain:**")
        if light1["status"] == "GREEN" or light2["status"] == "GREEN":
            st.error("🚨 **EXIT SHORT (PE) NOW:** Opposite Green Lights trigger ho gayi hain. Institutional support bounce detect hua hai.")
        elif light1["pattern"] in ["BULLISH HAMMER", "BULLISH ENGULFING"] and light1["volume_spike"]:
            st.error(f"⚠️ **TECHNICAL EXIT (PE):** Bottom bounce hammer/engulfing hua hai. Put position exit karein.")
        elif "DOJI" in light1["pattern"]:
            st.warning("⚠️ **TRAIL SL TO COST:** Support par Doji pause bana hai. Stop loss tight karein.")
        else:
            st.success("✅ **HOLD PE POSITION:** Downside intact hai. Hold position.")

st.divider()

# =========================================================
# NEXT-SESSION BLUEPRINT
# =========================================================

st.markdown("## 🔮 Tomorrow Market Blueprint")
if build_tomorrow_forecast is None:
    st.info("Tomorrow Forecast Engine module load nahi hua (Stand-alone mode active).")
else:
    try:
        t_data = {
            "symbol": underlying,
            "spot": market.get("last"),
            "support": market.get("support"),
            "resistance": market.get("resistance"),
            "rsi": market.get("rsi"),
            "technical_score": market.get("technical_score", 0),
            "institutional_score": market.get("institutional_score", 0),
            "score": market.get("score", 0),
            "pcr": pcr,
            "fii_net": fii_dii.get("fii_net"),
            "dii_net": fii_dii.get("dii_net"),
        }
        tomorrow = build_tomorrow_forecast(t_data)
        if tomorrow:
            tb1, tb2, tb3 = st.columns(3)
            tb1.metric("Next Session Bias", tomorrow.get("bias", "N/A"))
            tb2.metric("Support", fmt(tomorrow.get("support")))
            tb3.metric("Resistance", fmt(tomorrow.get("resistance")))
    except Exception as e:
        st.warning(f"Blueprint calculation error: {e}")

# =========================================================
# TRADE GENERATION PIPELINE
# =========================================================

st.subheader("🎯 Trade Ideas Generation")
if st.button("🚀 GENERATE DETAILED TRADE IDEAS", type="primary", use_container_width=True):
    with st.spinner("Processing technical indicators and traffic light confluence..."):
        ideas = []
        bound_side = option_type_choice if option_type_choice in ["CE", "PE"] else None

        base_idea = make_trade_idea(market, underlying, instrument="INDEX", expiry=selected_expiry, chain=chain, confluence=confluence)
        if base_idea: ideas.append(base_idea)

        opt_idea = make_trade_idea(market, underlying, instrument="INDEX OPTION", option_side=bound_side, expiry=selected_expiry, chain=chain, confluence=confluence)
        if opt_idea: ideas.append(opt_idea)

        for alt in ["BANKNIFTY", "NIFTY", "SENSEX"]:
            if alt != underlying:
                alt_m = analyze_market(alt, proxy)
                alt_idea = make_trade_idea(alt_m, alt, instrument="INDEX", confluence=confluence)
                if alt_idea: ideas.append(alt_idea)

        unique_ideas = []
        seen = set()
        for item in ideas:
            k = (item["segment"], item["symbol"], item["action"], item.get("option"), str(item.get("strike")))
            if k not in seen:
                seen.add(k)
                unique_ideas.append(item)
        ideas = unique_ideas[:4]

    if not ideas:
        st.warning("Market conditions indicate neutral alignment or conflict. No setup triggered.")
    else:
        st.success(f"{len(ideas)} systematic trade structure(s) generated.")
        for i, idea in enumerate(ideas, start=1):
            st.markdown(f"""
            <div class="trade-card">
            <h4>Setup {i}: {idea['symbol']} — {idea['action']} ({idea['segment']})</h4>
            Entry: {fmt(idea['entry'])} | SL: {fmt(idea['sl'])} | Target 1: {fmt(idea['target1'])} | Target 2: {fmt(idea['target2'])} | RR: 1:{idea['risk_reward']:.2f}
            </div>
            """, unsafe_allow_html=True)
            st.caption(f"**Setup Logic:** {idea['why']} • **Invalidation:** {idea['invalidation']}")

        if GEMINI_API_KEY:
            with st.spinner("Formulating AI synthesis..."):
                ai_text = ask_gemini(ideas, {"underlying": underlying, "spot": spot, "trend": market["trend"]})
                if ai_text:
                    st.markdown("#### 🤖 AI Analyst Explanation")
                    st.write(ai_text)

st.divider()
st.caption("Paper Trading Mode • Confluence Traffic Lights & Sequence Engine Merged • Real-Time Order Routing Disabled.")
