import streamlit as st
import pandas as pd
import numpy as np

from telemetry_engine import TelemetryEngine


st.set_page_config(
    page_title="AI Trading App",
    page_icon="📈",
    layout="wide",
)


# ============================================================
# SAMPLE MARKET DATA
# ============================================================

def create_sample_candles(rows=150):

    timestamps = pd.date_range(
        end=pd.Timestamp.now(),
        periods=rows,
        freq="5min",
    )

    base_price = 25000.0

    prices = (
        base_price
        + np.arange(rows) * 4.0
        + np.sin(np.arange(rows) / 5.0) * 35.0
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
# APP HEADER
# ============================================================

st.title("📈 Personal AI Trading App")

st.caption(
    "AI-assisted market research and paper-trading dashboard"
)

st.warning(
    "PAPER TRADING ONLY — NO REAL ORDERS"
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("⚙️ Trading Settings")

symbol = st.sidebar.selectbox(
    "Instrument",
    [
        "NIFTY26SEPFUT",
        "BANKNIFTY",
    ],
)

interval = st.sidebar.selectbox(
    "Candle Interval",
    [
        "FIVE_MINUTE",
        "ONE_MINUTE",
        "FIFTEEN_MINUTE",
    ],
)

analysis_mode = st.sidebar.selectbox(
    "Analysis Mode",
    [
        "Technical",
        "Technical + AI",
        "Strategy Research",
    ],
)


# ============================================================
# OFFLINE MARKET DATA
# ============================================================

df = create_sample_candles()

indicators = (
    TelemetryEngine.calculate_indicators(df)
)


# ============================================================
# MARKET SNAPSHOT
# ============================================================

st.subheader("Market Snapshot")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "LTP",
        f"₹{indicators['ltp']}",
    )

with col2:
    st.metric(
        "RSI",
        indicators["rsi"],
    )

with col3:
    st.metric(
        "VWAP",
        f"₹{indicators['vwap']}",
    )

with col4:
    st.metric(
        "ADX",
        indicators["adx"],
    )


# ============================================================
# TREND STATUS
# ============================================================

st.subheader("Market Analysis")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.write("**EMA Trend**")
    st.info(
        indicators["ema_trend"]
    )

with col2:
    st.write("**Supertrend**")
    st.info(
        indicators["supertrend"]
    )

with col3:
    st.write("**VWAP Position**")
    st.info(
        indicators["price_vs_vwap"]
    )

with col4:
    st.write("**Market Regime**")
    st.info(
        indicators["market_regime"]
    )


# ============================================================
# CHART
# ============================================================

st.subheader("📊 Price Chart")

chart_data = df.set_index(
    "timestamp"
)[["close"]]

st.line_chart(
    chart_data
)


# ============================================================
# CURRENT PAPER SIGNAL
# ============================================================

st.subheader("🤖 Paper Trading Signal")

if (
    indicators["ema_trend"] == "BULLISH"
    and indicators["supertrend"] == "BULLISH"
    and indicators["price_vs_vwap"] == "ABOVE"
):

    signal = "ENTER_LONG"

elif (
    indicators["ema_trend"] == "BEARISH"
    and indicators["supertrend"] == "BEARISH"
    and indicators["price_vs_vwap"] == "BELOW"
):

    signal = "ENTER_SHORT"

else:

    signal = "NO_TRADE"


if signal == "ENTER_LONG":

    st.success("🟢 ENTER LONG")

elif signal == "ENTER_SHORT":

    st.error("🔴 ENTER SHORT")

else:

    st.warning("🟡 NO TRADE")


# ============================================================
# TRADE PLAN
# ============================================================

st.subheader("🎯 Paper Trade Plan")

ltp = indicators["ltp"]
atr = indicators["atr"]

if signal == "ENTER_LONG":

    stop_loss = ltp - (1.0 * atr)
    target_1 = ltp + (1.5 * atr)
    target_2 = ltp + (2.5 * atr)

elif signal == "ENTER_SHORT":

    stop_loss = ltp + (1.0 * atr)
    target_1 = ltp - (1.5 * atr)
    target_2 = ltp - (2.5 * atr)

else:

    stop_loss = 0
    target_1 = 0
    target_2 = 0


col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "Entry",
        f"₹{ltp}",
    )

with col2:
    st.metric(
        "Stop Loss",
        f"₹{stop_loss:.2f}",
    )

with col3:
    st.metric(
        "Target 1",
        f"₹{target_1:.2f}",
    )


st.metric(
    "Target 2",
    f"₹{target_2:.2f}",
)


# ============================================================
# RECENT CANDLES
# ============================================================

with st.expander(
    "🕯️ Recent Candles"
):

    st.dataframe(
        df.tail(10),
        use_container_width=True,
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

st.subheader("🛡️ System Status")

status_data = {
    "Component": [
        "Market Data",
        "Technical Engine",
        "Risk Manager",
        "Paper Broker",
        "AI Layer",
        "Real Orders",
    ],
    "Status": [
        "OFFLINE TEST DATA",
        "READY",
        "READY",
        "READY",
        "READY",
        "DISABLED",
    ],
}

st.table(
    pd.DataFrame(status_data)
)


st.caption(
    "This dashboard currently uses simulated test candles. "
    "No real market order is sent."
)
