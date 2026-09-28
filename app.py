import os
import json
import time
from datetime import datetime

import streamlit as st
import pandas as pd

from telemetry_engine import TelemetryEngine
from advanced_analysis import build_advanced_analysis
from options_engine import OptionsEngine

from config import (
    AI_MODEL,
    PAPER_TRADING,
    MIN_AI_CONFIDENCE,
    EXCHANGE,
    SYMBOL,
    TOKEN,
    CANDLE_INTERVAL,
    HISTORICAL_DAYS,
)

try:
    from google import genai
except Exception:
    genai = None


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="AI Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# MOBILE FRIENDLY CSS
# ============================================================

st.markdown(
    """
    <style>

    .block-container {
        padding-top: 0.8rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }

    .section-title {
        font-size: 1.15rem;
        font-weight: 700;
        margin-top: 1.2rem;
        margin-bottom: 0.55rem;
    }

    .metric-card {
        border: 1px solid rgba(128,128,128,.28);
        border-radius: 12px;
        padding: 12px 14px;
        min-height: 88px;
        overflow: hidden;
    }

    .metric-label {
        font-size: 0.76rem;
        opacity: 0.72;
        margin-bottom: 5px;
    }

    .metric-value {
        font-size: 1.35rem;
        font-weight: 700;
        line-height: 1.25;
        white-space: normal;
        overflow-wrap: anywhere;
        word-break: normal;
    }

    .metric-sub {
        font-size: 0.76rem;
        opacity: 0.68;
        margin-top: 4px;
    }

    .signal-card {
        border: 1px solid rgba(128,128,128,.28);
        border-radius: 12px;
        padding: 14px;
        min-height: 115px;
    }

    .signal-value {
        font-size: 1.45rem;
        font-weight: 800;
        margin-top: 7px;
        overflow-wrap: anywhere;
    }

    .small-muted {
        font-size: 0.8rem;
        opacity: 0.7;
    }

    @media (max-width: 700px) {

        .block-container {
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }

        .section-title {
            font-size: 1.05rem;
        }

        .metric-value {
            font-size: 1.15rem;
        }

        .signal-value {
            font-size: 1.25rem;
        }
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SAFETY LOCK
# ============================================================

if PAPER_TRADING is not True:
    st.error(
        "🚨 SAFETY LOCK: PAPER_TRADING must remain True."
    )
    st.stop()


# ============================================================
# HEADER
# ============================================================

st.title("📈 AI Trading Bot")

st.caption(
    "Live Market Analysis • Options Intelligence • AI Signals • Paper Trading"
)

st.success(
    "🛡️ PAPER TRADING MODE — REAL ORDERS ARE DISABLED"
)


# ============================================================
# SECRET HELPERS
# ============================================================

def get_secret(name):
    value = os.getenv(name)

    if value:
        return value

    try:
        value = st.secrets.get(name)

        if value:
            return value
    except Exception:
        pass

    return None


def get_credentials():
    return {
        "api_key": get_secret("ANGEL_API_KEY"),
        "client_code": get_secret("ANGEL_CLIENT_CODE"),
        "pin": get_secret("ANGEL_PIN"),
        "totp_secret": get_secret("ANGEL_TOTP_SECRET"),
    }


def get_gemini_key():
    return get_secret("GEMINI_API_KEY")


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "telemetry": None,
    "options_engine": None,
    "connected": False,

    "jwt_token": None,
    "feed_token": None,

    "api_key": None,
    "client_code": None,

    "last_df": pd.DataFrame(),
    "last_ltp": None,

    "last_error": "",

    "ai_result": {
        "signal": "WAITING",
        "confidence": 0,
        "reason": "Waiting for live market data.",
    },

    "last_ai_time": 0,

    "options_chain": pd.DataFrame(),
    "options_greeks": pd.DataFrame(),
    "options_pcr": pd.DataFrame(),
    "options_oi": {},

    "selected_underlying": "NIFTY",
    "selected_expiry": None,
}


for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# CONNECTION
# ============================================================

def credentials_available():

    c = get_credentials()

    return all(
        [
            c["api_key"],
            c["client_code"],
            c["pin"],
            c["totp_secret"],
        ]
    )


def ensure_connection():

    if st.session_state.telemetry is not None:
        st.session_state.connected = True
        return True

    credentials = get_credentials()

    if not all(credentials.values()):

        st.session_state.connected = False

        return False

    try:

        engine = TelemetryEngine(
            api_key=credentials["api_key"],
            client_code=credentials["client_code"],
            pin=credentials["pin"],
            totp_secret=credentials["totp_secret"],
        )

        st.session_state.telemetry = engine
        st.session_state.connected = True

        st.session_state.api_key = credentials["api_key"]
        st.session_state.client_code = credentials["client_code"]

        try:
            st.session_state.feed_token = engine.feed_token
        except Exception:
            pass

        try:
            st.session_state.jwt_token = engine.jwt_token
        except Exception:
            pass

        st.session_state.last_error = ""

        return True

    except Exception as e:

        st.session_state.connected = False
        st.session_state.last_error = str(e)

        return False


# ============================================================
# OPTIONS ENGINE
# ============================================================

def ensure_options_engine():

    if st.session_state.options_engine is not None:
        return st.session_state.options_engine

    if not ensure_connection():
        return None

    jwt_token = st.session_state.jwt_token

    if not jwt_token:

        try:
            jwt_token = getattr(
                st.session_state.telemetry.smart_api,
                "access_token",
                None,
            )
        except Exception:
            jwt_token = None

    if not jwt_token:
        return None

    try:

        engine = OptionsEngine(
            jwt_token=jwt_token,
            api_key=st.session_state.api_key,
            client_code=st.session_state.client_code,
        )

        st.session_state.options_engine = engine

        return engine

    except Exception as e:

        st.session_state.last_error = (
            "Options Engine: " + str(e)
        )

        return None


# ============================================================
# MARKET DATA
# ============================================================

def fetch_market_data():

    if not ensure_connection():
        return None

    try:

        df = st.session_state.telemetry.fetch_ohlcv(
            exchange=EXCHANGE,
            token=str(TOKEN),
            interval=CANDLE_INTERVAL,
            days=HISTORICAL_DAYS,
        )

        if df is None or df.empty:
            return None

        st.session_state.last_error = ""

        return df

    except Exception as e:

        st.session_state.last_error = str(e)

        return None


def fetch_live_ltp():

    if not ensure_connection():
        return None

    try:

        result = st.session_state.telemetry.get_live_ltp(
            exchange=EXCHANGE,
            tradingsymbol=SYMBOL,
            symboltoken=str(TOKEN),
        )

        if result and result.get("status"):

            value = float(result["ltp"])

            st.session_state.last_ltp = value

            return value

    except Exception as e:

        st.session_state.last_error = str(e)

    return None


def apply_ltp(df, ltp):

    if df is None or df.empty or ltp is None:
        return df

    result = df.copy()

    try:

        idx = result.index[-1]

        result.loc[idx, "close"] = float(ltp)

        result.loc[idx, "high"] = max(
            float(result.loc[idx, "high"]),
            float(ltp),
        )

        result.loc[idx, "low"] = min(
            float(result.loc[idx, "low"]),
            float(ltp),
        )

    except Exception:
        pass

    return result


# ============================================================
# INDICATORS
# ============================================================

def safe_indicators(df):

    if df is None or df.empty:
        return {}

    try:

        result = TelemetryEngine.calculate_indicators(df)

        # NIFTY index may not provide usable volume.
        if "volume" in df.columns:

            volume_total = pd.to_numeric(
                df["volume"],
                errors="coerce"
            ).fillna(0).sum()

            if volume_total <= 0:
                result["vwap"] = None
                result["price_vs_vwap"] = "UNAVAILABLE"

        return result

    except Exception as e:

        st.session_state.last_error = (
            "Indicator error: " + str(e)
        )

        return {}


def safe_advanced(df):

    if df is None or df.empty:
        return {"status": "NO_DATA"}

    try:

        return build_advanced_analysis(df)

    except Exception as e:

        return {
            "status": "ERROR",
            "error": str(e),
        }


# ============================================================
# NUMBER FORMAT
# ============================================================

def fmt_number(value, decimals=2):

    if value is None:
        return "N/A"

    try:
        if pd.isna(value):
            return "N/A"

        return f"{float(value):,.{decimals}f}"

    except Exception:
        return str(value)


def show_card(label, value, sub=None):

    sub_html = ""

    if sub:
        sub_html = (
            f'<div class="metric-sub">{sub}</div>'
        )

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# AI
# ============================================================

def call_gemini(indicators, advanced, ltp):

    api_key = get_gemini_key()

    if not api_key:

        return {
            "signal": "WAITING",
            "confidence": 0,
            "reason": "Gemini API key not configured.",
        }

    if genai is None:

        return {
            "signal": "WAITING",
            "confidence": 0,
            "reason": "Gemini SDK unavailable.",
        }

    prompt = f"""
You are an AI market-analysis assistant.

PAPER TRADING ONLY.
Never place real orders.

Use ONLY supplied market data.
Never invent unavailable VIX, OI, PCR, IV, Greeks or news.

Instrument:
{SYMBOL}

Current price:
{ltp}

Technical indicators:
{json.dumps(indicators, default=str)}

Advanced analysis:
{json.dumps(advanced, default=str)}

Return ONLY valid JSON.

Allowed signals:
ENTER_LONG
ENTER_SHORT
NO_TRADE

Confidence must be between 0 and 100.

JSON:
{{
    "signal": "NO_TRADE",
    "confidence": 0,
    "reason": "Short explanation"
}}
"""

    try:

        client = genai.Client(
            api_key=api_key
        )

        response = client.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
        )

        raw = (
            response.text
            if response and response.text
            else ""
        )

        raw = (
            raw
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        result = json.loads(raw)

        signal = str(
            result.get(
                "signal",
                "NO_TRADE",
            )
        ).upper()

        confidence = float(
            result.get(
                "confidence",
                0,
            )
        )

        reason = str(
            result.get(
                "reason",
                "No clear setup.",
            )
        )

        allowed = {
            "ENTER_LONG",
            "ENTER_SHORT",
            "NO_TRADE",
        }

        if signal not in allowed:
            signal = "NO_TRADE"

        confidence = max(
            0,
            min(
                100,
                confidence,
            ),
        )

        if confidence < MIN_AI_CONFIDENCE:
            signal = "NO_TRADE"

        return {
            "signal": signal,
            "confidence": confidence,
            "reason": reason[:300],
        }

    except Exception as e:

        return {
            "signal": "WAITING",
            "confidence": 0,
            "reason": "Gemini error: " + str(e),
        }


# ============================================================
# TRADE LEVELS
# ============================================================

def calculate_levels(signal, price, atr):

    if price is None:
        return {
            "entry": None,
            "sl": None,
            "target1": None,
            "target2": None,
        }

    try:

        price = float(price)
        atr = float(atr or 0)

    except Exception:

        return {
            "entry": None,
            "sl": None,
            "target1": None,
            "target2": None,
        }

    if atr <= 0:
        atr = max(
            price * 0.002,
            1,
        )

    if signal == "ENTER_LONG":

        return {
            "entry": price,
            "sl": price - 1.5 * atr,
            "target1": price + 2 * atr,
            "target2": price + 3 * atr,
        }

    if signal == "ENTER_SHORT":

        return {
            "entry": price,
            "sl": price + 1.5 * atr,
            "target1": price - 2 * atr,
            "target2": price - 3 * atr,
        }

    return {
        "entry": None,
        "sl": None,
        "target1": None,
        "target2": None,
    }


# ============================================================
# OPTIONS HELPERS
# ============================================================

def load_expiries(underlying):

    engine = ensure_options_engine()

    if engine is None:
        return []

    try:

        return engine.get_expiries(
            underlying
        ) or []

    except Exception as e:

        st.session_state.last_error = str(e)

        return []


def load_option_chain(
    underlying,
    expiry,
    spot,
    strikes,
):

    engine = ensure_options_engine()

    if engine is None:
        return pd.DataFrame()

    try:

        return engine.get_option_chain(
            underlying=underlying,
            expiry_date=expiry,
            spot_price=float(spot),
            strikes_each_side=int(strikes),
        )

    except Exception as e:

        st.session_state.last_error = str(e)

        return pd.DataFrame()


def load_greeks(
    underlying,
    expiry,
):

    engine = ensure_options_engine()

    if engine is None:
        return pd.DataFrame()

    try:

        return engine.greeks_dataframe(
            underlying=underlying,
            expiry_date=expiry,
        )

    except Exception as e:

        st.session_state.last_error = str(e)

        return pd.DataFrame()


def load_pcr():

    engine = ensure_options_engine()

    if engine is None:
        return pd.DataFrame()

    try:

        return engine.pcr_dataframe()

    except Exception as e:

        st.session_state.last_error = str(e)

        return pd.DataFrame()


def load_oi():

    engine = ensure_options_engine()

    if engine is None:
        return {}

    try:

        return engine.get_all_oi_buildup(
            expiry_type="NEAR"
        ) or {}

    except Exception as e:

        st.session_state.last_error = str(e)

        return {}


def format_option_chain(df):

    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()

    rename = {
        "strike": "Strike",
        "option_type": "Type",
        "ltp": "LTP",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Prev Close",
        "tradeVolume": "Volume",
        "opnInterest": "OI",
        "totBuyQuan": "Buy Qty",
        "totSellQuan": "Sell Qty",
        "symbol": "Symbol",
    }

    for old, new in rename.items():

        if old in work.columns:

            work.rename(
                columns={
                    old: new
                },
                inplace=True,
            )

    preferred = [
        "Strike",
        "Type",
        "LTP",
        "OI",
        "Volume",
        "Buy Qty",
        "Sell Qty",
        "Open",
        "High",
        "Low",
        "Prev Close",
        "Symbol",
    ]

    cols = [
        c for c in preferred
        if c in work.columns
    ]

    if cols:
        work = work[cols]

    return work


# ============================================================
# PLACEHOLDER
# ============================================================

def unavailable(label, detail):

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">WAITING</div>
            <div class="small-muted">⏳ {detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Control Panel")

    st.write("### Connection")

    if credentials_available():

        st.success(
            "Angel One credentials detected"
        )

    else:

        st.warning(
            "Angel One credentials not configured"
        )

    if st.button(
        "🔄 Connect / Refresh Connection",
        use_container_width=True,
    ):

        st.session_state.telemetry = None
        st.session_state.options_engine = None
        st.session_state.connected = False
        st.session_state.jwt_token = None
        st.session_state.last_error = ""

        ensure_connection()

        st.rerun()

    st.divider()

    auto_refresh = st.checkbox(
        "🔄 Auto Refresh",
        value=False,
    )

    refresh_seconds = st.selectbox(
        "Refresh Interval",
        [5, 10, 15, 30, 60],
        index=2,
    )

    st.divider()

    st.write("### Safety")

    st.info(
        "Paper Trading Only"
    )

    st.caption(
        "Real orders are disabled by the safety lock."
    )


# ============================================================
# INITIAL DATA
# ============================================================

live_df = None
live_ltp = None
indicators = {}
advanced = {
    "status": "NO_DATA"
}


if st.session_state.connected:

    live_df = fetch_market_data()

    live_ltp = fetch_live_ltp()

    if live_df is not None:

        if live_ltp is not None:

            live_df = apply_ltp(
                live_df,
                live_ltp,
            )

        st.session_state.last_df = live_df

else:

    if (
        st.session_state.last_df is not None
        and not st.session_state.last_df.empty
    ):

        live_df = st.session_state.last_df


# ============================================================
# ANALYSIS
# ============================================================

if live_df is not None and not live_df.empty:

    indicators = safe_indicators(
        live_df
    )

    advanced = safe_advanced(
        live_df
    )

    if live_ltp is None:

        try:

            live_ltp = float(
                live_df["close"].iloc[-1]
            )

        except Exception:

            live_ltp = None


# ============================================================
# AI UPDATE
# IMPORTANT: AI BEFORE DISPLAY
# ============================================================

if (
    live_ltp is not None
    and indicators
):

    now = time.time()

    if (
        now
        - st.session_state.last_ai_time
        >= 60
    ):

        st.session_state.ai_result = call_gemini(
            indicators,
            advanced,
            live_ltp,
        )

        st.session_state.last_ai_time = now


# ============================================================
# CONNECTION BANNER
# ============================================================

if not st.session_state.connected:

    st.warning(
        "📡 Angel One connection is not active."
    )

else:

    st.success(
        "🟢 Angel One SmartAPI connected"
    )


# ============================================================
# MARKET OVERVIEW
# ============================================================

st.markdown(
    '<div class="section-title">📊 Market Overview</div>',
    unsafe_allow_html=True,
)

m1, m2 = st.columns(2)

with m1:

    show_card(
        "NIFTY / Instrument",
        fmt_number(live_ltp),
        SYMBOL,
    )

with m2:

    show_card(
        "RSI",
        fmt_number(
            indicators.get("rsi")
        ),
        "RSI 14",
    )


m3, m4 = st.columns(2)

with m3:

    vwap_value = indicators.get("vwap")

    if vwap_value is None:
        vwap_text = "N/A"
        vwap_sub = "Volume unavailable"
    else:
        vwap_text = fmt_number(vwap_value)
        vwap_sub = "VWAP"

    show_card(
        "VWAP",
        vwap_text,
        vwap_sub,
    )

with m4:

    show_card(
        "ADX",
        fmt_number(
            indicators.get("adx")
        ),
        "ADX 14",
    )


m5 = st.container()

with m5:

    show_card(
        "Market Regime",
        indicators.get(
            "market_regime",
            "WAITING",
        ),
    )


# ============================================================
# MARKET DIRECTION
# ============================================================

st.markdown(
    '<div class="section-title">🧭 Market Direction</div>',
    unsafe_allow_html=True,
)

d1, d2 = st.columns(2)

with d1:

    show_card(
        "EMA Trend",
        indicators.get(
            "ema_trend",
            "WAITING",
        ),
    )

with d2:

    show_card(
        "Supertrend",
        indicators.get(
            "supertrend",
            "WAITING",
        ),
    )


d3, d4 = st.columns(2)

with d3:

    show_card(
        "Price vs VWAP",
        indicators.get(
            "price_vs_vwap",
            "WAITING",
        ),
    )

with d4:

    structure = (
        advanced
        .get(
            "market_structure",
            {}
        )
        .get(
            "trend",
            "WAITING",
        )
    )

    show_card(
        "Market Structure",
        structure,
    )


# ============================================================
# AI SIGNAL
# ============================================================

st.markdown(
    '<div class="section-title">🤖 AI Trading Signal</div>',
    unsafe_allow_html=True,
)

ai = st.session_state.ai_result

a1, a2 = st.columns(2)

with a1:

    signal = ai.get(
        "signal",
        "WAITING",
    )

    st.markdown(
        f"""
        <div class="signal-card">
            <div class="metric-label">AI SIGNAL</div>
            <div class="signal-value">{signal}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with a2:

    confidence = float(
        ai.get(
            "confidence",
            0,
        )
    )

    show_card(
        "AI Confidence",
        f"{confidence:.0f}%",
    )


st.markdown(
    '<div class="metric-card">'
    '<div class="metric-label">AI REASON</div>'
    f'<div>{ai.get("reason", "Waiting for analysis.")}</div>'
    '</div>',
    unsafe_allow_html=True,
)


# ============================================================
# PAPER TRADE PLAN
# ============================================================

st.markdown(
    '<div class="section-title">🎯 Paper Trade Plan</div>',
    unsafe_allow_html=True,
)

levels = calculate_levels(
    ai.get("signal"),
    live_ltp,
    indicators.get("atr"),
)


p1, p2 = st.columns(2)

with p1:

    show_card(
        "Entry",
        fmt_number(levels["entry"]),
    )

with p2:

    show_card(
        "Stop Loss",
        fmt_number(levels["sl"]),
    )


p3, p4 = st.columns(2)

with p3:

    show_card(
        "Target 1",
        fmt_number(levels["target1"]),
    )

with p4:

    show_card(
        "Target 2",
        fmt_number(levels["target2"]),
    )


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

st.markdown(
    '<div class="section-title">📐 Technical Analysis</div>',
    unsafe_allow_html=True,
)

t1, t2 = st.columns(2)

with t1:

    show_card(
        "EMA 9",
        fmt_number(
            indicators.get("ema_9")
        ),
    )

with t2:

    show_card(
        "EMA 21",
        fmt_number(
            indicators.get("ema_21")
        ),
    )


t3, t4 = st.columns(2)

with t3:

    show_card(
        "EMA 50",
        fmt_number(
            indicators.get("ema_50")
        ),
    )

with t4:

    show_card(
        "ATR",
        fmt_number(
            indicators.get("atr")
        ),
    )


t5 = st.container()

with t5:

    ema200 = (
        advanced
        .get(
            "ema_200",
            {}
        )
        .get(
            "value",
            None,
        )
    )

    show_card(
        "EMA 200",
        fmt_number(ema200),
    )


# ============================================================
# ADVANCED PRICE ACTION
# ============================================================

st.markdown(
    '<div class="section-title">🔬 Advanced Price Action</div>',
    unsafe_allow_html=True,
)

patterns = advanced.get(
    "candlestick_patterns",
    [],
)

if patterns:

    pattern_text = " • ".join(
        str(x)
        for x in patterns
    )

else:

    pattern_text = "WAITING"


ap1, ap2 = st.columns(2)

with ap1:

    show_card(
        "Candlestick Pattern",
        pattern_text,
    )

with ap2:

    macd = advanced.get(
        "macd",
        {},
    )

    show_card(
        "MACD Bias",
        macd.get(
            "bias",
            "WAITING",
        ),
    )


ap3, ap4 = st.columns(2)

with ap3:

    sr = advanced.get(
        "support_resistance",
        {},
    )

    support = sr.get(
        "support",
        None,
    )

    show_card(
        "Support",
        fmt_number(support),
    )

with ap4:

    resistance = sr.get(
        "resistance",
        None,
    )

    show_card(
        "Resistance",
        fmt_number(resistance),
    )


volume = advanced.get(
    "volume",
    {},
)

show_card(
    "Volume",
    volume.get(
        "volume_signal",
        "WAITING",
    ),
)


# ============================================================
# LIVE CANDLES
# ============================================================

st.markdown(
    '<div class="section-title">🕯️ Live Candles</div>',
    unsafe_allow_html=True,
)

if live_df is not None and not live_df.empty:

    chart_df = live_df.tail(100).copy()

    if "timestamp" in chart_df.columns:

        chart_df = chart_df.set_index(
            "timestamp"
        )

    if "close" in chart_df.columns:

        st.line_chart(
            chart_df["close"]
        )

    with st.expander(
        "📋 View recent candles"
    ):

        display_df = live_df.tail(20).copy()

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )

