import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, time
import json
import math

# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="AI Trading Expert Advisor",
    page_icon="📊",
    layout="wide",
)

PAPER_TRADING = True

# =========================================================
# MOBILE UI
# =========================================================

st.markdown("""
<style>
.block-container{
    padding-top:1rem!important;
    padding-left:.7rem!important;
    padding-right:.7rem!important;
    max-width:100%!important;
}

@media(max-width:768px){
    [data-testid="stHorizontalBlock"]{
        flex-wrap:wrap!important;
        gap:.4rem!important;
    }

    [data-testid="column"]{
        min-width:48%!important;
        flex:1 1 48%!important;
    }

    [data-testid="stMetric"]{
        width:100%!important;
        min-width:0!important;
        overflow:visible!important;
    }

    [data-testid="stMetricLabel"]{
        font-size:11px!important;
        line-height:1.2!important;
        white-space:normal!important;
        overflow:visible!important;
    }

    [data-testid="stMetricValue"]{
        font-size:18px!important;
        line-height:1.2!important;
        white-space:normal!important;
        overflow:visible!important;
        text-overflow:clip!important;
    }

    h1{font-size:25px!important}
    h2{font-size:21px!important}
    h3{font-size:18px!important}

    .trade-card{
        padding:.75rem!important;
    }
}

.trade-card{
    border:1px solid rgba(128,128,128,.30);
    border-radius:12px;
    padding:1rem;
    margin:.5rem 0;
}

.small{
    font-size:.88rem;
    opacity:.85;
}

.reason{
    line-height:1.5;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# OPTIONAL ENGINES
# =========================================================

try:
    from telemetry_engine import TelemetryEngine
except Exception:
    TelemetryEngine = None

try:
    from options_engine import OptionsEngine
except Exception:
    OptionsEngine = None

# =========================================================
# HELPERS
# =========================================================

def secret(name):
    try:
        v = st.secrets.get(name)
        return str(v).strip() if v else ""
    except Exception:
        return ""


def num(x, default=None):
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace(",", "").strip()
        return float(x)
    except Exception:
        return default


def fmt(x, digits=2):
    x = num(x)
    if x is None:
        return "-"
    return f"{x:,.{digits}f}"


def safe_text(x):
    return str(x) if x is not None else ""


def market_open():
    now = datetime.now()
    return now.weekday() < 5 and time(9, 15) <= now.time() <= time(15, 30)


def expiry_norm(x):
    if x is None:
        return None

    if isinstance(x, (datetime, date)):
        return x.strftime("%Y-%m-%d")

    s = str(x).strip().upper()

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d%b%Y",
        "%d-%b-%Y",
        "%d%b%y",
        "%d-%b-%y",
    ]

    for f in formats:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except Exception:
            pass

    return s


def expiry_label(x):
    n = expiry_norm(x)
    if not n:
        return "-"

    try:
        return datetime.strptime(n, "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        return str(x)


def clean_df(df):
    if df is None:
        return pd.DataFrame()

    if isinstance(df, pd.DataFrame):
        return df.copy()

    try:
        return pd.DataFrame(df)
    except Exception:
        return pd.DataFrame()


def first_value(row, names, default=None):
    for n in names:
        if isinstance(row, dict) and n in row:
            v = row.get(n)
            if v is not None and str(v) != "":
                return v

        try:
            if n in row.index:
                v = row[n]
                if pd.notna(v):
                    return v
        except Exception:
            pass

    return default


# =========================================================
# SECRETS
# =========================================================

ANGEL_API_KEY = secret("ANGEL_API_KEY")
ANGEL_CLIENT_CODE = secret("ANGEL_CLIENT_CODE")
ANGEL_PIN = secret("ANGEL_PIN")
ANGEL_TOTP_SECRET = secret("ANGEL_TOTP_SECRET")
ANGEL_JWT_TOKEN = secret("ANGEL_JWT_TOKEN")

GEMINI_API_KEY = (
    secret("GEMINI_API_KEY")
    or secret("GOOGLE_API_KEY")
    or secret("GEMINI_KEY")
)

GEMINI_MODEL = secret("GEMINI_MODEL") or "gemini-3.6-flash"

# =========================================================
# ENGINES
# =========================================================

@st.cache_resource(show_spinner=False)
def create_telemetry():
    if TelemetryEngine is None:
        return None

    if not all([
        ANGEL_API_KEY,
        ANGEL_CLIENT_CODE,
        ANGEL_PIN,
        ANGEL_TOTP_SECRET,
    ]):
        return None

    try:
        return TelemetryEngine(
            api_key=ANGEL_API_KEY,
            client_code=ANGEL_CLIENT_CODE,
            pin=ANGEL_PIN,
            totp_secret=ANGEL_TOTP_SECRET,
        )
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def create_options():
    if OptionsEngine is None:
        return None

    try:
        if ANGEL_JWT_TOKEN:
            return OptionsEngine(
                jwt_token=ANGEL_JWT_TOKEN,
                api_key=ANGEL_API_KEY,
                client_code=ANGEL_CLIENT_CODE,
            )
    except Exception:
        pass

    telemetry_obj = create_telemetry()

    if telemetry_obj is not None:
        try:
            smart_api = telemetry_obj.smart_api
            token = getattr(smart_api, "access_token", None)

            if token:
                return OptionsEngine(
                    jwt_token=str(token),
                    api_key=ANGEL_API_KEY,
                    client_code=ANGEL_CLIENT_CODE,
                )
        except Exception:
            pass

    return None


telemetry = create_telemetry()
options = create_options()

# =========================================================
# MARKET CONFIG
# =========================================================

UNDERLYINGS = [
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "SENSEX",
    "BANKEX",
]

SPOT_TOKENS = {
    "NIFTY": ("NSE", "99926000"),
    "BANKNIFTY": ("NSE", "99926009"),
    "SENSEX": ("BSE", "99919000"),
}

# =========================================================
# SPOT
# =========================================================

def get_spot(symbol):
    if telemetry is None:
        return None

    exchange, token = SPOT_TOKENS.get(
        symbol,
        ("NSE", None)
    )

    if token is None:
        return None

    try:
        result = telemetry.get_live_ltp(
            exchange,
            symbol,
            token,
        )

        if isinstance(result, dict):
            if result.get("status"):
                return num(result.get("ltp"))

            for key in ["ltp", "data"]:
                value = result.get(key)

                if isinstance(value, dict):
                    v = (
                        value.get("ltp")
                        or value.get("LTP")
                    )
                    if v is not None:
                        return num(v)

        return num(result)

    except Exception:
        return None


# =========================================================
# EXPIRIES
# =========================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_expiries(symbol):
    if options is None:
        return []

    try:
        result = options.get_expiry_options(symbol)

        values = []

        for item in result or []:
            if isinstance(item, dict):
                value = (
                    item.get("value")
                    or item.get("expiry")
                    or item.get("expiryDate")
                )
            else:
                value = item

            value = expiry_norm(value)

            if not value:
                continue

            try:
                d = datetime.strptime(
                    value,
                    "%Y-%m-%d"
                ).date()

                if d >= date.today():
                    values.append(value)

            except Exception:
                pass

        return sorted(set(values))

    except Exception:
        return []


# =========================================================
# CONTRACTS
# =========================================================

@st.cache_data(ttl=120, show_spinner=False)
def load_contracts(symbol, expiry):
    if options is None or not expiry:
        return pd.DataFrame()

    try:
        return clean_df(
            options.get_option_contracts(
                underlying=symbol,
                expiry_date=expiry,
            )
        )
    except Exception:
        return pd.DataFrame()


def get_chain(symbol, expiry, spot):
    contracts = load_contracts(symbol, expiry)

    if contracts.empty:
        return pd.DataFrame(), contracts

    try:
        if spot is not None:
            near = options.get_near_atm_contracts(
                underlying=symbol,
                expiry_date=expiry,
                spot_price=spot,
                strikes_each_side=8,
            )
            near = clean_df(near)

            if not near.empty:
                contracts = near

    except Exception:
        pass

    try:
        quoted = options.get_market_quote(contracts)
        quoted = clean_df(quoted)

        if not quoted.empty:
            return quoted, contracts

    except Exception:
        pass

    return contracts.copy(), contracts


# =========================================================
# PCR
# =========================================================

def calculate_pcr(df):
    if df.empty:
        return None

    oi_col = None

    for c in ["opnInterest", "openInterest", "oi", "open_interest"]:
        if c in df.columns:
            oi_col = c
            break

    type_col = None

    for c in ["option_type", "optionType", "optionTypeName"]:
        if c in df.columns:
            type_col = c
            break

    if oi_col is None or type_col is None:
        return None

    work = df.copy()

    work[oi_col] = pd.to_numeric(
        work[oi_col],
        errors="coerce"
    ).fillna(0)

    types = (
        work[type_col]
        .astype(str)
        .str.upper()
    )

    ce = work.loc[
        types.str.contains("CE"),
        oi_col
    ].sum()

    pe = work.loc[
        types.str.contains("PE"),
        oi_col
    ].sum()

    if ce <= 0:
        return None

    return pe / ce


# =========================================================
# OHLCV
# =========================================================

@st.cache_data(ttl=120, show_spinner=False)
def fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=5):
    if telemetry is None:
        return pd.DataFrame()

    if symbol not in SPOT_TOKENS:
        return pd.DataFrame()

    exchange, token = SPOT_TOKENS[symbol]

    try:
        df = telemetry.fetch_ohlcv(
            exchange=exchange,
            token=token,
            interval=interval,
            days=days,
        )

        df = clean_df(df)

        if df.empty:
            return df

        # Normalize columns
        rename = {}

        for c in df.columns:
            lc = str(c).lower()

            if lc in ["open", "o"]:
                rename[c] = "open"

            elif lc in ["high", "h"]:
                rename[c] = "high"

            elif lc in ["low", "l"]:
                rename[c] = "low"

            elif lc in ["close", "c", "ltp"]:
                rename[c] = "close"

            elif lc in ["volume", "vol"]:
                rename[c] = "volume"

        df = df.rename(columns=rename)

        needed = [
            "open",
            "high",
            "low",
            "close",
        ]

        if not all(c in df.columns for c in needed):
            return pd.DataFrame()

        for c in needed + (
            ["volume"] if "volume" in df.columns else []
        ):
            df[c] = pd.to_numeric(
                df[c],
                errors="coerce"
            )

        df = df.dropna(
            subset=needed
        ).reset_index(drop=True)

        return df

    except Exception:
        return pd.DataFrame()


# =========================================================
# INDICATORS
# =========================================================

def add_indicators(df):
    df = df.copy()

    if df.empty:
        return df

    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["EMA20"] = close.ewm(
        span=20,
        adjust=False
    ).mean()

    df["EMA50"] = close.ewm(
        span=50,
        adjust=False
    ).mean()

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    df["RSI"] = 100 - (
        100 / (1 + rs)
    )

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    df["MACD"] = ema12 - ema26

    df["MACD_SIGNAL"] = df["MACD"].ewm(
        span=9,
        adjust=False
    ).mean()

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = tr.rolling(14).mean()

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where(
        (plus_dm > minus_dm) &
        (plus_dm > 0),
        0
    )

    minus_dm = minus_dm.where(
        (minus_dm > plus_dm) &
        (minus_dm > 0),
        0
    )

    plus_di = (
        100 *
        plus_dm.rolling(14).sum() /
        atr.rolling(14).sum()
    )

    minus_di = (
        100 *
        minus_dm.rolling(14).sum() /
        atr.rolling(14).sum()
    )

    dx = (
        100 *
        (plus_di - minus_di).abs() /
        (plus_di + minus_di).replace(
            0,
            np.nan
        )
    )

    df["ADX"] = dx.rolling(14).mean()

    if "volume" in df.columns:
        typical = (
            high + low + close
        ) / 3

        cumulative_volume = (
            df["volume"].cumsum()
        )

        df["VWAP"] = (
            (typical * df["volume"]).cumsum()
            / cumulative_volume.replace(
                0,
                np.nan
            )
        )

        df["VOL_AVG20"] = df[
            "volume"
        ].rolling(20).mean()

    else:
        df["VWAP"] = np.nan
        df["VOL_AVG20"] = np.nan

    return df


# =========================================================
# MARKET ANALYSIS
# =========================================================

def analyze_market(symbol):
    result = {
        "symbol": symbol,
        "trend": "UNKNOWN",
        "momentum": "NEUTRAL",
        "rsi": None,
        "adx": None,
        "ema20": None,
        "ema50": None,
        "macd": None,
        "macd_signal": None,
        "vwap": None,
        "volume_ratio": None,
        "support": None,
        "resistance": None,
        "last": None,
        "score": 0,
        "reasons": [],
    }

    df5 = add_indicators(
        fetch_ohlcv(
            symbol,
            "FIVE_MINUTE",
            5
        )
    )

    if df5.empty:
        return result

    row = df5.iloc[-1]

    last = num(row.get("close"))

    result["last"] = last
    result["rsi"] = num(row.get("RSI"))
    result["adx"] = num(row.get("ADX"))
    result["ema20"] = num(row.get("EMA20"))
    result["ema50"] = num(row.get("EMA50"))
    result["macd"] = num(row.get("MACD"))
    result["macd_signal"] = num(
        row.get("MACD_SIGNAL")
    )
    result["vwap"] = num(row.get("VWAP"))

    if (
        "volume" in df5.columns and
        num(row.get("volume")) is not None and
        num(row.get("VOL_AVG20")) not in [None, 0]
    ):
        result["volume_ratio"] = (
            num(row.get("volume")) /
            num(row.get("VOL_AVG20"))
        )

    recent = df5.tail(30)

    result["support"] = num(
        recent["low"].min()
    )

    result["resistance"] = num(
        recent["high"].max()
    )

    score = 0

    if (
        result["ema20"] is not None and
        result["ema50"] is not None
    ):
        if last > result["ema20"] > result["ema50"]:
            score += 2
            result["reasons"].append(
                "Price EMA20 aur EMA50 ke upar hai."
            )

        elif last < result["ema20"] < result["ema50"]:
            score -= 2
            result["reasons"].append(
                "Price EMA20 aur EMA50 ke neeche hai."
            )

    if result["vwap"] is not None:
        if last > result["vwap"]:
            score += 1
            result["reasons"].append(
                "Price VWAP ke upar hai."
            )
        elif last < result["vwap"]:
            score -= 1
            result["reasons"].append(
                "Price VWAP ke neeche hai."
            )

    if (
        result["macd"] is not None and
        result["macd_signal"] is not None
    ):
        if result["macd"] > result["macd_signal"]:
            score += 1
            result["reasons"].append(
                "MACD bullish side par hai."
            )
        else:
            score -= 1
            result["reasons"].append(
                "MACD bearish side par hai."
            )

    if result["rsi"] is not None:
        if result["rsi"] >= 60:
            score += 1
            result["momentum"] = "BULLISH"
        elif result["rsi"] <= 40:
            score -= 1
            result["momentum"] = "BEARISH"

    if (
        result["adx"] is not None and
        result["adx"] >= 20
    ):
        result["reasons"].append(
            f"ADX {result['adx']:.1f}, trend strength active."
        )

    if result["volume_ratio"] is not None:
        if result["volume_ratio"] >= 1.3:
            result["reasons"].append(
                "Volume average se significantly higher hai."
            )

    result["score"] = score

    if score >= 3:
        result["trend"] = "BULLISH"
    elif score <= -3:
        result["trend"] = "BEARISH"
    else:
        result["trend"] = "SIDEWAYS"

    return result


# =========================================================
# OPTION IDEA BUILDER
# =========================================================

def nearest_option(chain, spot, side):
    if chain.empty or spot is None:
        return None

    type_col = None

    for c in [
        "option_type",
        "optionType",
        "optionTypeName",
    ]:
        if c in chain.columns:
            type_col = c
            break

    strike_col = None

    for c in [
        "strike",
        "strikePrice",
        "strike_price",
    ]:
        if c in chain.columns:
            strike_col = c
            break

    if type_col is None or strike_col is None:
        return None

    work = chain.copy()

    types = (
        work[type_col]
        .astype(str)
        .str.upper()
    )

    work = work[
        types.str.contains(side)
    ].copy()

    if work.empty:
        return None

    work["_strike"] = pd.to_numeric(
        work[strike_col],
        errors="coerce"
    )

    work = work.dropna(
        subset=["_strike"]
    )

    if work.empty:
        return None

    work["_distance"] = (
        work["_strike"] - spot
    ).abs()

    return work.sort_values(
        "_distance"
    ).iloc[0]


def option_ltp(row):
    return num(
        first_value(
            row,
            [
                "ltp",
                "LTP",
                "lastTradedPrice",
                "last_price",
            ]
        )
    )


def make_trade_idea(
    market,
    symbol,
    instrument="INDEX",
    option_side=None,
    expiry=None,
    chain=None,
):
    last = market.get("last")

    if last is None:
        return None

    bullish = market["score"] >= 3
    bearish = market["score"] <= -3

    if not bullish and not bearish:
        return None

    direction = "BUY" if bullish else "SELL"

    if bullish:
        entry = last
        sl = (
            market["support"]
            if market["support"] and
            market["support"] < entry
            else entry * 0.997
        )

        risk = entry - sl

        target1 = entry + risk * 1.5
        target2 = entry + risk * 2.5

    else:
        entry = last
        sl = (
            market["resistance"]
            if market["resistance"] and
            market["resistance"] > entry
            else entry * 1.003
        )

        risk = sl - entry

        target1 = entry - risk * 1.5
        target2 = entry - risk * 2.5

    if risk <= 0:
        return None

    idea = {
        "segment": instrument,
        "symbol": symbol,
        "action": direction,
        "entry": entry,
        "sl": sl,
        "target1": target1,
        "target2": target2,
        "risk_reward": 1.5,
        "confidence": min(
            95,
            max(
                70,
                70 + abs(market["score"]) * 5
            )
        ),
        "holding": (
            "Intraday"
            if market_open()
            else "Next Session"
        ),
        "expiry": expiry,
        "option": None,
        "why": " ".join(
            market["reasons"][:5]
        ),
        "invalidation": (
            f"Price {'below' if bullish else 'above'} "
            f"SL level sustain kare."
        ),
    }

    # Option selection
    if (
        instrument == "INDEX OPTION" and
        chain is not None and
        not chain.empty
    ):
        side = "CE" if bullish else "PE"

        selected = nearest_option(
            chain,
            last,
            side
        )

        if selected is not None:
            strike = first_value(
                selected,
                [
                    "strike",
                    "strikePrice",
                    "strike_price",
                ]
            )

            ltp = option_ltp(selected)

            idea["option"] = side
            idea["strike"] = strike
            idea["option_ltp"] = ltp

            if ltp is not None and ltp > 0:
                idea["entry"] = ltp
                idea["sl"] = ltp * 0.85
                idea["target1"] = ltp * 1.20
                idea["target2"] = ltp * 1.35

            idea["why"] += (
                f" Direction ke according {side} selection "
                f"ki gayi hai, nearest ATM strike {strike}."
            )

    return idea


# =========================================================
# GEMINI
# =========================================================

def ask_gemini(ideas, market_data):
    if not GEMINI_API_KEY:
        return None

    try:
        from google import genai

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        payload = {
            "market": market_data,
            "ideas": ideas,
        }

        prompt = f"""
You are an Indian market research assistant for a PAPER TRADING ONLY
application.

Analyze the supplied market data.

Do NOT invent prices, OI, news, Greeks or other data.

For every supplied trade idea explain:
1. Why the setup exists
2. Trend confirmation
3. Momentum
4. Risk
5. What invalidates it
6. Whether it is intraday or next-session

Return concise professional analysis.

DATA:
{json.dumps(payload, default=str)}
"""

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        return getattr(
            response,
            "text",
            None
        )

    except Exception as e:
        return f"AI explanation unavailable: {e}"


# =========================================================
# HEADER
# =========================================================

st.title("📊 AI Trading Expert Advisor")

st.caption(
    "Live/After-Market Research • Options • Equities • "
    "Technical Analysis • Paper Trading Only"
)

h1, h2, h3, h4 = st.columns(4)

with h1:
    st.metric(
        "Mode",
        "PAPER ONLY"
    )

with h2:
    st.metric(
        "Market",
        "OPEN" if market_open()
        else "AFTER MARKET"
    )

with h3:
    st.metric(
        "Angel One",
        "CONNECTED"
        if telemetry is not None
        else "NOT CONNECTED"
    )

with h4:
    st.metric(
        "AI",
        "READY"
        if GEMINI_API_KEY
        else "DATA MODE"
    )

st.warning(
    "PAPER TRADING ONLY — koi real order place nahi hoga."
)

# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("⚙️ Expert Advisor")

old_underlying = st.session_state.get(
    "underlying",
    "NIFTY"
)

if old_underlying not in UNDERLYINGS:
    old_underlying = "NIFTY"

underlying = st.sidebar.selectbox(
    "Underlying",
    UNDERLYINGS,
    index=UNDERLYINGS.index(
        old_underlying
    ),
)

st.session_state["underlying"] = underlying

expiries = load_expiries(
    underlying
)

selected_expiry = None

if expiries:
    old_expiry = st.session_state.get(
        "expiry"
    )

    if old_expiry not in expiries:
        old_expiry = expiries[0]

    selected_expiry = st.sidebar.selectbox(
        "Expiry",
        expiries,
        index=expiries.index(
            old_expiry
        ),
        format_func=expiry_label,
    )

    st.session_state["expiry"] = (
        selected_expiry
    )
else:
    st.sidebar.info(
        "Expiry data unavailable"
    )

option_type = st.sidebar.selectbox(
    "Option Type",
    ["CE", "PE", "BOTH"],
)

if st.sidebar.button(
    "🔄 Refresh Data",
    use_container_width=True
):
    st.cache_data.clear()
    st.rerun()

# =========================================================
# CURRENT MARKET
# =========================================================

spot = get_spot(
    underlying
)

st.subheader(
    "📌 Current Market"
)

m1, m2, m3, m4 = st.columns(4)

with m1:
    st.metric(
        "Underlying",
        underlying
    )

with m2:
    st.metric(
        "LTP",
        fmt(spot)
    )

with m3:
    st.metric(
        "Expiry",
        expiry_label(
            selected_expiry
        )
        if selected_expiry
        else "-"
    )

with m4:
    st.metric(
        "Session",
        "LIVE"
        if market_open()
        else "AFTER MARKET"
    )

# =========================================================
# MARKET ANALYSIS
# =========================================================

market = analyze_market(
    underlying
)

st.subheader(
    "📈 Market Intelligence"
)

a1, a2, a3, a4 = st.columns(4)

with a1:
    st.metric(
        "Trend",
        market["trend"]
    )

with a2:
    st.metric(
        "Momentum",
        market["momentum"]
    )

with a3:
    st.metric(
        "RSI",
        fmt(market["rsi"], 1)
    )

with a4:
    st.metric(
        "ADX",
        fmt(market["adx"], 1)
    )

a5, a6, a7, a8 = st.columns(4)

with a5:
    st.metric(
        "EMA20",
        fmt(market["ema20"])
    )

with a6:
    st.metric(
        "EMA50",
        fmt(market["ema50"])
    )

with a7:
    st.metric(
        "VWAP",
        fmt(market["vwap"])
    )

with a8:
    st.metric(
        "Volume Ratio",
        fmt(market["volume_ratio"], 2)
    )

# =========================================================
# SUPPORT / RESISTANCE
# =========================================================

r1, r2 = st.columns(2)

with r1:
    st.metric(
        "Support",
        fmt(market["support"])
    )

with r2:
    st.metric(
        "Resistance",
        fmt(market["resistance"])
    )

if market["reasons"]:
    st.markdown("### Current Analysis")

    for reason in market["reasons"]:
        st.write("• " + reason)

# =========================================================
# OPTIONS
# =========================================================

chain = pd.DataFrame()

if selected_expiry:
    chain, all_contracts = get_chain(
        underlying,
        selected_expiry,
        spot
    )

pcr = calculate_pcr(
    chain
)

st.subheader(
    "🧮 Options Intelligence"
)

o1, o2, o3 = st.columns(3)

with o1:
    st.metric(
        "PCR",
        fmt(pcr, 2)
        if pcr is not None
        else "Unavailable"
    )

with o2:
    st.metric(
        "Contracts",
        len(chain)
    )

with o3:
    st.metric(
        "Expiry",
        expiry_label(
            selected_expiry
        )
        if selected_expiry
        else "-"
    )

if not chain.empty:
    display_cols = [
        "symbol",
        "strike",
        "option_type",
        "expiry_normalized",
        "ltp",
        "tradeVolume",
        "opnInterest",
    ]

    cols = [
        c for c in display_cols
        if c in chain.columns
    ]

    if option_type in ["CE", "PE"]:
        type_col = (
            "option_type"
            if "option_type" in chain.columns
            else None
        )

        if type_col:
            view = chain[
                chain[type_col]
                .astype(str)
                .str.upper()
                .eq(option_type)
            ]
        else:
            view = chain
    else:
        view = chain

    if cols:
        st.dataframe(
            view[cols],
            use_container_width=True,
            hide_index=True
        )

# =========================================================
# TRADE IDEAS
# =========================================================

st.divider()

st.subheader(
    "🎯 AI Trade Ideas"
)

st.write(
    "Trade Ideas button market ko dobara analyze karke "
    "available valid setups banayega."
)

if st.button(
    "🚀 GENERATE TRADE IDEAS",
    type="primary",
    use_container_width=True
):

    with st.spinner(
        "Market data + technical setup analyze ho raha hai..."
    ):

        ideas = []

        # -------------------------------------------------
        # 1. INDEX SPOT
        # -------------------------------------------------

        base_idea = make_trade_idea(
            market,
            underlying,
            "INDEX",
            expiry=selected_expiry,
            chain=chain,
        )

        if base_idea:
            ideas.append(
                base_idea
            )

        # -------------------------------------------------
        # 2. INDEX OPTION
        # -------------------------------------------------

        option_idea = make_trade_idea(
            market,
            underlying,
            "INDEX OPTION",
            expiry=selected_expiry,
            chain=chain,
        )

        if option_idea:
            ideas.append(
                option_idea
            )

        # -------------------------------------------------
        # 3. BANKNIFTY
        # -------------------------------------------------

        if underlying != "BANKNIFTY":

            bank_market = analyze_market(
                "BANKNIFTY"
            )

            bank_idea = make_trade_idea(
                bank_market,
                "BANKNIFTY",
                "INDEX",
            )

            if bank_idea:
                ideas.append(
                    bank_idea
                )

        # -------------------------------------------------
        # 4. NIFTY
        # -------------------------------------------------

        if underlying != "NIFTY":

            nifty_market = analyze_market(
                "NIFTY"
            )

            nifty_idea = make_trade_idea(
                nifty_market,
                "NIFTY",
                "INDEX",
            )

            if nifty_idea:
                ideas.append(
                    nifty_idea
                )

        # -------------------------------------------------
        # 5. SENSEX
        # -------------------------------------------------

        sensex_market = analyze_market(
            "SENSEX"
        )

        sensex_idea = make_trade_idea(
            sensex_market,
            "SENSEX",
            "INDEX",
        )

        if sensex_idea:
            ideas.append(
                sensex_idea
            )

        # Remove duplicates
        unique = []

        seen = set()

        for idea in ideas:
            key = (
                idea["segment"],
                idea["symbol"],
                idea["action"],
                idea.get("option"),
                str(idea.get("strike")),
            )

            if key not in seen:
                seen.add(key)
                unique.append(idea)

        ideas = unique[:5]

    if not ideas:

        st.warning(
            "Current available data se koi sufficiently strong "
            "setup confirm nahi hua. Fake trade generate nahi kiya gaya."
        )

    else:

        st.success(
            f"{len(ideas)} valid setup(s) generated."
        )

        # -------------------------------------------------
        # DISPLAY IDEAS
        # -------------------------------------------------

        for i, idea in enumerate(
            ideas,
            start=1
        ):

            st.markdown(
                f"""
                <div class="trade-card">
                <h3>Trade Idea {i} — {idea['symbol']}</h3>
                <div class="small">
                Segment: {idea['segment']} |
                Holding: {idea['holding']}
                </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            c1, c2, c3, c4 = st.columns(4)

            with c1:
                st.metric(
                    "Action",
                    idea["action"]
                )

            with c2:
                st.metric(
                    "Confidence",
                    f"{idea['confidence']:.0f}%"
                )

            with c3:
                st.metric(
                    "Entry",
                    fmt(idea["entry"])
                )

            with c4:
                st.metric(
                    "Risk/Reward",
                    f"1:{idea['risk_reward']:.1f}"
                )

            c5, c6, c7, c8 = st.columns(4)

            with c5:
                st.metric(
                    "SL",
                    fmt(idea["sl"])
                )

            with c6:
                st.metric(
                    "Target 1",
                    fmt(idea["target1"])
                )

            with c7:
                st.metric(
                    "Target 2",
                    fmt(idea["target2"])
                )

            with c8:
                if idea.get("option"):
                    label = (
                        f"{idea['option']} "
                        f"{idea.get('strike', '-')}"
                    )
                else:
                    label = "SPOT"

                st.metric(
                    "Instrument",
                    label
                )

            if idea.get("expiry"):
                st.write(
                    f"**Expiry:** "
                    f"{expiry_label(idea['expiry'])}"
                )

            if idea.get("option_ltp") is not None:
                st.write(
                    f"**Option LTP:** "
                    f"{fmt(idea['option_ltp'])}"
                )

            st.markdown(
                f"""
                <div class="reason">
                <b>Why this trade:</b>
                {idea['why']}
                </div>
                """,
                unsafe_allow_html=True
            )

            st.write(
                f"**Invalidation:** {idea['invalidation']}"
            )

            st.write(
                "**Trailing SL:** T1 hit hone ke baad "
                "SL ko cost/previous swing ke around trail karein."
            )

            st.divider()

        # -------------------------------------------------
        # GEMINI EXPLANATION
        # -------------------------------------------------

        if GEMINI_API_KEY:

            with st.spinner(
                "AI explanation prepare ho rahi hai..."
            ):

                ai_text = ask_gemini(
                    ideas,
                    {
                        "underlying": underlying,
                        "market_open": market_open(),
                        "spot": spot,
                        "trend": market["trend"],
                        "momentum": market["momentum"],
                        "rsi": market["rsi"],
                        "adx": market["adx"],
                        "ema20": market["ema20"],
                        "ema50": market["ema50"],
                        "vwap": market["vwap"],
                        "pcr": pcr,
                    }
                )

            if ai_text:
                st.subheader(
                    "🤖 AI Explanation"
                )
                st.write(ai_text)

        else:
            st.info(
                "Gemini API key available nahi hai. "
                "Current trade ideas real market-data/technical "
                "analysis par based hain; fake AI text nahi banaya gaya."
            )

# =========================================================
# STATUS
# =========================================================

st.divider()

st.caption(
    "Paper Trading Only • No real orders • "
    "Market data unavailable hone par fabricated trade nahi banaya jata."
)
