import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, time
import traceback

# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Trading Expert Advisor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAPER_TRADING = True

# ============================================================
# IMPORTS
# ============================================================

try:
    from options_engine import OptionsEngine
except Exception as e:
    OptionsEngine = None
    OPTIONS_IMPORT_ERROR = str(e)

try:
    from telemetry_engine import TelemetryEngine
except Exception:
    TelemetryEngine = None

try:
    import config
except Exception:
    config = None


# ============================================================
# HELPERS
# ============================================================

def safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value == "":
                return default
        return float(value)
    except Exception:
        return default


def fmt_number(value, decimals=2):
    value = safe_float(value)
    if value is None:
        return "-"
    return f"{value:,.{decimals}f}"


def normalize_expiry(value):
    if value is None:
        return None

    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip().upper()

    for fmt in [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d%b%Y",
        "%d%b%y",
        "%d-%b-%Y",
        "%d-%b-%y",
    ]:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass

    return text


def expiry_display(value):
    normalized = normalize_expiry(value)

    if not normalized:
        return str(value)

    try:
        d = datetime.strptime(normalized, "%Y-%m-%d")
        return d.strftime("%d %b %Y")
    except Exception:
        return str(value)


def is_market_open():
    now = datetime.now()

    if now.weekday() >= 5:
        return False

    current = now.time()

    return time(9, 15) <= current <= time(15, 30)


def get_market_status():
    if is_market_open():
        return "🟢 MARKET OPEN"
    return "🔴 MARKET CLOSED"


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "selected_underlying": None,
    "selected_expiry": None,
    "selected_option_type": "CE",
    "last_refresh": None,
    "option_data": None,
    "greeks_data": None,
    "quote_data": None,
    "advisory": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# HEADER
# ============================================================

st.title("📊 AI Trading Expert Advisor")

st.caption(
    "Technical + Options + Greeks + OI + PCR + AI + After-Market Preparation"
)

status_col1, status_col2, status_col3 = st.columns(3)

with status_col1:
    st.metric("Trading Mode", "PAPER ONLY")

with status_col2:
    st.metric("Market", get_market_status())

with status_col3:
    st.metric(
        "Last Refresh",
        st.session_state.last_refresh.strftime("%H:%M:%S")
        if st.session_state.last_refresh
        else "-"
    )

st.warning(
    "⚠️ PAPER TRADING ONLY — इस application से कोई real order place नहीं होगा."
)


# ============================================================
# ENGINE INITIALIZATION
# ============================================================

@st.cache_resource(show_spinner=False)
def create_options_engine():
    if OptionsEngine is None:
        return None

    try:
        return OptionsEngine()
    except Exception:
        return None


engine = create_options_engine()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("⚙️ Expert Advisor")

if engine is None:
    st.sidebar.error("Options Engine unavailable")

    if "OPTIONS_IMPORT_ERROR" in globals():
        st.sidebar.caption(OPTIONS_IMPORT_ERROR)


# ============================================================
# GET AVAILABLE UNDERLYINGS
# ============================================================

def get_available_underlyings():
    """
    Dynamically discover index option underlyings from the
    Angel One scrip master through OptionsEngine.
    """

    preferred = [
        "NIFTY",
        "BANKNIFTY",
        "FINNIFTY",
        "MIDCPNIFTY",
        "SENSEX",
        "BANKEX",
    ]

    discovered = []

    # --------------------------------------------------------
    # Try engine master / contracts
    # --------------------------------------------------------

    try:
        if engine is not None:

            master = None

            for attr in [
                "scrip_master",
                "master_df",
                "master",
                "df",
                "scrip_df",
            ]:
                try:
                    obj = getattr(engine, attr, None)
                    if isinstance(obj, pd.DataFrame) and not obj.empty:
                        master = obj
                        break
                except Exception:
                    pass

            if master is not None:

                df = master.copy()

                if "instrumenttype" in df.columns:
                    df = df[
                        df["instrumenttype"]
                        .astype(str)
                        .str.upper()
                        .eq("OPTIDX")
                    ]

                if "name" in df.columns:

                    names = (
                        df["name"]
                        .dropna()
                        .astype(str)
                        .str.upper()
                        .str.strip()
                        .unique()
                        .tolist()
                    )

                    discovered.extend(names)

    except Exception:
        pass

    # --------------------------------------------------------
    # Try known common contracts
    # --------------------------------------------------------

    for symbol in preferred:
        try:
            if engine is not None:

                contracts = engine.get_option_contracts(
                    underlying=symbol
                )

                if contracts is not None:
                    if isinstance(contracts, pd.DataFrame):
                        if not contracts.empty:
                            discovered.append(symbol)
                    elif len(contracts) > 0:
                        discovered.append(symbol)

        except Exception:
            pass

    discovered = [
        str(x).upper().strip()
        for x in discovered
        if x
    ]

    # Unique
    discovered = list(dict.fromkeys(discovered))

    # Preferred symbols first
    ordered = []

    for symbol in preferred:
        if symbol in discovered:
            ordered.append(symbol)

    for symbol in discovered:
        if symbol not in ordered:
            ordered.append(symbol)

    # Always keep these if engine is working
    if not ordered and engine is not None:
        ordered = preferred.copy()

    return ordered


