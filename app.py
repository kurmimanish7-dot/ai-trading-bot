import os, json, time
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo

import streamlit as st
import pandas as pd
import numpy as np
from SmartApi import SmartConnect

from telemetry_engine import TelemetryEngine
from advanced_analysis import build_advanced_analysis
from options_engine import OptionsEngine
from ea_pipeline import EAPipeline

try:
    from google import genai
except Exception:
    genai = None

st.set_page_config(page_title="AI Trading Bot", page_icon="📈", layout="wide")

if st.session_state.get("initialized") is not True:
    st.session_state.initialized = True
    st.session_state.smart_api = None
    st.session_state.jwt = None
    st.session_state.feed_token = None
    st.session_state.analysis = None
    st.session_state.analysis_key = None
    st.session_state.analysis_time = 0.0
    st.session_state.ai_result = None
    st.session_state.ai_time = 0.0
    st.session_state.last_error = ""
    st.session_state.last_ltp = None
    st.session_state.last_ltp_time = 0.0
    st.session_state.equity_master = None

st.markdown("""
<style>
*{animation:none!important;transition:none!important}
.metric-card,.signal-card{border:1px solid rgba(128,128,128,.3);border-radius:12px;padding:12px;margin-bottom:10px}
.metric-label{font-size:12px;opacity:.7}.metric-value{font-size:22px;font-weight:700;overflow-wrap:anywhere}.signal-value{font-size:27px;font-weight:800}
</style>
""", unsafe_allow_html=True)

PAPER_TRADING = True
IST = ZoneInfo("Asia/Kolkata")
MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"

INSTRUMENTS = {
    "NIFTY 50":{"exchange":"NSE","exchange_type":1,"token_secret":"NIFTY_TOKEN","token":"99926000","symbol":"NIFTY","option_name":"NIFTY"},
    "BANK NIFTY":{"exchange":"NSE","exchange_type":1,"token_secret":"BANKNIFTY_TOKEN","token":"99926009","symbol":"BANKNIFTY","option_name":"BANKNIFTY"},
    "SENSEX":{"exchange":"BSE","exchange_type":3,"token_secret":"SENSEX_TOKEN","token":None,"symbol":"SENSEX","option_name":"SENSEX"},
}


def secret(name):
    v=os.getenv(name)
    if v: return str(v)
    try:
        v=st.secrets.get(name)
        return str(v) if v else None
    except Exception: return None


def credentials():
    return {"api_key":secret("ANGEL_API_KEY"),"client_code":secret("ANGEL_CLIENT_CODE"),"pin":secret("ANGEL_PIN"),"totp":secret("ANGEL_TOTP_SECRET")}


def market_open():
    now=datetime.now(IST)
    if now.weekday()>=5: return False
    return dtime(9,15)<=now.time()<=dtime(15,30)


def fmt(v, digits=2):
    if v is None: return "DATA UNAVAILABLE"
    try:
        x=float(v)
        if not np.isfinite(x): return "DATA UNAVAILABLE"
        return f"{x:,.{digits}f}"
    except Exception: return str(v)


def card(label,value):
    st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>',unsafe_allow_html=True)


def login():
    c=credentials()
    if not all(c.values()): return None,"Angel One credentials incomplete."
    if st.session_state.smart_api is not None and st.session_state.jwt: return st.session_state.smart_api,None
    try:
        import pyotp
        api=SmartConnect(api_key=c["api_key"])
        s=api.generateSession(c["client_code"],c["pin"],pyotp.TOTP(c["totp"]).now())
        if not s or not s.get("status"): return None,str(s)
        data=s.get("data") or {}
        jwt=data.get("jwtToken")
        if not jwt: return None,"Angel One login returned no jwtToken."
        st.session_state.smart_api=api
        st.session_state.jwt=jwt
        try: st.session_state.feed_token=api.getfeedToken()
        except Exception: st.session_state.feed_token=None
        return api,None
    except Exception as e: return None,str(e)


def selected_equity(df, exchange, symbol):
    if df is None or df.empty: return None
    x=df[(df.exchange==exchange)&(df.symbol==symbol)]
    return x.iloc[0].to_dict() if not x.empty else None

