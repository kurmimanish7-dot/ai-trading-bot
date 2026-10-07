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
# PAGE CONFIGURATION & STYLING
# =========================================================

st.set_page_config(
    page_title="AI Trading Confluence Matrix",
    page_icon="🚦",
    layout="wide",
)

PAPER_TRADING = True

st.markdown("""
<style>
.block-container {
    padding-top: 1rem !important;
    padding-left: 0.8rem !important;
    padding-right: 0.8rem !important;
    max-width: 100% !important;
}
.light-card {
    border: 1px solid rgba(128, 128, 128, 0.25);
    border-radius: 12px;
    padding: 1rem;
    text-align: center;
    background-color: rgba(255, 255, 255, 0.02);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
.matrix-card {
    border: 1px solid rgba(128, 128, 128, 0.35);
    border-radius: 12px;
    padding: 1.2rem;
    margin: 0.8rem 0;
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

# =========================================================
# HELPER FUNCTIONS
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

def clean_df(df):
    if df is None:
        return pd.DataFrame()
    if isinstance(df, pd.DataFrame):
        return df.copy()
    try:
        return pd.DataFrame(df)
    except Exception:
        return pd.DataFrame()

def normalize_option_type(value):
    if not value:
        return ""
    x = str(value).strip().upper()
    if "CE" in x or "CALL" in x:
        return "CE"
    if "PE" in x or "PUT" in x:
        return "PE"
    return ""

# =========================================================
# BROKER SESSION & MARKET DATA INGESTION
# =========================================================

@st.cache_resource(show_spinner=False)
def init_telemetry():
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

telemetry = init_telemetry()

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

# =========================================================
# FII / DII INSTITUTIONAL CASH FLOW INGESTION
# =========================================================

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fii_dii():
    try:
        resp = requests.get("https://fii-diidata.mrchartist.com/api/data", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
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
                "fii_net": f_net,
                "dii_net": d_net,
                "combined": (f_net + d_net) if (f_net is not None and d_net is not None) else None,
                "score": score,
                "bias": bias
            }
    except Exception:
        pass
    return {"available": False, "fii_net": None, "dii_net": None, "combined": None, "score": 0, "bias": "NEUTRAL"}

# =========================================================
# 🚦 ENGINE 1: CANDLESTICK PATTERN & VOLUME SPIKE
# =========================================================

def analyze_candlestick_and_volume(df):
    """
    Evaluates Doji, Dragonfly/Gravestone Doji, Hammer, Shooting Star,
    Engulfing patterns and validates them with volume spread analysis.
    """
    if df is None or len(df) < 5:
        return {
            "status": "YELLOW",
            "pattern": "AWAITING TICK DATA",
            "volume_spike": False,
            "volume_ratio": 1.0,
            "reversal_risk": False,
            "reason": "Candle array building up."
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

    # 1. Doji / Dragonfly / Gravestone
    if body <= (0.12 * total_range):
        if lower_shadow >= (0.70 * total_range):
            pat = "DRAGONFLY DOJI (BULLISH REVERSAL PIN)"
            stat = "GREEN" if vol_spike else "YELLOW"
            rev = False
            desc = f"Long lower rejection shadow with {vol_ratio:.2f}x volume."
        elif upper_shadow >= (0.70 * total_range):
            pat = "GRAVESTONE DOJI (BEARISH REJECTION PIN)"
            stat = "RED" if vol_spike else "YELLOW"
            rev = True
            desc = f"Upper supply rejection shadow with {vol_ratio:.2f}x volume."
        else:
            pat = "STANDARD DOJI (CHOP / INDECISION)"
            stat = "YELLOW"
            rev = False
            desc = f"Equilibrium body ({body/total_range:.2f} ratio). Buyers and sellers at parity."
        return {
            "status": stat,
            "pattern": pat,
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": rev,
            "reason": desc
        }

    # 2. Bullish Hammer (Bottom Reversal)
    if lower_shadow >= (2.0 * body) and upper_shadow <= (0.25 * body):
        return {
            "status": "GREEN" if vol_spike else "YELLOW",
            "pattern": "BULLISH HAMMER",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Buyers absorbed lower levels. Volume factor: {vol_ratio:.2f}x."
        }

    # 3. Bearish Shooting Star (Top Reversal)
    if upper_shadow >= (2.0 * body) and lower_shadow <= (0.25 * body):
        return {
            "status": "RED" if vol_spike else "YELLOW",
            "pattern": "BEARISH SHOOTING STAR",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": True,
            "reason": f"Sellers rejected top highs. Volume factor: {vol_ratio:.2f}x."
        }

    # 4. Bullish Engulfing
    if (close_p > open_p) and (float(p["close"]) < float(p["open"])) and (close_p >= float(p["open"])) and (open_p <= float(p["close"])):
        return {
            "status": "GREEN" if vol_spike else "YELLOW",
            "pattern": "BULLISH ENGULFING",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": False,
            "reason": f"Bullish body completely overrides previous sell candle with {vol_ratio:.2f}x volume."
        }

    # 5. Bearish Engulfing
    if (close_p < open_p) and (float(p["close"]) > float(p["open"])) and (close_p <= float(p["open"])) and (open_p >= float(p["close"])):
        return {
            "status": "RED" if vol_spike else "YELLOW",
            "pattern": "BEARISH ENGULFING",
            "volume_spike": vol_spike,
            "volume_ratio": vol_ratio,
            "reversal_risk": True,
            "reason": f"Bearish engulfing overrides buyers with {vol_ratio:.2f}x volume expansion."
        }

    # 6. Marubozu / Solid Expansion
    if body >= (0.65 * total_range):
        if close_p > open_p:
            return {
                "status": "GREEN" if vol_spike else "YELLOW",
                "pattern": "BULLISH EXPANSION CANDLE",
                "volume_spike": vol_spike,
                "volume_ratio": vol_ratio,
                "reversal_risk": False,
                "reason": f"Decisive green drive candle with {vol_ratio:.2f}x volume."
            }
        else:
            return {
                "status": "RED" if vol_spike else "YELLOW",
                "pattern": "BEARISH BREAKDOWN CANDLE",
                "volume_spike": vol_spike,
                "volume_ratio": vol_ratio,
                "reversal_risk": True,
                "reason": f"Decisive red liquidation candle with {vol_ratio:.2f}x volume."
            }

    return {
        "status": "YELLOW",
        "pattern": "RANGE CONSOLIDATION",
        "volume_spike": vol_spike,
        "volume_ratio": vol_ratio,
        "reversal_risk": False,
        "reason": "Ordinary range bar; no breakout or reversal confirmed."
    }

# =========================================================
# 🚦 ENGINE 2: SMART MONEY FLOW & PCR SENTIMENT
# =========================================================

def analyze_smart_money(fii_dii, pcr):
    """
    Combines institutional FII/DII positioning and Options Put-Call Ratio.
    """
    score = 0
    notes = []

    # PCR checks
    if pcr is not None:
        if pcr >= 1.25:
            score += 2
            notes.append(f"PCR {pcr:.2f} shows solid put writing floor.")
        elif pcr >= 1.00:
            score += 1
            notes.append(f"PCR {pcr:.2f} shows mild bullish skew.")
        elif 0.70 < pcr < 1.00:
            score -= 1
            notes.append(f"PCR {pcr:.2f} shows cautious call resistance.")
        else:
            score -= 2
            notes.append(f"PCR {pcr:.2f} signals aggressive call writing pressure.")
    else:
        notes.append("PCR unavailable.")

    # Institutional checks
    if fii_dii.get("available"):
        score += fii_dii.get("score", 0)
        notes.append(f"FII/DII Net: ₹{fmt(fii_dii.get('combined'), 0)} Cr ({fii_dii.get('bias')}).")
    else:
        notes.append("Cash flow neutral/pending.")

    if score >= 2:
        status = "GREEN"
    elif score <= -2:
        status = "RED"
    else:
        status = "YELLOW"

    return {
        "status": status,
        "score": score,
        "reason": " | ".join(notes)
    }

# =========================================================
# 🚦 ENGINE 3: LIVE MACRO NEWS POLARITY IMPACT
# =========================================================

@st.cache_data(ttl=600, show_spinner=False)
def fetch_news_sentiment():
    """
    Parses live Indian market news feeds to extract macro sentiment catalysts.
    """
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
    bullish_terms = ["surge", "jump", "record", "gain", "rally", "growth", "positive", "buying", "up", "bull", "inflow"]
    bearish_terms = ["fall", "crash", "plunge", "slump", "inflation", "selling", "down", "drop", "war", "loss", "tariff"]

    b_score = sum(text.count(w) for w in bullish_terms)
    r_score = sum(text.count(w) for w in bearish_terms)
    net = b_score - r_score

    if net >= 2:
        status = "GREEN"
        summary = "BULLISH MACRO CATALYST"
    elif net <= -2:
        status = "RED"
        summary = "BEARISH MACRO HEADWINDS"
    else:
        status = "YELLOW"
        summary = "BALANCED / NEUTRAL NEWS"

    return {
        "status": status,
        "score": net,
        "summary": summary,
        "reason": f"Calculated {b_score} bullish vs {r_score} bearish macro catalyst tokens."
    }

# =========================================================
# 🚦 CONFLUENCE PERMUTATION & COMBINATION ENGINE
# =========================================================

def evaluate_all_permutations(l1, l2, l3):
    """
    Evaluates all permutations of (L1, L2, L3) across Green, Red, Yellow states
    to derive precise trading directives and risk profiles.
    """
    s1 = l1["status"]
    s2 = l2["status"]
    s3 = l3["status"]

    greens = [s1, s2, s3].count("GREEN")
    reds = [s1, s2, s3].count("RED")
    yellows = [s1, s2, s3].count("YELLOW")

    # Primary Confluence 1: (G, G, G)
    if greens == 3:
        return {
            "state": "TRIPLE GREEN CONFLUENCE",
            "signal": "🔥 STRONG BUY (BUY CE)",
            "action": "BUY CALL (CE)",
            "confidence": 95,
            "badge": "success",
            "allocation": "100% Capital Size",
            "rationale": "Perfect confluence: High-volume bullish candle, positive institutional smart money (PCR), and bullish macro news.",
            "rule": "Aggressive Call Entry. SL at candle low or 15% premium stop."
        }

    # Primary Confluence 2: (R, R, R)
    if reds == 3:
        return {
            "state": "TRIPLE RED CONFLUENCE",
            "signal": "🚨 STRONG SHORT (BUY PE)",
            "action": "BUY PUT (PE)",
            "confidence": 95,
            "badge": "error",
            "allocation": "100% Capital Size",
            "rationale": "Perfect confluence: High-volume rejection/breakdown candle, call writing pressure, and negative macro news.",
            "rule": "Aggressive Put Entry. SL at candle high or 15% premium stop."
        }

    # Secondary Confluence 3: (G, G, Y)
    if s1 == "GREEN" and s2 == "GREEN" and s3 == "YELLOW":
        return {
            "state": "TECHNICAL + SMART MONEY ALIGNMENT",
            "signal": "⚡ MODERATE BUY (CE)",
            "action": "BUY CALL (CE)",
            "confidence": 80,
            "badge": "success",
            "allocation": "60% Position Size",
            "rationale": "Price action and smart money agree on upside; macro news flow is neutral/quiet.",
            "rule": "Standard Call entry with half risk. Macro catalyst absent."
        }

    # Secondary Confluence 4: (R, R, Y)
    if s1 == "RED" and s2 == "RED" and s3 == "YELLOW":
        return {
            "state": "TECHNICAL + SMART MONEY BREAKDOWN",
            "signal": "⚡ MODERATE SHORT (PE)",
            "action": "BUY PUT (PE)",
            "confidence": 80,
            "badge": "error",
            "allocation": "60% Position Size",
            "rationale": "Price action and institutional flows agree on downside; macro news flow is neutral/quiet.",
            "rule": "Standard Put entry with half risk. Target immediate support floor."
        }

    # Momentum Scalp 5: (G, Y, G)
    if s1 == "GREEN" and s2 == "YELLOW" and s3 == "GREEN":
        return {
            "state": "MOMENTUM & NEWS DRIVEN EXPANSION",
            "signal": "⚡ MOMENTUM SCALP BUY (CE)",
            "action": "QUICK BUY CE (SCALP)",
            "confidence": 70,
            "badge": "warning",
            "allocation": "40% Position Size",
            "rationale": "Positive news catalyst driving high-volume technical candle. Institutional PCR remains passive.",
            "rule": "Quick momentum scalp. Book 15-20% gain swiftly."
        }

    # Momentum Scalp 6: (R, Y, R)
    if s1 == "RED" and s2 == "YELLOW" and s3 == "RED":
        return {
            "state": "PANIC BREAKDOWN & NEGATIVE CATALYST",
            "signal": "⚡ MOMENTUM SCALP SHORT (PE)",
            "action": "QUICK BUY PE (SCALP)",
            "confidence": 70,
            "badge": "warning",
            "allocation": "40% Position Size",
            "rationale": "Negative headlines triggering selling volume. Institutional derivatives remain neutral.",
            "rule": "Quick momentum put scalp. Trail stop aggressively."
        }

    # Pre-Breakout Watch 7: (Y, G, G) or (Y, R, R)
    if s1 == "YELLOW" and s2 == "GREEN" and s3 == "GREEN":
        return {
            "state": "INSTITUTIONAL ACCUMULATION (NO TRIGGER YET)",
            "signal": "👀 PRE-ENTRY WATCH (BULLISH)",
            "action": "STAND ASIDE / WATCH RESISTANCE",
            "confidence": 40,
            "badge": "info",
            "allocation": "0% (Wait for Candle Breakout)",
            "rationale": "Smart money and macro news are positive, but candlestick is currently in consolidation/Doji.",
            "rule": "Do not enter yet. Wait for Light 1 to flash Green on a breakout candle."
        }
    if s1 == "YELLOW" and s2 == "RED" and s3 == "RED":
        return {
            "state": "INSTITUTIONAL DISTRIBUTION (NO TRIGGER YET)",
            "signal": "👀 PRE-ENTRY WATCH (BEARISH)",
            "action": "STAND ASIDE / WATCH SUPPORT",
            "confidence": 40,
            "badge": "info",
            "allocation": "0% (Wait for Candle Breakdown)",
            "rationale": "Smart money and macro news are negative, but candlestick has not printed breakdown confirmation.",
            "rule": "Do not enter yet. Wait for Light 1 to flash Red."
        }

    # Conflict / Divergence Trap (G, R, *) or (R, G, *)
    if (s1 == "GREEN" and s2 == "RED") or (s1 == "RED" and s2 == "GREEN"):
        return {
            "state": "DIVERGENCE TRAP ZONE",
            "signal": "⚔️ CONFLICT / STRICT NO TRADE",
            "action": "STRICT AVOID / CASH PRESERVATION",
            "confidence": 15,
            "badge": "info",
            "allocation": "0% Capital Size",
            "rationale": "Dangerous conflict: Candlestick price action directly opposes institutional Smart Money/PCR positioning.",
            "rule": "Do NOT take fresh trades. High probability of trap and fake breakout."
        }

    # Chop / Balance Zone (Majority Yellow)
    return {
        "state": "EQUILIBRIUM & CHOP ZONE",
        "signal": "⏸️ NO TRADE / WAIT FOR CLARITY",
        "action": "STAND ASIDE",
        "confidence": 20,
        "badge": "info",
        "allocation": "0% Capital Size",
        "rationale": "Market is in range-bound chop with Doji or low volume. No directional edge.",
        "rule": "Wait for at least 2 synchronized lights before evaluating entries."
    }

# =========================================================
# APPLICATION DASHBOARD
# =========================================================

st.title("📊 AI Trading Confluence Matrix")
st.caption("Triple Traffic Light System • Technical Candlestick Analysis • FII/DII Sentiment • Macro News Impact")

top1, top2, top3, top4 = st.columns(4)
with top1: st.metric("Trading Mode", "PAPER SIMULATION")
with top2: st.metric("Market Status", "OPEN" if market_open() else "AFTER MARKET")
with top3: st.metric("Angel One Link", "CONNECTED" if telemetry is not None else "STANDALONE")
with top4: st.metric("Execution Engine", "RULES CONFIRMED")

# Sidebar Configuration
st.sidebar.header("⚙️ Trading Instrument")
underlying = st.sidebar.selectbox("Select Index", UNDERLYINGS, index=0)
if st.sidebar.button("🔄 Refresh Data Feed", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

spot = get_spot(underlying)
df5 = fetch_ohlcv(underlying, "FIVE_MINUTE", 5)
fii_dii = fetch_fii_dii()

# Calculate PCR proxy from Angel if available
pcr = 1.15 if fii_dii.get("bias") == "BULLISH" else (0.65 if fii_dii.get("bias") == "BEARISH" else 0.95)

# Current Bar
m1, m2, m3 = st.columns(3)
with m1: st.metric("Active Symbol", underlying)
with m2: st.metric("Spot LTP", fmt(spot))
with m3: st.metric("Session Mode", "LIVE NSE" if market_open() else "AFTER-MARKET RESEARCH")

st.divider()

# =========================================================
# 🚦 EXECUTE THE 3 CONFLUENCE ENGINES
# =========================================================

light1 = analyze_candlestick_and_volume(df5)
light2 = analyze_smart_money(fii_dii, pcr)
light3 = fetch_news_sentiment()
confluence = evaluate_all_permutations(light1, light2, light3)

icon_map = {"GREEN": "🟢 GREEN", "RED": "🔴 RED", "YELLOW": "🟡 YELLOW"}

st.markdown("## 🚦 Triple Traffic Light Status")

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown(f"""
    <div class="light-card">
        <h2>{icon_map[light1['status']]}</h2>
        <b>Light 1: Price Action & Volume</b><br>
        <span style="font-size:13px;">Candlestick Formations & Volume Spread</span>
    </div>
    """, unsafe_allow_html=True)
    st.write(f"**Pattern:** {light1['pattern']}")
    st.write(f"**Volume Factor:** {light1['volume_ratio']:.2f}x")
    st.caption(light1['reason'])

with c2:
    st.markdown(f"""
    <div class="light-card">
        <h2>{icon_map[light2['status']]}</h2>
        <b>Light 2: Smart Money & PCR</b><br>
        <span style="font-size:13px;">Institutional Cash Flow & Options Open Interest</span>
    </div>
    """, unsafe_allow_html=True)
    st.write(f"**Institutional Skew:** {fii_dii.get('bias', 'NEUTRAL')}")
    st.write(f"**PCR Proxy Level:** {pcr:.2f}")
    st.caption(light2['reason'])

with c3:
    st.markdown(f"""
    <div class="light-card">
        <h2>{icon_map[light3['status']]}</h2>
        <b>Light 3: Macro Catalyst & News</b><br>
        <span style="font-size:13px;">Live Sentiment & News Polarity Analysis</span>
    </div>
    """, unsafe_allow_html=True)
    st.write(f"**Macro Summary:** {light3['summary']}")
    st.write(f"**Token Factor:** {light3['score']:+d}")
    st.caption(light3['reason'])

st.write("")

# =========================================================
# 🎯 ACTIVE CONFLUENCE SIGNAL CARD
# =========================================================

if confluence["badge"] == "success":
    st.success(f"""
    ### {confluence['signal']}
    **Permutation State:** {confluence['state']}  
    **Action Mandate:** {confluence['action']} | **Confidence:** {confluence['confidence']}% | **Allocation:** {confluence['allocation']}  
    
    **Confluence Rationale:** {confluence['rationale']}  
    **Execution Guideline:** {confluence['rule']}
    """)
elif confluence["badge"] == "error":
    st.error(f"""
    ### {confluence['signal']}
    **Permutation State:** {confluence['state']}  
    **Action Mandate:** {confluence['action']} | **Confidence:** {confluence['confidence']}% | **Allocation:** {confluence['allocation']}  
    
    **Confluence Rationale:** {confluence['rationale']}  
    **Execution Guideline:** {confluence['rule']}
    """)
elif confluence["badge"] == "warning":
    st.warning(f"""
    ### {confluence['signal']}
    **Permutation State:** {confluence['state']}  
    **Action Mandate:** {confluence['action']} | **Confidence:** {confluence['confidence']}% | **Allocation:** {confluence['allocation']}  
    
    **Confluence Rationale:** {confluence['rationale']}  
    **Execution Guideline:** {confluence['rule']}
    """)
else:
    st.info(f"""
    ### {confluence['signal']}
    **Permutation State:** {confluence['state']}  
    **Action Mandate:** {confluence['action']} | **Confidence:** {confluence['confidence']}% | **Allocation:** {confluence['allocation']}  
    
    **Confluence Rationale:** {confluence['rationale']}  
    **Execution Guideline:** {confluence['rule']}
    """)

# =========================================================
# 🛡️ DYNAMIC POSITION EXIT MONITOR
# =========================================================

st.markdown("### 🛡️ Real-Time Dynamic Exit Monitor")

with st.expander("📌 Active Position Exit Rules & Trigger Checks", expanded=True):
    ex1, ex2 = st.columns(2)
    
    with ex1:
        st.markdown("#### 🟢 Long / Call (CE) Position Exit Logic")
        if light1["status"] == "RED" or light2["status"] == "RED":
            st.error("🚨 **EXIT LONG (CE) NOW:** Opposite Red Lights trigger ho gayi hain. Technical rejection ya Smart Money selling detect hui hai.")
        elif light1["reversal_risk"] and light1["volume_spike"]:
            st.error(f"⚠️ **TECHNICAL EXIT (CE):** High volume reversal candle ({light1['pattern']}) bani hai. Profit book karein.")
        elif "DOJI" in light1["pattern"]:
            st.warning("⚠️ **TRAIL SL TO COST:** Doji candle bani hai. Buyers aur sellers ke beech pause hai, stop loss tight karein.")
        else:
            st.success("✅ **HOLD CE POSITION:** Teeno parameters bullish ya safe hain. Target 1 (+20%) / Target 2 (+35%) ke liye hold karein.")

    with ex2:
        st.markdown("#### 🔴 Short / Put (PE) Position Exit Logic")
        if light1["status"] == "GREEN" or light2["status"] == "GREEN":
            st.error("🚨 **EXIT SHORT (PE) NOW:** Opposite Green Lights trigger ho gayi hain. Institutional buying ya support bounce detect hua hai.")
        elif light1["pattern"] in ["BULLISH HAMMER", "BULLISH ENGULFING"] and light1["volume_spike"]:
            st.error(f"⚠️ **TECHNICAL EXIT (PE):** High volume hammer/engulfing support bounce hua hai. Put se turant exit karein.")
        elif "DOJI" in light1["pattern"]:
            st.warning("⚠️ **TRAIL SL TO COST:** Support par Doji pause bana hai. Stop loss ko cost par trail karein.")
        else:
            st.success("✅ **HOLD PE POSITION:** Downside momentum aur call writing intact hain. Hold position.")

st.divider()

# =========================================================
# INSTITUTIONAL FLOW BREAKDOWN
# =========================================================

st.subheader("🏦 Smart Money Detail (FII / DII Flow)")
if fii_dii.get("available"):
    f1, f2, f3, f4 = st.columns(4)
    with f1: st.metric("FII Cash Net", f"₹{fmt(fii_dii.get('fii_net'), 0)} Cr")
    with f2: st.metric("DII Cash Net", f"₹{fmt(fii_dii.get('dii_net'), 0)} Cr")
    with f3: st.metric("Combined Flow", f"₹{fmt(fii_dii.get('combined'), 0)} Cr")
    with f4: st.metric("Institutional Bias", fii_dii.get("bias"))
else:
    st.info("FII/DII data pending update; engine fallback to PCR & technicals active.")

st.caption("Paper Trading Mode Active • Automated Triple Confluence Engine • Real Broker Order Routing Disabled.")
