import os
import json
import time
from datetime import date

import streamlit as st
import pandas as pd

from SmartApi import SmartConnect
from google import genai

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


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Trading Bot",
    page_icon="📈",
    layout="wide",
)

st.title("📈 AI Trading Bot")
st.caption(
    "Live Market Analysis • Options Intelligence • Paper Trading"
)


# ============================================================
# SAFETY LOCK
# ============================================================

if PAPER_TRADING is not True:
    st.error(
        "🚨 SAFETY LOCK: PAPER_TRADING must remain True."
    )
    st.stop()

st.success(
    "🛡️ PAPER TRADING MODE — REAL ORDERS DISABLED"
)


# ============================================================
# SECRET HELPER
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


# ============================================================
# CREDENTIALS
# ============================================================

def get_credentials():

    return {
        "api_key": get_secret(
            "SMARTAPI_API_KEY"
        ),
        "client_code": get_secret(
            "SMARTAPI_CLIENT_CODE"
        ),
        "pin": get_secret(
            "SMARTAPI_PIN"
        ),
        "totp_secret": get_secret(
            "SMARTAPI_TOTP_SECRET"
        ),
    }


def get_gemini_key():

    return get_secret(
        "GEMINI_API_KEY"
    )


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {
    "smart_api": None,
    "telemetry": None,
    "jwt_token": None,
    "feed_token": None,
    "api_key": None,
    "client_code": None,

    "connected": False,

    "last_df": pd.DataFrame(),

    "last_error": "",

    "ai_result": {
        "signal": "NO_TRADE",
        "confidence": 0,
        "reason": "Waiting for analysis.",
    },

    "last_ai_time": 0,

    "options_engine": None,

    "options_expiries": [],

    "options_chain": pd.DataFrame(),

    "options_greeks": pd.DataFrame(),

    "options_pcr": pd.DataFrame(),

    "options_oi": {},

    "last_options_time": 0,
}


for key, value in DEFAULTS.items():

    if key not in st.session_state:

        st.session_state[key] = value


# ============================================================
# ANGEL ONE LOGIN
# ============================================================

def login_angel():

    credentials = get_credentials()

    required = [
        credentials["api_key"],
        credentials["client_code"],
        credentials["pin"],
        credentials["totp_secret"],
    ]

    if not all(required):

        return (
            False,
            "Angel One credentials are missing.",
        )

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

            return (
                False,
                f"Angel login failed: {session}",
            )

        data = session.get(
            "data"
        ) or {}

        jwt_token = data.get(
            "jwtToken"
        )

        if not jwt_token:

            return (
                False,
                "JWT token missing from Angel One response.",
            )

        try:

            feed_token = (
                smart_api.getfeedToken()
            )

        except Exception:

            feed_token = None

        st.session_state.smart_api = smart_api
        st.session_state.jwt_token = jwt_token
        st.session_state.feed_token = feed_token
        st.session_state.api_key = credentials["api_key"]
        st.session_state.client_code = credentials["client_code"]
        st.session_state.connected = True

        return True, ""

    except Exception as e:

        return (
            False,
            str(e),
        )


# ============================================================
# TELEMETRY LOGIN
# ============================================================

def ensure_connection():

    if (
        st.session_state.telemetry
        is not None
    ):

        return True

    credentials = get_credentials()

    required = [
        credentials["api_key"],
        credentials["client_code"],
        credentials["pin"],
        credentials["totp_secret"],
    ]

    if not all(required):

        st.session_state.last_error = (
            "Angel One credentials are not configured."
        )

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

        return True

    except Exception as e:

        st.session_state.connected = False
        st.session_state.last_error = str(e)

        return False


# ============================================================
# OPTIONS ENGINE
# ============================================================

def ensure_options_engine():

    if (
        st.session_state.options_engine
        is not None
    ):

        return (
            st.session_state.options_engine
        )

    if not st.session_state.jwt_token:

        ok, error = login_angel()

        if not ok:

            st.session_state.last_error = error

            return None

    try:

        engine = OptionsEngine(
            jwt_token=st.session_state.jwt_token,
            api_key=st.session_state.api_key,
            client_code=st.session_state.client_code,
        )

        st.session_state.options_engine = engine

        return engine

    except Exception as e:

        st.session_state.last_error = str(e)

        return None


