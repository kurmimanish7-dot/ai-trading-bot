# -*- coding: utf-8 -*-
"""
Angel Data Source - FINAL FIX V6 - SENSEX 05 Nov Bug Fixed
Root cause: SENSEX 05 Nov 2026 is Thursday but SENSEX weekly is Tuesday
So Angel may have token as SENSEX05NOV2674500CE but expiry field 26NOV2026? No
Fix: Use BOTH tradingsymbol AND expiry field, match EITHER, and log
"""

import datetime
from datetime import datetime, timedelta, date
import re
import requests
import time

_MASTER_CACHE = None
_MASTER_CACHE_TIME = 0
_MASTER_CACHE_TTL = 300

KNOWN_INDEX_TOKENS = {
    "NIFTY": "99926000",
    "BANKNIFTY": "99926009",
    "FINNIFTY": "99926037",
    "SENSEX": "99919000",
    "MIDCPNIFTY": "99926034",
    "BANKEX": "99919001",
}

def parse_expiry_from_tradingsymbol_ULTIMATE(tradingsym: str, symbol: str = ""):
    try:
        sym = tradingsym.upper().strip()
        idx_names = ["BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "BANKEX", "NIFTY", "SENSEX"]
        remaining = sym
        for name in sorted(idx_names, key=len, reverse=True):
            if sym.startswith(name):
                remaining = sym[len(name):]
                break
        # Try DDMMMYYYY first (9 chars) - SENSEX05NOV202674500CE
        if len(remaining) >= 9:
            candidate_9 = remaining[:9]
            m = re.match(r'^(\d{2})([A-Z]{3})(\d{4})$', candidate_9)
            if m:
                day_str, mon_str, yr_str = m.groups()
                rest = remaining[9:]
                if re.match(r'^\d+CE$|^\d+PE$', rest):
                    day = int(day_str)
                    yr = int(yr_str)
                    mon_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                    mon = mon_map.get(mon_str.upper(), 0)
                    if mon and 1 <= day <= 31 and 2020 <= yr <= 2035:
                        return date(yr, mon, day)
        # Try DDMMMYY (7 chars) - SENSEX05NOV2674500CE
        if len(remaining) >= 7:
            candidate_7 = remaining[:7]
            m = re.match(r'^(\d{2})([A-Z]{3})(\d{2})$', candidate_7)
            if m:
                day_str, mon_str, yr_str = m.groups()
                rest = remaining[7:]
                if re.match(r'^\d+CE$|^\d+PE$', rest):
                    day = int(day_str)
                    yr = int(yr_str)
                    if yr < 100:
                        yr = 2000 + yr
                    mon_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                    mon = mon_map.get(mon_str.upper(), 0)
                    if mon and 1 <= day <= 31 and 2020 <= yr <= 2035:
                        return date(yr, mon, day)
        return None
    except:
        return None

def parse_expiry_to_date_ULTIMATE(s: str):
    if not s or str(s).strip() in ["", "-1", "None"]:
        return None
    s = str(s).strip().upper()
    # Try direct formats
    for fmt in ["%d%b%Y", "%d %b %Y", "%d-%b-%Y", "%d%b%y", "%d %b %y", "%Y-%m-%d", "%d-%m-%Y"]:
        try:
            test_s = s
            if "%b" in fmt:
                # Convert 05NOV2026 to 05 Nov 2026 format for parsing
                m = re.search(r'(\d{2})([A-Z]{3})(\d{2,4})', s)
                if m:
                    d, mon, y = m.groups()
                    if len(y) == 2:
                        y = "20" + y
                    if " " in fmt:
                        test_s = f"{d} {mon.title()} {y}"
                    elif "-" in fmt:
                        test_s = f"{d}-{mon.title()}-{y}"
                    else:
                        test_s = f"{d}{mon.title()}{y}"
            dt = datetime.strptime(test_s, fmt)
            return dt.date()
        except:
            continue
    # Regex fallback
    for pat in [r'(\d{2})([A-Z]{3})(\d{4})', r'(\d{2})([A-Z]{3})(\d{2})']:
        m = re.search(pat, s)
        if m:
            day_str, mon_str, yr_str = m.groups()
            try:
                day = int(day_str)
                yr = int(yr_str)
                if len(yr_str) == 2:
                    yr = 2000 + yr
                mon_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                mon = mon_map.get(mon_str, 0)
                if mon:
                    return date(yr, mon, day)
            except:
                continue
    return None

def get_angel_master_ULTIMATE(force_refresh=False):
    global _MASTER_CACHE, _MASTER_CACHE_TIME
    now = time.time()
    if not force_refresh and _MASTER_CACHE is not None and (now - _MASTER_CACHE_TIME) < _MASTER_CACHE_TTL:
        return _MASTER_CACHE
    try:
        master_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        r = requests.get(master_url, timeout=15)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")
        instruments = r.json()
        _MASTER_CACHE = instruments
        _MASTER_CACHE_TIME = now
        return instruments
    except Exception as e:
        if _MASTER_CACHE is not None:
            return _MASTER_CACHE
        return []

def get_all_expiries_for_dropdown_correct(symbol: str):
    try:
        instruments = get_angel_master_ULTIMATE()
        filtered = []
        sym_upper = symbol.upper().strip()
        for inst in instruments:
            if not isinstance(inst, dict):
                continue
            if str(inst.get("exch_seg","")).upper() not in ["NFO", "BFO"]:
                continue
            if "FUT" in str(inst.get("instrumenttype","")).upper():
                continue
            tradingsym = str(inst.get("symbol","")).upper()
            if sym_upper == "NIFTY":
                if not tradingsym.startswith("NIFTY") or any(x in tradingsym for x in ["FINNIFTY", "BANKNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]):
                    continue
            elif "BANKNIFTY" in sym_upper:
                if "BANKNIFTY" not in tradingsym:
                    continue
            elif "FINNIFTY" in sym_upper:
                if "FINNIFTY" not in tradingsym:
                    continue
            elif "SENSEX" in sym_upper and "BANKEX" not in sym_upper:
                if "SENSEX" not in tradingsym or "BANKEX" in tradingsym:
                    continue
            elif "BANKEX" in sym_upper:
                if "BANKEX" not in tradingsym:
                    continue
            exp_date = parse_expiry_from_tradingsymbol_ULTIMATE(tradingsym, sym_upper)
            if not exp_date:
                exp_raw = str(inst.get("expiry","")).strip()
                exp_date = parse_expiry_to_date_ULTIMATE(exp_raw)
            if exp_date:
                filtered.append(exp_date)
        unique = sorted(list(set(filtered)))
        today = datetime.now().date()
        future = [d for d in unique if d >= today - timedelta(days=7) and d <= today + timedelta(days=180)]
        return [d.strftime("%d %b %Y") for d in (future if future else unique)[:6]]
    except:
        return []

# FINAL FIX - NO FALLBACK EVER - EXACT ONLY
def get_angel_ltp_EXACT_EXPIRY_ONLY(symbol: str, strike: int, opt_type: str, expiry: str, api_key="", client_id="", password="", totp_secret=""):
    target_symbol = symbol.upper().strip()
    target_strike = int(strike)
    target_opt = opt_type.upper().strip()
    target_exp_date = parse_expiry_to_date_ULTIMATE(expiry)
    if not target_exp_date:
        target_exp_date = parse_expiry_from_tradingsymbol_ULTIMATE(expiry, target_symbol)
    if not target_exp_date:
        return 0, f"INVALID_EXPIRY_{expiry}_CANNOT_PARSE", False
    
    try:
        instruments = get_angel_master_ULTIMATE()
        candidates_exact = []
        all_sensex_74500_debug = []
        
        for inst in instruments:
            if not isinstance(inst, dict):
                continue
            exch = str(inst.get("exch_seg","")).upper()
            if exch not in ["NFO", "BFO"]:
                continue
            if "FUT" in str(inst.get("instrumenttype","")).upper():
                continue
            if "OPT" not in str(inst.get("instrumenttype","")).upper():
                continue
            tradingsym = str(inst.get("symbol","")).upper()
            
            # DEBUG: Collect all SENSEX 74500 CE for analysis
            if target_symbol == "SENSEX" and target_strike == 74500 and "74500" in tradingsym and tradingsym.endswith("CE") and "SENSEX" in tradingsym and "BANKEX" not in tradingsym:
                exp_debug = parse_expiry_from_tradingsymbol_ULTIMATE(tradingsym, target_symbol)
                if not exp_debug:
                    exp_debug = parse_expiry_to_date_ULTIMATE(str(inst.get("expiry","")))
                all_sensex_74500_debug.append(f"{tradingsym}|Exp:{exp_debug}|Token:{inst.get('token','')}|ExpiryField:{inst.get('expiry','')}")
            
            # Filter by symbol
            if target_symbol == "NIFTY":
                if not tradingsym.startswith("NIFTY") or any(x in tradingsym for x in ["FINNIFTY", "BANKNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]):
                    continue
            elif "BANKNIFTY" in target_symbol:
                if "BANKNIFTY" not in tradingsym:
                    continue
            elif "FINNIFTY" in target_symbol:
                if "FINNIFTY" not in tradingsym:
                    continue
            elif "SENSEX" in target_symbol and "BANKEX" not in target_symbol:
                if "SENSEX" not in tradingsym or "BANKEX" in tradingsym:
                    continue
            elif "BANKEX" in target_symbol:
                if "BANKEX" not in tradingsym:
                    continue
            
            # Strike check
            try:
                inst_strike_raw = inst.get("strike", -1)
                inst_strike = int(float(inst_strike_raw) / 100) if float(inst_strike_raw) > 1000 else int(float(inst_strike_raw))
            except:
                continue
            if inst_strike != target_strike:
                continue
            
            # Opt type check
            if target_opt == "CE" and not tradingsym.endswith("CE"):
                continue
            if target_opt == "PE" and not tradingsym.endswith("PE"):
                continue
            
            # Expiry check - EXACT ONLY - Try both tradingsymbol and expiry field
            inst_exp_date = parse_expiry_from_tradingsymbol_ULTIMATE(tradingsym, target_symbol)
            if not inst_exp_date:
                inst_expiry_raw = str(inst.get("expiry","")).strip()
                inst_exp_date = parse_expiry_to_date_ULTIMATE(inst_expiry_raw)
            
            if not inst_exp_date:
                continue
            if inst_exp_date != target_exp_date:
                continue
            
            token = str(inst.get("token",""))
            if token:
                candidates_exact.append({'token': token, 'tradingsym': tradingsym, 'expiry': inst_exp_date})
        
        # DEBUG for SENSEX 05 Nov
        debug_msg = ""
        if target_symbol == "SENSEX" and target_strike == 74500 and target_exp_date == date(2026, 11, 5):
            debug_msg = f"DEBUG_SENSEX_05NOV: Target {target_exp_date}, Found {len(candidates_exact)} exact, All 74500 tokens in master: {all_sensex_74500_debug[:3]}"
        
        if not candidates_exact:
            if all_sensex_74500_debug:
                return 0, f"NO_EXACT_05NOV_BUT_MASTER_HAS_{len(all_sensex_74500_debug)}_TOKENS_{all_sensex_74500_debug[:2]}_TARGET_{target_exp_date}_DEBUG_{debug_msg}", False
            return 0, f"NO_CANDIDATE_EXACT_{target_symbol}_{target_strike}{target_opt}_EXP_{target_exp_date.strftime('%d%b%Y')}_MASTER_{len(instruments)}_{debug_msg}", False
        
        # Fetch LTP
        try:
            from SmartApi import SmartConnect
            import pyotp
            if not api_key or not client_id:
                return 0, f"NO_CREDS_CAND_{len(candidates_exact)}_{debug_msg}", False
            
            obj = SmartConnect(api_key=api_key)
            totp = pyotp.TOTP(totp_secret).now() if totp_secret else ""
            sess = obj.generateSession(client_id, password, totp)
            if not sess or not sess.get('status'):
                return 0, f"SESSION_FAILED_{debug_msg}", False
            
            best_ltp = 0
            best_cand = None
            for cand in candidates_exact:
                try:
                    exchange = "BFO" if "SENSEX" in target_symbol or "BANKEX" in target_symbol else "NFO"
                    ltp_data = obj.ltpData(exchange, cand['tradingsym'], cand['token'])
                    if ltp_data and ltp_data.get('status'):
                        ltp = float(ltp_data.get('data', {}).get('ltp', 0))
                        if ltp > 0 and ltp < 10000:
                            if best_ltp == 0 or ltp < best_ltp:
                                best_ltp = ltp
                                best_cand = cand
                except:
                    continue
            
            if best_cand and best_ltp > 0:
                return best_ltp, f"ANGEL_EXACT_{target_symbol}_{target_strike}{target_opt}_EXP_{target_exp_date.strftime('%d%b%Y')}_LTP_{best_ltp}_TOKEN_{best_cand['token']}_{debug_msg}", True
            
            return 0, f"LTP_FAILED_CAND_{len(candidates_exact)}_{debug_msg}", False
            
        except Exception as e:
            return 0, f"EXC_{str(e)[:100]}_{debug_msg}", False
            
    except Exception as e:
        return 0, f"OUTER_EXC_{str(e)[:150]}", False

def get_angel_ltp_100pct_broker_match(symbol="NIFTY", strike=0, opt_type="CE", expiry=""):
    try:
        import streamlit as st
        api_key = st.secrets.get("ANGEL_API_KEY", "") or st.secrets.get("API_KEY", "")
        client_id = st.secrets.get("ANGEL_CLIENT_ID", "") or st.secrets.get("CLIENT_ID", "")
        password = st.secrets.get("ANGEL_PASSWORD", "") or st.secrets.get("PASSWORD", "")
        totp_secret = st.secrets.get("ANGEL_TOTP_SECRET", "") or st.secrets.get("TOTP_SECRET", "")
        return get_angel_ltp_EXACT_EXPIRY_ONLY(symbol, strike, opt_type, expiry, api_key, client_id, password, totp_secret)
    except:
        return get_angel_ltp_EXACT_EXPIRY_ONLY(symbol, strike, opt_type, expiry)
