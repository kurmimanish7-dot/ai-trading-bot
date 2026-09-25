import time
import os
import json
import threading

import streamlit as st
import pandas as pd
import numpy as np

from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from google import genai

from telemetry_engine import TelemetryEngine
from advanced_analysis import build_advanced_analysis

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
        "exchange_type": 1,
        "token_secret": "NIFTY_TOKEN",
        "default_token": "99926000",
        "description": "NIFTY 50 Index",
    },

    "BANK NIFTY": {
        "exchange": "NSE",
        "exchange_type": 1,
        "token_secret": "BANKNIFTY_TOKEN",
        "default_token": None,
        "description": "NIFTY Bank Index",
    },

    "SENSEX": {
        "exchange": "BSE",
        "exchange_type": 3,
        "token_secret": "SENSEX_TOKEN",
        "default_token": "99926009",
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
# LIVE WEBSOCKET STATE
# ============================================================

LIVE_LTP = {}
LIVE_TICKS = {}
LIVE_LTP_LOCK = threading.Lock()

LIVE_WS = None
LIVE_WS_THREAD = None
LIVE_WS_STARTED = False


# ============================================================
# WEBSOCKET CALLBACKS
# ============================================================

def websocket_on_data(wsapp, message):
    global LIVE_LTP

    try:
        if not isinstance(message, dict):
            return

        token = str(
            message.get("token", "")
        )

        raw_ltp = message.get(
            "last_traded_price"
        )

        if raw_ltp is None:
            return

        ltp = float(raw_ltp)

        # Angel One WebSocket V2
        # sends price in paise.
        ltp = ltp / 100.0

        with LIVE_LTP_LOCK:
            LIVE_LTP[token] = ltp
            LIVE_TICKS[token] = message

    except Exception:
        pass


def websocket_on_error(wsapp, error):
    pass


def websocket_on_close(wsapp):
    pass


def websocket_on_open(wsapp):
    pass


# ============================================================
# START ANGEL ONE WEBSOCKET
# ============================================================

def start_websocket(symbol):
    global LIVE_WS
    global LIVE_WS_THREAD
    global LIVE_WS_STARTED

    if LIVE_WS_STARTED:
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

        if not session:
            return

        if not session.get("status"):
            return

        auth_token = session["data"]["jwtToken"]

        feed_token = smart_api.getfeedToken()

        if not feed_token:
            return

        LIVE_WS = SmartWebSocketV2(
            auth_token,
            credentials["api_key"],
            credentials["client_code"],
            feed_token,
        )

        correlation_id = "ai_trading_live"

        mode = 1

        exchange_type = INSTRUMENTS[
            symbol
        ]["exchange_type"]

        token_list = [
            {
                "exchangeType": exchange_type,
                "tokens": [str(token)],
            }
        ]

        def on_open(wsapp):
            try:
                LIVE_WS.subscribe(
                    correlation_id,
                    mode,
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

    except Exception:
        LIVE_WS_STARTED = False


# ============================================================
# SAMPLE MARKET DATA
# FALLBACK ONLY
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
        + np.sin(
            np.arange(rows) / 5.0
        ) * 35.0
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
# ANGEL ONE REST LTP
# ============================================================

def fetch_live_ltp(instrument):

    try:

        credentials = get_angel_credentials()

        if not all(credentials.values()):
            return None, (
                "Angel One credentials incomplete"
            )

        telemetry = TelemetryEngine(
            api_key=credentials["api_key"],
            client_code=credentials["client_code"],
            pin=credentials["pin"],
            totp_secret=credentials["totp_secret"],
        )

        token = get_instrument_token(
            instrument
        )

        if not token:
            return None, (
                f"{instrument} token not configured"
            )

        exchange = INSTRUMENTS[
            instrument
        ]["exchange"]

        tradingsymbol = {
            "NIFTY 50": "NIFTY",
            "BANK NIFTY": "BANKNIFTY",
            "SENSEX": "SENSEX",
        }.get(
            instrument,
            instrument,
        )

        result = telemetry.get_live_ltp(
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            symboltoken=str(token),
        )

        if not result.get("status"):
            return None, result.get(
                "error",
                "LTP fetch failed",
            )

        return result, None

    except Exception as e:

        return None, str(e)


# ============================================================
# REAL MARKET DATA
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
            f"{symbol} token is not configured."
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

    exchange = INSTRUMENTS[
        symbol
    ]["exchange"]

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
                f"Angel One returned no candle "
                f"data for {symbol}."
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
                    f"Missing candle column: "
                    f"{column}"
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
                "No valid candle data "
                "after cleaning."
            )

        return df, None

    except Exception as e:

        return None, (
            "Angel One connection error: "
            + str(e)
        )


# ============================================================
# ADVANCED ANALYSIS
# ============================================================

def get_advanced_analysis(df):

    try:

        return build_advanced_analysis(df)

    except Exception as e:

        return {
            "status": "ERROR",
            "error": str(e),
        }


# ============================================================
# GEMINI ANALYSIS
# ============================================================

def get_ai_analysis(
    indicators,
    advanced_analysis,
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
- Do not invent news, price, VIX, OI, PCR,
  Greeks or any other unavailable data.
- If data is insufficient, return NO_TRADE.
- Be conservative.

Instrument:
{symbol}

Candle interval:
{interval}

BASE TECHNICAL DATA:

LTP: {indicators.get("ltp")}
RSI: {indicators.get("rsi")}
VWAP: {indicators.get("vwap")}
ADX: {indicators.get("adx")}
ATR: {indicators.get("atr")}
EMA Trend: {indicators.get("ema_trend")}
Supertrend: {indicators.get("supertrend")}
VWAP Position: {indicators.get("price_vs_vwap")}
Market Regime: {indicators.get("market_regime")}

ADVANCED ANALYSIS:

Candlestick:
{advanced_analysis.get("candlestick_patterns")}

MACD:
{advanced_analysis.get("macd")}

EMA 200:
{advanced_analysis.get("ema_200")}

Support / Resistance:
{advanced_analysis.get("support_resistance")}

Volume:
{advanced_analysis.get("volume")}

Market Structure:
{advanced_analysis.get("market_structure")}

Use the available confirmations together.

Do NOT assume that one indicator alone is enough.

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

        response_text = response.text.strip()

        if response_text.startswith("```"):

            response_text = response_text.replace(
                "```json",
                "",
            )

            response_text = response_text.replace(
                "```",
                "",
            )

            response_text = response_text.strip()

        result = json.loads(
            response_text
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

        reason = str(
            result.get(
                "reason",
                "No reason provided",
            )
        )

        if confidence < 0:
            confidence = 0

        if confidence > 100:
            confidence = 100

        allowed_signals = {
            "ENTER_LONG",
            "ENTER_SHORT",
            "NO_TRADE",
        }

        if signal not in allowed_signals:
            signal = "NO_TRADE"

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
            "confidence": 0.0,
            "reason": (
                "Gemini analysis error: "
                + str(e)
            ),
        }


# ============================================================
# SIGNAL LEVEL CALCULATION
# ============================================================

def calculate_trade_levels(
    df,
    signal,
    atr,
):

    if df is None or df.empty:
        return {
            "entry": 0.0,
            "stop_loss": 0.0,
            "target_1": 0.0,
            "target_2": 0.0,
        }

    price = float(
        df["close"].iloc[-1]
    )

    try:
        atr_value = float(atr)
    except Exception:
        atr_value = 0.0

    if atr_value <= 0:
        atr_value = max(
            price * 0.002,
            1.0,
        )

    if signal == "ENTER_LONG":

        stop_loss = price - (
            atr_value * 1.5
        )

        target_1 = price + (
            atr_value * 2.0
        )

        target_2 = price + (
            atr_value * 3.0
        )

    elif signal == "ENTER_SHORT":

        stop_loss = price + (
            atr_value * 1.5
        )

        target_1 = price - (
            atr_value * 2.0
        )

        target_2 = price - (
            atr_value * 3.0
        )

    else:

        stop_loss = 0.0
        target_1 = 0.0
        target_2 = 0.0

    return {
        "entry": price,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
    }


# ============================================================
# MAIN DASHBOARD
# ============================================================

st.title("📈 AI Trading Bot")

st.subheader(
    "Paper Trading Dashboard"
)

st.info(
    "🛡️ Paper Trading Mode is ON — "
    "No real broker orders are allowed."
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "⚙️ Market Settings"
)

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
    index=0,
)

auto_refresh = st.sidebar.checkbox(
    "Auto Refresh",
    value=True,
)

refresh_seconds = st.sidebar.slider(
    "Refresh Seconds",
    min_value=1,
    max_value=60,
    value=5,
)


# ============================================================
# LIVE CONNECTION
# ============================================================

start_websocket(symbol)

token = get_instrument_token(symbol)

live_ltp = None

if token:

    with LIVE_LTP_LOCK:

        live_ltp = LIVE_LTP.get(
            str(token)
        )


# ============================================================
# MARKET DATA
# ============================================================

df, market_error = fetch_real_market_data(
    symbol,
    interval,
)


if df is None:

    st.error(
        market_error
        or "Market data unavailable."
    )

    st.warning(
        "Live Angel One data is required "
        "for the paper-trading analysis."
    )

    st.stop()


# ============================================================
# INDICATORS
# ============================================================

try:

    credentials = get_angel_credentials()

    engine = TelemetryEngine(
        api_key=credentials["api_key"],
        client_code=credentials["client_code"],
        pin=credentials["pin"],
        totp_secret=credentials["totp_secret"],
    )

    indicators = engine.calculate_indicators(
        df
    )

except Exception as e:

    st.error(
        "Indicator calculation error: "
        + str(e)
    )

    st.stop()


# ============================================================
# LIVE LTP OVERRIDE
# ============================================================

if live_ltp is not None:

    indicators["ltp"] = live_ltp

else:

    try:
        indicators["ltp"] = float(
            df["close"].iloc[-1]
        )
    except Exception:
        indicators["ltp"] = 0.0


current_ltp = float(
    indicators.get(
        "ltp",
        0.0,
    )
)


# ============================================================
# ADVANCED ANALYSIS
# ============================================================

advanced_analysis = (
    get_advanced_analysis(df)
)

indicators["advanced_analysis"] = (
    advanced_analysis
)


# ============================================================
# AI ANALYSIS
# ============================================================

if analysis_mode == "Technical + AI":

    ai_result = get_ai_analysis(
        indicators,
        advanced_analysis,
        symbol,
        interval,
    )

else:

    ai_result = {
        "signal": "NO_TRADE",
        "confidence": 0.0,
        "reason": (
            "Technical Only mode selected."
        ),
    }


# ============================================================
# TRADE LEVELS
# ============================================================

trade_levels = calculate_trade_levels(
    df,
    ai_result["signal"],
    indicators.get("atr", 0),
)


# ============================================================
# TOP METRICS
# ============================================================

st.subheader(
    "📊 Live Market"
)

col1, col2, col3, col4 = st.columns(4)

with col1:

    st.metric(
        "LTP",
        f"{current_ltp:,.2f}",
    )

with col2:

    st.metric(
        "RSI",
        f"{float(indicators.get('rsi', 0)):.2f}",
    )

with col3:

    st.metric(
        "ADX",
        f"{float(indicators.get('adx', 0)):.2f}",
    )

with col4:

    st.metric(
        "ATR",
        f"{float(indicators.get('atr', 0)):.2f}",
    )


# ============================================================
# AI SIGNAL
# ============================================================

st.subheader(
    "🤖 AI Trading Signal"
)

signal = ai_result["signal"]
confidence = ai_result["confidence"]
reason = ai_result["reason"]


if signal == "ENTER_LONG":

    st.success(
        f"🟢 ENTER LONG — PAPER ONLY"
    )

elif signal == "ENTER_SHORT":

    st.error(
        f"🔴 ENTER SHORT — PAPER ONLY"
    )

else:

    st.warning(
        "🟡 NO TRADE"
    )


col1, col2 = st.columns(2)

with col1:

    st.metric(
        "AI Confidence",
        f"{confidence:.1f}%",
    )

with col2:

    st.write(
        "**AI Reason**"
    )

    st.write(reason)


# ============================================================
# TRADE LEVELS
# ============================================================

st.subheader(
    "🎯 Paper Trade Levels"
)

col1, col2, col3, col4 = st.columns(4)

with col1:

    st.metric(
        "Entry",
        f"{trade_levels['entry']:,.2f}",
    )

with col2:

    st.metric(
        "Stop Loss",
        (
            f"{trade_levels['stop_loss']:,.2f}"
            if trade_levels["stop_loss"]
            else "-"
        ),
    )

with col3:

    st.metric(
        "Target 1",
        (
            f"{trade_levels['target_1']:,.2f}"
            if trade_levels["target_1"]
            else "-"
        ),
    )

with col4:

    st.metric(
        "Target 2",
        (
            f"{trade_levels['target_2']:,.2f}"
            if trade_levels["target_2"]
            else "-"
        ),
    )


# ============================================================
# ADVANCED MARKET ANALYSIS
# ============================================================

st.subheader(
    "🧠 Advanced Market Analysis — Phase 1"
)


if advanced_analysis.get("status") == "OK":

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            "### 🕯️ Candlestick"
        )

        patterns = advanced_analysis.get(
            "candlestick_patterns",
            [],
        )

        if patterns:

            for pattern in patterns:
                st.write(
                    f"• {pattern}"
                )

        st.write(
            "### 📈 MACD"
        )

        macd = advanced_analysis.get(
            "macd",
            {},
        )

        st.write(
            f"MACD: "
            f"{float(macd.get('value', 0)):.4f}"
        )

        st.write(
            f"Signal: "
            f"{float(macd.get('signal', 0)):.4f}"
        )

        st.write(
            f"Histogram: "
            f"{float(macd.get('histogram', 0)):.4f}"
        )

        st.write(
            f"Bias: "
            f"**{macd.get('bias', 'UNKNOWN')}**"
        )

        st.write(
            "### 📊 EMA 200"
        )

        ema_200 = advanced_analysis.get(
            "ema_200",
            {},
        )

        st.write(
            f"EMA 200: "
            f"{float(ema_200.get('value', 0)):.2f}"
        )

        st.write(
            f"Position: "
            f"**{ema_200.get('position', 'UNKNOWN')}**"
        )

    with col2:

        st.write(
            "### 🧱 Support / Resistance"
        )

        sr = advanced_analysis.get(
            "support_resistance",
            {},
        )

        st.write(
            f"Support: "
            f"{float(sr.get('support', 0)):.2f}"
        )

        st.write(
            f"Resistance: "
            f"{float(sr.get('resistance', 0)):.2f}"
        )

        st.write(
            "### 📦 Volume"
        )

        volume = advanced_analysis.get(
            "volume",
            {},
        )

        st.write(
            f"Current Volume: "
            f"{float(volume.get('volume', 0)):,.0f}"
        )

        st.write(
            f"Average Volume: "
            f"{float(volume.get('average_volume', 0)):,.0f}"
        )

        st.write(
            f"Volume Ratio: "
            f"{float(volume.get('ratio', 0)):.2f}x"
        )

        st.write(
            f"Volume Signal: "
            f"**{volume.get('signal', 'UNKNOWN')}**"
        )

        st.write(
            "### 🧭 Market Structure"
        )

        structure = advanced_analysis.get(
            "market_structure",
            {},
        )

        st.write(
            f"Structure: "
            f"**{structure.get('structure', 'UNKNOWN')}**"
        )

        st.write(
            f"Bias: "
            f"**{structure.get('bias', 'UNKNOWN')}**"
        )

        st.write(
            f"Momentum: "
            f"**{structure.get('momentum', 'UNKNOWN')}**"
        )

