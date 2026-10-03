import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dtime
import json
import requests
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

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

/* ---------- MAIN CONTAINER ---------- */

.block-container{
    padding-top:1rem!important;
    padding-left:.7rem!important;
    padding-right:.7rem!important;
    max-width:100%!important;
}


/* ---------- MOBILE ---------- */

@media(max-width:768px){

    /* Columns */
    [data-testid="stHorizontalBlock"]{
        flex-wrap:wrap!important;
        gap:.45rem!important;
        width:100%!important;
    }

    [data-testid="column"]{
        min-width:48%!important;
        max-width:48%!important;
        flex:1 1 48%!important;
        width:48%!important;
        min-height:0!important;
    }

    /* Metric box */
    [data-testid="stMetric"]{
        width:100%!important;
        min-width:0!important;
        max-width:100%!important;
        overflow:visible!important;
    }

    /* Metric label */
    [data-testid="stMetricLabel"]{
        width:100%!important;
        max-width:100%!important;
        font-size:11px!important;
        line-height:1.25!important;
        white-space:normal!important;
        overflow:visible!important;
        text-overflow:clip!important;
        overflow-wrap:anywhere!important;
        word-break:break-word!important;
    }

    [data-testid="stMetricLabel"] > div{
        width:100%!important;
        max-width:100%!important;
        white-space:normal!important;
        overflow:visible!important;
        text-overflow:clip!important;
        overflow-wrap:anywhere!important;
        word-break:break-word!important;
    }

    /* Metric value */
    [data-testid="stMetricValue"]{
        width:100%!important;
        max-width:100%!important;
        min-width:0!important;
        font-size:clamp(14px,5vw,18px)!important;
        line-height:1.25!important;
        white-space:normal!important;
        overflow:visible!important;
        text-overflow:clip!important;
        overflow-wrap:anywhere!important;
        word-break:break-word!important;
    }

    [data-testid="stMetricValue"] > div{
        width:100%!important;
        max-width:100%!important;
        min-width:0!important;
        white-space:normal!important;
        overflow:visible!important;
        text-overflow:clip!important;
        overflow-wrap:anywhere!important;
        word-break:break-word!important;
    }

    /* Metric delta */
    [data-testid="stMetricDelta"]{
        max-width:100%!important;
        white-space:normal!important;
        overflow:visible!important;
        overflow-wrap:anywhere!important;
        word-break:break-word!important;
    }

    /* Headings */
    h1{
        font-size:25px!important;
        line-height:1.2!important;
        overflow-wrap:anywhere!important;
    }

    h2{
        font-size:21px!important;
        line-height:1.25!important;
        overflow-wrap:anywhere!important;
    }

    h3{
        font-size:18px!important;
        line-height:1.3!important;
        overflow-wrap:anywhere!important;
    }

    /* Tables / dataframes */
    [data-testid="stDataFrame"]{
        width:100%!important;
        max-width:100%!important;
        overflow-x:auto!important;
    }

    /* Text */
    p, span, div{
        overflow-wrap:anywhere;
        word-break:normal;
    }

    /* Trade cards */
    .trade-card{
        width:100%!important;
        max-width:100%!important;
        box-sizing:border-box!important;
        padding:.75rem!important;
        overflow-wrap:anywhere!important;
        word-break:break-word!important;
    }
}


/* ---------- TRADE CARD ---------- */

.trade-card{
    width:100%;
    box-sizing:border-box;
    border:1px solid rgba(128,128,128,.30);
    border-radius:12px;
    padding:1rem;
    margin:.5rem 0;
    overflow-wrap:anywhere;
}


/* ---------- SMALL TEXT ---------- */

.small{
    font-size:.88rem;
    opacity:.85;
    overflow-wrap:anywhere;
    word-break:break-word;
}


/* ---------- REASON TEXT ---------- */

