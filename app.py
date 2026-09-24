import os
import json

import streamlit as st
import pandas as pd
import numpy as np

from google import genai

from telemetry_engine import TelemetryEngine
from config import (
    AI_MODEL,
    PAPER_TRADING,
    MIN_AI_CONFIDENCE,
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Trading App",
    page_icon="📈",
    layout="wide",
)


# ============================================================
# SAMPLE MARKET DATA
# ============================================================

def create_sample_candles(rows=150):

    timestamps = pd.date_range(
        end=pd.Timestamp.now(),
        periods=rows,
        freq="5min",
    )

    base_price = 25000.0

    prices = (
        base_price
        + np.arange(rows) * 4.0
        + np.sin(np.arange(rows) / 5.0) * 35.0
    )

    close = prices

    open_price = close - 3.0
    high = close + 12.0
    low = close - 12.0

    volume = (
        100000
        + (np.arange(rows) % 10) * 5000
    )

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# ============================================================
# GEMINI API KEY
# ============================================================

def get_gemini_api_key():

    # First try environment variable
    key = os.getenv("GEMINI_API_KEY")

    if key:
        return key

    # Then try Streamlit Secrets
    try:
        key = st.secrets.get("GEMINI_API_KEY")

        if key:
            return key

    except Exception:
        pass

    return None


# ============================================================
# GEMINI ANALYSIS
# ============================================================

def get_ai_analysis(indicators, symbol, interval):

    api_key = get_gemini_api_key()

    if not api_key:

        return {
            "signal": "NO_TRADE",
            "confidence": 0.0,
            "reason": "Gemini API key is not available.",
        }

    try:

        client = genai.Client(
            api_key=api_key
        )

        prompt = f"""
You are an AI market-analysis assistant for a PAPER TRADING system.

IMPORTANT:
- This is NOT real trading.
- Do NOT place or recommend an actual broker order.
- Analyze only the supplied technical data.
- Do not invent news, price, VIX, OI, PCR or market data.
- If the data is insufficient, return NO_TRADE.
- Be conservative.

Instrument: {symbol}
Candle interval: {interval}

Technical indicators:

LTP: {indicators.get("ltp")}
RSI: {indicators.get("rsi")}
VWAP: {indicators.get("vwap")}
ADX: {indicators.get("adx")}
ATR: {indicators.get("atr")}
EMA Trend: {indicators.get("ema_trend")}
Supertrend: {indicators.get("supertrend")}
VWAP Position: {indicators.get("price_vs_vwap")}
Market Regime: {indicators.get("market_regime")}

Return ONLY valid JSON in this format:

{{
    "signal": "ENTER_LONG",
    "confidence": 80,
    "reason": "Short explanation"
}}

Allowed signal values:

ENTER_LONG
ENTER_SHORT
NO_TRADE

Confidence must be between 0 and 100.

If the setup is not sufficiently clear, return:

{{
    "signal": "NO_TRADE",
    "confidence": 0,
    "reason": "Insufficient confirmation"
}}
"""

        response = client.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
        )

        text = response.text.strip()

        # Remove markdown code fences if Gemini returns them
        if text.startswith("```"):
            text = text.replace("```json", "")
            text = text.replace("```", "")
            text = text.strip()

        result = json.loads(text)

        signal = str(
            result.get("signal", "NO_TRADE")
        ).upper()

        confidence = float(
            result.get("confidence", 0)
        )

        reason = str(
            result.get(
                "reason",
                "No explanation provided."
            )
        )

        if signal not in [
            "ENTER_LONG",
            "ENTER_SHORT",
            "NO_TRADE",
        ]:
            signal = "NO_TRADE"

        confidence = max(
            0.0,
            min(100.0, confidence)
        )

        return {
            "signal": signal,
            "confidence": confidence,
            "reason": reason,
        }

    except Exception as e:

        return {
            "signal": "NO_TRADE",
            "confidence": 0.0,
            "reason": f"AI analysis error: {str(e)}",
        }


# ============================================================
# APP HEADER
# ============================================================

st.title("📈 Personal AI Trading App")

st.caption(
    "AI-assisted market research and paper-trading dashboard"
)

st.warning(
    "PAPER TRADING ONLY — NO REAL ORDERS"
)


# ============================================================
# GEMINI STATUS
# ============================================================

gemini_key = get_gemini_api_key()

if gemini_key:

    st.success(
        "🟢 Gemini API Key: Connected"
    )

else:

    st.error(
        "🔴 Gemini API Key: Not Connected"
    )


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("⚙️ Trading Settings")

symbol = st.sidebar.selectbox(
    "Instrument",
    [
        "NIFTY26SEPFUT",
        "BANKNIFTY",
    ],
)

interval = st.sidebar.selectbox(
    "Candle Interval",
    [
        "FIVE_MINUTE",
        "ONE_MINUTE",
        "FIFTEEN_MINUTE",
    ],
)

analysis_mode = st.sidebar.selectbox(
    "Analysis Mode",
    [
        "Technical",
        "Technical + AI",
        "Strategy Research",
    ],
)


# ============================================================
# OFFLINE MARKET DATA
# ============================================================

df = create_sample_candles()

indicators = (
    TelemetryEngine.calculate_indicators(df)
)


# ============================================================
# MARKET SNAPSHOT
# ============================================================

st.subheader("Market Snapshot")