underlyings = get_available_underlyings()

if not underlyings:
    underlyings = [
        "NIFTY",
        "BANKNIFTY",
        "FINNIFTY",
        "MIDCPNIFTY",
        "SENSEX",
        "BANKEX",
    ]


# ============================================================
# UNDERLYING DROPDOWN
# ============================================================

default_underlying = st.session_state.selected_underlying

if default_underlying not in underlyings:
    default_underlying = underlyings[0]

selected_underlying = st.sidebar.selectbox(
    "Underlying",
    underlyings,
    index=underlyings.index(default_underlying),
)

st.session_state.selected_underlying = selected_underlying


# ============================================================
# EXPIRY DROPDOWN
# ============================================================

def get_expiry_list(symbol):
    expiries = []

    if engine is None:
        return expiries

    # First try new helper
    try:
        result = engine.get_expiry_options(symbol)

        if result:
            for item in result:

                if isinstance(item, dict):
                    value = item.get("value")
                    label = item.get("label", expiry_display(value))
                else:
                    value = item
                    label = expiry_display(item)

                if value:
                    expiries.append(
                        {
                            "value": normalize_expiry(value),
                            "label": label,
                        }
                    )
    except Exception:
        pass

    # Fallback
    if not expiries:
        try:
            result = engine.get_expiries(symbol)

            if result:
                for item in result:
                    value = normalize_expiry(item)

                    if value:
                        try:
                            d = datetime.strptime(
                                value,
                                "%Y-%m-%d"
                            ).date()

                            if d >= date.today():
                                expiries.append(
                                    {
                                        "value": value,
                                        "label": expiry_display(value),
                                    }
                                )
                        except Exception:
                            expiries.append(
                                {
                                    "value": value,
                                    "label": expiry_display(value),
                                }
                            )
        except Exception:
            pass

    # Remove duplicates
    final = []
    seen = set()

    for item in expiries:
        value = item["value"]

        if value and value not in seen:
            seen.add(value)
            final.append(item)

    # Sort
    try:
        final.sort(
            key=lambda x: datetime.strptime(
                x["value"],
                "%Y-%m-%d"
            )
        )
    except Exception:
        pass

    return final


expiry_items = get_expiry_list(selected_underlying)

if not expiry_items:
    st.sidebar.error(
        f"No expiry data available for {selected_underlying}"
    )

    selected_expiry = None

else:

    expiry_values = [
        item["value"]
        for item in expiry_items
    ]

    saved_expiry = st.session_state.selected_expiry

    if saved_expiry not in expiry_values:
        saved_expiry = expiry_values[0]

    expiry_index = expiry_values.index(saved_expiry)

    selected_expiry = st.sidebar.selectbox(
        "Option Expiry",
        expiry_values,
        index=expiry_index,
        format_func=lambda x: expiry_display(x),
    )

    st.session_state.selected_expiry = selected_expiry


# ============================================================
# OPTION TYPE
# ============================================================

selected_option_type = st.sidebar.selectbox(
    "Option Type",
    ["CE", "PE", "BOTH"],
    index=["CE", "PE", "BOTH"].index(
        st.session_state.selected_option_type
        if st.session_state.selected_option_type in ["CE", "PE", "BOTH"]
        else "CE"
    ),
)

st.session_state.selected_option_type = selected_option_type


# ============================================================
# REFRESH
# ============================================================

refresh = st.sidebar.button(
    "🔄 Refresh Market Data",
    use_container_width=True,
)

if refresh:
    st.session_state.last_refresh = datetime.now()
    st.cache_data.clear()
    st.rerun()


# ============================================================
# MARKET INFORMATION
# ============================================================

st.subheader("📌 Selected Contract")

