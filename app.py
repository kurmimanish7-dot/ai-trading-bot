import os
import json
import time

import streamlit as st
import pandas as pd

from SmartApi import SmartConnect
from google import genai

from telemetry_engine import TelemetryEngine
from advanced_analysis import build_advanced_analysis

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


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="AI Trading Bot",
    page_icon="📈",
    layout="wide",
)

st.title("📈 AI Trading Bot")
st.caption("Live Market Analysis • Paper Trading Only")


# ============================================================
# SAFETY LOCK
# ============================================================

if PAPER_TRADING is not True:
    st.error(
        "🚨 SAFETY LOCK: PAPER_TRADING must remain True."
    )
    st.stop()

st.success(
    "🛡️ PAPER TRADING MODE — Real orders are disabled."
)


# ============================================================
# SECRETS
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
    "smart_api": None,
    "telemetry": None,
    "last_df": pd.DataFrame(),
    "last_error": "",
    "last_fetch_time": 0,
    "last_ai_time": 0,
    "ai_result": {
        "signal": "NO_TRADE",
        "confidence": 0,
        "reason": "Waiting for AI analysis.",
    },
    "connected": False,
}

for key, value in defaults.items():

    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# ANGEL ONE LOGIN
# ============================================================

def create_telemetry():

    credentials = get_credentials()

    required = [
        credentials["api_key"],
        credentials["client_code"],
        credentials["pin"],
        credentials["totp_secret"],
    ]

    if not all(required):
        return None, "Angel One credentials are not configured."

    try:

        engine = TelemetryEngine(
            api_key=credentials["api_key"],
            client_code=credentials["client_code"],
            pin=credentials["pin"],
            totp_secret=credentials["totp_secret"],
        )

        return engine, ""

    except Exception as e:

        return None, str(e)


def ensure_connection():

    if st.session_state.telemetry is not None:
        return True

    engine, error = create_telemetry()

    if engine is None:

        st.session_state.connected = False
        st.session_state.last_error = error

        return False

    st.session_state.telemetry = engine
    st.session_state.connected = True
    st.session_state.last_error = ""

    return True


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
            raise ValueError(
                "No candle data received."
            )

        return df

    except Exception as e:

        st.session_state.last_error = str(e)

        return None


# ============================================================
# LIVE LTP
# ============================================================

def fetch_ltp():

    if not ensure_connection():
        return None

    try:

        result = (
            st.session_state.telemetry.get_live_ltp(
                exchange=EXCHANGE,
                tradingsymbol=SYMBOL,
                symboltoken=str(TOKEN),
            )
        )

        if not result:
            return None

        if not result.get("status"):
            return None

        return float(
            result["ltp"]
        )

    except Exception:

        return None


# ============================================================
# APPLY LIVE PRICE
# ============================================================

def apply_live_price(df, ltp):

    if df is None or df.empty:
        return df

    if ltp is None:
        return df

    result = df.copy()

    try:

        index = result.index[-1]

        result.loc[index, "close"] = float(ltp)

        result.loc[index, "high"] = max(
            float(result.loc[index, "high"]),
            float(ltp),
        )

        result.loc[index, "low"] = min(
            float(result.loc[index, "low"]),
            float(ltp),
        )

    except Exception:
        pass

    return result


# ============================================================
# AI ANALYSIS
# ============================================================

def short_reason(reason):

    if not reason:
        return "No clear setup."

    reason = str(reason).replace(
        "\n",
        " ",
    ).strip()

    if len(reason) > 160:
        reason = reason[:157] + "..."

    return reason


