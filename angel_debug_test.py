import streamlit as st
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")

st.set_page_config(page_title="Angel LTP Test - 22750 CE")

st.title("Angel 22750 CE LTP Test - Debug")

# Show secrets status
st.subheader("Secrets Status")
try:
    for k in st.secrets.keys():
        st.write(f"Found key: {k} = {len(str(st.secrets[k]))} chars")
except Exception as e:
    st.error(f"No secrets: {e}")

api_key = st.secrets.get("ANGEL_API_KEY", "") if "ANGEL_API_KEY" in st.secrets else ""
client_id = st.secrets.get("ANGEL_CLIENT_ID", "") if "ANGEL_CLIENT_ID" in st.secrets else ""
password = st.secrets.get("ANGEL_PASSWORD", "") if "ANGEL_PASSWORD" in st.secrets else ""
totp_secret = st.secrets.get("ANGEL_TOTP_SECRET", "") if "ANGEL_TOTP_SECRET" in st.secrets else ""

st.write(f"ANGEL_API_KEY present: {bool(api_key)}")
st.write(f"ANGEL_CLIENT_ID present: {bool(client_id)}")
st.write(f"ANGEL_PASSWORD present: {bool(password)}")
st.write(f"ANGEL_TOTP_SECRET present: {bool(totp_secret)}")

if st.button("Test Angel Login for 22750 CE"):
    try:
        import pyotp
        totp_code = pyotp.TOTP(totp_secret).now() if totp_secret else ""
        st.write(f"TOTP generated: {totp_code}")

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
        payload = {
            "clientcode": client_id,
            "password": password,
            "totp": totp_code
        }
        st.write("Logging in...")
        r = requests.post(login_url, json=payload, headers=headers, timeout=10)
        st.write(f"Login status: {r.status_code}")
        st.json(r.json())
        
        if r.status_code == 200:
            resp = r.json()
            if resp.get("status"):
                jwt = resp.get("data", {}).get("jwtToken")
                st.success(f"Login OK, JWT found: {bool(jwt)}")
                # Try LTP
                ltp_url = "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/getLTP"
                ltp_headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-UserType": "USER",
                    "X-SourceID": "WEB",
                    "X-ClientLocalIP": "192.168.1.1",
                    "X-ClientPublicIP": "106.193.147.98",
                    "X-MACAddress": "fe80::a2e8:8bff:fe00:1234",
                    "X-PrivateKey": api_key,
                    "Authorization": f"Bearer {jwt}"
                }
                # Try with known token for NIFTY 22750 CE - approximate token
                # We need to search master
                master_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
                mr = requests.get(master_url, timeout=12)
                st.write(f"Master status: {mr.status_code}, size: {len(mr.text)}")
                if mr.status_code == 200:
                    instruments = mr.json()
                    candidates = []
                    for inst in instruments:
                        if isinstance(inst, dict):
                            sym = str(inst.get("symbol", "")).upper()
                            if "NIFTY" in sym and "22750" in sym and "CE" in sym:
                                candidates.append(inst)
                    st.write(f"Found {len(candidates)} candidates for 22750 CE")
                    for c in candidates[:3]:
                        st.json(c)
                        # Try LTP
                        try:
                            payload_ltp = {
                                "exchange": c.get("exch_seg", "NFO"),
                                "tradingsymbol": c.get("symbol"),
                                "symboltoken": str(c.get("token"))
                            }
                            lr = requests.post(ltp_url, json=payload_ltp, headers=ltp_headers, timeout=8)
                            st.write(f"LTP for {c.get('symbol')}: {lr.status_code}")
                            st.json(lr.json())
                        except Exception as e:
                            st.error(str(e))
            else:
                st.error(f"Login failed: {resp}")
    except Exception as e:
        st.error(f"Exception: {e}")
        import traceback
        st.text(traceback.format_exc())
              