info1, info2, info3, info4 = st.columns(4)

with info1:
    st.metric(
        "Underlying",
        selected_underlying,
    )

with info2:
    st.metric(
        "Expiry",
        expiry_display(selected_expiry)
        if selected_expiry
        else "-",
    )

with info3:
    st.metric(
        "Option",
        selected_option_type,
    )

with info4:
    st.metric(
        "Market",
        "OPEN" if is_market_open() else "CLOSED",
    )


# ============================================================
# SPOT PRICE
# ============================================================

def find_spot_contract(symbol):
    """
    Try to dynamically locate underlying spot contract.
    """

    if engine is None:
        return None

    # --------------------------------------------------------
    # Try engine master
    # --------------------------------------------------------

    master = None

    for attr in [
        "scrip_master",
        "master_df",
        "master",
        "df",
        "scrip_df",
    ]:

        try:
            obj = getattr(engine, attr, None)

            if isinstance(obj, pd.DataFrame) and not obj.empty:
                master = obj
                break

        except Exception:
            pass

    if master is None:
        return None

    df = master.copy()

    if "exchange" in df.columns:
        exchange_mask = (
            df["exchange"]
            .astype(str)
            .str.upper()
            .isin(["NSE", "BSE"])
        )
        df = df[exchange_mask]

    elif "exch_seg" in df.columns:
        exchange_mask = (
            df["exch_seg"]
            .astype(str)
            .str.upper()
            .isin(["NSE", "BSE"])
        )
        df = df[exchange_mask]

    # Try exact name
    if "name" in df.columns:

        exact = df[
            df["name"]
            .astype(str)
            .str.upper()
            .eq(symbol.upper())
        ]

        if not exact.empty:
            return exact.iloc[0]

    # Try symbol
    if "symbol" in df.columns:

        exact = df[
            df["symbol"]
            .astype(str)
            .str.upper()
            .str.startswith(symbol.upper())
        ]

        if not exact.empty:
            return exact.iloc[0]

    return None


def get_spot_price(symbol):
    if engine is None:
        return None

    contract = find_spot_contract(symbol)

    if contract is None:
        # Common NIFTY fallback
        if symbol == "NIFTY":
            token = "99926000"
            exchange = "NSE"

        elif symbol == "BANKNIFTY":
            token = "99926009"
            exchange = "NSE"

        elif symbol == "SENSEX":
            token = "99919000"
            exchange = "BSE"

        else:
            return None
    else:
        token = str(
            contract.get("token")
            if hasattr(contract, "get")
            else ""
        )

        exchange = str(
            contract.get("exch_seg", "NSE")
            if hasattr(contract, "get")
            else "NSE"
        )

    # Try engine methods
    for method_name in [
        "get_live_ltp",
        "get_ltp",
        "get_market_quote",
    ]:

        try:

            method = getattr(engine, method_name, None)

            if method is None:
                continue

            result = None

            # get_live_ltp style
            try:
                result = method(
                    exchange,
                    symbol,
                    token,
                )
            except Exception:
                pass

            if result is None:
                try:
                    result = method(
                        symbol,
                        token,
                    )
                except Exception:
                    pass

            if result is None:
                continue

            if isinstance(result, dict):

                for key in [
                    "ltp",
                    "LTP",
                    "last_traded_price",
                    "lastTradedPrice",
                    "close",
                    "price",
                ]:
                    if key in result:
                        value = safe_float(result[key])

                        if value is not None:
                            return value

                data = result.get("data")

                if isinstance(data, dict):

                    for key in [
                        "ltp",
                        "LTP",
                        "last_traded_price",
                        "lastTradedPrice",
                        "close",
                        "price",
                    ]:
                        if key in data:
                            value = safe_float(data[key])

                            if value is not None:
                                return value

    except Exception:
        pass

    return None


spot_price = get_spot_price(selected_underlying)


# ============================================================
# SPOT DISPLAY
# ============================================================

st.subheader("📈 Underlying Market")

spot_col1, spot_col2, spot_col3 = st.columns(3)

with spot_col1:
    st.metric(
        "Spot / LTP",
        fmt_number(spot_price),
    )

with spot_col2:
    st.metric(
        "Selected Expiry",
        expiry_display(selected_expiry)
        if selected_expiry
        else "-",
    )

with spot_col3:

    if spot_price:
        st.metric(
            "ATM Reference",
            fmt_number(round(spot_price / 50) * 50),
        )
    else:
        st.metric(
            "ATM Reference",
            "-",
        )