# ============================================================
# FETCH CANDLES
# ============================================================

def fetch_market_data():

    if not ensure_connection():

        return None

    try:

        df = (
            st.session_state.telemetry.fetch_ohlcv(
                exchange=EXCHANGE,
                token=str(TOKEN),
                interval=CANDLE_INTERVAL,
                days=HISTORICAL_DAYS,
            )
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
# FETCH LIVE LTP
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

def apply_live_price(
    df,
    ltp,
):

    if df is None or df.empty:

        return df

    if ltp is None:

        return df

    result = df.copy()

    try:

        index = result.index[-1]

        result.loc[
            index,
            "close"
        ] = float(ltp)

        result.loc[
            index,
            "high"
        ] = max(
            float(
                result.loc[
                    index,
                    "high"
                ]
            ),
            float(ltp),
        )

        result.loc[
            index,
            "low"
        ] = min(
            float(
                result.loc[
                    index,
                    "low"
                ]
            ),
            float(ltp),
        )

    except Exception:

        pass

    return result


# ============================================================
# AI
# ============================================================

def short_reason(reason):

    if not reason:

        return "No clear setup."

    value = (
        str(reason)
        .replace("\n", " ")
        .strip()
    )

    if len(value) > 160:

        value = value[:157] + "..."

    return value


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
You are an AI market-analysis assistant.

PAPER TRADING ONLY.

Do not place real orders.

Use ONLY the supplied data.
Never invent news, VIX, OI, PCR, IV or Greeks.

Instrument:
{SYMBOL}

Current LTP:
{ltp}

Technical Indicators:
{indicators}

Advanced Analysis:
{advanced}

Return ONLY JSON.

Allowed signals:

ENTER_LONG
ENTER_SHORT
NO_TRADE

Confidence must be 0-100.

Reason must be short.

Example:

{{
    "signal": "ENTER_LONG",
    "confidence": 82,
    "reason": "Price is above VWAP with positive momentum."
}}
"""

    try:

        client = genai.Client(
            api_key=api_key
        )

        response = (
            client.models.generate_content(
                model=AI_MODEL,
                contents=prompt,
            )
        )

        raw = (
            response.text
            .strip()
        )

        raw = raw.replace(
            "```json",
            "",
        )

        raw = raw.replace(
            "```",
            "",
        )

        result = json.loads(
            raw.strip()
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

        if (
            confidence
            < MIN_AI_CONFIDENCE
        ):

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
# TRADE LEVELS
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
            "sl": price - 1.5 * atr_value,
            "target1": price + 2 * atr_value,
            "target2": price + 3 * atr_value,
        }

    if signal == "ENTER_SHORT":

        return {
            "entry": price,
            "sl": price + 1.5 * atr_value,
            "target1": price - 2 * atr_value,
            "target2": price - 3 * atr_value,
        }

    return {
        "entry": None,
        "sl": None,
        "target1": None,
        "target2": None,
    }


# ============================================================
# OPTION UNDERLYING
# ============================================================

OPTION_UNDERLYINGS = {
    "NIFTY": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
}


# ============================================================
# OPTION EXPIRIES
# ============================================================

def load_option_expiries(
    underlying,
):

    engine = ensure_options_engine()

    if engine is None:

        return []

    try:

        expiries = (
            engine.get_expiries(
                underlying
            )
        )

        return expiries or []

    except Exception as e:

        st.session_state.last_error = str(e)

        return []


# ============================================================
# OPTION CHAIN
# ============================================================

def load_option_chain(
    underlying,
    expiry,
    spot,
    strikes_each_side,
):

    engine = ensure_options_engine()

    if engine is None:

        return pd.DataFrame()

    try:

        chain = (
            engine.get_option_chain(
                underlying=underlying,
                expiry_date=expiry,
                spot_price=float(spot),
                strikes_each_side=int(
                    strikes_each_side
                ),
            )
        )

        if chain is None:

            return pd.DataFrame()

        return chain

    except Exception as e:

        st.session_state.last_error = str(e)

        return pd.DataFrame()


# ============================================================
# OPTION GREEKS
# ============================================================

def load_option_greeks(
    underlying,
    expiry,
):

    engine = ensure_options_engine()

    if engine is None:

        return pd.DataFrame()

    try:

        df = (
            engine.greeks_dataframe(
                underlying=underlying,
                expiry_date=expiry,
            )
        )

        if df is None:

            return pd.DataFrame()

        return df

    except Exception as e:

        st.session_state.last_error = str(e)

        return pd.DataFrame()


# ============================================================
# PCR
# ============================================================

def load_pcr():

    engine = ensure_options_engine()

    if engine is None:

        return pd.DataFrame()

    try:

        df = engine.pcr_dataframe()

        if df is None:

            return pd.DataFrame()

        return df

    except Exception as e:

        st.session_state.last_error = str(e)

        return pd.DataFrame()


# ============================================================
# OI BUILDUP
# ============================================================

def load_oi_buildup():

    engine = ensure_options_engine()

    if engine is None:

        return {}

    try:

        result = (
            engine.get_all_oi_buildup(
                expiry_type="NEAR"
            )
        )

        return result or {}

    except Exception as e:

        st.session_state.last_error = str(e)

        return {}


# ============================================================
# OPTION DISPLAY FORMAT
# ============================================================

def prepare_option_chain(
    df,
):

    if df is None or df.empty:

        return pd.DataFrame()

    work = df.copy()

    rename_map = {
        "symbol": "Symbol",
        "name": "Underlying",
        "strike": "Strike",
        "option_type": "Type",
        "expiry": "Expiry",
        "token": "Token",
        "ltp": "LTP",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Prev Close",
        "tradeVolume": "Volume",
        "opnInterest": "OI",
        "totBuyQuan": "Buy Qty",
        "totSellQuan": "Sell Qty",
    }

    available = {
        key: value
        for key, value in rename_map.items()
        if key in work.columns
    }

    work = work.rename(
        columns=available
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

    columns = [
        column
        for column in preferred
        if column in work.columns
    ]

    if columns:

        work = work[
            columns
        ]

    return work


# ============================================================
# OPTION DASHBOARD
# ============================================================

def render_options_dashboard(
    spot_price,
):

    st.subheader(
        "📊 Live Options Intelligence"
    )

    st.caption(
        "Angel One SmartAPI option-chain data • "
        "No artificial/fake values"
    )

    c1, c2, c3 = st.columns(3)

    with c1:

        underlying = st.selectbox(
            "Underlying",
            [
                "NIFTY",
                "BANKNIFTY",
            ],
            key="option_underlying",
        )

    with c2:

        strikes_each_side = st.slider(
            "Strikes each side",
            min_value=3,
            max_value=10,
            value=5,
            key="option_strikes",
        )

    with c3:

        st.metric(
            "Spot / Reference",
            f"{spot_price:,.2f}",
        )

    if st.button(
        "🔄 Load / Refresh Options",
        key="load_options_button",
    ):

        st.session_state.options_expiries = (
            load_option_expiries(
                underlying
            )
        )

        st.session_state.options_chain = (
            pd.DataFrame()
        )

        st.session_state.options_greeks = (
            pd.DataFrame()
        )

        st.session_state.options_pcr = (
            pd.DataFrame()
        )

        st.session_state.options_oi = {}

    if not st.session_state.options_expiries:

        with st.spinner(
            "Loading available expiries..."
        ):

            st.session_state.options_expiries = (
                load_option_expiries(
                    underlying
                )
            )

    expiries = (
        st.session_state.options_expiries
    )

    if not expiries:

        st.warning(
            "No option expiries received from Angel One."
        )

        if st.session_state.last_error:

            st.code(
                st.session_state.last_error
            )

        return

    expiry = st.selectbox(
        "Expiry",
        expiries,
        key="selected_option_expiry",
    )

    if st.button(
        "📡 Fetch Live Option Data",
        key="fetch_live_options",
    ):

        with st.spinner(
            "Fetching live option-chain, Greeks, PCR and OI..."
        ):

            st.session_state.options_chain = (
                load_option_chain(
                    underlying=underlying,
                    expiry=expiry,
                    spot=spot_price,
                    strikes_each_side=strikes_each_side,
                )
            )

            st.session_state.options_greeks = (
                load_option_greeks(
                    underlying=underlying,
                    expiry=expiry,
                )
            )

            st.session_state.options_pcr = (
                load_pcr()
            )

            st.session_state.options_oi = (
                load_oi_buildup()
            )

            st.session_state.last_options_time = (
                time.time()
            )

    chain = (
        st.session_state.options_chain
    )

    greeks = (
        st.session_state.options_greeks
    )

    pcr = (
        st.session_state.options_pcr
    )

    oi = (
        st.session_state.options_oi
    )

    # --------------------------------------------------------
    # OPTION CHAIN
    # --------------------------------------------------------

    st.markdown(
        "### 🧾 CE / PE Option Chain"
    )

    display_chain = prepare_option_chain(
        chain
    )

    if display_chain.empty:

        st.info(
            "Option-chain data not loaded yet. "
            "Press 'Fetch Live Option Data'."
        )

    else:

        st.dataframe(
            display_chain,
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # CE / PE SUMMARY
    # --------------------------------------------------------

    if (
        chain is not None
        and not chain.empty
        and "option_type" in chain.columns
    ):

        calls = chain[
            chain["option_type"]
            .astype(str)
            .str.upper()
            == "CE"
        ].copy()

        puts = chain[
            chain["option_type"]
            .astype(str)
            .str.upper()
            == "PE"
        ].copy()

        st.markdown(
            "### 📌 CE / PE Summary"
        )

        c1, c2 = st.columns(2)

        with c1:

            st.write(
                "**CALLS (CE)**"
            )

            if not calls.empty:

                columns = [
                    column
                    for column in [
                        "strike",
                        "ltp",
                        "opnInterest",
                        "tradeVolume",
                    ]
                    if column in calls.columns
                ]

                st.dataframe(
                    calls[columns],
                    use_container_width=True,
                    hide_index=True,
                )

        with c2:

            st.write(
                "**PUTS (PE)**"
            )

            if not puts.empty:

                columns = [
                    column
                    for column in [
                        "strike",
                        "ltp",
                        "opnInterest",
                        "tradeVolume",
                    ]
                    if column in puts.columns
                ]

                st.dataframe(
                    puts[columns],
                    use_container_width=True,
                    hide_index=True,
                )

    # --------------------------------------------------------
    # GREEKS
    # --------------------------------------------------------

    st.markdown(
        "### 🧮 Option Greeks / IV"
    )

    if greeks is not None and not greeks.empty:

        greek_columns = [
            column
            for column in [
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
            if column in greeks.columns
        ]

        st.dataframe(
            greeks[greek_columns],
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "Greeks data not loaded yet."
        )

    # --------------------------------------------------------
    # PCR
    # --------------------------------------------------------

    st.markdown(
        "### 📊 Put-Call Ratio"
    )

    if pcr is not None and not pcr.empty:

        st.dataframe(
            pcr,
            use_container_width=True,
            hide_index=True,
        )

        if "pcr" in pcr.columns:

            valid_pcr = pcr["pcr"].dropna()

            if not valid_pcr.empty:

                latest_pcr = float(
                    valid_pcr.iloc[-1]
                )

                st.metric(
                    "Latest PCR",
                    f"{latest_pcr:.2f}",
                )

    else:

        st.info(
            "PCR data not loaded yet."
        )

    # --------------------------------------------------------
    # OI BUILDUP
    # --------------------------------------------------------

    st.markdown(
        "### 📈 OI Buildup"
    )

    if oi:

        for buildup_type, data in oi.items():

            st.write(
                f"**{buildup_type}**"
            )

            if data:

                oi_df = pd.DataFrame(
                    data
                )

                st.dataframe(
                    oi_df,
                    use_container_width=True,
                    hide_index=True,
                )

            else:

                st.caption(
                    "No data returned."
                )

    else:

        st.info(
            "OI buildup data not loaded yet."
        )

    if st.session_state.last_options_time:

        updated = time.strftime(
            "%H:%M:%S",
            time.localtime(
                st.session_state.last_options_time
            ),
        )

        st.caption(
            f"Last options update: {updated}"
        )


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "⚙️ Bot Settings"
)

st.sidebar.write(
    f"**Futures Symbol:** {SYMBOL}"
)

st.sidebar.write(
    f"**Exchange:** {EXCHANGE}"
)

st.sidebar.write(
    f"**Token:** {TOKEN}"
)

st.sidebar.write(
    f"**Candle:** {CANDLE_INTERVAL}"
)

st.sidebar.write(
    "**Mode:** PAPER TRADING"
)


# ============================================================
# LOGIN BUTTON
# ============================================================

if st.sidebar.button(
    "🔐 Connect Angel One",
):

    with st.spinner(
        "Connecting to Angel One..."
    ):

        ok, error = login_angel()

        if ok:

            st.session_state.connected = True

            st.sidebar.success(
                "Connected"
            )

        else:

            st.sidebar.error(
                error
            )


# ============================================================
# REFRESH MARKET DATA
# ============================================================

if st.sidebar.button(
    "🔄 Refresh Market Data",
):

    df = fetch_market_data()

    if df is not None:

        st.session_state.last_df = df

    st.rerun()


# ============================================================
# LOAD INITIAL MARKET DATA
# ============================================================

if st.session_state.last_df.empty:

    with st.spinner(
        "Loading market candles..."
    ):

        df = fetch_market_data()

        if df is not None:

            st.session_state.last_df = df


df = st.session_state.last_df


# ============================================================
# MARKET DATA ERROR
# ============================================================

if df.empty:

    st.warning(
        "Market candle data is not available yet."
    )

    if st.session_state.last_error:

        st.code(
            st.session_state.last_error
        )

    st.info(
        "Check SmartAPI credentials/secrets and token configuration."
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


# ============================================================
# ADVANCED ANALYSIS
# ============================================================

try:

    advanced = (
        build_advanced_analysis(
            live_df
        )
    )

except Exception as e:

    advanced = {
        "status": "ERROR",
        "error": str(e),
    }


# ============================================================
# AI
# ============================================================

current_time = time.time()

if (
    current_time
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

    st.session_state.last_ai_time = (
        current_time
    )


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


# ============================================================
# TOP MARKET METRICS
# ============================================================

st.subheader(
    "📊 Live Market"
)

c1, c2, c3, c4, c5 = st.columns(5)

with c1:

    st.write(
        "**Trading Mode**"
    )

    st.write(
        "PAPER"
    )

with c2:

    st.write(
        "**Real Orders**"
    )

    st.write(
        "DISABLED"
    )

with c3:

    st.write(
        "**Angel One**"
    )

    st.write(
        "CONNECTED"
        if st.session_state.connected
        else "NOT CONNECTED"
    )

with c4:

    st.write(
        "**Options Engine**"
    )

    st.write(
        "READY"
        if st.session_state.options_engine
        else "NOT INITIALIZED"
    )


# ============================================================
# LAST ERROR
# ============================================================

if st.session_state.last_error:

    with st.expander(
        "⚠️ Last system message"
    ):

        st.code(
            st.session_state.last_error
        )


# ============================================================
# SAFETY
# ============================================================

st.caption(
    "🔒 Safety Lock: Real trading orders are disabled."
)

st.caption(
    "📡 Option-chain values are requested from Angel One SmartAPI."
)

st.caption(
    "⚠️ Missing API fields are shown as unavailable; "
    "the application does not invent market data."
)
   
