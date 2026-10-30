
import streamlit as st
import requests
import re
from datetime import datetime

st.set_page_config(page_title="Angel SmartAPI Test V4 - FIXED", layout="wide")
st.title("Angel Login Test V4 - FIXED (Expiry + All Tokens)")

# Secrets
st.subheader("Secrets Status")
for k in st.secrets.keys():
    st.write(f"{k} = {len(str(st.secrets[k]))} chars ✅")

api_key = client_id = password = totp_secret = ""
for k in ["ANGEL_API_KEY", "API_KEY", "SMARTAPI_KEY"]:
    if k in st.secrets:
        api_key = str(st.secrets[k]).strip()
        break
for k in ["ANGEL_CLIENT_ID", "ANGEL_CLIENT_CODE", "CLIENT_ID", "CLIENT_CODE"]:
    if k in st.secrets:
        client_id = str(st.secrets[k]).strip()
        break
for k in ["ANGEL_PASSWORD", "ANGEL_PIN", "PASSWORD", "PIN"]:
    if k in st.secrets:
        password = str(st.secrets[k]).strip()
        break
for k in ["ANGEL_TOTP_SECRET", "TOTP_SECRET"]:
    if k in st.secrets:
        totp_secret = str(st.secrets[k]).strip()
        break

col1, col2, col3, col4 = st.columns(4)
col1.metric("API_KEY", "✅" if api_key else "❌")
col2.metric("CLIENT", client_id if client_id else "❌")
col3.metric("PWD", "✅" if password else "❌")
col4.metric("TOTP", "✅" if totp_secret else "❌")

if st.button("🔍 Test NIFTY 23050 CE 03 Nov 2026 - ALL TOKENS (Fixes 294 bug)"):
    try:
        from SmartApi import SmartConnect
        import pyotp
        
        if not api_key or not client_id:
            st.error("Keys missing")
            st.stop()
            
        totp_code = pyotp.TOTP(totp_secret).now() if totp_secret else ""
        st.info(f"TOTP: {totp_code}")
        
        obj = SmartConnect(api_key=api_key)
        data = obj.generateSession(client_id, password, totp_code)
        
        if not (data and data.get("status") == True):
            st.error(f"Login failed: {data}")
            st.stop()
        
        st.success("Login SUCCESS!")
        st.json(data)
        
        # V45 logic: Check ALL tokens for 23050 CE 03 Nov
        target_strike = 23050
        target_opt = "CE"
        target_expiry = datetime(2026, 11, 3)  # 03 Nov 2026
        
        master_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        mr = requests.get(master_url, timeout=15)
        instruments = mr.json()
        
        candidates = []
        for inst in instruments:
            if not isinstance(inst, dict): continue
            if str(inst.get("exch_seg","")).upper() not in ["NFO","BFO"]: continue
            if "FUT" in str(inst.get("instrumenttype","")).upper(): continue
            sym = str(inst.get("symbol","")).upper()
            if not sym.startswith("NIFTY"): continue
            if any(x in sym for x in ["FINNIFTY","BANKNIFTY","MIDCPNIFTY"]): continue
            
            # Strike exact
            strike_raw = inst.get("strike")
            extracted = None
            if strike_raw is not None and str(strike_raw) not in ["","-1","-1.000000","0","0.000000"]:
                try:
                    s_val = float(strike_raw)
                    if s_val > 100000: s_val = s_val/100.0
                    extracted = int(round(s_val))
                except: pass
            if extracted is None:
                m = re.search(r'(\d{4,6})\s*(CE|PE)\s*$', sym)
                if m:
                    try: extracted = int(m.group(1))
                    except: pass
            if extracted != target_strike: continue
            
            # Option type
            if target_opt not in sym: continue
            
            # Expiry strict
            exp_raw = str(inst.get("expiry","")).strip()
            exp_dt = None
            if exp_raw:
                for fmt in ["%d%b%Y","%d%b%y","%d-%b-%Y"]:
                    try:
                        exp_dt = datetime.strptime(exp_raw.replace(" ","").upper(), fmt)
                        break
                    except: continue
            if not exp_dt:
                m_exp = re.search(r'(\d{2})([A-Z]{3})(\d{2,4})', sym)
                if m_exp:
                    day, mon, yr = m_exp.groups()
                    yr_full = "20"+yr if len(yr)==2 else yr
                    try: exp_dt = datetime.strptime(f"{day}{mon}{yr_full}", "%d%b%Y")
                    except: pass
            if exp_dt and exp_dt.date() != target_expiry.date(): continue
            
            candidates.append((inst, sym, exp_raw, exp_dt))
        
        st.write(f"Found {len(candidates)} candidates for 23050 CE 03 Nov")
        
        # Try ALL tokens
        results = []
        for inst, sym, exp_raw, exp_dt in candidates:
            token = str(inst.get("token",""))
            exch = inst.get("exch_seg","NFO")
            try:
                ltp_data = obj.ltpData(exch, sym, token)
                if ltp_data and ltp_data.get("status")==True:
                    ltp = ltp_data.get("data",{}).get("ltp",0)
                    if ltp and float(ltp)>0:
                        f_ltp = float(ltp)
                        exp_str = exp_dt.strftime("%d%b%Y") if exp_dt else exp_raw
                        results.append((f_ltp, sym, token, exp_str))
                        st.write(f"✅ {sym} token {token} EXP {exp_str} LTP ₹{f_ltp}")
                    else:
                        st.write(f"❌ {sym} token {token} NO LTP")
            except Exception as e:
                st.write(f"❌ {sym} EXC {e}")
        
        if results:
            results.sort(key=lambda x: x[0])
            st.success(f"All LTPs: {results}")
            # Sanity: Filter >250 for near expiry
            filtered = [r for r in results if r[0] <= 250]
            best = filtered[0] if filtered else results[0]
            st.metric("Best LTP (Weekly Fixed)", f"₹{best[0]}", delta=f"{best[1]} token {best[2]}")
            
            if best[0] > 250:
                st.warning("LTP >250 for 4-day expiry - likely monthly! Check other tokens")
            else:
                st.success(f"CORRECT WEEKLY LTP: ₹{best[0]} (should be ~110.65, not 294.80)")
        else:
            st.error("No LTP found")
            
    except Exception as e:
        st.error(f"Exception: {e}")
        import traceback
        st.text(traceback.format_exc())

if st.button("Test Direct REST"):
    try:
        import pyotp
        totp_code = pyotp.TOTP(totp_secret).now() if totp_secret else ""
        login_url = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "192.168.1.1",
            "X-ClientPublicIP": "106.193.147.98",
            "X-MACAddress": "fe80::a2e8:8bff:fe00:1234",
            "X-PrivateKey": api_key
        }
        payload = {"clientcode": client_id, "password": password, "totp": totp_code}
        r = requests.post(login_url, json=payload, headers=headers, timeout=10)
        st.json(r.json())
    except Exception as e:
        st.error(str(e))