else:

    st.error(
        advanced_analysis.get(
            "error",
            "Advanced analysis failed.",
        )
    )


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

st.subheader(
    "📐 Technical Indicators"
)

technical_data = {
    "LTP": indicators.get("ltp"),
    "RSI": indicators.get("rsi"),
    "VWAP": indicators.get("vwap"),
    "ADX": indicators.get("adx"),
    "ATR": indicators.get("atr"),
    "EMA Trend": indicators.get("ema_trend"),
    "Supertrend": indicators.get("supertrend"),
    "Price vs VWAP": indicators.get(
        "price_vs_vwap"
    ),
    "Market Regime": indicators.get(
        "market_regime"
    ),
}

st.dataframe(
    pd.DataFrame(
        [
            technical_data
        ]
    ),
    use_container_width=True,
)


# ============================================================
# RECENT CANDLES
# ============================================================

st.subheader(
    "🕯️ Recent Market Candles"
)

display_df = df.tail(20).copy()

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# SYSTEM STATUS
# ============================================================

st.subheader(
    "🛡️ System Status"
)

col1, col2, col3, col4 = st.columns(4)

with col1:

    st.metric(
        "Trading Mode",
        "PAPER",
    )

with col2:

    st.metric(
        "Market",
        INSTRUMENTS[symbol]["exchange"],
    )

with col3:

    st.metric(
        "Advanced Analysis",
        "ACTIVE",
    )

with col4:

    st.metric(
        "Real Orders",
        "DISABLED",
    )


# ============================================================
# SAFETY NOTICE
# ============================================================

st.info(
    "🔒 Safety Lock: This application is configured "
    "for PAPER TRADING only. No real broker order "
    "is placed by this dashboard."
)


# ============================================================
# REFRESH INFORMATION
# ============================================================

st.caption(
    f"Last dashboard refresh: "
    f"{pd.Timestamp.now().strftime('%H:%M:%S')}"
)

if auto_refresh:

    st.caption(
        f"Auto-refresh setting: "
        f"{refresh_seconds} seconds"
    )

    time.sleep(
        refresh_seconds
    )

    st.rerun()
