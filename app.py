import os
import json
import time
import threading

import streamlit as st
import pandas as pd
import numpy as np

from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from google import genai

from telemetry_engine import TelemetryEngine
from advanced_analysis import build_advanced_analysis

from config import AI_MODEL, PAPER_TRADING, MIN_AI_CONFIDENCE


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="AI Trading Bot",
    page_icon="📈",
    layout="wide",
)

st.title("📈 AI Trading Bot")
st.subheader("Paper Trading Dashboard")

st.info("🛡️ PAPER TRADING MODE — Real orders are disabled.")


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
# INSTRUMENTS
# ============================================================

INSTRUMENTS = {
    "NIFTY 50": {
        "exchange": "NSE",
        "exchange_type": 1,
        "token_secret": "NIFTY_TOKEN",
        "default_token": "99926000",
    },
    "BANK NIFTY": {
        "exchange": "NSE",
        "exchange_type": 1,
        "token_secret": "BANKNIFTY_TOKEN",
        "default_token": None,
    },
    "SENSEX": {
        "exchange": "BSE",
        "exchange_type": 3,
        "token_secret": "SENSEX_TOKEN",
        "default_token": "99926009",
    },
}


def get_instrument_token(symbol):
    item = INSTRUMENTS[symbol]

    token = get_secret(item["token_secret"])

    if token:
        return str(token)

    return item["default_token"]


# ============================================================
# LIVE WEBSOCKET
# ============================================================

LIVE_LTP = {}
LIVE_TICKS = {}
LIVE_LOCK = threading.Lock()

LIVE_WS = None
LIVE_WS_THREAD = None
LIVE_WS_STARTED = False
LIVE_WS_SYMBOL = None


def websocket_on_data(wsapp, message):
    try:
        if not isinstance(message, dict):
            return

        token = str(message.get("token", ""))

        raw_ltp = message.get("last_traded_price")

        if raw_ltp is None:
            return

        ltp = float(raw_ltp) / 100.0

        with LIVE_LOCK:
            LIVE_LTP[token] = ltp
            LIVE_TICKS[token] = message

    except Exception:
        pass


def websocket_on_error(wsapp, error):
    pass


def websocket_on_close(wsapp):
    pass


def start_websocket(symbol):
    global LIVE_WS
    global LIVE_WS_THREAD
    global LIVE_WS_STARTED
    global LIVE_WS_SYMBOL

    if LIVE_WS_STARTED and LIVE_WS_SYMBOL == symbol:
        return

    credentials = get_angel_credentials()

    if not all(credentials.values()):
        return

    token = get_instrument_token(symbol)

    if not token:
        return

    try:
        import pyotp

        smart_api = SmartConnect(
            api_key=credentials["api_key"]
        )

        totp = pyotp.TOTP(
            credentials["totp_secret"]
        ).now()

        session = smart_api.generateSession(
            credentials["client_code"],
            credentials["pin"],
            totp,
        )

        if not session or not session.get("status"):
            return

        auth_token = session["data"]["jwtToken"]
        feed_token = smart_api.getfeedToken()

        LIVE_WS = SmartWebSocketV2(
            auth_token,
            credentials["api_key"],
            credentials["client_code"],
            feed_token,
        )

        exchange_type = INSTRUMENTS[symbol]["exchange_type"]

        token_list = [
            {
                "exchangeType": exchange_type,
                "tokens": [str(token)],
            }
        ]

        def on_open(wsapp):
            try:
                LIVE_WS.subscribe(
                    "ai_trading_live",
                    1,
                    token_list,
                )
            except Exception:
                pass

        LIVE_WS.on_open = on_open
        LIVE_WS.on_data = websocket_on_data
        LIVE_WS.on_error = websocket_on_error
        LIVE_WS.on_close = websocket_on_close

        def run_socket():
            try:
                LIVE_WS.connect()
            except Exception:
                pass

        LIVE_WS_THREAD = threading.Thread(
            target=run_socket,
            daemon=True,
        )

        LIVE_WS_THREAD.start()

        LIVE_WS_STARTED = True
        LIVE_WS_SYMBOL = symbol

    except Exception:
        LIVE_WS_STARTED = False


# ============================================================
# MARKET DATA
# ============================================================

