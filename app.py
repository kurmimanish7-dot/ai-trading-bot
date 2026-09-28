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
# CSS
# ============================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
    }

    .metric-card {
        padding: 14px;
        border: 1px solid rgba(128,128,128,.25);
        border-radius: 12px;
        min-height: 105px;
    }

    .status-card {
        padding: 12px 15px;
        border-radius: 10px;
        border: 1px solid rgba(128,128,128,.25);
        margin-bottom: 8px;
    }

    .big-signal {
        font-size: 28px;
        font-weight: 700;
    }

    .small-muted {
        opacity: .7;
        font-size: 13px;
    }

    .section-title {
        font-size: 22px;
        font-weight: 700;
        margin-top: 18px;
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
        "🚨 SAFETY LOCK ACTIVE: PAPER_TRADING must remain True."
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
        "api_key": get_secret("SMARTAPI_API_KEY"),
        "client_code": get_secret("SMARTAPI_CLIENT_CODE"),
        "pin": get_secret("SMARTAPI_PIN"),
        "totp_secret": get_secret("SMARTAPI_TOTP_SECRET"),
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

    "last_options_time": 0,
    "selected_underlying": "NIFTY",
    "selected_expiry": None,
}


for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# CONNECTION STATUS
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

        return True

    except Exception as e:
        st.session_state.connected = False
        st.session_state.last_error = str(e)
        return False


def ensure_options_engine():

    if st.session_state.options_engine is not None:
        return st.session_state.options_engine

    if not ensure_connection():
        return None

    try:
        engine = OptionsEngine(
            jwt_token=st.session_state.telemetry.smart_api.access_token,
            api_key=st.session_state.api_key,
            client_code=st.session_state.client_code,
        )

        st.session_state.options_engine = engine

        return engine

    except Exception:
        try:
            smart_api = st.session_state.telemetry.smart_api

            jwt_token = getattr(
                smart_api,
                "access_token",
                None,
            )

            if jwt_token:
                engine = OptionsEngine(
                    jwt_token=jwt_token,
                    api_key=st.session_state.api_key,
                    client_code=st.session_state.client_code,
                )

                st.session_state.options_engine = engine
                return engine

        except Exception as e:
            st.session_state.last_error = str(e)

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
            return float(result["ltp"])

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
        return TelemetryEngine.calculate_indicators(df)
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

Use ONLY the supplied data.
Never invent news, VIX, OI, PCR, IV or Greeks.

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

Confidence: 0-100.

JSON format:
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

        raw = raw.replace(
            "```json",
            "",
        ).replace(
            "```",
            "",
        ).strip()

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

        if signal not in {
            "ENTER_LONG",
            "ENTER_SHORT",
            "NO_TRADE",
        }:
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
            "reason": reason[:250],
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
# OPTIONS
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