.reason{
    line-height:1.5;
    overflow-wrap:anywhere;
    word-break:break-word;
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
        value = st.secrets.get(name)
        return str(value).strip() if value else ""
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

    if x is None or not np.isfinite(x):
        return "-"

    return f"{x:,.{digits}f}"


def safe_text(x):
    return str(x) if x is not None else ""


def market_open():
    """
    NSE market status in IST.

    Normal equity/derivatives session:
    Monday-Friday, 09:15 to 15:30.

    NSE holidays are treated as CLOSED.
    """

    now = datetime.now(IST)

    # Saturday / Sunday
    if now.weekday() >= 5:
        return False

    # NSE trading holidays
    NSE_HOLIDAYS = {
        "2026-01-26",  # Republic Day
        "2026-03-03",  # Holi
        "2026-03-26",  # Ram Navami
        "2026-03-31",  # Mahavir Jayanti
        "2026-04-03",  # Good Friday
        "2026-04-14",  # Ambedkar Jayanti
        "2026-05-01",  # Maharashtra Day
        "2026-06-26",  # Bakri Id
        "2026-08-15",  # Independence Day
        "2026-08-26",  # Janmashtami
        "2026-09-14",  # Ganesh Chaturthi
        "2026-10-02",  # Gandhi Jayanti
        "2026-10-20",  # Dussehra
        "2026-11-09",  # Diwali
        "2026-11-10",  # Diwali Balipratipada
        "2026-11-24",  # Guru Nanak Jayanti
        "2026-12-25",  # Christmas
    }

    if now.strftime("%Y-%m-%d") in NSE_HOLIDAYS:
        return False

    return dtime(9, 15) <= now.time() <= dtime(15, 30)


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
            return datetime.strptime(
                s,
                f
            ).strftime("%Y-%m-%d")
        except Exception:
            pass

    return s


def expiry_label(x):
    n = expiry_norm(x)

    if not n:
        return "-"

    try:
        return datetime.strptime(
            n,
            "%Y-%m-%d"
        ).strftime("%d %b %Y")
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
    for name in names:

        if isinstance(row, dict) and name in row:
            value = row.get(name)

            if value is not None and str(value) != "":
                return value

        try:
            if name in row.index:
                value = row[name]

                if pd.notna(value):
                    return value
        except Exception:
            pass

    return default


def find_column(df, names):
    for name in names:
        if name in df.columns:
            return name
    return None


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

GEMINI_MODEL = (
    secret("GEMINI_MODEL")
    or "gemini-3.6-flash"
)

# =========================================================
# FII / DII
# =========================================================

FII_DII_API = (
    "https://fii-diidata.mrchartist.com/api/data"
)

FII_DII_HISTORY_API = (
    "https://fii-diidata.mrchartist.com/api/history"
)


def extract_number(obj, keys):
    if not isinstance(obj, dict):
        return None

    for key in keys:
        if key in obj:
            value = num(obj.get(key))

            if value is not None:
                return value

    return None


def find_nested_record(obj):
    if isinstance(obj, dict):

        for key in [
            "data",
            "result",
            "latest",
            "current",
            "record",
        ]:
            value = obj.get(key)

            if isinstance(value, dict):
                return value

            if isinstance(value, list) and value:
                if isinstance(value[0], dict):
                    return value[0]

        return obj

    if isinstance(obj, list) and obj:
        if isinstance(obj[0], dict):
            return obj[0]

    return {}


def parse_fii_dii_record(record):
    record = find_nested_record(record)

    fii_buy = extract_number(
        record,
        [
            "fii_buy",
            "fiiBuy",
            "fiibuy",
            "fb",
            "FII Buy",
            "FII_Buy",
        ],
    )

    fii_sell = extract_number(
        record,
        [
            "fii_sell",
            "fiiSell",
            "fiisell",
            "fs",
            "FII Sell",
            "FII_Sell",
        ],
    )

    fii_net = extract_number(
        record,
        [
            "fii_net",
            "fiiNet",
            "fiinet",
            "fn",
            "FII Net",
            "FII_Net",
        ],
    )

    dii_buy = extract_number(
        record,
        [
            "dii_buy",
            "diiBuy",
            "diibuy",
            "db",
            "DII Buy",
            "DII_Buy",
        ],
    )

    dii_sell = extract_number(
        record,
        [
            "dii_sell",
            "diiSell",
            "diisell",
            "ds",
            "DII Sell",
            "DII_Sell",
        ],
    )

    dii_net = extract_number(
        record,
        [
            "dii_net",
            "diiNet",
            "diinet",
            "dn",
            "DII Net",
            "DII_Net",
        ],
    )

    if fii_net is None and fii_buy is not None and fii_sell is not None:
        fii_net = fii_buy - fii_sell

    if dii_net is None and dii_buy is not None and dii_sell is not None:
        dii_net = dii_buy - dii_sell

    data_date = (
        record.get("date")
        or record.get("d")
        or record.get("trade_date")
        or record.get("tradeDate")
        or record.get("timestamp")
    )

    return {
        "fii_buy": fii_buy,
        "fii_sell": fii_sell,
        "fii_net": fii_net,
        "dii_buy": dii_buy,
        "dii_sell": dii_sell,
        "dii_net": dii_net,
        "date": data_date,
    }


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fii_dii():

    empty = {
        "available": False,
        "source": "Unavailable",
        "date": None,
        "fii_buy": None,
        "fii_sell": None,
        "fii_net": None,
        "dii_buy": None,
        "dii_sell": None,
        "dii_net": None,
        "combined_net": None,
        "fii_3d": None,
        "dii_3d": None,
        "institutional_score": 0,
        "bias": "UNAVAILABLE",
        "bias_score": "NEUTRAL",
        "status": "Data unavailable",
    }

    latest = None

    try:
        response = requests.get(
            FII_DII_API,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )

        if response.ok:
            latest = response.json()

    except Exception:
        latest = None

    if latest is None:
        return empty

    parsed = parse_fii_dii_record(latest)

    fii_net = parsed["fii_net"]
    dii_net = parsed["dii_net"]

    if fii_net is None and dii_net is None:
        return empty

    history = []

    try:
        response = requests.get(
            FII_DII_HISTORY_API,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )

        if response.ok:
            history_data = response.json()

            if isinstance(history_data, dict):

                for key in [
                    "data",
                    "history",
                    "results",
                ]:
                    if isinstance(
                        history_data.get(key),
                        list
                    ):
                        history = history_data[key]
                        break

            elif isinstance(history_data, list):
                history = history_data

    except Exception:
        history = []

    fii_history = []
    dii_history = []

    for item in history[:5]:

        row = parse_fii_dii_record(item)

        if row["fii_net"] is not None:
            fii_history.append(row["fii_net"])

        if row["dii_net"] is not None:
            dii_history.append(row["dii_net"])

    fii_values = (
        [fii_net] + fii_history[:2]
        if fii_net is not None
        else fii_history[:3]
    )

    dii_values = (
        [dii_net] + dii_history[:2]
        if dii_net is not None
        else dii_history[:3]
    )

    fii_3d = (
        sum(fii_values)
        if fii_values
        else None
    )

    dii_3d = (
        sum(dii_values)
        if dii_values
        else None
    )

    score = 0

    if fii_net is not None:

        if fii_net >= 2000:
            score += 2
        elif fii_net >= 500:
            score += 1
        elif fii_net <= -2000:
            score -= 2
        elif fii_net <= -500:
            score -= 1

    if dii_net is not None:

        if dii_net >= 2000:
            score += 1
        elif dii_net >= 500:
            score += 1
        elif dii_net <= -2000:
            score -= 1
        elif dii_net <= -500:
            score -= 1

    if fii_3d is not None and fii_3d >= 5000:
        score += 1

    elif fii_3d is not None and fii_3d <= -5000:
        score -= 1

    bias = "MIXED"

    if fii_net is not None and dii_net is not None:

        if fii_net > 500 and dii_net > 500:
            bias = "BULLISH CONFIRMATION"

        elif fii_net < -500 and dii_net < -500:
            bias = "BEARISH CONFIRMATION"

        elif fii_net < -500 and dii_net > 500:
            bias = "FII SELLING / DII BUYING"

        elif fii_net > 500 and dii_net < -500:
            bias = "FII BUYING / DII SELLING"

        else:
            bias = "MIXED / WEAK"

    elif fii_net is not None:

        if fii_net > 500:
            bias = "FII POSITIVE"

        elif fii_net < -500:
            bias = "FII NEGATIVE"

    if score > 0:
        bias_score = "POSITIVE"
    elif score < 0:
        bias_score = "NEGATIVE"
    else:
        bias_score = "NEUTRAL"

    return {
        "available": True,
        "source": "Free NSE-sourced FII/DII API",
        "date": parsed["date"],
        "fii_buy": parsed["fii_buy"],
        "fii_sell": parsed["fii_sell"],
        "fii_net": fii_net,
        "dii_buy": parsed["dii_buy"],
        "dii_sell": parsed["dii_sell"],
        "dii_net": dii_net,
        "combined_net": (
            fii_net + dii_net
            if fii_net is not None
            and dii_net is not None
            else None
        ),
        "fii_3d": fii_3d,
        "dii_3d": dii_3d,
        "institutional_score": score,
        "bias": bias,
        "bias_score": bias_score,
        "status": "Latest available / provisional",
    }


fii_dii = fetch_fii_dii()

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

            token = getattr(
                smart_api,
                "access_token",
                None
            )

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
    "FINNIFTY": ("NSE", "99926037"),
    "SENSEX": ("BSE", "99919000"),
    "BANKEX": ("BSE", "99919012"),
}
# =========================================================
# SPOT
# =========================================================