@st.cache_data(ttl=3600,show_spinner=False)
def load_master():
    try:
        import requests
        r=requests.get(MASTER_URL,timeout=30); r.raise_for_status(); data=r.json()
        rows=[]
        for x in data:
            if not isinstance(x,dict): continue
            ex=str(x.get("exch_seg","")).upper(); typ=str(x.get("instrumenttype","")).upper()
            sym=str(x.get("symbol","")).strip(); tok=str(x.get("token","")).strip()
            if ex in ("NSE","BSE") and sym and tok and (typ=="EQ" or typ==""):
                rows.append({"exchange":ex,"symbol":sym,"name":str(x.get("name","")).strip(),"token":tok})
        return pd.DataFrame(rows).drop_duplicates(["exchange","symbol","token"]).sort_values(["exchange","symbol"]).reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame()


def ltp(api, exchange, symbol, token):
    if api is None or not token: return None
    try:
        r=api.ltpData(exchange,symbol,str(token))
        d=(r or {}).get("data") or {}
        v=d.get("ltp")
        return float(v) if v is not None else None
    except Exception: return None


def option_contracts(api, underlying, expiry, spot):
    if api is None or not expiry or not spot: return {},"Missing option prerequisites."
    try:
        oe=OptionsEngine(st.session_state.jwt,credentials()["api_key"],credentials()["client_code"])
        chain=oe.get_option_chain(underlying,expiry,float(spot),strikes_each_side=8)
        greeks=oe.greeks_dataframe(oe.get_option_greeks(underlying,expiry))
        pcrdf=oe.pcr_dataframe(oe.get_pcr(underlying,expiry))
        contracts=[]
        if chain is None: chain=pd.DataFrame()
        g=greeks.copy() if isinstance(greeks,pd.DataFrame) else pd.DataFrame()
        for _,r in chain.iterrows():
            typ=str(r.get("option_type",r.get("optionType",""))).upper()
            if typ in ("CALL","C"): typ="CE"
            if typ in ("PUT","P"): typ="PE"
            strike=pd.to_numeric(r.get("strike"),errors="coerce")
            if pd.isna(strike): continue
            row={"symbol":r.get("symbol"),"strike":float(strike),"option_type":typ,"ltp":r.get("ltp"),"bid":r.get("bid",r.get("best_5_buy_data")),"ask":r.get("ask",r.get("best_5_sell_data")),"volume":r.get("tradeVolume",r.get("volume")),"oi":r.get("opnInterest",r.get("oi")),"change_oi":r.get("change_oi",r.get("changeOI"))}
            if not g.empty:
                gs=g.copy(); gs["_strike"]=pd.to_numeric(gs.get("strikePrice"),errors="coerce")
                if "optionType" in gs: gs["_type"]=gs.optionType.astype(str).str.upper().replace({"CALL":"CE","PUT":"PE","C":"CE","P":"PE"})
                m=gs[(gs._strike-round(float(strike),4)).abs()<.01] if "_strike" in gs else pd.DataFrame()
                if "_type" in gs: m=m[m._type==typ]
                if not m.empty:
                    z=m.iloc[0]
                    for a,b in [("impliedVolatility","iv"),("delta","delta"),("gamma","gamma"),("theta","theta"),("vega","vega")]: row[b]=z.get(a)
            contracts.append(row)
        pcr=None
        if isinstance(pcrdf,pd.DataFrame) and not pcrdf.empty:
            for col in ("pcr","putCallRatio","put_call_ratio"):
                if col in pcrdf: 
                    vals=pd.to_numeric(pcrdf[col],errors="coerce").dropna()
                    if not vals.empty: pcr=float(vals.iloc[-1]); break
        return {"contracts":contracts,"pcr":pcr,"chain":chain,"greeks":greeks,"pcr_df":pcrdf},None
    except Exception as e: return {},f"Options data unavailable: {e}"