col1, col2, col3, col4 = st.columns(4)

with col1:

    st.metric(
        "LTP",
        f"₹{indicators['ltp']}",
    )

with col2:

    st.metric(
        "RSI",
        indicators["rsi"],
    )

with col3:

    st.metric(
        "VWAP",
        f"₹{indicators['vwap']}",
    )

with col4:

    st.metric(
        "ADX",
        indicators["adx"],
    )


# ============================================================
# MARKET ANALYSIS
# ============================================================

st.subheader("Market Analysis")

col1, col2, col3, col4 = st.columns(4)

with col1:

    st.write("**EMA Trend**")

    st.info(
        indicators["ema_trend"]
    )

with col2:

    st.write("**Supertrend**")

    st.info(
        indicators["supertrend"]
    )

with col3:

    st.write("**VWAP Position**")

    st.info(
        indicators["price_vs_vwap"]
    )

with col4:

    st.write("**Market Regime**")

    st.info(
        indicators["market_regime"]
    )


# ============================================================
# PRICE CHART
# ============================================================

st.subheader("📊 Price Chart")

chart_data = df.set_index(
    "timestamp"
)[["close"]]

st.line_chart(
    chart_data
)


# ============================================================
# TECHNICAL SIGNAL
# ============================================================

if (
    indicators["ema_trend"] == "BULLISH"
    and indicators["supertrend"] == "BULLISH"
    and indicators["price_vs_vwap"] == "ABOVE"
):

    technical_signal = "ENTER_LONG"

elif (
    indicators["ema_trend"] == "BEARISH"
    and indicators["supertrend"] == "BEARISH"
    and indicators["price_vs_vwap"] == "BELOW"
):

    technical_signal = "ENTER_SHORT"

else:

    technical_signal = "NO_TRADE"


# ============================================================
# AI ANALYSIS
# ============================================================

ai_result = {
    "signal": "NO_TRADE",
    "confidence": 0.0,
    "reason": "AI analysis not requested.",
}


if analysis_mode == "Technical + AI":

    with st.spinner("🤖 Gemini is analyzing the technical setup..."):

        ai_result = get_ai_analysis(
            indicators,
            symbol,
            interval,
        )


# ============================================================
# FINAL PAPER SIGNAL
# ============================================================

if analysis_mode == "Technical + AI":

    ai_signal = ai_result["signal"]
    ai_confidence = ai_result["confidence"]

    # AI must meet minimum confidence
    if ai_confidence < MIN_AI_CONFIDENCE:

        signal = "NO_TRADE"

    # AI and technical setup must agree
    elif (
        ai_signal == technical_signal
        and ai_signal in [
            "ENTER_LONG",
            "ENTER_SHORT",
        ]
    ):

        signal = ai_signal

    else:

        signal = "NO_TRADE"

else:

    signal = technical_signal


# ============================================================
# PAPER TRADING SIGNAL
# ============================================================

st.subheader("🤖 Paper Trading Signal")

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


# ============================================================
# AI ANALYSIS DISPLAY
# ============================================================

if analysis_mode == "Technical + AI":

    st.subheader("🧠 Gemini AI Analysis")

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "AI Signal",
            ai_result["signal"],
        )

    with col2:

        st.metric(
            "AI Confidence",
            f"{ai_result['confidence']:.1f}%",
        )

    st.info(
        ai_result["reason"]
    )


# ============================================================
# TRADE PLAN
# ============================================================

st.subheader("🎯 Paper Trade Plan")

ltp = indicators["ltp"]
atr = indicators["atr"]


if signal == "ENTER_LONG":

    stop_loss = ltp - (1.0 * atr)
    target_1 = ltp + (1.5 * atr)
    target_2 = ltp + (2.5 * atr)

elif signal == "ENTER_SHORT":

    stop_loss = ltp + (1.0 * atr)
    target_1 = ltp - (1.5 * atr)
    target_2 = ltp - (2.5 * atr)

else:

    stop_loss = 0
    target_1 = 0
    target_2 = 0


col1, col2, col3 = st.columns(3)

with col1:

    st.metric(
        "Entry",
        f"₹{ltp}",
    )

with col2:

    st.metric(
        "Stop Loss",
        f"₹{stop_loss:.2f}",
    )

with col3:

    st.metric(
        "Target 1",
        f"₹{target_1:.2f}",
    )


st.metric(
    "Target 2",
    f"₹{target_2:.2f}",
)


# ============================================================
# RECENT CANDLES
# ============================================================

with st.expander(
    "🕯️ Recent Candles"
):

    st.dataframe(
        df.tail(10),
        use_container_width=True,
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

st.subheader("🛡️ System Status")

ai_status = (
    "CONNECTED"
    if gemini_key
    else "NOT CONNECTED"
)

status_data = {
    "Component": [
        "Market Data",
        "Technical Engine",
        "Risk Manager",
        "Paper Broker",
        "AI Layer",
        "Real Orders",
    ],
    "Status": [
        "OFFLINE TEST DATA",
        "READY",
        "READY",
        "READY",
        ai_status,
        "DISABLED",
    ],
}

st.table(
    pd.DataFrame(status_data)
)


# ============================================================
# SAFETY MESSAGE
# ============================================================

st.caption(
    "This dashboard currently uses simulated test candles. "
    "Gemini provides analysis only. "
    "No real market order is sent."
)