def get_spot(symbol):
    # 1. Try live LTP from Angel One
    if telemetry is not None:
        try:
            result = telemetry.get_ltp(symbol)

            if isinstance(result, dict):
                for key in (
                    "ltp",
                    "LTP",
                    "lastTradedPrice",
                    "lastTradedPriceValue",
                    "close",
                    "price",
                ):
                    if key in result:
                        value = num(result[key])
                        if value is not None and value > 0:
                            return value

            value = num(result)
            if value is not None and value > 0:
                return value

        except Exception:
            pass

    # 2. If live LTP fails, use latest OHLCV close
    try:
        df = fetch_ohlcv(
            symbol,
            interval="FIVE_MINUTE",
            days=5,
        )

        if df is not None and not df.empty:
            if "close" in df.columns:
                close = pd.to_numeric(
                    df["close"],
                    errors="coerce"
                ).dropna()

                if not close.empty:
                    value = float(close.iloc[-1])

                    if value > 0:
                        return value
    except Exception:
        pass

    # 3. No fake fallback number
    return None

# =========================================================
# EXPIRIES
# =========================================================

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

        return sorted(
            set(values)
        )

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

    contracts = load_contracts(
        symbol,
        expiry
    )

    if contracts.empty:
        return pd.DataFrame(), contracts

    # -----------------------------------------------------
    # STRIKE NORMALIZER
    # -----------------------------------------------------

    def normalize_strike_value(value):

        try:

            value = float(value)

            # Angel One contract-master raw strike
            # example: 2045000 -> 20450
            if abs(value) >= 100000:
                value = value / 100.0

            return value

        except Exception:
            return None

    # -----------------------------------------------------
    # NORMALIZE CONTRACT STRIKES
    # -----------------------------------------------------

    try:

        contract_strike_col = find_column(
            contracts,
            [
                "strike",
                "strikePrice",
                "strike_price",
            ]
        )

        if contract_strike_col is not None:

            contracts["strikePrice"] = (
                pd.to_numeric(
                    contracts[contract_strike_col],
                    errors="coerce"
                )
                .apply(normalize_strike_value)
            )

            # Keep strike column consistent too
            if "strike" in contracts.columns:
                contracts["strike"] = contracts[
                    "strikePrice"
                ]

    except Exception:
        pass

    # -----------------------------------------------------
    # NEAR ATM CONTRACTS
    # -----------------------------------------------------

    try:

        if spot is not None and options is not None:

            near = options.get_near_atm_contracts(
                underlying=symbol,
                expiry_date=expiry,
                spot_price=spot,
                strikes_each_side=10,
            )

            near = clean_df(near)

            if not near.empty:
                contracts = near

                # Normalize newly selected contracts
                near_strike_col = find_column(
                    contracts,
                    [
                        "strike",
                        "strikePrice",
                        "strike_price",
                    ]
                )

                if near_strike_col is not None:

                    contracts["strikePrice"] = (
                        pd.to_numeric(
                            contracts[near_strike_col],
                            errors="coerce"
                        )
                        .apply(normalize_strike_value)
                    )

                    if "strike" in contracts.columns:
                        contracts["strike"] = contracts[
                            "strikePrice"
                        ]

    except Exception:
        pass

    # -----------------------------------------------------
    # LIVE / LATEST OI + LTP + VOLUME
    # -----------------------------------------------------

    try:

        quoted = options.get_market_quote(
            contracts
        )

        quoted = clean_df(quoted)

        if not quoted.empty:
            chain = quoted
        else:
            chain = contracts.copy()

    except Exception:

        chain = contracts.copy()

    # -----------------------------------------------------
    # NORMALIZE OPTION TYPE
    # -----------------------------------------------------

    type_col = find_column(
        chain,
        [
            "option_type",
            "optionType",
            "optionTypeName",
            "option_type_name",
            "type",
        ]
    )

    if type_col is not None:

        chain["option_type"] = (
            chain[type_col]
            .map(normalize_option_type)
        )

    # -----------------------------------------------------
    # NORMALIZE STRIKE
    # -----------------------------------------------------

    strike_col = find_column(
        chain,
        [
            "strike",
            "strikePrice",
            "strike_price",
        ]
    )

    if strike_col is not None:

        chain["strikePrice"] = (
            pd.to_numeric(
                chain[strike_col],
                errors="coerce"
            )
            .apply(normalize_strike_value)
        )

        # Keep strike column consistent
        if "strike" in chain.columns:
            chain["strike"] = chain[
                "strikePrice"
            ]

    # -----------------------------------------------------
    # OI NORMALIZATION
    # -----------------------------------------------------

    oi_col = find_column(
        chain,
        [
            "opnInterest",
            "openInterest",
            "oi",
            "open_interest",
        ]
    )

    if oi_col is not None:

        chain["openInterest"] = pd.to_numeric(
            chain[oi_col],
            errors="coerce"
        )

    # -----------------------------------------------------
    # CHANGE IN OI
    # -----------------------------------------------------

    chg_oi_col = find_column(
        chain,
        [
            "changeinOpenInterest",
            "changeInOpenInterest",
            "change_in_open_interest",
            "change_oi",
            "chg_oi",
            "oi_change",
        ]
    )

    if chg_oi_col is not None:

        chain["changeInOpenInterest"] = pd.to_numeric(
            chain[chg_oi_col],
            errors="coerce"
        )

    # -----------------------------------------------------
    # GREEKS
    # -----------------------------------------------------

    try:

        if options is not None:

            greeks = clean_df(
                options.greeks_dataframe(
                    symbol,
                    expiry
                )
            )

            if not greeks.empty:

                # Normalize Greek strike column
                greek_strike = find_column(
                    greeks,
                    [
                        "strikePrice",
                        "strike",
                        "strike_price",
                    ]
                )

                if greek_strike is not None:

                    greeks["strikePrice"] = (
                        pd.to_numeric(
                            greeks[greek_strike],
                            errors="coerce"
                        )
                        .apply(normalize_strike_value)
                    )

                    greek_cols = [
                        "strikePrice",
                        "delta",
                        "gamma",
                        "theta",
                        "vega",
                        "impliedVolatility",
                    ]

                    greek_cols = [
                        c
                        for c in greek_cols
                        if c in greeks.columns
                    ]

                    if "strikePrice" in greek_cols:

                        # Greek API can have CE/PE rows.
                        # Merge by strike + option type when possible.
                        greek_type = find_column(
                            greeks,
                            [
                                "optionType",
                                "option_type",
                                "optionTypeName",
                            ]
                        )

                        if greek_type is not None:

                            greeks["option_type"] = (
                                greeks[greek_type]
                                .map(normalize_option_type)
                            )

                            chain = chain.merge(
                                greeks[
                                    greek_cols + [
                                        "option_type"
                                    ]
                                ].drop_duplicates(),
                                on=[
                                    "strikePrice",
                                    "option_type"
                                ],
                                how="left",
                                suffixes=("", "_greek")
                            )

                        else:

                            # Fallback: merge by strike only
                            chain = chain.merge(
                                greeks[
                                    greek_cols
                                ].drop_duplicates(
                                    subset=[
                                        "strikePrice"
                                    ]
                                ),
                                on="strikePrice",
                                how="left",
                                suffixes=("", "_greek")
                            )

    except Exception:
        # Greeks unavailable must never break
        # the option-chain itself.
        pass

    return (
        chain.reset_index(drop=True),
        contracts.reset_index(drop=True)
        )