else:

    unavailable(
        "Live Candle Data",
        "Waiting for Angel One market data",
    )


# ============================================================
# OPTIONS INTELLIGENCE
# ============================================================

st.markdown(
    '<div class="section-title">📊 Options Intelligence</div>',
    unsafe_allow_html=True,
)

if not st.session_state.connected:

    unavailable(
        "Options Chain",
        "Waiting for Angel One connection",
    )

else:

    o1, o2 = st.columns(2)

    with o1:

        underlying = st.selectbox(
            "Underlying",
            [
                "NIFTY",
                "BANKNIFTY",
            ],
            key="option_underlying",
        )

    with o2:

        strikes = st.slider(
            "Strikes on each side",
            min_value=2,
            max_value=10,
            value=5,
        )

    refresh_options = st.button(
        "🔄 Load Options",
        use_container_width=True,
    )

    expiries = load_expiries(
        underlying
    )

    if expiries:

        expiry = st.selectbox(
            "Expiry",
            expiries,
            key="option_expiry",
        )

        st.session_state.selected_expiry = expiry

        spot = live_ltp

        if spot is None:

            spot = indicators.get(
                "ltp"
            )

        if refresh_options and spot is not None:

            chain = load_option_chain(
                underlying,
                expiry,
                spot,
                strikes,
            )

            greeks = load_greeks(
                underlying,
                expiry,
            )

            pcr = load_pcr()

            oi = load_oi()

            st.session_state.options_chain = chain
            st.session_state.options_greeks = greeks
            st.session_state.options_pcr = pcr
            st.session_state.options_oi = oi

            st.session_state.last_error = ""

        chain = st.session_state.options_chain

        if chain is not None and not chain.empty:

            formatted = format_option_chain(
                chain
            )

            st.write(
                "### 🟢 Live CE / PE Chain"
            )

            st.dataframe(
                formatted,
                use_container_width=True,
                hide_index=True,
            )

        else:

            unavailable(
                "Option Chain",
                "Press Load Options for live chain",
            )


        # ----------------------------------------------------
        # GREEKS
        # ----------------------------------------------------

        st.write("### 🧮 Greeks / IV")

        greeks = st.session_state.options_greeks

        if greeks is not None and not greeks.empty:

            preferred = [
                "strikePrice",
                "delta",
                "gamma",
                "theta",
                "vega",
                "impliedVolatility",
                "tradeVolume",
            ]

            cols = [
                c
                for c in preferred
                if c in greeks.columns
            ]

            st.dataframe(
                greeks[cols]
                if cols
                else greeks,
                use_container_width=True,
                hide_index=True,
            )

        else:

            unavailable(
                "Greeks / IV",
                "No live Greeks received yet",
            )


        # ----------------------------------------------------
        # PCR
        # ----------------------------------------------------

        st.write("### 📊 Put-Call Ratio")

        pcr = st.session_state.options_pcr

        if pcr is not None and not pcr.empty:

            st.dataframe(
                pcr,
                use_container_width=True,
                hide_index=True,
            )

        else:

            unavailable(
                "PCR",
                "No live PCR received yet",
            )


        # ----------------------------------------------------
        # OI BUILDUP
        # ----------------------------------------------------

        st.write("### 🏗️ OI Buildup")

        oi_data = st.session_state.options_oi

        if oi_data:

            for name, data in oi_data.items():

                with st.expander(
                    str(name)
                ):

                    if data:

                        try:

                            st.dataframe(
                                pd.DataFrame(data),
                                use_container_width=True,
                                hide_index=True,
                            )

                        except Exception:

                            st.write(data)

                    else:

                        st.write(
                            "No data."
                        )

        else:

            unavailable(
                "OI Buildup",
                "No live OI buildup received yet",
            )

    else:

        unavailable(
            "Option Expiry",
            "No expiry list received",
        )


