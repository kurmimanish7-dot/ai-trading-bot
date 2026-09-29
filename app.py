import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, time

# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="AI Trading Expert Advisor",
    page_icon="📊",
    layout="wide",
)

PAPER_TRADING = True

st.markdown("""
<style>
@media (max-width: 768px) {

    /* Main content ko mobile width use karne do */
    .block-container {
        padding-left: 0.65rem !important;
        padding-right: 0.65rem !important;
        max-width: 100% !important;
    }

    /* Columns ko zabardasti 47% me mat squeeze karo */
    [data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-wrap: wrap !important;
        width: 100% !important;
        gap: 0.45rem !important;
    }

    [data-testid="column"] {
        min-width: 48% !important;
        width: 48% !important;
        flex: 1 1 48% !important;
    }

    /* Metric card */
    [data-testid="stMetric"] {
        width: 100% !important;
        min-width: 0 !important;
        overflow: visible !important;
    }

    [data-testid="stMetricLabel"] {
        font-size: 10px !important;
        line-height: 1.15 !important;
        white-space: normal !important;
        overflow: visible !important;
    }

    [data-testid="stMetricValue"] {
        font-size: 18px !important;
        line-height: 1.15 !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        word-break: normal !important;
    }

    [data-testid="stMetricDelta"] {
        font-size: 10px !important;
        white-space: normal !important;
    }

    /* Headings */
    h1 {
        font-size: 27px !important;
        line-height: 1.08 !important;
        word-break: normal !important;
    }

    h2 {
        font-size: 21px !important;
        line-height: 1.15 !important;
    }

    h3 {
        font-size: 18px !important;
        line-height: 1.15 !important;
    }

    /* Normal text */
    p, label, div {
        word-break: normal !important;
    }

    /* Tables */
    [data-testid="stDataFrame"] {
        width: 100% !important;
        overflow-x: auto !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# IMPORTS
# ============================================================

try:
    from options_engine import OptionsEngine
except Exception as e:
    OptionsEngine = None
    OPTIONS_ERROR = str(e)

try:
    from telemetry_engine import TelemetryEngine
except Exception as e:
    TelemetryEngine = None
    TELEMETRY_ERROR = str(e)

# ============================================================
# HELPERS
# ============================================================

def sf(x, default=None):
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace(",", "").strip()
            if not x:
                return default
        return float(x)
    except Exception:
        return default


def fmt(x, d=2):
    x = sf(x)
    return "-" if x is None else f"{x:,.{d}f}"


def expiry_norm(x):
    if x is None:
        return None

    if isinstance(x, (datetime, date)):
        return x.strftime("%Y-%m-%d")

    s = str(x).strip().upper()

    for f in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d%b%Y",
        "%d-%b-%Y",
        "%d%b%y",
        "%d-%b-%y",
    ):
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except Exception:
            pass

    return s


def expiry_label(x):
    n = expiry_norm(x)

    if not n:
        return str(x)

    try:
        return datetime.strptime(
            n, "%Y-%m-%d"
        ).strftime("%d %b %Y")
    except Exception:
        return str(x)


def market_open():
    now = datetime.now()

    if now.weekday() >= 5:
        return False

    return time(9, 15) <= now.time() <= time(15, 30)


# ============================================================
# SECRETS
# ============================================================

def secret(name):
    try:
        value = st.secrets.get(name)
        return str(value).strip() if value else ""
    except Exception:
        return ""


ANGEL_API_KEY = secret("ANGEL_API_KEY")
ANGEL_CLIENT_CODE = secret("ANGEL_CLIENT_CODE")
ANGEL_PIN = secret("ANGEL_PIN")
ANGEL_TOTP_SECRET = secret("ANGEL_TOTP_SECRET")
ANGEL_JWT_TOKEN = secret("ANGEL_JWT_TOKEN")


# ============================================================
# CREATE TELEMETRY
# ============================================================

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


telemetry = create_telemetry()


# ============================================================
# CREATE OPTIONS ENGINE
# ============================================================

@st.cache_resource(show_spinner=False)
def create_options():
    if OptionsEngine is None:
        return None

    # OptionsEngine needs JWT.
    # First use explicitly stored JWT if available.
    if ANGEL_JWT_TOKEN:
        try:
            return OptionsEngine(
                jwt_token=ANGEL_JWT_TOKEN,
                api_key=ANGEL_API_KEY,
                client_code=ANGEL_CLIENT_CODE,
            )
        except Exception:
            pass

    # If JWT is not stored, use TelemetryEngine's
    # SmartAPI session and feed the generated auth token.
    if telemetry is not None:
        try:
            smart_api = telemetry.smart_api

            session = getattr(
    smart_api,
    "access_token",
    None,
            )

            if session:
                return OptionsEngine(
                    jwt_token=str(session),
                    api_key=ANGEL_API_KEY,
                    client_code=ANGEL_CLIENT_CODE,
                )
        except Exception:
            pass

    return None


options = create_options()


# ============================================================
# HEADER
# ============================================================

st.title("📊 AI Trading Expert Advisor")

st.caption(
    "Options + Technical Analysis + Greeks + OI + PCR + "
    "Expiry Risk + After-Market Preparation"
)

h1, h2, h3 = st.columns(3)

with h1:
    st.metric("Mode", "PAPER ONLY")

with h2:
    st.metric(
        "Market",
        "OPEN" if market_open() else "CLOSED",
    )

with h3:
    st.metric(
        "Angel One",
        "CONNECTED"
        if telemetry is not None
        else "CHECK",
    )

st.warning(
    "⚠️ PAPER TRADING ONLY — कोई real order place नहीं होगा."
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("⚙️ Expert Advisor")


# ============================================================
# UNDERLYINGS
# ============================================================

UNDERLYINGS = [
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "SENSEX",
    "BANKEX",
]

saved_underlying = st.session_state.get(
    "underlying",
    "NIFTY",
)

if saved_underlying not in UNDERLYINGS:
    saved_underlying = "NIFTY"

underlying = st.sidebar.selectbox(
    "Underlying",
    UNDERLYINGS,
    index=UNDERLYINGS.index(
        saved_underlying
    ),
)

st.session_state["underlying"] = underlying


# ============================================================
# EXPIRIES
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_expiries(symbol):

    if options is None:
        return []

    try:
        result = options.get_expiry_options(
            symbol
        )

        values = []

        for item in result or []:

            if isinstance(item, dict):
                value = item.get("value")
            else:
                value = item

            value = expiry_norm(value)

            if value:
                try:
                    d = datetime.strptime(
                        value,
                        "%Y-%m-%d",
                    ).date()

                    if d >= date.today():
                        values.append(value)

                except Exception:
                    pass

        return sorted(
            list(set(values))
        )

    except Exception:
        return []


expiries = load_expiries(
    underlying
)

if not expiries:
    st.sidebar.error(
        "Expiry data unavailable"
    )
    selected_expiry = None
else:

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

    st.session_state["expiry"] = selected_expiry


# ============================================================
# OPTION TYPE
# ============================================================

old_type = st.session_state.get(
    "option_type",
    "CE",
)

if old_type not in [
    "CE",
    "PE",
    "BOTH",
]:
    old_type = "CE"

option_type = st.sidebar.selectbox(
    "Option Type",
    ["CE", "PE", "BOTH"],
    index=[
        "CE",
        "PE",
        "BOTH",
    ].index(old_type),
)

st.session_state["option_type"] = option_type


# ============================================================
# REFRESH
# ============================================================

if st.sidebar.button(
    "🔄 Refresh",
    use_container_width=True,
):
    st.cache_data.clear()
    st.session_state["last_refresh"] = (
        datetime.now()
    )
    st.rerun()


# ============================================================
# SELECTED CONTRACT
# ============================================================

st.subheader("📌 Selected Contract")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric(
        "Underlying",
        underlying,
    )

with c2:
    st.metric(
        "Expiry",
        expiry_label(
            selected_expiry
        )
        if selected_expiry
        else "-",
    )

with c3:
    st.metric(
        "Option",
        option_type,
    )

with c4:
    st.metric(
        "Session",
        "LIVE"
        if market_open()
        else "AFTER MARKET",
    )


# ============================================================
# SPOT
# ============================================================

SPOT_TOKENS = {
    "NIFTY": ("NSE", "99926000"),
    "BANKNIFTY": ("NSE", "99926009"),
    "SENSEX": ("BSE", "99919000"),
}


def get_spot(symbol):

    if telemetry is None:
        return None

    exchange, token = SPOT_TOKENS.get(
        symbol,
        ("NSE", None),
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

                return sf(
                    result.get("ltp")
                )

    except Exception:
        pass

    return None


spot = get_spot(
    underlying
)


# ============================================================
# SPOT DISPLAY
# ============================================================

st.subheader("📈 Underlying")

s1, s2, s3 = st.columns(3)

with s1:
    st.metric(
        "LTP",
        fmt(spot),
    )

with s2:

    if spot:
        atm = round(
            spot / 50
        ) * 50
        st.metric(
            "ATM Reference",
            fmt(atm, 0),
        )
    else:
        st.metric(
            "ATM Reference",
            "-",
        )

with s3:
    st.metric(
        "Expiry Count",
        len(expiries),
    )


# ============================================================
# OPTION CONTRACTS
# ============================================================

@st.cache_data(ttl=120, show_spinner=False)
def load_contracts(
    symbol,
    expiry,
):

    if options is None or not expiry:
        return pd.DataFrame()

    try:
        return options.get_option_contracts(
            underlying=symbol,
            expiry_date=expiry,
        )
    except Exception:
        return pd.DataFrame()


contracts = load_contracts(
    underlying,
    selected_expiry,
)


# ============================================================
# NEAR ATM
# ============================================================

if (
    spot is not None
    and not contracts.empty
):

    try:

        near_atm = (
            options.get_near_atm_contracts(
                underlying=underlying,
                expiry_date=selected_expiry,
                spot_price=spot,
                strikes_each_side=5,
            )
        )

    except Exception:
        near_atm = contracts.copy()

else:
    near_atm = contracts.copy()


# ============================================================
# FILTER
# ============================================================

if not near_atm.empty:

    if option_type in [
        "CE",
        "PE",
    ]:

        near_atm = near_atm[
            near_atm[
                "option_type"
            ]
            .astype(str)
            .str.upper()
            == option_type
        ].copy()


# ============================================================
# LIVE OPTION QUOTES
# ============================================================

if (
    options is not None
    and not near_atm.empty
):

    try:
        chain = options.get_market_quote(
            near_atm
        )
    except Exception:
        chain = near_atm.copy()

else:
    chain = pd.DataFrame()


# ============================================================
# OPTION CHAIN
# ============================================================

st.subheader("⛓️ Option Chain")

if chain.empty:

    st.info(
        "Option chain data unavailable."
    )

else:

    show_cols = [
        "symbol",
        "strike",
        "option_type",
        "expiry_normalized",
        "token",
        "ltp",
        "open",
        "high",
        "low",
        "close",
        "tradeVolume",
        "opnInterest",
    ]

    cols = [
        c for c in show_cols
        if c in chain.columns
    ]

    display = chain[cols].copy()

    if "strike" in display.columns:
        display["strike"] = pd.to_numeric(
            display["strike"],
            errors="coerce",
        )

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# PCR
# ============================================================

def calculate_pcr(df):

    if (
        df is None
        or df.empty
        or "opnInterest"
        not in df.columns
        or "option_type"
        not in df.columns
    ):
        return None

    work = df.copy()

    work["opnInterest"] = pd.to_numeric(
        work["opnInterest"],
        errors="coerce",
    ).fillna(0)

    ce = work.loc[
        work["option_type"].eq("CE"),
        "opnInterest",
    ].sum()

    pe = work.loc[
        work["option_type"].eq("PE"),
        "opnInterest",
    ].sum()

    if ce <= 0:
        return None

    return pe / ce


pcr = calculate_pcr(
    chain
)


# ============================================================
# OPTIONS INTELLIGENCE
# ============================================================

st.subheader(
    "📊 Options Intelligence"
)

o1, o2, o3, o4 = st.columns(4)

with o1:
    st.metric(
        "PCR",
        f"{pcr:.2f}"
        if pcr is not None
        else "Unavailable",
    )

with o2:
    st.metric(
        "Contracts",
        len(chain),
    )

with o3:
    st.metric(
        "Expiry",
        expiry_label(
            selected_expiry
        )
        if selected_expiry
        else "-",
    )

with o4:
    st.metric(
        "Spot",
        fmt(spot),
    )


# ============================================================
# GREEKS
# ============================================================

st.subheader("🧮 Option Greeks")

if (
    options is None
    or not selected_expiry
):

    st.info(
        "Greeks unavailable."
    )

else:

    try:

        greek_rows = (
            options.get_option_greeks(
                underlying,
                selected_expiry,
            )
        )

        greek_df = pd.DataFrame(
            greek_rows or []
        )

        if greek_df.empty:
            st.info(
                "Greeks data unavailable."
            )
        else:

            greek_cols = [
                "tradingSymbol",
                "symbol",
                "strikePrice",
                "optionType",
                "delta",
                "gamma",
                "theta",
                "vega",
                "impliedVolatility",
                "tradeVolume",
            ]

            cols = [
                c for c in greek_cols
                if c in greek_df.columns
            ]

            st.dataframe(
                greek_df[cols]
                if cols
                else greek_df,
                use_container_width=True,
                hide_index=True,
            )

    except Exception as e:

        st.info(
            f"Greeks unavailable: {e}"
        )


# ============================================================
# OI BUILDUP
# ============================================================

st.subheader("📌 OI Buildup")

if options is None:

    st.info(
        "Options engine unavailable."
    )

else:

    oi_tabs = st.tabs([
        "Long Built Up",
        "Short Built Up",
        "Short Covering",
        "Long Unwinding",
    ])

    oi_types = [
        "Long Built Up",
        "Short Built Up",
        "Short Covering",
        "Long Unwinding",
    ]

    for tab, oi_type in zip(
        oi_tabs,
        oi_types,
    ):

        with tab:

            try:

                rows = options.get_oi_buildup(
                    expiry_type="NEAR",
                    data_type=oi_type,
                )

                df = pd.DataFrame(
                    rows or []
                )

                if df.empty:
                    st.info(
                        "Data unavailable."
                    )
                else:
                    st.dataframe(
                        df,
                        use_container_width=True,
                        hide_index=True,
                    )

            except Exception:
                st.info(
                    "OI buildup data unavailable."
                )


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

st.subheader(
    "📈 Technical Analysis"
)

TECH_TOKENS = {
    "NIFTY": (
        "NSE",
        "99926000",
    ),
    "BANKNIFTY": (
        "NSE",
        "99926009",
    ),
}


@st.cache_data(ttl=120, show_spinner=False)
def technical_data(
    symbol,
):

    if telemetry is None:
        return None

    if symbol not in TECH_TOKENS:
        return None

    exchange, token = TECH_TOKENS[
        symbol
    ]

    try:

        df = telemetry.fetch_ohlcv(
            exchange=exchange,
            token=token,
            interval="FIVE_MINUTE",
            days=5,
        )

        if df.empty:
            return None

        rsi = telemetry.calculate_rsi(
            df["close"]
        )

        atr = telemetry.calculate_atr(
            df
        )

        ema9 = telemetry.calculate_ema(
            df["close"],
            9,
        )

        ema21 = telemetry.calculate_ema(
            df["close"],
            21,
        )

        ema50 = telemetry.calculate_ema(
            df["close"],
            50,
        )

        adx = telemetry.calculate_adx(
            df
        )

        vwap = telemetry.calculate_vwap(
            df
        )

        supertrend = (
            telemetry.calculate_supertrend(
                df
            )
        )

        last = df.iloc[-1]

        return {
            "close": sf(
                last["close"]
            ),
            "rsi": sf(
                rsi.iloc[-1]
            ),
            "atr": sf(
                atr.iloc[-1]
            ),
            "ema9": sf(
                ema9.iloc[-1]
            ),
            "ema21": sf(
                ema21.iloc[-1]
            ),
            "ema50": sf(
                ema50.iloc[-1]
            ),
            "adx": sf(
                adx.iloc[-1]
            ),
            "vwap": sf(
                vwap.iloc[-1]
            ),
            "supertrend": (
                "BULLISH"
                if supertrend.iloc[-1] == 1
                else "BEARISH"
            ),
        }

    except Exception:
        return None


tech = technical_data(
    underlying
)


if tech is None:

    st.info(
        "Technical data unavailable."
    )

else:

    t1, t2, t3, t4, t5, t6 = (
        st.columns(6)
    )

    with t1:
        st.metric(
            "RSI",
            fmt(tech["rsi"]),
        )

    with t2:
        st.metric(
            "ADX",
            fmt(tech["adx"]),
        )

    with t3:
        st.metric(
            "VWAP",
            fmt(tech["vwap"]),
        )

    with t4:
        st.metric(
            "EMA 9",
            fmt(tech["ema9"]),
        )

    with t5:
        st.metric(
            "EMA 21",
            fmt(tech["ema21"]),
        )

    with t6:
        st.metric(
            "Trend",
            tech["supertrend"],
        )


# ============================================================
# EXPERT ADVISOR
# ============================================================

st.subheader(
    "🤖 Expert Advisor"
)

signal = "WAIT"
confidence = 0
reasons = []


if tech is not None:

    if (
        tech["ema9"] is not None
        and tech["ema21"] is not None
    ):

        if tech["ema9"] > tech["ema21"]:
            reasons.append(
                "Short EMA above EMA21"
            )
        else:
            reasons.append(
                "Short EMA below EMA21"
            )

    if (
        tech["rsi"] is not None
    ):

        if tech["rsi"] > 60:
            reasons.append(
                "RSI bullish zone"
            )
        elif tech["rsi"] < 40:
            reasons.append(
                "RSI bearish zone"
            )
        else:
            reasons.append(
                "RSI neutral"
            )

    if (
        tech["adx"] is not None
    ):

        if tech["adx"] >= 25:
            reasons.append(
                "Trend strength elevated"
            )
        else:
            reasons.append(
                "Trend strength weak/range"
            )

    if tech["supertrend"] == "BULLISH":
        signal = "BULLISH WATCH"
    elif tech["supertrend"] == "BEARISH":
        signal = "BEARISH WATCH"

    confidence = 50

    if pcr is not None:
        confidence += 10

    if tech["adx"] is not None:
        confidence += 10

else:

    reasons.append(
        "Technical data unavailable"
    )


a1, a2, a3 = st.columns(3)

with a1:
    st.metric(
        "EA Signal",
        signal,
    )

with a2:
    st.metric(
        "Confidence",
        f"{min(confidence, 100)}%",
    )

with a3:
    st.metric(
        "Execution",
        "DISABLED",
    )

st.write(
    "**Analysis:** "
    + (
        " | ".join(reasons)
        if reasons
        else "Waiting for data"
    )
)


# ============================================================
# AFTER MARKET
# ============================================================

st.subheader(
    "🌙 After-Market Preparation"
)

if market_open():

    st.info(
        "Market open — live/paper analysis mode."
    )

else:

    st.success(
        "Market closed — After-Market Expert Advisor active."
    )

st.markdown(
    f"""
**Next-session preparation**

- Underlying: **{underlying}**
- Selected expiry: **{expiry_label(selected_expiry) if selected_expiry else "-"}**
- Option side: **{option_type}**
- Reference spot: **{fmt(spot)}**
- Current EA state: **{signal}**

### Pre-trade checklist

☐ Trend confirmation  
☐ Multi-timeframe confirmation  
☐ Support / resistance  
☐ RSI / ADX  
☐ VWAP / EMA  
☐ OI buildup  
☐ PCR  
☐ Delta / Gamma / Theta  
☐ India VIX  
☐ News / sentiment  
☐ Risk / reward  
☐ Expiry risk
"""
)


# ============================================================
# RISK
# ============================================================

st.subheader(
    "🛡️ Risk Controls"
)

r1, r2, r3, r4 = st.columns(4)

with r1:
    st.metric(
        "Paper Trading",
        "ON",
    )

with r2:
    st.metric(
        "Max Daily Loss",
        "₹2,000",
    )

with r3:
    st.metric(
        "Max Trades",
        "5",
    )

with r4:
    st.metric(
        "Real Orders",
        "OFF",
    )


# ============================================================
# STATUS
# ============================================================

with st.expander(
    "🔧 System Status"
):

    st.write(
        "Options Engine:",
        "READY"
        if options is not None
        else "CHECK",
    )

    st.write(
        "Telemetry Engine:",
        "READY"
        if telemetry is not None
        else "CHECK",
    )

    st.write(
        "Expiry Count:",
        len(expiries),
    )

    st.write(
        "Selected Expiry:",
        selected_expiry,
    )

    st.write(
        "Market:",
        "OPEN"
        if market_open()
        else "CLOSED",
    )

    if OptionsEngine is None:
        st.error(
            f"Options import error: "
            f"{OPTIONS_ERROR}"
        )

    if TelemetryEngine is None:
        st.error(
            f"Telemetry import error: "
            f"{TELEMETRY_ERROR}"
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "AI Trading Expert Advisor • "
    "PAPER TRADING ONLY • NO REAL ORDERS"
)