# =========================================================
# OPTION TYPE NORMALIZATION
# =========================================================

def normalize_option_type(value):

    if value is None:
        return ""

    x = str(value).strip().upper()

    if x in ["CE", "CALL", "C"]:
        return "CE"

    if x in ["PE", "PUT", "P"]:
        return "PE"

    if "CALL" in x:
        return "CE"

    if "PUT" in x:
        return "PE"

    if x.endswith("CE"):
        return "CE"

    if x.endswith("PE"):
        return "PE"

    return ""

# =========================================================
# PCR
# =========================================================

def calculate_pcr(df):

    # First priority: actual option-chain OI
    if df is not None and not df.empty:

        oi_col = find_column(
            df,
            [
                "opnInterest",
                "openInterest",
                "oi",
                "open_interest",
            ]
        )

        type_col = find_column(
            df,
            [
                "option_type",
                "optionType",
                "optionTypeName",
                "option_type_name",
                "type",
            ]
        )

        if oi_col is not None and type_col is not None:

            work = df.copy()

            work["_oi"] = pd.to_numeric(
                work[oi_col]
                .astype(str)
                .str.replace(",", "", regex=False),
                errors="coerce"
            ).fillna(0)

            work["_option_type"] = (
                work[type_col]
                .map(normalize_option_type)
            )

            ce_oi = work.loc[
                work["_option_type"] == "CE",
                "_oi"
            ].sum()

            pe_oi = work.loc[
                work["_option_type"] == "PE",
                "_oi"
            ].sum()

            if ce_oi > 0 and pe_oi >= 0:

                pcr = pe_oi / ce_oi

                if np.isfinite(pcr) and 0 < pcr <= 10:
                    return float(pcr)

    # Second priority: Angel One official PCR API
    try:

        if options is not None:

            pcr_df = clean_df(
                options.pcr_dataframe()
            )

            if not pcr_df.empty:

                for col in [
                    "pcr",
                    "putCallRatio",
                    "put_call_ratio",
                ]:

                    if col in pcr_df.columns:

                        values = pd.to_numeric(
                            pcr_df[col],
                            errors="coerce"
                        ).dropna()

                        if not values.empty:

                            value = float(
                                values.iloc[-1]
                            )

                            if (
                                np.isfinite(value)
                                and 0 < value <= 10
                            ):
                                return value

    except Exception:
        pass

    return None

# =========================================================
# LIVE DERIVATIVES / OPTION-CHAIN PROXY
# =========================================================

def calculate_live_derivatives_proxy(chain, pcr):

    result = {
        "available": False,
        "score": 0,
        "bias": "UNAVAILABLE",
        "source": "Live option-chain positioning proxy",
        "status": "No usable derivatives positioning",
        "reasons": [],
        "pcr": pcr,
    }

    if chain.empty:
        return result

    type_col = find_column(
        chain,
        [
            "option_type",
            "optionType",
            "optionTypeName",
            "option_type_name",
            "type",
        ]
    )

    oi_col = find_column(
        chain,
        [
            "opnInterest",
            "openInterest",
            "oi",
            "open_interest",
        ]
    )

    chg_oi_col = find_column(
        chain,
        [
            "changeinOpenInterest",
            "changeInOpenInterest",
            "change_in_open_interest",
            "change_oi",
            "chg_oi",
            "oi_change",
        ]
    )

    score = 0
    reasons = []
    usable = False

    # -----------------------------------------------------
    # PCR component
    # -----------------------------------------------------

    if pcr is not None:

        usable = True

        if 1.10 <= pcr <= 1.80:

            score += 2

            reasons.append(
                f"PCR {pcr:.2f} supportive hai."
            )

        elif 0.90 <= pcr < 1.10:

            score += 1

            reasons.append(
                f"PCR {pcr:.2f} mildly supportive hai."
            )

        elif 0.70 <= pcr < 0.90:

            reasons.append(
                f"PCR {pcr:.2f} neutral-to-cautious zone mein hai."
            )

        elif 0.40 <= pcr < 0.70:

            score -= 1

            reasons.append(
                f"PCR {pcr:.2f} bearish pressure indicate karta hai."
            )

        elif pcr < 0.40:

            score -= 2

            reasons.append(
                f"PCR {pcr:.2f} strong caution zone mein hai."
            )

    # -----------------------------------------------------
    # Change in OI component
    # -----------------------------------------------------

    if type_col is not None and chg_oi_col is not None:

        work = chain.copy()

        work["_type"] = (
            work[type_col]
            .map(normalize_option_type)
        )

        work["_chg_oi"] = pd.to_numeric(
            work[chg_oi_col]
            .astype(str)
            .str.replace(",", "", regex=False),
            errors="coerce"
        ).fillna(0)

        ce_change = work.loc[
            work["_type"] == "CE",
            "_chg_oi"
        ].sum()

        pe_change = work.loc[
            work["_type"] == "PE",
            "_chg_oi"
        ].sum()

        if (
            work["_type"].isin(
                ["CE", "PE"]
            ).any()
        ):
            usable = True

            # This is deliberately only a small supporting weight.
            # It is not treated as a guaranteed directional signal.

            if pe_change > 0 and ce_change < 0:

                score += 1

                reasons.append(
                    "Option-chain change in OI mildly bullish side par hai."
                )

            elif ce_change > 0 and pe_change < 0:

                score -= 1

                reasons.append(
                    "Option-chain change in OI mildly bearish side par hai."
                )

    # -----------------------------------------------------
    # OI availability
    # -----------------------------------------------------

    if type_col is not None and oi_col is not None:

        work = chain.copy()

        work["_type"] = (
            work[type_col]
            .map(normalize_option_type)
        )

        work["_oi"] = pd.to_numeric(
            work[oi_col]
            .astype(str)
            .str.replace(",", "", regex=False),
            errors="coerce"
        ).fillna(0)

        ce_oi = work.loc[
            work["_type"] == "CE",
            "_oi"
        ].sum()

        pe_oi = work.loc[
            work["_type"] == "PE",
            "_oi"
        ].sum()

        if ce_oi > 0 or pe_oi > 0:
            usable = True

    if not usable:
        return result

    score = max(
        -2,
        min(
            2,
            score
        )
    )

    if score >= 2:
        bias = "BULLISH PROXY"

    elif score == 1:
        bias = "MILD BULLISH PROXY"

    elif score == -1:
        bias = "MILD BEARISH PROXY"

    elif score <= -2:
        bias = "BEARISH PROXY"

    else:
        bias = "NEUTRAL PROXY"

    result.update({
        "available": True,
        "score": score,
        "bias": bias,
        "status": (
            "Live broker option-chain positioning"
            if market_open()
            else "Latest broker option-chain positioning"
        ),
        "reasons": reasons,
    })

    return result

