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
    page_title="AI Trading Expert Advisor with Traffic Lights",
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
    border-radius: 10px;
    padding: 0.8rem;
    text-align: center;
    background-color: rgba(255, 255, 255, 0.03);
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# OPTIONAL ANALYTIC ENGINES (FALLBACK)
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
# UTILITY AND NORMALIZATION FUNCTIONS
# =========================================================

def secret(name):
    try:
        value = st.secrets.get(name)
        return str(value).strip() if value else ""
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
    if val is None:
        return "-"
    return f"{val:,.{digits}f}"

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
    if value is None:
        return ""
    x = str(value).strip().upper()
    if x in ["CE", "CALL", "C"] or x.endswith("CE") or "CALL" in x:
        return "CE"
    if x in ["PE", "PUT", "P"] or x.endswith("PE") or "PUT" in x:
        return "PE"
    return ""

# =========================================================
# SECRETS MANAGEMENT
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
        "fii_buy": None,
        "fii_sell": None,
        "fii_net": None,
        "dii_buy": None,
        "dii_sell": None,
        "dii_net": None,
        "combined_net": None,
        "institutional_score": 0,
        "bias": "UNAVAILABLE",
    }
    try:
        resp = requests.get(FII_DII_API, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        if resp.ok:
            data = resp.json()
            if isinstance(data, list) and data:
                data = data[0]
            fii_net = num(data.get("fii_net") or data.get("fiiNet"))
            dii_net = num(data.get("dii_net") or data.get("diiNet"))
            
            score = 0
            if fii_net is not None:
                score += 1 if fii_net > 500 else (-1 if fii_net < -500 else 0)
            if dii_net is not None:
                score += 1 if dii_net > 500 else (-1 if dii_net < -500 else 0)

            bias = "BULLISH" if score > 0 else ("BEARISH" if score < 0 else "NEUTRAL")
            return {
                "available": True,
                "source": "NSE FII/DII API",
                "date": data.get("date"),
                "fii_net": fii_net,
                "dii_net": dii_net,
                "combined_net": (fii_net + dii_net) if (fii_net is not None and dii_net is not None) else None,
                "institutional_score": score,
                "bias": bias,
            }
    except Exception:
        pass
    return empty

fii_dii = fetch_fii_dii()

# =========================================================
# TELEMETRY & OPTIONS ENGINE SETUP
# =========================================================

@st.cache_resource(show_spinner=False)
def create_telemetry():
    if TelemetryEngine is None or not all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET]):
        return None
    try:
        return TelemetryEngine(api_key=ANGEL_API_KEY, client_code=ANGEL_CLIENT_CODE, pin=ANGEL_PIN, totp_secret=ANGEL_TOTP_SECRET)
    except Exception:
        return None

@st.cache_resource(show_spinner=False)
def create_options():
    if OptionsEngine is None:
        return None
    try:
        if ANGEL_JWT_TOKEN:
            return OptionsEngine(jwt_token=ANGEL_JWT_TOKEN, api_key=ANGEL_API_KEY, client_code=ANGEL_CLIENT_CODE)
    except Exception:
        pass
    return None

telemetry = create_telemetry()
options = create_options()

UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]
SPOT_TOKENS = {
    "NIFTY": ("NSE", "99926000"),
    "BANKNIFTY": ("NSE", "99926009"),
    "FINNIFTY": ("NSE", "99926037"),
    "MIDCPNIFTY": ("NSE", "99926074"),
    "SENSEX": ("BSE", "99919000"),
    "BANKEX": ("BSE", "99919012"),
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
            if v and v > 0: return v
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
# 🚦 TRIPLE TRAFFIC LIGHT ENGINES
# =========================================================

def analyze_candlesticks_and_volume(df):
    """LIGHT 1: Candlesticks & Volume Confirmation"""
    if df is None or len(df) < 5:
        return {
            "status": "YELLOW",
            "pattern": "WAITING FOR TICKS",
            "volume_spike": False,
            "volume_ratio": 1.0,
            "score": 0,
            "reason": "Market live stream ya candle array load ho raha hai."
        }

    c = df.iloc[-1]
    p = df.iloc[-2]
    open_p = float(c["open"])
    close_p = float(c["close"])
    high_p = float(c["high"])
    low_p = float(c["low"])
    vol = float(c["volume"]) if "volume" in c and pd.notna(c["volume"]) else 1.0
    avg_vol = float(df["volume"].tail(20).mean()) if "volume" in df.columns else 1.0
    vol_ratio = (vol / avg_vol) if avg_vol > 0 else 1.0
    vol_spike = vol_ratio >= 1.25

    total_range = max(high_p - low_p, 0.001)
    body = abs(close_p - open_p)
    upper_shadow = high_p - max(open_p, close_p)
    lower_shadow = min(open_p, close_p) - low_p

    # Doji / Indecision
    if body <= (0.12 * total_range):
        return {
            "status": "YELLOW",
            "pattern": "DOJI (INDECISION)",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "score": 0,
            "reason": f"Doji candle bani hai (Body: {body/total_range:.2f}). Market me indecision hai."
        }

    # Bullish Hammer
    if lower_shadow >= (2.0 * body) and upper_shadow <= (0.3 * body):
        return {
            "status": "GREEN" if vol_spike else "YELLOW",
            "pattern": "BULLISH HAMMER",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "score": 2 if vol_spike else 1,
            "reason": f"Hammer rejection at bottom with {vol_ratio:.2f}x volume confirmation."
        }

    # Bearish Shooting Star
    if upper_shadow >= (2.0 * body) and lower_shadow <= (0.3 * body):
        return {
            "status": "RED" if vol_spike else "YELLOW",
            "pattern": "SHOOTING STAR",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "score": -2 if vol_spike else -1,
            "reason": f"Shooting star rejection at top with {vol_ratio:.2f}x volume spike."
        }

    # Bullish Engulfing / Strong Green Body
    if close_p > open_p and body >= (0.6 * total_range):
        return {
            "status": "GREEN" if vol_spike else "YELLOW",
            "pattern": "BULLISH EXPANSION",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "score": 2 if vol_spike else 1,
            "reason": f"Strong green expansion candle with {vol_ratio:.2f}x volume."
        }

    # Bearish Breakdown / Strong Red Body
    if close_p < open_p and body >= (0.6 * total_range):
        return {
            "status": "RED" if vol_spike else "YELLOW",
            "pattern": "BEARISH BREAKDOWN",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "score": -2 if vol_spike else -1,
            "reason": f"Strong red breakdown candle with {vol_ratio:.2f}x volume."
        }

    return {
        "status": "YELLOW",
        "pattern": "CONSOLIDATION CANDLE",
        "volume_spike": vol_spike,
        "volume_ratio": vol_ratio,
        "score": 0,
        "reason": "Normal candle, koi clear breakout ya reversal pattern nahi hai."
    }

def analyze_sentiment_and_smart_money(fii_dii, pcr, derivatives_proxy):
    """LIGHT 2: Market Sentiment, FII/DII & Options PCR"""
    score = 0
    reasons = []

    if pcr is not None:
        if pcr >= 1.20:
            score += 2
            reasons.append(f"PCR {pcr:.2f} bullish put writing zone me hai.")
        elif pcr <= 0.70:
            score -= 2
            reasons.append(f"PCR {pcr:.2f} bearish call writing pressure me hai.")
        else:
            reasons.append(f"PCR {pcr:.2f} neutral balance me hai.")

    if fii_dii.get("available"):
        score += fii_dii.get("institutional_score", 0)
        reasons.append(f"FII/DII Net Flow: {fii_dii.get('bias')}.")
    elif derivatives_proxy.get("available"):
        score += derivatives_proxy.get("score", 0)
        reasons.append(f"Derivatives Proxy: {derivatives_proxy.get('bias')}.")

    status = "GREEN" if score >= 2 else ("RED" if score <= -2 else "YELLOW")
    return {
        "status": status,
        "score": score,
        "pcr": pcr,
        "reasons": " | ".join(reasons) if reasons else "Neutral institutional balance."
    }

@st.cache_data(ttl=600, show_spinner=False)
def fetch_market_news_sentiment():
    """LIGHT 3: Live Macro News Polarity"""
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

    if not headlines:
        return {"status": "YELLOW", "sentiment": "NEUTRAL", "reason": "No breaking headlines found."}

    text = " ".join(headlines).lower()
    bullish_words = ["surge", "jump", "record", "gain", "rally", "growth", "positive", "buying", "up", "bull"]
    bearish_words = ["fall", "crash", "plunge", "slump", "inflation", "selling", "down", "drop", "war", "loss"]

    b_score = sum(text.count(w) for w in bullish_words)
    r_score = sum(text.count(w) for w in bearish_words)
    net = b_score - r_score

    status = "GREEN" if net >= 2 else ("RED" if net <= -2 else "YELLOW")
    sentiment = "POSITIVE MACRO" if net >= 2 else ("NEGATIVE MACRO" if net <= -2 else "NEUTRAL NEWS FLOW")

    return {
        "status": status,
        "sentiment": sentiment,
        "reason": f"Headline factor: +{b_score} positive vs -{r_score} negative."
    }

def evaluate_three_lights(l1, l2, l3):
    """Permutations & Combinations for Entry/Exit"""
    lights = [l1["status"], l2["status"], l3["status"]]
    greens = lights.count("GREEN")
    reds = lights.count("RED")

    if greens == 3:
        return {
            "signal": "🔥 STRONG BUY SIGNAL (BUY CE)",
            "action": "BUY CALL (CE)",
            "badge": "success",
            "desc": "3 Green Lights Aligned! Technical candle + Volume + Institutional PCR + News positive hain.",
            "exit_alert": False
        }
    elif reds == 3:
        return {
            "signal": "🚨 STRONG SHORT SIGNAL (BUY PE)",
            "action": "BUY PUT (PE)",
            "badge": "error",
            "desc": "3 Red Lights Aligned! Breakdown candle + Call writing + Negative sentiment confirm hua.",
            "exit_alert": False
        }
    elif greens >= 2 and reds == 0:
        return {
            "signal": "⚡ MODERATE BUY (SCALP ONLY)",
            "action": "BUY CE (SMALL QUANTITY)",
            "badge": "warning",
            "desc": "2 Lights Green hain aur 1 Yellow. Half-position se scalp karein.",
            "exit_alert": False
        }
    elif reds >= 2 and greens == 0:
        return {
            "signal": "⚡ MODERATE SHORT (SCALP ONLY)",
            "action": "BUY PE (SMALL QUANTITY)",
            "badge": "warning",
            "desc": "2 Lights Red hain aur 1 Yellow. Half-position se PE scalp karein.",
            "exit_alert": False
        }
    else:
        return {
            "signal": "⏸️ NO TRADE / WAIT ZONE",
            "action": "WAIT FOR 3 LIGHTS",
            "badge": "info",
            "desc": "Market me conflict ya chop hai. Candlestick Doji ya Mixed sentiments me trade na lein.",
            "exit_alert": False
        }

# =========================================================
# APPLICATION DASHBOARD
# =========================================================

st.title("📊 AI Trading Expert Advisor with Traffic Lights")
st.caption("Triple Traffic Light Confluence • Technicals • Sentiments • News Impact • Paper Trading Only")

col_t1, col_t2, col_t3, col_t4 = st.columns(4)
with col_t1: st.metric("Mode", "PAPER ONLY")
with col_t2: st.metric("Market", "OPEN" if market_open() else "AFTER MARKET")
with col_t3: st.metric("Broker API", "CONNECTED" if telemetry is not None else "STANDALONE")
with col_t4: st.metric("AI Engine", "READY" if GEMINI_API_KEY else "RULES MODE")

# Sidebar
st.sidebar.header("⚙️ Market Settings")
underlying = st.sidebar.selectbox("Underlying Index", UNDERLYINGS, index=0)
expiries = load_expiries(underlying)
selected_expiry = st.sidebar.selectbox("Expiry", expiries, format_func=expiry_label) if expiries else None
option_type_choice = st.sidebar.selectbox("Option Bias Filter", ["BOTH", "CE", "PE"])

if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

spot = get_spot(underlying)
chain, _ = get_chain(underlying, selected_expiry, spot)
pcr = calculate_pcr(chain)
derivatives_proxy = calculate_live_derivatives_proxy(chain, pcr)
df5 = fetch_ohlcv(underlying, "FIVE_MINUTE", 5)

# Current Market Summary
st.subheader("📌 Current Market")
m1, m2, m3, m4 = st.columns(4)
with m1: st.metric("Underlying", underlying)
with m2: st.metric("Spot LTP", fmt(spot))
with m3: st.metric("PCR", fmt(pcr, 2) if pcr else "-")
with m4: st.metric("Selected Expiry", expiry_label(selected_expiry) if selected_expiry else "-")

st.divider()

# =========================================================
# 🚦 RENDER TRAFFIC LIGHT CONFLUENCE (GUARANTEED VISIBLE)
# =========================================================

st.markdown("## 🚦 Triple Traffic Light Confluence System")
st.caption("Jab 3 Green Lights aayengi tabhi BUY call hoga, aur 3 Red Lights aane par hi SHORT trigger hoga.")

# Run the 3 Engines
light1 = analyze_candlesticks_and_volume(df5)
light2 = analyze_sentiment_and_smart_money(fii_dii, pcr, derivatives_proxy)
light3 = fetch_market_news_sentiment()
decision = evaluate_three_lights(light1, light2, light3)

icon_map = {"GREEN": "🟢 GREEN", "RED": "🔴 RED", "YELLOW": "🟡 YELLOW"}

tl1, tl2, tl3 = st.columns(3)

with tl1:
    st.markdown(f"""
    <div class="light-box">
        <h3>{icon_map[light1['status']]}</h3>
        <b>Light 1: Price Action</b><br>
        <span style="font-size:13px;">Candlestick & Volume Spike</span>
    </div>
    """, unsafe_allow_html=True)
    st.write(f"**Pattern:** {light1['pattern']}")
    st.write(f"**Volume Ratio:** {light1['volume_ratio']:.2f}x")
    st.caption(light1['reason'])

with tl2:
    st.markdown(f"""
    <div class="light-box">
        <h3>{icon_map[light2['status']]}</h3>
        <b>Light 2: Market Sentiment</b><br>
        <span style="font-size:13px;">FII/DII & Options PCR</span>
    </div>
    """, unsafe_allow_html=True)
    st.write(f"**PCR:** {fmt(light2['pcr'], 2) if light2['pcr'] else 'N/A'}")
    st.write(f"**FII/DII Bias:** {fii_dii.get('bias', 'NEUTRAL')}")
    st.caption(light2['reasons'])

with tl3:
    st.markdown(f"""
    <div class="light-box">
        <h3>{icon_map[light3['status']]}</h3>
        <b>Light 3: News Impact</b><br>
        <span style="font-size:13px;">Macro News Polarity</span>
    </div>
    """, unsafe_allow_html=True)
    st.write(f"**Macro State:** {light3['sentiment']}")
    st.caption(light3['reason'])

st.write("")

# Action Alert Box
if decision["badge"] == "success":
    st.success(f"### {decision['signal']}\n**Action:** {decision['action']}\n\n{decision['desc']}")
elif decision["badge"] == "error":
    st.error(f"### {decision['signal']}\n**Action:** {decision['action']}\n\n{decision['desc']}")
elif decision["badge"] == "warning":
    st.warning(f"### {decision['signal']}\n**Action:** {decision['action']}\n\n{decision['desc']}")
else:
    st.info(f"### {decision['signal']}\n**Action:** {decision['action']}\n\n{decision['desc']}")

# Exit Management System
st.markdown("#### 🛡️ Position & Exit Monitor")
with st.expander("Active Trade Exit Rules Check (Open Karein)", expanded=True):
    ex1, ex2 = st.columns(2)
    with ex1:
        st.markdown("**Agar aap BUY (CE) Position hold kar rahe hain:**")
        if light1["status"] == "RED" or light2["status"] == "RED":
            st.error("⚠️ **EXIT ALERT FOR CE:** Reversal candle ya selling volume badh raha hai. Target/SL ka wait kiye bina profit book karein.")
        elif "DOJI" in light1["pattern"]:
            st.warning("⚠️ **CAUTION:** Doji ban gayi hai, stop-loss ko cost par trail karein.")
        else:
            st.success("✅ **HOLD CE:** Trend aur volume safe hain.")
    with ex2:
        st.markdown("**Agar aap SHORT (PE) Position hold kar rahe hain:**")
        if light1["status"] == "GREEN" or light2["status"] == "GREEN":
            st.error("⚠️ **EXIT ALERT FOR PE:** Support par buying pressure ya hammer pattern aa chuka hai. Exit PE immediately.")
        elif "DOJI" in light1["pattern"]:
            st.warning("⚠️ **CAUTION:** Doji ban gayi hai, stop-loss ko cost par trail karein.")
        else:
            st.success("✅ **HOLD PE:** Downside momentum intact hai.")

st.divider()

# Institutional View
st.subheader("🏦 Institutional Flow Overview")
f1, f2, f3, f4 = st.columns(4)
with f1: st.metric("FII Net", f"₹{fmt(fii_dii['fii_net'], 0)} Cr" if fii_dii.get('fii_net') else "-")
with f2: st.metric("DII Net", f"₹{fmt(fii_dii['dii_net'], 0)} Cr" if fii_dii.get('dii_net') else "-")
with f3: st.metric("Combined Net", f"₹{fmt(fii_dii['combined_net'], 0)} Cr" if fii_dii.get('combined_net') else "-")
with f4: st.metric("Institutional Bias", fii_dii.get("bias", "UNAVAILABLE"))

st.caption("Paper Trading Mode • Confluence Traffic Lights Active • Pure Automated Rules Engine")


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="AI Trading Expert Advisor",
    page_icon="📊",
    layout="wide",
)