def fetch_market_data(symbol, interval):

    credentials = get_angel_credentials()

    if not all(credentials.values()):
        return None, "Angel One credentials incomplete."

    token = get_instrument_token(symbol)

    if not token:
        return None, f"{symbol} token is not configured."

    try:
        engine = TelemetryEngine(
            api_key=credentials["api_key"],
            client_code=credentials["client_code"],
            pin=credentials["pin"],
            totp_secret=credentials["totp_secret"],
        )

        df = engine.fetch_ohlcv(
            exchange=INSTRUMENTS[symbol]["exchange"],
            token=token,
            interval=interval,
            days=5,
        )

        if df is None or df.empty:
            return None, "No candle data received."

        required = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        for column in required:
            if column not in df.columns:
                return None, f"Missing column: {column}"

        df = df.copy()

        df["timestamp"] = pd.to_datetime(df["timestamp"])

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

        return df, None

    except Exception as e:
        return None, str(e)


# ============================================================
# LIVE CANDLE
# ============================================================

def apply_live_price(df, live_ltp):

    if df is None or df.empty or live_ltp is None:
        return df

    live_df = df.copy()

    try:
        price = float(live_ltp)

        idx = live_df.index[-1]

        old_high = float(live_df.loc[idx, "high"])
        old_low = float(live_df.loc[idx, "low"])

        live_df.loc[idx, "close"] = price
        live_df.loc[idx, "high"] = max(old_high, price)
        live_df.loc[idx, "low"] = min(old_low, price)

        return live_df

    except Exception:
        return df


# ============================================================
# GEMINI
# ============================================================

def short_reason(reason):

    if not reason:
        return "Market conditions are unclear."

    reason = str(reason).replace("\n", " ").strip()

    if len(reason) > 150:
        reason = reason[:147].rstrip() + "..."

    return reason