# ============================================================
# OPTION CONTRACTS
# ============================================================

def fetch_contracts(symbol, expiry):
    if engine is None:
        return pd.DataFrame()

    if not expiry:
        return pd.DataFrame()

    try:

        result = engine.get_option_contracts(
            underlying=symbol,
            expiry=expiry,
        )

        if isinstance(result, pd.DataFrame):
            return result.copy()

        if isinstance(result, list):
            return pd.DataFrame(result)

    except TypeError:

        try:
            result = engine.get_option_contracts(
                symbol,
                expiry,
            )

            if isinstance(result, pd.DataFrame):
                return result.copy()

            return pd.DataFrame(result)

        except Exception:
            pass

    except Exception:
        pass

    return pd.DataFrame()


contracts = fetch_contracts(
    selected_underlying,
    selected_expiry,
)


# ============================================================
# FILTER OPTION TYPE
# ============================================================

if not contracts.empty:

    if "option_type" in contracts.columns:

        if selected_option_type in ["CE", "PE"]:
            contracts = contracts[
                contracts["option_type"]
                .astype(str)
                .str.upper()
                .eq(selected_option_type)
            ]

    elif "symbol" in contracts.columns:

        if selected_option_type in ["CE", "PE"]:
            contracts = contracts[
                contracts["symbol"]
                .astype(str)
                .str.upper()
                .str.endswith(selected_option_type)
            ]


# ============================================================
# OPTION CHAIN
# ============================================================

st.subheader("⛓️ Option Chain")

if contracts.empty:

    st.info(
        "Option contracts अभी उपलब्ध नहीं हैं. "
        "Expiry/underlying selection और Angel One master data check करें."
    )

else:

    display_df = contracts.copy()

    # Numeric strike
    if "strike" in display_df.columns:
        display_df["strike"] = pd.to_numeric(
            display_df["strike"],
            errors="coerce",
        )

    # Sort
    if "strike" in display_df.columns:
        display_df = display_df.sort_values("strike")

    # Show relevant columns
    preferred_columns = [
        "symbol",
        "name",
        "strike",
        "option_type",
        "expiry_normalized",
        "expiry",
        "token",
        "exch_seg",
    ]

    columns = [
        c for c in preferred_columns
        if c in display_df.columns
    ]

    if columns:
        display_df = display_df[columns]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# OPTION CHAIN / QUOTES
# ============================================================

def fetch_option_chain(symbol, expiry):
    if engine is None:
        return None

    methods = [
        "get_option_chain",
        "analyze_strikes",
    ]

    for method_name in methods:

        try:

            method = getattr(engine, method_name, None)

            if method is None:
                continue

            try:
                result = method(
                    underlying=symbol,
                    expiry=expiry,
                )
            except Exception:

                try:
                    result = method(
                        symbol,
                        expiry,
                    )
                except Exception:
                    continue

            if result is not None:
                return result

        except Exception:
            continue

    return None


chain_result = fetch_option_chain(
    selected_underlying,
    selected_expiry,
)


# ============================================================
# PCR
# ============================================================

def calculate_pcr_from_contracts(df):
    if df is None or df.empty:
        return None

    oi_col = None

    for col in [
        "oi",
        "open_interest",
        "openInterest",
        "OI",
    ]:
        if col in df.columns:
            oi_col = col
            break

    if oi_col is None:
        return None

    option_col = None

    for col in [
        "option_type",
        "optionType",
        "instrument",
        "symbol",
    ]:
        if col in df.columns:
            option_col = col
            break

    if option_col is None:
        return None

    temp = df.copy()

    temp[oi_col] = pd.to_numeric(
        temp[oi_col],
        errors="coerce",
    ).fillna(0)

    types = (
        temp[option_col]
        .astype(str)
        .str.upper()
    )

    ce_oi = temp.loc[
        types.str.contains("CE"),
        oi_col,
    ].sum()

    pe_oi = temp.loc[
        types.str.contains("PE"),
        oi_col,
    ].sum()

    if ce_oi <= 0:
        return None

    return pe_oi / ce_oi


pcr_value = calculate_pcr_from_contracts(contracts)


# ============================================================
# OPTIONS SUMMARY
# ============================================================

st.subheader("📊 Options Intelligence")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric(
        "PCR",
        f"{pcr_value:.2f}"
        if pcr_value is not None
        else "Unavailable",
    )

with c2:
    st.metric(
        "Contracts",
        len(contracts),
    )