PAPER_TRADING = True

# =========================================================
# MOBILE RESPONSIVE UI STYLES
# =========================================================

st.markdown("""
<style>
/* Main Container */
.block-container {
    padding-top: 1rem !important;
    padding-left: 0.7rem !important;
    padding-right: 0.7rem !important;
    max-width: 100% !important;
}

/* Responsive Columns */
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
        min-height: 0 !important;
    }

    [data-testid="stMetric"] {
        width: 100% !important;
        min-width: 0 !important;
        max-width: 100% !important;
        overflow: visible !important;
    }

    [data-testid="stMetricLabel"] {
        width: 100% !important;
        font-size: 11px !important;
        line-height: 1.25 !important;
        white-space: normal !important;
        overflow-wrap: anywhere !important;
    }

    [data-testid="stMetricValue"] {
        font-size: clamp(14px, 5vw, 18px) !important;
        line-height: 1.25 !important;
        overflow-wrap: anywhere !important;
    }

    h1 { font-size: 25px !important; }
    h2 { font-size: 21px !important; }
    h3 { font-size: 18px !important; }

    [data-testid="stDataFrame"] {
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: auto !important;
    }

    .trade-card {
        padding: 0.75rem !important;
    }
}

/* Card Presentation */
.trade-card {
    width: 100%;
    box-sizing: border-box;
    border: 1px solid rgba(128, 128, 128, 0.30);
    border-radius: 12px;
    padding: 1rem;
    margin: 0.5rem 0;
    overflow-wrap: anywhere;
}

.small {
    font-size: 0.88rem;
    opacity: 0.85;
    overflow-wrap: anywhere;
    word-break: break-word;
}

.reason {
    line-height: 1.5;
    overflow-wrap: anywhere;
    word-break: break-word;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# OPTIONAL ANALYTIC ENGINES (GRACEFUL FALLBACK)
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
# UTILITY AND NORMALIZATION FUNCTIONS
# =========================================================

def secret(name):
    try:
        value = st.secrets.get(name)
        return str(value).strip() if value else ""
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
    if val is None:
        return "-"
    return f"{val:,.{digits}f}"


def safe_text(x):
    return str(x) if x is not None else ""


def market_open():
    """Validates active trading sessions in IST."""
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False

    NSE_HOLIDAYS = {
        "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31",
        "2026-04-03", "2026-04-14", "2026-05-01", "2026-06-26",
        "2026-08-15", "2026-08-26", "2026-09-14", "2026-10-02",
        "2026-10-20", "2026-11-09", "2026-11-10", "2026-11-24",
        "2026-12-25",
    }

    if now.strftime("%Y-%m-%d") in NSE_HOLIDAYS:
        return False

    return dtime(9, 15) <= now.time() <= dtime(15, 30)


def expiry_norm(x):
    if x is None:
        return None
    if isinstance(x, (datetime, date)):
        return x.strftime("%Y-%m-%d")

    s = str(x).strip().upper()
    formats = [
        "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y",
        "%d%b%Y", "%d-%b-%Y", "%d%b%y", "%d-%b-%y",
    ]
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
    if value is None:
        return ""
    x = str(value).strip().upper()
    if x in ["CE", "CALL", "C"] or x.endswith("CE") or "CALL" in x:
        return "CE"
    if x in ["PE", "PUT", "P"] or x.endswith("PE") or "PUT" in x:
        return "PE"
    return ""

# =========================================================
# SECRETS MANAGEMENT
# =========================================================

ANGEL_API_KEY = secret("ANGEL_API_KEY")
ANGEL_CLIENT_CODE = secret("ANGEL_CLIENT_CODE")
ANGEL_PIN = secret("ANGEL_PIN")
ANGEL_TOTP_SECRET = secret("ANGEL_TOTP_SECRET")
ANGEL_JWT_TOKEN = secret("ANGEL_JWT_TOKEN")

GEMINI_API_KEY = (
    secret("GEMINI_API_KEY")
    or secret("GOOGLE_API_KEY")
    or secret("GEMINI_KEY")
)

GEMINI_MODEL = secret("GEMINI_MODEL") or "gemini-2.5-flash"

# =========================================================
# INSTITUTIONAL CAPITAL FLOW INGESTION (FII / DII)
# =========================================================

FII_DII_API = "https://fii-diidata.mrchartist.com/api/data"
FII_DII_HISTORY_API = "https://fii-diidata.mrchartist.com/api/history"


def extract_number(obj, keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj:
            val = num(obj.get(key))
            if val is not None:
                return val
    return None


def find_nested_record(obj):
    if isinstance(obj, dict):
        for key in ["data", "result", "latest", "current", "record"]:
            val = obj.get(key)
            if isinstance(val, dict):
                return val
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return val[0]
        return obj
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj[0]
    return {}


def parse_fii_dii_record(record):
    record = find_nested_record(record)
    fii_buy = extract_number(record, ["fii_buy", "fiiBuy", "fiibuy", "fb", "FII Buy", "FII_Buy"])
    fii_sell = extract_number(record, ["fii_sell", "fiiSell", "fiisell", "fs", "FII Sell", "FII_Sell"])
    fii_net = extract_number(record, ["fii_net", "fiiNet", "fiinet", "fn", "FII Net", "FII_Net"])
    dii_buy = extract_number(record, ["dii_buy", "diiBuy", "diibuy", "db", "DII Buy", "DII_Buy"])
    dii_sell = extract_number(record, ["dii_sell", "diiSell", "diisell", "ds", "DII Sell", "DII_Sell"])
    dii_net = extract_number(record, ["dii_net", "diiNet", "diinet", "dn", "DII Net", "DII_Net"])

    if fii_net is None and fii_buy is not None and fii_sell is not None:
        fii_net = fii_buy - fii_sell
    if dii_net is None and dii_buy is not None and dii_sell is not None:
        dii_net = dii_buy - dii_sell

    data_date = (
        record.get("date")
        or record.get("d")
        or record.get("trade_date")
        or record.get("tradeDate")
        or record.get("timestamp")
    )

    return {
        "fii_buy": fii_buy,
        "fii_sell": fii_sell,
        "fii_net": fii_net,
        "dii_buy": dii_buy,
        "dii_sell": dii_sell,
        "dii_net": dii_net,
        "date": data_date,
    }


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fii_dii():
    empty = {
        "available": False,
        "source": "Unavailable",
        "date": None,
        "fii_buy": None,
        "fii_sell": None,
        "fii_net": None,
        "dii_buy": None,
        "dii_sell": None,
        "dii_net": None,
        "combined_net": None,
        "fii_3d": None,
        "dii_3d": None,
        "institutional_score": 0,
        "bias": "UNAVAILABLE",
        "bias_score": "NEUTRAL",
        "status": "Data unavailable",
    }

    latest = None
    try:
        response = requests.get(FII_DII_API, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if response.ok:
            latest = response.json()
    except Exception:
        latest = None

    if latest is None:
        return empty

    parsed = parse_fii_dii_record(latest)
    fii_net = parsed["fii_net"]
    dii_net = parsed["dii_net"]

    if fii_net is None and dii_net is None:
        return empty

    history = []
    try:
        hist_resp = requests.get(FII_DII_HISTORY_API, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if hist_resp.ok:
            h_data = hist_resp.json()
            if isinstance(h_data, dict):
                for k in ["data", "history", "results"]:
                    if isinstance(h_data.get(k), list):
                        history = h_data[k]
                        break
            elif isinstance(h_data, list):
                history = h_data
    except Exception:
        history = []

    fii_history, dii_history = [], []
    for item in history[:5]:
        row = parse_fii_dii_record(item)
        if row["fii_net"] is not None:
            fii_history.append(row["fii_net"])
        if row["dii_net"] is not None:
            dii_history.append(row["dii_net"])

    fii_vals = [fii_net] + fii_history[:2] if fii_net is not None else fii_history[:3]
    dii_vals = [dii_net] + dii_history[:2] if dii_net is not None else dii_history[:3]

    fii_3d = sum(fii_vals) if fii_vals else None
    dii_3d = sum(dii_vals) if dii_vals else None

    score = 0
    if fii_net is not None:
        if fii_net >= 2000:
            score += 2
        elif fii_net >= 500:
            score += 1
        elif fii_net <= -2000:
            score -= 2
        elif fii_net <= -500:
            score -= 1

    if dii_net is not None:
        if dii_net >= 2000:
            score += 1
        elif dii_net >= 500:
            score += 1
        elif dii_net <= -2000:
            score -= 1
        elif dii_net <= -500:
            score -= 1

    if fii_3d is not None and fii_3d >= 5000:
        score += 1
    elif fii_3d is not None and fii_3d <= -5000:
        score -= 1

    bias = "MIXED"
    if fii_net is not None and dii_net is not None:
        if fii_net > 500 and dii_net > 500:
            bias = "BULLISH CONFIRMATION"
        elif fii_net < -500 and dii_net < -500:
            bias = "BEARISH CONFIRMATION"
        elif fii_net < -500 and dii_net > 500:
            bias = "FII SELLING / DII BUYING"
        elif fii_net > 500 and dii_net < -500:
            bias = "FII BUYING / DII SELLING"
        else:
            bias = "MIXED / WEAK"
    elif fii_net is not None:
        bias = "FII POSITIVE" if fii_net > 500 else ("FII NEGATIVE" if fii_net < -500 else "MIXED")

    bias_score = "POSITIVE" if score > 0 else ("NEGATIVE" if score < 0 else "NEUTRAL")

    return {
        "available": True,
        "source": "Free NSE-sourced FII/DII API",
        "date": parsed["date"],
        "fii_buy": parsed["fii_buy"],
        "fii_sell": parsed["fii_sell"],
        "fii_net": fii_net,
        "dii_buy": parsed["dii_buy"],
        "dii_sell": parsed["dii_sell"],
        "dii_net": dii_net,
        "combined_net": (fii_net + dii_net) if (fii_net is not None and dii_net is not None) else None,
        "fii_3d": fii_3d,
        "dii_3d": dii_3d,
        "institutional_score": score,
        "bias": bias,
        "bias_score": bias_score,
        "status": "Latest available / provisional",
    }


fii_dii = fetch_fii_dii()

# =========================================================
# CLIENT ENGINE INSTANTIATION
# =========================================================

@st.cache_resource(show_spinner=False)
def create_telemetry():
    if TelemetryEngine is None:
        return None
    if not all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET]):
        return None
    try:
        return TelemetryEngine(
            api_key=ANGEL_API_KEY,
            client_code=ANGEL_CLIENT_CODE,
            pin=ANGEL_PIN,
            totp_secret=ANGEL_TOTP_SECRET,
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
                client_code=ANGEL_CLIENT_CODE,
            )
    except Exception:
        pass

    telemetry_obj = create_telemetry()
    if telemetry_obj is not None:
        try:
            token = getattr(telemetry_obj.smart_api, "access_token", None)
            if token:
                return OptionsEngine(
                    jwt_token=str(token),
                    api_key=ANGEL_API_KEY,
                    client_code=ANGEL_CLIENT_CODE,
                )
        except Exception:
            pass
    return None


telemetry = create_telemetry()
options = create_options()

# =========================================================
# MARKET CONFIGURATION AND SPOT EXTRACTION
# =========================================================

UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]

SPOT_TOKENS = {
    "NIFTY": ("NSE", "99926000"),
    "BANKNIFTY": ("NSE", "99926009"),
    "FINNIFTY": ("NSE", "99926037"),
    "MIDCPNIFTY": ("NSE", "99926074"),
    "SENSEX": ("BSE", "99919000"),
    "BANKEX": ("BSE", "99919012"),
}


def get_spot(symbol):
    if telemetry is not None:
        try:
            result = telemetry.get_ltp(symbol)
            if isinstance(result, dict):
                for key in ("ltp", "LTP", "lastTradedPrice", "lastTradedPriceValue", "close", "price"):
                    if key in result:
                        val = num(result[key])
                        if val is not None and val > 0:
                            return val
            val = num(result)
            if val is not None and val > 0:
                return val
        except Exception:
            pass

    try:
        df = fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=5)
        if df is not None and not df.empty and "close" in df.columns:
            close = pd.to_numeric(df["close"], errors="coerce").dropna()
            if not close.empty:
                val = float(close.iloc[-1])
                if val > 0:
                    return val
    except Exception:
        pass
    return None

# =========================================================
# DERIVATIVES CONTRACTS AND OPTION CHAIN INGESTION
# =========================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_expiries(symbol):
    if options is None:
        return []
    try:
        result = options.get_expiry_options(symbol)
        values = []
        for item in result or []:
            val = item.get("value") or item.get("expiry") or item.get("expiryDate") if isinstance(item, dict) else item
            val = expiry_norm(val)
            if not val:
                continue
            try:
                d = datetime.strptime(val, "%Y-%m-%d").date()
                if d >= date.today():
                    values.append(val)
            except Exception:
                pass
        return sorted(set(values))
    except Exception:
        return []


@st.cache_data(ttl=120, show_spinner=False)
def load_contracts(symbol, expiry):
    if options is None or not expiry:
        return pd.DataFrame()
    try:
        return clean_df(options.get_option_contracts(underlying=symbol, expiry_date=expiry))
    except Exception:
        return pd.DataFrame()


def get_chain(symbol, expiry, spot):
    contracts = load_contracts(symbol, expiry)
    if contracts.empty:
        return pd.DataFrame(), contracts

    def normalize_strike_value(v):
        try:
            val = float(v)
            if abs(val) >= 100000:
                val = val / 100.0
            return val
        except Exception:
            return None

    try:
        strike_col = find_column(contracts, ["strike", "strikePrice", "strike_price"])
        if strike_col:
            contracts["strikePrice"] = pd.to_numeric(contracts[strike_col], errors="coerce").apply(normalize_strike_value)
            contracts["strike"] = contracts["strikePrice"]
    except Exception:
        pass

    try:
        if spot is not None and options is not None:
            near = options.get_near_atm_contracts(
                underlying=symbol,
                expiry_date=expiry,
                spot_price=spot,
                strikes_each_side=10,
            )
            near = clean_df(near)
            if not near.empty:
                contracts = near
                n_col = find_column(contracts, ["strike", "strikePrice", "strike_price"])
                if n_col:
                    contracts["strikePrice"] = pd.to_numeric(contracts[n_col], errors="coerce").apply(normalize_strike_value)
                    contracts["strike"] = contracts["strikePrice"]
    except Exception:
        pass

    try:
        quoted = clean_df(options.get_market_quote(contracts))
        chain = quoted if not quoted.empty else contracts.copy()
    except Exception:
        chain = contracts.copy()

    type_col = find_column(chain, ["option_type", "optionType", "optionTypeName", "option_type_name", "type"])
    if type_col:
        chain["option_type"] = chain[type_col].map(normalize_option_type)

    stk_col = find_column(chain, ["strike", "strikePrice", "strike_price"])
    if stk_col:
        chain["strikePrice"] = pd.to_numeric(chain[stk_col], errors="coerce").apply(normalize_strike_value)
        chain["strike"] = chain["strikePrice"]

    oi_col = find_column(chain, ["opnInterest", "openInterest", "oi", "open_interest"])
    if oi_col:
        chain["openInterest"] = pd.to_numeric(chain[oi_col], errors="coerce")

    chg_oi = find_column(chain, ["changeinOpenInterest", "changeInOpenInterest", "change_in_open_interest", "change_oi", "chg_oi", "oi_change"])
    if chg_oi:
        chain["changeInOpenInterest"] = pd.to_numeric(chain[chg_oi], errors="coerce")

    try:
        if options is not None:
            greeks = clean_df(options.greeks_dataframe(symbol, expiry))
            if not greeks.empty:
                g_stk = find_column(greeks, ["strikePrice", "strike", "strike_price"])
              
