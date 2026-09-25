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
# CREDENTIAL HELPERS
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


def get_gemini_api_key():
    return get_secret("GEMINI_API_KEY")


def get_angel_credentials():
    return {
        "api_key": get_secret("ANGEL_API_KEY"),
        "client_code": get_secret("ANGEL_CLIENT_CODE"),
        "pin": get_secret("ANGEL_PIN"),
        "totp_secret": get_secret("ANGEL_TOTP_SECRET"),
    }


# ============================================================
# INSTRUMENT CONFIGURATION
# ============================================================

INSTRUMENTS = {
    "NIFTY 50": {
        "exchange": "NSE",
        "token_secret": "NIFTY_TOKEN",
        "default_token": "99926000",
        "description": "NIFTY 50 Index",
    },

    "BANK NIFTY": {
        "exchange": "NSE",
        "token_secret": "BANKNIFTY_TOKEN",
        "default_token": None,
        "description": "NIFTY Bank Index",
    },

    "SENSEX": {
        "exchange": "BSE",
        "token_secret": "SENSEX_TOKEN",
        "default_token": None,
        "description": "BSE SENSEX Index",
    },
}


def get_instrument_token(symbol):
    instrument = INSTRUMENTS[symbol]

    secret_token = get_secret(
        instrument["token_secret"]
    )

    if secret_token:
        return str(secret_token)

    return instrument["default_token"]


# ============================================================
# SAMPLE MARKET DATA - FALLBACK ONLY
# ============================================================

def create_sample_candles(
    rows=150,
    base_price=25000.0,
):

    timestamps = pd.date_range(
        end=pd.Timestamp.now(),
        periods=rows,
        freq="5min",
    )

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
# ANGEL ONE MARKET DATA
# ============================================================