def call_gemini(indicators, advanced, symbol, interval):

    api_key = get_gemini_api_key()

    if not api_key:
        return {
            "signal": "NO_TRADE",
            "confidence": 0,
            "reason": "Gemini API key unavailable.",
        }

    try:
        client = genai.Client(
            api_key=api_key
        )

        prompt = f"""
You are an AI trading-analysis assistant.

PAPER TRADING ONLY.
Never place orders.

Use ONLY supplied data.
Do not invent news, VIX, OI, PCR, Greeks or IV.

Instrument: {symbol}
Interval: {interval}

LTP: {indicators.get("ltp")}
RSI: {indicators.get("rsi")}
VWAP: {indicators.get("vwap")}
ADX: {indicators.get("adx")}
ATR: {indicators.get("atr")}
EMA Trend: {indicators.get("ema_trend")}
Supertrend: {indicators.get("supertrend")}
VWAP Position: {indicators.get("price_vs_vwap")}
Market Regime: {indicators.get("market_regime")}

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

Return ONLY valid JSON.

Signal must be one of:
ENTER_LONG
ENTER_SHORT
NO_TRADE

Confidence must be 0-100.

Reason MUST be ONE SHORT SENTENCE,
maximum 120 characters.

Example:
{{
 "signal": "ENTER_LONG",
 "confidence": 82,
 "reason": "Bullish momentum with price above VWAP and supportive RSI."
}}
"""

        response = client.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
        )

        response_text = response.text.strip()

        response_text = response_text.replace(
            "```json",
            "",
        )

        response_text = response_text.replace(
            "```",
            "",
        )

        result = json.loads(
            response_text.strip()
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
# TRADE LEVELS
# ============================================================

def calculate_levels(df, signal, atr, live_ltp):

    if df is None or df.empty:
        return {
            "entry": 0,
            "sl": 0,
            "target1": 0,
            "target2": 0,
        }

    try:
        price = float(live_ltp)
    except Exception:
        price = float(df["close"].iloc[-1])

    try:
        atr = float(atr)
    except Exception:
        atr = 0

    if atr <= 0:
        atr = max(
            price * 0.002,
            1,
        )

    if signal == "ENTER_LONG":

        sl = price - atr * 1.5
        target1 = price + atr * 2
        target2 = price + atr * 3

    elif signal == "ENTER_SHORT":

        sl = price + atr * 1.5
        target1 = price - atr * 2
        target2 = price - atr * 3

    else:
        sl = 0
        target1 = 0
        target2 = 0

    return {
        "entry": price,
        "sl": sl,
        "target1": target1,
        "target2": target2,
    }


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "last_df": None,
    "last_market_fetch": 0.0,
    "ai_result": {
        "signal": "NO_TRADE",
        "confidence": 0,
        "reason": "Waiting for AI analysis.",
    },
    "last_ai_time": 0.0,
    "ai_blocked_until": 0.0,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# SIDEBAR
# ============================================================

symbol = st.sidebar.selectbox(
    "Instrument",
    list(INSTRUMENTS.keys()),
    index=0,
)

interval = st.sidebar.selectbox(
    "Candle Interval",
    [
        "ONE_MINUTE",
        "FIVE_MINUTE",
        "FIFTEEN_MINUTE",
    ],
    index=1,
)

analysis_mode = st.sidebar.selectbox(
    "Analysis Mode",
    [
        "Technical + AI",
        "Technical Only",
    ],
)

ai_interval = st.sidebar.slider(
    "Gemini Analysis Interval",
    60,
    900,
    300,
    step=60,
)

st.sidebar.caption(
    "⚡ Market numbers update live. "
    "Gemini analysis is throttled to protect API quota."
)


# ============================================================
# START LIVE FEED
# ============================================================

start_websocket(symbol)


# ============================================================
# LIVE DASHBOARD
# ============================================================

@st.fragment(run_every=1)
def live_dashboard():

    now = time.time()

    token = get_instrument_token(symbol)

    live_ltp = None

    if token:

        with LIVE_LOCK:
            live_ltp = LIVE_LTP.get(
                str(token)
            )

    # --------------------------------------------------------
    # FETCH CANDLES PERIODICALLY
    # --------------------------------------------------------

    candle_refresh = 30

    should_fetch = (
        st.session_state.last_df is None
        or
        (
            now
            - st.session_state.last_market_fetch
            >= candle_refresh
        )
    )

    if should_fetch:

        df, error = fetch_market_data(
            symbol,
            interval,
        )

        if df is not None:

            st.session_state.last_df = df
            st.session_state.last_market_fetch = now

        elif st.session_state.last_df is None:

            st.error(
                error or "Market data unavailable."
            )

            return

    df = st.session_state.last_df

    if df is None or df.empty:
        st.warning("Waiting for market data...")
        return

    # --------------------------------------------------------
    # APPLY LIVE PRICE TO CURRENT CANDLE
    # --------------------------------------------------------

    live_df = apply_live_price(
        df,
        live_ltp,
    )

    if live_ltp is None:
        live_ltp = float(
            live_df["close"].iloc[-1]
        )

    # --------------------------------------------------------
    # INDICATORS
    # --------------------------------------------------------

    try:

        credentials = get_angel_credentials()

        engine = TelemetryEngine(
            api_key=credentials["api_key"],
            client_code=credentials["client_code"],
            pin=credentials["pin"],
            totp_secret=credentials["totp_secret"],
        )

        indicators = engine.calculate_indicators(
            live_df
        )

    except Exception as e:

        st.error(
            "Indicator error: " + str(e)
        )

        return

    indicators["ltp"] = float(live_ltp)

    # --------------------------------------------------------
    # ADVANCED ANALYSIS
    # --------------------------------------------------------

    advanced = build_advanced_analysis(
        live_df
    )

    # --------------------------------------------------------
    # GEMINI
    # --------------------------------------------------------

    if analysis_mode == "Technical + AI":

        ai_due = (
            now
            - st.session_state.last_ai_time
            >= ai_interval
        )

        quota_blocked = (
            now
            < st.session_state.ai_blocked_until
        )

        if ai_due and not quota_blocked:

            result = call_gemini(
                indicators,
                advanced,
                symbol,
                interval,
            )

            st.session_state.ai_result = result
            st.session_state.last_ai_time = now

            if "Gemini error: 429" in str(
                result.get("reason", "")
            ):

                st.session_state.ai_blocked_until = (
                    now + 900
                )

    else:

        st.session_state.ai_result = {
            "signal": "NO_TRADE",
            "confidence": 0,
            "reason": "Technical Only mode.",
        }

    ai_result = st.session_state.ai_result

    # --------------------------------------------------------
    # TRADE LEVELS
    # --------------------------------------------------------

    levels = calculate_levels(
        live_df,
        ai_result["signal"],
        indicators.get("atr", 0),
        live_ltp,
    )

    # ========================================================
    # LIVE MARKET
    # ========================================================

    st.subheader("📊 Live Market")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "LTP",
            f"{float(live_ltp):,.2f}",
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

    # ========================================================
    # AI SIGNAL
    # ========================================================

    st.subheader("🤖 AI Trading Signal")

    signal = ai_result["signal"]

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
            f"{ai_result['confidence']:.1f}%",
        )

    with c2:

        st.write("**AI Reason**")
        st.info(
            short_reason(
                ai_result["reason"]
            )
        )

    # ========================================================
    # TRADE LEVELS
    # ========================================================

    st.subheader("🎯 Paper Trade Levels")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Entry",
            f"{levels['entry']:,.2f}",
        )

    with c2:
        st.metric(
            "Stop Loss",
            f"{levels['sl']:,.2f}"
            if levels["sl"]
            else "-",
        )

    with c3:
        st.metric(
            "Target 1",
            f"{levels['target1']:,.2f}"
            if levels["target1"]
            else "-",
        )

    with c4:
        st.metric(
            "Target 2",
            f"{levels['target2']:,.2f}"
            if levels["target2"]
            else "-",
        )

    # ========================================================
    # ADVANCED ANALYSIS
    # ========================================================

    st.subheader(
        "🧠 Advanced Market Analysis — Phase 1"
    )

    if advanced.get("status") == "OK":

        c1, c2 = st.columns(2)

        with c1:

            st.write("### 🕯️ Candlestick")

            for pattern in advanced.get(
                "candlestick_patterns",
                [],
            ):
                st.write(
                    f"• {pattern}"
                )

            macd = advanced.get(
                "macd",
                {},
            )

            st.write("### 📈 MACD")

            st.write(
                f"Value: {float(macd.get('value', 0)):.4f}"
            )

            st.write(
                f"Signal: {float(macd.get('signal', 0)):.4f}"
            )

            st.write(
                f"Bias: **{macd.get('bias', 'UNKNOWN')}**"
            )

            ema = advanced.get(
                "ema_200",
                {},
            )

            st.write("### 📊 EMA 200")

            st.write(
                f"EMA 200: {float(ema.get('value', 0)):.2f}"
            )

            st.write(
                f"Position: **{ema.get('position', 'UNKNOWN')}**"
            )

        with c2:

            sr = advanced.get(
                "support_resistance",
                {},
            )

            st.write(
                "### 🧱 Support / Resistance"
            )

            st.write(
                f"Support: {float(sr.get('support', 0)):.2f}"
            )

            st.write(
                f"Resistance: {float(sr.get('resistance', 0)):.2f}"
            )

            volume = advanced.get(
                "volume",
                {},
            )

            st.write("### 📦 Volume")

            st.write(
                f"Volume Ratio: "
                f"{float(volume.get('ratio', 0)):.2f}x"
            )

            st.write(
                f"Signal: **{volume.get('signal', 'UNKNOWN')}**"
            )

            structure = advanced.get(
                "market_structure",
                {},
            )

            st.write(
                "### 🧭 Market Structure"
            )

            st.write(
                f"Structure: "
                f"**{structure.get('structure', 'UNKNOWN')}**"
            )

            st.write(
                f"Bias: **{structure.get('bias', 'UNKNOWN')}**"
            )

            st.write(
                f"Momentum: "
                f"**{structure.get('momentum', 'UNKNOWN')}**"
            )

    # ========================================================
    # TECHNICAL INDICATORS
    # ========================================================

    st.subheader("📐 Technical Indicators")

    technical = {
        "LTP": indicators.get("ltp"),
        "RSI": indicators.get("rsi"),
        "VWAP": indicators.get("vwap"),
        "ADX": indicators.get("adx"),
        "ATR": indicators.get("atr"),
        "EMA Trend": indicators.get("ema_trend"),
        "Supertrend": indicators.get("supertrend"),
        "VWAP Position": indicators.get("price_vs_vwap"),
        "Market Regime": indicators.get("market_regime"),
    }

    st.dataframe(
        pd.DataFrame([technical]),
        use_container_width=True,
        hide_index=True,
    )

    # ========================================================
    # RECENT CANDLES
    # ========================================================

    st.subheader("🕯️ Recent Market Candles")

    st.dataframe(
        live_df.tail(20),
        use_container_width=True,
        hide_index=True,
    )

    # ========================================================
    # SYSTEM STATUS
    # ========================================================

    st.subheader("🛡️ System Status")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Trading Mode",
            "PAPER",
        )

    with c2:
        st.metric(
            "Market",
            INSTRUMENTS[symbol]["exchange"],
        )

    with c3:
        st.metric(
            "Advanced Analysis",
            "ACTIVE",
        )

    with c4:
        st.metric(
            "Real Orders",
            "DISABLED",
        )

    st.caption(
        "🔒 Safety Lock: No real broker orders are placed."
    )

    st.caption(
        "⚡ Live market feed active"
    )


# ============================================================
# RUN
# ============================================================

live_dashboard()
