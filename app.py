import os
import json
import time
import threading
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np

from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

try:
    from google import genai
except Exception:
    genai = None

from telemetry_engine import TelemetryEngine
from advanced_analysis import build_advanced_analysis
from options_engine import OptionsEngine

from config import (
    AI_MODEL,
    PAPER_TRADING,
    MIN_AI_CONFIDENCE,
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
st.caption("AI Market Research + Paper Trading Dashboard")

if PAPER_TRADING is not True:
    st.error("🚨 SAFETY LOCK: PAPER_TRADING must remain True.")
    st.stop()

st.info("🛡️ PAPER TRADING ONLY — NO REAL ORDERS")


# ============================================================
# CSS - MOBILE + NO ANIMATION
# ============================================================

st.markdown(
    """
    <style>

    * {
        animation: none !important;
        transition: none !important;
    }

    .metric-card {
        border: 1px solid rgba(128,128,128,0.30);
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 10px;
        min-height: 105px;
        overflow: hidden;
    }

    .metric-label {
        font-size: 13px;
        opacity: 0.70;
        margin-bottom: 7px;
        white-space: normal;
    }

    .metric-value {
        font-size: 25px;
        font-weight: 700;
        line-height: 1.20;
        white-space: normal !important;
        overflow-wrap: anywhere !important;
        word-break: break-word !important;
    }

    .signal-card {
        border: 1px solid rgba(128,128,128,0.35);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
    }

    .signal-value {
        font-size: 28px;
        font-weight: 800;
        overflow-wrap: anywhere;
    }

    .small-text {
        font-size: 13px;
        opacity: 0.75;
    }

    .status-box {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 8px;
    }

    @media (max-width: 768px) {

        .metric-value {
            font-size: 21px !important;
        }

        .signal-value {
            font-size: 24px !important;
        }

        .block-container {
            padding-left: 0.7rem;
            padding-right: 0.7rem;
        }

    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SECRET HELPERS
# ============================================================

def get_secret(name):

    value = os.getenv(name)

    if value:
        return str(value)

    try:
        value = st.secrets.get(name)

        if value:
            return str(value)

    except Exception:
        pass

    return None


def get_angel_credentials():

    return {
        "api_key": get_secret("ANGEL_API_KEY"),
        "client_code": get_secret("ANGEL_CLIENT_CODE"),
        "pin": get_secret("ANGEL_PIN"),
        "totp_secret": get_secret("ANGEL_TOTP_SECRET"),
    }


def get_gemini_key():

    return get_secret("GEMINI_API_KEY")


# ============================================================
# INSTRUMENT DEFINITIONS
# ============================================================

INSTRUMENTS = {
    "NIFTY 50": {
        "exchange": "NSE",
        "exchange_type": 1,
        "token_secret": "NIFTY_TOKEN",
        "default_token": "99926000",
        "options_name": "NIFTY",
        "tradingsymbol": "NIFTY",
    },

    "BANK NIFTY": {
        "exchange": "NSE",
        "exchange_type": 1,
        "token_secret": "BANKNIFTY_TOKEN",
        "default_token": "99926009",
        "options_name": "BANKNIFTY",
        "tradingsymbol": "BANKNIFTY",
    },

    "SENSEX": {
        "exchange": "BSE",
        "exchange_type": 3,
        "token_secret": "SENSEX_TOKEN",
        "default_token": None,
        "options_name": "SENSEX",
        "tradingsymbol": "SENSEX",
    },
}


def get_instrument_token(name):

    item = INSTRUMENTS[name]

    secret_token = get_secret(
        item["token_secret"]
    )

    if secret_token:
        return str(secret_token)

    return item["default_token"]


# ============================================================
# EQUITY MASTER
# ============================================================

SCRIP_MASTER_URL = (
    "https://margincalculator.angelone.in/"
    "OpenAPI_File/files/OpenAPIScripMaster.json"
)


@st.cache_data(ttl=3600, show_spinner=False)
def load_equity_master():

    try:

        import requests

        response = requests.get(
            SCRIP_MASTER_URL,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list):
            return pd.DataFrame()

        rows = []

        for item in data:

            if not isinstance(item, dict):
                continue

            exch_seg = str(
                item.get("exch_seg", "")
            ).upper()

            instrument_type = str(
                item.get("instrumenttype", "")
            ).upper()

            symbol = str(
                item.get("symbol", "")
            ).strip()

            token = str(
                item.get("token", "")
            ).strip()

            name = str(
                item.get("name", "")
            ).strip()

            if not symbol or not token:
                continue

            is_equity = (
                instrument_type == "EQ"
                or instrument_type == ""
            )

            if exch_seg in {"NSE", "BSE"} and is_equity:

                rows.append(
                    {
                        "exchange": exch_seg,
                        "symbol": symbol,
                        "name": name,
                        "token": token,
                        "instrumenttype": instrument_type,
                    }
                )

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        df = df.drop_duplicates(
            subset=[
                "exchange",
                "symbol",
                "token",
            ]
        )

        return df.sort_values(
            [
                "exchange",
                "symbol",
            ]
        ).reset_index(drop=True)

    except Exception:
        return pd.DataFrame()


# ============================================================
# LIVE WEBSOCKET STATE
# ============================================================

LIVE_LTP = {}
LIVE_TICKS = {}

LIVE_LOCK = threading.Lock()

LIVE_WS = None
LIVE_WS_THREAD = None
LIVE_WS_STARTED = False
LIVE_WS_KEY = None


# ============================================================
# WEBSOCKET CALLBACK
# ============================================================

def websocket_on_data(
    wsapp,
    message,
):

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

        price = float(
            raw_ltp
        ) / 100.0

        if price <= 0:
            return

        with LIVE_LOCK:

            LIVE_LTP[token] = price
            LIVE_TICKS[token] = message

    except Exception:
        pass


def websocket_on_error(
    wsapp,
    error,
):
    pass


def websocket_on_close(
    wsapp,
):
    pass


# ============================================================
# START WEBSOCKET
# ============================================================

def start_websocket(
    exchange_type,
    token,
    key,
):

    global LIVE_WS
    global LIVE_WS_THREAD
    global LIVE_WS_STARTED
    global LIVE_WS_KEY

    if not token:
        return False

    if (
        LIVE_WS_STARTED
        and LIVE_WS_KEY == key
    ):
        return True

    credentials = get_angel_credentials()

    if not all(
        credentials.values()
    ):
        return False

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
            return False

        data = session.get(
            "data"
        ) or {}

        jwt_token = data.get(
            "jwtToken"
        )

        if not jwt_token:
            return False

        st.session_state.angel_jwt_token = jwt_token
        st.session_state.angel_api_key = credentials["api_key"]
        st.session_state.angel_client_code = credentials["client_code"]

        feed_token = smart_api.getfeedToken()

        LIVE_WS = SmartWebSocketV2(
            jwt_token,
            credentials["api_key"],
            credentials["client_code"],
            feed_token,
        )

        token_list = [
            {
                "exchangeType": int(exchange_type),
                "tokens": [
                    str(token)
                ],
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
        LIVE_WS_KEY = key

        return True

    except Exception:

        LIVE_WS_STARTED = False
        return False


# ============================================================
# MARKET DATA
# ============================================================

def fetch_market_data(
    exchange,
    token,
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

    if not token:

        return (
            None,
            "Instrument token is not configured."
        )

    try:

        engine = TelemetryEngine(
            api_key=credentials["api_key"],
            client_code=credentials["client_code"],
            pin=credentials["pin"],
            totp_secret=credentials["totp_secret"],
        )

        df = engine.fetch_ohlcv(
            exchange=exchange,
            token=str(token),
            interval=interval,
            days=5,
        )

        if df is None or df.empty:

            return (
                None,
                "No candle data received."
            )

        df = df.copy()

        for column in [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]:

            if column not in df.columns:

                return (
                    None,
                    f"Missing column: {column}"
                )

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        if "timestamp" in df.columns:

            df["timestamp"] = pd.to_datetime(
                df["timestamp"],
                errors="coerce",
            )

        df = df.dropna(
            subset=[
                "open",
                "high",
                "low",
                "close",
            ]
        ).reset_index(
            drop=True
        )

        if len(df) < 30:

            return (
                None,
                f"Only {len(df)} candles received. Need at least 30."
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
# LIVE PRICE
# ============================================================

def get_websocket_price(
    token,
):

    if not token:
        return None

    with LIVE_LOCK:

        value = LIVE_LTP.get(
            str(token)
        )

    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


def get_rest_ltp(
    exchange,
    tradingsymbol,
    token,
):

    credentials = get_angel_credentials()

    if not all(
        credentials.values()
    ):
        return None

    try:

        engine = TelemetryEngine(
            api_key=credentials["api_key"],
            client_code=credentials["client_code"],
            pin=credentials["pin"],
            totp_secret=credentials["totp_secret"],
        )

        result = engine.get_live_ltp(
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            symboltoken=str(token),
        )

        if not result:
            return None

        value = result.get(
            "ltp"
        )

        if value is None:
            return None

        return float(value)

    except Exception:
        return None


# ============================================================
# APPLY LIVE PRICE TO LAST CANDLE
# ============================================================

def apply_live_price(
    df,
    live_price,
):

    if (
        df is None
        or df.empty
        or live_price is None
    ):
        return df

    result = df.copy()

    try:

        price = float(
            live_price
        )

        idx = result.index[-1]

        old_high = float(
            result.loc[idx, "high"]
        )

        old_low = float(
            result.loc[idx, "low"]
        )

        result.loc[
            idx,
            "close",
        ] = price

        result.loc[
            idx,
            "high",
        ] = max(
            old_high,
            price,
        )

        result.loc[
            idx,
            "low",
        ] = min(
            old_low,
            price,
        )

        return result

    except Exception:

        return df


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

def calculate_technical_signal(
    indicators,
    advanced,
):

    if not indicators:
        return {
            "signal": "NO_TRADE",
            "confidence": 0,
            "reason": "Technical data unavailable.",
        }

    score = 0
    reasons = []

    ema_trend = str(
        indicators.get(
            "ema_trend",
            ""
        )
    ).upper()

    supertrend = str(
        indicators.get(
            "supertrend",
            ""
        )
    ).upper()

    price_vwap = str(
        indicators.get(
            "price_vs_vwap",
            ""
        )
    ).upper()

    rsi = indicators.get(
        "rsi"
    )

    adx = indicators.get(
        "adx"
    )

    macd = (
        advanced.get(
            "macd",
            {}
        )
        if advanced
        else {}
    )

    macd_bias = str(
        macd.get(
            "bias",
            ""
        )
    ).upper()

    structure = (
        advanced.get(
            "market_structure",
            {}
        )
        if advanced
        else {}
    )

    structure_trend = str(
        structure.get(
            "trend",
            ""
        )
    ).upper()

    if ema_trend == "BULLISH":
        score += 2
        reasons.append("EMA bullish")

    elif ema_trend == "BEARISH":
        score -= 2
        reasons.append("EMA bearish")

    if supertrend == "BULLISH":
        score += 2
        reasons.append("Supertrend bullish")

    elif supertrend == "BEARISH":
        score -= 2
        reasons.append("Supertrend bearish")

    if price_vwap == "ABOVE":
        score += 1
        reasons.append("above VWAP")

    elif price_vwap == "BELOW":
        score -= 1
        reasons.append("below VWAP")

    if macd_bias == "BULLISH":
        score += 2
        reasons.append("MACD bullish")

    elif macd_bias == "BEARISH":
        score -= 2
        reasons.append("MACD bearish")

    if structure_trend == "BULLISH":
        score += 1
        reasons.append("higher structure")

    elif structure_trend == "BEARISH":
        score -= 1
        reasons.append("lower structure")

    try:

        if rsi is not None:

            if float(rsi) >= 55:
                score += 1
                reasons.append("RSI positive")

            elif float(rsi) <= 45:
                score -= 1
                reasons.append("RSI weak")

    except Exception:
        pass

    try:

        if adx is not None and float(adx) >= 25:
            if score > 0:
                score += 1
            elif score < 0:
                score -= 1

    except Exception:
        pass

    if score >= 4:

        signal = "ENTER_LONG"
        confidence = min(
            95,
            60 + score * 5,
        )

    elif score <= -4:

        signal = "ENTER_SHORT"
        confidence = min(
            95,
            60 + abs(score) * 5,
        )

    else:

        signal = "NO_TRADE"
        confidence = 50 + min(
            15,
            abs(score) * 3,
        )

    reason = ", ".join(
        reasons[:4]
    )

    if not reason:
        reason = "Technical conditions are mixed."

    return {
        "signal": signal,
        "confidence": float(confidence),
        "reason": reason,
    }


# ============================================================
# GEMINI
# ============================================================

def short_reason(
    reason,
    max_len=160,
):

    if not reason:
        return "Market conditions are unclear."

    value = str(
        reason
    ).replace(
        "\n",
        " ",
    ).strip()

    if len(value) > max_len:

        value = (
            value[:max_len - 3]
            + "..."
        )

    return value


def call_gemini(
    indicators,
    advanced,
    symbol,
):

    api_key = get_gemini_key()

    if not api_key:

        return {
            "signal": "NO_TRADE",
            "confidence": 0,
            "reason": "Gemini API key unavailable.",
        }

    if genai is None:

        return {
            "signal": "NO_TRADE",
            "confidence": 0,
            "reason": "Gemini SDK unavailable.",
        }

    try:

        client = genai.Client(
            api_key=api_key
        )

        prompt = f"""
You are an Indian market technical-analysis assistant.

PAPER TRADING ONLY.
Do not place real orders.

Instrument:
{symbol}

Use ONLY the supplied technical data.
Do not invent news, VIX, OI, PCR, Greeks or other unavailable data.

LTP:
{indicators.get("ltp")}

RSI:
{indicators.get("rsi")}

ADX:
{indicators.get("adx")}

VWAP:
{indicators.get("vwap")}

Price vs VWAP:
{indicators.get("price_vs_vwap")}

EMA Trend:
{indicators.get("ema_trend")}

Supertrend:
{indicators.get("supertrend")}

ATR:
{indicators.get("atr")}

Market Regime:
{indicators.get("market_regime")}

Advanced Analysis:
{json.dumps(advanced, default=str)}

Return ONLY JSON:

{{
  "signal": "ENTER_LONG",
  "confidence": 80,
  "reason": "Short technical reason."
}}

Allowed signal values:
ENTER_LONG
ENTER_SHORT
NO_TRADE

Confidence must be 0-100.
"""

        response = client.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
        )

        raw = str(
            response.text
        ).strip()

        raw = raw.replace(
            "```json",
            "",
        ).replace(
            "```",
            "",
        ).strip()

        result = json.loads(
            raw
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
            ),
            160,
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
                "Gemini error: " + str(e),
                160,
            ),
        }


# ============================================================
# PAPER TRADE LEVELS
# ============================================================

def calculate_levels(
    signal,
    atr,
    price,
):

    try:
        price = float(price)
    except Exception:
        price = 0

    try:
        atr = float(atr)
    except Exception:
        atr = 0

    if price <= 0:
        return {
            "entry": 0,
            "sl": 0,
            "target1": 0,
            "target2": 0,
            "trailing": 0,
        }

    if atr <= 0:
        atr = max(
            price * 0.002,
            1,
        )

    if signal == "ENTER_LONG":

        sl = price - (
            atr * 1.5
        )

        target1 = price + (
            atr * 2
        )

        target2 = price + (
            atr * 3
        )

        trailing = price - (
            atr * 1.0
        )

    elif signal == "ENTER_SHORT":

        sl = price + (
            atr * 1.5
        )

        target1 = price - (
            atr * 2
        )

        target2 = price - (
            atr * 3
        )

        trailing = price + (
            atr * 1.0
        )

    else:

        sl = 0
        target1 = 0
        target2 = 0
        trailing = 0

    return {
        "entry": price,
        "sl": sl,
        "target1": target1,
        "target2": target2,
        "trailing": trailing,
    }


# ============================================================
# OPTIONS
# ============================================================

def get_options_engine():

    jwt_token = st.session_state.get(
        "angel_jwt_token"
    )

    api_key = st.session_state.get(
        "angel_api_key"
    )

    client_code = st.session_state.get(
        "angel_client_code"
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
    underlying,
    expiry_date,
    spot_price,
):

    if underlying == "SENSEX":

        return {
            "status": "UNAVAILABLE",
            "message": (
                "Current OptionsEngine is NSE-focused. "
                "SENSEX option APIs need a separate BSE implementation."
            ),
            "greeks": pd.DataFrame(),
            "chain": pd.DataFrame(),
            "pcr": pd.DataFrame(),
            "oi": {},
        }

    if not expiry_date:

        return {
            "status": "WAITING",
            "message": "Enter expiry date to load option data.",
            "greeks": pd.DataFrame(),
            "chain": pd.DataFrame(),
            "pcr": pd.DataFrame(),
            "oi": {},
        }

    engine = get_options_engine()

    if engine is None:

        return {
            "status": "WAITING",
            "message": "Angel One option session not ready.",
            "greeks": pd.DataFrame(),
            "chain": pd.DataFrame(),
            "pcr": pd.DataFrame(),
            "oi": {},
        }

    result = {
        "status": "OK",
        "message": "Options data refreshed.",
        "greeks": pd.DataFrame(),
        "chain": pd.DataFrame(),
        "pcr": pd.DataFrame(),
        "oi": {},
    }

    try:

        result["greeks"] = engine.greeks_dataframe(
            underlying,
            expiry_date,
        )

    except Exception as e:

        result["message"] = (
            "Greeks unavailable: "
            + short_reason(
                str(e),
                180,
            )
        )

    try:

        result["chain"] = engine.get_option_chain(
            underlying,
            expiry_date,
            float(spot_price),
            strikes_each_side=5,
        )

    except Exception:
        result["chain"] = pd.DataFrame()

    try:

        result["pcr"] = engine.pcr_dataframe()

    except Exception:
        result["pcr"] = pd.DataFrame()

    try:

        result["oi"] = engine.get_all_oi_buildup(
            expiry_type="NEAR"
        )

    except Exception:
        result["oi"] = {}

    return result


# ============================================================
# OPTIONS SUMMARY
# ============================================================

def options_summary(
    greeks,
    chain,
    pcr,
    oi,
    spot,
):

    result = {
        "atm": None,
        "call_iv": None,
        "put_iv": None,
        "pcr": None,
        "oi_bias": "UNAVAILABLE",
    }

    try:

        if (
            greeks is not None
            and not greeks.empty
            and "strikePrice" in greeks.columns
        ):

            g = greeks.copy()

            g["strikePrice"] = pd.to_numeric(
                g["strikePrice"],
                errors="coerce",
            )

            g = g.dropna(
                subset=[
                    "strikePrice"
                ]
            )

            if not g.empty:

                g["distance"] = (
                    g["strikePrice"]
                    - float(spot)
                ).abs()

                g = g.sort_values(
                    "distance"
                )

                result["atm"] = float(
                    g.iloc[0]["strikePrice"]
                )

            if (
                "optionType" in g.columns
                and "impliedVolatility" in g.columns
            ):

                g["impliedVolatility"] = pd.to_numeric(
                    g["impliedVolatility"],
                    errors="coerce",
                )

                calls = g[
                    g["optionType"]
                    .astype(str)
                    .str.upper()
                    == "CE"
                ]

                puts = g[
                    g["optionType"]
                    .astype(str)
                    .str.upper()
                    == "PE"
                ]

                if not calls.empty:
                    result["call_iv"] = float(
                        calls[
                            "impliedVolatility"
                        ].mean()
                    )

                if not puts.empty:
                    result["put_iv"] = float(
                        puts[
                            "impliedVolatility"
                        ].mean()
                    )

    except Exception:
        pass

    try:

        if (
            pcr is not None
            and not pcr.empty
            and "pcr" in pcr.columns
        ):

            values = pd.to_numeric(
                pcr["pcr"],
                errors="coerce",
            ).dropna()

            if not values.empty:

                result["pcr"] = float(
                    values.mean()
                )

    except Exception:
        pass

    try:

        if oi:

            long_build = len(
                oi.get(
                    "Long Built Up",
                    [],
                )
                or []
            )

            short_build = len(
                oi.get(
                    "Short Built Up",
                    [],
                )
                or []
            )

            short_cover = len(
                oi.get(
                    "Short Covering",
                    [],
                )
                or []
            )

            long_unwind = len(
                oi.get(
                    "Long Unwinding",
                    [],
                )
                or []
            )

            if long_build > short_build:

                result["oi_bias"] = (
                    "LONG BUILDUP"
                )

            elif short_build > long_build:

                result["oi_bias"] = (
                    "SHORT BUILDUP"
                )

            elif short_cover > long_unwind:

                result["oi_bias"] = (
                    "SHORT COVERING"
                )

            elif long_unwind > short_cover:

                result["oi_bias"] = (
                    "LONG UNWINDING"
                )

    except Exception:
        pass

    return result


# ============================================================
# FORMATTING
# ============================================================

def number(
    value,
    decimals=2,
):

    if value is None:
        return "—"

    try:

        value = float(value)

        if np.isnan(value):
            return "—"

        return f"{value:,.{decimals}f}"

    except Exception:

        return "—"


def metric_card(
    label,
    value,
):

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "last_df": None,
    "last_token": None,
    "last_symbol_key": None,
    "last_market_fetch": 0.0,
    "last_indicator_update": 0.0,
    "last_advanced_update": 0.0,
    "last_ai_time": 0.0,
    "last_options_time": 0.0,
    "live_indicators": {},
    "advanced": {},
    "ai_result": {
        "signal": "NO_TRADE",
        "confidence": 0,
        "reason": "Waiting for AI analysis.",
    },
    "technical_result": {
        "signal": "NO_TRADE",
        "confidence": 0,
        "reason": "Waiting for technical analysis.",
    },
    "options_data": {
        "status": "WAITING",
        "message": "Waiting for options data.",
        "greeks": pd.DataFrame(),
        "chain": pd.DataFrame(),
        "pcr": pd.DataFrame(),
        "oi": {},
    },
    "angel_jwt_token": None,
    "angel_api_key": None,
    "angel_client_code": None,
    "last_error": "",
}

for key, value in defaults.items():

    if key not in st.session_state:

        st.session_state[key] = value


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("⚙️ Market Settings")

instrument_type = st.sidebar.selectbox(
    "Instrument",
    [
        "NIFTY 50",
        "BANK NIFTY",
        "SENSEX",
        "EQUITY",
    ],
)

equity_exchange = None
equity_symbol = None
equity_token = None
equity_name = None

if instrument_type == "EQUITY":

    equity_exchange = st.sidebar.selectbox(
        "Exchange",
        [
            "NSE",
            "BSE",
        ],
    )

    equity_master = load_equity_master()

    if not equity_master.empty:

        filtered = equity_master[
            equity_master["exchange"]
            == equity_exchange
        ].copy()

        if not filtered.empty:

            display_options = (
                filtered[
                    "symbol"
                ]
                .astype(str)
                .tolist()
            )

            equity_symbol = st.sidebar.selectbox(
                "Equity",
                display_options,
            )

            selected_row = filtered[
                filtered["symbol"]
                == equity_symbol
            ]

            if not selected_row.empty:

                row = selected_row.iloc[0]

                equity_token = str(
                    row["token"]
                )

                equity_name = str(
                    row["name"]
                )

        else:

            st.sidebar.warning(
                "No equity symbols found."
            )

    else:

        st.sidebar.warning(
            "Equity master unavailable."
        )

    market_exchange = equity_exchange
    market_token = equity_token
    market_symbol = equity_symbol or "EQUITY"
    exchange_type = (
        1
        if equity_exchange == "NSE"
        else 3
    )

else:

    market_exchange = INSTRUMENTS[
        instrument_type
    ]["exchange"]

    market_token = get_instrument_token(
        instrument_type
    )

    market_symbol = INSTRUMENTS[
        instrument_type
    ]["tradingsymbol"]

    exchange_type = INSTRUMENTS[
        instrument_type
    ]["exchange_type"]


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


# ============================================================
# OPTIONS SETTINGS
# ============================================================

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Options Intelligence")

if instrument_type == "EQUITY":

    st.sidebar.caption(
        "Equity mode: stock analysis selected."
    )

    expiry_date = ""

else:

    expiry_date = st.sidebar.text_input(
        "Expiry Date",
        value="",
        placeholder="Example: 29SEP2026",
        help="Format: DDMMMYYYY",
    )

options_refresh_seconds = st.sidebar.slider(
    "Options Refresh",
    30,
    300,
    60,
    step=30,
)

st.sidebar.markdown("---")

st.sidebar.caption(
    "⚡ Live LTP: WebSocket"
)

st.sidebar.caption(
    "📊 Technical update: 5 sec"
)

st.sidebar.caption(
    "🤖 AI calls: throttled"
)

st.sidebar.caption(
    "🔒 Real orders: DISABLED"
)


# ============================================================
# IDENTIFIER
# ============================================================

instrument_key = (
    f"{instrument_type}|"
    f"{market_exchange}|"
    f"{market_token}|"
    f"{market_symbol}"
)


# ============================================================
# START LIVE FEED
# ============================================================

ws_ok = False

if market_token:

    ws_ok = start_websocket(
        exchange_type=exchange_type,
        token=market_token,
        key=instrument_key,
    )


# ============================================================
# MARKET DATA INITIAL / PERIODIC FETCH
# ============================================================

now = time.time()

symbol_changed = (
    st.session_state.last_symbol_key
    != instrument_key
)

if symbol_changed:

    st.session_state.last_df = None
    st.session_state.live_indicators = {}
    st.session_state.advanced = {}

    st.session_state.ai_result = {
        "signal": "NO_TRADE",
        "confidence": 0,
        "reason": "Waiting for AI analysis.",
    }

    st.session_state.technical_result = {
        "signal": "NO_TRADE",
        "confidence": 0,
        "reason": "Waiting for technical analysis.",
    }

    st.session_state.options_data = {
        "status": "WAITING",
        "message": "Waiting for options data.",
        "greeks": pd.DataFrame(),
        "chain": pd.DataFrame(),
        "pcr": pd.DataFrame(),
        "oi": {},
    }

    st.session_state.last_market_fetch = 0
    st.session_state.last_indicator_update = 0
    st.session_state.last_advanced_update = 0
    st.session_state.last_ai_time = 0
    st.session_state.last_options_time = 0

    st.session_state.last_symbol_key = (
        instrument_key
    )


should_fetch = (
    st.session_state.last_df is None
    or symbol_changed
    or (
        now
        - st.session_state.last_market_fetch
        >= 30
    )
)


if should_fetch and market_token:

    df, error = fetch_market_data(
        exchange=market_exchange,
        token=market_token,
        interval=interval,
    )

    if df is not None:

        st.session_state.last_df = df
        st.session_state.last_market_fetch = now
        st.session_state.last_error = ""

    else:

        st.session_state.last_error = (
            error or "Market data unavailable."
        )


# ============================================================
# CURRENT LIVE PRICE
# ============================================================

live_price = None

if market_token:

    live_price = get_websocket_price(
        market_token
    )

if live_price is None and market_token:

    cached_rest_time = st.session_state.get(
        "last_rest_ltp_time",
        0,
    )

    if (
        time.time()
        - cached_rest_time
        >= 15
    ):

        live_price = get_rest_ltp(
            exchange=market_exchange,
            tradingsymbol=market_symbol,
            token=market_token,
        )

        st.session_state.last_rest_ltp_time = time.time()

        if live_price is not None:

            st.session_state.last_rest_ltp = (
                live_price
            )

    else:

        live_price = st.session_state.get(
            "last_rest_ltp"
        )


# ============================================================
# CALCULATIONS
# ============================================================

df = st.session_state.last_df

if df is not None and not df.empty:

    working_df = apply_live_price(
        df,
        live_price,
    )

    calc_now = time.time()

    if (
        not st.session_state.live_indicators
        or calc_now
        - st.session_state.last_indicator_update
        >= 5
    ):

        try:

            indicators = (
                TelemetryEngine
                .calculate_indicators(
                    working_df
                )
            )

            if live_price is not None:

                indicators["ltp"] = round(
                    float(live_price),
                    2,
                )

            st.session_state.live_indicators = (
                indicators
            )

            st.session_state.last_indicator_update = (
                calc_now
            )

        except Exception as e:

            st.session_state.last_error = str(e)

    if (
        not st.session_state.advanced
        or calc_now
        - st.session_state.last_advanced_update
        >= 5
    ):

        try:

            st.session_state.advanced = (
                build_advanced_analysis(
                    working_df
                )
            )

            st.session_state.last_advanced_update = (
                calc_now
            )

        except Exception as e:

            st.session_state.last_error = str(e)


indicators = st.session_state.live_indicators
advanced = st.session_state.advanced


# ============================================================
# TECHNICAL SIGNAL
# ============================================================

if indicators:

    st.session_state.technical_result = (
        calculate_technical_signal(
            indicators,
            advanced,
        )
    )

technical_result = (
    st.session_state.technical_result
)


# ============================================================
# AI SIGNAL
# ============================================================

if analysis_mode == "Technical + AI":

    ai_now = time.time()

    if (
        indicators
        and (
            st.session_state.last_ai_time == 0
            or ai_now
            - st.session_state.last_ai_time
            >= 300
        )
    ):

        st.session_state.ai_result = (
            call_gemini(
                indicators,
                advanced,
                instrument_type,
            )
        )

        st.session_state.last_ai_time = ai_now


ai_result = st.session_state.ai_result


# ============================================================
# SELECT FINAL SIGNAL
# ============================================================

if analysis_mode == "Technical Only":

    final_result = technical_result

else:

    final_result = ai_result


final_signal = final_result.get(
    "signal",
    "NO_TRADE",
)

final_confidence = final_result.get(
    "confidence",
    0,
)

final_reason = final_result.get(
    "reason",
    "Waiting for analysis.",
)


# ============================================================
# PAPER LEVELS
# ============================================================

price_for_levels = (
    live_price
    if live_price is not None
    else indicators.get("ltp")
)

levels = calculate_levels(
    signal=final_signal,
    atr=indicators.get("atr"),
    price=price_for_levels,
)


# ============================================================
# HEADER
# ============================================================

st.subheader(
    f"📌 {instrument_type}"
)

if instrument_type == "EQUITY":

    st.caption(
        f"{equity_exchange or ''} • "
        f"{equity_symbol or 'Select equity'}"
    )

else:

    st.caption(
        f"{market_exchange} • "
        f"{market_symbol} • "
        f"Token {market_token or 'NOT CONFIGURED'}"
    )


# ============================================================
# MARKET OVERVIEW
# ============================================================

st.markdown("### 📊 Market Overview")

c1, c2, c3, c4 = st.columns(4)

with c1:

    metric_card(
        "LIVE LTP",
        number(
            live_price
            if live_price is not None
            else indicators.get("ltp")
        ),
    )

with c2:

    metric_card(
        "RSI (14)",
        number(
            indicators.get("rsi")
        ),
    )

with c3:

    metric_card(
        "ADX (14)",
        number(
            indicators.get("adx")
        ),
    )

with c4:

    metric_card(
        "VWAP",
        number(
            indicators.get("vwap")
        ),
    )


# ============================================================
# TREND
# ============================================================

st.markdown("### 📈 Market Trend & Momentum")

c1, c2, c3, c4 = st.columns(4)

with c1:

    metric_card(
        "EMA Trend",
        indicators.get(
            "ema_trend",
            "—",
        ),
    )

with c2:

    metric_card(
        "Supertrend",
        indicators.get(
            "supertrend",
            "—",
        ),
    )

with c3:

    metric_card(
        "Price vs VWAP",
        indicators.get(
            "price_vs_vwap",
            "—",
        ),
    )

with c4:

    metric_card(
        "Market Regime",
        indicators.get(
            "market_regime",
            "—",
        ),
    )


# ============================================================
# SIGNAL
# ============================================================

st.markdown("### 🎯 Trading Signal")

c1, c2 = st.columns(2)

with c1:

    st.markdown(
        f"""
        <div class="signal-card">
            <div class="metric-label">SIGNAL</div>
            <div class="signal-value">{final_signal}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:

    st.markdown(
        f"""
        <div class="signal-card">
            <div class="metric-label">CONFIDENCE</div>
            <div class="signal-value">{number(final_confidence, 1)}%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.info(
    f"🧠 Reason: {final_reason}"
)


# ============================================================
# PAPER TRADE PLAN
# ============================================================

st.markdown("### 📝 Paper Trade Plan")

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    metric_card(
        "Entry",
        number(
            levels["entry"]
        ),
    )

with c2:
    metric_card(
        "Stop Loss",
        number(
            levels["sl"]
        ),
    )

with c3:
    metric_card(
        "Target 1",
        number(
            levels["target1"]
        ),
    )

with c4:
    metric_card(
        "Target 2",
        number(
            levels["target2"]
        ),
    )

with c5:
    metric_card(
        "Trailing SL",
        number(
            levels["trailing"]
        ),
    )


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

st.markdown("### 🔧 Technical Indicators")

tech_table = pd.DataFrame(
    {
        "Indicator": [
            "LTP",
            "RSI 14",
            "ADX 14",
            "ATR 14",
            "EMA 9",
            "EMA 21",
            "EMA 50",
            "VWAP",
            "Supertrend",
        ],
        "Value": [
            number(indicators.get("ltp")),
            number(indicators.get("rsi")),
            number(indicators.get("adx")),
            number(indicators.get("atr")),
            number(indicators.get("ema_9")),
            number(indicators.get("ema_21")),
            number(indicators.get("ema_50")),
            number(indicators.get("vwap")),
            indicators.get("supertrend", "—"),
        ],
    }
)

st.dataframe(
    tech_table,
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# ADVANCED PRICE ACTION
# ============================================================

st.markdown("### 🔍 Advanced Price Action")

a1, a2 = st.columns(2)

with a1:

    candle = advanced.get(
        "candlestick_patterns",
        [],
    )

    if isinstance(candle, list):

        candle_text = ", ".join(
            map(
                str,
                candle,
            )
        )

    else:

        candle_text = str(
            candle
        )

    st.write(
        f"**Candlestick:** {candle_text or '—'}"
    )

    macd = advanced.get(
        "macd",
        {},
    )

    st.write(
        f"**MACD Bias:** "
        f"{macd.get('bias', '—')}"
    )

    st.write(
        f"**MACD:** "
        f"{number(macd.get('value'), 4)}"
    )

with a2:

    sr = advanced.get(
        "support_resistance",
        {},
    )

    st.write(
        f"**Support:** "
        f"{number(sr.get('support'))}"
    )

    st.write(
        f"**Resistance:** "
        f"{number(sr.get('resistance'))}"
    )

    volume = advanced.get(
        "volume",
        {},
    )

    st.write(
        f"**Volume:** "
        f"{number(volume.get('volume'))}"
    )

    st.write(
        f"**Volume Signal:** "
        f"{volume.get('volume_signal', '—')}"
    )


structure = advanced.get(
    "market_structure",
    {},
)

st.write(
    f"**Market Structure:** "
    f"{structure.get('structure', '—')}"
)

st.write(
    f"**Structure Trend:** "
    f"{structure.get('trend', '—')}"
)

st.write(
    f"**Momentum:** "
    f"{structure.get('momentum', '—')}"
)


# ============================================================
# OPTIONS INTELLIGENCE
# ============================================================

st.markdown("### 📊 Options Intelligence")

if instrument_type == "EQUITY":

    st.info(
        "Equity mode selected — options intelligence is not used for this stock."
    )

else:

    if instrument_type == "SENSEX":

        st.warning(
            "SENSEX dropdown is active. "
            "Current OptionsEngine implementation is NSE-focused, "
            "so SENSEX option Greeks/PCR/OI need a separate BSE API implementation."
        )

    else:

        underlying = INSTRUMENTS[
            instrument_type
        ]["options_name"]

        if expiry_date:

            options_now = time.time()

            if (
                options_now
                - st.session_state.last_options_time
                >= options_refresh_seconds
                or st.session_state.last_options_time == 0
            ):

                spot = (
                    live_price
                    if live_price is not None
                    else indicators.get("ltp", 0)
                )

                st.session_state.options_data = (
                    refresh_options_data(
                        underlying=underlying,
                        expiry_date=expiry_date,
                        spot_price=spot,
                    )
                )

                st.session_state.last_options_time = (
                    options_now
                )

        else:

            st.info(
                "Expiry date enter karo, example: 29SEP2026"
            )

        option_data = (
            st.session_state.options_data
        )

        st.caption(
            option_data.get(
                "message",
                "",
            )
        )

        greeks_df = option_data.get(
            "greeks",
            pd.DataFrame(),
        )

        chain_df = option_data.get(
            "chain",
            pd.DataFrame(),
        )

        pcr_df = option_data.get(
            "pcr",
            pd.DataFrame(),
        )

        oi_data = option_data.get(
            "oi",
            {},
        )

        spot = (
            live_price
            if live_price is not None
            else indicators.get("ltp", 0)
        )

        opt_summary = options_summary(
            greeks=greeks_df,
            chain=chain_df,
            pcr=pcr_df,
            oi=oi_data,
            spot=spot,
        )

        o1, o2, o3, o4 = st.columns(4)

        with o1:
            metric_card(
                "ATM Strike",
                number(
                    opt_summary["atm"]
                ),
            )

        with o2:
            metric_card(
                "Call IV",
                number(
                    opt_summary["call_iv"]
                ),
            )

        with o3:
            metric_card(
                "Put IV",
                number(
                    opt_summary["put_iv"]
                ),
            )

        with o4:
            metric_card(
                "PCR",
                number(
                    opt_summary["pcr"]
                ),
            )

        st.write(
            f"**OI Bias:** {opt_summary['oi_bias']}"
        )

        if (
            not greeks_df.empty
        ):

            st.write("#### Greeks")

            greek_columns = [
                "name",
                "expiry",
                "strikePrice",
                "optionType",
                "delta",
                "gamma",
                "theta",
                "vega",
                "impliedVolatility",
            ]

            available = [
                c
                for c in greek_columns
                if c in greeks_df.columns
            ]

            if available:

                display_greeks = (
                    greeks_df[
                        available
                    ]
                    .copy()
                )

                for col in [
                    "strikePrice",
                    "delta",
                    "gamma",
                    "theta",
                    "vega",
                    "impliedVolatility",
                ]:

                    if col in display_greeks.columns:

                        display_greeks[col] = (
                            pd.to_numeric(
                                display_greeks[col],
                                errors="coerce",
                            )
                        )

                st.dataframe(
                    display_greeks,
                    use_container_width=True,
                    hide_index=True,
                )

        else:

            st.caption(
                "Option Greeks data unavailable for the selected expiry."
            )

        if (
            not chain_df.empty
        ):

            st.write("#### Near ATM CE / PE Chain")

            chain_display = chain_df.copy()

            columns = [
                "symbol",
                "strike",
                "option_type",
                "ltp",
                "open",
                "high",
                "low",
                "close",
                "tradeVolume",
                "opnInterest",
            ]

            available = [
                c
                for c in columns
                if c in chain_display.columns
            ]

            if available:

                st.dataframe(
                    chain_display[
                        available
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

        else:

            st.caption(
                "Option chain data unavailable."
            )


# ============================================================
# RECENT CANDLES
# ============================================================

st.markdown("### 🕯️ Recent Candles")

if df is not None and not df.empty:

    recent = df.tail(10).copy()

    display_columns = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    available = [
        c
        for c in display_columns
        if c in recent.columns
    ]

    recent_display = recent[
        available
    ].copy()

    for col in [
        "open",
        "high",
        "low",
        "close",
    ]:

        if col in recent_display.columns:

            recent_display[col] = (
                recent_display[col]
                .map(
                    lambda x: number(x)
                )
            )

    st.dataframe(
        recent_display,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.warning(
        "Market candle data is not available yet."
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

st.markdown("### 🖥️ System Status")

credentials = get_angel_credentials()

angel_ready = all(
    credentials.values()
)

gemini_ready = bool(
    get_gemini_key()
)

options_ready = bool(
    st.session_state.get(
        "angel_jwt_token"
    )
)

s1, s2, s3, s4 = st.columns(4)

with s1:

    metric_card(
        "Paper Trading",
        "ON",
    )

with s2:

    metric_card(
        "Angel One",
        "CONNECTED"
        if angel_ready
        else "NOT CONNECTED",
    )

with s3:

    metric_card(
        "Gemini",
        "READY"
        if gemini_ready
        else "NOT CONNECTED",
    )

with s4:

    metric_card(
        "Live Feed",
        "CONNECTED"
        if ws_ok
        else "WAITING",
    )


# ============================================================
# ERROR / WAITING INFORMATION
# ============================================================

if st.session_state.last_error:

    with st.expander(
        "⚠️ Latest System Message"
    ):

        st.write(
            st.session_state.last_error
        )


# ============================================================
# MARKET CLOSED MESSAGE
# ============================================================

current_time = datetime.now()

is_weekend = (
    current_time.weekday()
    >= 5
)

market_minutes = (
    current_time.hour * 60
    + current_time.minute
)

market_open_minutes = (
    9 * 60 + 15
)

market_close_minutes = (
    15 * 60 + 30
)

market_open = (
    not is_weekend
    and market_open_minutes
    <= market_minutes
    <= market_close_minutes
)

if not market_open:

    st.caption(
        "ℹ️ Market is currently outside normal Indian equity market hours "
        "(09:15–15:30, Monday–Friday). Live prices may remain unchanged."
    )


# ============================================================
# AUTO UPDATE
# ============================================================

@st.fragment(run_every=2)
def live_update():

    st.empty()


live_update()