# ============================================================
# SYSTEM STATUS
# ============================================================

st.markdown(
    '<div class="section-title">🖥️ System Status</div>',
    unsafe_allow_html=True,
)

s1, s2 = st.columns(2)

with s1:

    show_card(
        "Paper Trading",
        "ON",
    )

with s2:

    show_card(
        "Angel One",
        "CONNECTED"
        if st.session_state.connected
        else "WAITING",
    )


s3, s4 = st.columns(2)

with s3:

    show_card(
        "Gemini",
        "READY"
        if get_gemini_key()
        else "WAITING",
    )

with s4:

    show_card(
        "Options Engine",
        "READY"
        if st.session_state.options_engine
        else "WAITING",
    )


# ============================================================
# SYSTEM MESSAGE
# ============================================================

if st.session_state.last_error:

    with st.expander(
        "⚠️ Latest System Message"
    ):

        st.code(
            st.session_state.last_error
        )


st.divider()

st.caption(
    "🔒 Real trading orders are disabled."
)

st.caption(
    "📡 Market values are displayed only when received from Angel One SmartAPI."
)

st.caption(
    "🚫 The application does not fabricate VIX, OI, PCR, IV, Greeks or news."
)

st.caption(
    "Last UI refresh: "
    + datetime.now().strftime("%H:%M:%S")
)


# ============================================================
# AUTO REFRESH
# ============================================================

if auto_refresh:

    time.sleep(
        int(refresh_seconds)
    )

    st.rerun()