def expiry_days(exp):
    if not exp:return None
    for f in ("%d%b%Y","%d-%b-%Y","%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
        try:return float((datetime.strptime(exp.upper(),f).date()-date.today()).days)
        except ValueError:pass
    return None


def equity_decision(tech, market, instrument):
    score=float(tech.get("score",0) or 0); direction=str(tech.get("direction","NEUTRAL")).upper()
    tf=market.get("mtf",{}); base=tf.get("5M") or tf.get("15M") or {}
    price=base.get("price"); atr=base.get("atr");
    if price is None or atr is None or direction=="NEUTRAL":
        return {"status":"OK","decision":"WAIT","direction":direction,"final_score":score,"reasons":["Equity technical confluence not confirmed or ATR unavailable."],"paper_trading":True}
    price=float(price); atr=float(atr)
    if direction=="LONG": sl=price-1.2*atr; t1=price+1.5*atr; t2=price+2.5*atr
    else: sl=price+1.2*atr; t1=price-1.5*atr; t2=price-2.5*atr
    risk=abs(price-sl); rr=abs(t2-price)/risk if risk else 0
    decision="TRADE_CANDIDATE" if score>=70 and rr>=1.5 else "WAIT"
    return {"status":"OK","decision":decision,"instrument":instrument,"direction":direction,"underlying":{"price":price,"atr":atr},"risk":{"entry":price,"stop_loss":sl,"target1":t1,"target2":t2,"trailing_sl":(price+risk if direction=="LONG" else price-risk)},"scores":{"technical":score,"options":None,"final_confluence":score},"rr":rr,"reasons":[f"Technical confluence: {score:.1f}/100","Equity setup uses ATR-based risk levels."],"paper_trading":True}


def compact_ai_payload(a):
    if not a:return {}
    return {k:a.get(k) for k in ("status","decision","direction","scores","option","risk","reasons") if k in a}


def ask_ai(payload,instrument):
    key=secret("GEMINI_API_KEY")
    if not key or genai is None:return {"status":"UNAVAILABLE","reason":"Gemini unavailable; deterministic EA remains active."}
    try:
        model=secret("AI_MODEL") or "gemini-3.6-flash"
        client=genai.Client(api_key=key)
        prompt="""You are a neutral Indian-market analysis assistant. Paper trading only. Interpret ONLY supplied structured EA data. Never invent unavailable news, VIX, OI, PCR or Greeks. Do not override a DATA_UNAVAILABLE/NO_TRADE decision. Return concise JSON with view, rationale and risks."""+f"\nInstrument: {instrument}\nDATA:\n{json.dumps(payload,default=str)}"
        r=client.models.generate_content(model=model,contents=prompt)
        return {"status":"OK","text":getattr(r,"text","") or "No AI commentary returned."}
    except Exception as e:return {"status":"UNAVAILABLE","reason":f"Gemini unavailable: {e}"}


# ---------------- UI ----------------
st.title("📈 AI Trading Bot — Expert Advisor")
st.caption("Multi-timeframe technical + options intelligence | PAPER TRADING ONLY")
st.info("🛡️ NO REAL ORDERS — this app is analysis/paper-trading only.")

with st.sidebar:
    st.header("⚙️ Controls")
    instrument_type=st.selectbox("Instrument",["NIFTY 50","BANK NIFTY","SENSEX","EQUITY"])
    analysis_mode=st.radio("Analysis Mode",["Technical Only","Technical + AI"])
    refresh=st.slider("EA analysis refresh (seconds)",30,300,60,10)
    days=st.select_slider("Historical data",options=[5,10,20,30],value=10)
    if instrument_type=="EQUITY":
        master=load_master()
        ex=st.selectbox("Exchange",["NSE","BSE"])
        syms=master.loc[master.exchange==ex,"symbol"].tolist() if not master.empty else []
        equity_symbol=st.selectbox("Equity",syms) if syms else None
        selected=selected_equity(master,ex,equity_symbol) if equity_symbol else None
        market_exchange=ex; market_symbol=equity_symbol; market_token=selected.get("token") if selected else None; exchange_type=1 if ex=="NSE" else 3
    else:
        x=INSTRUMENTS[instrument_type]
        market_exchange=x["exchange"]; market_symbol=x["symbol"]; market_token=secret(x["token_secret"]) or x["token"]; exchange_type=x["exchange_type"]
    expiry=None
    if instrument_type in ("NIFTY 50","BANK NIFTY"):
        expiry=st.text_input("Expiry Date","",placeholder="29SEP2026",help="DDMMMYYYY")
    run=st.button("🔄 Run / Refresh EA Analysis",use_container_width=True)
    if not market_open(): st.caption("Market closed: Mon–Fri 09:15–15:30 IST")

api,login_error=login()
if login_error: st.session_state.last_error=login_error

live=ltp(api,market_exchange,market_symbol,market_token) if market_token else None
if live is not None: st.session_state.last_ltp=live; st.session_state.last_ltp_time=time.time()
else: live=st.session_state.last_ltp

key=f"{instrument_type}|{market_exchange}|{market_token}|{expiry}|{days}"
need=run or st.session_state.analysis is None or st.session_state.analysis_key!=key or time.time()-st.session_state.analysis_time>=refresh

if api and market_token and need:
    try:
        pipe=EAPipeline(smart_api=api,technical_score=65,option_score=65,final_score=70,minimum_rr=1.5)
        market=pipe.run_market_analysis(market_exchange,str(market_token),market_symbol,days=days)
        tech=pipe.run_technical_analysis(market)
        opt={"status":"DATA_UNAVAILABLE","contracts":[]}
        opt_msg=""
        if instrument_type in ("NIFTY 50","BANK NIFTY") and expiry and live:
            od,opt_msg=option_contracts(api,INSTRUMENTS[instrument_type]["option_name"],expiry,live)
            opt=od or opt
            opt["expiry"]=expiry
        if instrument_type in ("NIFTY 50","BANK NIFTY"):
            decision=pipe.run_decision(market,tech,opt,symbol=market_symbol)
        elif instrument_type=="EQUITY":
            decision=equity_decision(tech,market,market_symbol)
        else:
            decision={"status":"DATA_UNAVAILABLE","decision":"NO_TRADE","direction":tech.get("direction","NEUTRAL"),"scores":{"technical":tech.get("score",0),"options":None,"final_confluence":tech.get("score",0)},"reasons":["SENSEX options require BSE-specific option-chain integration; no fake option data used."],"paper_trading":True}
        result={"market":market,"technical":tech,"options":opt,"decision":decision,"options_message":opt_msg,"generated_at":datetime.now(IST).isoformat()}
        st.session_state.analysis=result; st.session_state.analysis_key=key; st.session_state.analysis_time=time.time(); st.session_state.last_error=opt_msg or ""
    except Exception as e:
        st.session_state.last_error=f"EA pipeline error: {e}"

res=st.session_state.analysis or {}
market=res.get("market",{}); tech=res.get("technical",{}); opt=res.get("options",{}); dec=res.get("decision",{})

# Header metrics
st.subheader(f"📌 {instrument_type}" + (f" — {market_symbol}" if instrument_type=="EQUITY" else ""))
a,b,c,d=st.columns(4)
with a: card("LIVE LTP",fmt(live))
with b: card("TECHNICAL SCORE",fmt(tech.get("score"),1))
with c: card("FINAL CONFLUENCE",fmt((dec.get("scores") or {}).get("final_confluence"),1))
with d: card("DECISION",dec.get("decision","DATA UNAVAILABLE"))

st.markdown("### 🎯 Expert Advisor Signal")
sig=dec.get("decision","DATA UNAVAILABLE"); direction=dec.get("direction",tech.get("direction","NEUTRAL"))
st.markdown(f'<div class="signal-card"><div class="metric-label">DIRECTION / DECISION</div><div class="signal-value">{direction} / {sig}</div></div>',unsafe_allow_html=True)
for r in dec.get("reasons",[])[:8]: st.write("• "+str(r))

st.markdown("### 📊 Multi-Timeframe Analysis")
mtf=market.get("mtf") or market.get("timeframes") or {}
rows=[]
for tf in ("1M","3M","5M","15M","30M","1H"):
    x=mtf.get(tf,{})
    if x: rows.append({"TF":tf,"Price":fmt(x.get("price")),"EMA Trend":x.get("ema_trend","—"),"RSI":fmt(x.get("rsi"),1),"ADX":fmt(x.get("adx"),1),"VWAP":x.get("price_vs_vwap","—"),"MACD":x.get("macd_bias","—"),"Structure":x.get("market_structure","—"),"Candle":x.get("candle_pattern","—")})
if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
else: st.warning("DATA UNAVAILABLE — no multi-timeframe candles returned.")

st.markdown("### 🔧 Technical Confluence")
cols=st.columns(4)
with cols[0]: card("Direction",tech.get("direction","NEUTRAL"))
with cols[1]: card("Score",fmt(tech.get("score"),1))
with cols[2]: card("Decision",tech.get("decision","WAIT"))
with cols[3]: card("Status",tech.get("status","DATA_UNAVAILABLE"))

# Selected timeframe detail
base=(mtf.get("5M") or mtf.get("15M") or mtf.get("1H") or {})
tab=st.tabs(["Price Action","Risk Plan","Options Intelligence","AI Analysis"])
with tab[0]:
    pcols=st.columns(4)
    with pcols[0]: card("RSI",fmt(base.get("rsi"),1))
    with pcols[1]: card("ATR",fmt(base.get("atr")))
    with pcols[2]: card("VWAP",fmt(base.get("vwap")))
    with pcols[3]: card("EMA Trend",base.get("ema_trend","—"))
    st.write("**Market regime:**",base.get("market_regime","—"))
    st.write("**Candle pattern:**",base.get("candle_pattern","—"))
    st.write("**Market structure:**",base.get("market_structure","—"))
    st.write("**Support:**",fmt(base.get("support"))," | **Resistance:**",fmt(base.get("resistance")))
with tab[1]:
    risk=dec.get("risk") or {}
    if instrument_type=="EQUITY":
        rr=dec.get("rr")
        card("R:R to T2",fmt(rr,2))
        r=risk
        st.dataframe(pd.DataFrame([{"Entry":fmt(r.get("entry")),"SL":fmt(r.get("stop_loss")),"T1":fmt(r.get("target1")),"T2":fmt(r.get("target2")),"Trailing SL":fmt(r.get("trailing_sl"))}]),use_container_width=True,hide_index=True)
    else:
        orisk=risk.get("option") if isinstance(risk,dict) else {}
        u=risk.get("underlying") if isinstance(risk,dict) else {}
        st.write("**Underlying risk levels**",u)
        st.write("**Option risk levels**",orisk)
with tab[2]:
    if instrument_type=="EQUITY": st.info("Equity mode: index-option intelligence is not used.")
    elif instrument_type=="SENSEX": st.warning("SENSEX option chain/Greeks/PCR are DATA UNAVAILABLE until BSE-specific implementation is added. No fake values.")
    else:
        setup=dec.get("option") or {}
        st.write("**Selected candidate:**",setup or "DATA UNAVAILABLE")
        if opt.get("chain") is not None and isinstance(opt.get("chain"),pd.DataFrame) and not opt["chain"].empty:
            st.dataframe(opt["chain"].head(20),use_container_width=True,hide_index=True)
        else: st.info("Option chain unavailable for selected expiry.")
with tab[3]:
    if analysis_mode=="Technical + AI":
        now=time.time()
        if st.session_state.ai_result is None or now-st.session_state.ai_time>=300:
            st.session_state.ai_result=ask_ai(compact_ai_payload(dec),market_symbol); st.session_state.ai_time=now
        ai=st.session_state.ai_result or {}
        st.write(ai.get("text") or ai.get("reason","AI unavailable; deterministic EA remains active."))
    else: st.info("Technical Only selected — Gemini is not called.")

st.markdown("### 🖥️ System Status")
s=st.columns(4)
with s[0]: card("Paper Trading","ON")
with s[1]: card("Angel One","CONNECTED" if api else "NOT CONNECTED")
with s[2]: card("EA Pipeline","READY" if res else "WAITING")
with s[3]: card("Gemini","READY" if secret("GEMINI_API_KEY") else "NOT CONFIGURED")

if st.session_state.last_error:
    with st.expander("⚠️ Latest System Message"): st.write(st.session_state.last_error)
st.caption("Market hours: Monday–Friday 09:15–15:30 IST. Outside hours live values may remain unchanged.")