def call_gemini(
    indicators,
    advanced,
    ltp,
):

    api_key = get_gemini_key()

    if not api_key:

        return {
            "signal": "NO_TRADE",
            "confidence": 0,
            "reason": "Gemini API key unavailable.",
        }

    prompt = f"""
You are an AI trading-analysis assistant.

IMPORTANT:
PAPER TRADING ONLY.
Never place real orders.

Use ONLY the supplied market data.
Do not invent news, VIX, OI, PCR, IV or Greeks.

Instrument: {SYMBOL}

LTP: {ltp}

RSI: {indicators.get("rsi")}
VWAP: {indicators.get("vwap")}
ADX: {indicators.get("adx")}
ATR: {indicators.get("atr")}
EMA Trend: {indicators.get("ema_trend")}
Supertrend: {indicators.get("supertrend")}
VWAP Position: {indicators.get("price_vs_vwap")}
Market Regime: {indicators.get("market_regime")}

Advanced analysis:

Candlestick:
{advanced.get("candlestick_patterns")}

MACD:
{advanced.get("macd")}

EMA 200:
{advanced.get("ema_200")}

Support/Resistance:
{advanced.get("support_resistance")}

Volume:
{advanced.get("volume")}

Market Structure:
{advanced.get("market_structure")}

Return ONLY JSON.

Allowed signal:

ENTER_LONG
ENTER_SHORT
NO_TRADE

Confidence: 0 to 100.

Reason: one short sentence.

Example:

{{
    "signal": "ENTER_LONG",
    "confidence": 82,
    "reason": "Price is above VWAP with bullish momentum."
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

        text = response.text.strip()

        text = text.replace(
            "```json",
            "",
        )

        text = text.replace(
            "```",
            "",
        )

        result = json.loads(
            text.strip()
        )

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

        reason = short_reason(
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
            "reason": reason,
        }

    except Exception as e:

        return {
            "signal": "NO_TRADE",
            "confidence": 0,
            "reason": short_reason(
                "Gemini error: " + str(e)
            ),
        }


# ============================================================
# PAPER TRADE LEVELS
# ============================================================

def calculate_levels(
    signal,
    ltp,
    atr,
):

    try:
        price = float(ltp)
    except Exception:
        price = 0

    try:
        atr_value = float(atr)
    except Exception:
        atr_value = 0

    if atr_value <= 0:
        atr_value = max(
            price * 0.002,
            1,
        )

    if signal == "ENTER_LONG":

        return {
            "entry": price,
            "sl": price - atr_value * 1.5,
            "target1": price + atr_value * 2,
            "target2": price + atr_value * 3,
        }

    if signal == "ENTER_SHORT":

        return {
            "entry": price,
            "sl": price + atr_value * 1.5,
            "target1": price - atr_value * 2,
            "target2": price - atr_value * 3,
        }

    return {
        "entry": None,
        "sl": None,
        "target1": None,
        "target2": None,
    }


# ============================================================
# INITIAL DATA LOAD
# ============================================================

if st.session_state.last_df.empty:

    with st.spinner(
        "Loading market candles..."
    ):

        df = fetch_market_data()

        if df is not None:
            st.session_state.last_df = df
            st.session_state.last_fetch_time = time.time()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("⚙️ Bot Settings")

st.sidebar.write(
    f"**Symbol:** {SYMBOL}"
)

st.sidebar.write(
    f"**Exchange:** {EXCHANGE}"
)

st.sidebar.write(
    f"**Token:** {TOKEN}"
)

st.sidebar.write(
    f"**Interval:** {CANDLE_INTERVAL}"
)

st.sidebar.write(
    "**Trading:** PAPER ONLY"
)

refresh = st.sidebar.button(
    "🔄 Refresh Market Data"
)

if refresh:

    df = fetch_market_data()

    if df is not None:

        st.session_state.last_df = df

        st.session_state.last_fetch_time = (
            time.time()
        )

    st.rerun()


# ============================================================
# CONNECTION STATUS
# ============================================================

if st.session_state.connected:

    st.success(
        "🟢 Angel One connection ready"
    )

else:

    st.warning(
        "🟡 Angel One credentials/session not ready"
    )


# ============================================================
# MARKET DATA CHECK
# ============================================================

df = st.session_state.last_df

if df.empty:

    st.error(
        "Market data unavailable."
    )

    if st.session_state.last_error:

        st.code(
            st.session_state.last_error
        )

    st.info(
        "API credentials and SmartAPI configuration "
        "will be checked next."
    )

    st.stop()


# ============================================================
# LIVE LTP
# ============================================================

live_ltp = fetch_ltp()

if live_ltp is None:

    live_ltp = float(
        df["close"].iloc[-1]
    )

live_df = apply_live_price(
    df,
    live_ltp,
)


# ============================================================
# INDICATORS
# ============================================================

try:

    indicators = (
        TelemetryEngine.calculate_indicators(
            live_df
        )
    )

except Exception as e:

    indicators = {}

    st.warning(
        "Indicator calculation issue: "
        + str(e)
    )


indicators["ltp"] = live_ltp


# ============================================================
# ADVANCED ANALYSIS
# ============================================================

try:

    advanced = build_advanced_analysis(
        live_df
    )

except Exception as e:

    advanced = {
        "status": "ERROR",
        "error": str(e),
    }


# ============================================================
# AI UPDATE
# ============================================================

now = time.time()

AI_REFRESH_SECONDS = 60

if (
    now
    - st.session_state.last_ai_time
    >= AI_REFRESH_SECONDS
):

    st.session_state.ai_result = (
        call_gemini(
            indicators,
            advanced,
            live_ltp,
        )
    )

    st.session_state.last_ai_time = now


ai_result = st.session_state.ai_result

signal = ai_result.get(
    "signal",
    "NO_TRADE",
)

confidence = float(
    ai_result.get(
        "confidence",
        0,
    )
)

reason = short_reason(
    ai_result.get(
        "reason",
        "No clear setup.",
    )
)


# ============================================================
# TOP METRICS
# ============================================================

st.subheader("📊 Live Market")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric(
        "LTP",
        f"{live_ltp:,.2f}",
    )

with c2:
    st.metric(
        "RSI",
        f"{float(indicators.get('rsi', 0)):.2f}",
    )

with c3:
    st.metric(
        "ADX",
        f"{float(indicators.get('adx', 0)):.2f}",
    )

with c4:
    st.metric(
        "ATR",
        f"{float(indicators.get('atr', 0)):.2f}",
    )


# ============================================================
# SIGNAL
# ============================================================

st.subheader("🤖 AI Signal")

if signal == "ENTER_LONG":

    st.success(
        "🟢 ENTER LONG — PAPER ONLY"
    )

elif signal == "ENTER_SHORT":

    st.error(
        "🔴 ENTER SHORT — PAPER ONLY"
    )

else:

    st.warning(
        "🟡 NO TRADE"
    )


c1, c2 = st.columns(2)

with c1:

    st.metric(
        "AI Confidence",
        f"{confidence:.1f}%",
    )

with c2:

    st.write(
        "**AI Reason**"
    )

    st.write(reason)


# ============================================================
# PAPER LEVELS
# ============================================================

atr = indicators.get(
    "atr",
    0,
)

levels = calculate_levels(
    signal,
    live_ltp,
    atr,
)

st.subheader(
    "🎯 Paper Trade Levels"
)

c1, c2, c3, c4 = st.columns(4)

with c1:

    value = levels["entry"]

    st.metric(
        "Entry",
        (
            f"{value:,.2f}"
            if value is not None
            else "—"
        ),
    )

with c2:

    value = levels["sl"]

    st.metric(
        "Stop Loss",
        (
            f"{value:,.2f}"
            if value is not None
            else "—"
        ),
    )

with c3:

    value = levels["target1"]

    st.metric(
        "Target 1",
        (
            f"{value:,.2f}"
            if value is not None
            else "—"
        ),
    )

with c4:

    value = levels["target2"]

    st.metric(
        "Target 2",
        (
            f"{value:,.2f}"
            if value is not None
            else "—"
        ),
    )


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

st.subheader(
    "📈 Technical Analysis"
)

technical_data = {
    "LTP": indicators.get("ltp"),
    "RSI": indicators.get("rsi"),
    "VWAP": indicators.get("vwap"),
    "ADX": indicators.get("adx"),
    "ATR": indicators.get("atr"),
    "EMA Trend": indicators.get("ema_trend"),
    "Supertrend": indicators.get("supertrend"),
    "VWAP Position": indicators.get(
        "price_vs_vwap"
    ),
    "Market Regime": indicators.get(
        "market_regime"
    ),
}

technical_df = pd.DataFrame(
    [technical_data]
)

st.dataframe(
    technical_df,
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# ADVANCED ANALYSIS
# ============================================================

st.subheader(
    "🧠 Advanced Analysis"
)

if advanced.get("status") == "OK":

    patterns = advanced.get(
        "candlestick_patterns",
        [],
    )

    st.write(
        "**Candlestick:**",
        ", ".join(
            map(
                str,
                patterns,
            )
        ),
    )

    macd = advanced.get(
        "macd",
        {},
    )

    st.write(
        "**MACD Bias:**",
        macd.get(
            "bias",
            "UNKNOWN",
        ),
    )

    ema = advanced.get(
        "ema_200",
        {},
    )

    st.write(
        "**EMA 200 Position:**",
        ema.get(
            "position",
            "UNKNOWN",
        ),
    )

    sr = advanced.get(
        "support_resistance",
        {},
    )

    c1, c2 = st.columns(2)

    with c1:

        st.metric(
            "Support",
            (
                f"{float(sr.get('support')):,.2f}"
                if sr.get("support") is not None
                else "—"
            ),
        )

    with c2:

        st.metric(
            "Resistance",
            (
                f"{float(sr.get('resistance')):,.2f}"
                if sr.get("resistance") is not None
                else "—"
            ),
        )

    volume = advanced.get(
        "volume",
        {},
    )

    st.write(
        "**Volume Signal:**",
        volume.get(
            "volume_signal",
            "UNKNOWN",
        ),
    )

    structure = advanced.get(
        "market_structure",
        {},
    )

    st.write(
        "**Market Structure:**",
        structure.get(
            "structure",
            "UNKNOWN",
        ),
    )

    st.write(
        "**Momentum:**",
        structure.get(
            "momentum",
            "UNKNOWN",
        ),
    )

else:

    st.info(
        "Advanced analysis is waiting for sufficient data."
    )


# ============================================================
# RECENT CANDLES
# ============================================================

st.subheader(
    "🕯️ Recent Candles"
)

st.dataframe(
    live_df.tail(20),
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# STATUS
# ============================================================

st.subheader(
    "🛡️ System Status"
)

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.write("**Trading Mode**")
    st.write("PAPER")

with c2:
    st.write("**Real Orders**")
    st.write("DISABLED")

with c3:
    st.write("**AI Analysis**")
    st.write("ACTIVE")

with c4:
    st.write("**Market Data**")
    st.write(
        "LIVE"
        if live_ltp is not None
        else "UNAVAILABLE"
    )


# ============================================================
# AUTO REFRESH
# ============================================================

st.caption(
    "🔄 Refresh the page every few seconds for updated market data."
)

st.caption(
    "🔒 Safety Lock: This application does not place real orders."
)
