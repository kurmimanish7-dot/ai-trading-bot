import streamlit as st

st.set_page_config(
    page_title="AI Trading Bot",
    page_icon="📈",
    layout="wide"
)

st.title("📈 AI Trading Bot")
st.subheader("Paper Trading Dashboard")

st.info("Paper Trading Mode is ON")

st.write("### System Status")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Trading Mode", "PAPER")

with col2:
    st.metric("Market", "NSE")

with col3:
    st.metric("Status", "Ready")

st.write("---")
st.write("### Risk Controls")

st.write("✅ Maximum Daily Loss: ₹2,000")
st.write("✅ Maximum Trades Per Day: 5")
st.write("✅ Maximum Position: 50")
st.write("✅ Minimum AI Confidence: 75%")

st.write("---")
st.caption("AI Trading Bot — Paper Trading Only")
