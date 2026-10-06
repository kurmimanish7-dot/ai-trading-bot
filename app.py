import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dtime
import json
import requests
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="AI Trading Expert Advisor",
    page_icon="📊",
    layout="wide",
)

PAPER_TRADING = True

# =========================================================
# MOBILE RESPONSIVE UI STYLES
# =========================================================

st.markdown("""
<style>
/* Main Container */
.block-container {
    padding-top: 1rem !important;
    padding-left: 0.7rem !important;
    padding-right: 0.7rem !important;
    max-width: 100% !important;
}

/* Responsive Columns */
@media(max-width: 768px) {
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 0.45rem !important;
        width: 100% !important;
    }

    [data-testid="column"] {
        min-width: 48% !important;
        max-width: 48% !important;
        flex: 1 1 48% !important;
        width: 48% !important;
        min-height: 0 !important;
    }

    [data-testid="stMetric"] {
        width: 100% !important;
        min-width: 0 !important;
        max-width: 100% !important;
        overflow: visible !important;
    }

    [data-testid="stMetricLabel"] {
        width: 100% !important;
        font-size: 11px !important;
        line-height: 1.25 !important;
        white-space: normal !important;
        overflow-wrap: anywhere !important;
    }

    [data-testid="stMetricValue"] {
        font-size: clamp(14px, 5vw, 18px) !important;
        line-height: 1.25 !important;
        overflow-wrap: anywhere !important;
    }

    h1 { font-size: 25px !important; }
    h2 { font-size: 21px !important; }
    h3 { font-size: 18px !important; }

    [data-testid="stDataFrame"] {
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: auto !important;
    }

    .trade-card {
        padding: 0.75rem !important;
    }
}

/* Card Presentation */
.trade-card {
    width: 100%;
    box-sizing: border-box;
    border: 1px solid rgba(128, 128, 128, 0.30);
    border-radius: 12px;
    padding: 1rem;
    margin: 0.5rem 0;
    overflow-wrap: anywhere;
}

.small {
    font-size: 0.88rem;
    opacity: 0.85;
    overflow-wrap: anywhere;
    word-break: break-word;
}

.reason {
    line-height: 1.5;
    overflow-wrap: anywhere;
    word-break: break-word;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# OPTIONAL ANALYTIC ENGINES (GRACEFUL FALLBACK)
# =========================================================

try:
    from telemetry_engine import TelemetryEngine
except Exception:
    TelemetryEngine = None

try:
    from options_engine import OptionsEngine
except Exception:
    OptionsEngine = None

try:
    from tomorrow_forecast_engine import build_tomorrow_forecast
except Exception:
    build_tomorrow_forecast = None

# =========================================================
# UTILITY AND NORMALIZATION FUNCTIONS
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
        val = float(x)
        return val if np.isfinite(val) else default
    except Exception:
        return default


def fmt(x, digits=2):
    val = num(x)
    if val is None:
        return "-"
    return f"{val:,.{digits}f}"


def safe_text(x):
    return str(x) if x is not None else ""


def market_open():
    """Validates active trading sessions in IST."""
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False

    NSE_HOLIDAYS = {
        "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31",
        "2026-04-03", "2026-04-14", "2026-05-01", "2026-06-26",
        "2026-08-15", "2026-08-26", "2026-09-14", "2026-10-02",
        "2026-10-20", "2026-11-09", "2026-11-10", "2026-11-24",
        "2026-12-25",
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
        "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y",
        "%d%b%Y", "%d-%b-%Y", "%d%b%y", "%d-%b-%y",
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
    for name in names:
        if isinstance(row, dict) and name in row:
            val = row.get(name)
            if val is not None and str(val) != "":
                return val
        try:
            if hasattr(row, "index") and name in row.index:
                val = row[name]
                if pd.notna(val):
                    return val
        except Exception:
            pass
    return default


def find_column(df, names):
    for name in names:
        if name in df.columns:
            return name
    return None


def normalize_option_type(value):
    if value is None:
        return ""
    x = str(value).strip().upper()
    if x in ["CE", "CALL", "C"] or x.endswith("CE") or "CALL" in x:
        return "CE"
    if x in ["PE", "PUT", "P"] or x.endswith("PE") or "PUT" in x:
        return "PE"
    return ""

# =========================================================
# SECRETS MANAGEMENT
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

GEMINI_MODEL = secret("GEMINI_MODEL") or "gemini-2.5-flash"

# =========================================================
# INSTITUTIONAL CAPITAL FLOW INGESTION (FII / DII)
# =========================================================

FII_DII_API = "https://fii-diidata.mrchartist.com/api/data"
FII_DII_HISTORY_API = "https://fii-diidata.mrchartist.com/api/history"


def extract_number(obj, keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj:
            val = num(obj.get(key))
            if val is not None:
                return val
    return None


def find_nested_record(obj):
    if isinstance(obj, dict):
        for key in ["data", "result", "latest", "current", "record"]:
            val = obj.get(key)
            if isinstance(val, dict):
                return val
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return val[0]
        return obj
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj[0]
    return {}


def parse_fii_dii_record(record):
    record = find_nested_record(record)
    fii_buy = extract_number(record, ["fii_buy", "fiiBuy", "fiibuy", "fb", "FII Buy", "FII_Buy"])
    fii_sell = extract_number(record, ["fii_sell", "fiiSell", "fiisell", "fs", "FII Sell", "FII_Sell"])
    fii_net = extract_number(record, ["fii_net", "fiiNet", "fiinet", "fn", "FII Net", "FII_Net"])
    dii_buy = extract_number(record, ["dii_buy", "diiBuy", "diibuy", "db", "DII Buy", "DII_Buy"])
    dii_sell = extract_number(record, ["dii_sell", "diiSell", "diisell", "ds", "DII Sell", "DII_Sell"])
    dii_net = extract_number(record, ["dii_net", "diiNet", "diinet", "dn", "DII Net", "DII_Net"])

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
        response = requests.get(FII_DII_API, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
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
        hist_resp = requests.get(FII_DII_HISTORY_API, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if hist_resp.ok:
            h_data = hist_resp.json()
            if isinstance(h_data, dict):
                for k in ["data", "history", "results"]:
                    if isinstance(h_data.get(k), list):
                        history = h_data[k]
                        break
            elif isinstance(h_data, list):
                history = h_data
    except Exception:
        history = []

    fii_history, dii_history = [], []
    for item in history[:5]:
        row = parse_fii_dii_record(item)
        if row["fii_net"] is not None:
            fii_history.append(row["fii_net"])
        if row["dii_net"] is not None:
            dii_history.append(row["dii_net"])

    fii_vals = [fii_net] + fii_history[:2] if fii_net is not None else fii_history[:3]
    dii_vals = [dii_net] + dii_history[:2] if dii_net is not None else dii_history[:3]

    fii_3d = sum(fii_vals) if fii_vals else None
    dii_3d = sum(dii_vals) if dii_vals else None

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
        bias = "FII POSITIVE" if fii_net > 500 else ("FII NEGATIVE" if fii_net < -500 else "MIXED")

    bias_score = "POSITIVE" if score > 0 else ("NEGATIVE" if score < 0 else "NEUTRAL")

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
        "combined_net": (fii_net + dii_net) if (fii_net is not None and dii_net is not None) else None,
        "fii_3d": fii_3d,
        "dii_3d": dii_3d,
        "institutional_score": score,
        "bias": bias,
        "bias_score": bias_score,
        "status": "Latest available / provisional",
    }


fii_dii = fetch_fii_dii()

# =========================================================
# CLIENT ENGINE INSTANTIATION
# =========================================================

@st.cache_resource(show_spinner=False)
def create_telemetry():
    if TelemetryEngine is None:
        return None
    if not all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET]):
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
            token = getattr(telemetry_obj.smart_api, "access_token", None)
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
# MARKET CONFIGURATION AND SPOT EXTRACTION
# =========================================================

UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]

SPOT_TOKENS = {
    "NIFTY": ("NSE", "99926000"),
    "BANKNIFTY": ("NSE", "99926009"),
    "FINNIFTY": ("NSE", "99926037"),
    "MIDCPNIFTY": ("NSE", "99926074"),
    "SENSEX": ("BSE", "99919000"),
    "BANKEX": ("BSE", "99919012"),
}


def get_spot(symbol):
    if telemetry is not None:
        try:
            result = telemetry.get_ltp(symbol)
            if isinstance(result, dict):
                for key in ("ltp", "LTP", "lastTradedPrice", "lastTradedPriceValue", "close", "price"):
                    if key in result:
                        val = num(result[key])
                        if val is not None and val > 0:
                            return val
            val = num(result)
            if val is not None and val > 0:
                return val
        except Exception:
            pass

    try:
        df = fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=5)
        if df is not None and not df.empty and "close" in df.columns:
            close = pd.to_numeric(df["close"], errors="coerce").dropna()
            if not close.empty:
                val = float(close.iloc[-1])
                if val > 0:
                    return val
    except Exception:
        pass
    return None

# =========================================================
# DERIVATIVES CONTRACTS AND OPTION CHAIN INGESTION
# =========================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_expiries(symbol):
    if options is None:
        return []
    try:
        result = options.get_expiry_options(symbol)
        values = []
        for item in result or []:
            val = item.get("value") or item.get("expiry") or item.get("expiryDate") if isinstance(item, dict) else item
            val = expiry_norm(val)
            if not val:
                continue
            try:
                d = datetime.strptime(val, "%Y-%m-%d").date()
                if d >= date.today():
                    values.append(val)
            except Exception:
                pass
        return sorted(set(values))
    except Exception:
        return []


@st.cache_data(ttl=120, show_spinner=False)
def load_contracts(symbol, expiry):
    if options is None or not expiry:
        return pd.DataFrame()
    try:
        return clean_df(options.get_option_contracts(underlying=symbol, expiry_date=expiry))
    except Exception:
        return pd.DataFrame()


def get_chain(symbol, expiry, spot):
    contracts = load_contracts(symbol, expiry)
    if contracts.empty:
        return pd.DataFrame(), contracts

    def normalize_strike_value(v):
        try:
            val = float(v)
            if abs(val) >= 100000:
                val = val / 100.0
            return val
        except Exception:
            return None

    try:
        strike_col = find_column(contracts, ["strike", "strikePrice", "strike_price"])
        if strike_col:
            contracts["strikePrice"] = pd.to_numeric(contracts[strike_col], errors="coerce").apply(normalize_strike_value)
            contracts["strike"] = contracts["strikePrice"]
    except Exception:
        pass

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
                n_col = find_column(contracts, ["strike", "strikePrice", "strike_price"])
                if n_col:
                    contracts["strikePrice"] = pd.to_numeric(contracts[n_col], errors="coerce").apply(normalize_strike_value)
                    contracts["strike"] = contracts["strikePrice"]
    except Exception:
        pass

    try:
        quoted = clean_df(options.get_market_quote(contracts))
        chain = quoted if not quoted.empty else contracts.copy()
    except Exception:
        chain = contracts.copy()

    type_col = find_column(chain, ["option_type", "optionType", "optionTypeName", "option_type_name", "type"])
    if type_col:
        chain["option_type"] = chain[type_col].map(normalize_option_type)

    stk_col = find_column(chain, ["strike", "strikePrice", "strike_price"])
    if stk_col:
        chain["strikePrice"] = pd.to_numeric(chain[stk_col], errors="coerce").apply(normalize_strike_value)
        chain["strike"] = chain["strikePrice"]

    oi_col = find_column(chain, ["opnInterest", "openInterest", "oi", "open_interest"])
    if oi_col:
        chain["openInterest"] = pd.to_numeric(chain[oi_col], errors="coerce")

    chg_oi = find_column(chain, ["changeinOpenInterest", "changeInOpenInterest", "change_in_open_interest", "change_oi", "chg_oi", "oi_change"])
    if chg_oi:
        chain["changeInOpenInterest"] = pd.to_numeric(chain[chg_oi], errors="coerce")

    try:
        if options is not None:
            greeks = clean_df(options.greeks_dataframe(symbol, expiry))
            if not greeks.empty:
                g_stk = find_column(greeks, ["strikePrice", "strike", "strike_price"])
                if g_stk:
                    greeks["strikePrice"] = pd.to_numeric(greeks[g_stk], errors="coerce").apply(normalize_strike_value)
                    greek_cols = [c for c in ["strikePrice", "delta", "gamma", "theta", "vega", "impliedVolatility"] if c in greeks.columns]
                    g_type = find_column(greeks, ["optionType", "option_type", "optionTypeName"])
                    if g_type:
                        greeks["option_type"] = greeks[g_type].map(normalize_option_type)
                        chain = chain.merge(
                            greeks[greek_cols + ["option_type"]].drop_duplicates(subset=["strikePrice", "option_type"]),
                            on=["strikePrice", "option_type"],
                            how="left",
                            suffixes=("", "_greek")
                        )
                    else:
                        chain = chain.merge(
                            greeks[greek_cols].drop_duplicates(subset=["strikePrice"]),
                            on="strikePrice",
                            how="left",
                            suffixes=("", "_greek")
                        )
    except Exception:
        pass

    return chain.reset_index(drop=True), contracts.reset_index(drop=True)

# =========================================================
# PCR AND DERIVATIVE PROXY ENGINE
# =========================================================

def calculate_pcr(df):
    if df is not None and not df.empty:
        oi_col = find_column(df, ["opnInterest", "openInterest", "oi", "open_interest"])
        type_col = find_column(df, ["option_type", "optionType", "optionTypeName", "type"])
        if oi_col and type_col:
            work = df.copy()
            work["_oi"] = pd.to_numeric(work[oi_col].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
            work["_opt_type"] = work[type_col].map(normalize_option_type)
            ce_oi = work.loc[work["_opt_type"] == "CE", "_oi"].sum()
            pe_oi = work.loc[work["_opt_type"] == "PE", "_oi"].sum()
            if ce_oi > 0:
                pcr_val = pe_oi / ce_oi
                if np.isfinite(pcr_val) and 0 < pcr_val <= 10:
                    return float(pcr_val)

    try:
        if options is not None:
            pcr_df = clean_df(options.pcr_dataframe())
            if not pcr_df.empty:
                for col in ["pcr", "putCallRatio", "put_call_ratio"]:
                    if col in pcr_df.columns:
                        vals = pd.to_numeric(pcr_df[col], errors="coerce").dropna()
                        if not vals.empty:
                            v = float(vals.iloc[-1])
                            if np.isfinite(v) and 0 < v <= 10:
                                return v
    except Exception:
        pass
    return None


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

    type_col = find_column(chain, ["option_type", "optionType", "optionTypeName", "type"])
    oi_col = find_column(chain, ["opnInterest", "openInterest", "oi", "open_interest"])
    chg_oi_col = find_column(chain, ["changeinOpenInterest", "changeInOpenInterest", "change_oi", "chg_oi"])

    score = 0
    reasons = []
    usable = False

    if pcr is not None:
        usable = True
        if 1.10 <= pcr <= 1.80:
            score += 2
            reasons.append(f"PCR {pcr:.2f} supportive zone mein hai.")
        elif 0.90 <= pcr < 1.10:
            score += 1
            reasons.append(f"PCR {pcr:.2f} mildly supportive hai.")
        elif 0.70 <= pcr < 0.90:
            reasons.append(f"PCR {pcr:.2f} neutral-to-cautious zone mein hai.")
        elif 0.40 <= pcr < 0.70:
            score -= 1
            reasons.append(f"PCR {pcr:.2f} bearish pressure indicate karta hai.")
        elif pcr < 0.40:
            score -= 2
            reasons.append(f"PCR {pcr:.2f} strong caution zone mein hai.")

    if type_col and chg_oi_col:
        work = chain.copy()
        work["_type"] = work[type_col].map(normalize_option_type)
        work["_chg_oi"] = pd.to_numeric(work[chg_oi_col].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
        ce_change = work.loc[work["_type"] == "CE", "_chg_oi"].sum()
        pe_change = work.loc[work["_type"] == "PE", "_chg_oi"].sum()

        if work["_type"].isin(["CE", "PE"]).any():
            usable = True
            if pe_change > 0 and ce_change < 0:
                score += 1
                reasons.append("Option-chain change in OI mildly bullish bias show kar raha hai.")
            elif ce_change > 0 and pe_change < 0:
                score -= 1
                reasons.append("Option-chain change in OI mildly bearish bias show kar raha hai.")

    if not usable:
        return result

    score = max(-2, min(2, score))
    bias = (
        "BULLISH PROXY" if score >= 2 else (
            "MILD BULLISH PROXY" if score == 1 else (
                "MILD BEARISH PROXY" if score == -1 else (
                    "BEARISH PROXY" if score <= -2 else "NEUTRAL PROXY"
                )
            )
        )
    )

    result.update({
        "available": True,
        "score": score,
        "bias": bias,
        "status": "Live broker option-chain positioning" if market_open() else "Latest broker option-chain positioning",
        "reasons": reasons,
    })
    return result

# =========================================================
# TECHNICAL INDICATOR COMPUTATION ENGINE
# =========================================================

@st.cache_data(ttl=120, show_spinner=False)
def fetch_ohlcv(symbol, interval="FIVE_MINUTE", days=5):
    if telemetry is None or symbol not in SPOT_TOKENS:
        return pd.DataFrame()

    exchange, token = SPOT_TOKENS[symbol]
    try:
        df = clean_df(telemetry.fetch_ohlcv(exchange=exchange, token=token, interval=interval, days=days))
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

        df = df.rename(columns=rename)
        needed = ["open", "high", "low", "close"]
        if not all(c in df.columns for c in needed):
            return pd.DataFrame()

        for c in needed + (["volume"] if "volume" in df.columns else []):
            df[c] = pd.to_numeric(df[c], errors="coerce")

        return df.dropna(subset=needed).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def add_indicators(df):
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()

    close, high, low = df["close"], df["high"], df["low"]
    df["EMA20"] = close.ewm(span=20, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    plus_di = 100 * plus_dm.rolling(14).sum() / atr.rolling(14).sum().replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(14).sum() / atr.rolling(14).sum().replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["ADX"] = dx.rolling(14).mean()

    if "volume" in df.columns:
        typical = (high + low + close) / 3
        cum_vol = df["volume"].cumsum()
        df["VWAP"] = (typical * df["volume"]).cumsum() / cum_vol.replace(0, np.nan)
        df["VOL_AVG20"] = df["volume"].rolling(20).mean()
    else:
        df["VWAP"] = np.nan
        df["VOL_AVG20"] = np.nan

    return df


def analyze_market(symbol, derivatives_proxy=None):
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

    df5 = add_indicators(fetch_ohlcv(symbol, "FIVE_MINUTE", 5))
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
    result["macd_signal"] = num(row.get("MACD_SIGNAL"))
    result["vwap"] = num(row.get("VWAP"))

    if "volume" in df5.columns and num(row.get("volume")) is not None and num(row.get("VOL_AVG20")) not in [None, 0]:
        result["volume_ratio"] = num(row.get("volume")) / num(row.get("VOL_AVG20"))

    recent = df5.tail(30)
    result["support"] = num(recent["low"].min())
    result["resistance"] = num(recent["high"].max())

    score = 0
    if result["ema20"] is not None and result["ema50"] is not None and last is not None:
        if last > result["ema20"] > result["ema50"]:
            score += 2
            result["reasons"].append("Price EMA20 aur EMA50 ke upar sustained hai.")
        elif last < result["ema20"] < result["ema50"]:
            score -= 2
            result["reasons"].append("Price EMA20 aur EMA50 ke neeche sustained hai.")

    if result["vwap"] is not None and last is not None:
        if last > result["vwap"]:
            score += 1
            result["reasons"].append("Price VWAP ke upar trade kar raha hai.")
        elif last < result["vwap"]:
            score -= 1
            result["reasons"].append("Price VWAP ke neeche trade kar raha hai.")

    if result["macd"] is not None and result["macd_signal"] is not None:
        if result["macd"] > result["macd_signal"]:
            score += 1
            result["reasons"].append("MACD bullish cross state mein hai.")
        else:
            score -= 1
            result["reasons"].append("MACD bearish cross state mein hai.")

    if result["rsi"] is not None:
        if result["rsi"] >= 60:
            score += 1
            result["momentum"] = "BULLISH"
        elif result["rsi"] <= 40:
            score -= 1
            result["momentum"] = "BEARISH"

    if result["adx"] is not None and result["adx"] >= 20:
        result["reasons"].append(f"ADX {result['adx']:.1f} active trend strength indicate karta hai.")

    if result["volume_ratio"] is not None and result["volume_ratio"] >= 1.3:
        result["reasons"].append("Volume 20-period average se significantly higher hai.")

    result["technical_score"] = score

    if fii_dii.get("available"):
        inst_score = int(fii_dii.get("institutional_score", 0))
        result["institutional_score"] = inst_score
        result["institutional_bias"] = fii_dii.get("bias", "MIXED")
        result["institutional_source"] = "ACTUAL FII/DII"
        if inst_score > 0:
            result["reasons"].append("Actual FII/DII institutional buying market ko support de rahi hai.")
        elif inst_score < 0:
            result["reasons"].append("Actual FII/DII net selling pressure exert kar rahi hai.")
        else:
            result["reasons"].append("Actual FII/DII flow neutral zone mein hai.")
    elif derivatives_proxy is not None and derivatives_proxy.get("available"):
        inst_score = int(derivatives_proxy.get("score", 0))
        result["institutional_score"] = inst_score
        result["institutional_bias"] = derivatives_proxy.get("bias", "DERIVATIVES PROXY")
        result["institutional_source"] = "LIVE DERIVATIVES PROXY"
        result["reasons"].append("FII/DII cash flow pending hai; live option-chain positioning proxy active hai.")
        result["reasons"].extend(derivatives_proxy.get("reasons", []))
    else:
        result["institutional_score"] = 0
        result["institutional_bias"] = "FII/DII PENDING"
        result["institutional_source"] = "NONE"
        result["reasons"].append("Institutional data unavailable; institutional score zeroed out.")

    result["score"] = score + result["institutional_score"]

    if result["score"] >= 4:
        result["trend"] = "BULLISH"
    elif result["score"] <= -4:
        result["trend"] = "BEARISH"
    else:
        result["trend"] = "SIDEWAYS"

    return result

# =========================================================
# MULTI-TIMEFRAME CONFIRMATION ENGINE
# =========================================================

@st.cache_data(ttl=120, show_spinner=False)
def fetch_confirmation_timeframe(symbol, interval, days):
    try:
        df = fetch_ohlcv(symbol, interval, days)
        return add_indicators(df) if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def analyze_confirmation_timeframe(df, label):
    res = {
        "label": label,
        "available": False,
        "trend": "UNKNOWN",
        "score": 0,
        "last": None,
        "ema20": None,
        "ema50": None,
        "rsi": None,
        "adx": None,
        "vwap": None,
        "volume_ratio": None,
        "structure": "UNKNOWN",
        "reasons": [],
    }

    if df is None or df.empty:
        return res

    row = df.iloc[-1]
    last = num(row.get("close"))
    if last is None:
        return res

    res["available"] = True
    res["last"] = last
    res["ema20"] = num(row.get("EMA20"))
    res["ema50"] = num(row.get("EMA50"))
    res["rsi"] = num(row.get("RSI"))
    res["adx"] = num(row.get("ADX"))
    res["vwap"] = num(row.get("VWAP"))

    if "volume" in df.columns and num(row.get("volume")) is not None and num(row.get("VOL_AVG20")) not in [None, 0]:
        res["volume_ratio"] = num(row.get("volume")) / num(row.get("VOL_AVG20"))

    score = 0
    if res["ema20"] is not None and res["ema50"] is not None:
        if last > res["ema20"] > res["ema50"]:
            score += 2
            res["reasons"].append(f"{label}: EMA alignment bullish.")
        elif last < res["ema20"] < res["ema50"]:
            score -= 2
            res["reasons"].append(f"{label}: EMA alignment bearish.")

    if res["vwap"] is not None:
        if last > res["vwap"]:
            score += 1
            res["reasons"].append(f"{label}: price VWAP ke upar trade kar raha hai.")
        elif last < res["vwap"]:
            score -= 1
            res["reasons"].append(f"{label}: price VWAP ke neeche trade kar raha hai.")

    if res["rsi"] is not None:
        if res["rsi"] >= 55:
            score += 1
        elif res["rsi"] <= 45:
            score -= 1

    macd = num(row.get("MACD"))
    macd_signal = num(row.get("MACD_SIGNAL"))
    if macd is not None and macd_signal is not None:
        score += 1 if macd > macd_signal else -1

    if res["adx"] is not None and res["adx"] >= 20:
        res["reasons"].append(f"{label}: ADX {res['adx']:.1f} trend active.")

    if len(df) >= 8:
        recent = df.tail(8)
        r_highs = recent["high"].tail(4).values
        p_highs = recent["high"].head(4).values
        r_lows = recent["low"].tail(4).values
        p_lows = recent["low"].head(4).values
        try:
            if np.nanmean(r_highs) > np.nanmean(p_highs) and np.nanmean(r_lows) > np.nanmean(p_lows):
                res["structure"] = "HIGHER HIGH / HIGHER LOW"
                score += 2
                res["reasons"].append(f"{label}: bullish market structure (HH/HL).")
            elif np.nanmean(r_highs) < np.nanmean(p_highs) and np.nanmean(r_lows) < np.nanmean(p_lows):
                res["structure"] = "LOWER HIGH / LOWER LOW"
                score -= 2
                res["reasons"].append(f"{label}: bearish market structure (LH/LL).")
        except Exception:
            pass

    if res["volume_ratio"] is not None and res["volume_ratio"] >= 1.20:
        res["reasons"].append(f"{label}: volume expansion confirmed.")

    res["score"] = score
    res["trend"] = "BULLISH" if score >= 2 else ("BEARISH" if score <= -2 else "NEUTRAL")
    return res


def build_trade_confirmation(symbol, market):
    conf = {
        "available": False,
        "status": "WAIT",
        "direction": "NEUTRAL",
        "score": 0,
        "max_score": 0,
        "strength": 0,
        "timeframes": {},
        "checks": [],
        "reasons": [],
        "warnings": [],
    }

    tf_configs = [("5M", "FIVE_MINUTE", 5), ("15M", "FIFTEEN_MINUTE", 10), ("1H", "ONE_HOUR", 20)]
    results = []
    for label, interval, days in tf_configs:
        df = fetch_confirmation_timeframe(symbol, interval, days)
        analysis = analyze_confirmation_timeframe(df, label)
        conf["timeframes"][label] = analysis
        if analysis["available"]:
            results.append(analysis)

    if not results:
        conf["warnings"].append("Multi-timeframe data completely unavailable.")
        return conf

    conf["available"] = True
    bull_votes = sum(1 for x in results if x["trend"] == "BULLISH")
    bear_votes = sum(1 for x in results if x["trend"] == "BEARISH")

    if bull_votes >= 2 and bull_votes > bear_votes:
        direction = "BULLISH"
    elif bear_votes >= 2 and bear_votes > bull_votes:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    conf["direction"] = direction
    raw_score = sum(x["score"] for x in results)
    conf["score"] = raw_score
    max_possible = len(results) * 7
    conf["max_score"] = max_possible

    if max_possible > 0:
        conf["strength"] = round(min(100, abs(raw_score) / max_possible * 100), 1)

    if bull_votes >= 2 and bear_votes == 0:
        conf["checks"].append("MTF BULLISH ALIGNMENT")
        conf["score"] += 2
        conf["reasons"].append("5M/15M/1H intervals fully aligned on bullish side.")
    elif bear_votes >= 2 and bull_votes == 0:
        conf["checks"].append("MTF BEARISH ALIGNMENT")
        conf["score"] -= 2
        conf["reasons"].append("5M/15M/1H intervals fully aligned on bearish side.")
    else:
        conf["warnings"].append("Timeframes mixed divergence show kar rahe hain.")

    bull_struct = sum(1 for x in results if x["structure"] == "HIGHER HIGH / HIGHER LOW")
    bear_struct = sum(1 for x in results if x["structure"] == "LOWER HIGH / LOWER LOW")

    if bull_struct >= 2:
        conf["checks"].append("BULLISH PRICE STRUCTURE")
        conf["score"] += 2
        conf["reasons"].append("Multiple timeframes higher-high / higher-low structure validate kar rahe hain.")
    elif bear_struct >= 2:
        conf["checks"].append("BEARISH PRICE STRUCTURE")
        conf["score"] -= 2
        conf["reasons"].append("Multiple timeframes lower-high / lower-low structure validate kar rahe hain.")

    if any(x["volume_ratio"] is not None and x["volume_ratio"] >= 1.20 for x in results):
        conf["checks"].append("VOLUME CONFIRMATION")
        conf["reasons"].append("Volume confirmation multiple intervals par present hai.")

    m_score = float(market.get("technical_score", 0) or 0)
    if direction == "BULLISH" and m_score > 0:
        conf["checks"].append("TECHNICAL DIRECTION ALIGNED")
        conf["score"] += 2
    elif direction == "BEARISH" and m_score < 0:
        conf["checks"].append("TECHNICAL DIRECTION ALIGNED")
        conf["score"] -= 2

    final_score = conf["score"]
    if direction == "BULLISH":
        conf["status"] = "CONFIRMED" if final_score >= 5 else ("WATCH" if final_score >= 2 else "REJECT")
    elif direction == "BEARISH":
        conf["status"] = "CONFIRMED" if final_score <= -5 else ("WATCH" if final_score <= -2 else "REJECT")
    else:
        conf["status"] = "WATCH"

    return conf

# =========================================================
# REFACTORED TRADE IDEA GENERATION ENGINE
# =========================================================

def nearest_option(chain, spot, side):
    if chain.empty or spot is None:
        return None
    type_col = find_column(chain, ["option_type", "optionType", "optionTypeName", "type"])
    strike_col = find_column(chain, ["strike", "strikePrice", "strike_price"])
    if not type_col or not strike_col:
        return None

    work = chain.copy()
    work["_type"] = work[type_col].map(normalize_option_type)
    work = work[work["_type"] == side].copy()
    if work.empty:
        return None

    work["_strike"] = pd.to_numeric(work[strike_col].astype(str).str.replace(",", "", regex=False), errors="coerce")
    work = work.dropna(subset=["_strike"])
    if work.empty:
        return None

    work["_distance"] = (work["_strike"] - spot).abs()
    return work.sort_values("_distance").iloc[0]


def option_ltp(row):
    return num(first_value(row, ["ltp", "LTP", "lastTradedPrice", "last_price"]))


def make_trade_idea(
    market,
    symbol,
    instrument="INDEX",
    option_side=None,
    expiry=None,
    chain=None,
):
    """
    Refactored, deterministic trade generation module.
    Eliminates all unreachable blocks and ensures strict parameter binding.
    """
    last = market.get("last")
    if last is None:
        return None

    entry_spot = num(last)
    if entry_spot is None or entry_spot <= 0:
        return None

    confirmation = build_trade_confirmation(symbol, market)
    if not confirmation.get("available") or confirmation.get("status") == "REJECT":
        return None

    technical_score = float(market.get("technical_score", 0) or 0)
    institutional_score = float(market.get("institutional_score", 0) or 0)
    combined_score = float(market.get("score", technical_score + institutional_score) or 0)

    if combined_score >= 2:
        bullish = True
    elif combined_score <= -2:
        bullish = False
    else:
        if technical_score > 0:
            bullish = True
        elif technical_score < 0:
            bullish = False
        else:
            return None

    direction = "BUY" if bullish else "SELL"
    support = num(market.get("support"))
    resistance = num(market.get("resistance"))

    if bullish:
        sl = support if (support is not None and support < entry_spot) else (entry_spot * 0.997)
        risk = entry_spot - sl
        if risk <= 0:
            return None
        target1 = entry_spot + (risk * 1.5)
        target2 = entry_spot + (risk * 2.5)
    else:
        sl = resistance if (resistance is not None and resistance > entry_spot) else (entry_spot * 1.003)
        risk = sl - entry_spot
        if risk <= 0:
            return None
        target1 = entry_spot - (risk * 1.5)
        target2 = entry_spot - (risk * 2.5)

    confidence = min(95, max(65, 65 + abs(combined_score) * 4 + abs(institutional_score) * 2))

    idea = {
        "segment": instrument,
        "symbol": symbol,
        "action": direction,
        "entry": entry_spot,
        "sl": sl,
        "target1": target1,
        "target2": target2,
        "risk_reward": (abs(target1 - entry_spot) / risk) if risk > 0 else 1.5,
        "target2_risk_reward": (abs(target2 - entry_spot) / risk) if risk > 0 else 2.5,
        "confidence": confidence,
        "holding": "Intraday" if market_open() else "NEXT SESSION",
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
        "institutional_bias": market.get("institutional_bias", "UNAVAILABLE"),
        "institutional_source": market.get("institutional_source", "NONE"),
        "why": " ".join(market.get("reasons", [])[:8]),
        "invalidation": f"Price {'below' if bullish else 'above'} SL level sustain kare.",
    }

    if instrument == "INDEX OPTION" and chain is not None and not chain.empty:
        opt_type = option_side if option_side in ["CE", "PE"] else ("CE" if bullish else "PE")
        selected = nearest_option(chain, entry_spot, opt_type)

        if selected is not None:
            strike = first_value(selected, ["strike", "strikePrice", "strike_price"])
            opt_price = option_ltp(selected)

            idea["option"] = opt_type
            idea["action"] = "BUY"
            idea["strike"] = strike
            idea["option_ltp"] = opt_price
            idea["oi"] = num(first_value(selected, ["openInterest", "opnInterest", "oi"]))
            idea["change_oi"] = num(first_value(selected, ["changeInOpenInterest", "changeinOpenInterest", "change_oi"]))
            idea["delta"] = num(first_value(selected, ["delta"]))
            idea["gamma"] = num(first_value(selected, ["gamma"]))
            idea["theta"] = num(first_value(selected, ["theta"]))
            idea["vega"] = num(first_value(selected, ["vega"]))
            idea["iv"] = num(first_value(selected, ["impliedVolatility", "iv"]))

            if opt_price is not None and opt_price > 0:
                opt_entry = float(opt_price)
                opt_sl = opt_entry * 0.85
                opt_t1 = opt_entry * 1.20
                opt_t2 = opt_entry * 1.35
                opt_risk = opt_entry - opt_sl

                if opt_risk > 0:
                    idea["entry"] = opt_entry
                    idea["sl"] = opt_sl
                    idea["target1"] = opt_t1
                    idea["target2"] = opt_t2
                    idea["risk_reward"] = (opt_t1 - opt_entry) / opt_risk
                    idea["target2_risk_reward"] = (opt_t2 - opt_entry) / opt_risk

            dir_text = "Bullish" if bullish else "Bearish"
            idea["why"] = (
                f"{idea['why']} {dir_text} setup confirmation: "
                f"BUY {opt_type} near ATM strike {strike}. "
                f"Option buying model active; no short positions suggested."
            ).strip()

    return idea

# =========================================================
# GENERATIVE AI INTEGRATION (DUAL SDK RESILIENCE)
# =========================================================

def ask_gemini(ideas, market_data):
    if not GEMINI_API_KEY:
        return None

    payload = {
        "market": market_data,
        "ideas": ideas,
        "fii_dii": fii_dii,
    }

    prompt = f"""
You are an Indian financial markets research analyst for a PAPER TRADING ONLY system.
Rely STRICTLY on the supplied data. Do NOT extrapolate or fabricate numbers.

CRITICAL RULES:
1. Actual FII/DII data maintains priority when available.
2. If actual FII/DII is absent, the LIVE DERIVATIVES PROXY must be explicitly noted as a proxy.
3. Detail technical structures, institutional context, derivative positioning, risks, and invalidations.
4. If a setup lacks conviction, output NO TRADE / WAIT clearly.

DATA PAYLOAD:
{json.dumps(payload, default=str)}
"""

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return getattr(response, "text", None)
    except ImportError:
        pass
    except Exception as e:
        return f"Primary AI engine error: {e}"

    try:
        import google.generativeai as legacy_genai
        legacy_genai.configure(api_key=GEMINI_API_KEY)
        model = legacy_genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return getattr(response, "text", None)
    except Exception as e:
        return f"AI explanation unavailable: {e}"

# =========================================================
# APPLICATION DASHBOARD RENDERING
# =========================================================

st.title("📊 AI Trading Expert Advisor")
st.caption("Live/After-Market Research • Options • Equities • Technical Analysis • FII/DII • Paper Trading Only")

h1, h2, h3, h4 = st.columns(4)
with h1:
    st.metric("Mode", "PAPER ONLY")
with h2:
    st.metric("Market", "OPEN" if market_open() else "AFTER MARKET")
with h3:
    st.metric("Angel One", "CONNECTED" if telemetry is not None else "NOT CONNECTED")
with h4:
    st.metric("AI Status", "READY" if GEMINI_API_KEY else "DATA MODE")

st.warning("PAPER TRADING ONLY — System execution creates zero live broker orders.")

st.sidebar.header("⚙️ Expert Advisor")
old_underlying = st.session_state.get("underlying", "NIFTY")
if old_underlying not in UNDERLYINGS:
    old_underlying = "NIFTY"

underlying = st.sidebar.selectbox("Underlying", UNDERLYINGS, index=UNDERLYINGS.index(old_underlying))
st.session_state["underlying"] = underlying

expiries = load_expiries(underlying)
selected_expiry = None

if expiries:
    old_expiry = st.session_state.get("expiry")
    if old_expiry not in expiries:
        old_expiry = expiries[0]
    selected_expiry = st.sidebar.selectbox(
        "Expiry",
        expiries,
        index=expiries.index(old_expiry),
        format_func=expiry_label,
    )
    st.session_state["expiry"] = selected_expiry
else:
    st.sidebar.info("Expiry series unavailable.")

option_type_choice = st.sidebar.selectbox("Option Type", ["CE", "PE", "BOTH"])

if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

spot = get_spot(underlying)

st.subheader("📌 Current Market")
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Underlying", underlying)
with m2:
    st.metric("LTP", fmt(spot))
with m3:
    st.metric("Expiry", expiry_label(selected_expiry) if selected_expiry else "-")
with m4:
    st.metric("Session", "LIVE" if market_open() else "AFTER MARKET")

chain = pd.DataFrame()
if selected_expiry:
    chain, all_contracts = get_chain(underlying, selected_expiry, spot)

pcr = calculate_pcr(chain)
derivatives_proxy = calculate_live_derivatives_proxy(chain, pcr)
market = analyze_market(underlying, derivatives_proxy)

# =========================================================
# TOMORROW MARKET BLUEPRINT
# =========================================================

st.markdown("## 🔮 Tomorrow Market Blueprint")

if build_tomorrow_forecast is None:
    st.warning("Tomorrow Forecast Engine currently unavailable.")
else:
    try:
        tomorrow_data = {
            "symbol": underlying,
            "spot": market.get("last"),
            "support": market.get("support"),
            "resistance": market.get("resistance"),
            "rsi": market.get("rsi"),
            "adx": market.get("adx"),
            "ema20": market.get("ema20"),
            "ema50": market.get("ema50"),
            "vwap": market.get("vwap"),
            "technical_score": market.get("technical_score", 0),
            "institutional_score": market.get("institutional_score", 0),
            "score": market.get("score", 0),
            "institutional_bias": market.get("institutional_bias", "UNAVAILABLE"),
            "pcr": pcr,
            "fii_net": fii_dii.get("fii_net"),
            "dii_net": fii_dii.get("dii_net"),
        }

        tomorrow = build_tomorrow_forecast(tomorrow_data)
        if tomorrow:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Next Session Bias", tomorrow.get("bias", "N/A"))
            c2.metric("Forecast Confidence", f"{num(tomorrow.get('confidence'), 0):.0f}%")
            c3.metric("Combined Score", f"{num(tomorrow.get('combined_score'), 0):+.1f}")
            c4.metric("Data Quality", tomorrow.get("data_quality", "N/A"))

            st.markdown("### 📊 Reference Levels")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Reference Spot", fmt(tomorrow.get("spot")))
            r2.metric("Support", fmt(tomorrow.get("support")))
            r3.metric("Resistance", fmt(tomorrow.get("resistance")))

            exp_range = tomorrow.get("expected_range")
            range_text = "N/A"
            if isinstance(exp_range, dict):
                low_val = num(exp_range.get("low"))
                high_val = num(exp_range.get("high"))
                if low_val is not None and high_val is not None:
                    range_text = f"{low_val:,.2f} - {high_val:,.2f}"

            r4.metric("Expected Range", range_text)

            st.markdown("### 🎯 Key Triggers")
            t1, t2 = st.columns(2)
            with t1:
                st.success(f"**Bullish Trigger**\n\n{tomorrow.get('bullish_trigger', 'N/A')}")
            with t2:
                st.error(f"**Bearish Trigger**\n\n{tomorrow.get('bearish_trigger', 'N/A')}")

            st.markdown("### 🧠 Market Scenarios")
            scenarios = tomorrow.get("scenarios", [])
            if scenarios:
                for sc in scenarios:
                    st.write(f"**{sc.get('scenario', 'Scenario')}** — {sc.get('condition', '')}")
                    st.caption(sc.get("view", ""))
            else:
                st.info("No scenario distributions formulated.")

            st.markdown("### 🔎 Research Reasons")
            reasons = tomorrow.get("reasons", [])
            if reasons:
                for r in reasons:
                    st.write(f"• {r}")
            else:
                st.info("No qualitative observations available.")

            st.markdown("### ⚠️ Invalidation")
            st.warning(tomorrow.get("invalidation", "Forecast invalidation level unavailable."))
            st.caption(tomorrow.get("disclaimer", "Scenario-based research only. Non-guaranteed."))
        else:
            st.info("Tomorrow forecast evaluation returned empty record.")
    except Exception as e:
        st.warning(f"Tomorrow Market Blueprint encountered an issue: {e}")

# =========================================================
# INSTITUTIONAL CAPITAL FLOW VISUALIZATION
# =========================================================

st.subheader("🏦 Institutional Flow")
if fii_dii["available"]:
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.metric("FII Net", f"₹{fmt(fii_dii['fii_net'], 0)} Cr" if fii_dii["fii_net"] is not None else "Unavailable")
    with f2:
        st.metric("DII Net", f"₹{fmt(fii_dii['dii_net'], 0)} Cr" if fii_dii["dii_net"] is not None else "Unavailable")
    with f3:
        st.metric("Combined Net", f"₹{fmt(fii_dii['combined_net'], 0)} Cr" if fii_dii["combined_net"] is not None else "Unavailable")
    with f4:
        st.metric("Institutional Score", f"{fii_dii['institutional_score']:+d}")

    f5, f6, f7, f8 = st.columns(4)
    with f5:
        st.metric("FII 3-Session", f"₹{fmt(fii_dii['fii_3d'], 0)} Cr" if fii_dii["fii_3d"] is not None else "-")
    with f6:
        st.metric("DII 3-Session", f"₹{fmt(fii_dii['dii_3d'], 0)} Cr" if fii_dii["dii_3d"] is not None else "-")
    with f7:
        st.metric("Institutional Bias", fii_dii["bias"])
    with f8:
        st.metric("Source", "ACTUAL")

    st.caption(f"Source: {fii_dii['source']} • {fii_dii['status']} • Date: {safe_text(fii_dii['date'])}")
else:
    st.warning("Actual FII/DII cash-flow data unavailable. System automatically fails over to live derivative positioning proxies.")

# =========================================================
# DERIVATIVES POSITIONING PROXY VIEW
# =========================================================

st.subheader("🧮 Derivatives Institutional Proxy")
if derivatives_proxy.get("available"):
    d1, d2, d3 = st.columns(3)
    with d1:
        st.metric("Proxy Score", f"{derivatives_proxy['score']:+d}")
    with d2:
        st.metric("Proxy Bias", derivatives_proxy["bias"])
    with d3:
        st.metric("PCR", fmt(derivatives_proxy.get("pcr"), 2))

    st.caption(f"Source: {derivatives_proxy['source']} • {derivatives_proxy['status']}")
    for reason in derivatives_proxy.get("reasons", []):
        st.write(f"• {reason}")
else:
    st.info("Usable derivatives positioning unavailable. Institutional allocation anchored at zero weight.")

# =========================================================
# TECHNICAL INTELLIGENCE
# =========================================================

st.subheader("📈 Market Intelligence")
a1, a2, a3, a4 = st.columns(4)
with a1:
    st.metric("Trend", market["trend"])
with a2:
    st.metric("Momentum", market["momentum"])
with a3:
    st.metric("RSI", fmt(market["rsi"], 1))
with a4:
    st.metric("ADX", fmt(market["adx"], 1))

a5, a6, a7, a8 = st.columns(4)
with a5:
    st.metric("EMA20", fmt(market["ema20"]))
with a6:
    st.metric("EMA50", fmt(market["ema50"]))
with a7:
    st.metric("VWAP", fmt(market["vwap"]))
with a8:
    st.metric("Volume Ratio", fmt(market["volume_ratio"], 2))

a9, a10, a11, a12 = st.columns(4)
with a9:
    st.metric("Technical Score", f"{market.get('technical_score', 0):+d}")
with a10:
    st.metric("Institutional Score", f"{market.get('institutional_score', 0):+d}")
with a11:
    st.metric("Combined Score", f"{market.get('score', 0):+d}")
with a12:
    st.metric("Institutional Source", market.get("institutional_source", "NONE"))

r1, r2 = st.columns(2)
with r1:
    st.metric("Support", fmt(market["support"]))
with r2:
    st.metric("Resistance", fmt(market["resistance"]))

if market["reasons"]:
    st.markdown("### Structural Observations")
    for reason in market["reasons"]:
        st.write(f"• {reason}")

# =========================================================
# DERIVATIVE CHAIN VISUALIZATION
# =========================================================

st.subheader("🧮 Options Intelligence")
o1, o2, o3 = st.columns(3)
with o1:
    st.metric("PCR", fmt(pcr, 2))
with o2:
    st.metric("Total Contracts", len(chain))
with o3:
    st.metric("Target Expiry", expiry_label(selected_expiry) if selected_expiry else "-")

if not chain.empty:
    display_cols = [
        "symbol", "strikePrice", "option_type", "ltp", "tradeVolume",
        "openInterest", "changeInOpenInterest", "delta", "gamma", "theta", "vega", "impliedVolatility"
    ]
    cols = [c for c in display_cols if c in chain.columns]
    view = chain.copy()

    if option_type_choice in ["CE", "PE"] and "option_type" in view.columns:
        view = view[view["option_type"] == option_type_choice]

    if cols and not view.empty:
        st.dataframe(view[cols], use_container_width=True, hide_index=True)

# =========================================================
# SYSTEMATIC TRADE SIGNAL EXECUTION PIPELINE
# =========================================================

st.divider()
st.subheader("🎯 AI Trade Ideas")

st.write(
    "Live session: Technical structure + Open Interest distribution + Institutional flows generate real-time ideas."
    if market_open() else
    "After-market session: System formulates structured paper-trading setups for the NEXT SESSION. Inconclusive setups default to NO TRADE."
)

if st.button("🚀 GENERATE TRADE IDEAS", type="primary", use_container_width=True):
    with st.spinner("Processing technical structures and institutional parameters..."):
        ideas = []
        bound_side = option_type_choice if option_type_choice in ["CE", "PE"] else None

        # 1. Selected Index Cash Spot
        base_idea = make_trade_idea(
            market,
            underlying,
            instrument="INDEX",
            expiry=selected_expiry,
            chain=chain,
        )
        if base_idea:
            ideas.append(base_idea)

        # 2. Selected Index Derivative
        opt_idea = make_trade_idea(
            market,
            underlying,
            instrument="INDEX OPTION",
            option_side=bound_side,
            expiry=selected_expiry,
            chain=chain,
        )
        if opt_idea:
            ideas.append(opt_idea)

        # 3. Alternate Index Evaluations
        for alt_symbol in ["BANKNIFTY", "NIFTY", "SENSEX"]:
            if alt_symbol != underlying:
                alt_market = analyze_market(alt_symbol, derivatives_proxy)
                alt_idea = make_trade_idea(alt_market, alt_symbol, instrument="INDEX")
                if alt_idea:
                    ideas.append(alt_idea)

        unique_ideas = []
        seen = set()
        for id_item in ideas:
            key = (id_item["segment"], id_item["symbol"], id_item["action"], id_item.get("option"), str(id_item.get("strike")))
            if key not in seen:
                seen.add(key)
                unique_ideas.append(id_item)

        ideas = unique_ideas[:5]

    if not ideas:
        st.warning("Market conditions indicate structural ambiguity or neutral alignment. No systematic trade generated.")
        if not market_open():
            st.info("After-market perspective: Higher timeframe confirmation required before establishing forward session risk.")
    else:
        st.success(f"{len(ideas)} systematic trade structure(s) identified.")

        for i, idea in enumerate(ideas, start=1):
            st.markdown(
                f"""
                <div class="trade-card">
                <h3>Trade Setup {i} — {idea['symbol']}</h3>
                <div class="small">
                Segment: {idea['segment']} | Holding Period: {idea['holding']} |
                Institutional Origin: {idea.get('institutional_source', 'NONE')}
                </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Action", idea["action"])
            with c2:
                st.metric("Confidence", f"{idea['confidence']:.0f}%")
            with c3:
                st.metric("Entry Level", fmt(idea["entry"]))
            with c4:
                st.metric("Risk / Reward", f"1:{idea['risk_reward']:.2f}")

            c5, c6, c7, c8 = st.columns(4)
            with c5:
                st.metric("Stop Loss", fmt(idea["sl"]))
            with c6:
                st.metric("Target 1", fmt(idea["target1"]))
            with c7:
                st.metric("Target 2", fmt(idea["target2"]))
            with c8:
                st.metric("Instrument", f"{idea['option']} {idea.get('strike', '-')}" if idea.get("option") else "SPOT")

            s1, s2, s3 = st.columns(3)
            with s1:
                st.metric("Technical Score", f"{idea.get('technical_score', 0):.0f}")
            with s2:
                st.metric("Institutional Score", f"{idea.get('institutional_score', 0):+.0f}")
            with s3:
                st.metric("Institutional Bias", idea.get("institutional_bias", "Unavailable"))

            if idea.get("expiry"):
                st.write(f"**Contract Expiry:** {expiry_label(idea['expiry'])}")

            if idea.get("option_ltp") is not None:
                st.write(f"**Contract Premium LTP:** ₹{fmt(idea['option_ltp'])}")

            if idea.get("option"):
                g1, g2, g3, g4 = st.columns(4)
                with g1:
                    st.metric("Open Interest", fmt(idea.get("oi"), 0))
                with g2:
                    st.metric("Change in OI", fmt(idea.get("change_oi"), 0))
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
                    st.metric("IV (%)", fmt(idea.get("iv"), 2))

            st.markdown(f"""
            <div class="reason">
            <b>Setup Logic:</b> {idea['why']}
            </div>
            """, unsafe_allow_html=True)

            st.write(f"**Structural Invalidation:** {idea['invalidation']}")
            st.write("**Trailing Guidance:** Target 1 hit hone par SL ko entry cost ya immediate swing boundary par trail karein.")
            st.divider()

        if GEMINI_API_KEY:
            with st.spinner("Formulating AI synthesis..."):
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
                        "institutional_source": market.get("institutional_source", "NONE"),
                    }
                )

            if ai_text:
                st.subheader("🤖 AI Explanation")
                st.write(ai_text)
        else:
            st.info("Gemini API key missing. Operating in deterministic quantitative rules mode.")

st.divider()
st.caption("Paper Trading Mode • Deterministic Quantitative Rules Engine • Real-Time Order Routing Disabled.")