def unavailable(label, detail="Waiting for connection"):

    st.markdown(
        f"""
        <div class="status-card">
        <b>{label}</b><br>
        <span class="small-muted">⏳ {detail}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Control Panel")

    st.write(
        "### Connection"
    )

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

    st.write(
        "### Safety"
    )

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
# CONNECTION BANNER
# ============================================================

if not st.session_state.connected:

    st.warning(
        "📡 Live connection is not active. "
        "Dashboard is ready — configure Angel One credentials "
        "to populate live market data."
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

m1, m2, m3, m4, m5 = st.columns(5)

with m1:

    if live_ltp is not None:
        st.metric(
            "NIFTY / Instrument",
            f"{live_ltp:,.2f}",
        )
    else:
        st.metric(
            "NIFTY / Instrument",
            "WAITING",
        )

with m2:

    if indicators:
        st.metric(
            "RSI",
            indicators.get("rsi", "—"),
        )
    else:
        st.metric(
            "RSI",
            "—",
        )

with m3:

    if indicators:
        st.metric(
            "VWAP",
            indicators.get("vwap", "—"),
        )
    else:
        st.metric(
            "VWAP",
            "—",
        )

with m4:

    if indicators:
        st.metric(
            "ADX",
            indicators.get("adx", "—"),
        )
    else:
        st.metric(
            "ADX",
            "—",
        )

with m5:

    if indicators:
        st.metric(
            "Market Regime",
            indicators.get(
                "market_regime",
                "—",
            ),
        )
    else:
        st.metric(
            "Market Regime",
            "WAITING",
        )


# ============================================================
# MARKET DIRECTION
# ============================================================

st.markdown(
    '<div class="section-title">🧭 Market Direction</div>',
    unsafe_allow_html=True,
)

d1, d2, d3, d4 = st.columns(4)

with d1:

    st.metric(
        "EMA Trend",
        indicators.get(
            "ema_trend",
            "WAITING",
        ),
    )

with d2:

    st.metric(
        "Supertrend",
        indicators.get(
            "supertrend",
            "WAITING",
        ),
    )

with d3:

    st.metric(
        "Price vs VWAP",
        indicators.get(
            "price_vs_vwap",
            "WAITING",
        ),
    )

with d4:

    structure = (
        advanced
        .get("market_structure", {})
        .get("trend", "WAITING")
    )

    st.metric(
        "Structure",
        structure,
    )


# ============================================================
# AI SIGNAL
# ============================================================

st.markdown(
    '<div class="section-title">🤖 AI Trading Signal</div>',
    unsafe_allow_html=True,
)

ai_col1, ai_col2, ai_col3 = st.columns(3)

ai = st.session_state.ai_result

with ai_col1:

    signal = ai.get(
        "signal",
        "WAITING",
    )

    st.markdown(
        f'<div class="metric-card">'
        f'<div class="small-muted">SIGNAL</div>'
        f'<div class="big-signal">{signal}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

with ai_col2:

    confidence = float(
        ai.get(
            "confidence",
            0,
        )
    )

    st.metric(
        "AI Confidence",
        f"{confidence:.0f}%",
    )

with ai_col3:

    st.write("**AI Reason**")

    st.write(
        ai.get(
            "reason",
            "Waiting for analysis.",
        )
    )


# ============================================================
# AI UPDATE
# ============================================================

if (
    live_ltp is not None
    and indicators
):

    now = time.time()

    # Gemini call maximum once per 60 seconds.
    if (
        now
        - st.session_state.last_ai_time
        >= 60
    ):

        st.session_state.ai_result = (
            call_gemini(
                indicators,
                advanced,
                live_ltp,
            )
        )

        st.session_state.last_ai_time = now


# ============================================================
# TRADE PLAN
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

t1, t2, t3, t4 = st.columns(4)

with t1:
    st.metric(
        "Entry",
        f"{levels['entry']:.2f}"
        if levels["entry"] is not None
        else "WAITING",
    )

with t2:
    st.metric(
        "Stop Loss",
        f"{levels['sl']:.2f}"
        if levels["sl"] is not None
        else "WAITING",
    )

with t3:
    st.metric(
        "Target 1",
        f"{levels['target1']:.2f}"
        if levels["target1"] is not None
        else "WAITING",
    )

with t4:
    st.metric(
        "Target 2",
        f"{levels['target2']:.2f}"
        if levels["target2"] is not None
        else "WAITING",
    )


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

st.markdown(
    '<div class="section-title">📐 Technical Analysis</div>',
    unsafe_allow_html=True,
)

tech1, tech2, tech3, tech4, tech5 = st.columns(5)

with tech1:
    st.metric(
        "EMA 9",
        indicators.get("ema_9", "—"),
    )

with tech2:
    st.metric(
        "EMA 21",
        indicators.get("ema_21", "—"),
    )

with tech3:
    st.metric(
        "EMA 50",
        indicators.get("ema_50", "—"),
    )

with tech4:
    st.metric(
        "ATR",
        indicators.get("atr", "—"),
    )

with tech5:

    ema200 = (
        advanced
        .get("ema_200", {})
        .get("value", "—")
    )

    st.metric(
        "EMA 200",
        ema200,
    )


# ============================================================
# ADVANCED ANALYSIS
# ============================================================

st.markdown(
    '<div class="section-title">🔬 Advanced Price Action</div>',
    unsafe_allow_html=True,
)

a1, a2 = st.columns(2)

with a1:

    patterns = advanced.get(
        "candlestick_patterns",
        [],
    )

    st.write("**Candlestick Pattern**")

    if patterns:
        st.write(
            " • ".join(
                str(x)
                for x in patterns
            )
        )
    else:
        st.write("WAITING")

    macd = advanced.get(
        "macd",
        {},
    )

    st.write(
        "**MACD Bias:** "
        + str(
            macd.get(
                "bias",
                "WAITING",
            )
        )
    )

with a2:

    sr = advanced.get(
        "support_resistance",
        {},
    )

    st.write(
        "**Support:** "
        + str(
            sr.get(
                "support",
                "WAITING",
            )
        )
    )

    st.write(
        "**Resistance:** "
        + str(
            sr.get(
                "resistance",
                "WAITING",
            )
        )
    )

    volume = advanced.get(
        "volume",
        {},
    )

    st.write(
        "**Volume:** "
        + str(
            volume.get(
                "volume_signal",
                "WAITING",
            )
        )
    )


# ============================================================
# LIVE CANDLE CHART
# ============================================================

st.markdown(
    '<div class="section-title">🕯️ Live Candles</div>',
    unsafe_allow_html=True,
)

if live_df is not None and not live_df.empty:

    chart_df = live_df.copy()

    chart_df = chart_df.tail(100)

    if "timestamp" in chart_df.columns:

        chart_df = chart_df.set_index(
            "timestamp"
        )

    if "close" in chart_df.columns:

        st.line_chart(
            chart_df["close"]
        )

    with st.expander(
        "View recent candles"
    ):

        st.dataframe(
            live_df.tail(20),
            use_container_width=True,
        )

else:

    unavailable(
        "Live Candle Data",
        "Angel One connection required",
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

    unavailable(
        "OI / PCR / Greeks",
        "Waiting for Angel One connection",
    )

else:

    o1, o2, o3 = st.columns(3)

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

    with o3:

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

        st.session_state.selected_expiry = (
            expiry
        )

        spot = live_ltp

        if spot is None:
            spot = indicators.get(
                "ltp"
            )

        if refresh_options:

            if spot is not None:

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
                st.session_state.last_options_time = time.time()

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

            if "option_type" in chain.columns:

                ce = chain[
                    chain["option_type"]
                    .astype(str)
                    .str.upper()
                    == "CE"
                ]

                pe = chain[
                    chain["option_type"]
                    .astype(str)
                    .str.upper()
                    == "PE"
                ]

                c1, c2, c3, c4 = st.columns(4)

                with c1:
                    st.metric(
                        "CE Contracts",
                        len(ce),
                    )

                with c2:
                    st.metric(
                        "PE Contracts",
                        len(pe),
                    )

                with c3:

                    ce_oi = (
                        ce["opnInterest"].sum()
                        if "opnInterest" in ce.columns
                        else 0
                    )

                    st.metric(
                        "CE OI",
                        f"{ce_oi:,.0f}",
                    )

                with c4:

                    pe_oi = (
                        pe["opnInterest"].sum()
                        if "opnInterest" in pe.columns
                        else 0
                    )

                    st.metric(
                        "PE OI",
                        f"{pe_oi:,.0f}",
                    )

        else:

            unavailable(
                "Option Chain",
                "Click Load Options to request live data",
            )

        # ----------------------------------------------------
        # GREEKS
        # ----------------------------------------------------

        st.write(
            "### 🧮 Greeks / IV"
        )

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
                c for c in preferred
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

        st.write(
            "### 📊 Put-Call Ratio"
        )

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

        st.write(
            "### 🏗️ OI Buildup"
        )

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
            "No expiry list received from Angel One",
        )


# ============================================================
# SYSTEM STATUS
# ============================================================

st.markdown(
    '<div class="section-title">🖥️ System Status</div>',
    unsafe_allow_html=True,
)

s1, s2, s3, s4 = st.columns(4)

with s1:

    st.metric(
        "Paper Trading",
        "ON",
    )

with s2:

    st.metric(
        "Angel One",
        "CONNECTED"
        if st.session_state.connected
        else "WAITING",
    )

with s3:

    st.metric(
        "Gemini",
        "READY"
        if get_gemini_key()
        else "WAITING",
    )

with s4:

    st.metric(
        "Options Engine",
        "READY"
        if st.session_state.options_engine
        else "WAITING",
    )


# ============================================================
# ERROR / INFO
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
    "📡 Market values are shown only when received from Angel One SmartAPI."
)

st.caption(
    "🚫 The application does not fabricate VIX, OI, PCR, IV, Greeks or news."
)

st.caption(
    f"Last UI refresh: {datetime.now().strftime('%H:%M:%S')}"
)


# ============================================================
# AUTO REFRESH
# ============================================================

if auto_refresh:

    time.sleep(
        int(refresh_seconds)
    )

    st.rerun()