with c3:
    st.metric(
        "Underlying",
        selected_underlying,
    )

with c4:
    st.metric(
        "Expiry",
        expiry_display(selected_expiry)
        if selected_expiry
        else "-",
    )


# ============================================================
# GREEKS
# ============================================================

st.subheader("🧮 Option Greeks")

def fetch_greeks(symbol, expiry):
    if engine is None:
        return None

    try:

        method = getattr(
            engine,
            "get_option_greeks",
            None,
        )

        if method is None:
            return None

        try:
            return method(
                underlying=symbol,
                expiry=expiry,
            )
        except Exception:

            try:
                return method(
                    symbol,
                    expiry,
                )
            except Exception:
                return None

    except Exception:
        return None


greeks = fetch_greeks(
    selected_underlying,
    selected_expiry,
)

if greeks is None:

    st.info(
        "Greeks data अभी available नहीं है."
    )

else:

    if isinstance(greeks, pd.DataFrame):

        if greeks.empty:
            st.info("Greeks data empty है.")

        else:
            st.dataframe(
                greeks,
                use_container_width=True,
                hide_index=True,
            )

    elif isinstance(greeks, list):

        if len(greeks) > 0:
            st.dataframe(
                pd.DataFrame(greeks),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Greeks data empty है.")

    elif isinstance(greeks, dict):

        st.json(greeks)

    else:
        st.write(greeks)


# ============================================================
# OI BUILDUP
# ============================================================

st.subheader("📌 OI Buildup")

def fetch_oi(symbol, expiry):
    if engine is None:
        return None

    for method_name in [
        "get_all_oi_buildup",
        "get_oi_buildup",
    ]:

        try:

            method = getattr(
                engine,
                method_name,
                None,
            )

            if method is None:
                continue

            try:
                result = method(
                    underlying=symbol,
                    expiry=expiry,
                )
            except Exception:

                try:
                    result = method(
                        symbol,
                        expiry,
                    )
                except Exception:
                    continue

            if result is not None:
                return result

        except Exception:
            continue

    return None


oi_result = fetch_oi(
    selected_underlying,
    selected_expiry,
)

if oi_result is None:

    st.info(
        "OI buildup data unavailable."
    )

else:

    if isinstance(oi_result, pd.DataFrame):

        st.dataframe(
            oi_result,
            use_container_width=True,
            hide_index=True,
        )

    elif isinstance(oi_result, list):

        st.dataframe(
            pd.DataFrame(oi_result),
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.json(oi_result)
        

# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

st.subheader("📈 Technical Analysis")

technical_columns = st.columns(6)

technical_values = [
    ("RSI", "-"),
    ("ADX", "-"),
    ("VWAP", "-"),
    ("EMA 20", "-"),
    ("MACD", "-"),
    ("Trend", "WAITING"),
]

for column, (label, value) in zip(
    technical_columns,
    technical_values,
):
    with column:
        st.metric(label, value)


st.caption(
    "Technical engine connected होने पर RSI, ADX, VWAP, EMA, MACD, "
    "support/resistance और momentum यहाँ populate होंगे."
)


# ============================================================
# AI EXPERT ADVISORY
# ============================================================

st.subheader("🤖 AI Expert Advisory")

if not is_market_open():

    st.info(
        "🌙 Market closed है — After-Market Expert Advisor active है. "
        "Selected expiry के लिए next-session preparation यहाँ की जा सकती है."
    )

else:

    st.info(
        "🟢 Market open है — live/paper-trading analysis mode."
    )


# ============================================================
# RULE BASED ADVISORY
# ============================================================

def build_advisory(
    symbol,
    expiry,
    option_type,
    spot,
    contracts_df,
    pcr,
):

    if spot is None:
        return {
            "signal": "WAITING",
            "confidence": 0,
            "reason": "Underlying LTP unavailable",
        }

    reasons = []

    signal = "WAIT"

    # --------------------------------------------------------
    # PCR
    # --------------------------------------------------------

    if pcr is not None:

        if pcr > 1.20:
            reasons.append(
                "PCR relatively high"
            )

        elif pcr < 0.80:
            reasons.append(
                "PCR relatively low"
            )

        else:
            reasons.append(
                "PCR neutral zone"
            )

    # --------------------------------------------------------
    # Basic expiry awareness
    # --------------------------------------------------------

    expiry_text = expiry_display(expiry)

    reasons.append(
        f"Selected expiry: {expiry_text}"
    )

    reasons.append(
        f"Underlying: {symbol}"
    )

    # --------------------------------------------------------
    # No automatic trade call
    # --------------------------------------------------------

    if option_type == "CE":

        if pcr is not None and pcr > 1.20:
            signal = "CE WATCH"
        else:
            signal = "CE WAIT"

    elif option_type == "PE":

        if pcr is not None and pcr < 0.80:
            signal = "PE WATCH"
        else:
            signal = "PE WAIT"

    else:

        signal = "WAIT"

    confidence = 50

    if pcr is not None:
        confidence += 10

    return {
        "signal": signal,
        "confidence": min(confidence, 100),
        "reason": " | ".join(reasons),
    }


advisory = build_advisory(
    selected_underlying,
    selected_expiry,
    selected_option_type,
    spot_price,
    contracts,
    pcr_value,
)

st.session_state.advisory = advisory


adv1, adv2, adv3 = st.columns(3)

with adv1:
    st.metric(
        "EA Signal",
        advisory["signal"],
    )

with adv2:
    st.metric(
        "Confidence",
        f'{advisory["confidence"]}%',
    )

with adv3:
    st.metric(
        "Mode",
        "PAPER",
    )

st.write(
    f"**Reason:** {advisory['reason']}"
)


# ============================================================
# AFTER MARKET PLAN
# ============================================================

st.subheader("🌙 After-Market Trade Preparation")

if not is_market_open():

    st.success(
        "After-market planning enabled."
    )

else:

    st.info(
        "Market open है. After-market section current selected expiry "
        "को continuously monitor कर सकता है."
    )


plan_col1, plan_col2 = st.columns(2)

with plan_col1:

    st.markdown("### 📋 Tomorrow / Future Plan")

    st.write(
        f"**Underlying:** {selected_underlying}"
    )

    st.write(
        f"**Expiry:** "
        f"{expiry_display(selected_expiry) if selected_expiry else '-'}"
    )

    st.write(
        f"**Option:** {selected_option_type}"
    )

    st.write(
        f"**Reference Spot:** {fmt_number(spot_price)}"
    )


with plan_col2:

    st.markdown("### 🎯 EA Checklist")

    st.write("☐ Trend confirmation")
    st.write("☐ Support / Resistance")
    st.write("☐ RSI / ADX confirmation")
    st.write("☐ VWAP / EMA confirmation")
    st.write("☐ OI buildup")
    st.write("☐ PCR")
    st.write("☐ Greeks")
    st.write("☐ Risk / Reward")
    st.write("☐ Expiry risk")
    st.write("☐ News / Sentiment")


# ============================================================
# RISK MANAGEMENT
# ============================================================

st.subheader("🛡️ Risk Management")

risk1, risk2, risk3, risk4 = st.columns(4)

with risk1:
    st.metric("Trading Mode", "PAPER")

with risk2:
    st.metric(
        "Max Daily Loss",
        "₹2,000",
    )

with risk3:
    st.metric(
        "Max Trades",
        "5",
    )

with risk4:
    st.metric(
        "Real Orders",
        "DISABLED",
    )


st.warning(
    "⚠️ EA किसी भी स्थिति में इस UI से real order execute नहीं करेगा."
)


# ============================================================
# SYSTEM STATUS
# ============================================================

st.subheader("🔧 System Status")

s1, s2, s3, s4 = st.columns(4)

with s1:
    st.metric(
        "Paper Trading",
        "ON",
    )

with s2:

    st.metric(
        "Angel One",
        "CONNECTED"
        if engine is not None
        else "CHECK",
    )

with s3:

    st.metric(
        "Options Engine",
        "READY"
        if engine is not None
        else "ERROR",
    )

with s4:

    st.metric(
        "AI",
        "READY"
        if config is not None
        else "CHECK",
    )


# ============================================================
# DEBUG
# ============================================================

with st.expander("🔍 Technical Debug Information"):

    st.write(
        "Underlying:",
        selected_underlying,
    )

    st.write(
        "Expiry:",
        selected_expiry,
    )

    st.write(
        "Option Type:",
        selected_option_type,
    )

    st.write(
        "Contracts:",
        len(contracts),
    )

    st.write(
        "Spot:",
        spot_price,
    )

    st.write(
        "Market:",
        "OPEN" if is_market_open() else "CLOSED",
    )

    if engine is None:
        st.error(
            "OptionsEngine initialize नहीं हुआ."
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "AI Trading Expert Advisor • Paper Trading Only • "
    "No Real Orders • Options + Technical + AI Research"
)