def fetch_real_market_data(
    symbol,
    interval,
):

    credentials = get_angel_credentials()

    missing = [
        key
        for key, value in credentials.items()
        if not value
    ]

    if missing:
        return None, (
            "Missing Angel One credentials: "
            + ", ".join(missing)
        )

    instrument_token = get_instrument_token(
        symbol
    )

    if not instrument_token:

        return None, (
            f"{symbol} token is not configured yet. "
            f"Add {INSTRUMENTS[symbol]['token_secret']} "
            f"to Streamlit Secrets when available."
        )

    interval_map = {
        "ONE_MINUTE": "ONE_MINUTE",
        "FIVE_MINUTE": "FIVE_MINUTE",
        "FIFTEEN_MINUTE": "FIFTEEN_MINUTE",
    }

    api_interval = interval_map.get(
        interval,
        "FIVE_MINUTE",
    )

    exchange = INSTRUMENTS[symbol]["exchange"]

    try:

        engine = TelemetryEngine(
            api_key=credentials["api_key"],
            client_code=credentials["client_code"],
            pin=credentials["pin"],
            totp_secret=credentials["totp_secret"],
        )

        df = engine.fetch_ohlcv(
            exchange=exchange,
            token=instrument_token,
            interval=api_interval,
            days=5,
        )

        if df is None or df.empty:
            return None, (
                f"Angel One returned no candle data "
                f"for {symbol}."
            )

        required_columns = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        for column in required_columns:

            if column not in df.columns:

                return None, (
                    f"Missing candle column: {column}"
                )

        df = df.copy()

        df["timestamp"] = pd.to_datetime(
            df["timestamp"]
        )

        for column in [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        df = df.dropna(
            subset=[
                "open",
                "high",
                "low",
                "close",
            ]
        )

        if df.empty:
            return None, (
                "No valid candle data after cleaning."
            )

        return df, None

    except Exception as e:

        return None, (
            "Angel One connection error: "
            + str(e)
        )


# ============================================================
# GEMINI ANALYSIS
# ============================================================

def get_ai_analysis(
    indicators,
    symbol,
    interval,
):

    api_key = get_gemini_api_key()

    if not api_key:

        return {
            "signal": "NO_TRADE",
            "confidence": 0.0,
            "reason": (
                "Gemini API key is not available."
            ),
        }

    try:

        client = genai.Client(
            api_key=api_key
        )

        prompt = f"""
You are an AI market-analysis assistant
for a PAPER TRADING system.

IMPORTANT:

- This is NOT real trading.
- Do NOT place any actual broker order.
- Analyze only the supplied technical data.
- Do not invent news, price, VIX, OI, PCR
  or any other market data.
- If data is insufficient, return NO_TRADE.
- Be conservative.

Instrument:
{symbol}

Candle interval:
{interval}

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

Return ONLY valid JSON:

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

If the setup is unclear:

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

        if text.startswith("```"):

            text = text.replace(
                "```json",
                "",
            )

            text = text.replace(
                "```",
                "",
            )

            text = text.strip()

        result = json.loads(text)

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
                "No explanation provided.",
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
            min(100.0, confidence),
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
            "reason": (
                f"AI analysis error: {str(e)}"
            ),
        }


# ============================================================
# APP HEADER
# ============================================================

st.title("📈 Personal AI Trading App")

st.caption(
    "AI-assisted market research and "
    "paper-trading dashboard"
)

st.warning(
    "PAPER TRADING ONLY — NO REAL ORDERS"
)


# ============================================================
# API STATUS
# ============================================================

gemini_key = get_gemini_api_key()

angel_credentials = get_angel_credentials()

angel_connected = all(
    angel_credentials.values()
)


if gemini_key:

    st.success(
        "🟢 Gemini API Key: Connected"
    )

else:

    st.error(
        "🔴 Gemini API Key: Not Connected"
    )


if angel_connected:

    st.success(
        "🟢 Angel One Credentials: Connected"
    )

else:

    st.warning(
        "🟡 Angel One Credentials: Incomplete"
    )


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "⚙️ Trading Settings"
)

symbol = st.sidebar.selectbox(
    "Instrument",
    [
        "NIFTY 50",
        "BANK NIFTY",
        "SENSEX",
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
# SELECTED INSTRUMENT INFO
# ============================================================

selected_instrument = INSTRUMENTS[symbol]

st.sidebar.markdown("---")

st.sidebar.write(
    f"**Exchange:** "
    f"{selected_instrument['exchange']}"
)

st.sidebar.write(
    f"**Instrument:** "
    f"{selected_instrument['description']}"
)

selected_token = get_instrument_token(
    symbol
)

if selected_token:

    st.sidebar.success(
        "Instrument Token: Available"
    )

else:

    st.sidebar.warning(
        "Instrument Token: Not configured"
    )


# ============================================================
# MARKET DATA
# ============================================================

df = None

data_error = None

data_source = (
    "ANGEL ONE LIVE/HISTORICAL DATA"
)


if angel_connected:

    with st.spinner(
        f"📡 Fetching {symbol} data "
        f"from Angel One..."
    ):

        df, data_error = (
            fetch_real_market_data(
                symbol,
                interval,
            )
        )


# ============================================================
# FALLBACK DATA
# ============================================================

if df is None:

    data_source = (
        "OFFLINE TEST DATA"
    )

    base_prices = {
        "NIFTY 50": 25000.0,
        "BANK NIFTY": 55000.0,
        "SENSEX": 82000.0,
    }

    df = create_sample_candles(
        base_price=base_prices[symbol]
    )

    if data_error:

        st.warning(
            f"⚠️ {symbol} live data could "
            f"not be loaded."
        )

        st.caption(
            f"Reason: {data_error}"
        )

        st.info(
            "Dashboard is using simulated "
            "test candles. No real order "
            "is being sent."
        )


# ============================================================
# DATA SOURCE DISPLAY
# ============================================================

if data_source == "OFFLINE TEST DATA":

    st.warning(
        f"📊 Data Source: OFFLINE TEST DATA — "
        f"{symbol}"
    )

else:

    st.success(
        f"📡 Data Source: ANGEL ONE — "
        f"{symbol}"
    )


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

indicators = (
    TelemetryEngine.calculate_indicators(
        df
    )
)


# ============================================================
# MARKET SNAPSHOT
# ============================================================

st.subheader(
    f"📊 {symbol} Market Snapshot"
)

col1, col2, col3, col4 = st.columns(4)


with col1:

    st.metric(
        "LTP",
        f"{indicators['ltp']:.2f}",
    )


with col2:

    st.metric(
        "RSI",
        indicators["rsi"],
    )


with col3:

    st.metric(
        "VWAP",
        f"{indicators['vwap']:.2f}",
    )


with col4:

    st.metric(
        "ADX",
        indicators["adx"],
    )


# ============================================================
# MARKET ANALYSIS
# ============================================================

st.subheader(
    "🔎 Market Analysis"
)

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

st.subheader(
    f"📈 {symbol} Price Chart"
)

chart_data = (
    df.set_index("timestamp")[["close"]]
)

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
    "reason": (
        "AI analysis not requested."
    ),
}


if analysis_mode == "Technical + AI":

    with st.spinner(
        "🤖 Gemini is analyzing "
        "the technical setup..."
    ):

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

    ai_confidence = (
        ai_result["confidence"]
    )

    if (
        ai_confidence
        < MIN_AI_CONFIDENCE
    ):

        signal = "NO_TRADE"

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

st.subheader(
    "🤖 Paper Trading Signal"
)

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

    st.subheader(
        "🧠 Gemini AI Analysis"
    )

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
# PAPER TRADE PLAN
# ============================================================

st.subheader(
    "🎯 Paper Trade Plan"
)

ltp = indicators["ltp"]

atr = indicators["atr"]


if signal == "ENTER_LONG":

    stop_loss = (
        ltp - (1.0 * atr)
    )

    target_1 = (
        ltp + (1.5 * atr)
    )

    target_2 = (
        ltp + (2.5 * atr)
    )

elif signal == "ENTER_SHORT":

    stop_loss = (
        ltp + (1.0 * atr)
    )

    target_1 = (
        ltp - (1.5 * atr)
    )

    target_2 = (
        ltp - (2.5 * atr)
    )

else:

    stop_loss = 0

    target_1 = 0

    target_2 = 0


col1, col2, col3 = st.columns(3)


with col1:

    st.metric(
        "Entry",
        f"{ltp:.2f}",
    )


with col2:

    st.metric(
        "Stop Loss",
        f"{stop_loss:.2f}",
    )


with col3:

    st.metric(
        "Target 1",
        f"{target_1:.2f}",
    )


st.metric(
    "Target 2",
    f"{target_2:.2f}",
)


# ============================================================
# RECENT CANDLES
# ============================================================

with st.expander(
    f"🕯️ Recent {symbol} Candles"
):

    st.dataframe(
        df.tail(10),
        use_container_width=True,
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

st.subheader(
    "🛡️ System Status"
)

ai_status = (
    "CONNECTED"
    if gemini_key
    else "NOT CONNECTED"
)

market_status = (
    "ANGEL ONE DATA"
    if data_source != "OFFLINE TEST DATA"
    else "OFFLINE TEST DATA"
)

paper_status = (
    "ENABLED"
    if PAPER_TRADING
    else "DISABLED"
)

status_data = {
    "Component": [
        "Selected Instrument",
        "Market Data",
        "Technical Engine",
        "Risk Manager",
        "Paper Broker",
        "AI Layer",
        "Paper Trading",
        "Real Orders",
    ],

    "Status": [
        symbol,
        market_status,
        "READY",
        "READY",
        "READY",
        ai_status,
        paper_status,
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
    "🔒 Safety Lock: Real broker orders are disabled. "
    "This dashboard is for paper trading and "
    "market research only."
)
