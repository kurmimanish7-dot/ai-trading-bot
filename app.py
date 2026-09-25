import os
import json
import time
import threading

import streamlit as st
import pandas as pd

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

st.info(
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

    token = get_secret(
        item["token_secret"]
    )

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

        token = str(
            message.get(
                "token",
                ""
            )
        )

        raw_ltp = message.get(
            "last_traded_price"
        )

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

    if (
        LIVE_WS_STARTED
        and LIVE_WS_SYMBOL == symbol
    ):
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

        if (
            not session
            or not session.get("status")
        ):
            return

        auth_token = session["data"]["jwtToken"]

        feed_token = smart_api.getfeedToken()

        LIVE_WS = SmartWebSocketV2(
            auth_token,
            credentials["api_key"],
            credentials["client_code"],
            feed_token,
        )

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

def fetch_market_data(
    symbol,
    interval,
):

    credentials = get_angel_credentials()

    if not all(credentials.values()):

        return (
            None,
            "Angel One credentials incomplete.",
        )

    token = get_instrument_token(symbol)

    if not token:

        return (
            None,
            f"{symbol} token is not configured.",
        )

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

            return (
                None,
                "No candle data received.",
            )

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

                return (
                    None,
                    f"Missing column: {column}",
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

        return df, None

    except Exception as e:

        return None, str(e)


# ============================================================
# APPLY LIVE PRICE TO CURRENT CANDLE
# ============================================================

def apply_live_price(
    df,
    live_ltp,
):

    if (
        df is None
        or df.empty
        or live_ltp is None
    ):
        return df

    live_df = df.copy()

    try:

        price = float(live_ltp)

        idx = live_df.index[-1]

        old_high = float(
            live_df.loc[idx, "high"]
        )

        old_low = float(
            live_df.loc[idx, "low"]
        )

        live_df.loc[idx, "close"] = price

        live_df.loc[idx, "high"] = max(
            old_high,
            price,
        )

        live_df.loc[idx, "low"] = min(
            old_low,
            price,
        )

        return live_df

    except Exception:

        return df


# ============================================================
# SHORT AI REASON
# ============================================================

def short_reason(reason):

    if not reason:
        return "Market conditions are unclear."

    reason = str(reason).replace(
        "\n",
        " ",
    ).strip()

    if len(reason) > 150:

        reason = (
            reason[:147].rstrip()
            + "..."
        )

    return reason


# ============================================================
# GEMINI
# ============================================================

def call_gemini(
    indicators,
    advanced,
    symbol,
    interval,
):

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

def calculate_levels(
    signal,
    atr,
    live_ltp,
):

    try:
        price = float(live_ltp)
    except Exception:
        price = 0

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

    "last_indicator_update": 0.0,

    "live_indicators": {},

    "initial_advanced": {},

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
    "⚡ LTP live update: 1 sec"
)

st.sidebar.caption(
    "📊 Indicators update: 5 sec"
)

st.sidebar.caption(
    "🤖 Gemini analysis is throttled."
)


# ============================================================
# START WEBSOCKET
# ============================================================

start_websocket(symbol)


# ============================================================
# INITIAL MARKET DATA
# ============================================================

now = time.time()

should_fetch = (
    st.session_state.last_df is None
    or (
        now
        - st.session_state.last_market_fetch
        >= 30
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

        st.stop()


df = st.session_state.last_df


if df is None or df.empty:

    st.warning(
        "Waiting for market data..."
    )

    st.stop()


# ============================================================
# INITIAL LTP
# ============================================================

token = get_instrument_token(symbol)

with LIVE_LOCK:

    initial_ltp = (
        LIVE_LTP.get(
            str(token)
        )
        if token
        else None
    )


if initial_ltp is None:

    initial_ltp = float(
        df["close"].iloc[-1]
    )


initial_live_df = apply_live_price(
    df,
    initial_ltp,
)


# ============================================================
# INITIAL INDICATORS
# ============================================================

try:

    credentials = get_angel_credentials()

    engine = TelemetryEngine(
        api_key=credentials["api_key"],
        client_code=credentials["client_code"],
        pin=credentials["pin"],
        totp_secret=credentials["totp_secret"],
    )

    initial_indicators = (
        engine.calculate_indicators(
            initial_live_df
        )
    )

    initial_indicators["ltp"] = float(
        initial_ltp
    )

    st.session_state.live_indicators = (
        initial_indicators.copy()
    )

except Exception as e:

    st.error(
        "Indicator error: " + str(e)
    )

    st.stop()


# ============================================================
# ADVANCED ANALYSIS
# ============================================================

initial_advanced = build_advanced_analysis(
    initial_live_df
)

st.session_state.initial_advanced = (
    initial_advanced
)


# ============================================================
# INITIAL GEMINI
# ============================================================

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
            initial_indicators,
            initial_advanced,
            symbol,
            interval,
        )

        st.session_state.ai_result = result

        st.session_state.last_ai_time = now

        if "Gemini error: 429" in str(
            result.get(
                "reason",
                "",
            )
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


# ============================================================
# CONTAINERS
# ============================================================

st.subheader("📊 Live Market")

live_market_area = st.empty()

live_market_area.write(
    "Connecting to live market feed..."
)


st.subheader("🤖 AI Trading Signal")

signal_area = st.empty()

signal_area.write(
    "AI analysis loaded."
)


st.subheader("🎯 Paper Trade Levels")

levels_area = st.empty()

levels_area.write(
    "Calculating paper levels..."
)


st.subheader(
    "🧠 Advanced Market Analysis — Phase 1"
)

advanced_area = st.empty()


st.subheader("📐 Technical Indicators")

technical_area = st.empty()


st.subheader("🕯️ Recent Market Candles")

candles_area = st.empty()


st.subheader("🛡️ System Status")

system_area = st.empty()


# ============================================================
# INITIAL STATIC AI SIGNAL
# ============================================================

def render_ai_signal():

    result = st.session_state.ai_result

    signal = result["signal"]

    if signal == "ENTER_LONG":

        message = "🟢 ENTER LONG — PAPER ONLY"

    elif signal == "ENTER_SHORT":

        message = "🔴 ENTER SHORT — PAPER ONLY"

    else:

        message = "🟡 NO TRADE"

    with signal_area.container():

        st.write(f"**{message}**")

        st.write(
            f"**AI Confidence:** "
            f"{result['confidence']:.1f}%"
        )

        st.write(
            "**AI Reason:** "
            + short_reason(
                result["reason"]
            )
        )


render_ai_signal()


# ============================================================
# INITIAL ADVANCED ANALYSIS
# ============================================================

def render_advanced():

    advanced = (
        st.session_state.initial_advanced
    )

    with advanced_area.container():

        if advanced.get("status") != "OK":

            st.write(
                "Advanced analysis unavailable."
            )

            return

        c1, c2 = st.columns(2)

        with c1:

            st.write("### 🕯️ Candlestick")

            patterns = advanced.get(
                "candlestick_patterns",
                [],
            )

            if patterns:

                for pattern in patterns:

                    st.write(
                        f"• {pattern}"
                    )

            else:

                st.write(
                    "No confirmed pattern."
                )

            macd = advanced.get(
                "macd",
                {},
            )

            st.write("### 📈 MACD")

            st.write(
                f"Value: "
                f"{float(macd.get('value', 0)):.4f}"
            )

            st.write(
                f"Signal: "
                f"{float(macd.get('signal', 0)):.4f}"
            )

            st.write(
                f"Bias: "
                f"**{macd.get('bias', 'UNKNOWN')}**"
            )

            ema = advanced.get(
                "ema_200",
                {},
            )

            st.write("### 📊 EMA 200")

            st.write(
                f"EMA 200: "
                f"{float(ema.get('value', 0)):.2f}"
            )

            st.write(
                f"Position: "
                f"**{ema.get('position', 'UNKNOWN')}**"
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
                f"Support: "
                f"{float(sr.get('support', 0)):.2f}"
            )

            st.write(
                f"Resistance: "
                f"{float(sr.get('resistance', 0)):.2f}"
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
                f"Signal: "
                f"**{volume.get('signal', 'UNKNOWN')}**"
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
                f"Bias: "
                f"**{structure.get('bias', 'UNKNOWN')}**"
            )

            st.write(
                f"Momentum: "
                f"**{structure.get('momentum', 'UNKNOWN')}**"
            )


render_advanced()


# ============================================================
# INITIAL TECHNICAL TABLE
# ============================================================

def render_technical():

    indicators = (
        st.session_state.live_indicators
    )

    technical = {

        "LTP":
            indicators.get("ltp"),

        "RSI":
            indicators.get("rsi"),

        "VWAP":
            indicators.get("vwap"),

        "ADX":
            indicators.get("adx"),

        "ATR":
            indicators.get("atr"),

        "EMA Trend":
            indicators.get("ema_trend"),

        "Supertrend":
            indicators.get("supertrend"),

        "VWAP Position":
            indicators.get("price_vs_vwap"),

        "Market Regime":
            indicators.get("market_regime"),
    }

    with technical_area.container():

        st.dataframe(
            pd.DataFrame(
                [technical]
            ),
            use_container_width=True,
            hide_index=True,
        )


render_technical()


# ============================================================
# INITIAL CANDLES
# ============================================================

with candles_area.container():

    st.dataframe(
        initial_live_df.tail(20),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

with system_area.container():

    st.write(
        "Trading Mode: **PAPER**"
    )

    st.write(
        "Market: **"
        + INSTRUMENTS[symbol]["exchange"]
        + "**"
    )

    st.write(
        "Advanced Analysis: **ACTIVE**"
    )

    st.write(
        "Real Orders: **DISABLED**"
    )

    st.caption(
        "🔒 Safety Lock: No real broker orders are placed."
    )

    st.caption(
        "⚡ Live WebSocket market feed active."
    )


# ============================================================
# LIVE LTP + LEVELS
# ============================================================

@st.fragment(
    run_every=1,
    key="live_market_fragment",
)
def live_market_fragment():

    token_now = get_instrument_token(
        symbol
    )

    with LIVE_LOCK:

        current_ltp = (
            LIVE_LTP.get(
                str(token_now)
            )
            if token_now
            else None
        )

    if current_ltp is None:

        current_ltp = float(
            st.session_state.last_df[
                "close"
            ].iloc[-1]
        )

    indicators = (
        st.session_state.live_indicators
    )

    atr = indicators.get(
        "atr",
        0,
    )

    signal = (
        st.session_state.ai_result[
            "signal"
        ]
    )

    levels = calculate_levels(
        signal,
        atr,
        current_ltp,
    )

    # --------------------------------------------------------
    # LIVE MARKET
    # --------------------------------------------------------

    with live_market_area.container():

        st.markdown(
            f"**LTP:** "
            f"`{float(current_ltp):,.2f}`"
            f"  |  "
            f"**RSI:** "
            f"`{float(indicators.get('rsi', 0)):.2f}`"
            f"  |  "
            f"**ADX:** "
            f"`{float(indicators.get('adx', 0)):.2f}`"
            f"  |  "
            f"**ATR:** "
            f"`{float(indicators.get('atr', 0)):.2f}`"
        )

    # --------------------------------------------------------
    # PAPER LEVELS
    # --------------------------------------------------------

    with levels_area.container():

        if signal == "ENTER_LONG":

            text = (
                f"**Entry:** `{levels['entry']:,.2f}`"
                f"  |  "
                f"**SL:** `{levels['sl']:,.2f}`"
                f"  |  "
                f"**Target 1:** `{levels['target1']:,.2f}`"
                f"  |  "
                f"**Target 2:** `{levels['target2']:,.2f}`"
            )

        elif signal == "ENTER_SHORT":

            text = (
                f"**Entry:** `{levels['entry']:,.2f}`"
                f"  |  "
                f"**SL:** `{levels['sl']:,.2f}`"
                f"  |  "
                f"**Target 1:** `{levels['target1']:,.2f}`"
                f"  |  "
                f"**Target 2:** `{levels['target2']:,.2f}`"
            )

        else:

            text = (
                f"**Entry:** `{levels['entry']:,.2f}`"
                f"  |  "
                f"**SL:** `—`"
                f"  |  "
                f"**Target 1:** `—`"
                f"  |  "
                f"**Target 2:** `—`"
            )

        st.markdown(text)


# ============================================================
# INDICATOR / CANDLE / AI UPDATE
# ============================================================

@st.fragment(
    run_every=5,
    key="analysis_fragment",
)
def analysis_fragment():

    current_time = time.time()

    token_now = get_instrument_token(
        symbol
    )

    with LIVE_LOCK:

        current_ltp = (
            LIVE_LTP.get(
                str(token_now)
            )
            if token_now
            else None
        )

    if current_ltp is None:

        current_ltp = float(
            st.session_state.last_df[
                "close"
            ].iloc[-1]
        )

    # --------------------------------------------------------
    # REFRESH REST CANDLES EVERY 30 SEC
    # --------------------------------------------------------

    if (
        current_time
        - st.session_state.last_market_fetch
        >= 30
    ):

        new_df, error = fetch_market_data(
            symbol,
            interval,
        )

        if new_df is not None:

            st.session_state.last_df = new_df

            st.session_state.last_market_fetch = (
                current_time
            )

    live_df = apply_live_price(
        st.session_state.last_df,
        current_ltp,
    )

    # --------------------------------------------------------
    # INDICATORS
    # --------------------------------------------------------

    if (
        current_time
        - st.session_state.last_indicator_update
        >= 5
    ):

        try:

            credentials = (
                get_angel_credentials()
            )

            engine = TelemetryEngine(
                api_key=credentials["api_key"],
                client_code=credentials["client_code"],
                pin=credentials["pin"],
                totp_secret=credentials["totp_secret"],
            )

            indicators = (
                engine.calculate_indicators(
                    live_df
                )
            )

            indicators["ltp"] = float(
                current_ltp
            )

            st.session_state.live_indicators = (
                indicators
            )

            st.session_state.last_indicator_update = (
                current_time
            )

        except Exception:

            pass

    # --------------------------------------------------------
    # ADVANCED ANALYSIS
    # --------------------------------------------------------

    try:

        advanced = build_advanced_analysis(
            live_df
        )

        st.session_state.initial_advanced = (
            advanced
        )

    except Exception:

        advanced = (
            st.session_state.initial_advanced
        )

    # --------------------------------------------------------
    # GEMINI — THROTTLED
    # --------------------------------------------------------

    if analysis_mode == "Technical + AI":

        ai_due = (
            current_time
            - st.session_state.last_ai_time
            >= ai_interval
        )

        quota_blocked = (
            current_time
            < st.session_state.ai_blocked_until
        )

        if ai_due and not quota_blocked:

            result = call_gemini(
                st.session_state.live_indicators,
                advanced,
                symbol,
                interval,
            )

            st.session_state.ai_result = (
                result
            )

            st.session_state.last_ai_time = (
                current_time
            )

            if "Gemini error: 429" in str(
                result.get(
                    "reason",
                    "",
                )
            ):

                st.session_state.ai_blocked_until = (
                    current_time + 900
                )

            render_ai_signal()

    # --------------------------------------------------------
    # TECHNICAL TABLE
    # --------------------------------------------------------

    render_technical()

    # --------------------------------------------------------
    # CANDLES
    # --------------------------------------------------------

    with candles_area.container():

        st.dataframe(
            live_df.tail(20),
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # ADVANCED
    # --------------------------------------------------------

    render_advanced()


# ============================================================
# RUN FRAGMENTS
# ============================================================

live_market_fragment()

analysis_fragment()
