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
from options_engine import OptionsEngine

from config import AI_MODEL, PAPER_TRADING, MIN_AI_CONFIDENCE


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Trading Bot",
    page_icon="📈",
    layout="wide",
)

st.title("📈 AI Trading Bot")
st.subheader("Paper Trading Dashboard")

st.info("🛡️ PAPER TRADING MODE — Real orders are disabled.")

if PAPER_TRADING is not True:
    st.error("🚨 SAFETY LOCK: PAPER_TRADING must remain True.")
    st.stop()


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>
    .live-box {
        border: 1px solid rgba(128,128,128,0.30);
        border-radius: 10px;
        padding: 12px 14px;
        min-height: 90px;
        margin-bottom: 8px;
        background: rgba(128,128,128,0.04);
    }

    .live-label {
        font-size: 13px;
        opacity: 0.70;
        margin-bottom: 6px;
    }

    .live-value {
        font-size: 25px;
        font-weight: 700;
        line-height: 1.1;
    }

    .signal-box {
        border: 1px solid rgba(128,128,128,0.30);
        border-radius: 10px;
        padding: 14px;
        margin-bottom: 8px;
    }

    .signal-title {
        font-size: 13px;
        opacity: 0.70;
    }

    .signal-value {
        font-size: 24px;
        font-weight: 700;
        margin-top: 5px;
    }

    .reason-box {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 10px;
        padding: 12px;
        margin-top: 8px;
    }

    .live-box,
    .live-box *,
    .signal-box,
    .signal-box *,
    .reason-box,
    .reason-box * {
        animation: none !important;
        transition: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
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
        "options_name": "NIFTY",
    },

    "BANK NIFTY": {
        "exchange": "NSE",
        "exchange_type": 1,
        "token_secret": "BANKNIFTY_TOKEN",
        "default_token": None,
        "options_name": "BANKNIFTY",
    },

    "SENSEX": {
        "exchange": "BSE",
        "exchange_type": 3,
        "token_secret": "SENSEX_TOKEN",
        "default_token": "99926009",
        "options_name": "SENSEX",
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
# LIVE WEBSOCKET STATE
# ============================================================

LIVE_LTP = {}
LIVE_TICKS = {}

LIVE_LOCK = threading.Lock()

LIVE_WS = None
LIVE_WS_THREAD = None
LIVE_WS_STARTED = False
LIVE_WS_SYMBOL = None


# ============================================================
# WEBSOCKET CALLBACKS
# ============================================================

def websocket_on_data(wsapp, message):

    try:

        if not isinstance(message, dict):
            return

        token = str(
            message.get(
                "token",
                "",
            )
        )

        raw_ltp = message.get(
            "last_traded_price"
        )

        if raw_ltp is None:
            return

        ltp = float(
            raw_ltp
        ) / 100.0

        with LIVE_LOCK:

            LIVE_LTP[token] = ltp
            LIVE_TICKS[token] = message

    except Exception:

        pass


def websocket_on_error(wsapp, error):

    pass


def websocket_on_close(wsapp):

    pass


# ============================================================
# START WEBSOCKET
# ============================================================

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

    if not all(
        credentials.values()
    ):
        return

    token = get_instrument_token(
        symbol
    )

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

        auth_token = session[
            "data"
        ]["jwtToken"]

        # ----------------------------------------------------
        # SAVE AUTH SESSION FOR OPTIONS ENGINE
        # ----------------------------------------------------

        st.session_state.angel_jwt_token = (
            auth_token
        )

        st.session_state.angel_api_key = (
            credentials["api_key"]
        )

        st.session_state.angel_client_code = (
            credentials["client_code"]
        )

        feed_token = (
            smart_api.getfeedToken()
        )

        LIVE_WS = SmartWebSocketV2(
            auth_token,
            credentials["api_key"],
            credentials["client_code"],
            feed_token,
        )

        exchange_type = (
            INSTRUMENTS[symbol][
                "exchange_type"
            ]
        )

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

    if not all(
        credentials.values()
    ):

        return (
            None,
            "Angel One credentials incomplete."
        )

    token = get_instrument_token(
        symbol
    )

    if not token:

        return (
            None,
            f"{symbol} token is not configured."
        )

    try:

        engine = TelemetryEngine(
            api_key=credentials["api_key"],
            client_code=credentials["client_code"],
            pin=credentials["pin"],
            totp_secret=credentials["totp_secret"],
        )

        df = engine.fetch_ohlcv(
            exchange=INSTRUMENTS[
                symbol
            ]["exchange"],
            token=token,
            interval=interval,
            days=5,
        )

        if (
            df is None
            or df.empty
        ):

            return (
                None,
                "No candle data received."
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
                    f"Missing column: {column}"
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

        return (
            df,
            None
        )

    except Exception as e:

        return (
            None,
            str(e)
        )


# ============================================================
# APPLY LIVE PRICE
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

        price = float(
            live_ltp
        )

        idx = live_df.index[-1]

        old_high = float(
            live_df.loc[
                idx,
                "high",
            ]
        )

        old_low = float(
            live_df.loc[
                idx,
                "low",
            ]
        )

        live_df.loc[
            idx,
            "close",
        ] = price

        live_df.loc[
            idx,
            "high",
        ] = max(
            old_high,
            price,
        )

        live_df.loc[
            idx,
            "low",
        ] = min(
            old_low,
            price,
        )

        return live_df

    except Exception:

        return df


# ============================================================
# SHORT REASON
# ============================================================

def short_reason(reason):

    if not reason:

        return "Market conditions are unclear."

    reason = str(
        reason
    ).replace(
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

        response_text = (
            response.text.strip()
        )

        response_text = (
            response_text.replace(
                "```json",
                "",
            )
        )

        response_text = (
            response_text.replace(
                "```",
                "",
            )
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
                "Gemini error: "
                + str(e)
            ),
        }


# ============================================================
# PAPER LEVELS
# ============================================================

def calculate_levels(
    signal,
    atr,
    live_ltp,
):

    try:

        price = float(
            live_ltp
        )

    except Exception:

        price = 0

    try:

        atr = float(
            atr
        )

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
# OPTIONS ENGINE
# ============================================================

def get_options_engine():

    jwt_token = (
        st.session_state.get(
            "angel_jwt_token"
        )
    )

    api_key = (
        st.session_state.get(
            "angel_api_key"
        )
    )

    client_code = (
        st.session_state.get(
            "angel_client_code"
        )
    )

    if not all(
        [
            jwt_token,
            api_key,
            client_code,
        ]
    ):

        return None

    try:

        return OptionsEngine(
            jwt_token=jwt_token,
            api_key=api_key,
            client_code=client_code,
        )

    except Exception:

        return None


def refresh_options_data(
    symbol,
    expiry_date,
):

    if symbol == "SENSEX":

        return {
            "status": "UNAVAILABLE",
            "message": (
                "SmartAPI Option Greeks/PCR/OI APIs "
                "used here are NSE-focused."
            ),
            "greeks": pd.DataFrame(),
            "pcr": pd.DataFrame(),
            "oi": {},
        }

    if not expiry_date:

        return {
            "status": "WAITING",
            "message": (
                "Enter expiry date to load option Greeks."
            ),
            "greeks": pd.DataFrame(),
            "pcr": pd.DataFrame(),
            "oi": {},
        }

    engine = get_options_engine()

    if engine is None:

        return {
            "status": "WAITING",
            "message": (
                "Angel One session not ready."
            ),
            "greeks": pd.DataFrame(),
            "pcr": pd.DataFrame(),
            "oi": {},
        }

    underlying = (
        INSTRUMENTS[
            symbol
        ]["options_name"]
    )

    try:

        greeks = (
            engine.greeks_dataframe(
                underlying,
                expiry_date,
            )
        )

    except Exception as e:

        greeks = pd.DataFrame()

        greek_error = str(e)

    else:

        greek_error = ""

    try:

        pcr = (
            engine.pcr_dataframe()
        )

    except Exception:

        pcr = pd.DataFrame()

    try:

        oi = (
            engine.get_all_oi_buildup(
                expiry_type="NEAR"
            )
        )

    except Exception:

        oi = {}

    if (
        greeks.empty
        and greek_error
    ):

        message = (
            "Greeks unavailable: "
            + greek_error
        )

    else:

        message = "Options data refreshed."

    return {
        "status": "OK",
        "message": message,
        "greeks": greeks,
        "pcr": pcr,
        "oi": oi,
    }


# ============================================================
# OPTIONS ANALYSIS
# ============================================================

def build_options_summary(
    greeks,
    pcr,
    oi,
    spot_price,
):

    result = {
        "atm": None,
        "call_count": 0,
        "put_count": 0,
        "avg_call_iv": None,
        "avg_put_iv": None,
        "pcr": None,
        "oi_bias": "UNAVAILABLE",
    }

    if (
        greeks is not None
        and not greeks.empty
        and "strikePrice" in greeks.columns
    ):

        work = greeks.copy()

        work["distance"] = (
            work["strikePrice"]
            - float(spot_price)
        ).abs()

        work = work.sort_values(
            "distance"
        )

        if not work.empty:

            result["atm"] = float(
                work.iloc[0][
                    "strikePrice"
                ]
            )

        if "optionType" in work.columns:

            result["call_count"] = int(
                (
                    work["optionType"]
                    .astype(str)
                    .str.upper()
                    == "CE"
                ).sum()
            )

            result["put_count"] = int(
                (
                    work["optionType"]
                    .astype(str)
                    .str.upper()
                    == "PE"
                ).sum()
            )

        if (
            "impliedVolatility"
            in work.columns
        ):

            calls = work[
                work["optionType"]
                .astype(str)
                .str.upper()
                == "CE"
            ]

            puts = work[
                work["optionType"]
                .astype(str)
                .str.upper()
                == "PE"
            ]

            if not calls.empty:

                result["avg_call_iv"] = float(
                    calls[
                        "impliedVolatility"
                    ].mean()
                )

            if not puts.empty:

                result["avg_put_iv"] = float(
                    puts[
                        "impliedVolatility"
                    ].mean()
                )

    if (
        pcr is not None
        and not pcr.empty
        and "pcr" in pcr.columns
    ):

        pcr_values = pd.to_numeric(
            pcr["pcr"],
            errors="coerce",
        ).dropna()

        if not pcr_values.empty:

            result["pcr"] = float(
                pcr_values.mean()
            )

    if oi:

        counts = {
            "Long Built Up": 0,
            "Short Built Up": 0,
            "Short Covering": 0,
            "Long Unwinding": 0,
        }

        for key in counts:

            data = oi.get(
                key,
                []
            )

            if data:

                counts[key] = len(
                    data
                )

        if counts[
            "Long Built Up"
        ] > counts[
            "Short Built Up"
        ]:

            result["oi_bias"] = (
                "LONG BUILDUP"
            )

        elif counts[
            "Short Built Up"
        ] > counts[
            "Long Built Up"
        ]:

            result["oi_bias"] = (
                "SHORT BUILDUP"
            )

        elif counts[
            "Short Covering"
        ] > counts[
            "Long Unwinding"
        ]:

            result["oi_bias"] = (
                "SHORT COVERING"
            )

        elif counts[
            "Long Unwinding"
        ] > counts[
            "Short Covering"
        ]:

            result["oi_bias"] = (
                "LONG UNWINDING"
            )

    return result


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_AI = {
    "signal": "NO_TRADE",
    "confidence": 0,
    "reason": "Waiting for AI analysis.",
}


if "last_df" not in st.session_state:

    st.session_state.last_df = None


if "last_market_fetch" not in st.session_state:

    st.session_state.last_market_fetch = 0.0


if "last_indicator_update" not in st.session_state:

    st.session_state.last_indicator_update = 0.0


if "last_advanced_update" not in st.session_state:

    st.session_state.last_advanced_update = 0.0


if "live_indicators" not in st.session_state:

    st.session_state.live_indicators = {}


if "advanced" not in st.session_state:

    st.session_state.advanced = {}


if "ai_result" not in st.session_state:

    st.session_state.ai_result = (
        DEFAULT_AI.copy()
    )


if "last_ai_time" not in st.session_state:

    st.session_state.last_ai_time = 0.0


if "ai_blocked_until" not in st.session_state:

    st.session_state.ai_blocked_until = 0.0


if "angel_jwt_token" not in st.session_state:

    st.session_state.angel_jwt_token = None


if "angel_api_key" not in st.session_state:

    st.session_state.angel_api_key = None


if "angel_client_code" not in st.session_state:

    st.session_state.angel_client_code = None


if "options_data" not in st.session_state:

    st.session_state.options_data = {
        "status": "WAITING",
        "message": "Waiting for options data.",
        "greeks": pd.DataFrame(),
        "pcr": pd.DataFrame(),
        "oi": {},
    }


if "last_options_time" not in st.session_state:

    st.session_state.last_options_time = 0.0


# ============================================================
# SIDEBAR
# ============================================================

symbol = st.sidebar.selectbox(
    "Instrument",
    list(
        INSTRUMENTS.keys()
    ),
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


# ============================================================
# OPTIONS SETTINGS
# ============================================================

st.sidebar.markdown("---")

st.sidebar.subheader(
    "⚙️ Options Analysis"
)

expiry_date = st.sidebar.text_input(
    "Expiry Date",
    value="",
    placeholder="Example: 29SEP2026",
    help="Format: DDMMMYYYY, e.g. 29SEP2026",
)

options_interval = st.sidebar.slider(
    "Options Refresh",
    30,
    300,
    60,
    step=30,
)


st.sidebar.caption(
    "⚡ LTP target: near-live"
)

st.sidebar.caption(
    "📊 Indicators update every 5 seconds"
)

st.sidebar.caption(
    "🤖 Gemini calls are throttled"
)

st.sidebar.caption(
    "📊 Options APIs are throttled"
)

st.sidebar.caption(
    "🔒 Real orders are disabled"
)


# ============================================================
# START LIVE FEED
# ============================================================

start_websocket(
    symbol
)


# ============================================================
# INITIAL MARKET FETCH
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

        st.session_state.last_market_fetch = (
            now
        )

    elif st.session_state.last_df is None:

        st.error(
            error
            or "Market data unavailable."
        )

        st.stop()


df = st.session_state.last_df


if (
    df is None
    or df.empty
):

    st.warning(
        "Waiting for market data..."
    )

    st.stop()


# ============================================================
# INITIAL LTP
# ============================================================

token = get_instrument_token(
    symbol
)

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
            initial_live_df
        )
    )

    indicators["ltp"] = float(
        initial_ltp
    )

    st.session_state.live_indicators = (
        indicators
    )

    st.session_state.last_indicator_update = (
        time.time()
    )

except Exception as e:

    st.error(
        "Indicator error: "
        + str(e)
    )

    st.stop()


# ============================================================
# INITIAL ADVANCED ANALYSIS
# ============================================================

try:

    advanced = (
        build_advanced_analysis(
            initial_live_df
        )
    )

    st.session_state.advanced = (
        advanced
    )

    st.session_state.last_advanced_update = (
        time.time()
    )

except Exception:

    st.session_state.advanced = {}


# ============================================================
# INITIAL OPTIONS DATA
# ============================================================

if (
    expiry_date
    and (
        time.time()
        - st.session_state.last_options_time
        >= options_interval
    )
):

    st.session_state.options_data = (
        refresh_options_data(
            symbol,
            expiry_date.strip().upper(),
        )
    )

    st.session_state.last_options_time = (
        time.time()
    )


# ============================================================
# LIVE MARKET
# ============================================================

st.subheader(
    "📊 Live Market"
)

live_columns = st.columns(4)


with live_columns[0]:

    st.markdown(
        """
        <div class="live-box">
            <div class="live-label">LTP</div>
        """,
        unsafe_allow_html=True,
    )

    ltp_placeholder = st.empty()

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


with live_columns[1]:

    st.markdown(
        """
        <div class="live-box">
            <div class="live-label">RSI</div>
        """,
        unsafe_allow_html=True,
    )

    rsi_placeholder = st.empty()

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


with live_columns[2]:

    st.markdown(
        """
        <div class="live-box">
            <div class="live-label">ADX</div>
        """,
        unsafe_allow_html=True,
    )

    adx_placeholder = st.empty()

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


with live_columns[3]:

    st.markdown(
        """
        <div class="live-box">
            <div class="live-label">ATR</div>
        """,
        unsafe_allow_html=True,
    )

    atr_placeholder = st.empty()

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


# ============================================================
# PAPER LEVELS
# ============================================================

st.subheader(
    "🎯 Paper Trade Levels"
)

level_columns = st.columns(4)


with level_columns[0]:

    st.markdown(
        """
        <div class="live-box">
            <div class="live-label">Entry</div>
        """,
        unsafe_allow_html=True,
    )

    entry_placeholder = st.empty()

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


with level_columns[1]:

    st.markdown(
        """
        <div class="live-box">
            <div class="live-label">Stop Loss</div>
        """,
        unsafe_allow_html=True,
    )

    sl_placeholder = st.empty()

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


with level_columns[2]:

    st.markdown(
        """
        <div class="live-box">
            <div class="live-label">Target 1</div>
        """,
        unsafe_allow_html=True,
    )

    target1_placeholder = st.empty()

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


with level_columns[3]:

    st.markdown(
        """
        <div class="live-box">
            <div class="live-label">Target 2</div>
        """,
        unsafe_allow_html=True,
    )

    target2_placeholder = st.empty()

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


# ============================================================
# AI SIGNAL
# ============================================================

st.subheader(
    "🤖 AI Trading Signal"
)

signal_placeholder = st.empty()

confidence_placeholder = st.empty()

reason_placeholder = st.empty()


# ============================================================
# TECHNICAL
# ============================================================

st.subheader(
    "📐 Technical Indicators"
)

technical_placeholder = st.empty()


# ============================================================
# ADVANCED
# ============================================================

st.subheader(
    "🧠 Advanced Market Analysis — Phase 1"
)

advanced_placeholder = st.empty()


# ============================================================
# OPTIONS DASHBOARD
# ============================================================

st.subheader(
    "📊 Options Intelligence"
)

options_status_placeholder = st.empty()

options_metrics = st.columns(5)

with options_metrics[0]:

    atm_placeholder = st.empty()

with options_metrics[1]:

    call_count_placeholder = st.empty()

with options_metrics[2]:

    put_count_placeholder = st.empty()

with options_metrics[3]:

    pcr_placeholder = st.empty()

with options_metrics[4]:

    oi_bias_placeholder = st.empty()


greeks_placeholder = st.empty()

oi_placeholder = st.empty()


# ============================================================
# INITIAL PLACEHOLDERS
# ============================================================

for placeholder in [
    ltp_placeholder,
    rsi_placeholder,
    adx_placeholder,
    atr_placeholder,
    entry_placeholder,
    sl_placeholder,
    target1_placeholder,
    target2_placeholder,
]:

    placeholder.markdown(
        '<div class="live-value">—</div>',
        unsafe_allow_html=True,
    )


signal_placeholder.markdown(
    """
    <div class="signal-box">
        <div class="signal-title">Current Signal</div>
        <div class="signal-value">
            🟡 NO TRADE
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

confidence_placeholder.markdown(
    "**AI Confidence:** —"
)

reason_placeholder.markdown(
    """
    <div class="reason-box">
        <b>AI Reason:</b>
        Waiting for AI analysis.
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# LIVE FRAGMENT
# ============================================================

@st.fragment(
    run_every=1
)
def live_market():

    current_time = time.time()

    # --------------------------------------------------------
    # TOKEN
    # --------------------------------------------------------

    token_now = get_instrument_token(
        symbol
    )

    # --------------------------------------------------------
    # LIVE LTP
    # --------------------------------------------------------

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

    current_ltp = float(
        current_ltp
    )

    # --------------------------------------------------------
    # LIVE CANDLE
    # --------------------------------------------------------

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

            fresh_indicators = (
                engine.calculate_indicators(
                    live_df
                )
            )

            fresh_indicators["ltp"] = (
                current_ltp
            )

            st.session_state.live_indicators = (
                fresh_indicators
            )

            st.session_state.last_indicator_update = (
                current_time
            )

        except Exception:

            pass

    else:

        st.session_state.live_indicators[
            "ltp"
        ] = current_ltp

    # --------------------------------------------------------
    # ADVANCED
    # --------------------------------------------------------

    if (
        current_time
        - st.session_state.last_advanced_update
        >= 5
    ):

        try:

            fresh_advanced = (
                build_advanced_analysis(
                    live_df
                )
            )

            st.session_state.advanced = (
                fresh_advanced
            )

            st.session_state.last_advanced_update = (
                current_time
            )

        except Exception:

            pass

    # --------------------------------------------------------
    # OPTIONS
    # --------------------------------------------------------

    if (
        expiry_date
        and (
            current_time
            - st.session_state.last_options_time
            >= options_interval
        )
    ):

        try:

            st.session_state.options_data = (
                refresh_options_data(
                    symbol,
                    expiry_date.strip().upper(),
                )
            )

            st.session_state.last_options_time = (
                current_time
            )

        except Exception as e:

            st.session_state.options_data = {
                "status": "ERROR",
                "message": str(e),
                "greeks": pd.DataFrame(),
                "pcr": pd.DataFrame(),
                "oi": {},
            }

    # --------------------------------------------------------
    # CURRENT DATA
    # --------------------------------------------------------

    indicators_now = (
        st.session_state.live_indicators
    )

    advanced_now = (
        st.session_state.advanced
    )

    try:

        atr = float(
            indicators_now.get(
                "atr",
                0,
            )
        )

    except Exception:

        atr = 0

    # --------------------------------------------------------
    # GEMINI
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

        if (
            ai_due
            and not quota_blocked
        ):

            result = call_gemini(
                indicators_now,
                advanced_now,
                symbol,
                interval,
            )

            st.session_state.ai_result = (
                result
            )

            st.session_state.last_ai_time = (
                current_time
            )

            reason_text = str(
                result.get(
                    "reason",
                    "",
                )
            )

            if (
                "429" in reason_text
                or "RESOURCE_EXHAUSTED"
                in reason_text
            ):

                st.session_state.ai_blocked_until = (
                    current_time + 900
                )

    else:

        st.session_state.ai_result = {
            "signal": "NO_TRADE",
            "confidence": 0,
            "reason": "Technical Only mode.",
        }

    # --------------------------------------------------------
    # AI RESULT
    # --------------------------------------------------------

    ai_result = (
        st.session_state.ai_result
    )

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

    # --------------------------------------------------------
    # LEVELS
    # --------------------------------------------------------

    levels = calculate_levels(
        signal,
        atr,
        current_ltp,
    )

    # ========================================================
    # LIVE VALUES
    # ========================================================

    ltp_placeholder.markdown(
        f"""
        <div class="live-value">
            {current_ltp:,.2f}
        </div>
        """,
        unsafe_allow_html=True,
    )

    rsi_placeholder.markdown(
        f"""
        <div class="live-value">
            {float(indicators_now.get("rsi", 0)):.2f}
        </div>
        """,
        unsafe_allow_html=True,
    )

    adx_placeholder.markdown(
        f"""
        <div class="live-value">
            {float(indicators_now.get("adx", 0)):.2f}
        </div>
        """,
        unsafe_allow_html=True,
    )

    atr_placeholder.markdown(
        f"""
        <div class="live-value">
            {atr:.2f}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # PAPER LEVELS
    # --------------------------------------------------------

    if signal in {
        "ENTER_LONG",
        "ENTER_SHORT",
    }:

        entry_placeholder.markdown(
            f"""
            <div class="live-value">
                {levels["entry"]:,.2f}
            </div>
            """,
            unsafe_allow_html=True,
        )

        sl_placeholder.markdown(
            f"""
            <div class="live-value">
                {levels["sl"]:,.2f}
            </div>
            """,
            unsafe_allow_html=True,
        )

        target1_placeholder.markdown(
            f"""
            <div class="live-value">
                {levels["target1"]:,.2f}
            </div>
            """,
            unsafe_allow_html=True,
        )

        target2_placeholder.markdown(
            f"""
            <div class="live-value">
                {levels["target2"]:,.2f}
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:

        for placeholder in [
            entry_placeholder,
            sl_placeholder,
            target1_placeholder,
            target2_placeholder,
        ]:

            placeholder.markdown(
                '<div class="live-value">—</div>',
                unsafe_allow_html=True,
            )

    # --------------------------------------------------------
    # SIGNAL
    # --------------------------------------------------------

    if signal == "ENTER_LONG":

        signal_text = (
            "🟢 ENTER LONG — PAPER ONLY"
        )

    elif signal == "ENTER_SHORT":

        signal_text = (
            "🔴 ENTER SHORT — PAPER ONLY"
        )

    else:

        signal_text = "🟡 NO TRADE"

    signal_placeholder.markdown(
        f"""
        <div class="signal-box">
            <div class="signal-title">
                Current Signal
            </div>
            <div class="signal-value">
                {signal_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    confidence_placeholder.markdown(
        f"**AI Confidence:** {confidence:.1f}%"
    )

    reason_placeholder.markdown(
        f"""
        <div class="reason-box">
            <b>AI Reason:</b> {reason}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # TECHNICAL TABLE
    # --------------------------------------------------------

    technical = {

        "LTP": indicators_now.get(
            "ltp"
        ),

        "RSI": indicators_now.get(
            "rsi"
        ),

        "VWAP": indicators_now.get(
            "vwap"
        ),

        "ADX": indicators_now.get(
            "adx"
        ),

        "ATR": indicators_now.get(
            "atr"
        ),

        "EMA Trend": indicators_now.get(
            "ema_trend"
        ),

        "Supertrend": indicators_now.get(
            "supertrend"
        ),

        "VWAP Position": indicators_now.get(
            "price_vs_vwap"
        ),

        "Market Regime": indicators_now.get(
            "market_regime"
        ),
    }

    technical_html = (
        pd.DataFrame(
            [technical]
        ).to_html(
            index=False,
            border=0,
            justify="center",
        )
    )

    technical_placeholder.markdown(
        technical_html,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # ADVANCED
    # --------------------------------------------------------

    if (
        advanced_now.get(
            "status"
        )
        == "OK"
    ):

        patterns = advanced_now.get(
            "candlestick_patterns",
            [],
        )

        if patterns:

            pattern_text = "<br>".join(
                [
                    "• " + str(p)
                    for p in patterns
                ]
            )

        else:

            pattern_text = (
                "No confirmed pattern."
            )

        macd = advanced_now.get(
            "macd",
            {},
        )

        ema = advanced_now.get(
            "ema_200",
            {},
        )

        sr = advanced_now.get(
            "support_resistance",
            {},
        )

        volume = advanced_now.get(
            "volume",
            {},
        )

        structure = advanced_now.get(
            "market_structure",
            {},
        )

        advanced_html = f"""
        <div style="padding:4px 0;">

        <b>🕯️ Candlestick</b><br>
        {pattern_text}

        <br><br>

        <b>📈 MACD</b><br>
        Value: {float(macd.get("value", 0)):.4f}<br>
        Signal: {float(macd.get("signal", 0)):.4f}<br>
        Bias: <b>{macd.get("bias", "UNKNOWN")}</b>

        <br><br>

        <b>📊 EMA 200</b><br>
        EMA 200: {float(ema.get("value", 0)):.2f}<br>
        Position: <b>{ema.get("position", "UNKNOWN")}</b>

        <br><br>

        <b>🧱 Support / Resistance</b><br>
        Support: {float(sr.get("support", 0)):.2f}<br>
        Resistance: {float(sr.get("resistance", 0)):.2f}

        <br><br>

        <b>📦 Volume</b><br>
        Volume Ratio: {float(volume.get("ratio", 0)):.2f}x<br>
        Signal: <b>{volume.get("signal", "UNKNOWN")}</b>

        <br><br>

        <b>🧭 Market Structure</b><br>
        Structure: <b>{structure.get("structure", "UNKNOWN")}</b><br>
        Bias: <b>{structure.get("bias", "UNKNOWN")}</b><br>
        Momentum: <b>{structure.get("momentum", "UNKNOWN")}</b>

        </div>
        """

        advanced_placeholder.markdown(
            advanced_html,
            unsafe_allow_html=True,
        )

    else:

        advanced_placeholder.info(
            "Advanced analysis waiting for data."
        )

    # ========================================================
    # OPTIONS DASHBOARD
    # ========================================================

    options_data = (
        st.session_state.options_data
    )

    options_status_placeholder.info(
        options_data.get(
            "message",
            "Waiting for options data.",
        )
    )

    greeks = options_data.get(
        "greeks",
        pd.DataFrame(),
    )

    pcr = options_data.get(
        "pcr",
        pd.DataFrame(),
    )

    oi = options_data.get(
        "oi",
        {},
    )

    options_summary = (
        build_options_summary(
            greeks,
            pcr,
            oi,
            current_ltp,
        )
    )

    atm = options_summary.get(
        "atm"
    )

    call_count = options_summary.get(
        "call_count",
        0,
    )

    put_count = options_summary.get(
        "put_count",
        0,
    )

    pcr_value = options_summary.get(
        "pcr"
    )

    oi_bias = options_summary.get(
        "oi_bias",
        "UNAVAILABLE",
    )

    atm_placeholder.metric(
        "ATM Strike",
        (
            f"{atm:.0f}"
            if atm is not None
            else "—"
        ),
    )

    call_count_placeholder.metric(
        "CE Rows",
        call_count,
    )

    put_count_placeholder.metric(
        "PE Rows",
        put_count,
    )

    pcr_placeholder.metric(
        "PCR",
        (
            f"{pcr_value:.2f}"
            if pcr_value is not None
            else "—"
        ),
    )

    oi_bias_placeholder.metric(
        "OI Bias",
        oi_bias,
    )

    # --------------------------------------------------------
    # GREEKS TABLE
    # --------------------------------------------------------

    if (
        greeks is not None
        and not greeks.empty
    ):

        display_columns = [
            "name",
            "expiry",
            "strikePrice",
            "optionType",
            "delta",
            "gamma",
            "theta",
            "vega",
            "impliedVolatility",
            "tradeVolume",
        ]

        available_columns = [
            c
            for c in display_columns
            if c in greeks.columns
        ]

        greek_display = (
            greeks[
                available_columns
            ].copy()
        )

        if "strikePrice" in greek_display.columns:

            greek_display[
                "strikePrice"
            ] = pd.to_numeric(
                greek_display[
                    "strikePrice"
                ],
                errors="coerce",
            )

            greek_display[
                "distance"
            ] = (
                greek_display[
                    "strikePrice"
                ]
                - current_ltp
            ).abs()

            greek_display = (
                greek_display
                .sort_values(
                    "distance"
                )
                .head(20)
            )

            greek_display = (
                greek_display.drop(
                    columns=[
                        "distance"
                    ],
                    errors="ignore",
                )
            )

        greeks_placeholder.markdown(
            "### 🧮 Option Greeks — Near ATM"
        )

        greeks_placeholder.dataframe(
            greek_display,
            use_container_width=True,
            hide_index=True,
        )

    else:

        greeks_placeholder.info(
            "Option Greeks data unavailable or expiry not entered."
        )

    # --------------------------------------------------------
    # OI BUILDUP
    # --------------------------------------------------------

    if oi:

        oi_rows = []

        for buildup_type, rows in oi.items():

            if not rows:
                continue

                        if isinstance(rows, dict):

                normalized_rows = (
                    rows.get("data")
                    or rows.get("result")
                    or []
                )

                if isinstance(normalized_rows, dict):
                    normalized_rows = [
                        normalized_rows
                    ]

            elif isinstance(rows, (list, tuple)):

                normalized_rows = rows

            else:

                normalized_rows = []

            for row in normalized_rows[:10]:

                if not isinstance(row, dict):
                    continue

                item = dict(row)

                item[
                    "buildup_type"
                ] = buildup_type

                oi_rows.append(
                    item
                )

        if oi_rows:

            oi_df = pd.DataFrame(
                oi_rows
            )

            oi_placeholder.markdown(
                "### 📊 OI Buildup — Near Expiry"
            )

            oi_placeholder.dataframe(
                oi_df,
                use_container_width=True,
                hide_index=True,
            )

        else:

            oi_placeholder.info(
                "No OI buildup data returned."
            )

    else:

        oi_placeholder.info(
            "OI buildup data unavailable."
        )


# ============================================================
# RUN LIVE FRAGMENT
# ============================================================

live_market()


# ============================================================
# RECENT CANDLES
# ============================================================

st.subheader(
    "🕯️ Recent Market Candles"
)

st.dataframe(
    initial_live_df.tail(20),
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# SYSTEM STATUS
# ============================================================

st.subheader(
    "🛡️ System Status"
)

c1, c2, c3, c4 = st.columns(4)


with c1:

    st.write(
        "**Trading Mode**"
    )

    st.write(
        "PAPER"
    )


with c2:

    st.write(
        "**Market**"
    )

    st.write(
        INSTRUMENTS[
            symbol
        ]["exchange"]
    )


with c3:

    st.write(
        "**Advanced Analysis**"
    )

    st.write(
        "ACTIVE"
    )


with c4:

    st.write(
        "**Real Orders**"
    )

    st.write(
        "DISABLED"
    )


st.caption(
    "🔒 Safety Lock: No real broker orders are placed."
)

st.caption(
    "⚡ Angel One WebSocket live feed active."
)

st.caption(
    "📊 Options Greeks / PCR / OI data are API-dependent and shown only when returned by SmartAPI."
)
