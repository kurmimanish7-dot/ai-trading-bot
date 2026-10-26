
import streamlit as st
import requests

st.set_page_config(page_title="Angel SmartAPI Test V3")

st.title("Angel Login Test V3 - SmartConnect")

# Show secrets
st.subheader("Secrets Found")
for k in st.secrets.keys():
    st.write(f"{k} = {len(str(st.secrets[k]))} chars")

# Get secrets with all variations
api_key = ""
client_id = ""
password = ""
totp_secret = ""

for k in ["ANGEL_API_KEY", "API_KEY"]:
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

st.write(f"API_KEY: {bool(api_key)} | CLIENT: {client_id} | PWD: {bool(password)} | TOTP: {bool(totp_secret)}")

if st.button("Test with SmartConnect Library"):
    try:
        from SmartApi import SmartConnect
        import pyotp
        
        if not api_key or not client_id:
            st.error("Keys missing")
        else:
            totp_code = pyotp.TOTP(totp_secret).now() if totp_secret else ""
            st.write(f"TOTP: {totp_code}")
            
            st.write("Creating SmartConnect...")
            obj = SmartConnect(api_key=api_key)
            
            st.write(f"Logging in with {client_id}...")
            data = obj.generateSession(client_id, password, totp_code)
            
            st.write("Login response:")
            st.json(data)
            
            if data and data.get("status") == True:
                st.success("Login SUCCESS! Now testing 22750 CE LTP")
                
                # Try to get LTP
                try:
                    # Get master
                    master_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
                    mr = requests.get(master_url, timeout=10)
                    if mr.status_code == 200:
                        instruments = mr.json()
                        for inst in instruments:
                            if not isinstance(inst, dict):
                                continue
                            sym = str(inst.get("symbol", "")).upper()
                            # Look for NIFTY 22750 CE with recent expiry
                            if "NIFTY" in sym and "22750" in sym and "CE" in sym:
                                st.write(f"Found: {sym} token {inst.get('token')}")
                                token = str(inst.get("token", ""))
                                exch = inst.get("exch_seg", "NFO")
                                try:
                                    ltp_data = obj.ltpData(exch, sym, token)
                                    st.json(ltp_data)
                                    if ltp_data and ltp_data.get("status") == True:
                                        ltp = ltp_data.get("data", {}).get("ltp")
                                        st.success(f"LTP for {sym}: ₹{ltp} - BROKER MATCHED!")
                                        break
                                except Exception as e:
                                    st.error(f"LTP error for {sym}: {e}")
                                    continue
                except Exception as e:
                    st.error(f"LTP fetch error: {e}")
                    import traceback
                    st.text(traceback.format_exc())
            else:
                st.error(f"Login failed: {data}")
                
    except ImportError as e:
        st.error(f"SmartConnect library not installed: {e}")
        st.write("Add to requirements.txt: smartapi-python")
    except Exception as e:
        st.error(f"Exception: {e}")
        import traceback
        st.text(traceback.format_exc())

if st.button("Test with Direct REST - 3 payload variations"):
    try:
        import pyotp
        totp_code = pyotp.TOTP(totp_secret).now() if totp_secret else ""
        st.write(f"TOTP: {totp_code}")
        
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
        
        payloads = [
            {"clientcode": client_id, "password": password, "totp": totp_code, "note": "lowercase clientcode"},
            {"clientCode": client_id, "password": password, "totp": totp_code, "note": "camelCase clientCode"},
            {"client_code": client_id, "password": password, "totp": totp_code, "note": "snake_case client_code"},
        ]
        
        for p in payloads:
            note = p.pop("note")
            st.write(f"Trying {note}: {p}")
            try:
                r = requests.post(login_url, json=p, headers=headers, timeout=10)
                st.write(f"Status: {r.status_code}")
                st.json(r.json())
                if r.status_code == 200 and r.json().get("status") == True:
                    st.success(f"SUCCESS with {note}!")
                    break
            except Exception as e:
                st.error(f"Error with {note}: {e}")
                
    except Exception as e:
        st.error(f"Exception: {e}")
        import traceback
        st.text(traceback.format_exc())