# =========================================================
# OHLCV
# =========================================================

@st.cache_data(ttl=120, show_spinner=False)
def fetch_ohlcv(
    symbol,
    interval="FIVE_MINUTE",
    days=5
):

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

        df = df.rename(
            columns=rename
        )

        needed = [
            "open",
            "high",
            "low",
            "close",
        ]

        if not all(
            c in df.columns
            for c in needed
        ):
            return pd.DataFrame()

        for c in needed + (
            ["volume"]
            if "volume" in df.columns
            else []
        ):

            df[c] = pd.to_numeric(
                df[c],
                errors="coerce"
            )

        df = df.dropna(
            subset=needed
        ).reset_index(
            drop=True
        )

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

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.rolling(
        14
    ).mean()

    avg_loss = loss.rolling(
        14
    ).mean()

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

    df["MACD_SIGNAL"] = df[
        "MACD"
    ].ewm(
        span=9,
        adjust=False
    ).mean()

    tr1 = high - low

    tr2 = (
        high - close.shift()
    ).abs()

    tr3 = (
        low - close.shift()
    ).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = tr.rolling(
        14
    ).mean()

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where(
        (plus_dm > minus_dm)
        & (plus_dm > 0),
        0
    )

    minus_dm = minus_dm.where(
        (minus_dm > plus_dm)
        & (minus_dm > 0),
        0
    )

    plus_di = (
        100
        * plus_dm.rolling(14).sum()
        / atr.rolling(14).sum()
    )

    minus_di = (
        100
        * minus_dm.rolling(14).sum()
        / atr.rolling(14).sum()
    )

    dx = (
        100
        * (plus_di - minus_di).abs()
        / (
            plus_di + minus_di
        ).replace(
            0,
            np.nan
        )
    )

    df["ADX"] = dx.rolling(
        14
    ).mean()

    if "volume" in df.columns:

        typical = (
            high + low + close
        ) / 3

        cumulative_volume = (
            df["volume"].cumsum()
        )

        df["VWAP"] = (
            (
                typical
                * df["volume"]
            ).cumsum()
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

def analyze_market(
    symbol,
    derivatives_proxy=None
):

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
        "technical_score": 0,
        "institutional_score": 0,
        "institutional_bias": "UNAVAILABLE",
        "institutional_source": "NONE",
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

    last = num(
        row.get("close")
    )

    result["last"] = last

    result["rsi"] = num(
        row.get("RSI")
    )

    result["adx"] = num(
        row.get("ADX")
    )

    result["ema20"] = num(
        row.get("EMA20")
    )

    result["ema50"] = num(
        row.get("EMA50")
    )

    result["macd"] = num(
        row.get("MACD")
    )

    result["macd_signal"] = num(
        row.get("MACD_SIGNAL")
    )

    result["vwap"] = num(
        row.get("VWAP")
    )

    if (
        "volume" in df5.columns
        and num(row.get("volume")) is not None
        and num(row.get("VOL_AVG20")) not in [
            None,
            0
        ]
    ):

        result["volume_ratio"] = (
            num(row.get("volume"))
            / num(row.get("VOL_AVG20"))
        )

    recent = df5.tail(30)

    result["support"] = num(
        recent["low"].min()
    )

    result["resistance"] = num(
        recent["high"].max()
    )

    score = 0

    # -----------------------------------------------------
    # EMA
    # -----------------------------------------------------

    if (
        result["ema20"] is not None
        and result["ema50"] is not None
        and last is not None
    ):

        if (
            last
            > result["ema20"]
            > result["ema50"]
        ):

            score += 2

            result["reasons"].append(
                "Price EMA20 aur EMA50 ke upar hai."
            )

        elif (
            last
            < result["ema20"]
            < result["ema50"]
        ):

            score -= 2

            result["reasons"].append(
                "Price EMA20 aur EMA50 ke neeche hai."
            )

    # -----------------------------------------------------
    # VWAP
    # -----------------------------------------------------

    if (
        result["vwap"] is not None
        and last is not None
    ):

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

    # -----------------------------------------------------
    # MACD
    # -----------------------------------------------------

    if (
        result["macd"] is not None
        and result["macd_signal"] is not None
    ):

        if (
            result["macd"]
            > result["macd_signal"]
        ):

            score += 1

            result["reasons"].append(
                "MACD bullish side par hai."
            )

        else:

            score -= 1

            result["reasons"].append(
                "MACD bearish side par hai."
            )

    # -----------------------------------------------------
    # RSI
    # -----------------------------------------------------

    if result["rsi"] is not None:

        if result["rsi"] >= 60:

            score += 1

            result["momentum"] = "BULLISH"

        elif result["rsi"] <= 40:

            score -= 1

            result["momentum"] = "BEARISH"

    # -----------------------------------------------------
    # ADX
    # -----------------------------------------------------

    if (
        result["adx"] is not None
        and result["adx"] >= 20
    ):

        result["reasons"].append(
            f"ADX {result['adx']:.1f}, trend strength active."
        )

    # -----------------------------------------------------
    # VOLUME
    # -----------------------------------------------------

    if result["volume_ratio"] is not None:

        if result["volume_ratio"] >= 1.3:

            result["reasons"].append(
                "Volume average se significantly higher hai."
            )

    result["technical_score"] = score

    # =====================================================
    # INSTITUTIONAL DECISION ENGINE
    # =====================================================

    if fii_dii.get("available"):

        institutional_score = int(
            fii_dii.get(
                "institutional_score",
                0
            )
        )

        result["institutional_score"] = institutional_score

        result["institutional_bias"] = fii_dii.get(
            "bias",
            "MIXED"
        )

        result["institutional_source"] = (
            "ACTUAL FII/DII"
        )

        if institutional_score > 0:

            result["reasons"].append(
                "Actual FII/DII flow market direction ko support kar raha hai."
            )

        elif institutional_score < 0:

            result["reasons"].append(
                "Actual FII/DII flow market direction par pressure daal raha hai."
            )

        else:

            result["reasons"].append(
                "Actual FII/DII flow mixed/neutral hai."
            )

    elif (
        derivatives_proxy is not None
        and derivatives_proxy.get("available")
    ):

        institutional_score = int(
            derivatives_proxy.get(
                "score",
                0
            )
        )

        result["institutional_score"] = institutional_score

        result["institutional_bias"] = derivatives_proxy.get(
            "bias",
            "DERIVATIVES PROXY"
        )

        result["institutional_source"] = (
            "LIVE DERIVATIVES PROXY"
        )

        result["reasons"].append(
            "Actual FII/DII cash data pending hai; "
            "live option-chain positioning ko temporary institutional proxy "
            "ke roop mein use kiya gaya hai."
        )

        for reason in derivatives_proxy.get(
            "reasons",
            []
        ):
            result["reasons"].append(
                reason
            )

    else:

        result["institutional_score"] = 0

        result["institutional_bias"] = (
            "FII/DII PENDING"
        )

        result["institutional_source"] = (
            "NONE"
        )

        result["reasons"].append(
            "FII/DII aur usable derivatives positioning "
            "dono unavailable hain; institutional weight 0 rakha gaya hai."
        )

    result["score"] = (
        score
        + result["institutional_score"]
    )

    # -----------------------------------------------------
    # FINAL TREND
    # -----------------------------------------------------

    if result["score"] >= 4:

        result["trend"] = "BULLISH"

    elif result["score"] <= -4:

        result["trend"] = "BEARISH"

    else:

        result["trend"] = "SIDEWAYS"

    return result

# =========================================================
# OPTION SELECTION
# =========================================================

def nearest_option(
    chain,
    spot,
    side
):

    if chain.empty or spot is None:
        return None

    type_col = find_column(
        chain,
        [
            "option_type",
            "optionType",
            "optionTypeName",
            "option_type_name",
            "type",
        ]
    )

    strike_col = find_column(
        chain,
        [
            "strike",
            "strikePrice",
            "strike_price",
        ]
    )

    if type_col is None or strike_col is None:
        return None

    work = chain.copy()

    work["_type"] = (
        work[type_col]
        .map(normalize_option_type)
    )

    work = work[
        work["_type"] == side
    ].copy()

    if work.empty:
        return None

    work["_strike"] = pd.to_numeric(
        work[strike_col]
        .astype(str)
        .str.replace(",", "", regex=False),
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

# =========================================================
# TRADE IDEA
# =========================================================

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

    score = float(
        market.get("score", 0)
    )

    technical_score = float(
        market.get("technical_score", 0)
    )

    institutional_score = float(
        market.get("institutional_score", 0)
    )

    # -----------------------------------------------------
    # DIRECTION
    # -----------------------------------------------------

    if score >= 2:
        direction = "BUY"
        bullish = True

    elif score <= -2:
        direction = "SELL"
        bullish = False

    else:
        # After-market planning:
        # use technical direction if combined score
        # is not strong enough for an immediate signal.
        if technical_score > 0:
            direction = "BUY"
            bullish = True
        elif technical_score < 0:
            direction = "SELL"
            bullish = False
        else:
            return None

    # -----------------------------------------------------
    # SPOT RISK MODEL
    # -----------------------------------------------------

    entry = float(last)

    support = market.get("support")
    resistance = market.get("resistance")

    if bullish:

        if support is not None and support < entry:
            sl = float(support)
        else:
            sl = entry * 0.997

        risk = entry - sl

        if risk <= 0:
            return None

        target1 = entry + risk * 1.5
        target2 = entry + risk * 2.5

    else:

        if resistance is not None and resistance > entry:
            sl = float(resistance)
        else:
            sl = entry * 1.003

        risk = sl - entry

        if risk <= 0:
            return None

        target1 = entry - risk * 1.5
        target2 = entry - risk * 2.5

    # -----------------------------------------------------
    # CONFIDENCE
    # -----------------------------------------------------

    confidence = 65 + (
        abs(score) * 4
    ) + (
        abs(institutional_score) * 2
    )

    confidence = min(
        95,
        max(
            65,
            confidence
        )
    )

    idea = {
        "segment": instrument,
        "symbol": symbol,
        "action": direction,
        "entry": entry,
        "sl": sl,
        "target1": target1,
        "target2": target2,
        "risk_reward": 1.5,
        "confidence": confidence,
        "holding": (
            "Intraday"
            if market_open()
            else "NEXT SESSION"
        ),
        "expiry": expiry,
        "option": None,
        "strike": None,
        "option_ltp": None,
        "delta": None,
        "gamma": None,
        "theta": None,
        "vega": None,
        "iv": None,
        "oi": None,
        "change_oi": None,
        "technical_score": technical_score,
        "institutional_score": institutional_score,
        "institutional_bias": market.get(
            "institutional_bias",
            "UNAVAILABLE"
        ),
        "institutional_source": market.get(
            "institutional_source",
            "NONE"
        ),
        "why": " ".join(
            market.get(
                "reasons",
                []
            )[:8]
        ),
        "invalidation": (
            f"Price {'below' if bullish else 'above'} "
            f"SL level sustain kare."
        ),
    }

    # -----------------------------------------------------
    # OPTION IDEA
    # -----------------------------------------------------

    if (
        instrument == "INDEX OPTION"
        and chain is not None
        and not chain.empty
    ):

        side = (
            "CE"
            if bullish
            else "PE"
        )

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

            ltp = option_ltp(
                selected
            )

            idea["option"] = side
            idea["strike"] = strike
            idea["option_ltp"] = ltp

            # OI
            idea["oi"] = num(
                first_value(
                    selected,
                    [
                        "openInterest",
                        "opnInterest",
                        "oi",
                    ]
                )
            )

            # Change in OI
            idea["change_oi"] = num(
                first_value(
                    selected,
                    [
                        "changeInOpenInterest",
                        "changeinOpenInterest",
                        "change_oi",
                        "chg_oi",
                    ]
                )
            )

            # Greeks
            idea["delta"] = num(
                first_value(
                    selected,
                    ["delta"]
                )
            )

            idea["gamma"] = num(
                first_value(
                    selected,
                    ["gamma"]
                )
            )

            idea["theta"] = num(
                first_value(
                    selected,
                    ["theta"]
                )
            )

            idea["vega"] = num(
                first_value(
                    selected,
                    ["vega"]
                )
            )

            idea["iv"] = num(
                first_value(
                    selected,
                    [
                        "impliedVolatility",
                        "iv",
                    ]
                )
            )

            # Option price based targets
            if ltp is not None and ltp > 0:

                idea["entry"] = ltp
                idea["sl"] = ltp * 0.85
                idea["target1"] = ltp * 1.20
                idea["target2"] = ltp * 1.35

                idea["risk_reward"] = 1.35

            idea["why"] += (
                f" {side} selected near ATM "
                f"strike {strike}."
            )

    return idea
# =========================================================
# GEMINI
# =========================================================

def ask_gemini(
    ideas,
    market_data
):

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
            "fii_dii": fii_dii,
        }

        prompt = f"""
You are an Indian market research assistant for a
PAPER TRADING ONLY application.

Use ONLY supplied data.

Do NOT invent:
- prices
- OI
- news
- Greeks
- FII/DII values
- option data
- support/resistance

IMPORTANT:

Actual FII/DII data has priority when available.

If actual FII/DII is unavailable, the supplied
LIVE DERIVATIVES PROXY may be used only as a
clearly-labelled proxy.

Never call the derivatives proxy actual FII/DII.

For every supplied trade idea explain:

1. Technical setup
2. Institutional input
3. Whether actual FII/DII or derivatives proxy was used
4. Options context if available
5. Risk
6. Invalidation
7. Intraday or next-session context

If the setup is weak, say that clearly.

Do not manufacture a trade.

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

        return (
            f"AI explanation unavailable: {e}"
        )

# =========================================================
# HEADER
# =========================================================

st.title(
    "📊 AI Trading Expert Advisor"
)

st.caption(
    "Live/After-Market Research • Options • Equities • "
    "Technical Analysis • FII/DII • Paper Trading Only"
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
        "OPEN"
        if market_open()
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

st.sidebar.header(
    "⚙️ Expert Advisor"
)

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

st.session_state[
    "underlying"
] = underlying

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

    st.session_state[
        "expiry"
    ] = selected_expiry

else:

    st.sidebar.info(
        "Expiry data unavailable"
    )

option_type = st.sidebar.selectbox(
    "Option Type",
    [
        "CE",
        "PE",
        "BOTH"
    ],
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
# OPTIONS DATA FIRST
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

derivatives_proxy = (
    calculate_live_derivatives_proxy(
        chain,
        pcr
    )
)

# =========================================================
# MARKET ANALYSIS
# =========================================================

market = analyze_market(
    underlying,
    derivatives_proxy
)

# =========================================================
# FII / DII
# =========================================================

st.subheader(
    "🏦 Institutional Flow"
)

if fii_dii["available"]:

    f1, f2, f3, f4 = st.columns(4)

    with f1:
        st.metric(
            "FII Net",
            (
                f"₹{fmt(fii_dii['fii_net'], 0)} Cr"
                if fii_dii["fii_net"] is not None
                else "Unavailable"
            )
        )

    with f2:
        st.metric(
            "DII Net",
            (
                f"₹{fmt(fii_dii['dii_net'], 0)} Cr"
                if fii_dii["dii_net"] is not None
                else "Unavailable"
            )
        )

    with f3:
        st.metric(
            "Combined Net",
            (
                f"₹{fmt(fii_dii['combined_net'], 0)} Cr"
                if fii_dii["combined_net"] is not None
                else "Unavailable"
            )
        )

    with f4:
        st.metric(
            "Institutional Score",
            f"{fii_dii['institutional_score']:+d}"
        )

    f5, f6, f7, f8 = st.columns(4)

    with f5:
        st.metric(
            "FII 3-Session",
            (
                f"₹{fmt(fii_dii['fii_3d'], 0)} Cr"
                if fii_dii["fii_3d"] is not None
                else "-"
            )
        )

    with f6:
        st.metric(
            "DII 3-Session",
            (
                f"₹{fmt(fii_dii['dii_3d'], 0)} Cr"
                if fii_dii["dii_3d"] is not None
                else "-"
            )
        )

    with f7:
        st.metric(
            "Institutional Bias",
            fii_dii["bias"]
        )

    with f8:
        st.metric(
            "Source",
            "ACTUAL"
        )

    st.caption(
        f"Source: {fii_dii['source']} • "
        f"{fii_dii['status']} • "
        f"Date: {safe_text(fii_dii['date'])}"
    )

else:

    st.warning(
        "Actual FII/DII cash-flow data abhi unavailable hai. "
        "AI analysis rukega nahi — live/latest option-chain positioning "
        "available hone par institutional proxy use hoga."
    )

# =========================================================
# DERIVATIVES PROXY
# =========================================================

st.subheader(
    "🧮 Derivatives Institutional Proxy"
)

if derivatives_proxy.get("available"):

    d1, d2, d3 = st.columns(3)

    with d1:
        st.metric(
            "Proxy Score",
            f"{derivatives_proxy['score']:+d}"
        )

    with d2:
        st.metric(
            "Proxy Bias",
            derivatives_proxy["bias"]
        )

    with d3:
        st.metric(
            "PCR",
            (
                fmt(
                    derivatives_proxy.get("pcr"),
                    2
                )
                if derivatives_proxy.get("pcr") is not None
                else "-"
            )
        )

    st.caption(
        f"Source: {derivatives_proxy['source']} • "
        f"{derivatives_proxy['status']} • "
        f"Actual FII/DII available hone par proxy automatically replace hota hai."
    )

    for reason in derivatives_proxy.get(
        "reasons",
        []
    ):
        st.write(
            "• " + reason
        )

else:

    st.info(
        "Usable derivatives positioning bhi unavailable hai. "
        "Institutional score ko 0 rakha gaya hai — koi fake value nahi."
    )

# =========================================================
# MARKET INTELLIGENCE
# =========================================================

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
        fmt(
            market["rsi"],
            1
        )
    )

with a4:
    st.metric(
        "ADX",
        fmt(
            market["adx"],
            1
        )
    )

a5, a6, a7, a8 = st.columns(4)

with a5:
    st.metric(
        "EMA20",
        fmt(
            market["ema20"]
        )
    )

with a6:
    st.metric(
        "EMA50",
        fmt(
            market["ema50"]
        )
    )

with a7:
    st.metric(
        "VWAP",
        fmt(
            market["vwap"]
        )
    )

with a8:
    st.metric(
        "Volume Ratio",
        fmt(
            market["volume_ratio"],
            2
        )
    )

a9, a10, a11, a12 = st.columns(4)

with a9:
    st.metric(
        "Technical Score",
        f"{market.get('technical_score', 0):+d}"
    )

with a10:
    st.metric(
        "Institutional Score",
        f"{market.get('institutional_score', 0):+d}"
    )

with a11:
    st.metric(
        "Combined Score",
        f"{market.get('score', 0):+d}"
    )

with a12:
    st.metric(
        "Institutional Source",
        market.get(
            "institutional_source",
            "NONE"
        )
    )

# =========================================================
# SUPPORT / RESISTANCE
# =========================================================

r1, r2 = st.columns(2)

with r1:
    st.metric(
        "Support",
        fmt(
            market["support"]
        )
    )

with r2:
    st.metric(
        "Resistance",
        fmt(
            market["resistance"]
        )
    )

st.caption(
    f"Institutional input: "
    f"{market.get('institutional_bias', 'UNAVAILABLE')}"
)

if market["reasons"]:

    st.markdown(
        "### Current Analysis"
    )

    for reason in market["reasons"]:
        st.write(
            "• " + reason
        )

# =========================================================
# OPTIONS INTELLIGENCE
# =========================================================

st.subheader(
    "🧮 Options Intelligence"
)

o1, o2, o3 = st.columns(3)

with o1:
    st.metric(
        "PCR",
        fmt(
            pcr,
            2
        )
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
        "strikePrice",
        "option_type",
        "optionType",
        "expiry_normalized",
        "ltp",
        "LTP",
        "tradeVolume",
        "opnInterest",
        "openInterest",
    ]

    cols = [
        c
        for c in display_cols
        if c in chain.columns
    ]

    view = chain.copy()

    type_col = find_column(
        view,
        [
            "option_type",
            "optionType",
            "optionTypeName",
        ]
    )

    if option_type in [
        "CE",
        "PE"
    ] and type_col:

        view = view[
            view[type_col]
            .map(normalize_option_type)
            .eq(option_type)
        ]

    if cols and not view.empty:

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

if market_open():

    st.write(
        "Live market mode: Technical + Options + "
        "Institutional input se paper-trading setup generate hoga."
    )

else:

    st.write(
        "After-market mode: Available data ke basis par "
        "**NEXT SESSION planned paper-trade idea** generate hoga. "
        "Weak setup hone par NO TRADE / WAIT rahega."
    )

if st.button(
    "🚀 GENERATE TRADE IDEAS",
    type="primary",
    use_container_width=True
):

    with st.spinner(
        "Market + Options + Institutional data analyze ho raha hai..."
    ):

        ideas = []

        # -------------------------------------------------
        # 1. SELECTED INDEX SPOT
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
        # 2. SELECTED INDEX OPTION
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
                "BANKNIFTY",
                derivatives_proxy
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
                "NIFTY",
                derivatives_proxy
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

        if underlying != "SENSEX":

            sensex_market = analyze_market(
                "SENSEX",
                derivatives_proxy
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

        # -------------------------------------------------
        # REMOVE DUPLICATES
        # -------------------------------------------------

        unique = []
        seen = set()

        for idea in ideas:

            key = (
                idea["segment"],
                idea["symbol"],
                idea["action"],
                idea.get("option"),
                str(
                    idea.get("strike")
                ),
            )

            if key not in seen:

                seen.add(key)

                unique.append(
                    idea
                )

        ideas = unique[:5]

    # =====================================================
    # NO TRADE
    # =====================================================

    if not ideas:

        st.warning(
            "Current data se sufficiently strong setup "
            "confirm nahi hua. Fake trade generate nahi kiya gaya."
        )

        if not market_open():

            st.info(
                "After-market mein iska matlab hai: "
                "NEXT SESSION ke liye abhi reliable setup confirm nahi hua. "
                "Wait / fresh confirmation preferred."
            )

    # =====================================================
    # VALID IDEAS
    # =====================================================

    else:

        st.success(
            f"{len(ideas)} valid paper-trading setup(s) generated."
        )

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
                Holding: {idea['holding']} |
                Institutional Source: {idea.get('institutional_source', 'NONE')}
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
                    fmt(
                        idea["entry"]
                    )
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
                    fmt(
                        idea["sl"]
                    )
                )

            with c6:
                st.metric(
                    "Target 1",
                    fmt(
                        idea["target1"]
                    )
                )

            with c7:
                st.metric(
                    "Target 2",
                    fmt(
                        idea["target2"]
                    )
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

            s1, s2, s3 = st.columns(3)

            with s1:
                st.metric(
                    "Technical Score",
                    f"{idea.get('technical_score', 0):.0f}"
                )

            with s2:
                st.metric(
                    "Institutional Score",
                    f"{idea.get('institutional_score', 0):+.0f}"
                )

            with s3:
                st.metric(
                    "Institutional Input",
                    idea.get(
                        "institutional_bias",
                        "Unavailable"
                    )
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
                
            if idea.get("option"):
                g1, g2, g3, g4 = st.columns(4)

                with g1:
                    st.metric("OI", fmt(idea.get("oi")))

                with g2:
                    st.metric("Change OI", fmt(idea.get("change_oi")))

                with g3:
                    st.metric("Delta", fmt(idea.get("delta"), 3))

                with g4:
                    st.metric("Gamma", fmt(idea.get("gamma"), 4))

                g5, g6, g7 = st.columns(3)

                with g5:
                    st.metric("Theta", fmt(idea.get("theta"), 3))

                with g6:
                    st.metric("Vega", fmt(idea.get("vega"), 3))

                with g7:
                    st.metric("IV", fmt(idea.get("iv"), 2))            
                    

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
                f"**Institutional source:** "
                f"{idea.get('institutional_source', 'NONE')}"
            )

            st.write(
                f"**Institutional view:** "
                f"{idea.get('institutional_bias', 'Unavailable')}"
            )

            st.write(
                f"**Invalidation:** "
                f"{idea['invalidation']}"
            )

            st.write(
                "**Trailing SL:** T1 hit hone ke baad "
                "SL ko cost/previous swing ke around trail karein."
            )

            st.divider()

        # =================================================
        # GEMINI
        # =================================================

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
                        "fii_dii": fii_dii,
                        "derivatives_proxy": derivatives_proxy,
                        "institutional_source": market.get(
                            "institutional_source",
                            "NONE"
                        ),
                    }
                )

            if ai_text:

                st.subheader(
                    "🤖 AI Explanation"
                )

                st.write(
                    ai_text
                )

        else:

            st.info(
                "Gemini API key available nahi hai. "
                "Current trade ideas market-data, "
                "technical analysis, options aur "
                "institutional input par based hain."
            )

# =========================================================
# STATUS
# =========================================================

st.divider()

st.caption(
    "Paper Trading Only • No real orders • "
    "Actual FII/DII gets priority • "
    "Otherwise clearly-labelled derivatives proxy • "
    "No fabricated institutional values."
)
